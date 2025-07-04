# send_monitor.py

import logging
import time
from telegram.error import BadRequest
import asyncio

SEND_LOG = []

async def safe_send_message(bot, *args, context=None, **kwargs):
    SEND_LOG.append(time.time())
    recent = [t for t in SEND_LOG if t > time.time()-5]
    SEND_LOG[:] = recent
    logging.info(f"[safe_send_message] called at {SEND_LOG[-1]} | total in last 5 sec: {len(recent)} | chat_id: {kwargs.get('chat_id', 'unknown')}")
    user_data = getattr(context, "user_data", None) if context else None
    if user_data and user_data.get("last_bot_message"):
        await safe_delete_message(user_data.pop("last_bot_message"))
    msg = await bot.send_message(*args, **kwargs)
    if user_data is not None:
        user_data["last_bot_message"] = msg
    return msg

async def safe_reply_text(message, *args, context=None, **kwargs):
    SEND_LOG.append(time.time())
    recent = [t for t in SEND_LOG if t > time.time()-5]
    SEND_LOG[:] = recent
    logging.info(f"[safe_reply_text] called at {SEND_LOG[-1]} | total in last 5 sec: {len(recent)} | chat_id: {getattr(message, 'chat_id', 'unknown')}")
    user_data = getattr(context, "user_data", None) if context else None
    if user_data and user_data.get("last_bot_message"):
        await safe_delete_message(user_data.pop("last_bot_message"))
    msg = await message.reply_text(*args, **kwargs)
    if user_data is not None:
        user_data["last_bot_message"] = msg
    return msg

async def safe_delete_message(message):
    """Удаляет сообщение, игнорируя ошибки."""
    try:
        await message.delete()
    except BadRequest as exc:
        if str(exc) == "Message to delete not found":
            logging.warning("[safe_delete_message] message already deleted")
        else:
            logging.exception("[safe_delete_message] %s", exc)
    except Exception as exc:
        logging.exception("[safe_delete_message] %s", exc)

async def safe_edit_message_reply_markup(obj, *args, **kwargs):
    """Edit message reply markup and ignore missing-message errors."""
    try:
        result = obj.edit_message_reply_markup(*args, **kwargs)
        if asyncio.iscoroutine(result):
            await result
    except BadRequest as exc:
        if str(exc) == "Message to edit not found":
            logging.warning(
                "[safe_edit_message_reply_markup] message already deleted"
            )
        else:
            logging.exception(
                "[safe_edit_message_reply_markup] %s", exc
            )
    except Exception as exc:
        logging.exception(
            "[safe_edit_message_reply_markup] %s", exc
        )

# Дополнительно можешь сделать так для send_photo, edit_message и т.д., если надо отслеживать и их.
