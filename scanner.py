"""Core scan orchestration — the critical pipeline for Comply.

run_comply_scan() drives the full sequence:
  ephemeral Kuzu DB → codebase scan → model build → compliance evaluation → report

run_comply_scan_multi() scans once and evaluates against multiple frameworks.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
import yaml
from datetime import datetime, timezone
from typing import List, Optional

from comply.git_clone import clone_or_resolve, is_git_url

log = logging.getLogger(__name__)


def _is_monorepo_available() -> bool:
    """Check if extended graph pipeline is available. Always False in OSS."""
    return False


def run_comply_scan(
    target: str,
    framework: str = "eu-ai-act",
    scan_depth: str = "content",
    output_dir: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_provider: Optional[str] = None,
    max_files: int = 500,
    on_progress: Optional[callable] = None,
    use_cache: bool = True,
    baseline_id: Optional[str] = None,
) -> dict:
    """Run a full compliance scan and return the report dict.

    Args:
        target: Local path or git URL to scan.
        framework: Compliance framework ID (e.g. "eu-ai-act").
        scan_depth: "structure", "content", or "semantic".
        output_dir: Where to write reports. If None, uses a temp dir.
        llm_api_key: Optional API key for LLM-powered semantic analysis.
        llm_provider: Optional provider name (anthropic/openai/gemini).
        max_files: Max files to scan (default 500).
        on_progress: Optional callback(step, detail) for progress updates.
        use_cache: Whether to use scan model cache (default True).
        baseline_id: Optional scan ID for incremental scanning.

    Returns:
        Report dict with compliance status, per-control evidence, and metadata.
    """
    results = run_comply_scan_multi(
        target=target,
        frameworks=[framework],
        scan_depth=scan_depth,
        output_dir=output_dir,
        llm_api_key=llm_api_key,
        llm_provider=llm_provider,
        max_files=max_files,
        on_progress=on_progress,
        use_cache=use_cache,
        baseline_id=baseline_id,
    )
    return results[0]


def run_comply_scan_multi(
    target: str,
    frameworks: Optional[List[str]] = None,
    scan_depth: str = "content",
    output_dir: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_provider: Optional[str] = None,
    max_files: int = 500,
    on_progress: Optional[callable] = None,
    use_cache: bool = True,
    baseline_id: Optional[str] = None,
) -> List[dict]:
    """Scan once, evaluate against multiple frameworks. Returns list of report dicts."""
    if frameworks is None:
        frameworks = ["eu-ai-act"]

    # ── Tier enforcement ─────────────────────────────────────────
    from comply.tiers import (
        check_framework_allowed, check_depth_allowed, get_tier,
        check_multi_framework_allowed,
    )

    for fw in frameworks:
        if not check_framework_allowed(fw):
            tier = get_tier()
            from comply.tiers import TIERS
            allowed = TIERS.get(tier, {}).get("frameworks", [])
            raise PermissionError(
                f"Framework '{fw}' is not available on the {tier} tier. "
                f"Allowed: {', '.join(allowed)}. Upgrade to Pro or Enterprise for more frameworks."
            )

    if not check_multi_framework_allowed(len(frameworks)):
        tier = get_tier()
        raise PermissionError(
            f"Multi-framework scan ({len(frameworks)} frameworks) is not available on the {tier} tier. "
            f"Upgrade for multi-framework support."
        )

    if not check_depth_allowed(scan_depth):
        tier = get_tier()
        from comply.tiers import TIERS
        max_depth = TIERS.get(tier, {}).get("max_depth", "content")
        raise PermissionError(
            f"Scan depth '{scan_depth}' is not available on the {tier} tier "
            f"(max: {max_depth}). Upgrade to Pro or Enterprise for semantic analysis."
        )

    tmp_root = None
    original_env = {}

    def _progress(step: str, detail: str = ""):
        if on_progress:
            on_progress(step, detail)
        log.info("[multi] %s %s", step, detail)

    try:
        # ── 1. Set up work directory ──────────────────────────────────
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            work_dir = output_dir
        else:
            tmp_root = tempfile.mkdtemp(prefix="comply-")
            work_dir = tmp_root

        # ── 2. Resolve target ─────────────────────────────────────────
        _progress("resolving", target)
        repo_path = clone_or_resolve(target, work_dir)
        _progress("resolved", repo_path)

        # ── 3. Configure LLM ─────────────────────────────────────────
        # Fall back to the stored config when no key was passed in. Until this
        # existed, `config set llm_api_key` had WRITERS and no READER: the CLI
        # accepted the key, the server accepted it, the startup banner told you
        # to set it, and nothing ever read it back out. Resolved here, at the
        # single entry point, rather than at each of the four call sites.
        if not llm_api_key or not llm_provider:
            from comply.config import load_config
            stored = load_config()
            llm_api_key = llm_api_key or stored.get("llm_api_key") or ""
            llm_provider = llm_provider or stored.get("llm_provider") or ""

        if llm_api_key:
            provider_name = llm_provider or "anthropic"
            _configure_llm(provider_name, llm_api_key, original_env)

        if scan_depth == "semantic" and not llm_api_key:
            log.warning("No LLM API key provided; falling back to content depth")
            scan_depth = "content"

        # ── 4-6. Scan and build model (with cache) ───────────────────
        commit_sha = _get_commit_sha(repo_path)
        model_result = _scan_and_build_model(
            repo_path=repo_path,
            scan_depth=scan_depth,
            max_files=max_files,
            work_dir=work_dir,
            commit_sha=commit_sha,
            use_cache=use_cache,
            on_progress=_progress,
        )

        # ── 6b. Incremental: detect changes and map impact ─────────
        incremental_ctx = None
        if baseline_id:
            try:
                from comply.incremental import detect_changes, map_impact
                from comply.store import get_scan
                from comply.remediation import _STRATEGY_MAP

                baseline_scan = get_scan(baseline_id)
                if baseline_scan and baseline_scan.get("commit_sha"):
                    baseline_sha = baseline_scan["commit_sha"]
                    changes = detect_changes(repo_path, baseline_sha)
                    if changes and changes["total_changed"] > 0:
                        impact = map_impact(changes, _STRATEGY_MAP)
                        incremental_ctx = {
                            "baseline_scan": baseline_scan,
                            "changes": changes,
                            "impact": impact,
                        }
                        _progress("incremental",
                            f"{changes['total_changed']} files changed, "
                            f"{len(impact['affected_fns'])} evidence fns affected, "
                            f"{len(impact['unaffected_fns'])} carried forward")
                    elif changes and changes["total_changed"] == 0:
                        _progress("incremental", "no changes since baseline")
                    else:
                        _progress("incremental", "change detection failed, running full scan")
            except Exception as exc:
                log.debug("Incremental setup failed, running full scan: %s", exc)

        # ── 7-10. Evaluate each framework and generate reports ───────
        reports = []
        for fw in frameworks:
            report = _evaluate_and_report(
                framework=fw,
                model_result=model_result,
                target=target,
                scan_depth=scan_depth,
                repo_path=repo_path,
                commit_sha=commit_sha,
                work_dir=work_dir,
                on_progress=_progress,
                llm_api_key=llm_api_key or "",
                llm_provider=llm_provider or "",
                incremental_ctx=incremental_ctx,
            )
            reports.append(report)

        _progress("complete", f"{len(reports)} framework(s)")
        return reports

    except Exception as exc:
        log.exception("Scan failed: %s", exc)
        raise
    finally:
        _restore_env(original_env)
        if tmp_root and not output_dir:
            with contextlib.suppress(OSError):
                shutil.rmtree(tmp_root, ignore_errors=True)


def _scan_and_build_model(
    repo_path: str,
    scan_depth: str,
    max_files: int,
    work_dir: str,
    commit_sha: str,
    use_cache: bool,
    on_progress: callable,
) -> dict:
    """Scan the codebase and build the product model. Uses cache if available."""
    # Check cache
    if use_cache and commit_sha:
        try:
            from comply.cache import get_cached_project
            cached = get_cached_project(repo_path, scan_depth, commit_sha)
            if cached is not None:
                on_progress("cache_hit", f"sha={commit_sha[:8]}")
                return cached
        except Exception as exc:
            log.warning("Cache lookup failed: %s", exc)

    # Standalone scanner (vendored pure-Python)
    on_progress("scanning", f"depth={scan_depth} (standalone)")
    from comply._vendor.codebase_scanner import scan_codebase as standalone_scan
    codebase_model = standalone_scan(
        repo_path=repo_path,
        scan_depth=scan_depth,
        max_files=max_files,
    )
    # Store the codebase_model for the evaluator
    model_result = {
        "scan": {
            "files_scanned": codebase_model.get("file_count", 0),
            "features_created": codebase_model.get("feature_count", 0),
            "features_updated": 0,
            "edges_created": len(codebase_model.get("relationships", [])),
        },
        "reconciliation": {"matched": [], "code_only": [], "plan_only": [], "coverage": 0},
        "validation": {"score": 0, "findings": {}},
        "_codebase_model": codebase_model,
    }

    # Save to cache
    if use_cache and commit_sha:
        try:
            from comply.cache import save_to_cache
            save_to_cache(repo_path, scan_depth, commit_sha, model_result)
        except Exception as exc:
            log.warning("Cache save failed: %s", exc)

    return model_result


def _evaluate_and_report(
    framework: str,
    model_result: dict,
    target: str,
    scan_depth: str,
    repo_path: str,
    commit_sha: str,
    work_dir: str,
    on_progress: callable,
    llm_api_key: str = "",
    llm_provider: str = "",
    incremental_ctx: Optional[dict] = None,
) -> dict:
    """Evaluate compliance for one framework and produce a report."""
    scan_id = uuid.uuid4().hex[:12]

    on_progress("evaluating", framework)
    # Standalone evaluation using vendored evaluator
    from comply._vendor.compliance_eval import evaluate_compliance as standalone_eval, reset_semantic_counter
    codebase_model = model_result.get("_codebase_model", {})
    use_semantic = scan_depth == "semantic" and bool(llm_api_key)
    if use_semantic:
        reset_semantic_counter()
    compliance_status = standalone_eval(
        framework, codebase_model,
        semantic=use_semantic,
        llm_provider=llm_provider or "anthropic",
        llm_api_key=llm_api_key or "",
        llm_model="",
    )

    on_progress("generating", f"report ({framework})")
    report = _generate_report(
        framework=framework,
        compliance_status=compliance_status,
        model_result=model_result,
        target=target,
        scan_depth=scan_depth,
        scan_id=scan_id,
        repo_path=repo_path,
        commit_sha=commit_sha,
    )

    # M.2: Pass through semantic-to-structure correction log
    if compliance_status.get("corrections"):
        report["corrections"] = compliance_status["corrections"]

    # Three-layer evidence: check for configured adapters
    try:
        from comply.adapters.registry import list_adapters, get_adapter
        from comply.evidence_layers import compute_combined_posture
        from comply.regression import detect_regression

        configured = [a for a in list_adapters() if a.get("configured")]

        # Fetch CI/CD records for Layer 2 enhancement
        cicd_records = None
        try:
            from comply.store import query_cicd_records
            cicd_records = query_cicd_records(limit=500)
        except (ImportError, OSError, RuntimeError) as exc:
            log.debug("CI/CD records unavailable: %s", exc)

        if configured or cicd_records:
            # Fetch audit records from all configured adapters
            all_records = []
            for adapter_info in configured:
                adapter_name = adapter_info.get("name", "")
                adapter = get_adapter(adapter_name)
                if adapter:
                    try:
                        records = adapter.fetch_records(limit=1000)
                        all_records.extend(records)
                    except Exception as exc:
                        log.warning("Adapter %s fetch failed: %s", adapter_name, exc)

            # Regression result for Layer 2
            regression_result = None
            try:
                regression_result = detect_regression(repo_path, framework, report)
            except (ValueError, KeyError, RuntimeError) as exc:
                log.debug("Regression detection skipped: %s", exc)

            if all_records or cicd_records:
                posture = compute_combined_posture(
                    scan_report=report,
                    regression_result=regression_result,
                    audit_records=all_records,
                    framework=framework,
                    cicd_records=cicd_records,
                )
                # Merge layer data into each control
                posture_controls = {}
                for art in posture.get("articles", []):
                    for ctrl in art.get("controls", []):
                        posture_controls[ctrl["controlId"]] = ctrl

                for art in report.get("articles", []):
                    for ctrl in art.get("controls", []):
                        pc = posture_controls.get(ctrl.get("controlId", ""))
                        if pc:
                            ctrl["layers"] = pc.get("layers", {})
                            ctrl["combinedStatus"] = pc.get("combinedStatus", ctrl.get("status", "gap"))

                report["posture"] = {
                    "combinedScore": posture.get("combinedScore", 0),
                    "auditSummary": posture.get("auditSummary", {}),
                    "hasBaseline": posture.get("hasBaseline", False),
                    "regressionDetected": posture.get("regressionDetected", False),
                }
    except Exception as exc:
        log.debug("Three-layer evidence skipped: %s", exc)

    # Incremental merge: carry forward unaffected controls from baseline
    if incremental_ctx and incremental_ctx.get("impact"):
        try:
            from comply.incremental import build_incremental_report
            baseline_report = incremental_ctx["baseline_scan"].get("report", {})
            if baseline_report and baseline_report.get("articles"):
                impact = incremental_ctx["impact"]
                # Add SHA info to impact for metadata
                changes = incremental_ctx.get("changes", {})
                impact["baseline_sha"] = changes.get("baseline_sha", "")
                impact["current_sha"] = changes.get("current_sha", "")
                report = build_incremental_report(baseline_report, report, impact)
                on_progress("incremental_merge",
                    f"{report['incremental']['controls_reevaluated']} re-evaluated, "
                    f"{report['incremental']['controls_carried_forward']} carried forward")
        except Exception as exc:
            log.debug("Incremental merge failed, using full report: %s", exc)

    # Graph-aware remediation (Level 3 -- no LLM cost)
    try:
        from comply.remediation import generate_remediations
        codebase_graph = report.get("model", {}).get("codebaseGraph", {})
        if codebase_graph and codebase_graph.get("files"):
            remediations = generate_remediations(
                report["articles"], codebase_graph, framework,
                summary=report.get("summary"),
            )
            if remediations:
                report["remediations"] = remediations
    except Exception as exc:
        log.debug("Remediation generation skipped: %s", exc)

    # Write report file
    fname = f"compliance_report_{framework}.json" if framework != "eu-ai-act" else "compliance_report.json"
    report_path = os.path.join(work_dir, fname)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    report["_outputDir"] = work_dir
    report["_reportPath"] = report_path

    # Persist to scan history
    try:
        from comply.store import save_scan
        save_scan(report)
    except Exception as exc:
        log.warning("Failed to save scan to history: %s", exc)

    # No platform integration in standalone OSS: the monorepo build fires
    # Coalesce reflexes here, and that dispatch is deliberately absent.

    return report


def _restore_env(original_env: dict):
    """Restore environment variables and config after a scan."""
    for key, val in original_env.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "grok": "grok-3-mini",
}


def _configure_llm(provider_name: str, api_key: str, original_env: dict):
    """Configure the LLM provider so semantic analysis uses the right backend."""
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "grok": "XAI_API_KEY",
    }
    env_var = env_map.get(provider_name, "ANTHROPIC_API_KEY")
    original_env[env_var] = os.environ.get(env_var)
    os.environ[env_var] = api_key



def _get_commit_sha(repo_path: str) -> str:
    """Try to get the current git commit SHA for the repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("Could not read git commit SHA: %s", exc)
    return ""


def _trim_codebase_model(model_result: dict) -> dict:
    """Extract a trimmed codebase model for persistence (no raw content)."""
    cm = model_result.get("_codebase_model", {})
    if not cm:
        return {}
    trimmed_files = []
    for f in cm.get("files", []):
        trimmed_files.append({
            "path": f.get("path", ""),
            "language": f.get("language", ""),
            "size": f.get("size_bytes", 0),
            "classes": f.get("classes", []),
            "functions": f.get("functions", []),
            "imports": f.get("imports", []),
            "has_tests": f.get("has_tests", False),
            "is_config": f.get("is_config", False),
        })
    return {
        "files": trimmed_files,
        "features": cm.get("features", []),
        "relationships": cm.get("relationships", []),
        "dependencies": cm.get("dependencies", []),
        "languageBreakdown": cm.get("language_breakdown", {}),
    }


def _generate_report(
    framework: str,
    compliance_status: dict,
    model_result: dict,
    target: str,
    scan_depth: str,
    scan_id: str,
    repo_path: str,
    commit_sha: str = "",
) -> dict:
    """Assemble the final report dict."""
    summary = compliance_status.get("summary", {})

    return {
        "reportType": "comply_scan",
        "scanId": scan_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "repoPath": repo_path,
        "framework": framework,
        "scanDepth": scan_depth,
        "commitSha": commit_sha,
        "summary": {
            "met": summary.get("met", 0),
            "partial": summary.get("partial", 0),
            "gap": summary.get("gap", 0),
            "total": summary.get("total", 0),
            "score": _compute_score(summary),
        },
        "articles": compliance_status.get("articles", []),
        "model": {
            "filesScanned": model_result.get("scan", {}).get("files_scanned", 0),
            "featuresDiscovered": model_result.get("scan", {}).get("features_created", 0),
            "completenessScore": model_result.get("validation", {}).get("score", 0),
            "codebaseGraph": _trim_codebase_model(model_result),
        },
    }


def _compute_score(summary: dict) -> float:
    """Compute a 0-100 compliance score from met/partial/gap counts."""
    total = summary.get("total", 0)
    if total == 0:
        return 0.0
    met = summary.get("met", 0)
    partial = summary.get("partial", 0)
    return round((met * 1.0 + partial * 0.5) / total * 100, 1)


def list_frameworks() -> list:
    """Return metadata for all supported frameworks."""
    try:
        from comply._vendor.framework_loader import get_framework_details
        return get_framework_details()
    except Exception:
        return [{"id": "eu-ai-act", "name": "EU AI Act", "controls": "~30"}]


def generate_audit_bundle(framework: str = "eu-ai-act") -> Optional[bytes]:
    """Generate a ZIP audit bundle. Placeholder for future standalone implementation."""
    log.info("Audit bundle generation not available in standalone mode")
    return None


def generate_docx_report(framework: str = "eu-ai-act", report: Optional[dict] = None) -> Optional[bytes]:
    """Generate a DOCX report if python-docx is available.

    Uses the standalone generator if a report dict is provided,
    otherwise falls back to the monorepo generator.
    """
    # Standalone path: use the report dict directly
    if report is not None:
        try:
            from comply.docx_report import generate_comply_docx
            return generate_comply_docx(report)
        except ImportError:
            log.info("python-docx not installed; DOCX export unavailable")
            return None
        except Exception as exc:
            log.warning("Standalone DOCX generation failed: %s", exc)
            return None

    # No report dict provided -- cannot generate without scan data
    log.info("DOCX generation requires a report dict in standalone mode")
    return None
