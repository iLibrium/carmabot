import aiohttp
import os

N8N_BASE_URL = os.getenv("N8N_BASE_URL")  # например, http://localhost:5678

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

# Аналогично реализуем n8n_add_comment, n8n_get_issues, n8n_upload_file и т.д.
