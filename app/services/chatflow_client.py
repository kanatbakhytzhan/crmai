"""
ChatFlow.kz API client: отправка текста в WhatsApp через send-text.
Использует ENV: CHATFLOW_TOKEN, CHATFLOW_INSTANCE_ID, CHATFLOW_API_BASE (опционально).
"""
import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://app.chatflow.kz/api/v1"
TIMEOUT = 20.0


def _get_base() -> str:
    base = (os.getenv("CHATFLOW_API_BASE") or "").strip()
    return base or DEFAULT_API_BASE


async def send_text(jid: str, msg: str) -> dict[str, Any]:
    """
    Отправить текстовое сообщение в WhatsApp через ChatFlow send-text.
    GET {CHATFLOW_API_BASE}/send-text?token=...&instance_id=...&jid=...&msg=...
    Логирует status и body; выбрасывает исключение если success != true.
    """
    token = (os.getenv("CHATFLOW_TOKEN") or "").strip()
    instance_id = (os.getenv("CHATFLOW_INSTANCE_ID") or "").strip()
    if not token or not instance_id:
        log.warning("[CHATFLOW] SEND skipped: CHATFLOW_TOKEN or CHATFLOW_INSTANCE_ID not set")
        raise ValueError("CHATFLOW_TOKEN and CHATFLOW_INSTANCE_ID must be set")

    base = _get_base().rstrip("/")
    url = f"{base}/send-text"

    params = {
        "token": token,
        "instance_id": instance_id,
        "jid": jid,
        "msg": (msg or ""),
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not body and resp.text:
            try:
                import json
                body = json.loads(resp.text)
            except Exception:
                body = {"raw": resp.text[:500]}

        log.info("[CHATFLOW] SEND response status=%s body=%s", resp.status_code, body)

        result = dict(body) if isinstance(body, dict) else {}
        result["status_code"] = resp.status_code
        result["response_text"] = resp.text

        if not (isinstance(body, dict) and body.get("success") is True):
            err_msg = body.get("message") or body.get("error") or str(body)[:200]
            raise RuntimeError(f"ChatFlow send-text failed: {err_msg}")
        return result
    except httpx.HTTPError as e:
        log.error("[CHATFLOW] ERROR send_text HTTP: %s", type(e).__name__)
        raise
    except Exception as e:
        log.error("[CHATFLOW] ERROR send_text: %s", type(e).__name__)
        raise
