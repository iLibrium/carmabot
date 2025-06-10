from __future__ import annotations

import asyncio
import logging
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

from database import Database
from keyboards import (
    main_reply_keyboard,
    contact_keyboard,
)
from states import RegistrationStates


# Универсальная функция для вывода главного меню с reply-кнопками
async def show_main_reply_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "Главное меню:",
            reply_markup=main_reply_keyboard()
        )
    elif update.message:
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=main_reply_keyboard()
        )
        await safe_delete_message(update.message)
        await safe_delete_message(update.message)

# ────────────────────────── /start  ─────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "Чтобы продолжить, поделитесь контактом:",
            reply_markup=contact_keyboard(),
        )
        await safe_delete_message(update.message)
    return RegistrationStates.waiting_for_contact

async def show_user_info(update, context):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    user_info = await db.get_user(user_id)
    if not user_info:
        await update.message.reply_text("❌ Вы не зарегистрированы.")
        return

    full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
    phone = user_info.get("phone_number", "Нет данных")

    await update.message.reply_text(
        f"👤 <b>Ваши данные:</b>\n"
        f"Имя: {full_name}\n"
        f"Телефон: {phone}\n"
        f"Telegram: @{update.effective_user.username or 'Нет'}",
        parse_mode="HTML"
    )
    await safe_delete_message(update.message)

# ─────────────────── обработка контакта (регистрация) ────────────────────
async def process_contact(update: Update, context: CallbackContext):
    """Получает Contact, сохраняет в БД и выводит меню."""
    user = update.effective_user
    contact = update.message.contact

    db: Database = context.bot_data["db"]
    await db.register_user(
        user.id,
        user.first_name,
        user.last_name,
        contact.phone_number,
    )

    await safe_reply_text(update.message, "✅ Регистрация успешна!")
    await show_main_reply_menu(update, context)
    return ConversationHandler.END


# ──────────────────────── главное меню (универсальное) ────────────────────
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню с reply-кнопками."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
        await update.callback_query.message.reply_text(
            "Главное меню:",
            reply_markup=main_reply_keyboard()
        )
    elif update.message:
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=main_reply_keyboard()
        )

def register_handlers(application):
    registration_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
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
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(show_user_info, pattern="^user_info$"))

    # --- (ОСТАЛЬНОЕ ОСТАВИТЬ для совместимости) ---
    application.add_handler(MessageHandler(filters.Regex("^🔄 Главное меню$"), main_menu))
    application.add_handler(MessageHandler(filters.Regex("^👤 Моя информация$"), show_user_info))
