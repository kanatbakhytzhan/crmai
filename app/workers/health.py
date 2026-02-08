"""
Worker Health State - Shared module for health monitoring

This module stores the last worker tick timestamp.
Used by both the worker and the health endpoint to avoid circular imports.
"""
from datetime import datetime
from typing import Optional

_last_tick: Optional[datetime] = None


def update_tick():
    """Update the last worker tick timestamp (called by worker)"""
    global _last_tick
    _last_tick = datetime.utcnow()


def get_last_tick() -> Optional[datetime]:
    """Get the last worker tick timestamp (called by health endpoint)"""
    return _last_tick


def get_status() -> str:
    """
    Get worker status based on last tick
    
    Returns:
        "running" if ticked in last 5 minutes
        "stale" if ticked more than 5 minutes ago
        "unknown" if never ticked
    """
    if _last_tick is None:
        return "unknown"
    
    elapsed = (datetime.utcnow() - _last_tick).total_seconds()
    return "running" if elapsed < 300 else "stale"
