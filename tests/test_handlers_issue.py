import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pytest

from handlers_issue import confirm_issue_creation
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
