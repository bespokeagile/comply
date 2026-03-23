"""REST endpoints for the Comply monitor daemon."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

monitor_router = APIRouter(prefix="/monitors", tags=["monitors"])


class CreateMonitorRequest(BaseModel):
    repo_path: str
    framework: str = "eu_ai_act"
    scan_depth: str = "content"
    interval_secs: int = 300
    max_files: int = 500
    webhook_url: str = ""


class UpdateMonitorRequest(BaseModel):
    framework: Optional[str] = None
    scan_depth: Optional[str] = None
    interval_secs: Optional[int] = None
    max_files: Optional[int] = None
    webhook_url: Optional[str] = None


# ── Static routes (before /{id}) ──────────────────────────────────────────

@monitor_router.get("/daemon/status")
def daemon_status():
    """Get daemon running status, active monitor count, queue depth."""
    from comply.monitor import get_daemon
    return get_daemon().get_status()


@monitor_router.get("/events/recent")
def recent_events(limit: int = 50):
    """Get recent events across all monitors."""
    from comply.monitor import list_recent_events
    return list_recent_events(limit=limit)


@monitor_router.get("/alerts/recent")
def recent_alerts(limit: int = 50):
    """Get recent alerts across all monitors."""
    from comply.monitor import list_monitor_alerts
    return list_monitor_alerts(limit=limit)


# ── Collection routes ─────────────────────────────────────────────────────

@monitor_router.post("")
def create_monitor_endpoint(req: CreateMonitorRequest):
    """Create a new monitor."""
    from comply.monitor import create_monitor
    mon = create_monitor(
        repo_path=req.repo_path,
        framework=req.framework,
        scan_depth=req.scan_depth,
        interval_secs=req.interval_secs,
        max_files=req.max_files,
        webhook_url=req.webhook_url,
    )
    return mon


@monitor_router.get("")
def list_monitors_endpoint(status: Optional[str] = None):
    """List monitors, optionally filtered by status."""
    from comply.monitor import list_monitors
    return list_monitors(status=status)


# ── Item routes ───────────────────────────────────────────────────────────

@monitor_router.get("/{monitor_id}")
def get_monitor_endpoint(monitor_id: str):
    """Get monitor detail."""
    from comply.monitor import get_monitor
    mon = get_monitor(monitor_id)
    if mon is None:
        raise HTTPException(404, f"Monitor '{monitor_id}' not found")
    return mon


@monitor_router.put("/{monitor_id}")
def update_monitor_endpoint(monitor_id: str, req: UpdateMonitorRequest):
    """Update monitor configuration."""
    from comply.monitor import get_monitor, update_monitor
    if get_monitor(monitor_id) is None:
        raise HTTPException(404, f"Monitor '{monitor_id}' not found")

    kwargs = {k: v for k, v in req.dict().items() if v is not None}
    mon = update_monitor(monitor_id, **kwargs)
    return mon


@monitor_router.delete("/{monitor_id}")
def delete_monitor_endpoint(monitor_id: str):
    """Delete a monitor and its events/alerts."""
    from comply.monitor import delete_monitor
    ok = delete_monitor(monitor_id)
    if not ok:
        raise HTTPException(404, f"Monitor '{monitor_id}' not found")
    return {"ok": True, "deleted": monitor_id}


@monitor_router.post("/{monitor_id}/start")
def start_monitor_endpoint(monitor_id: str):
    """Start a monitor (starts daemon if needed)."""
    from comply.monitor import get_monitor, start_monitor
    if get_monitor(monitor_id) is None:
        raise HTTPException(404, f"Monitor '{monitor_id}' not found")
    mon = start_monitor(monitor_id)
    return mon


@monitor_router.post("/{monitor_id}/stop")
def stop_monitor_endpoint(monitor_id: str):
    """Stop a monitor (stops daemon if no monitors running)."""
    from comply.monitor import get_monitor, stop_monitor
    if get_monitor(monitor_id) is None:
        raise HTTPException(404, f"Monitor '{monitor_id}' not found")
    mon = stop_monitor(monitor_id)
    return mon


@monitor_router.get("/{monitor_id}/events")
def monitor_events_endpoint(monitor_id: str, limit: int = 50):
    """Get events for a specific monitor."""
    from comply.monitor import get_monitor, list_monitor_events
    if get_monitor(monitor_id) is None:
        raise HTTPException(404, f"Monitor '{monitor_id}' not found")
    return list_monitor_events(monitor_id, limit=limit)


@monitor_router.get("/{monitor_id}/alerts")
def monitor_alerts_endpoint(monitor_id: str, limit: int = 50):
    """Get alerts for a specific monitor."""
    from comply.monitor import get_monitor, list_monitor_alerts
    if get_monitor(monitor_id) is None:
        raise HTTPException(404, f"Monitor '{monitor_id}' not found")
    return list_monitor_alerts(monitor_id=monitor_id, limit=limit)
