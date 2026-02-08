"""
Worker Health Check Endpoint

Provides health status for followup worker monitoring.
"""
from fastapi import APIRouter
from datetime import datetime
import logging

router = APIRouter(prefix="/worker", tags=["worker"])
log = logging.getLogger(__name__)

# Simple in-memory state (in production, use Redis or DB)
_last_worker_tick = None


def update_worker_tick():
    """Called by worker to update last tick timestamp"""
    global _last_worker_tick
    _last_worker_tick = datetime.utcnow()


@router.get("/health")
async def worker_health():
    """
    Worker health check endpoint
    
    Returns:
        - ok: bool
        - last_tick: datetime or null (when worker last checked for followups)
        - status: "running" | "unknown" | "stale"
    """
    global _last_worker_tick
    
    if _last_worker_tick is None:
        status = "unknown"
        log.warning("[WORKER_HEALTH] No worker ticks recorded yet")
    else:
        # Check if worker ticked in last 5 minutes
        elapsed = (datetime.utcnow() - _last_worker_tick).total_seconds()
        if elapsed < 300:  # 5 minutes
            status = "running"
        else:
            status = "stale"
            log.warning(f"[WORKER_HEALTH] Worker appears stale, last tick {elapsed:.0f}s ago")
    
    return {
        "ok": True,
        "last_tick": _last_worker_tick.isoformat() if _last_worker_tick else None,
        "status": status,
        "checked_at": datetime.utcnow().isoformat()
    }
