from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import html
import time
from collections import defaultdict
from typing import Final, List, Dict
from telegram.ext import ContextTypes, CallbackContext
from config import Config

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    Message,
)
from telegram.error import TelegramError
from telegram.ext import (
    MessageHandler, CallbackQueryHandler, ConversationHandler, filters
)
from states import IssueStates

from send_monitor import (
    safe_send_message,
    safe_reply_text,
    safe_delete_message,
)
from database import Database
from tracker_client import TrackerAPI
from keyboards import (
    main_reply_keyboard,
    register_keyboard,
)
from messages import (
    NO_ISSUES,
    ISSUES_LIST,
    ENTER_ISSUE_TITLE,
    TITLE_EMPTY,
    ENTER_ISSUE_DESCRIPTION,
    ASK_FOR_ATTACHMENTS,
    UNSUPPORTED_FILE,
    FILES_UPLOADED,
    TELEGRAM_DOWNLOAD_FAILED,
    FILE_UPLOAD_FAILED,
    ALBUM_FILE_FAILED,
    FILE_TOO_LARGE,
    ISSUE_CREATED,
    ISSUE_CREATION_ERROR,
    COMMENT_PROMPT,
    NO_ISSUE_SELECTED,
    COMMENT_ADDED,
    NOT_REGISTERED,
    REQUEST_PENDING,
)
from handlers_common import check_rate_limit, show_main_reply_menu

# ──────────────────────────── буфер медиа‑альбомов ─────────────────────────────

_album_buffer: Dict[str, List[Message]] = defaultdict(list)  # media_group_id -> [Message]


async def upload_file(file, bot, tracker):
    """Download a Telegram *file* and upload it to Tracker."""

    file_info = await bot.get_file(file.file_id)
    if getattr(file, "file_name", None):
        ext = os.path.splitext(file.file_name)[1] or ".jpg"
    else:
        ext = ".jpg"
    # Some albums may contain the same file multiple times which means
    # ``file_unique_id`` would be identical for each message.  In such
    # cases concurrent downloads would try to use the same path in ``/tmp``
    # leading to race conditions when deleting the temporary file.  Use a
    # unique filename instead of ``file_unique_id`` to avoid collisions.
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        temp_path = tmp.name

    await file_info.download_to_drive(temp_path)
    try:
        file_id = await tracker.upload_file(
            temp_path, getattr(file, "file_name", None)
        )
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            logging.warning("Failed to remove temporary file %s", temp_path)

    return file_id

# ═══════════════════════════ список задач ═════════════════════════════════════

async def my_issues(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет список задач пользователя за исключением закрытых.

    Функция работает и для inline-кнопок, и для текстовой команды.
    """
    logging.info("my_issues requested by %s", update.effective_user.id)
    if update.callback_query:
        allowed = await check_rate_limit(update, context, "_my_issues_ts", "получение списка задач")
        if not allowed:
            return
    # Сбрасываем временные данные, если пользователь прервал создание задачи
    context.user_data.clear()
    telegram_id = update.effective_user.id
    db: Database = context.bot_data["db"]
    if not await db.get_user(telegram_id):
        if update.callback_query:
            await update.callback_query.answer()
            await safe_reply_text(
                update.callback_query.message,
                NOT_REGISTERED,
                reply_markup=register_keyboard(),
                context=context,
            )
        elif update.message:
            await safe_reply_text(
                update.message,
                NOT_REGISTERED,
                reply_markup=register_keyboard(),
                context=context,
            )
            await safe_delete_message(update.message)
        return

    tracker: TrackerAPI = context.bot_data["tracker"]

    issues = await tracker.get_active_issues_by_telegram_id(telegram_id)
    keyboard = [
        [InlineKeyboardButton(f"{issue.get('key')}: {issue.get('summary', 'Без описания')}",
                              callback_data=f"issue_{issue['key']}")]
        for issue in issues
    ]
    keyboard.append([InlineKeyboardButton("🔄 Главное меню", callback_data="main_menu")])
    markup = InlineKeyboardMarkup(keyboard)

    if not issues:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(NO_ISSUES, reply_markup=markup)
        elif update.message:
            await safe_reply_text(update.message, NO_ISSUES, reply_markup=markup, context=context)
        if update.message:
            await safe_delete_message(update.message)
        return

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(ISSUES_LIST, reply_markup=markup)
        context.user_data["issues_list_message"] = update.callback_query.message
    elif update.message:
        sent = await safe_reply_text(update.message, ISSUES_LIST, reply_markup=markup, context=context)
        context.user_data["issues_list_message"] = sent
    if update.message:
        await safe_delete_message(update.message)

# ═══════════════════════════ создание задачи (FSM) ════════════════════════════

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

async def start_create_issue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 0 FSM: предлагаем ввести заголовок (работает с inline-кнопками и командами)."""
    logging.info("start_create_issue by %s", update.effective_user.id)
    if update.callback_query:
        allowed = await check_rate_limit(update, context, "_start_issue_ts", "создание задачи")
        if not allowed:
            return ConversationHandler.END
    db: Database = context.bot_data["db"]
    if not await db.get_user(update.effective_user.id):
        if update.callback_query:
            await update.callback_query.answer()
            await safe_reply_text(
                update.callback_query.message,
                NOT_REGISTERED,
                reply_markup=register_keyboard(),
                context=context,
            )
        elif update.message:
            await safe_reply_text(
                update.message,
                NOT_REGISTERED,
                reply_markup=register_keyboard(),
                context=context,
            )
            await safe_delete_message(update.message)
        return ConversationHandler.END
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")]
    ])
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                ENTER_ISSUE_TITLE,
                reply_markup=markup
            )
        except TelegramError as exc:
            logging.warning(
                "start_create_issue edit failed for %s: %s",
                update.effective_user.id,
                exc,
            )
            await safe_send_message(
                context.bot,
                chat_id=update.effective_chat.id,
                text=ENTER_ISSUE_TITLE,
                reply_markup=markup,
                context=context,
            )
    elif update.message:
        await safe_reply_text(
            update.message,
            ENTER_ISSUE_TITLE,
            reply_markup=markup,
            context=context,
        )
        await safe_delete_message(update.message)
    return IssueStates.waiting_for_title


# ─────────────────────────── заголовок задачи ────────────────────────────────

async def process_issue_title(update: Update, context: CallbackContext):
    logging.info("process_issue_title from %s: %s", update.effective_user.id, update.message.text)
    title = update.message.text.strip()
    if not title:
        await safe_reply_text(update.message, TITLE_EMPTY, context=context)
        return IssueStates.waiting_for_title

    context.user_data["issue_title"] = title
    await safe_reply_text(update.message, ENTER_ISSUE_DESCRIPTION,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")]])
    , context=context)
    return IssueStates.waiting_for_description

# ─────────────────────────── описание задачи ─────────────────────────────────

async def skip_issue_description(update: Update, context: CallbackContext):
    logging.info("skip_issue_description by %s", update.effective_user.id)
    context.user_data["issue_description"] = ""
    return await ask_for_attachments(update, context)

async def process_issue_description(update: Update, context: CallbackContext):
    logging.info("process_issue_description from %s: %s", update.effective_user.id, update.message.text)
    context.user_data["issue_description"] = update.message.text.strip()
    return await ask_for_attachments(update, context)

# ─────────────────────────── вложения задачи ─────────────────────────────────

async def ask_for_attachments(update: Update, context: CallbackContext):
    """Просим пользователя загрузить вложения или завершить создание."""
    logging.info("ask_for_attachments for %s", update.effective_user.id)
    await safe_reply_text(update.message, ASK_FOR_ATTACHMENTS,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Создать задачу", callback_data="create_issue")],
            [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")],
        ])
    , context=context)
    context.user_data["attachments"] = []  # обнуляем список
    return IssueStates.waiting_for_attachment

# ─────────────────────────── одиночный файл ──────────────────────────────────

async def handle_attachment(update: Update, context: CallbackContext):
    """Обрабатывает одиночное фото/документ и загружает его в Tracker."""
    logging.info("handle_attachment from %s", update.effective_user.id)
    tracker: TrackerAPI = context.bot_data["tracker"]
    attachments = context.user_data.get("attachments", [])

    file = update.message.photo[-1] if update.message.photo else update.message.document
    if not file:
        await safe_reply_text(update.message, UNSUPPORTED_FILE, context=context)
        return IssueStates.waiting_for_attachment
    if getattr(file, "file_size", 0) > Config.MAX_FILE_SIZE:
        await safe_reply_text(update.message, FILE_TOO_LARGE, context=context)
        return IssueStates.waiting_for_attachment

    try:
        file_id = await upload_file(file, context.bot, tracker)
        if not file_id:
            raise RuntimeError("upload_file вернул None")

        attachments.append(file_id)
        context.user_data["attachments"] = attachments

        await safe_reply_text(
            update.message,
            FILES_UPLOADED.format(count=len(attachments)),
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📤 Создать задачу", callback_data="create_issue")],
                    [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")],
                ]
            ),
            context=context,
        )

    except TelegramError:
        await safe_reply_text(update.message, TELEGRAM_DOWNLOAD_FAILED, context=context)
    except Exception as exc:
        logging.exception("Ошибка загрузки вложения: %s", exc)
        await safe_reply_text(update.message, FILE_UPLOAD_FAILED, context=context)

    return IssueStates.waiting_for_attachment

# ─────────────────────────── медиа‑альбом ────────────────────────────────────

async def handle_photo_or_album(update: Update, context: CallbackContext):  # noqa: C901 (размер)
    """Собирает медиа‑группу целиком, после чего загружает все файлы пачкой."""
    logging.info("handle_photo_or_album from %s", update.effective_user.id)
    if update.message.media_group_id:
        gid = update.message.media_group_id
        _album_buffer[gid].append(update.message)
        # запускаем отложенную обработку альбома только при первом фото
        if len(_album_buffer[gid]) == 1:
            asyncio.create_task(_process_album_later(gid, context))
    else:
        # одиночное фото/документ
        return await handle_attachment(update, context)

async def _process_album_later(group_id: str, context: CallbackContext):
    """Ждёт 2 секунды, чтобы Telegram прислал все фото, затем загружает."""
    logging.info("processing album %s", group_id)
    await asyncio.sleep(2)
    messages = _album_buffer.pop(group_id, [])
    if not messages:
        return

    tracker: TrackerAPI = context.bot_data["tracker"]
    attachments: List[int] = []
    chat_id = messages[0].chat_id

    files = []
    for msg in messages:
        file = msg.photo[-1] if msg.photo else msg.document
        if not file:
            continue
        if getattr(file, "file_size", 0) > Config.MAX_FILE_SIZE:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=FILE_TOO_LARGE,
                context=context,
            )
            return
        files.append(file)

    try:
        results = await asyncio.gather(
            *(upload_file(f, context.bot, tracker) for f in files)
        )
        attachments.extend([r for r in results if r])
    except Exception as exc:
        logging.exception("Ошибка загрузки из альбома: %s", exc)
        await safe_send_message(context.bot, chat_id=chat_id, text=ALBUM_FILE_FAILED, context=context)
        return  # прерываем весь альбом

    # складываем ID вложений в user_data
    context.user_data["attachments"] = context.user_data.get("attachments", []) + attachments

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=FILES_UPLOADED.format(count=len(attachments)),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Создать задачу", callback_data="create_issue")],
            [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")],
        ]),
        context=context,
    )

# ─────────────────────────── финальное подтверждение ─────────────────────────

async def confirm_issue_creation(update: Update, context: CallbackContext):
    """Создаёт задачу в Tracker и сохраняет её в БД."""
    logging.info("confirm_issue_creation by %s", update.effective_user.id)
    query = update.callback_query
    allowed = await check_rate_limit(update, context, "_create_issue_ts", "создание задачи")
    if not allowed:
        return IssueStates.waiting_for_attachment
    await query.answer()
    # Hide the inline keyboard of the confirmation message so users can't press
    # it multiple times.
    try:
        result = query.edit_message_reply_markup(reply_markup=None)
        if asyncio.iscoroutine(result):
            await result
    except TelegramError as exc:
        logging.warning("confirm_issue_creation: failed to clear markup: %s", exc)
    
    db: Database = context.bot_data["db"]
    tracker: TrackerAPI = context.bot_data["tracker"]
    user = update.effective_user

    title = context.user_data.get("issue_title")
    description = context.user_data.get("issue_description", "")
    attachments = context.user_data.get("attachments", [])

    user_info = await db.get_user(user.id) or {}
    full_description = (
        f"{description}\n\n---\n"
        f"👤 {user.first_name} {user.last_name or ''}\n"
        f"📞 {user_info.get('phone_number', 'неизвестно')}\n"
        f"🔗 @{user.username or 'без username'}"
    )

    extra_fields = {
        "telegramId": str(user.id),
        "project": Config.PROJECT,
        "tags": Config.DEFAULT_TAGS,
        Config.PRODUCT_CUSTOM_FIELD: Config.PRODUCT_DEFAULT,
    }
    if attachments:
        # При создании задачи вложения передаются через поле attachmentIds
        extra_fields["attachmentIds"] = attachments
    issue = await tracker.create_issue(title, full_description, extra_fields)
    if issue and "key" in issue:
        await db.create_issue(user.id, issue["key"])
        logging.info("issue %s created for %s", issue['key'], user.id)
        text = ISSUE_CREATED.format(issue_key=issue['key'], summary=html.escape(title))
        await safe_reply_text(
            query.message,
            text,
            parse_mode="HTML",
            reply_markup=main_reply_keyboard(),
            context=context,
        )
    else:
        await safe_reply_text(
            query.message,
            ISSUE_CREATION_ERROR,
            context=context,
        )
        logging.error("failed to create issue for %s", user.id)

    context.user_data.clear()
    return ConversationHandler.END

# ─────────────────────────── комментарий к задаче ─────────────────────────────

async def select_issue_for_comment(update: Update, context: CallbackContext):
    """Сохраняет выбранный `issue_key` и переводит FSM в режим ожидания комментария."""
    logging.info("select_issue_for_comment %s", update.callback_query.data)
    db: Database = context.bot_data["db"]
    if not await db.get_user(update.effective_user.id):
        await update.callback_query.answer()
        await safe_reply_text(
            update.callback_query.message,
            NOT_REGISTERED,
            reply_markup=register_keyboard(),
            context=context,
        )
        return ConversationHandler.END
    query = update.callback_query
    allowed = await check_rate_limit(update, context, "_comment_request_ts", "добавление комментария")
    if not allowed:
        return ConversationHandler.END

    issue_key = query.data.split("_", 1)[1]
    context.user_data["issue_key"] = issue_key
    msg = context.user_data.pop("issues_list_message", None)
    if msg:
        await safe_delete_message(msg)
    await safe_reply_text(
        query.message,
        COMMENT_PROMPT,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 Главное меню", callback_data="main_menu")]]
        ),
        context=context,
    )
    return IssueStates.waiting_for_comment

async def process_comment(update: Update, context: CallbackContext):
    """Добавляет текст и/или вложение в выбранную задачу."""
    logging.info("process_comment from %s", update.effective_user.id)
    tracker: TrackerAPI = context.bot_data["tracker"]
    issue_key: str | None = context.user_data.get("issue_key")
    if not issue_key:
        await safe_reply_text(update.message, NO_ISSUE_SELECTED, context=context)
        return ConversationHandler.END

    db: Database = context.bot_data["db"]

    text = (update.message.text or update.message.caption or "📎 Вложение").strip()
    attachment_ids: list[int] = []

    # Если в сообщении есть файл — загружаем
    if update.message.photo or update.message.document:
        file = update.message.document or update.message.photo[-1]
        if getattr(file, "file_size", 0) > Config.MAX_FILE_SIZE:
            await safe_reply_text(update.message, FILE_TOO_LARGE, context=context)
            return IssueStates.waiting_for_comment
        try:
            results = await asyncio.gather(
                upload_file(file, context.bot, tracker)
            )
            file_id = results[0]
            if file_id:
                attachment_ids.append(file_id)
        except Exception as exc:
            logging.exception("Ошибка загрузки файла комментария: %s", exc)
            await safe_reply_text(update.message, FILE_UPLOAD_FAILED, context=context)
            return IssueStates.waiting_for_comment

    user = update.effective_user
    user_info = await db.get_user(user.id) or {}
    full_text = (
        f"{text}\n\n---\n"
        f"👤 {user.first_name} {user.last_name or ''}\n"
        f"📞 {user_info.get('phone_number', 'неизвестно')}\n"
        f"🔗 @{user.username or 'без username'}\n"
        f"\n\n---\n"
    )

    await tracker.add_comment(issue_key, full_text, attachment_ids)
    logging.info("comment added to %s by %s", issue_key, user.id)

    issue = await tracker.get_issue_details(issue_key)
    summary = issue.get("summary", issue_key)
    await safe_reply_text(
        update.message,
        COMMENT_ADDED.format(issue_key=issue_key, summary=summary),
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
        context=context,
    )
    context.user_data.clear()
    return ConversationHandler.END

# ═══════════════════════════ регистрация хендлеров ════════════════════════════

def register_handlers(app):
    """Подключает все issue‑хендлеры к объекту Application."""

    # Заглушка для отмены FSM через inline-кнопку
    async def do_nothing(update, context):
        if update.callback_query:
            await update.callback_query.answer()
        await show_main_reply_menu(update, context)
        return ConversationHandler.END

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📋 Создать задачу$"), start_create_issue),
            CallbackQueryHandler(start_create_issue, pattern="^create_issue$"),
            CallbackQueryHandler(select_issue_for_comment, pattern="^issue_")
        ],
        states={
            IssueStates.waiting_for_title: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), process_issue_title),
            ],
            IssueStates.waiting_for_description: [
                MessageHandler(filters.Regex("^/skip$"), skip_issue_description),
                MessageHandler(filters.TEXT & (~filters.COMMAND), process_issue_description),
            ],
            IssueStates.waiting_for_attachment: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_photo_or_album),
                CallbackQueryHandler(confirm_issue_creation, pattern="^create_issue$")
            ],
            IssueStates.waiting_for_comment: [
                MessageHandler(filters.ALL, process_comment),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(do_nothing, pattern="^main_menu$"),
        ],
        name="issue_flow",
        per_chat=True,
    )
    app.add_handler(conv)

    # Мои задачи: поддержка и reply, и inline
    app.add_handler(MessageHandler(filters.Regex("^📂 Мои задачи$"), my_issues))
    app.add_handler(CallbackQueryHandler(my_issues, pattern="^my_issues$"))

    # Общие ловцы альбомов и вложений (если нужны вне FSM)
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_photo_or_album))

