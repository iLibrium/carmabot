import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pytest
from database import Database

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name, conn_method, args",
    [
        ("get_user", "fetchrow", (1,)),
        ("register_user", "execute", (1, "a", "b", "c")),
        ("create_issue", "execute", (1, "ISSUE-1")),
        ("get_user_issues", "fetch", (1,)),
    ],
)
async def test_release_called_on_exception(monkeypatch, method_name, conn_method, args):
    db = Database()
    conn = MagicMock()
    setattr(conn, conn_method, AsyncMock(side_effect=Exception("boom")))
    db._pool = MagicMock()
    db._pool.release = AsyncMock()

    async def fake_ensure_connection():
        return conn

    monkeypatch.setattr(db, "ensure_connection", fake_ensure_connection)

    with pytest.raises(Exception):
        await getattr(db, method_name)(*args)

    db._pool.release.assert_called_once_with(conn)


@pytest.mark.asyncio
async def test_no_release_when_no_connection(monkeypatch):
    db = Database()
    db._pool = MagicMock()
    db._pool.release = AsyncMock()

    async def fake_ensure_connection():
        return None

    monkeypatch.setattr(db, "ensure_connection", fake_ensure_connection)

    result = await db.get_user(1)
    assert result is None
    db._pool.release.assert_not_called()

