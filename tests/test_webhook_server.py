import os
import sys
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# set token before importing modules
os.environ['API_TOKEN'] = 'TOKEN'

from webhook_server import setup_webhook_routes, router
from tracker_client import TrackerAPI


def create_app_and_tracker():
    app = FastAPI()
    router.routes.clear()
    tracker = MagicMock(spec=TrackerAPI)
    telegram_app = MagicMock()
    telegram_app.bot.send_media_group = AsyncMock()
    telegram_app.bot.send_document = AsyncMock()
    setup_webhook_routes(app, telegram_app, tracker)
    client = TestClient(app)
    return client, tracker


def test_invalid_comment_id_ignored():
    client, tracker = create_app_and_tracker()
    data = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1"},
        "comment": {"id": "bad*id"}
    }
    resp = client.post("/trackers/comment", json=data, headers={"Authorization": "Bearer TOKEN"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}
    tracker.get_comment_author.assert_not_called()
    tracker.get_issue.assert_not_called()
    tracker.get_attachments_for_comment.assert_not_called()


def test_valid_comment_id_processed():
    client, tracker = create_app_and_tracker()
    tracker.get_comment_author = AsyncMock(return_value="Tester")
    tracker.get_issue = AsyncMock(return_value={"telegramId": "1"})
    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
    tracker.get_session = AsyncMock(return_value=MagicMock())
    data = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test"},
        "comment": {"id": "123", "text": "hi"}
    }
    resp = client.post("/trackers/comment", json=data, headers={"Authorization": "Bearer TOKEN"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    tracker.get_issue.assert_called_once()

