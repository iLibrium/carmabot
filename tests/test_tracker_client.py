from unittest.mock import AsyncMock, MagicMock, patch
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


class MockResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status = status

    async def json(self):
        return self._json

    async def text(self):
        return str(self._json)

    async def read(self):
        return b""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass
import pytest

from tracker_client import TrackerAPI

@pytest.mark.asyncio
async def test_get_headers():
    api = TrackerAPI('http://example.com', 'TOKEN', org_id='ORG')
    headers = api.get_headers()
    assert headers['Authorization'] == 'OAuth TOKEN'
    assert headers['X-Cloud-Org-ID'] == 'ORG'

@pytest.mark.asyncio
async def test_get_issue():
    api = TrackerAPI('http://example.com', 'TOKEN')
    mock_session = MagicMock()
    mock_session.get.return_value = MockResponse({'key': 'ISSUE-1'})
    api.get_session = AsyncMock(return_value=mock_session)

    issue = await api.get_issue('ISSUE-1')
    assert issue['key'] == 'ISSUE-1'

@pytest.mark.asyncio
async def test_get_comment_author():
    api = TrackerAPI('http://example.com', 'TOKEN')
    mock_session = MagicMock()
    mock_session.get.return_value = MockResponse({'createdBy': {'display': 'Tester'}})
    api.get_session = AsyncMock(return_value=mock_session)

    author = await api.get_comment_author('ISSUE-1', '1')
    assert author == 'Tester'

@pytest.mark.asyncio
async def test_get_attachments_for_comment():
    api = TrackerAPI('http://example.com', 'TOKEN')
    mock_session = MagicMock()
    mock_session.get.return_value = MockResponse({
        'attachments': [
            {
                'fileName': 'file.txt',
                'urls': {'download': 'http://files/file.txt'}
            }
        ]
    })
    api.get_session = AsyncMock(return_value=mock_session)

    atts = await api.get_attachments_for_comment('ISSUE-1', '1')
    assert atts[0]['filename'] == 'file.txt'
    assert 'http://' in atts[0]['content_url']


@pytest.mark.asyncio
async def test_get_attachments_for_comment_display_name():
    api = TrackerAPI('http://example.com', 'TOKEN')
    mock_session = MagicMock()
    mock_session.get.return_value = MockResponse({
        'attachments': [
            {
                'display': 'image.png',
                'self': 'http://files/image.png'
            }
        ]
    })
    api.get_session = AsyncMock(return_value=mock_session)

    atts = await api.get_attachments_for_comment('ISSUE-1', '1')
    assert atts[0]['filename'] == 'image.png'
    assert atts[0]['content_url'].endswith('/download')


@pytest.mark.asyncio
async def test_get_active_issues_filters_statuses():
    api = TrackerAPI('http://example.com', 'TOKEN', queue='CRM')
    mock_session = MagicMock()
    mock_session.post.return_value = MockResponse([
        {'key': 'ISSUE-1', 'status': {'key': 'open'}},
        {'key': 'ISSUE-2', 'status': {'key': 'closed'}},
        {'key': 'ISSUE-3', 'status': {'key': 'canceled'}},
    ])
    api.get_session = AsyncMock(return_value=mock_session)

    issues = await api.get_active_issues_by_telegram_id(1)
    keys = [i['key'] for i in issues]
    assert keys == ['ISSUE-1']


def test_normalize_comment_id():
    api = TrackerAPI('http://example.com', 'TOKEN')
    assert api._normalize_comment_id('123') == 123
    hex_id = '507f1f77bcf86cd799439011'
    assert api._normalize_comment_id(hex_id) == hex_id
    assert api._normalize_comment_id(321) == 321


@pytest.mark.asyncio
async def test_upload_file_uses_mimetype(tmp_path):
    api = TrackerAPI('http://example.com', 'TOKEN')
    dummy_session = MagicMock()
    dummy_session.post.return_value = MockResponse({"id": 1}, status=201)
    api.get_session = AsyncMock(return_value=dummy_session)

    captured = {}

    class DummyFD:
        def add_field(self, name, f, filename=None, content_type=None):
            captured["content_type"] = content_type

    with patch('aiohttp.FormData', return_value=DummyFD()):
        file_path = tmp_path / 'pic.png'
        file_path.write_bytes(b'data')
        await api.upload_file(str(file_path))

    assert captured["content_type"] == 'image/png'
