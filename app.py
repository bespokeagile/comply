"""FastAPI application factory for the Comply web server."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start monitor daemon on boot if monitors are running; stop on shutdown."""
    from comply.monitor import get_daemon, list_monitors
    daemon = get_daemon()
    if list_monitors(status="running"):
        daemon.start()

    # Demo mode: no visitor data cleanup needed (scans are deleted immediately)

    yield
    daemon.stop()


def create_comply_app() -> FastAPI:
    """Create and configure the Comply FastAPI application."""
    from comply import __version__
    from comply.demo_security import is_demo_mode

    demo_mode = is_demo_mode()

    app = FastAPI(
        title="BespokeAgile Comply",
        description="Compliance gap analysis for any codebase",
        version=__version__,
        lifespan=_lifespan,
    )

    # CORS -- configurable via env, permissive fallback for local dev
    cors_origins_str = os.environ.get("COMPLY_CORS_ORIGINS", "")
    if cors_origins_str:
        cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
    else:
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip compression for JSON responses and static assets
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Rate limiting via slowapi (always available, enforced on specific routes)
    try:
        from slowapi import Limiter
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address
        from starlette.responses import JSONResponse

        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter

        async def _rate_limit_handler(request, exc):
            retry_after = getattr(exc, "retry_after", 60)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "You've reached the scan limit. Try again shortly, or use an invite link for a higher limit.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    except ImportError:
        log.debug("slowapi not installed; rate limiting disabled")

    # Mount API routes
    from comply.routes import router
    app.include_router(router)

    from comply.monitor_routes import monitor_router
    app.include_router(monitor_router)

    from comply.gate_routes import gate_router
    app.include_router(gate_router)

    from comply.forecast_routes import forecast_router
    app.include_router(forecast_router)

    # Demo routes (rate limiting applied via decorator in routes_demo.py)
    from comply.routes_demo import router as demo_router
    app.include_router(demo_router)

    # Funded scan routes (invite-only server-funded semantic scans)
    from comply.routes_funded import router as funded_router
    app.include_router(funded_router)

    # AI bridge routes (SSE push from MCP to dashboard)
    from comply.bridge_routes import bridge_router
    app.include_router(bridge_router)

    # Mount new dashboard static files
    dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
    if os.path.isdir(dashboard_dir):
        app.mount("/dashboard", StaticFiles(directory=dashboard_dir), name="dashboard")

    # Serve new dashboard at root
    dashboard_index = os.path.join(dashboard_dir, "index.html")

    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard():
        if os.path.isfile(dashboard_index):
            with open(dashboard_index) as f:
                return f.read()
        return RedirectResponse("/legacy")

    # Keep old UI accessible at /legacy
    legacy_path = os.path.join(os.path.dirname(__file__), "ui.html")

    @app.get("/legacy", response_class=HTMLResponse)
    async def serve_legacy():
        if os.path.isfile(legacy_path):
            with open(legacy_path) as f:
                return f.read()
        return "<h1>BespokeAgile Comply</h1><p>Legacy UI not found.</p>"

    # Alice conversation endpoint (requires LLM API key)
    @app.post("/alice")
    async def alice_message(request: Request):
        """Handle a message from the Alice conversation panel."""
        # Check for LLM API key
        llm_key = (
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GROK_API_KEY")
        )
        if not llm_key:
            return JSONResponse(
                status_code=400,
                content={"error": "No LLM API key configured. Set ANTHROPIC_API_KEY or another provider key."},
            )
        try:
            body = await request.json()
            from comply.mcp_server import _handle_alice_message
            result = _handle_alice_message(body)
            return result
        except ImportError:
            return JSONResponse(
                status_code=501,
                content={"reply": "Alice message handler not available. Install MCP dependencies."},
            )
        except Exception as e:
            log.error("Alice message error: %s", e)
            return JSONResponse(
                status_code=500,
                content={"reply": "An error occurred processing your message."},
            )

    # Auto-configure adapters on startup
    try:
        from comply.adapters.registry import auto_configure_from_config
        auto_configure_from_config()
    except Exception as e:
        log.debug("Adapter auto-configuration failed: %s", e)

    return app


