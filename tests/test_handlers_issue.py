import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pytest

from handlers_issue import confirm_issue_creation, handle_attachment
from config import Config

@pytest.mark.asyncio
async def test_confirm_issue_creation_extra_fields():
    update = MagicMock()
    user = MagicMock()
    user.id = 1
    user.first_name = "A"
    user.last_name = "B"
    user.username = "user"
    update.effective_user = user

    query = MagicMock()
    query.answer = AsyncMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {
        "issue_title": "Title",
        "issue_description": "Desc",
        "attachments": [123],
    }
    db = MagicMock()
    db.get_user = AsyncMock(return_value={"phone_number": "111"})
    db.create_issue = AsyncMock()
    tracker = MagicMock()
    tracker.create_issue = AsyncMock(return_value={"key": "ISSUE-1"})
    context.bot_data = {"db": db, "tracker": tracker}

    await confirm_issue_creation(update, context)

    extra = tracker.create_issue.call_args.args[2]
    assert extra["project"] == Config.PROJECT
    assert extra["tags"] == Config.DEFAULT_TAGS
    assert extra["attachmentIds"] == [123]
    assert extra[Config.PRODUCT_CUSTOM_FIELD] == Config.PRODUCT_DEFAULT


@pytest.mark.asyncio
async def test_handle_attachment_document_extension(monkeypatch):
    update = MagicMock()
    message = MagicMock()
    update.message = message
    update.effective_user = MagicMock(id=1)

    document = MagicMock()
    document.file_unique_id = "uid"
    document.file_id = "fid"
    document.file_name = "file.pdf"
    message.document = document
    message.photo = []
    message.reply_text = AsyncMock()

    file_info = MagicMock()

    async def fake_download(path):
        # create dummy file so os.remove doesn't fail if called
        open(path, "wb").close()

    file_info.download_to_drive = AsyncMock(side_effect=fake_download)

    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=file_info)

    tracker = MagicMock()
    tracker.upload_file = AsyncMock(return_value=1)

    context = MagicMock()
    context.bot = bot
    context.bot_data = {"tracker": tracker}
    context.user_data = {}

    monkeypatch.setattr(os, "remove", lambda *_: None)

    await handle_attachment(update, context)

    upload_path = tracker.upload_file.call_args.args[0]
    assert upload_path.endswith(".pdf")
