"""REST endpoints for the Comply CI/CD Compliance Gate."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

gate_router = APIRouter(prefix="/gate", tags=["gate"])


class GateRequest(BaseModel):
    repo_path: str
    framework: str = "eu_ai_act"
    scan_depth: str = "content"
    max_files: int = 500
    threshold_score: float = 0.0
    fail_on_regression: bool = False
    max_critical_gaps: int = -1
    use_cache: bool = False


@gate_router.post("")
def run_gate(req: GateRequest):
    """Run a compliance gate check. Returns structured pass/fail decision.

    Synchronous — blocks while scanning. Typical scan takes 5-15 seconds.
    """
    from comply.gate import run_gate as _run_gate

    try:
        result = _run_gate(
            repo_path=req.repo_path,
            framework=req.framework,
            scan_depth=req.scan_depth,
            max_files=req.max_files,
            threshold_score=req.threshold_score,
            fail_on_regression=req.fail_on_regression,
            max_critical_gaps=req.max_critical_gaps,
            use_cache=req.use_cache,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@gate_router.get("/decisions")
def list_decisions(
    repo: Optional[str] = None,
    framework: Optional[str] = None,
    limit: int = 50,
):
    """List past gate decisions with optional filters."""
    from comply.store import list_gate_decisions
    return list_gate_decisions(repo=repo, framework=framework, limit=limit)


@gate_router.get("/summary")
def gate_summary(
    repo: Optional[str] = None,
    framework: Optional[str] = None,
):
    """Aggregate gate decision statistics: total, passed, failed, pass rate."""
    from comply.store import get_gate_summary
    return get_gate_summary(repo=repo, framework=framework)


@gate_router.get("/{decision_id}")
def get_decision(decision_id: str):
    """Get a single gate decision by ID."""
    from comply.store import get_gate_decision

    d = get_gate_decision(decision_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Gate decision not found")
    return d


@gate_router.get("/badge/{framework}")
def badge(framework: str, repo: Optional[str] = None):
    """Return an SVG compliance badge showing the latest score for a framework.

    Usage in README: ![Comply](https://your-server/gate/badge/eu_ai_act?repo=my-repo)
    """
    from comply.store import get_latest_scan

    fw = framework.replace("-", "_")
    scan = get_latest_scan(repo_path=repo, framework=fw) if repo else None

    # Fallback: get most recent scan for this framework
    if not scan:
        from comply.store import _get_conn
        conn = _get_conn()
        row = conn.execute(
            "SELECT score FROM scans WHERE framework = ? AND status = 'complete' "
            "ORDER BY created_at DESC LIMIT 1",
            (fw,),
        ).fetchone()
        score = round(row["score"]) if row else None

    else:
        score = round(scan.get("score", 0))

    if score is None:
        label = "comply"
        value = "no data"
        color = "#555"
    else:
        label = fw.replace("_", " ")
        value = f"{score}%"
        color = "#3fb950" if score >= 70 else "#d29922" if score >= 40 else "#f85149"

    # Shields.io-compatible SVG badge
    label_width = max(len(label) * 6.5 + 10, 50)
    value_width = max(len(value) * 7 + 10, 40)
    total_width = label_width + value_width

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="a"><rect width="{total_width}" height="20" rx="3"/></clipPath>
  <g clip-path="url(#a)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,sans-serif" font-size="11">
    <text x="{label_width/2}" y="14">{label}</text>
    <text x="{label_width + value_width/2}" y="14">{value}</text>
  </g>
</svg>"""

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, max-age=300"},
    )
