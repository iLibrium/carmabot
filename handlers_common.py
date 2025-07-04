from __future__ import annotations

import asyncio
import logging
import time
from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.ext import CallbackContext, ConversationHandler
from send_monitor import (
    safe_send_message,
    safe_reply_text,
    safe_delete_message,
)
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
)
from states import RegistrationStates
from messages import (
    MAIN_MENU,
    REQUEST_CONTACT,
    NOT_REGISTERED,
    REGISTRATION_SUCCESS,
    REQUEST_PENDING,
)

from database import Database
from keyboards import (
    main_reply_keyboard,
    contact_keyboard,
    register_keyboard,
)


async def check_rate_limit(update: Update, context: CallbackContext, key: str, action: str) -> bool:
    """Return True if action is allowed, otherwise send alert and return False."""
    now = time.time()
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        context.user_data = {}
        user_data = context.user_data
    last = user_data.get(key)
    if last and now - last < 10:
        if update.callback_query:
            await update.callback_query.answer(
                text=REQUEST_PENDING.format(action=action),
                show_alert=True,
            )
        return False
    user_data[key] = now
    return True

# Универсальная функция для вывода главного меню с reply-кнопками
async def show_main_reply_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("show_main_reply_menu triggered by %s", update.effective_user.id)
    # Allow immediate re-opening of the create issue flow after returning to the
    # main menu by clearing the rate-limit timestamp.
    context.user_data.pop("_start_issue_ts", None)
    if update.callback_query:
        await update.callback_query.answer()
        await safe_reply_text(
            update.callback_query.message,
            MAIN_MENU,
            reply_markup=main_reply_keyboard(),
            parse_mode="HTML",
            context=context,
        )
    elif update.message:
        msg = context.user_data.pop("issues_list_message", None)
        if msg:
            await safe_delete_message(msg)
        await safe_reply_text(
            update.message,
            MAIN_MENU,
            reply_markup=main_reply_keyboard(),
            parse_mode="HTML",
            context=context,
        )
        await safe_delete_message(update.message)

# ────────────────────────── /start  ─────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("/start by %s", update.effective_user.id)
    user_id = update.effective_user.id
    db = context.bot_data["db"]
    user_info = await db.get_user(user_id)
    if user_info:
        await show_main_reply_menu(update, context)
        return ConversationHandler.END

    # Пользователь не найден в БД – просим отправить контакт
    if update.message:
        await safe_reply_text(
            update.message,
            REQUEST_CONTACT,
            reply_markup=contact_keyboard(),
            context=context,
        )
        await safe_delete_message(update.message)
    return RegistrationStates.waiting_for_contact

async def show_user_info(update, context):
    logging.info("show_user_info for %s", update.effective_user.id)
    if update.callback_query:
        allowed = await check_rate_limit(update, context, "_user_info_ts", "получение информации")
        if not allowed:
            return
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    user_info = await db.get_user(user_id)
    if not user_info:
        await safe_reply_text(
            update.message,
            NOT_REGISTERED,
            reply_markup=register_keyboard(),
            context=context,
        )
        return

    full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
    phone = user_info.get("phone_number", "Нет данных")

    await safe_reply_text(
        update.message,
        f"👤 <b>Ваши данные:</b>\n"
        f"Имя: {full_name}\n"
        f"Телефон: {phone}\n"
        f"Telegram: @{update.effective_user.username or 'Нет'}",
        parse_mode="HTML",
        context=context,
    )
    await safe_delete_message(update.message)

# ─────────────────── обработка контакта (регистрация) ────────────────────
async def process_contact(update: Update, context: CallbackContext):
    """Получает Contact, сохраняет в БД и выводит меню."""
    logging.info("process_contact from %s", update.effective_user.id)
    user = update.effective_user
    contact = update.message.contact

    db: Database = context.bot_data["db"]
    await db.register_user(
        user.id,
        user.first_name,
        user.last_name,
        contact.phone_number,
    )

    await safe_reply_text(update.message, REGISTRATION_SUCCESS, context=context)
    await show_main_reply_menu(update, context)
    return ConversationHandler.END


# ──────────────────────── главное меню (универсальное) ────────────────────
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню с reply-кнопками."""
    logging.info("main_menu requested by %s", update.effective_user.id)
    if update.callback_query:
        allowed = await check_rate_limit(update, context, "_main_menu_ts", "открытие меню")
        if not allowed:
            return
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
        msg = context.user_data.pop("issues_list_message", None)
        if msg:
            await safe_delete_message(msg)
        await safe_reply_text(
            update.callback_query.message,
            MAIN_MENU,
            reply_markup=main_reply_keyboard(),
            parse_mode="HTML",
            context=context,
        )
    elif update.message:
        msg = context.user_data.pop("issues_list_message", None)
        if msg:
            await safe_delete_message(msg)
        await safe_reply_text(
            update.message,
            MAIN_MENU,
            reply_markup=main_reply_keyboard(),
            parse_mode="HTML",
            context=context,
        )

def register_handlers(application):
    registration_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^📝 Зарегистрироваться$"), start),
        ],
        states={
            RegistrationStates.waiting_for_contact: [
                MessageHandler(filters.CONTACT, process_contact),
            ],
        },
        fallbacks=[],
        name="registration_flow",
    )
    application.add_handler(registration_conv)

    # --- INLINE-КНОПКИ ---
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"), group=1)
    application.add_handler(CallbackQueryHandler(show_user_info, pattern="^user_info$"), group=1)

    # --- (ОСТАЛЬНОЕ ОСТАВИТЬ для совместимости) ---
    application.add_handler(MessageHandler(filters.Regex("^🔄 Главное меню$"), main_menu), group=1)
    application.add_handler(MessageHandler(filters.Regex("^👤 Моя информация$"), show_user_info), group=1)
