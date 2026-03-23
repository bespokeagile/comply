"""Funded scan routes: invite-only server-funded semantic scans + admin API."""
from __future__ import annotations

import logging
import threading
import tempfile
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from comply.funded import (
    check_token,
    get_admin_token,
    get_funded_api_key,
    get_funded_model,
    get_max_files,
    get_usage_stats,
    grant_credits,
    has_credits,
    is_funded_enabled,
    list_users,
    revoke_credits,
    use_credit,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["funded"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_admin(request: Request):
    """Verify admin token from Authorization header."""
    admin_token = get_admin_token()
    if not admin_token:
        raise HTTPException(503, "Funded scans admin not configured (set COMPLY_FUNDED_ADMIN_TOKEN)")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    else:
        token = auth
    if token != admin_token:
        raise HTTPException(401, "Invalid admin token")


def _require_funded():
    """Check that funded scans are enabled and configured."""
    if not is_funded_enabled():
        raise HTTPException(503, "Funded scans are not enabled")
    if not get_funded_api_key():
        raise HTTPException(503, "Funded scans API key not configured")


# ---------------------------------------------------------------------------
# User-facing: check credits + run funded scan
# ---------------------------------------------------------------------------


@router.get("/demo/funded/check")
def check_funded_credits(token: str = ""):
    """Check credits remaining for an invite token."""
    if not is_funded_enabled():
        return {"enabled": False, "remaining": 0}
    info = check_token(token)
    if info is None:
        return {"enabled": True, "valid": False, "remaining": 0}
    return {
        "enabled": True,
        "valid": True,
        "email": info["email"],
        "remaining": info["remaining"],
        "total_credits": info["total_credits"],
        "used_credits": info["used_credits"],
    }


class FundedScanRequest(BaseModel):
    url: str
    framework: str = "eu-ai-act"
    token: str  # invite token
    baseline_id: Optional[str] = None


@router.post("/demo/funded-scan")
def funded_scan(req: FundedScanRequest, request: Request):
    """Run a semantic scan using the server's API key (requires valid invite token)."""
    _require_funded()

    # Validate invite token has credits
    if not has_credits(req.token):
        info = check_token(req.token)
        if info is None:
            raise HTTPException(401, "Invalid invite token")
        raise HTTPException(403, "No funded scan credits remaining")

    # Validate URL (reuse demo security)
    from comply.demo_security import validate_demo_url, validate_framework
    url_err = validate_demo_url(req.url)
    if url_err:
        raise HTTPException(400, url_err)
    fw_err = validate_framework(req.framework)
    if fw_err:
        raise HTTPException(400, fw_err)

    # Create scan record
    from comply.scan_state import create_scan, update_scan
    output_dir = tempfile.mkdtemp(prefix="comply-funded-")
    scan = create_scan(
        url=req.url,
        framework=req.framework,
        depth="semantic",
        output_dir=output_dir,
    )
    update_scan(scan.id, status="pending")

    # Run in background thread
    t = threading.Thread(
        target=_run_funded_scan_thread,
        args=(scan.id, req.url, req.framework, req.token, request.headers.get("X-Visitor-Id", ""), req.baseline_id),
        daemon=True,
    )
    t.start()

    return Response(
        content='{"scanId": "' + scan.id + '", "status": "pending", "funded": true}',
        media_type="application/json",
        headers={"X-Key-Retention": "none", "X-Key-Policy": "server-funded-scan"},
    )


def _run_funded_scan_thread(scan_id: str, url: str, framework: str, token: str, visitor_id: str, baseline_id: str = None):
    """Execute a funded semantic scan in a background thread."""
    from comply.scan_state import get_scan, update_scan

    scan = get_scan(scan_id)
    if scan is None:
        return

    _STEP_STATUS_MAP = {
        "resolving": "cloning",
        "resolved": "cloning",
        "initializing": "scanning",
        "cache_hit": "scanning",
        "scanning": "scanning",
        "building": "building",
        "evaluating": "evaluating",
        "generating": "evaluating",
        "complete": "complete",
    }

    def on_progress(step: str, detail: str = ""):
        status = _STEP_STATUS_MAP.get(step, scan.status)
        update_scan(scan_id, status=status, progress_step=step, progress_detail=detail)

    try:
        api_key = get_funded_api_key()
        model = get_funded_model()
        max_files = get_max_files()

        from comply.scanner import run_comply_scan
        report = run_comply_scan(
            target=url,
            framework=framework,
            scan_depth="semantic",
            output_dir=scan.output_dir,
            llm_api_key=api_key,
            llm_provider="anthropic",
            max_files=max_files,
            on_progress=on_progress,
            use_cache=True,
            baseline_id=baseline_id,
        )

        # Track usage
        model_info = report.get("_model_info", {})
        input_tokens = model_info.get("input_tokens", 0)
        output_tokens = model_info.get("output_tokens", 0)
        # Rough cost estimate: Sonnet 4.5 pricing ($3/M input, $15/M output)
        estimated_cost = (input_tokens * 3 + output_tokens * 15) / 1_000_000

        use_credit(
            token=token,
            scan_id=scan_id,
            framework=framework,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
        )

        # Tag with funded source
        report["_funded"] = True
        report["_funded_model"] = model
        report["_estimated_cost_usd"] = round(estimated_cost, 4)

        from datetime import datetime, timezone
        update_scan(
            scan_id,
            status="complete",
            report=report,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        # Save metadata for persistence (same as cost-scan flow)
        try:
            from comply.store import save_scan_metadata, increment_demo_counter
            save_scan_metadata(report, visitor_id=visitor_id)
            increment_demo_counter("funded_scans_total")
            increment_demo_counter("funded_cost_usd", estimated_cost)
        except Exception as exc:
            log.debug("Funded scan metadata save failed: %s", exc)

    except Exception as exc:
        update_scan(scan_id, status="error", error=str(exc))
        log.error("Funded scan %s failed: %s", scan_id, exc)


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


class GrantRequest(BaseModel):
    email: str
    credits: int = 5


@router.post("/admin/funded/grant")
def admin_grant(req: GrantRequest, request: Request):
    """Grant funded scan credits to an email. Returns invite token."""
    _require_admin(request)
    result = grant_credits(req.email, req.credits)
    return result


class RevokeRequest(BaseModel):
    email: str
    reduce_by: Optional[int] = None  # None = full revoke


@router.post("/admin/funded/revoke")
def admin_revoke(req: RevokeRequest, request: Request):
    """Revoke or reduce credits for an email."""
    _require_admin(request)
    result = revoke_credits(req.email, req.reduce_by)
    if result is None:
        raise HTTPException(404, f"No funded credits found for {req.email}")
    return result


@router.get("/admin/funded/usage")
def admin_usage(request: Request):
    """Return funded scan usage statistics."""
    _require_admin(request)
    return get_usage_stats()


@router.get("/admin/funded/users")
def admin_users(request: Request):
    """List all invited users with credit info."""
    _require_admin(request)
    return list_users()


class ConfigUpdate(BaseModel):
    enabled: Optional[bool] = None


@router.post("/admin/funded/config")
def admin_config(req: ConfigUpdate, request: Request):
    """Update funded scan configuration (runtime only, not persisted to env)."""
    _require_admin(request)
    # For now, just report current config. True config changes require env vars.
    return {
        "enabled": is_funded_enabled(),
        "daily_cap": get_funded_api_key() is not None,
        "note": "Configuration is managed via environment variables. Use fly secrets or .env to change.",
    }
