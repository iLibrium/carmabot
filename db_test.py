import asyncpg
import asyncio
from config import Config

async def test():
    try:
        conn = await asyncpg.connect(
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            host=Config.DB_HOST,
            port=Config.DB_PORT
        )
        print("✅ Подключение успешно!")
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

asyncio.run(test())