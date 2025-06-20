from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from webhook_server import setup_webhook_routes, router
from config import Config


def create_app(application, tracker):
    app = FastAPI()
    router.routes.clear()
    setup_webhook_routes(app, application, tracker)
    return app


def create_mocks(telegram_id=None):
    bot = MagicMock()
    bot.send_media_group = AsyncMock()
    bot.send_document = AsyncMock()
    bot.send_message = AsyncMock()

    application = MagicMock()
    application.bot = bot

    tracker = MagicMock()
    tracker.get_issue = AsyncMock(return_value={"telegramId": telegram_id})
    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
    tracker.get_session = AsyncMock(return_value=MagicMock())
    tracker.get_comment_author = AsyncMock(return_value="Tester")
    return application, tracker, bot


class DummyResp:
    def __init__(self, data=b"", status=200):
        self._data = data
        self.status = status

    async def read(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


def test_receive_webhook_with_telegram_id():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()
    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {"id": "1", "text": "hi", "createdBy": {"display": "Tester"}},
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    tracker.get_issue.assert_not_called()
    bot.send_message.assert_called_once()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 123
    assert kwargs["parse_mode"] == "HTML"


def test_receive_webhook_fallback_to_get_issue():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks(telegram_id="321")
    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test"},
        "comment": {"id": "1", "text": "hi", "createdBy": {"display": "Tester"}},
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    tracker.get_issue.assert_called_once_with("ISSUE-1")
    bot.send_message.assert_called_once()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 321


def test_receive_webhook_without_comment_id():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks(telegram_id="123")
    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {"text": "hi"},
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    tracker.get_comment_author.assert_not_called()
    tracker.get_attachments_for_comment.assert_not_called()
    bot.send_message.assert_called_once()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 123


def test_update_status_with_telegram_id():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()
    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "issueUpdated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "status": {"name": "In Progress"},
        "changedBy": {"display": "Tester"},
    }

    response = client.post(
        "/trackers/updateStatus",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    tracker.get_issue.assert_not_called()
    bot.send_message.assert_called_once()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 123
    assert kwargs["parse_mode"] == "HTML"


def test_update_status_fallback_to_get_issue():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks(telegram_id="456")
    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "issueUpdated",
        "issue": {"key": "ISSUE-1", "summary": "Test"},
        "status": {"name": "Closed"},
        "changedBy": {"display": "Tester"},
    }

    response = client.post(
        "/trackers/updateStatus",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    tracker.get_issue.assert_called_once_with("ISSUE-1")
    bot.send_message.assert_called_once()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 456


def test_receive_webhook_skips_invalid_attachments():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[
            {"content_url": "http://files/file1.txt", "filename": None},
            {"content_url": None, "filename": "file2.txt"},
        ]
    )

    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp()
    tracker.get_session = AsyncMock(return_value=mock_session)

    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {"id": "1", "text": "hi"},
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    bot.send_message.assert_called_once()
    bot.send_document.assert_not_called()
    bot.send_media_group.assert_not_called()

