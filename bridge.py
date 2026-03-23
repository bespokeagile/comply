"""AI bridge event bus -- pushes events from MCP tools to the dashboard via SSE."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process event bus (server-side)
# ---------------------------------------------------------------------------

_clients: Dict[str, asyncio.Queue] = {}
_lock = threading.Lock()


def subscribe() -> Tuple[str, asyncio.Queue]:
    """Register an SSE client. Returns (client_id, queue)."""
    import uuid
    client_id = uuid.uuid4().hex[:12]
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    with _lock:
        _clients[client_id] = q
    log.debug("bridge: client %s subscribed (%d total)", client_id, len(_clients))
    return client_id, q


def unsubscribe(client_id: str) -> None:
    """Remove an SSE client on disconnect."""
    with _lock:
        _clients.pop(client_id, None)
    log.debug("bridge: client %s unsubscribed", client_id)


def client_count() -> int:
    """Number of connected SSE clients."""
    with _lock:
        return len(_clients)


def push_event(event_type: str, payload: Optional[Dict[str, Any]] = None) -> int:
    """Fan out an event to all connected SSE clients.

    Returns the number of clients that received the event.
    """
    data = {"type": event_type, **(payload or {})}
    sent = 0
    with _lock:
        dead = []
        for cid, q in _clients.items():
            try:
                q.put_nowait(data)
                sent += 1
            except asyncio.QueueFull:
                dead.append(cid)
        for cid in dead:
            _clients.pop(cid, None)
    return sent


# ---------------------------------------------------------------------------
# HTTP notify helper (for MCP process -> Comply server)
# ---------------------------------------------------------------------------

def notify_dashboard(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    port: Optional[int] = None,
) -> bool:
    """POST an event to the co-located Comply server's /bridge/push endpoint.

    Fire-and-forget: returns True on success, False on any failure.
    The MCP tool should never block or fail because of this.
    """
    if port is None:
        port = int(os.environ.get("COMPLY_PORT", "8001"))

    url = f"http://127.0.0.1:{port}/bridge/push"
    body = json.dumps({"type": event_type, **(payload or {})}).encode()

    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, Exception) as exc:
        log.debug("bridge notify failed (non-fatal): %s", exc)
        return False
