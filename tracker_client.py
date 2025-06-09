import logging
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
        # Позволяет переиспользовать одну сессию во всем приложении (рекомендуется)
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
            headers["X-Org-Id"] = self.org_id
        return headers

    async def create_issue(
        self,
        title,
        description,
        attachments=None,
        telegram_id=None,
        extra_fields=None,
    ):
        """
        Создание задачи в трекере.

        :param attachments: список ``fileId`` для прикрепления к задаче
        :param telegram_id: идентификатор автора, пишется в системное поле
            ``telegramId``
        :param extra_fields: словарь дополнительных полей, объединяется с
            основными данными
        """
        url = f"{self.base_url}/v2/issues/"
        data = {
            "summary": title,
            "description": description,
        }
        if self.queue:
            data["queue"] = self.queue
        if attachments:
            data["attachments"] = attachments
        if telegram_id is not None:
            data["telegramId"] = str(telegram_id)
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
        """
        Получить детали задачи по её ключу.
        """
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
        """
        Вернуть активные задачи для указанного Telegram ID.
        """
        url = f"{self.base_url}/v2/issues/_search"
        query = {
            "filter": {
                "queue": self.queue,
                "telegramId": str(telegram_id)
            }
        }
        session = await self.get_session()
        headers = self._get_headers()
        async with session.post(url, json=query, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to search issues: {resp.status} {text}")
                raise Exception(f"Search issues failed: {resp.status} {text}")
            return await resp.json()

    async def add_comment(self, issue_key, comment):
        """
        Добавить комментарий к задаче.
        """
        url = f"{self.base_url}/v2/issues/{issue_key}/comments"
        data = {"text": comment}
        session = await self.get_session()
        headers = self._get_headers()
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status != 201:
                text = await resp.text()
                logger.error(f"Failed to add comment: {resp.status} {text}")
                raise Exception(f"Add comment failed: {resp.status} {text}")
            return await resp.json()

    async def upload_file(self, file_path):
        """
        Загрузить файл и получить его fileId для дальнейших вложений.
        """
        url = f"{self.base_url}/v2/files"
        session = await self.get_session()
        headers = self._get_headers()
        with open(file_path, "rb") as f:
            data = f.read()
        upload_headers = headers.copy()
        upload_headers["Content-Type"] = "application/octet-stream"
        async with session.post(url, data=data, headers=upload_headers) as resp:
            if resp.status != 201:
                text = await resp.text()
                logger.error(f"Failed to upload file: {resp.status} {text}")
                raise Exception(f"Upload file failed: {resp.status} {text}")
            return await resp.json()

    async def add_attachment_comment(self, issue_key, file_id):
        """
        Добавить комментарий с вложением к задаче.
        """
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
        """
        Получить комментарии к задаче (с расширением для вложений).
        """
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
        """
        Получить содержимое файла по self-ссылке.
        """
        session = await self.get_session()
        headers = self._get_headers()
        async with session.get(file_self_url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Failed to get file content: {resp.status} {text}")
                raise Exception(f"Get file content failed: {resp.status} {text}")
            return await resp.read()

    # Если нужно очистить сессию на выходе
    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def __aenter__(self):
        return self

# Для совместимости с "async with TrackerAPI(...) as tracker:"
# Не забудь закрывать сессию в конце работы (или при завершении приложения)!
