"""AI bridge SSE endpoints -- pushes AI events to the dashboard in real time."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from comply.bridge import subscribe, unsubscribe, push_event, client_count

log = logging.getLogger(__name__)
bridge_router = APIRouter(tags=["bridge"])


@bridge_router.get("/bridge/events")
async def bridge_events(request: Request):
    """SSE stream -- dashboard connects here to receive AI events."""
    client_id, queue = subscribe()

    async def _generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            unsubscribe(client_id)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@bridge_router.post("/bridge/push")
async def bridge_push(request: Request):
    """Accept an AI event and fan out to all SSE clients.

    Blocked in demo mode (AI bridge is local-only).
    """
    from comply.demo_security import is_demo_mode

    if is_demo_mode():
        return JSONResponse(
            status_code=403,
            content={"error": "AI bridge disabled in demo mode"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON"},
        )

    event_type = body.pop("type", None)
    if not event_type:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing 'type' field"},
        )

    n = push_event(event_type, body)
    return JSONResponse(content={"ok": True, "clients": n})
