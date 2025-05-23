import aiohttp
import logging
from config import Config

class TrackerAPI:
    def __init__(self, session: aiohttp.ClientSession = None):
        self.base_url = "https://api.tracker.yandex.net/v2"
        self.upload_url = f"{self.base_url}/attachments"
        self.headers = {
            "Authorization": f"Bearer {str(Config.TRACKER_TOKEN).strip()}",
            "X-Cloud-Org-ID": str(Config.TRACKER_ORG_ID).strip()
        }
        self._session = session or aiohttp.ClientSession()  # ✅ Создаём сессию, если не передана
        self.queue = Config.TRACKER_QUEUE

    async def get_session(self):
        """Возвращает существующую сессию или создаёт новую."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close_session(self):
        """Закрывает сессию, если она была создана."""
        if self._session:
            await self._session.close()
            self._session = None

    async def upload_file(self, file_path: str):
        """Асинхронная загрузка одного файла в Yandex Tracker."""
        uploaded_files = await self.upload_files([file_path])
        return uploaded_files[0] if uploaded_files else None

    async def upload_files(self, file_paths: list):
        """Асинхронная загрузка нескольких файлов в Yandex Tracker и возврат их ID."""
        attachment_ids = []
        session = await self.get_session()

        for file_path in file_paths:
            try:
                logging.info(f"📤 Загружаем файл: {file_path}")

                async with session.post(
                    self.upload_url,
                    headers=self.headers,
                    data={"file": open(file_path, "rb")}
                ) as response:

                    response_json = await response.json()
                    logging.info(f"📥 Ответ API: {response.status} - {response_json}")

                    if response.status != 201:
                        logging.error(f"❌ Ошибка загрузки файла {file_path}: {response_json}")
                        continue

                    file_id = response_json.get("id")
                    if file_id:
                        attachment_ids.append(file_id)

            except Exception as e:
                logging.error(f"❌ Ошибка при загрузке файла {file_path}: {e}")

        return attachment_ids

    # Внутри TrackerAPI
    async def get_issue_details(self, issue_keys: list[str]):
        """Получает подробности задач по ключам."""
        session = await self.get_session()
        details = []

        for key in issue_keys:
            try:
                async with session.get(
                    f"{self.base_url}/issues/{key}",
                    headers=self.headers
                ) as response:
                    response_json = await response.json()
                    if response.status == 200:
                        details.append(response_json)
                    else:
                        logging.error(f"❌ Ошибка получения задачи {key}: {response.status} - {response_json}")
            except Exception as e:
                logging.error(f"❌ Исключение при получении задачи {key}: {e}")

        return details

    async def get_active_issues_by_telegram_id(self, telegram_id: int):
        query = {
            "filter": {
                "queue": self.queue,
                "telegramId": str(telegram_id)
            }
        }

        session = await self.get_session()  # ← добавь эту строку

        try:
            async with session.post(
                f"{self.base_url}/issues/_search",
                headers=self.headers,
                json=query
            ) as response:
                response_json = await response.json()
                logging.info(f"📥 Ответ API (поиск задач): {response.status} - {response_json}")

                if response.status != 200:
                    logging.error(f"❌ Ошибка поиска задач: {response_json}")
                    return []

                return response_json

        except Exception as e:
            logging.error(f"❌ Ошибка при поиске задач: {e}")
            return []

    async def create_issue(self, title: str, description: str, attachment_ids=None, telegram_id=None):
        session = await self.get_session()
        issue_data = {
            "queue": Config.TRACKER_QUEUE,
            "summary": title,
            "description": description
        }

        # ✅ Добавляем telegram_id как системное поле
        if telegram_id:
            issue_data["telegramId"] = str(telegram_id)

        if isinstance(attachment_ids, list) and attachment_ids:
            filtered_ids = [int(fid) for fid in attachment_ids if str(fid).isdigit()]
            if filtered_ids:
                issue_data["attachmentIds"] = filtered_ids

        try:
            async with session.post(
                f"{self.base_url}/issues",
                headers=self.headers,
                json=issue_data
            ) as response:
                response_json = await response.json()
                logging.info(f"📥 Ответ API (создание задачи): {response.status} - {response_json}")

                if response.status != 201:
                    logging.error(f"❌ Ошибка создания задачи: {response_json}")
                    return None

                return response_json
        except Exception as e:
            logging.error(f"❌ Ошибка при создании задачи: {e}")
            return None

    async def get_issue(self, issue_key: str):
        """Получает детали задачи."""
        session = await self.get_session()
        try:
            async with session.get(
                f"{self.base_url}/issues/{issue_key}",
                headers=self.headers
            ) as response:

                response_json = await response.json()
                if response.status != 200:
                    logging.error(f"❌ Ошибка получения данных о задаче {issue_key}: {response_json}")
                    return None

                return response_json

        except Exception as e:
            logging.error(f"❌ Ошибка при запросе задачи {issue_key}: {e}")
            return None

    async def add_comment(self, issue_key: str, comment_text: str, attachment_ids=None):
        """Добавляет комментарий в задачу."""
        session = await self.get_session()
        comment_data = {"text": comment_text}

        if attachment_ids:
            comment_data["attachments"] = [{"id": file_id} for file_id in attachment_ids]

        try:
            async with session.post(
                f"{self.base_url}/issues/{issue_key}/comments",
                headers=self.headers,
                json=comment_data
            ) as response:

                response_json = await response.json()
                if response.status != 201:
                    logging.error(f"❌ Ошибка при добавлении комментария: {response_json}")
                    return None

                return response_json

        except Exception as e:
            logging.error(f"❌ Ошибка при добавлении комментария к задаче {issue_key}: {e}")
            return None
