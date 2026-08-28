"""Comply scan lifecycle, history, diff, cache, baseline, regression, progress, adapters, CI/CD."""
from __future__ import annotations

import os
import tempfile
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from comply.scan_state import create_scan, get_scan, update_scan, list_scans

router = APIRouter()


def _get_scan_or_stored(scan_id: str):
    """Look up a scan in in-memory state first, then fall back to persistent store."""
    scan = get_scan(scan_id)
    if scan is not None:
        return scan
    # Fall back to SQLite store for historical scans
    from comply.store import get_scan as get_stored_scan
    row = get_stored_scan(scan_id)
    if row is None:
        return None

    class _StoredScan:
        pass

    s = _StoredScan()
    s.id = row["id"]
    s.url = row.get("repo_url") or row.get("repo_path", "")
    s.framework = row.get("framework", "")
    s.status = row.get("status", "complete")
    s.report = row.get("report")  # store._row_to_dict already parses JSON
    s.error = None
    s.created_at = row.get("created_at", "")
    s.completed_at = row.get("completed_at", "")
    s.progress_step = ""
    s.progress_detail = ""
    return s


class ScanRequest(BaseModel):
    url: str
    framework: str = "eu-ai-act"  # comma-separated for multi-framework
    depth: str = "content"
    llm_key: Optional[str] = None
    llm_provider: Optional[str] = None
    max_files: int = 500
    no_cache: bool = False
    jurisdiction: Optional[str] = None  # expands to framework list via mapping
    baseline_id: Optional[str] = None   # for incremental scanning


@router.post("/scan")
def start_scan(req: ScanRequest):
    """Start a compliance scan in a background thread."""
    # Resolve jurisdiction to framework list
    if req.jurisdiction:
        from comply.mapping import resolve_frameworks
        fw_list = resolve_frameworks(req.jurisdiction)
        req.framework = ",".join(fw_list)

    output_dir = tempfile.mkdtemp(prefix="comply-web-")
    scan = create_scan(
        url=req.url,
        framework=req.framework,
        depth=req.depth,
        output_dir=output_dir,
    )
    update_scan(scan.id, status="pending")

    t = threading.Thread(
        target=_run_scan_thread,
        args=(scan.id, req),
        daemon=True,
    )
    t.start()

    # Explicit signal: key is in-flight only, never persisted
    return Response(
        content='{"scanId": "' + scan.id + '", "status": "pending"}',
        media_type="application/json",
        headers={"X-Key-Retention": "none", "X-Key-Policy": "forwarded-to-provider-only"},
    )


def _run_scan_thread(scan_id: str, req: ScanRequest):
    """Execute the scan pipeline in a background thread."""
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
        frameworks = [fw.strip() for fw in req.framework.split(",") if fw.strip()]
        if len(frameworks) == 1:
            from comply.scanner import run_comply_scan
            report = run_comply_scan(
                target=req.url,
                framework=frameworks[0],
                scan_depth=req.depth,
                output_dir=scan.output_dir,
                llm_api_key=req.llm_key,
                llm_provider=req.llm_provider,
                max_files=req.max_files,
                on_progress=on_progress,
                use_cache=not req.no_cache,
                baseline_id=req.baseline_id,
            )
            result = report
        else:
            from comply.scanner import run_comply_scan_multi
            reports = run_comply_scan_multi(
                target=req.url,
                frameworks=frameworks,
                scan_depth=req.depth,
                output_dir=scan.output_dir,
                llm_api_key=req.llm_key,
                llm_provider=req.llm_provider,
                max_files=req.max_files,
                on_progress=on_progress,
                use_cache=not req.no_cache,
                baseline_id=req.baseline_id,
            )
            # Store all reports: main report is first, extras under "_multiReports"
            result = reports[0]
            if len(reports) > 1:
                result["_multiReports"] = reports[1:]

        from datetime import datetime, timezone
        update_scan(
            scan_id,
            status="complete",
            report=result,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        update_scan(scan_id, status="error", error=str(exc))


@router.get("/scan/{scan_id}")
def poll_scan(scan_id: str):
    """Poll scan status."""
    scan = _get_scan_or_stored(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return {
        "id": scan.id,
        "url": scan.url,
        "framework": scan.framework,
        "status": scan.status,
        "progress_step": scan.progress_step,
        "progress_detail": scan.progress_detail,
        "error": scan.error,
        "created_at": scan.created_at,
        "completed_at": scan.completed_at,
    }


@router.get("/scan/{scan_id}/report")
def get_report(scan_id: str):
    """Get the compliance report JSON."""
    scan = _get_scan_or_stored(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    if scan.status != "complete":
        raise HTTPException(400, f"Scan is {scan.status}, not complete")
    if scan.report is None:
        raise HTTPException(500, "Report not available")

    # Strip internal fields
    clean = {k: v for k, v in scan.report.items() if not k.startswith("_")}
    return clean


@router.get("/scan/{scan_id}/download")
def download_report(scan_id: str, fmt: str = "json"):
    """Download report in requested format (json, docx, zip)."""
    scan = _get_scan_or_stored(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    if scan.status != "complete":
        raise HTTPException(400, f"Scan is {scan.status}, not complete")

    if fmt == "json":
        # Try file on disk first (in-flight scans), fall back to report dict
        output_dir = getattr(scan, "output_dir", None)
        if output_dir:
            json_path = os.path.join(output_dir, "compliance_report.json")
            if os.path.isfile(json_path):
                return FileResponse(json_path, filename="compliance_report.json",
                                    media_type="application/json")
        if scan.report:
            import json as json_mod
            return Response(
                content=json_mod.dumps(scan.report, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=compliance_report.json"},
            )
        raise HTTPException(404, "JSON report not found")

    elif fmt == "docx":
        from comply.scanner import generate_docx_report
        docx_bytes = generate_docx_report(scan.framework, report=scan.report)
        if docx_bytes is None:
            raise HTTPException(501, "DOCX export requires python-docx (pip install bespoketracker-comply[docx])")
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=compliance_report.docx"},
        )

    elif fmt == "zip":
        from comply.scanner import generate_audit_bundle
        bundle = generate_audit_bundle(scan.framework)
        if bundle is None:
            raise HTTPException(500, "Audit bundle generation failed")
        return Response(
            content=bundle,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=audit_bundle.zip"},
        )

    elif fmt == "sarif":
        from comply.formats import to_sarif
        import json as json_mod
        sarif = to_sarif(scan.report)
        return Response(
            content=json_mod.dumps(sarif, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=comply.sarif"},
        )

    elif fmt == "junit":
        from comply.formats import to_junit
        xml_str = to_junit(scan.report)
        return Response(
            content=xml_str,
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=comply.xml"},
        )

    elif fmt == "markdown":
        from comply.formats import to_markdown
        md = to_markdown(scan.report)
        return Response(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=comply.md"},
        )

    raise HTTPException(400, f"Unknown format: {fmt}. Supported: json, docx, zip, sarif, junit, markdown")


@router.get("/scans")
def get_scans():
    """List all scans."""
    return list_scans()


@router.get("/frameworks")
def get_frameworks():
    """List supported compliance frameworks."""
    from comply.scanner import list_frameworks
    return list_frameworks()


@router.get("/config")
def get_config_info():
    """Return current LLM configuration status (no secrets)."""
    from comply.config import load_config
    cfg = load_config()
    provider = cfg.get("llm_provider", "")
    model = cfg.get("llm_model", "")
    key = cfg.get("llm_api_key", "")
    return {
        "llm_provider": provider or "",
        "llm_model": model or "",
        "llm_api_key_set": bool(key),
        "llm_api_key_hint": (key[:4] + "..." + key[-4:]) if key and len(key) > 8 else ("set" if key else ""),
    }


class ConfigUpdate(BaseModel):
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None


@router.put("/config")
def update_config(req: ConfigUpdate):
    """Update LLM configuration (writes to ~/.comply/config.yaml)."""
    from comply.config import load_config, save_config
    cfg = load_config()
    changed = []
    if req.llm_provider is not None:
        cfg["llm_provider"] = req.llm_provider
        changed.append("llm_provider")
    if req.llm_model is not None:
        cfg["llm_model"] = req.llm_model
        changed.append("llm_model")
    if req.llm_api_key is not None:
        cfg["llm_api_key"] = req.llm_api_key
        changed.append("llm_api_key")
    if changed:
        save_config(cfg)
    return {"updated": changed}


@router.get("/capabilities")
def get_capabilities():
    """Return app capabilities for the frontend — single source of truth for mode detection."""
    from comply.config import load_config
    from comply.demo_security import is_demo_mode
    key = load_config().get("llm_api_key", "")
    return {
        "demo_mode": is_demo_mode(),
        "has_api_key": bool(key),
        "encryption": is_demo_mode(),       # client-side encryption in demo mode
        "funded_scans": is_demo_mode(),      # funded scans only in demo mode
        "catalog": is_demo_mode(),           # pre-scanned catalog only in demo mode
    }


@router.get("/history")
def get_history(repo: Optional[str] = None, framework: Optional[str] = None, limit: int = 20):
    """List past scans from persistent store."""
    from comply.store import list_scans as list_stored_scans
    scans = list_stored_scans(repo=repo, framework=framework, limit=limit)
    # Return without the full report blob (too large for listing)
    return [
        {k: v for k, v in s.items() if k != "report"}
        for s in scans
    ]


@router.get("/history/{scan_id}")
def get_history_scan(scan_id: str):
    """Get a single scan from persistent store (includes full report)."""
    from comply.store import get_scan as get_stored_scan
    scan = get_stored_scan(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found in history")
    return scan


@router.get("/scan/preview-changes/{baseline_id}")
def preview_changes(baseline_id: str, url: str):
    """Preview impact of changes since a baseline scan without running a full scan.

    Returns which files changed and which controls would be re-evaluated.
    Fast: no evidence evaluation, no LLM calls.
    """
    import tempfile
    from comply.store import get_scan as get_stored_scan

    baseline = get_stored_scan(baseline_id)
    if baseline is None:
        raise HTTPException(404, "Baseline scan not found")

    baseline_sha = baseline.get("commit_sha", "")
    if not baseline_sha:
        raise HTTPException(400, "Baseline scan has no commit SHA")

    baseline_report = baseline.get("report", {})
    if not baseline_report.get("articles"):
        raise HTTPException(400, "Baseline scan has no report data")

    # Clone/resolve the repo to get current state
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="comply-preview-")
        from comply.scanner import clone_or_resolve
        repo_path = clone_or_resolve(url, tmp_dir)

        from comply.incremental import detect_changes, preview_impact
        from comply.remediation import _STRATEGY_MAP

        changes = detect_changes(repo_path, baseline_sha)
        if changes is None:
            raise HTTPException(400, "Unable to detect changes (git diff failed)")

        preview = preview_impact(changes, _STRATEGY_MAP, baseline_report)
        return preview

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Preview failed: {exc}")
    finally:
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/diff")
def get_diff(scan1: str, scan2: str):
    """Compute the diff between two stored scans."""
    from comply.store import get_scan as get_stored_scan

    s1 = get_stored_scan(scan1)
    if s1 is None:
        raise HTTPException(404, f"Scan '{scan1}' not found")
    s2 = get_stored_scan(scan2)
    if s2 is None:
        raise HTTPException(404, f"Scan '{scan2}' not found")

    from comply.__main__ import _compute_diff
    return _compute_diff(s1["report"], s2["report"])


@router.get("/cache/stats")
def cache_stats():
    """Return scan model cache stats."""
    from comply.cache import get_cache_stats
    return get_cache_stats()


@router.delete("/cache")
def clear_cache_route():
    """Clear all cached scan models."""
    from comply.cache import clear_cache
    count = clear_cache()
    return {"cleared": count}


@router.delete("/scan/{scan_id}")
def delete_scan_route(scan_id: str):
    """Delete a specific scan by ID."""
    from comply.store import delete_scan
    ok = delete_scan(scan_id)
    if not ok:
        raise HTTPException(404, "Scan not found")
    return {"ok": True, "scanId": scan_id}


@router.delete("/history")
def clear_history_route():
    """Delete all scan history."""
    from comply.store import _get_conn
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM scans")
    conn.commit()
    return {"cleared": cursor.rowcount}


@router.post("/baseline/{scan_id}")
def set_baseline_route(scan_id: str):
    """Set a scan as the baseline for its repo+framework."""
    from comply.store import set_baseline
    ok = set_baseline(scan_id)
    if not ok:
        raise HTTPException(404, "Scan not found")
    return {"ok": True, "scanId": scan_id}


@router.get("/baseline")
def get_baseline_route(repo: str, framework: str = "eu-ai-act"):
    """Get the current baseline scan for a repo+framework."""
    from comply.store import get_baseline
    bl = get_baseline(repo, framework)
    if bl is None:
        raise HTTPException(404, "No baseline set")
    return {k: v for k, v in bl.items() if k != "report"}


@router.get("/scan/{scan_id}/regression")
def get_regression(scan_id: str):
    """Compare a scan against its baseline to detect regressions."""
    from comply.store import get_scan as get_stored_scan
    scan = get_stored_scan(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")

    from comply.regression import detect_regression
    result = detect_regression(
        scan["repo_path"],
        scan["framework"],
        scan["report"],
    )
    if result is None:
        return {"regressionDetected": False, "message": "No baseline set"}
    return result


@router.get("/scan/{scan_id}/progress")
def get_scan_progress(scan_id: str):
    """Get scan progress (cleaner polling endpoint)."""
    scan = _get_scan_or_stored(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return {
        "id": scan.id,
        "status": scan.status,
        "step": scan.progress_step,
        "detail": scan.progress_detail,
        "error": scan.error,
    }


# -- Adapter endpoints --------------------------------------------------------

class IngestRequest(BaseModel):
    since: Optional[str] = None
    until: Optional[str] = None
    limit: int = 1000


@router.get("/adapters")
def get_adapters():
    """List all registered audit log adapters and their status."""
    from comply.adapters.registry import list_adapters
    return list_adapters()


@router.post("/adapters/{name}/test")
def test_adapter(name: str):
    """Test connectivity for a specific adapter."""
    from comply.adapters.registry import get_adapter, configure_adapter, _REGISTRY
    adapter = get_adapter(name)
    if adapter is None:
        if name not in _REGISTRY:
            raise HTTPException(404, f"Unknown adapter: {name}")
        raise HTTPException(400, f"Adapter '{name}' is registered but not configured")
    ok = adapter.test_connection()
    return {"adapter": name, "connected": ok}


@router.post("/adapters/{name}/ingest")
def ingest_adapter_records(name: str, req: IngestRequest):
    """Fetch records from an adapter and store them."""
    from comply.adapters.registry import get_adapter, _REGISTRY
    adapter = get_adapter(name)
    if adapter is None:
        if name not in _REGISTRY:
            raise HTTPException(404, f"Unknown adapter: {name}")
        raise HTTPException(400, f"Adapter '{name}' is not configured")

    records = adapter.fetch_records(since=req.since, until=req.until, limit=req.limit)
    from comply.store import ingest_audit_records
    count = ingest_audit_records(records)
    return {"adapter": name, "fetched": len(records), "ingested": count}


@router.get("/adapters/{name}/records")
def get_adapter_records(name: str, since: Optional[str] = None, until: Optional[str] = None, limit: int = 100):
    """Query stored audit records for an adapter."""
    from comply.store import query_audit_records
    records = query_audit_records(adapter=name, since=since, until=until, limit=limit)
    return records


# -- CI/CD endpoints ----------------------------------------------------------


@router.get("/cicd/summary")
def get_cicd_summary():
    """Get aggregate CI/CD statistics from ingested records."""
    from comply.store import get_cicd_summary as _get_cicd_summary
    return _get_cicd_summary()


@router.get("/cicd/records")
def get_cicd_records(
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
    cicd_type: Optional[str] = None,
):
    """Query CI/CD records with optional filters."""
    from comply.store import query_cicd_records
    return query_cicd_records(since=since, until=until, limit=limit, cicd_type=cicd_type)


class CicdIngestRequest(BaseModel):
    adapter: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    limit: int = 1000


@router.post("/cicd/ingest")
def ingest_cicd_records(req: CicdIngestRequest):
    """Ingest records from CI/CD adapters (github_actions, gitlab_ci)."""
    from comply.adapters.registry import get_adapter, auto_configure_from_config
    from comply.store import ingest_audit_records, CICD_ADAPTER_NAMES

    auto_configure_from_config()

    adapter_names = [req.adapter] if req.adapter else list(CICD_ADAPTER_NAMES)
    results = []

    for name in adapter_names:
        adapter = get_adapter(name)
        if adapter is None:
            results.append({"adapter": name, "status": "not_configured", "fetched": 0, "ingested": 0})
            continue
        try:
            records = adapter.fetch_records(since=req.since, until=req.until, limit=req.limit)
            count = ingest_audit_records(records)
            results.append({"adapter": name, "status": "ok", "fetched": len(records), "ingested": count})
        except Exception as exc:
            results.append({"adapter": name, "status": "error", "error": str(exc), "fetched": 0, "ingested": 0})

    total_fetched = sum(r.get("fetched", 0) for r in results)
    total_ingested = sum(r.get("ingested", 0) for r in results)
    return {"adapters": results, "total_fetched": total_fetched, "total_ingested": total_ingested}


# -- Programs (portfolio grouping) -------------------------------------------


class ProgramRequest(BaseModel):
    name: str
    description: str = ""
    repos: list = []         # list of URLs or {url, label} dicts
    frameworks: list = []    # list of framework IDs


@router.get("/programs")
def api_list_programs():
    from comply.store import list_programs
    return list_programs()


@router.post("/programs")
def api_create_program(req: ProgramRequest):
    from comply.store import save_program
    pid = save_program(req.dict())
    return {"id": pid}


@router.get("/programs/{program_id}")
def api_get_program(program_id: str):
    from comply.store import get_program
    prog = get_program(program_id)
    if not prog:
        raise HTTPException(404, "Program not found")
    return prog


@router.put("/programs/{program_id}")
def api_update_program(program_id: str, req: ProgramRequest):
    from comply.store import get_program, save_program
    existing = get_program(program_id)
    if not existing:
        raise HTTPException(404, "Program not found")
    data = req.dict()
    data["id"] = program_id
    data["created_at"] = existing["created_at"]
    save_program(data)
    return {"ok": True}


@router.delete("/programs/{program_id}")
def api_delete_program(program_id: str):
    from comply.store import delete_program
    if not delete_program(program_id):
        raise HTTPException(404, "Program not found")
    return {"ok": True}


@router.get("/programs/{program_id}/posture")
def api_program_posture(program_id: str):
    from comply.store import get_program_posture
    return get_program_posture(program_id)
