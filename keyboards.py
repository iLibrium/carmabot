"""keyboards.py
================
Все функции, формирующие **Reply‑** и **Inline‑клавиатуры** Telegram‑бота CARMA.
Выделены в отдельный модуль, чтобы:
    • держать логику UI в одном месте;
    • упростить тестирование и переиспользование;
    • сократить объём основного файла обработчиков.

Импортировать так:
    from keyboards import (
        main_reply_keyboard,
        main_inline_keyboard,
        contact_keyboard,
    )
"""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# ────────────────────────── Reply‑клавиатуры ──────────────────────────

def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню, выводится *под строкой ввода* (Reply‑кнопки).
    • «Создать задачу» запускает FSM‑процесс.
    • «Мои задачи» запрашивает открытые задачи пользователя.
    • «Моя информация» выводит профиль.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("📋 Создать задачу"),
                KeyboardButton("📂 Мои задачи"),
            ],
            [KeyboardButton("👤 Моя информация")],
        ],
        resize_keyboard=True,
    )

# ───────────────────────── Inline‑клавиатуры ──────────────────────────

def main_inline_keyboard() -> InlineKeyboardMarkup:
    """Главное меню в виде *inline‑кнопок* (callback‑query)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 Создать задачу", callback_data="create_issue")],
            [InlineKeyboardButton("📂 Мои задачи", callback_data="my_issues")],
            [InlineKeyboardButton("👤 Моя информация", callback_data="my_info")],
        ]
    )

# ───────────────────────── Специальные клавиатуры ─────────────────────

def contact_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с одной кнопкой *"Поделиться контактом"*."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("📲 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def register_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard with a single button to restart registration."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("📝 Зарегистрироваться")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
