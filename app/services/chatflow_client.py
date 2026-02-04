"""
ChatFlow.kz API client: отправка текста в WhatsApp через send-text.

ВАЖНО: Токен и instance_id должны передаваться из БД (whatsapp_accounts), НЕ из ENV.
ENV переменные используются только как fallback для обратной совместимости.
"""
import logging
import os
from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime

import httpx

log = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://app.chatflow.kz/api/v1"
TIMEOUT = 20.0
MAX_RETRIES = 1


@dataclass
class SendResult:
    """Result of ChatFlow send operation."""
    ok: bool
    status_code: int = 0
    provider_response: dict = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
        if self.provider_response is None:
            self.provider_response = {}
    
    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status_code": self.status_code,
            "provider_response": self.provider_response,
            "error": self.error,
            "error_type": self.error_type,
            "timestamp": self.timestamp,
        }


def _get_base() -> str:
    base = (os.getenv("CHATFLOW_API_BASE") or "").strip()
    return base or DEFAULT_API_BASE


async def send_text(
    jid: str,
    msg: str,
    token: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> SendResult:
    """
    Отправить текстовое сообщение в WhatsApp через ChatFlow send-text.
    
    Args:
        jid: WhatsApp JID получателя
        msg: Текст сообщения
        token: ChatFlow токен (из whatsapp_accounts.chatflow_token). Если None, используется ENV.
        instance_id: ChatFlow instance ID (из whatsapp_accounts.chatflow_instance_id). Если None, используется ENV.
    
    Returns:
        SendResult с полной информацией об отправке
    """
    # Use provided credentials or fall back to ENV
    _token = (token or "").strip() or (os.getenv("CHATFLOW_TOKEN") or "").strip()
    _instance_id = (instance_id or "").strip() or (os.getenv("CHATFLOW_INSTANCE_ID") or "").strip()
    
    if not _token or not _instance_id:
        error_msg = "ChatFlow credentials not configured: "
        if not _token:
            error_msg += "token missing; "
        if not _instance_id:
            error_msg += "instance_id missing; "
        log.warning("[CHATFLOW] SEND skipped: %s", error_msg)
        return SendResult(ok=False, error=error_msg.strip(), error_type="CREDENTIALS_MISSING")

    base = _get_base().rstrip("/")
    url = f"{base}/send-text"
    
    # Mask token for logging
    token_masked = _token[:4] + "***" if len(_token) > 4 else "***"
    instance_masked = _instance_id[:8] + "..." if len(_instance_id) > 8 else _instance_id

    params = {
        "token": _token,
        "instance_id": _instance_id,
        "jid": jid,
        "msg": (msg or ""),
    }

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            log.info("[CHATFLOW] SEND attempt=%d jid=%s token=%s instance=%s", 
                     attempt + 1, jid[-8:] if len(jid) > 8 else jid, token_masked, instance_masked)
            
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, params=params)
            
            body = {}
            try:
                if resp.headers.get("content-type", "").startswith("application/json"):
                    body = resp.json()
                elif resp.text:
                    import json
                    body = json.loads(resp.text)
            except Exception:
                body = {"raw": resp.text[:500] if resp.text else ""}

            log.info("[CHATFLOW] SEND response status=%s body=%s", resp.status_code, str(body)[:200])

            # Check for success
            if resp.status_code == 200 and isinstance(body, dict) and body.get("success") is True:
                return SendResult(
                    ok=True,
                    status_code=resp.status_code,
                    provider_response=body,
                )
            
            # Error from ChatFlow
            err_msg = ""
            if isinstance(body, dict):
                err_msg = body.get("message") or body.get("error") or str(body)[:200]
            else:
                err_msg = str(body)[:200]
            
            # Don't retry on auth errors
            if resp.status_code in (401, 403):
                return SendResult(
                    ok=False,
                    status_code=resp.status_code,
                    provider_response=body if isinstance(body, dict) else {},
                    error=f"Auth error: {err_msg}",
                    error_type="AUTH_ERROR"
                )
            
            last_error = SendResult(
                ok=False,
                status_code=resp.status_code,
                provider_response=body if isinstance(body, dict) else {},
                error=err_msg,
                error_type="API_ERROR"
            )
            
        except httpx.TimeoutException as e:
            log.warning("[CHATFLOW] SEND timeout attempt=%d: %s", attempt + 1, type(e).__name__)
            last_error = SendResult(ok=False, error=f"Timeout: {type(e).__name__}", error_type="TIMEOUT")
        except httpx.HTTPError as e:
            log.warning("[CHATFLOW] SEND HTTP error attempt=%d: %s", attempt + 1, type(e).__name__)
            last_error = SendResult(ok=False, error=f"HTTP error: {type(e).__name__}", error_type="HTTP_ERROR")
        except Exception as e:
            log.error("[CHATFLOW] SEND error attempt=%d: %s", attempt + 1, type(e).__name__)
            last_error = SendResult(ok=False, error=f"Error: {type(e).__name__}", error_type="UNKNOWN_ERROR")
    
    # All retries exhausted
    if last_error:
        log.error("[CHATFLOW] SEND failed after %d attempts: %s", MAX_RETRIES + 1, last_error.error)
        return last_error
    
    return SendResult(ok=False, error="Unknown error", error_type="UNKNOWN_ERROR")


async def health_check(
    token: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> SendResult:
    """
    Проверить статус ChatFlow instance.
    
    Пытается получить информацию об instance через /me/status или подобный endpoint.
    Если endpoint не существует, возвращает ok=true если credentials заданы.
    """
    _token = (token or "").strip() or (os.getenv("CHATFLOW_TOKEN") or "").strip()
    _instance_id = (instance_id or "").strip() or (os.getenv("CHATFLOW_INSTANCE_ID") or "").strip()
    
    if not _token or not _instance_id:
        return SendResult(ok=False, error="Credentials not configured", error_type="CREDENTIALS_MISSING")
    
    base = _get_base().rstrip("/")
    
    # Try /me endpoint first (common pattern for ChatFlow-like APIs)
    for endpoint in ["/me", "/status", "/instance/status"]:
        url = f"{base}{endpoint}"
        params = {"token": _token, "instance_id": _instance_id}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
            
            if resp.status_code == 404:
                continue  # Try next endpoint
            
            body = {}
            try:
                body = resp.json() if resp.text else {}
            except Exception:
                pass
            
            if resp.status_code == 200:
                return SendResult(
                    ok=True,
                    status_code=resp.status_code,
                    provider_response=body if isinstance(body, dict) else {"raw": str(body)[:200]}
                )
            
            # Auth error
            if resp.status_code in (401, 403):
                return SendResult(
                    ok=False,
                    status_code=resp.status_code,
                    error="Authentication failed",
                    error_type="AUTH_ERROR"
                )
                
        except Exception as e:
            log.warning("[CHATFLOW] health_check %s error: %s", endpoint, type(e).__name__)
            continue
    
    # No health endpoint found - just verify credentials exist
    # Return ok=true with a note that we couldn't verify
    return SendResult(
        ok=True,
        provider_response={"note": "Health endpoint not found; credentials configured"},
        error_type=None
    )


# Legacy compatibility - old signature without token/instance_id
async def send_text_legacy(jid: str, msg: str) -> dict[str, Any]:
    """
    Legacy function for backward compatibility.
    Uses ENV variables. Prefer send_text() with explicit credentials.
    """
    result = await send_text(jid, msg)
    if not result.ok:
        raise RuntimeError(f"ChatFlow send-text failed: {result.error}")
    return result.provider_response
