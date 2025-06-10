from unittest.mock import AsyncMock, MagicMock
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
