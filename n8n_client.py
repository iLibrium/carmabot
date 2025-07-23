import aiohttp
import os

N8N_BASE_URL = os.getenv("N8N_BASE_URL")  # например, http://localhost:5678
N8N_MESSAGE_WEBHOOK_URL = os.getenv(
    "N8N_MESSAGE_WEBHOOK_URL",
    "http://n8n.mxmit.ru:5678/webhook-test/15ce4d64-adee-4522-8591-8463573d0bc6/webhook",
)

async def n8n_create_issue(title, description, telegram_id, attachments=None):
    url = f"{N8N_BASE_URL}/n8n/create_issue"
    payload = {
        "title": title,
        "description": description,
        "telegram_id": telegram_id,
        "attachments": attachments or [],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                raise Exception(await resp.text())
            return await resp.json()


async def n8n_forward_message(token: str, message: str):
    """Send a user message to the configured n8n webhook."""
    if not N8N_MESSAGE_WEBHOOK_URL:
        raise RuntimeError("N8N_MESSAGE_WEBHOOK_URL not configured")

    payload = {"token": token, "message": message}
    async with aiohttp.ClientSession() as session:
        async with session.post(N8N_MESSAGE_WEBHOOK_URL, json=payload) as resp:
            if resp.status != 200:
                raise Exception(await resp.text())
            try:
                return await resp.json()
            except Exception:
                return await resp.text()

# Аналогично реализуем n8n_add_comment, n8n_get_issues, n8n_upload_file и т.д.
