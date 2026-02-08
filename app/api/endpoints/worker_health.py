"""
Worker Health Check Endpoint

Provides health status for followup worker monitoring.
"""
from fastapi import APIRouter
from datetime import datetime
import logging

router = APIRouter(prefix="/worker", tags=["worker"])
log = logging.getLogger(__name__)


@router.get("/health")
async def worker_health():
    """
    Worker health check endpoint
    
    Returns:
        - ok: bool
        - last_tick: datetime or null (when worker last checked for followups)
        - status: "running" | "unknown" | "stale"
    """
    from app.workers.health import get_last_tick, get_status
    
    last_tick = get_last_tick()
    status = get_status()
    
    if status == "stale":
        log.warning(f"[WORKER_HEALTH] Worker appears stale")
    elif status == "unknown":
        log.warning("[WORKER_HEALTH] No worker ticks recorded yet")
    
    return {
        "ok": True,
        "last_tick": last_tick.isoformat() if last_tick else None,
        "status": status,
        "checked_at": datetime.utcnow().isoformat()
    }
