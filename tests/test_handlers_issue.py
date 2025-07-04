import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, ANY

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pytest

from handlers_issue import (
    confirm_issue_creation,
    handle_attachment,
    _process_album_later,
    process_comment,
    my_issues,
    start_create_issue,
    _album_buffer,
)
from messages import NOT_REGISTERED, FILE_TOO_LARGE
from states import IssueStates
from telegram.ext import ConversationHandler
from config import Config

@pytest.mark.asyncio
async def test_confirm_issue_creation_extra_fields(monkeypatch):
    update = MagicMock()
    user = MagicMock()
    user.id = 1
    user.first_name = "A"
    user.last_name = "B"
    user.username = "user"
    update.effective_user = user

    query = MagicMock()
    query.answer = AsyncMock()
    monkeypatch.setattr(sys.modules["handlers_issue"], "safe_reply_text", AsyncMock())
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
    document.file_size = 123
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
    assert tracker.upload_file.call_args.args[1] == "file.pdf"


@pytest.mark.asyncio
async def test_handle_attachment_too_large(monkeypatch):
    update = MagicMock()
    message = MagicMock()
    update.message = message
    update.effective_user = MagicMock(id=1)

    document = MagicMock()
    document.file_unique_id = "uid"
    document.file_id = "fid"
    document.file_size = Config.MAX_FILE_SIZE + 1
    message.document = document
    message.photo = []
    message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot = MagicMock()
    context.user_data = {}

    monkeypatch.setattr(
        sys.modules["handlers_issue"], "safe_reply_text", AsyncMock()
    )

    state = await handle_attachment(update, context)

    sys.modules["handlers_issue"].safe_reply_text.assert_awaited_once_with(
        message, FILE_TOO_LARGE, context=context
    )
    assert state == IssueStates.waiting_for_attachment


@pytest.mark.asyncio
async def test_process_album_later_passes_filename(monkeypatch):
    msg = MagicMock()
    file = MagicMock()
    file.file_unique_id = "uid"
    file.file_id = "fid"
    file.file_name = "orig.jpg"
    file.file_size = 123
    msg.photo = []
    msg.document = file
    msg.chat_id = 1
    _album_buffer["gid"] = [msg]

    file_info = MagicMock()

    async def fake_download(path):
        open(path, "wb").close()

    file_info.download_to_drive = AsyncMock(side_effect=fake_download)

    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=file_info)
    bot.send_message = AsyncMock()
    monkeypatch.setattr(sys.modules["handlers_issue"], "safe_send_message", AsyncMock())

    tracker = MagicMock()
    tracker.upload_file = AsyncMock(return_value=1)

    context = MagicMock()
    context.bot = bot
    context.bot_data = {"tracker": tracker}
    context.user_data = {}

    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(os, "remove", lambda *_: None)

    await _process_album_later("gid", context)

    assert tracker.upload_file.call_args.args[1] == "orig.jpg"


@pytest.mark.asyncio
async def test_process_comment_passes_filename(monkeypatch):
    update = MagicMock()
    message = MagicMock()
    update.message = message
    update.effective_user = MagicMock(
        id=1, first_name="A", last_name="B", username="u"
    )

    doc = MagicMock()
    doc.file_unique_id = "uid"
    doc.file_id = "fid"
    doc.file_name = "doc.txt"
    doc.file_size = 123
    message.document = doc
    message.photo = []
    message.text = None
    message.caption = None

    file_info = MagicMock()

    async def fake_download(path):
        open(path, "wb").close()

    file_info.download_to_drive = AsyncMock(side_effect=fake_download)

    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=file_info)

    tracker = MagicMock()
    tracker.upload_file = AsyncMock(return_value=1)
    tracker.add_comment = AsyncMock()
    tracker.get_issue_details = AsyncMock(return_value={"summary": "s"})

    db = MagicMock()
    db.get_user = AsyncMock(return_value={})

    context = MagicMock()
    context.bot = bot
    context.bot_data = {"tracker": tracker, "db": db}
    context.user_data = {"issue_key": "ISSUE-1"}

    monkeypatch.setattr(os, "remove", lambda *_: None)
    monkeypatch.setattr(
        sys.modules["handlers_issue"], "safe_reply_text", AsyncMock()
    )

    await process_comment(update, context)

    assert tracker.upload_file.call_args.args[1] == "doc.txt"
    sent_text = tracker.add_comment.call_args.args[1]
    assert sent_text.endswith("\n---\n")


@pytest.mark.asyncio
async def test_process_comment_too_large(monkeypatch):
    update = MagicMock()
    message = MagicMock()
    update.message = message
    update.effective_user = MagicMock(id=1, first_name="A", last_name="B", username="u")

    doc = MagicMock()
    doc.file_unique_id = "uid"
    doc.file_id = "fid"
    doc.file_size = Config.MAX_FILE_SIZE + 1
    message.document = doc
    message.photo = []
    message.text = None
    message.caption = None

    context = MagicMock()
    context.bot = MagicMock()
    context.bot_data = {"tracker": MagicMock(), "db": MagicMock()}
    context.user_data = {"issue_key": "ISSUE-1"}

    monkeypatch.setattr(
        sys.modules["handlers_issue"], "safe_reply_text", AsyncMock()
    )

    state = await process_comment(update, context)

    sys.modules["handlers_issue"].safe_reply_text.assert_awaited_once_with(
        message, FILE_TOO_LARGE, context=context
    )
    assert state == IssueStates.waiting_for_comment


@pytest.mark.asyncio
async def test_my_issues_unregistered(monkeypatch):
    update = MagicMock()
    update.effective_user = MagicMock(id=1)
    cbq = MagicMock()
    cbq.answer = AsyncMock()
    monkeypatch.setattr(sys.modules["handlers_issue"], "safe_reply_text", AsyncMock())
    update.callback_query = cbq

    context = MagicMock()
    db = MagicMock()
    db.get_user = AsyncMock(return_value=None)
    context.bot_data = {"db": db, "tracker": MagicMock()}

    await my_issues(update, context)

    sys.modules["handlers_issue"].safe_reply_text.assert_awaited_once_with(
        cbq.message, NOT_REGISTERED, reply_markup=ANY, context=context
    )


@pytest.mark.asyncio
async def test_my_issues_clears_user_data(monkeypatch):
    update = MagicMock()
    msg = MagicMock()
    update.message = msg
    update.callback_query = None
    update.effective_user = MagicMock(id=1)
    monkeypatch.setattr(sys.modules["handlers_issue"], "safe_reply_text", AsyncMock())

    context = MagicMock()
    context.user_data = {"tmp": "data"}
    db = MagicMock()
    db.get_user = AsyncMock(return_value={})
    tracker = MagicMock()
    tracker.get_active_issues_by_telegram_id = AsyncMock(return_value=[])
    context.bot_data = {"db": db, "tracker": tracker}

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        sys.modules["handlers_issue"], "safe_delete_message", delete_mock
    )

    await my_issues(update, context)

    assert context.user_data == {}
    sys.modules["handlers_issue"].safe_reply_text.assert_awaited_once_with(
        msg, ANY, reply_markup=ANY, context=context
    )
    delete_mock.assert_called_once_with(msg)


@pytest.mark.asyncio
async def test_start_create_issue_unregistered(monkeypatch):
    update = MagicMock()
    update.effective_user = MagicMock(id=1)
    cbq = MagicMock()
    cbq.answer = AsyncMock()
    update.callback_query = cbq
    monkeypatch.setattr(sys.modules["handlers_issue"], "safe_reply_text", AsyncMock())

    context = MagicMock()
    db = MagicMock()
    db.get_user = AsyncMock(return_value=None)
    context.bot_data = {"db": db}

    result = await start_create_issue(update, context)

    assert result == ConversationHandler.END
    sys.modules["handlers_issue"].safe_reply_text.assert_awaited_once_with(
        cbq.message, NOT_REGISTERED, reply_markup=ANY, context=context
    )
