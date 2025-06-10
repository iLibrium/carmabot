import logging
import os
import aiohttp

logger = logging.getLogger(__name__)

class TrackerAPI:
    def __init__(self, base_url, token, org_id=None, queue=None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.org_id = org_id
        self.queue = queue
        self._session = None

    async def get_session(self):
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_headers(self):
        headers = {
            "Authorization": f"OAuth {self.token}",
            "Content-Type": "application/json",
        }
        if self.org_id:
            headers["X-Cloud-Org-ID"] = self.org_id
        return headers

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
        headers = self._get_headers()
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status != 201:
                text = await resp.text()
                logger.error(f"Failed to create issue: {resp.status} {text}")
                raise Exception(f"Create issue failed: {resp.status} {text}")
            return await resp.json()

    async def get_issue_details(self, issue_key):
        url = f"{self.base_url}/v2/issues/{issue_key}"
        session = await self.get_session()
        headers = self._get_headers()
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to get issue details: {resp.status} {text}")
                raise Exception(f"Get issue failed: {resp.status} {text}")
            return await resp.json()

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
        headers = self._get_headers()
        async with session.post(url, json=query, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to search issues: {resp.status} {text}")
                raise Exception(f"Search issues failed: {resp.status} {text}")
            issues = await resp.json()

        # Фильтруем закрытые задачи вручную
        filtered = [
            issue for issue in issues
            if issue.get("status", {}).get("key") != "closed"
        ]
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
        headers = self._get_headers()
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status != 201:
                text = await resp.text()
                logger.error(f"Failed to add comment: {resp.status} {text}")
                raise Exception(f"Add comment failed: {resp.status} {text}")
            return await resp.json()

    async def upload_file(self, file_path):
        """Uploads a file to Tracker and returns its attachment ID."""
        url = f"{self.base_url}/v2/attachments"
        session = await self.get_session()
        headers = self._get_headers()
        headers.pop("Content-Type", None)

        with open(file_path, "rb") as f:
            form = aiohttp.FormData()
            form.add_field(
                "file",
                f,
                filename=os.path.basename(file_path),
                content_type="application/octet-stream",
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
        headers = self._get_headers()
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
        headers = self._get_headers()
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to get comments: {resp.status} {text}")
                raise Exception(f"Get comments failed: {resp.status} {text}")
            return await resp.json()

    async def get_file_content(self, file_self_url):
        session = await self.get_session()
        headers = self._get_headers()
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
