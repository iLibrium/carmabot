# Carmabot

Carmabot is a Telegram bot integrated with Yandex Tracker. It uses FastAPI for webhook handling and PostgreSQL for persistence.

## Installation

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

The bot is configured via environment variables. You can place them in a `.env` file or export them before running the bot.

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token |
| `TRACKER_TOKEN` | Yandex Tracker API token |
| `TRACKER_ORG_ID` | Tracker organization ID |
| `TRACKER_QUEUE` | Default Tracker queue |
| `API_TOKEN` | Token used to authorize incoming webhooks |
| `DB_USER` | PostgreSQL user name |
| `DB_PASSWORD` | PostgreSQL user password |
| `DB_NAME` | PostgreSQL database name |
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port |

## Running the bot

After configuring environment variables, start the bot with:

```bash
python main.py --host 0.0.0.0 --port 8000
```

The bot will start polling Telegram and expose FastAPI webhook endpoints.

## Running tests

Install test dependencies (already included in `requirements.txt`) and run:

```bash
pytest
```

