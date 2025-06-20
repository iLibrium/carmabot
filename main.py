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
import contextlib


from config import Config
from database import Database
from tracker_client import TrackerAPI
from webhook_server import setup_webhook_routes
from messages import TELEGRAM_ERROR

# Импорт регистраторов хендлеров
from handlers_common import register_handlers as register_common_handlers
from handlers_issue import register_handlers as register_issue_handlers

# ────────────────────────── конфигурация логов ────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)
logging.info("python-telegram-bot version: %s", telegram.__version__)

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

async def start_webhook_server(host: str, port: int):
    """Запускает FastAPI‑сервер и возвращает ``Server`` и задачу его работы."""
    config = uvicorn.Config(app=fastapi_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    logging.info("🌐 FastAPI сервер запускается на http://%s:%d", host, port)
    server_task = asyncio.create_task(server.serve())
    return server, server_task

async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    import traceback
    logging.error("Exception caught: %s", traceback.format_exc())
    if update and hasattr(update, 'message') and update.message:
        await update.message.reply_text(TELEGRAM_ERROR)

async def main() -> None:
    """Главная асинхронная точка входа."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    logging.info("🔎 Запуск бота...")

    # ───── создаём Telegram‑Application ─────
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(
            HTTPXRequest(
                connection_pool_size=20,
                read_timeout=60,
                connect_timeout=30,
                httpx_kwargs={
                    "limits": Limits(
                        max_connections=20, max_keepalive_connections=10
                    )
                },
            )
        )
        .build()
    )

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
    setup_webhook_routes(fastapi_app, application, tracker)

    logging.info("🤖 Бот (polling) и FastAPI‑webhook стартуют…")

    # ───── запуск приложения и вебхука в одном event loop ─────
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        logging.info("✅ Бот запущен и ожидает события")

        server, server_task = await start_webhook_server(args.host, args.port)
        await server_task
        logging.info("✅ FastAPI сервер завершил работу")
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("🛑 Interrupt received. Shutting down…")
    finally:
        await application.updater.stop()
        logging.info("✅ Бот остановлен")
        await application.stop()
        await application.shutdown()
        if 'server' in locals():
            server.should_exit = True
            # ``server_task`` could raise ``KeyboardInterrupt`` or ``CancelledError``
            # during shutdown, which should be ignored to finish gracefully
            with contextlib.suppress(Exception, asyncio.CancelledError, KeyboardInterrupt):
                await server_task
            logging.info("✅ FastAPI сервер остановлен")
        await tracker.close()
        await db.close()
        logging.info("✅ Завершение работы: ресурсы освобождены")

if __name__ == "__main__":
    nest_asyncio.apply()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # ``uvicorn.Server`` re-raises the interrupt signal when shutting down
        # which would otherwise surface as a traceback here.
        pass
