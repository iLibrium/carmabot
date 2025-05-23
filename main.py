from __future__ import annotations

import argparse
import asyncio
import logging
import os

import nest_asyncio
import uvicorn
from fastapi import FastAPI
from telegram.ext import Application, ContextTypes
from dotenv import load_dotenv
from httpx import Limits
from telegram.request import HTTPXRequest
from telegram.ext import ApplicationBuilder
import telegram
print("python-telegram-bot version:", telegram.__version__)


from config import Config
from database import Database
from tracker_client import TrackerAPI
from webhook_server import setup_webhook_routes

# Импорт регистраторов хендлеров
from handlers_common import register_handlers as register_common_handlers
from handlers_issue import register_handlers as register_issue_handlers

# ────────────────────────── конфигурация логов ────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# ────────────── .env ───────────────
load_dotenv()

# Получаем значения из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
TRACKER_TOKEN = os.getenv("TRACKER_TOKEN")
TRACKER_ORG_ID = os.getenv("TRACKER_ORG_ID")
TRACKER_QUEUE = os.getenv("TRACKER_QUEUE")
TRACKER_BASE_URL = "https://api.tracker.yandex.net"

# ────────────────────────── FastAPI приложение ───────────────────────────────
fastapi_app = FastAPI()

async def run_webhook_server(host: str, port: int) -> None:
    """Запускает FastAPI‑сервер как отдельную async‑задачу."""
    config = uvicorn.Config(app=fastapi_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    import traceback
    logging.error("Exception caught: %s", traceback.format_exc())
    if update and hasattr(update, 'message') and update.message:
        await update.message.reply_text("⚠️ Ошибка связи с Telegram. Попробуйте ещё раз.")

async def main() -> None:
    """Главная асинхронная точка входа."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    logging.info("🔎 Запуск бота...")

    # ───── создаём Telegram‑Application ─────
    application = ApplicationBuilder()\
        .token(BOT_TOKEN)\
        .request(HTTPXRequest(
            read_timeout=60,
            connect_timeout=30
            # без pool_limits!
        ))\
        .build()

    application.add_error_handler(error_handler)

    # ───── подключаемся к БД ─────
    db = Database()
    await db.connect()
    if not db._pool:
        logging.error("❌ Не удалось подключиться к PostgreSQL – выход")
        return
    logging.info("✅ PostgreSQL: подключение установлено")

    # ───── инициализируем TrackerAPI ─────
    tracker = TrackerAPI(
        base_url=TRACKER_BASE_URL,
        token=TRACKER_TOKEN,
        org_id=TRACKER_ORG_ID,
        queue=TRACKER_QUEUE
    )

    # Делаем tracker и db доступными во всех хендлерах
    application.bot_data["tracker"] = tracker
    application.bot_data["db"] = db

    # ───── регистрируем хендлеры ─────
    register_common_handlers(application)
    register_issue_handlers(application)

    # ───── FastAPI маршруты вебхука ─────
    setup_webhook_routes(fastapi_app, application.bot, tracker)

    logging.info("🤖 Бот (polling) и FastAPI‑webhook стартуют…")

    # ───── параллельный запуск ─────
    await asyncio.gather(
        application.run_polling(),
        run_webhook_server(args.host, args.port),
    )

    # закрываем ресурсы
    await db.close()
    logging.info("✅ Завершение работы: ресурсы освобождены")

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
