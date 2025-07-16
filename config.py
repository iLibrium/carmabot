from dotenv import load_dotenv
import os

load_dotenv(override=True)

class Config:
    # Telegram
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    TELEGRAM_POOL_SIZE = int(os.getenv('TELEGRAM_POOL_SIZE', 40))
    TELEGRAM_KEEPALIVE = int(os.getenv('TELEGRAM_KEEPALIVE', TELEGRAM_POOL_SIZE // 2))
    TELEGRAM_READ_TIMEOUT = float(os.getenv('TELEGRAM_READ_TIMEOUT', 60))
    TELEGRAM_CONNECT_TIMEOUT = float(os.getenv('TELEGRAM_CONNECT_TIMEOUT', 30))
    TELEGRAM_HTTP2 = os.getenv('TELEGRAM_HTTP2', '1') not in ('0', 'false', 'False')
    
    # Yandex Tracker
    TRACKER_TOKEN = os.getenv('TRACKER_TOKEN')
    TRACKER_ORG_ID = os.getenv('TRACKER_ORG_ID')
    TRACKER_QUEUE = os.getenv('TRACKER_QUEUE')  # Добавлено
    TRACKER_POOL_LIMIT = int(os.getenv('TRACKER_POOL_LIMIT', 20))

    API_TOKEN = os.getenv('API_TOKEN')  # Добавлено

    # Default values for Tracker issue creation
    PROJECT = {
        "self": "https://api.tracker.yandex.net/v2/projects/4",
        "id": "4",
        "display": "CRM",
    }
    # Default tags for created issues
    DEFAULT_TAGS = ["Запрос"]

    # Custom field for product selection
    PRODUCT_CUSTOM_FIELD = "67c0879c407b93717eac01e6--product"
    PRODUCT_DEFAULT = ["CRM"]

    # Maximum allowed file size for uploads (50 MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024

    
    # PostgreSQL
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_NAME = os.getenv('DB_NAME')
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = os.getenv('DB_PORT')
    
    # Для совместимости со старым кодом
    DB_CONFIG = {
        'user': DB_USER,
        'password': DB_PASSWORD,
        'database': DB_NAME,
        'host': DB_HOST,
        'port': DB_PORT
    }
