from __future__ import annotations

import asyncio
import logging
from telegram import Update, Message
from telegram.ext import CallbackContext, ConversationHandler


from database import Database
from keyboards import (
    main_reply_keyboard,
    main_inline_keyboard,
    contact_keyboard,
)
from states import RegistrationStates

# ──────────────────────── вспомогательные функции ─────────────────────────
async def _show_reply_menu(message: Message):
    """Отправляет reply‑клавиатуру отдельным сообщением."""
    await message.reply_text("🔄 Выберите действие:", reply_markup=main_reply_keyboard())


async def _show_inline_menu(message: Message, *, edit: bool = False):
    """Показывает inline‑меню (редактируя существующее сообщение или отправляя новое).

    Args:
        message: исходное сообщение (для reply или callback).
        edit: если True — редактирует *message*, иначе отправляет новое.
    """
    if edit:
        await message.edit_text("🔄 Выберите действие:", reply_markup=main_inline_keyboard())
    else:
        await message.reply_text("🔄 Выберите действие:", reply_markup=main_inline_keyboard())


# ────────────────────────── /start  ─────────────────────────────
async def start(update: Update, context: CallbackContext):
    """Команда /start.
    • Если пользователь уже известен — сразу показывает меню.
    • Иначе просит контакт для регистрации.
    """
    user_id = update.effective_user.id
    db: Database = context.bot_data["db"]

    user_info = await db.get_user(user_id)
    if user_info:
        # Отправляем оба меню параллельно и завершаем.
        await asyncio.gather(
            _show_inline_menu(update.message, edit=False),
            _show_reply_menu(update.message),
        )
        return ConversationHandler.END

    # Новый пользователь — просим контакт.
    await update.message.reply_text(
        "📲 Отправьте ваш контакт для регистрации.",
        reply_markup=contact_keyboard(),
    )
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

    # После регистрации показываем оба меню.
    await asyncio.gather(
        _show_inline_menu(update.message, edit=False),
        _show_reply_menu(update.message),
    )
    return ConversationHandler.END


# ──────────────────────── главное меню (универсальное) ────────────────────
async def main_menu(update: Update, context: CallbackContext):
    """Выводит оба меню для сообщения или callback‑запроса."""
    if update.callback_query:
        # Редактируем сообщение с inline‑кнопкой + отправляем reply‑меню
        await asyncio.gather(
            _show_inline_menu(update.callback_query.message, edit=True),
            _show_reply_menu(update.callback_query.message),
        )
        await update.callback_query.answer()
    elif update.message:
        # От обычного текста/команды — два новых сообщения
        await asyncio.gather(
            _show_inline_menu(update.message, edit=False),
            _show_reply_menu(update.message),
        )

def register_handlers(application):
    from telegram.ext import CommandHandler, MessageHandler, filters, ConversationHandler

    registration_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
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

    # Остальные message/callback хендлеры
    application.add_handler(MessageHandler(filters.Regex("^🔄 Главное меню$"), main_menu))
    application.add_handler(MessageHandler(filters.Regex("^👤 Моя информация$"), show_user_info))
    # и другие message/callback хендлеры по необходимости
