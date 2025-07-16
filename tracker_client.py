import logging
import os
import asyncio
import aiohttp
import mimetypes
from config import Config

logger = logging.getLogger(__name__)

class TrackerAPI:
    def __init__(self, base_url, token, org_id=None, queue=None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.org_id = org_id
        self.queue = queue
        # Store sessions per event loop to avoid cross-loop errors
        self._sessions = {}
        self._connector = None

    async def get_session(self):
        """Return an ``aiohttp`` session bound to the current event loop."""
        loop = asyncio.get_running_loop()
        session = self._sessions.get(loop)
        if session is None or session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            if self._connector is None or self._connector.closed:
                self._connector = aiohttp.TCPConnector(
                    limit=Config.TRACKER_POOL_LIMIT
                )
            session = aiohttp.ClientSession(timeout=timeout, connector=self._connector)
            self._sessions[loop] = session
        return session

    async def close(self):
        """Close all underlying sessions."""
        for session in list(self._sessions.values()):
            if session and not session.closed:
                await session.close()
        self._sessions.clear()
        if self._connector and not self._connector.closed:
            await self._connector.close()
        self._connector = None

    def _get_headers(self):
        headers = {
            "Authorization": f"OAuth {self.token}",
            "Content-Type": "application/json",
        }
        if self.org_id:
            headers["X-Cloud-Org-ID"] = self.org_id
        return headers

    def get_headers(self):
        """Return headers for Tracker API requests."""
        return self._get_headers()

    async def create_issue(self, title, description, extra_fields=None):
        url = f"{self.base_url}/v2/issues/"
        data = {
            "summary": title,
            "description": description,
        }
        if self.queue:
            data["queue"] = self.queue
        if extra_fields:
            data.update(extra_fields)
        session = await self.get_session()
        headers = self.get_headers()
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status != 201:
                text = await resp.text()
                logger.error(f"Failed to create issue: {resp.status} {text}")
                raise Exception(f"Create issue failed: {resp.status} {text}")
            return await resp.json()

    async def get_issue_details(self, issue_key):
        url = f"{self.base_url}/v2/issues/{issue_key}"
        session = await self.get_session()
        headers = self.get_headers()
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to get issue details: {resp.status} {text}")
                raise Exception(f"Get issue failed: {resp.status} {text}")
            return await resp.json()

    async def get_issue(self, issue_key):
        """Fetch issue information."""
        return await self.get_issue_details(issue_key)

    def _normalize_comment_id(self, comment_id):
        """Return comment id cast to ``int`` if it's a digit-only string."""
        if isinstance(comment_id, str) and comment_id.isdigit():
            return int(comment_id)
        return comment_id

    async def get_comment_author(self, issue_key, comment_id):
        """Return display name of the comment author."""
        comment_id = self._normalize_comment_id(comment_id)
        url = f"{self.base_url}/v2/issues/{issue_key}/comments/{comment_id}"
        session = await self.get_session()
        headers = self.get_headers()
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(
                    f"Failed to get comment author: {resp.status} {text}"
                )
                raise Exception(
                    f"Get comment author failed: {resp.status} {text}"
                )
            comment = await resp.json()
        author_info = comment.get("createdBy") or comment.get("author") or {}
        if isinstance(author_info, dict):
            return author_info.get("display") or author_info.get("login")
        return str(author_info)

    async def get_attachments_for_comment(self, issue_key, comment_id):
        """Return attachment info for a comment."""
        comment_id = self._normalize_comment_id(comment_id)
        url = (
            f"{self.base_url}/v2/issues/{issue_key}/comments/{comment_id}?expand=attachments"
        )
        session = await self.get_session()
        headers = self.get_headers()
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(
                    f"Failed to get comment attachments: {resp.status} {text}"
                )
                raise Exception(
                    f"Get attachments failed: {resp.status} {text}"
                )
            comment = await resp.json()
        attachments = []
        for att in comment.get("attachments", []):
            content_url = None
            if isinstance(att.get("urls"), dict):
                content_url = att["urls"].get("download") or att["urls"].get("self")
            content_url = content_url or att.get("contentUrl") or att.get("self")
            if att.get("self") and (not content_url or content_url == att["self"]):
                content_url = f"{att['self']}/download"
            filename = (
                att.get("fileName")
                or att.get("name")
                or att.get("filename")
                or att.get("display")
            )
            if not content_url or not filename:
                logger.warning("Skip attachment without filename or content url: %s", att)
                continue
            attachments.append({"content_url": content_url, "filename": filename})
        return attachments

    async def get_active_issues_by_telegram_id(self, telegram_id: int):
        """Return all user's issues except those in the closed status."""
        url = f"{self.base_url}/v2/issues/_search"
        query = {
            "filter": {
                "queue": self.queue,
                "telegramId": str(telegram_id),
            }
        }
        session = await self.get_session()
        headers = self.get_headers()
        async with session.post(url, json=query, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to search issues: {resp.status} {text}")
                raise Exception(f"Search issues failed: {resp.status} {text}")
            issues = await resp.json()

        # Фильтруем закрытые, отменённые и завершённые задачи вручную
        filtered = []
        for issue in issues:
            status = issue.get("status") or {}
            if isinstance(status, dict):
                key = str(status.get("key", "")).lower()
                name = str(status.get("name", "")).lower()
            else:
                key = str(status).lower()
                name = ""

            skip = False
            if any(w in key for w in ("closed", "canceled", "cancelled", "done")):
                skip = True
            if any(substr in name for substr in ("заверш", "отмен")):
                skip = True

            if not skip:
                filtered.append(issue)

        return filtered

    async def add_comment(
        self,
        issue_key,
        comment,
        attachment_ids=None,
        summonees=None,
        maillist_summonees=None,
        markup_type="md",
    ):
        """Add a comment to an issue using the modern API.

        Parameters
        ----------
        issue_key : str
            Key of the issue.
        comment : str
            Comment text.
        attachment_ids : list[str] | None
            Temporary file identifiers for attachments.
        summonees : list[str] | None
            Users to mention in the comment.
        maillist_summonees : list[str] | None
            Mailing lists to mention.
        markup_type : str
            Markup type of ``comment``. ``md`` enables Markdown/YFM.
        """

        url = f"{self.base_url}/v2/issues/{issue_key}/comments"
        data = {"text": comment, "markupType": markup_type}
        if attachment_ids:
            data["attachmentIds"] = attachment_ids
        if summonees:
            data["summonees"] = summonees
        if maillist_summonees:
            data["maillistSummonees"] = maillist_summonees

        session = await self.get_session()
        headers = self.get_headers()
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status != 201:
                text = await resp.text()
                logger.error(f"Failed to add comment: {resp.status} {text}")
                raise Exception(f"Add comment failed: {resp.status} {text}")
            return await resp.json()

    async def upload_file(self, file_path, orig_filename=None):
        """Uploads a file to Tracker and returns its attachment ID.

        Parameters
        ----------
        file_path : str
            Path to a temporary file to read from.
        orig_filename : str | None
            Original filename to pass to Tracker. If ``None`` the basename of
            ``file_path`` is used.
        """
        url = f"{self.base_url}/v2/attachments"
        session = await self.get_session()
        headers = self.get_headers()
        headers.pop("Content-Type", None)

        with open(file_path, "rb") as f:
            form = aiohttp.FormData()
            mime_type, _ = mimetypes.guess_type(file_path)
            form.add_field(
                "file",
                f,
                filename=orig_filename or os.path.basename(file_path),
                content_type=mime_type or "application/octet-stream",
            )

            async with session.post(url, data=form, headers=headers) as resp:
                if resp.status != 201:
                    text = await resp.text()
                    logger.error(f"Failed to upload file: {resp.status} {text}")
                    raise Exception(f"Upload file failed: {resp.status} {text}")

                json_resp = await resp.json()
                return json_resp.get("id")

    async def add_attachment_comment(self, issue_key, file_id):
        url = f"{self.base_url}/v2/issues/{issue_key}/comments"
        data = {
            "text": "Вложение",
            "attachments": [file_id]
        }
        session = await self.get_session()
        headers = self.get_headers()
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status != 201:
                text = await resp.text()
                logger.error(f"Failed to add attachment comment: {resp.status} {text}")
                raise Exception(f"Add attachment comment failed: {resp.status} {text}")
            return await resp.json()

    async def get_issue_comments(self, issue_key, expand_attachments=False):
        url = f"{self.base_url}/v2/issues/{issue_key}/comments"
        if expand_attachments:
            url += "?expand=attachments"
        session = await self.get_session()
        headers = self.get_headers()
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to get comments: {resp.status} {text}")
                raise Exception(f"Get comments failed: {resp.status} {text}")
            return await resp.json()

    async def get_file_content(self, file_self_url):
        session = await self.get_session()
        headers = self.get_headers()
        async with session.get(file_self_url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to get file content: {resp.status} {text}")
                raise Exception(f"Get file content failed: {resp.status} {text}")
            return await resp.read()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

# Не забудь закрывать сессию в конце работы (или при завершении приложения)!
