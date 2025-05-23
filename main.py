from __future__ import annotations

import argparse
import asyncio
import logging

import aiohttp
import nest_asyncio
import uvicorn
from fastapi import FastAPI
from telegram.ext import Application
from telegram.ext import ContextTypes
from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest


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

# ────────────────────────── FastAPI приложение ───────────────────────────────
app = FastAPI()
app = ApplicationBuilder()\
    .token("BOT_TOKEN")\
    .request(HTTPXRequest(
        read_timeout=60,   # сколько ждать ответа
        connect_timeout=30 # сколько ждать соединения
    ))\
    .build()

async def run_webhook_server(host: str, port: int) -> None:
    """Запускает FastAPI‑сервер как отдельную async‑задачу."""
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
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
    application = Application.builder().token(Config.BOT_TOKEN).build()
    application.add_error_handler(error_handler)


    # ───── подключаемся к БД ─────
    db = Database()
    await db.connect()
    if not db._pool:
        logging.error("❌ Не удалось подключиться к PostgreSQL – выход")
        return
    logging.info("✅ PostgreSQL: подключение установлено")

    # ───── общая aiohttp‑сессия для TrackerAPI ─────
    async with aiohttp.ClientSession() as session:
        tracker = TrackerAPI(session=session)

        application.bot_data.update(tracker=tracker, db=db)

        # ───── регистрируем хендлеры ─────
        register_common_handlers(application)
        register_issue_handlers(application)

        # ───── FastAPI маршруты вебхука ─────
        setup_webhook_routes(app, application.bot, tracker)

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
