from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Final, List, Dict
from telegram.ext import ContextTypes, CallbackContext

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
from states import IssueStates

from send_monitor import safe_send_message, safe_reply_text
from database import Database
from tracker_client import TrackerAPI
from states import IssueStates
from keyboards import (
    main_reply_keyboard,
)

# ──────────────────────────── буфер медиа‑альбомов ─────────────────────────────

_album_buffer: Dict[str, List[Message]] = defaultdict(list)  # media_group_id -> [Message]

# ═══════════════════════════ список задач ═════════════════════════════════════

async def my_issues(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет список задач пользователя за исключением закрытых.

    Функция работает и для inline-кнопок, и для текстовой команды.
    """
    telegram_id = update.effective_user.id
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
            await update.callback_query.edit_message_text("📭 У вас нет задач.", reply_markup=markup)
        elif update.message:
            await update.message.reply_text("📭 У вас нет задач.", reply_markup=markup)
        return

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("📂 Ваши задачи:", reply_markup=markup)
    elif update.message:
        await update.message.reply_text("📂 Ваши задачи:", reply_markup=markup)

# ═══════════════════════════ создание задачи (FSM) ════════════════════════════

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

async def start_create_issue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 0 FSM: предлагаем ввести заголовок (работает с inline-кнопками и командами)."""
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")]
    ])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "📋 Введите заголовок задачи:",
            reply_markup=markup
        )
    elif update.message:
        await update.message.reply_text(
            "📋 Введите заголовок задачи:",
            reply_markup=markup
        )
    return IssueStates.waiting_for_title


# ─────────────────────────── заголовок задачи ────────────────────────────────

async def process_issue_title(update: Update, context: CallbackContext):
    title = update.message.text.strip()
    if not title:
        await safe_reply_text(update.message, "❌ Заголовок не может быть пустым. Повторите ввод:")
        return IssueStates.waiting_for_title

    context.user_data["issue_title"] = title
    await safe_reply_text(update.message, "📝 Введите описание задачи (или отправьте /skip):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")]])
    )
    return IssueStates.waiting_for_description

# ─────────────────────────── описание задачи ─────────────────────────────────

async def skip_issue_description(update: Update, context: CallbackContext):
    context.user_data["issue_description"] = ""
    return await ask_for_attachments(update, context)

async def process_issue_description(update: Update, context: CallbackContext):
    context.user_data["issue_description"] = update.message.text.strip()
    return await ask_for_attachments(update, context)

# ─────────────────────────── вложения задачи ─────────────────────────────────

async def ask_for_attachments(update: Update, context: CallbackContext):
    """Просим пользователя загрузить вложения или завершить создание."""
    await safe_reply_text(update.message, "📎 Прикрепите фото или нажмите 📤 Создать задачу:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Создать задачу", callback_data="create_issue")],
            [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")],
        ])
    )
    context.user_data["attachments"] = []  # обнуляем список
    return IssueStates.waiting_for_attachment

# ─────────────────────────── одиночный файл ──────────────────────────────────

async def handle_attachment(update: Update, context: CallbackContext):
    """Обрабатывает одиночное фото/документ и загружает его в Tracker."""
    tracker: TrackerAPI = context.bot_data["tracker"]
    attachments = context.user_data.get("attachments", [])

    file = update.message.photo[-1] if update.message.photo else update.message.document
    if not file:
        await safe_reply_text(update.message, "❌ Поддерживаются только фото или документы.")
        return IssueStates.waiting_for_attachment

    try:
        file_info = await context.bot.get_file(file.file_id)
        filename = f"{file.file_unique_id}.jpg"
        temp_path = os.path.join("/tmp", filename)

        await file_info.download_to_drive(temp_path)
        file_id = await tracker.upload_file(temp_path)
        os.remove(temp_path)

        if not file_id:
            raise RuntimeError("upload_file вернул None")

        attachments.append(file_id)
        context.user_data["attachments"] = attachments

        await safe_reply_text(update.message, f"📎 Загружено файлов: {len(attachments)}. Добавьте ещё или нажмите 📤 Создать задачу.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Создать задачу", callback_data="create_issue")],
                [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")],
            ])
        )

    except TelegramError:
        await safe_reply_text(update.message, "❌ Не удалось получить файл из Telegram. Попробуйте снова.")
    except Exception as exc:
        logging.exception("Ошибка загрузки вложения: %s", exc)
        await safe_reply_text(update.message, "❌ Не удалось загрузить файл. Попробуйте ещё раз…")

    return IssueStates.waiting_for_attachment

# ─────────────────────────── медиа‑альбом ────────────────────────────────────

async def handle_photo_or_album(update: Update, context: CallbackContext):  # noqa: C901 (размер)
    """Собирает медиа‑группу целиком, после чего загружает все файлы пачкой."""
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
    await asyncio.sleep(2)
    messages = _album_buffer.pop(group_id, [])
    if not messages:
        return

    tracker: TrackerAPI = context.bot_data["tracker"]
    attachments: List[int] = []
    chat_id = messages[0].chat_id

    for msg in messages:
        file = msg.photo[-1] if msg.photo else msg.document
        if not file:
            continue
        try:
            file_info = await context.bot.get_file(file.file_id)
            filename = f"{file.file_unique_id}.jpg"
            temp_path = os.path.join("/tmp", filename)
            await file_info.download_to_drive(temp_path)
            file_id = await tracker.upload_file(temp_path)
            os.remove(temp_path)
            if file_id:
                attachments.append(file_id)
        except Exception as exc:
            logging.exception("Ошибка загрузки из альбома: %s", exc)
            await safe_send_message(context.bot, chat_id=chat_id, text="❌ Не удалось загрузить одно из фото. Отправьте альбом снова.")
            return  # прерываем весь альбом

    # складываем ID вложений в user_data
    context.user_data["attachments"] = context.user_data.get("attachments", []) + attachments

    await context.bot.send_message(
        chat_id,
        text=f"📎 Загружено файлов: {len(attachments)}. Добавьте ещё или нажмите 📤 Создать задачу.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Создать задачу", callback_data="create_issue")],
            [InlineKeyboardButton("🔄 Отмена", callback_data="main_menu")],
        ])
    )

# ─────────────────────────── финальное подтверждение ─────────────────────────

async def confirm_issue_creation(update: Update, context: CallbackContext):
    """Создаёт задачу в Tracker и сохраняет её в БД."""
    query = update.callback_query
    await query.answer()

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

    extra_fields = {"telegramId": str(user.id)}
    if attachments:
        # При создании задачи вложения передаются через поле attachmentIds
        extra_fields["attachmentIds"] = attachments
    issue = await tracker.create_issue(title, full_description, extra_fields)
    if issue and "key" in issue:
        await db.create_issue(user.id, issue["key"])
        await query.message.reply_text(
            f"✅ Задача <a href='https://tracker.yandex.ru/{issue['key']}'>{issue['key']}</a> успешно создана!",
            parse_mode="HTML",
            reply_markup=main_reply_keyboard(),  # показываем reply‑меню
        )
    else:
        await query.message.reply_text("❌ Ошибка при создании задачи. Попробуйте позже.")

    context.user_data.clear()
    return ConversationHandler.END

# ─────────────────────────── комментарий к задаче ─────────────────────────────

async def select_issue_for_comment(update: Update, context: CallbackContext):
    """Сохраняет выбранный `issue_key` и переводит FSM в режим ожидания комментария."""
    query = update.callback_query
    issue_key = query.data.split("_", 1)[1]
    context.user_data["issue_key"] = issue_key
    await query.message.reply_text(
        "📝 Напишите комментарий или прикрепите файл…",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 Главное меню", callback_data="main_menu")]]
        ),
    )
    return IssueStates.waiting_for_comment

async def process_comment(update: Update, context: CallbackContext):
    """Добавляет текст и/или вложение в выбранную задачу."""
    tracker: TrackerAPI = context.bot_data["tracker"]
    issue_key: str | None = context.user_data.get("issue_key")
    if not issue_key:
        await safe_reply_text(update.message, "❌ Сначала выберите задачу в списке.")
        return ConversationHandler.END

    db: Database = context.bot_data["db"]

    text = (update.message.text or update.message.caption or "📎 Вложение").strip()
    attachment_ids: list[int] = []

    # Если в сообщении есть файл — загружаем
    if update.message.photo or update.message.document:
        file = update.message.document or update.message.photo[-1]
        try:
            file_info = await context.bot.get_file(file.file_id)
            filename = f"{file.file_unique_id}.jpg"
            temp_path = os.path.join("/tmp", filename)
            await file_info.download_to_drive(temp_path)
            file_id = await tracker.upload_file(temp_path)
            os.remove(temp_path)
            if file_id:
                attachment_ids.append(file_id)
        except Exception as exc:
            logging.exception("Ошибка загрузки файла комментария: %s", exc)
            await safe_reply_text(update.message, "❌ Не удалось загрузить файл. Попробуйте ещё раз…")
            return IssueStates.waiting_for_comment

    user = update.effective_user
    user_info = await db.get_user(user.id) or {}
    full_text = (
        f"{text}\n\n---\n"
        f"👤 {user.first_name} {user.last_name or ''}\n"
        f"📞 {user_info.get('phone_number', 'неизвестно')}\n"
        f"🔗 @{user.username or 'без username'}"
    )

    await tracker.add_comment(issue_key, full_text, attachment_ids)

    issue = await tracker.get_issue_details(issue_key)
    summary = issue.get("summary", issue_key)
    await safe_reply_text(
        update.message,
        f"✅ Комментарий добавлен к задаче - <a href='https://tracker.yandex.ru/{issue_key}'>{summary}</a>",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(),
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
                MessageHandler(filters.PHOTO, handle_photo_or_album),
                MessageHandler(filters.Document.IMAGE, handle_photo_or_album),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_attachment),
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
    )
    app.add_handler(conv)

    # Мои задачи: поддержка и reply, и inline
    app.add_handler(MessageHandler(filters.Regex("^📂 Мои задачи$"), my_issues))
    app.add_handler(CallbackQueryHandler(my_issues, pattern="^my_issues$"))

    # Общие ловцы альбомов и вложений (если нужны вне FSM)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_or_album))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_photo_or_album))

