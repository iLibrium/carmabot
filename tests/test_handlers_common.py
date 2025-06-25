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
