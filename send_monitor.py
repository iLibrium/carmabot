# send_monitor.py

import logging
import time

SEND_LOG = []

async def safe_send_message(bot, *args, **kwargs):
    SEND_LOG.append(time.time())
    recent = [t for t in SEND_LOG if t > time.time()-5]
    logging.info(f"[safe_send_message] called at {SEND_LOG[-1]} | total in last 5 sec: {len(recent)} | chat_id: {kwargs.get('chat_id', 'unknown')}")
    return await bot.send_message(*args, **kwargs)

async def safe_reply_text(message, *args, **kwargs):
    SEND_LOG.append(time.time())
    recent = [t for t in SEND_LOG if t > time.time()-5]
    logging.info(f"[safe_reply_text] called at {SEND_LOG[-1]} | total in last 5 sec: {len(recent)} | chat_id: {getattr(message, 'chat_id', 'unknown')}")
    return await message.reply_text(*args, **kwargs)

async def safe_delete_message(message):
    """Удаляет сообщение, игнорируя ошибки."""
    try:
        await message.delete()
    except Exception as exc:
        logging.exception("[safe_delete_message] %s", exc)

# Дополнительно можешь сделать так для send_photo, edit_message и т.д., если надо отслеживать и их.
