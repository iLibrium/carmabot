from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
import aiohttp
from telegram import InputMediaPhoto, InputFile
from telegram.ext import Application
from config import Config
from tracker_client import TrackerAPI
import os

router = APIRouter()
bearer_scheme = HTTPBearer()

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

        issue = data.get("issue")
        comment_data = data.get("comment", {})
        issue_key = issue.get("key")
        comment_id = comment_data.get("id")
        issue_summary = issue.get("summary", "Нет темы")

        comment_author = await tracker.get_comment_author(issue_key, comment_id)

        issue_info = await tracker.get_issue(issue_key)
        telegram_id = issue_info.get("telegramId")
        if not telegram_id:
            logging.warning(f"❌ Не найден telegramId для задачи {issue_key}")
            return {"status": "ignored"}

        chat_id = int(telegram_id)
        attachments = await tracker.get_attachments_for_comment(issue_key, comment_id)

        media_photos = []
        documents = []

        async with aiohttp.ClientSession() as session:
            for att in attachments:
                content_url = att["content_url"]
                filename = att["filename"]
                
                async with session.get(content_url, headers=tracker.get_headers()) as resp:
                    if resp.status != 200:
                        logging.error(f"Ошибка загрузки файла {filename}: {resp.status}")
                        continue
                    file_bytes = await resp.read()

                file_path = os.path.join("/tmp", filename)
                with open(file_path, "wb") as f:
                    f.write(file_bytes)
                
                telegram_file = InputFile(file_path)
                
                if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                    media_photos.append(InputMediaPhoto(media=telegram_file))
                else:
                    documents.append(telegram_file)
        
        message_text = (
            f"💬 Добавлен комментарий - <a href='https://tracker.yandex.ru/{issue_key}'>{issue_summary}</a>\n\n"
            f"<blockquote>{comment_data.get('text', '')}</blockquote>\n\n"
            f"<b>👤 Автор комментария:</b> {comment_author}"
        )
        
        try:
            if media_photos:
                await application.bot.send_media_group(chat_id, media_photos)
            for doc in documents:
                await application.bot.send_document(chat_id, doc)
            
            await application.bot.send_message(chat_id, message_text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"❌ Ошибка при отправке сообщений в Telegram: {e}")
        
        logging.info(f"✅ Комментарий отправлен в Telegram для задачи: {issue_key}")
        return {"status": "ok"}

    app.include_router(router)