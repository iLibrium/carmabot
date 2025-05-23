import httpx
import logging
import re
from typing import Any, Dict, Optional, List

class TrackerAPI:
    def __init__(
        self,
        base_url: str,
        token: str,
        org_id: Optional[str] = None,
        queue: Optional[str] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"OAuth {token}",
            "Content-Type": "application/json",
        }
        if org_id:
            self.headers["X-Org-Id"] = org_id
        self.queue = queue
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

    async def close(self):
        await self.client.aclose()

    # 1. Создать задачу (issue)
    async def create_issue(self, summary: str, description: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/v2/issues"
        data = {
            "summary": summary,
            "description": description
        }
        if self.queue:
            data["queue"] = self.queue
        try:
            resp = await self.client.post(url, headers=self.headers, json=data)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in create_issue: {exc}")
        return None

    # 2. Получить подробности задач (по ключам)
    async def get_issue_details(self, issue_keys: List[str]) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}/v2/issues/_search"
        data = {
            "filter": {
                "key": issue_keys
            },
            "expand": ["description", "attachments"]
        }
        try:
            resp = await self.client.post(url, headers=self.headers, json=data)
            resp.raise_for_status()
            return resp.json().get("issues", [])
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in get_issue_details: {exc}")
        return None

    # 3. Получить комментарии к задаче (с вложениями)
    async def get_issue_comments(self, issue_key: str, expand_attachments: bool = True) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}/v2/issues/{issue_key}/comments"
        params = {"expand": "attachments"} if expand_attachments else None
        try:
            resp = await self.client.get(url, headers=self.headers, params=params)
            resp.raise_for_status()
            return resp.json().get("comments", [])
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in get_issue_comments: {exc}")
        return None

    # 4. Получить информацию о вложении (по self url)
    async def get_attachment_info(self, self_url: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await self.client.get(self_url, headers=self.headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in get_attachment_info: {exc}")
        return None

    # 5. Загрузить файл и получить его id
    async def upload_file(self, file_path: str) -> Optional[str]:
        url = f"{self.base_url}/v2/attachments"
        try:
            with open(file_path, "rb") as f:
                files = {'file': (file_path, f)}
                resp = await self.client.post(url, headers={"Authorization": self.headers["Authorization"]}, files=files)
                resp.raise_for_status()
                result = resp.json()
                return result.get("id")
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in upload_file: {exc}")
        return None

    # 6. Добавить текстовый комментарий к задаче
    async def add_comment(self, issue_key: str, comment: str) -> bool:
        url = f"{self.base_url}/v2/issues/{issue_key}/comments"
        data = {"text": comment}
        try:
            resp = await self.client.post(url, headers=self.headers, json=data)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in add_comment: {exc}")
        return False

    # 7. Добавить комментарий с вложением к задаче
    async def add_attachment_comment(self, issue_key: str, file_id: str, text: str = "Файл прикреплен.") -> bool:
        url = f"{self.base_url}/v2/issues/{issue_key}/comments"
        data = {
            "attachments": [file_id],
            "text": text
        }
        try:
            resp = await self.client.post(url, headers=self.headers, json=data)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in add_attachment_comment: {exc}")
        return False

    # 8. Извлечь ключ задачи из текста
    @staticmethod
    def extract_issue_key(text: str) -> Optional[str]:
        match = re.search(r"\b([A-Z]+-\d+)\b", text)
        return match.group(1) if match else None

    # 9. Получить задачи по очереди
    async def get_issues_by_queue(self, queue: str, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}/v2/issues/_search"
        data = {
            "filter": {
                "queue": queue
            },
            "orderBy": "-createdAt",
            "pageSize": limit
        }
        try:
            resp = await self.client.post(url, headers=self.headers, json=data)
            resp.raise_for_status()
            return resp.json().get("issues", [])
        except Exception as exc:
            logging.error(f"TrackerAPI: Error in get_issues_by_queue: {exc}")
        return None
