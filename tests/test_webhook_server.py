from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from telegram.error import BadRequest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from webhook_server import (
    setup_webhook_routes,
    router,
    processed_comment_ids,
    PROCESSED_IDS_TTL,
)
from config import Config


def create_app(application, tracker):
    app = FastAPI()
    router.routes.clear()
    processed_comment_ids.clear()
    setup_webhook_routes(app, application, tracker)
    return app


def create_mocks(telegram_id=None):
    bot = MagicMock()
    bot.send_media_group = AsyncMock()
    bot.send_photo = AsyncMock()
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
    bot.send_photo.assert_not_called()

def test_receive_webhook_handles_display_attachment():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[
            {"content_url": "http://files/image.png", "filename": "image.png"},
            {"content_url": "http://files/doc.txt", "filename": "doc.txt"},
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
    bot.send_photo.assert_called_once()
    bot.send_media_group.assert_not_called()
    bot.send_document.assert_called_once()


def test_send_photo_fallbacks_to_document():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[{"content_url": "http://files/image.png", "filename": "image.png"}]
    )

    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp()
    tracker.get_session = AsyncMock(return_value=mock_session)

    bot.send_photo.side_effect = BadRequest("Image_process_failed")

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
    bot.send_photo.assert_called_once()
    bot.send_media_group.assert_not_called()
    bot.send_document.assert_called_once()


def test_receive_webhook_strips_image_links():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp()
    tracker.get_session = AsyncMock(return_value=mock_session)

    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {
            "id": "1",
            "text": "Hello ![image.png](/ajax/v2/attachments/1 =800x600) there",
        },
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    sent_text = bot.send_message.call_args.kwargs["text"]
    assert "![" not in sent_text
    assert "Hello" in sent_text


def test_receive_webhook_strips_file_links():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp()
    tracker.get_session = AsyncMock(return_value=mock_session)

    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {
            "id": "1",
            "text": "Hello :file[doc.doc](/ajax/v2/attachments/1){type=\"application/msword\"}",
        },
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    sent_text = bot.send_message.call_args.kwargs["text"]
    assert ":file[" not in sent_text
    assert "Hello" in sent_text


def test_receive_webhook_strips_reply_metadata():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp()
    tracker.get_session = AsyncMock(return_value=mock_session)

    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {
            "id": "1",
            "text": "> [\u0412 \u043e\u0442\u0432\u0435\u0442 \u043d\u0430](http://t.y/1){data-quotelink=true}\n> > old\n>\n---\n\n\ud83d\udc64 Name\n\ud83d\udcf1 123\n\ud83d\udd17 @name\nReply"},
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    sent_text = bot.send_message.call_args.kwargs["text"]
    assert "\u0412 \u043e\u0442\u0432\u0435\u0442" not in sent_text  # "В ответ"
    assert "\ud83d\udc64" not in sent_text  # signature icon
    assert "Reply" in sent_text


def test_receive_webhook_converts_nbsp():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp()
    tracker.get_session = AsyncMock(return_value=mock_session)

    app = create_app(application, tracker)
    client = TestClient(app)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {"id": "1", "text": "Hello\xa0World &nbsp;!"},
    }

    response = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response.status_code == 200
    sent_text = bot.send_message.call_args.kwargs["text"]
    assert "\xa0" not in sent_text
    assert "&nbsp;" not in sent_text


def test_receive_webhook_deduplicates_comment():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
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

    response1 = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )
    response2 = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    bot.send_message.assert_called_once()


def test_receive_webhook_dedup_expires(monkeypatch):
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(return_value=[])
    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp()
    tracker.get_session = AsyncMock(return_value=mock_session)

    app = create_app(application, tracker)
    client = TestClient(app)

    monkeypatch.setattr(sys.modules["webhook_server"], "PROCESSED_IDS_TTL", 1)

    current = {"t": 0}

    def fake_time():
        return current["t"]

    monkeypatch.setattr(sys.modules["webhook_server"].time, "time", fake_time)

    payload = {
        "event": "commentCreated",
        "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
        "comment": {"id": "1", "text": "hi"},
    }

    response1 = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )
    current["t"] = 2
    response2 = client.post(
        "/trackers/comment",
        json=payload,
        headers={"Authorization": "Bearer TOKEN"},
    )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert bot.send_message.call_count == 2


def test_download_attachment_sanitizes_filename(monkeypatch):
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[{"content_url": "http://files/evil.txt", "filename": "../evil.txt"}]
    )

    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp(b"data")
    tracker.get_session = AsyncMock(return_value=mock_session)

    captured = []

    class DummyInputFile:
        def __init__(self, file_obj, filename=None):
            captured.append((file_obj, filename))

    monkeypatch.setattr(sys.modules["webhook_server"], "InputFile", DummyInputFile)

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
    assert captured
    file_obj, fname = captured[0]
    basename = os.path.basename(file_obj.name)
    assert basename.endswith("_evil.txt")
    assert fname == "evil.txt"
    assert file_obj.closed
    assert not os.path.exists(file_obj.name)


def test_download_attachment_unique_paths(monkeypatch):
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[
            {"content_url": "http://files/doc1.txt", "filename": "same.txt"},
            {"content_url": "http://files/doc2.txt", "filename": "same.txt"},
        ]
    )

    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp(b"data")
    tracker.get_session = AsyncMock(return_value=mock_session)

    captured = []

    class DummyInputFile:
        def __init__(self, file_obj, filename=None):
            captured.append((file_obj, filename))

    monkeypatch.setattr(sys.modules["webhook_server"], "InputFile", DummyInputFile)

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
    assert len(captured) == 2
    file1, fname1 = captured[0]
    file2, fname2 = captured[1]
    assert file1.name != file2.name
    assert fname1 == fname2 == "same.txt"
    assert os.path.basename(file1.name).endswith("_same.txt")
    assert os.path.basename(file2.name).endswith("_same.txt")
    assert file1.closed and file2.closed
    assert not os.path.exists(file1.name)
    assert not os.path.exists(file2.name)


def test_large_photo_sent_as_document():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[{"content_url": "http://files/large.png", "filename": "large.png"}]
    )

    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp(b"x" * (10 * 1024 * 1024 + 1))
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
    bot.send_document.assert_called_once()
    bot.send_photo.assert_not_called()
    bot.send_media_group.assert_not_called()


def test_send_document_failure_removes_file(monkeypatch):
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[{"content_url": "http://files/doc.txt", "filename": "doc.txt"}]
    )

    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp(b"data")
    tracker.get_session = AsyncMock(return_value=mock_session)

    captured = []

    class DummyInputFile:
        def __init__(self, file_obj, filename=None):
            captured.append(file_obj)

    monkeypatch.setattr(sys.modules["webhook_server"], "InputFile", DummyInputFile)

    bot.send_document.side_effect = BadRequest("fail")

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
    bot.send_document.assert_called_once()
    assert captured
    file_obj = captured[0]
    assert file_obj.closed
    assert not os.path.exists(file_obj.name)


def test_attachments_sent_before_message():
    Config.API_TOKEN = "TOKEN"
    application, tracker, bot = create_mocks()

    tracker.get_attachments_for_comment = AsyncMock(
        return_value=[{"content_url": "http://files/doc.txt", "filename": "doc.txt"}]
    )

    mock_session = MagicMock()
    mock_session.get.return_value = DummyResp(b"data")
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

    calls = [c[0] for c in bot.mock_calls]
    assert calls[0] == "send_document"
    assert "send_message" in calls
    assert calls.index("send_document") < calls.index("send_message")
