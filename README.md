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
| `TELEGRAM_POOL_SIZE` | Number of HTTP connections for Telegram API |
| `TELEGRAM_KEEPALIVE` | Keep-alive pool size for Telegram requests |
| `TELEGRAM_READ_TIMEOUT` | Read timeout for Telegram requests |
| `TELEGRAM_CONNECT_TIMEOUT` | Connect timeout for Telegram requests |
| `TELEGRAM_HTTP2` | Enable HTTP/2 for Telegram API (`1`/`0`) |
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

## Sending and receiving attachments

To attach files when creating a comment you must first upload them to Tracker.
Send each file to `/v2/attachments` and pass the returned IDs in the
`attachmentIds` field when calling `/v2/issues/{key}/comments`.

When receiving webhooks the bot downloads attachments by calling
`/v2/issues/{key}/comments/{id}?expand=attachments`.
Images up to 10&nbsp;MB are sent using `sendPhoto`. Larger files or images that
Telegram fails to process are delivered with `sendDocument`. Files larger than
50&nbsp;MB are rejected.

Example payload for the webhook endpoint:

```json
{
  "event": "commentCreated",
  "issue": {"key": "ISSUE-1", "summary": "Test", "telegramId": "123"},
  "comment": {
    "id": "1",
    "text": "hi",
    "createdBy": {"display": "Tester"}
  }
}
```

