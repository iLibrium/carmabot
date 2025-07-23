import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pytest
from telegram.ext import ConversationHandler

from handlers_common import start, process_contact
from states import RegistrationStates


@pytest.mark.asyncio
async def test_registration_flow(monkeypatch):
    update_start = MagicMock()
    msg_start = MagicMock()
    update_start.message = msg_start
    update_start.effective_user = MagicMock(id=1)

    context = MagicMock()
    db = MagicMock()
    db.get_user = AsyncMock(return_value=None)
    db.register_user = AsyncMock()
    context.bot_data = {"db": db}

    monkeypatch.setattr("handlers_common.safe_reply_text", AsyncMock())
    monkeypatch.setattr("handlers_common.safe_delete_message", AsyncMock())
    monkeypatch.setattr("handlers_common.show_main_reply_menu", AsyncMock())

    state = await start(update_start, context)
    assert state == RegistrationStates.waiting_for_contact

    update_contact = MagicMock()
    msg_contact = MagicMock()
    msg_contact.contact = MagicMock(phone_number="111")
    update_contact.message = msg_contact
    update_contact.effective_user = MagicMock(id=1, first_name="A", last_name="B")

    result = await process_contact(update_contact, context)
    assert result == ConversationHandler.END
    db.register_user.assert_awaited_once_with(1, "A", "B", "111")


@pytest.mark.asyncio
async def test_start_registration_button(monkeypatch):
    update = MagicMock()
    message = MagicMock()
    message.text = "📝 Зарегистрироваться"
    update.message = message
    update.effective_user = MagicMock(id=1)

    context = MagicMock()
    db = MagicMock()
    db.get_user = AsyncMock(return_value=None)
    context.bot_data = {"db": db}

    monkeypatch.setattr("handlers_common.safe_reply_text", AsyncMock())
    monkeypatch.setattr("handlers_common.safe_delete_message", AsyncMock())
    monkeypatch.setattr("handlers_common.show_main_reply_menu", AsyncMock())

    result = await start(update, context)

    assert result == RegistrationStates.waiting_for_contact


@pytest.mark.asyncio
async def test_forward_message_to_n8n(monkeypatch):
    update = MagicMock()
    message = MagicMock()
    message.text = "hello"
    update.message = message
    update.effective_user = MagicMock(id=1)

    context = MagicMock()
    context.bot = MagicMock(token="TOKEN")

    forward_mock = AsyncMock()
    monkeypatch.setattr("handlers_common.n8n_forward_message", forward_mock)

    from handlers_common import forward_message_to_n8n

    await forward_message_to_n8n(update, context)

    forward_mock.assert_awaited_once_with("TOKEN", "hello")
