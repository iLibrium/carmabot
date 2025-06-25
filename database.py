import asyncpg
import logging
from config import Config

class Database:
    def __init__(self):
        self._pool = None

    async def connect(self):
        """Подключение к базе данных с проверкой"""
        try:
            if not self._pool:
                self._pool = await asyncpg.create_pool(
                    user=Config.DB_USER,
                    password=Config.DB_PASSWORD,
                    database=Config.DB_NAME,
                    host=Config.DB_HOST,
                    port=Config.DB_PORT,
                    min_size=1,  # Минимальное количество соединений
                    max_size=10,  # Максимальное количество соединений
                    timeout=10  # Таймаут на подключение
                )
                logging.info("✅ Подключение к БД установлено")
        except Exception as e:
            logging.error(f"❌ Ошибка подключения к БД: {e}")
            self._pool = None

    async def ensure_connection(self):
        """Гарантирует, что подключение активно"""
        if not self._pool:
            logging.warning("⚠️ Подключение к БД отсутствует. Повторное подключение...")
            await self.connect()
        if not self._pool:
            logging.error("❌ Не удалось восстановить подключение к БД")
            return None
        return await self._pool.acquire()

    async def close(self):
        """Закрывает соединение с БД"""
        if self._pool:
            await self._pool.close()
            logging.info("🔒 Подключение к БД закрыто")
            self._pool = None

    async def get_user(self, user_id: int):
        """Получает информацию о пользователе по user_id."""
        conn = await self.ensure_connection()
        if not conn:
            return None
        try:
            query = "SELECT first_name, last_name, phone_number FROM users WHERE user_id = $1"
            user_data = await conn.fetchrow(query, user_id)
            return dict(user_data) if user_data else None
        finally:
            await self._pool.release(conn)  # ✅ Правильное освобождение соединения

    async def register_user(self, user_id: int, first_name: str, last_name: str, phone_number: str):
        """Регистрирует пользователя в базе данных"""
        conn = await self.ensure_connection()
        if not conn:
            return
        try:
            query = """
            INSERT INTO users (user_id, first_name, last_name, phone_number)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                phone_number = EXCLUDED.phone_number
            """
            await conn.execute(query, user_id, first_name, last_name, phone_number)
            logging.info(f"✅ Пользователь {user_id} зарегистрирован")
        finally:
            await self._pool.release(conn)

    async def create_issue(self, user_id: int, tracker_id: str):
        """Сохраняет созданную задачу в базе данных"""
        conn = await self.ensure_connection()
        if not conn:
            return
        try:
            query = """
            INSERT INTO issues (user_id, tracker_id)
            VALUES ($1, $2)
            """
            await conn.execute(query, user_id, tracker_id)
            logging.info(f"✅ Задача {tracker_id} сохранена для пользователя {user_id}")
        finally:
            await self._pool.release(conn)

    async def get_user_issues(self, user_id: int):
        """Получает список задач пользователя"""
        conn = await self.ensure_connection()
        if not conn:
            return []
        try:
            query = "SELECT tracker_id FROM issues WHERE user_id = $1"
            rows = await conn.fetch(query, user_id)
            return [row["tracker_id"] for row in rows]
        finally:
            await self._pool.release(conn)
