"""Demo API endpoints: pre-scanned repos, cost scan, visitor scan management."""
from __future__ import annotations

import logging
import os
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from comply.demo_security import (
    ALLOWED_FRAMEWORKS,
    check_clone_size,
    is_demo_mode,
    validate_demo_url,
    validate_framework,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    def _rate_limit_key(request: Request) -> str:
        """Use invite token as key if present (separate, higher bucket)."""
        token = request.headers.get("X-Invite-Token", "")
        if token:
            return f"invited:{token[:16]}"
        return get_remote_address(request)

    _limiter = Limiter(key_func=_rate_limit_key)
except ImportError:
    _limiter = None

# Rate limit: 20/hr per bucket. Invite holders get a separate bucket
# via _rate_limit_key, so they don't compete with anonymous users.
_RATE_LIMIT = "20/hour"


def _load_demo_repos() -> list:
    """Load pre-scanned repo config from demo_repos.yaml."""
    yaml_path = os.path.join(os.path.dirname(__file__), "demo_repos.yaml")
    if not os.path.isfile(yaml_path):
        return []
    with open(yaml_path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("repos", [])


# ---------------------------------------------------------------------------
# GET /demo/repos -- list pre-scanned repositories with their latest scores
# DEPRECATED: Frontend now reads from static catalog JSON files (DemoCatalog).
#             This endpoint remains for backward compatibility.
# ---------------------------------------------------------------------------


@router.get("/repos")
def list_demo_repos():
    """List pre-scanned repositories with their latest scores per framework."""
    repos = _load_demo_repos()
    result = []

    from comply.store import list_scans as list_stored_scans

    for repo in repos:
        repo_url = repo.get("url", "")
        frameworks = repo.get("frameworks", [])
        scans_by_fw = {}

        for fw in frameworks:
            # Find latest scan for this repo+framework
            scans = list_stored_scans(repo=None, framework=fw, limit=50)
            for s in scans:
                # Match by repo_url or repo_path containing the slug
                if repo_url and (s.get("repo_url", "") == repo_url or
                                 repo.get("slug", "") in s.get("repo_path", "")):
                    scans_by_fw[fw] = {
                        "scan_id": s.get("id", ""),
                        "score": s.get("score", 0),
                        "scan_depth": s.get("scan_depth", ""),
                        "created_at": s.get("created_at", ""),
                    }
                    break

        result.append({
            "slug": repo.get("slug", ""),
            "name": repo.get("name", ""),
            "url": repo_url,
            "frameworks": frameworks,
            "scans": scans_by_fw,
            "has_results": len(scans_by_fw) > 0,
        })

    return result


# ---------------------------------------------------------------------------
# GET /demo/prescan -- get pre-scanned results for a repo+framework
# DEPRECATED: Frontend now reads from static catalog JSON files (DemoCatalog).
#             This endpoint remains for backward compatibility.
# ---------------------------------------------------------------------------


@router.get("/prescan")
def get_prescan(repo: str, framework: str = "eu-ai-act"):
    """Return full pre-scanned report for a repo slug + framework."""
    repos = _load_demo_repos()
    target_repo = None
    for r in repos:
        if r.get("slug") == repo:
            target_repo = r
            break

    if target_repo is None:
        raise HTTPException(404, f"Unknown repo: {repo}")

    if framework not in target_repo.get("frameworks", []):
        raise HTTPException(400, f"Framework '{framework}' not pre-scanned for {repo}")

    # Find the scan in history
    from comply.store import list_scans as list_stored_scans, get_scan as get_stored_scan

    scans = list_stored_scans(framework=framework, limit=50)
    for s in scans:
        repo_url = target_repo.get("url", "")
        slug = target_repo.get("slug", "")
        if repo_url and (s.get("repo_url", "") == repo_url or slug in s.get("repo_path", "")):
            full = get_stored_scan(s["id"])
            if full and full.get("report"):
                return full["report"]

    raise HTTPException(404, f"No pre-scanned results found for {repo}/{framework}")


# ---------------------------------------------------------------------------
# GET /demo/prescan-pair -- get both structure + semantic pre-scanned results
# DEPRECATED: Frontend now reads from static catalog JSON files (DemoCatalog).
#             This endpoint remains for backward compatibility.
# ---------------------------------------------------------------------------


@router.get("/prescan-pair")
def get_prescan_pair(repo: str, framework: str = "eu-ai-act"):
    """Return both structure and semantic pre-scanned reports for a repo+framework."""
    repos = _load_demo_repos()
    target_repo = None
    for r in repos:
        if r.get("slug") == repo:
            target_repo = r
            break

    if target_repo is None:
        raise HTTPException(404, f"Unknown repo: {repo}")

    if framework not in target_repo.get("frameworks", []):
        raise HTTPException(400, f"Framework '{framework}' not pre-scanned for {repo}")

    from comply.store import list_scans as list_stored_scans, get_scan as get_stored_scan

    scans = list_stored_scans(framework=framework, limit=50)
    repo_url = target_repo.get("url", "")
    slug = target_repo.get("slug", "")

    structure_report = None
    semantic_report = None

    for s in scans:
        if not (repo_url and (s.get("repo_url", "") == repo_url or slug in s.get("repo_path", ""))):
            continue
        depth = s.get("scan_depth", "")
        if depth == "structure" and structure_report is None:
            full = get_stored_scan(s["id"])
            if full and full.get("report"):
                structure_report = full["report"]
        elif depth == "semantic" and semantic_report is None:
            full = get_stored_scan(s["id"])
            if full and full.get("report"):
                semantic_report = full["report"]
        if structure_report and semantic_report:
            break

    if not structure_report and not semantic_report:
        raise HTTPException(404, f"No pre-scanned results found for {repo}/{framework}")

    return {"structure": structure_report, "semantic": semantic_report}


# ---------------------------------------------------------------------------
# POST /demo/cost-scan -- structure-only scan + cost estimate (no LLM)
# ---------------------------------------------------------------------------


class CostScanRequest(BaseModel):
    url: str
    framework: str = "eu-ai-act"
    baseline_id: Optional[str] = None


@router.post("/cost-scan")
@(_limiter.limit(_RATE_LIMIT) if _limiter else (lambda f: f))
def cost_scan(req: CostScanRequest, request: Request):
    """Run a structure-only scan and return findings + estimated semantic cost.

    Rate limited: 20/hour anonymous, 120/hour for invite holders.
    Zero LLM calls -- uses structure depth only.
    """
    # Validate URL
    err = validate_demo_url(req.url)
    if err:
        raise HTTPException(400, err)

    # Validate framework
    fw_err = validate_framework(req.framework)
    if fw_err:
        raise HTTPException(400, fw_err)

    # Run structure-only scan (no LLM, no API key needed)
    from comply.scanner import run_comply_scan

    try:
        report = run_comply_scan(
            target=req.url,
            framework=req.framework,
            scan_depth="structure",
            llm_api_key=None,
            max_files=500,
            use_cache=True,
            baseline_id=req.baseline_id,
        )
    except RuntimeError as exc:
        raise HTTPException(400, f"Scan failed: {exc}")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))

    # Strip internal fields
    clean = {k: v for k, v in report.items() if not k.startswith("_")}

    # Estimate cost for semantic scan
    cost_estimate = _estimate_semantic_cost(report)
    clean["cost_estimate"] = cost_estimate

    # Tag scan with visitor_id for persistence (metadata only, no plaintext report)
    visitor_id = request.headers.get("X-Visitor-Id", "")
    try:
        from comply.store import increment_demo_counter, save_scan_metadata
        score = report.get("summary", {}).get("score", 0)
        increment_demo_counter("scans_total")
        increment_demo_counter(f"fw_{req.framework}")
        increment_demo_counter("score_sum", score)
        # Persist metadata only; client encrypts and pushes report separately
        save_scan_metadata(report, visitor_id=visitor_id)
    except Exception as exc:
        log.debug("Counter/save failed: %s", exc)

    return clean


def _estimate_semantic_cost(report: dict) -> dict:
    """Estimate the cost of running a full semantic scan based on structure results."""
    summary = report.get("summary", {})
    total_controls = summary.get("total", 0)
    files_scanned = report.get("model", {}).get("filesScanned", 0)

    # Rough cost model: ~$0.002 per control for semantic evaluation
    # Plus ~$0.001 per file for content analysis
    semantic_cost = total_controls * 0.002 + files_scanned * 0.001
    content_cost = files_scanned * 0.0005

    return {
        "structure_cost_usd": 0.0,
        "content_cost_usd": round(content_cost, 4),
        "semantic_cost_usd": round(semantic_cost, 4),
        "model_options": [
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "estimated_cost_usd": round(semantic_cost, 4),
            },
            {
                "provider": "openai",
                "model": "gpt-4o",
                "estimated_cost_usd": round(semantic_cost * 0.8, 4),
            },
        ],
        "controls_to_evaluate": total_controls,
        "files_to_analyze": files_scanned,
    }


# ---------------------------------------------------------------------------
# GET /demo/config -- demo mode status (for frontend)
# ---------------------------------------------------------------------------


@router.get("/config")
def demo_config():
    """Return demo mode configuration for the frontend."""
    llm_key_set = bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GROK_API_KEY")
    )
    return {
        "demo_mode": is_demo_mode(),
        "allowed_frameworks": sorted(ALLOWED_FRAMEWORKS),
        "repos": _load_demo_repos(),
        "llm_api_key_set": llm_key_set,
    }


# ---------------------------------------------------------------------------
# DELETE /demo/scan/{scan_id} -- delete visitor scan from server after saving locally
# ---------------------------------------------------------------------------


@router.delete("/scan/{scan_id}")
def delete_visitor_scan(scan_id: str, request: Request):
    """Delete a specific visitor scan (checks visitor_id ownership)."""
    from comply.store import get_scan, delete_scan
    visitor_id = request.headers.get("X-Visitor-Id", "")
    scan = get_scan(scan_id)
    if not scan:
        return {"ok": False, "message": "Scan not found"}
    # Only allow deletion if visitor_id matches (or scan has no visitor_id)
    scan_vid = scan.get("visitor_id", "")
    if scan_vid and visitor_id and scan_vid != visitor_id:
        raise HTTPException(403, "Not your scan")
    deleted = delete_scan(scan_id)
    return {"ok": deleted}


# ---------------------------------------------------------------------------
# GET /demo/my-scans -- list visitor's persisted scans
# ---------------------------------------------------------------------------


@router.get("/my-scans")
def list_my_scans(request: Request):
    """List scans belonging to this visitor (summary, no full reports)."""
    visitor_id = request.headers.get("X-Visitor-Id", "")
    if not visitor_id:
        return []
    from comply.store import list_visitor_scans
    rows = list_visitor_scans(visitor_id)
    return [
        {
            "id": r["id"],
            "url": r.get("repo_url", ""),
            "framework": r.get("framework", ""),
            "score": r.get("score", 0),
            "depth": r.get("scan_depth", ""),
            "timestamp": r.get("created_at", ""),
            "source": "user",
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /demo/my-scans/{scan_id} -- full scan with report for cache miss
# ---------------------------------------------------------------------------


@router.get("/my-scans/{scan_id}")
def get_my_scan(scan_id: str, request: Request):
    """Return full scan report for a specific visitor scan.

    If the report is encrypted, returns { encrypted: true, iv, ciphertext }
    so the client can decrypt locally.
    """
    visitor_id = request.headers.get("X-Visitor-Id", "")
    from comply.store import get_scan
    scan = get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    scan_vid = scan.get("visitor_id", "")
    if scan_vid and visitor_id and scan_vid != visitor_id:
        raise HTTPException(403, "Not your scan")
    if scan.get("encrypted"):
        return {"encrypted": True, **scan.get("report", {})}
    return scan.get("report", {})


# ---------------------------------------------------------------------------
# PUT /demo/my-scans/{scan_id}/encrypted -- store client-encrypted report
# ---------------------------------------------------------------------------


class EncryptedScanPayload(BaseModel):
    iv: str
    ciphertext: str
    url: str = ""
    framework: str = ""
    score: float = 0
    depth: str = "structure"
    timestamp: str = ""


@router.put("/my-scans/{scan_id}/encrypted")
def put_encrypted_scan(scan_id: str, payload: EncryptedScanPayload, request: Request):
    """Store a client-encrypted scan report.

    The server cannot read the report; it stores the opaque {iv, ciphertext} blob.
    """
    visitor_id = request.headers.get("X-Visitor-Id", "")
    if not visitor_id:
        raise HTTPException(400, "X-Visitor-Id header required")

    from comply.store import save_encrypted_scan
    ok = save_encrypted_scan(
        scan_id=scan_id,
        visitor_id=visitor_id,
        iv=payload.iv,
        ciphertext=payload.ciphertext,
        metadata={
            "url": payload.url,
            "framework": payload.framework,
            "score": payload.score,
            "depth": payload.depth,
            "timestamp": payload.timestamp,
        },
    )
    if not ok:
        raise HTTPException(403, "Not your scan")
    return {"ok": True}


# ---------------------------------------------------------------------------
# DELETE /demo/my-scans -- delete all visitor scans
# ---------------------------------------------------------------------------


@router.delete("/my-scans")
def delete_my_scans(request: Request):
    """Delete all scans for this visitor."""
    visitor_id = request.headers.get("X-Visitor-Id", "")
    if not visitor_id:
        return {"ok": False, "deleted": 0}
    from comply.store import delete_visitor_scans
    count = delete_visitor_scans(visitor_id)
    return {"ok": True, "deleted": count}


# ---------------------------------------------------------------------------
# GET /demo/stats -- anonymous usage counters (no identifying info)
# ---------------------------------------------------------------------------


@router.get("/stats")
def demo_stats():
    """Return anonymous aggregate usage counters."""
    from comply.store import get_demo_counters
    counters = get_demo_counters()
    total = counters.get("scans_total", 0)
    score_sum = counters.get("score_sum", 0)
    return {
        "scans_total": int(total),
        "avg_score": round(score_sum / max(total, 1), 1),
        "frameworks": {
            k.replace("fw_", ""): int(v)
            for k, v in counters.items()
            if k.startswith("fw_")
        },
    }
