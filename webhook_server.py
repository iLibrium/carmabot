from fastapi import FastAPI, APIRouter, Request, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
import asyncio
import re
import time
from telegram import InputMediaPhoto, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from messages import WEBHOOK_COMMENT, WEBHOOK_STATUS
from telegram.ext import Application
from config import Config
from tracker_client import TrackerAPI
import os
import uuid

app = FastAPI()

router = APIRouter()
bearer_scheme = HTTPBearer()

# In-memory store of processed comment IDs with timestamp to prevent duplicates
processed_comment_ids: dict[str, float] = {}
# Time-to-live for stored comment IDs in seconds
PROCESSED_IDS_TTL = 3600


def prune_processed_ids() -> None:
    """Remove expired comment IDs from the cache."""
    now = time.time()
    expired = [cid for cid, ts in processed_comment_ids.items() if now - ts > PROCESSED_IDS_TTL]
    for cid in expired:
        processed_comment_ids.pop(cid, None)

# Regex to strip markdown image links like ![alt](url)
IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

def strip_image_links(text: str) -> str:
    """Remove markdown image links from text."""
    if not text:
        return ""
    cleaned = IMAGE_LINK_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()

def setup_webhook_routes(app, application: Application, tracker: TrackerAPI):
    """Настраивает маршруты вебхуков"""
    @router.post("/trackers/comment")
    async def receive_webhook(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
    ):
        if credentials.credentials != Config.API_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid Bearer token")
        
        data = await request.json()
        logging.info(f"📥 Webhook получен: {data}")

        if data.get("event") != "commentCreated":
            return {"status": "ignored"}

        issue = data.get("issue") or {}
        comment_data = data.get("comment", {})
        issue_key = issue.get("key")
        comment_id = comment_data.get("id")
        issue_summary = issue.get("summary", "Нет темы")

        prune_processed_ids()

        if comment_id and str(comment_id) in processed_comment_ids:
            logging.info("Duplicate comment %s ignored", comment_id)
            return {"status": "ignored"}
        if comment_id:
            processed_comment_ids[str(comment_id)] = time.time()

        telegram_id = issue.get("telegramId")

        comment_author = comment_data.get("createdBy", {}).get("display")
        if not comment_author and comment_id:
            try:
                comment_author = await tracker.get_comment_author(issue_key, comment_id)
            except Exception as exc:
                logging.error(f"Не удалось получить автора комментария: {exc}")
                comment_author = "неизвестен"

        issue_info = None
        if not telegram_id:
            try:
                issue_info = await tracker.get_issue(issue_key)
            except Exception as exc:
                logging.error(f"Не удалось получить информацию о задаче: {exc}")
                return {"status": "error"}
            telegram_id = issue_info.get("telegramId")
        if not telegram_id:
            logging.warning(f"❌ Не найден telegramId для задачи {issue_key}")
            return {"status": "ignored"}

        chat_id = int(telegram_id)
        attachments = []
        if comment_id:
            try:
                attachments = await tracker.get_attachments_for_comment(issue_key, comment_id)
            except Exception as exc:
                logging.error(f"Не удалось получить вложения комментария: {exc}")

        media_photos = []
        documents = []

        session = await tracker.get_session()

        async def download_attachment(att):
            content_url = att.get("content_url")
            filename = att.get("filename")
            if not content_url or not filename:
                logging.warning("Некорректные данные вложения: %s", att)
                return None
            async with session.get(content_url, headers=tracker.get_headers()) as resp:
                if resp.status != 200:
                    logging.error(f"Ошибка загрузки файла {filename}: {resp.status}")
                    return None
                file_bytes = await resp.read()
                is_large = len(file_bytes) > 10 * 1024 * 1024

            safe_name = os.path.basename(filename)
            unique_name = f"{uuid.uuid4().hex}_{safe_name}"
            file_path = os.path.join("/tmp", unique_name)
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            file_handle = open(file_path, "rb")
            telegram_file = InputFile(file_handle, filename=safe_name)
            if (
                filename.lower().endswith((".jpg", ".png", ".jpeg"))
                and not is_large
            ):
                return ("photo", telegram_file, file_path, file_handle)
            return ("document", telegram_file, file_path, file_handle)

        download_results = await asyncio.gather(*(download_attachment(att) for att in attachments))
        for result in download_results:
            if not result:
                continue
            kind, tg_file, file_path, handle = result
            if kind == "photo":
                media_photos.append((tg_file, file_path, handle))
            else:
                documents.append((tg_file, file_path, handle))
        
        clean_text = strip_image_links(comment_data.get("text", ""))
        message_text = WEBHOOK_COMMENT.format(
            issue_key=issue_key,
            issue_summary=issue_summary,
            text=clean_text,
            author=comment_author,
        )

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("💬 Ответить", callback_data=f"issue_{issue_key}")]]
        )

        try:
            if media_photos:
                tg_photos = [InputMediaPhoto(media=file) for file, _, _ in media_photos]
                try:
                    if len(tg_photos) > 1:
                        await application.bot.send_media_group(chat_id, tg_photos)
                    else:
                        await application.bot.send_photo(chat_id, tg_photos[0].media)
                except BadRequest as exc:

                    message = getattr(exc, "message", str(exc)).lower()
                    if "image_process_failed" in message:
                        logging.warning(
                            "Image failed to process, sending as documents: %s",
                            exc,
                        )

                    if "Image_process_failed" in str(exc):
                        logging.warning(
                            "Image failed to process, sending as documents: %s",
                            exc,
                        )

                        for doc, path, handle in media_photos:
                            try:
                                await application.bot.send_document(chat_id, doc)
                            finally:
                                if not handle.closed:
                                    handle.close()
                                try:
                                    os.remove(path)
                                except OSError as exc:
                                    logging.error(
                                        "Не удалось удалить временный файл %s: %s",
                                        path,
                                        exc,
                                    )
                    else:
                        raise
                finally:
                    for _, path, handle in media_photos:
                        if not handle.closed:
                            handle.close()
                        if os.path.exists(path):
                            try:
                                os.remove(path)
                            except OSError as exc:
                                logging.error(
                                    "Не удалось удалить временный файл %s: %s",
                                    path,
                                    exc,
                                )

            for doc, path, handle in documents:
                try:
                    await application.bot.send_document(chat_id, doc)
                finally:
                    if not handle.closed:
                        handle.close()
                    try:
                        os.remove(path)
                    except OSError as exc:
                        logging.error(
                            "Не удалось удалить временный файл %s: %s",
                            path,
                            exc,
                        )

            await application.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

        except Exception as e:
            logging.error(f"❌ Ошибка при отправке сообщений в Telegram: {e}")
        
        logging.info(f"✅ Комментарий отправлен в Telegram для задачи: {issue_key}")
        return {"status": "ok"}

    @router.post("/trackers/updateStatus")
    async def receive_status_webhook(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
    ):
        if credentials.credentials != Config.API_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid Bearer token")

        data = await request.json()
        logging.info(f"📥 Status webhook получен: {data}")

        if data.get("event") != "issueUpdated":
            return {"status": "ignored"}

        issue = data.get("issue") or {}
        issue_key = issue.get("key")
        issue_summary = issue.get("summary", "Нет темы")
        telegram_id = issue.get("telegramId")

        changed_by = data.get("changedBy") or data.get("updatedBy") or {}
        if isinstance(changed_by, dict):
            changed_by = changed_by.get("display") or changed_by.get("login")

        status_data = data.get("status") or data.get("newStatus") or {}
        status_name = (
            status_data.get("display")
            or status_data.get("name")
            or status_data.get("key")
        )

        issue_info = None
        if not telegram_id:
            try:
                issue_info = await tracker.get_issue(issue_key)
            except Exception as exc:
                logging.error(f"Не удалось получить информацию о задаче: {exc}")
                return {"status": "error"}
            telegram_id = issue_info.get("telegramId")
        if not telegram_id:
            logging.warning(f"❌ Не найден telegramId для задачи {issue_key}")
            return {"status": "ignored"}

        chat_id = int(telegram_id)

        message_text = WEBHOOK_STATUS.format(
            issue_key=issue_key,
            issue_summary=issue_summary,
            status_name=status_name,
            changed_by=changed_by,
        )

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("💬 Ответить", callback_data=f"issue_{issue_key}")]]
        )

        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception as e:
            logging.error(f"❌ Ошибка при отправке сообщений в Telegram: {e}")

        logging.info(f"✅ Изменение статуса отправлено в Telegram для задачи: {issue_key}")
        return {"status": "ok"}

    app.include_router(router)
