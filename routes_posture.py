"""Comply posture, predicate audit, cross-framework matrix, mapping, statistics."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from comply.scan_state import get_scan

log = logging.getLogger(__name__)

router = APIRouter()


# -- Posture endpoints ---------------------------------------------------------

@router.get("/posture")
def get_posture():
    """Get combined three-layer posture for all frameworks with data."""
    from comply.store import list_scans as list_stored, get_audit_summary
    scans = list_stored(limit=10)
    summary = get_audit_summary()
    frameworks = {}
    for s in scans:
        fw = s.get("framework", "")
        if fw and fw not in frameworks:
            frameworks[fw] = {
                "framework": fw,
                "lastScore": s.get("score", 0),
                "lastScanId": s.get("id", ""),
                "lastScanDate": s.get("created_at", ""),
            }
    return {
        "frameworks": list(frameworks.values()),
        "auditSummary": summary,
    }


@router.get("/posture/{framework}")
def get_posture_for_framework(framework: str):
    """Get three-layer posture for a specific framework."""
    from comply.store import list_scans as list_stored, query_audit_records
    from comply.adapters.registry import list_adapters, get_adapter
    from comply.adapters.base import NormalizedTrafficRecord

    # Get latest scan report
    scans = list_stored(framework=framework, limit=1)
    if not scans:
        raise HTTPException(404, f"No scans found for framework '{framework}'")
    scan = scans[0]
    report = scan.get("report", {})

    # Fetch audit records from all configured adapters
    all_records = []
    configured = [a for a in list_adapters() if a.get("configured")]
    for adapter_info in configured:
        adapter_name = adapter_info.get("name", "")
        adapter = get_adapter(adapter_name)
        if adapter:
            try:
                records = adapter.fetch_records(limit=1000)
                all_records.extend(records)
            except Exception as e:
                log.debug("Failed to fetch records from adapter %s: %s", adapter_name, e)

    # Also include stored records
    stored = query_audit_records(limit=1000)
    for rec in stored:
        all_records.append(NormalizedTrafficRecord(
            record_id=rec.get("id", ""),
            timestamp=rec.get("timestamp", ""),
            source_adapter=rec.get("adapter_name", ""),
            tool_name=rec.get("tool_name", ""),
            caller_identity=rec.get("caller_identity", ""),
            action=rec.get("action", "call"),
            duration_ms=rec.get("duration_ms", 0),
            status=rec.get("status", "ok"),
            policy_matched=rec.get("policy_matched", ""),
            cost_usd=rec.get("cost_usd", 0),
            metadata=rec.get("metadata", {}),
        ))

    # Regression
    from comply.regression import detect_regression
    regression_result = None
    try:
        regression_result = detect_regression(
            scan.get("repo_path", ""), framework, report
        )
    except Exception as e:
        log.debug("Regression detection failed for framework %s: %s", framework, e)

    # Fetch CI/CD records for Layer 2 enhancement
    from comply.store import query_cicd_records as _query_cicd
    cicd_records = _query_cicd(limit=500)

    from comply.evidence_layers import compute_combined_posture
    posture = compute_combined_posture(
        scan_report=report,
        regression_result=regression_result,
        audit_records=all_records,
        framework=framework,
        cicd_records=cicd_records or None,
    )
    posture["baseScanId"] = scan.get("id", "")
    return posture


# -- Predicate Audit endpoint (lead-gen) ---------------------------------------

# Rate limiter: 5 scans/day per IP (in-memory, resets on restart)
_AUDIT_RATE_LIMITS: dict = defaultdict(list)  # ip -> [timestamps]
_AUDIT_RATE_LIMIT = 5
_AUDIT_RATE_WINDOW = 86400  # 24 hours


class AuditRequest(BaseModel):
    url: str
    framework: str = "eu-ai-act"
    email: Optional[str] = None  # optional email capture


# Controls that require multi-hop graph traversal for proper evaluation.
# These are undecidable from infrastructure config, pipeline metadata,
# or traffic logs alone.
_GRAPH_REQUIRED_EVIDENCE_FNS = {
    "evidence_risk_assessment_gateway",
    "evidence_risk_categorization",
    "evidence_risk_register_auto",
    "evidence_impact_documentation",
    "evidence_human_oversight_gateway",
    "evidence_ai_system_inventory",
    "evidence_retention_compliance",
}

# Controls evaluable from infrastructure config (Vanta-decidable)
_INFRA_EVIDENCE_FNS = {
    "evidence_logical_access",
    "evidence_availability_controls",
    "evidence_data_handling",
}

# Controls evaluable from pipeline/CI metadata (GitLab-decidable)
_PIPELINE_EVIDENCE_FNS = {
    "evidence_change_management",
    "evidence_continuous_monitoring",
    "evidence_performance_measurement",
    "evidence_incident_response",
}


@router.post("/audit")
def predicate_audit(req: AuditRequest, request: Request):
    """Run a predicate gap audit -- the free lead-gen tool.

    Returns a report classifying each control by evaluation method:
    - keyword_match: evaluable by simple code scanning
    - graph_required: requires multi-hop graph traversal (only BespokeTracker)

    Also separates controls into three decidability categories:
    - infrastructure: decidable by Vanta/infrastructure scanning
    - pipeline: decidable by GitLab/CI-CD metadata
    - product_model: requires product model graph (only Comply Platform)
    """
    # Rate limiting by IP
    client_ip = "unknown"
    if request.client:
        client_ip = request.client.host
    now = time.time()
    _AUDIT_RATE_LIMITS[client_ip] = [
        t for t in _AUDIT_RATE_LIMITS[client_ip]
        if now - t < _AUDIT_RATE_WINDOW
    ]
    if len(_AUDIT_RATE_LIMITS[client_ip]) >= _AUDIT_RATE_LIMIT:
        raise HTTPException(
            429,
            f"Rate limit exceeded: {_AUDIT_RATE_LIMIT} audits per 24 hours. "
            "Install Comply CLI for unlimited local scans."
        )
    _AUDIT_RATE_LIMITS[client_ip].append(now)

    # Run the scan
    import tempfile
    output_dir = tempfile.mkdtemp(prefix="comply-audit-")

    try:
        from comply.scanner import run_comply_scan
        report = run_comply_scan(
            target=req.url,
            framework=req.framework,
            scan_depth="content",
            output_dir=output_dir,
            max_files=300,  # faster for audit
            use_cache=True,
        )
    except FileNotFoundError:
        raise HTTPException(400, "Repository path not found. Provide a valid local path or git URL.")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))

    # Classify controls by evaluation method and decidability
    infrastructure_controls = []
    pipeline_controls = []
    product_model_controls = []
    total_graph_required = 0
    total_keyword_match = 0

    for article in report.get("articles", []):
        for ctrl in article.get("controls", []):
            evidence_fn = ctrl.get("evidence_fn", "")

            # Classify evaluation method
            if evidence_fn in _GRAPH_REQUIRED_EVIDENCE_FNS:
                ctrl["evaluationMethod"] = "graph_required"
                ctrl["evaluationNote"] = (
                    "This control requires multi-hop graph traversal across "
                    "feature->spec->code relationships. Cannot be evaluated from "
                    "infrastructure config or pipeline metadata alone."
                )
                total_graph_required += 1
            else:
                ctrl["evaluationMethod"] = "keyword_match"
                ctrl["evaluationNote"] = (
                    "This control can be partially evaluated via code pattern matching."
                )
                total_keyword_match += 1

            # Classify decidability category
            if evidence_fn in _INFRA_EVIDENCE_FNS:
                ctrl["decidability"] = "infrastructure"
                infrastructure_controls.append(ctrl)
            elif evidence_fn in _PIPELINE_EVIDENCE_FNS:
                ctrl["decidability"] = "pipeline"
                pipeline_controls.append(ctrl)
            else:
                ctrl["decidability"] = "product_model"
                product_model_controls.append(ctrl)

    # Build the audit response
    total = report.get("summary", {}).get("total", 0)
    audit_result = {
        "reportType": "predicate_audit",
        "framework": req.framework,
        "target": req.url,
        "generatedAt": report.get("generatedAt", ""),
        "scanScore": report.get("summary", {}).get("score", 0),
        "predicateGap": {
            "totalControls": total,
            "graphRequired": total_graph_required,
            "keywordMatch": total_keyword_match,
            "graphRequiredPercent": round(total_graph_required / total * 100, 1) if total else 0,
            "message": (
                f"{total_graph_required} of {total} controls require product model "
                f"graph traversal that infrastructure scanning tools cannot evaluate."
            ),
        },
        "sections": {
            "infrastructure": {
                "label": "Infrastructure Controls (Vanta-decidable)",
                "description": "These controls can be evaluated by infrastructure compliance tools.",
                "controlCount": len(infrastructure_controls),
                "controls": infrastructure_controls,
            },
            "pipeline": {
                "label": "Pipeline Controls (GitLab-decidable)",
                "description": "These controls can be evaluated from CI/CD pipeline metadata.",
                "controlCount": len(pipeline_controls),
                "controls": pipeline_controls,
            },
            "product_model": {
                "label": "Product Model Controls (Comply only)",
                "description": (
                    "These controls require multi-hop graph traversal across "
                    "feature->spec->code->agent relationships. Only evaluable with "
                    "a product model graph."
                ),
                "controlCount": len(product_model_controls),
                "controls": product_model_controls,
            },
        },
        "articles": report.get("articles", []),
        "model": report.get("model", {}),
    }

    # Store email if provided
    if req.email:
        _store_audit_email(req.email, req.url, req.framework, audit_result)

    # Clean up temp dir
    import shutil
    try:
        shutil.rmtree(output_dir, ignore_errors=True)
    except OSError as e:
        log.debug("Failed to remove temp dir %s: %s", output_dir, e)

    return audit_result


def _store_audit_email(email: str, url: str, framework: str, result: dict):
    """Store email capture from predicate audit (append to JSONL file)."""
    import json
    from datetime import datetime, timezone

    email_log = os.path.expanduser("~/.comply/audit_emails.jsonl")
    os.makedirs(os.path.dirname(email_log), exist_ok=True)
    entry = {
        "email": email,
        "url": url,
        "framework": framework,
        "score": result.get("scanScore", 0),
        "graphRequired": result.get("predicateGap", {}).get("graphRequired", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(email_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.debug("Failed to write audit email log: %s", e)


# -- Cross-framework matrix ---------------------------------------------------


@router.get("/matrix")
def get_cross_framework_matrix(frameworks: str = "eu-ai-act,nist-ai-rmf,iso-42001"):
    """Get cross-framework compliance matrix from latest scans.

    Pass comma-separated framework IDs. Uses the latest scan for each framework.
    """
    from comply.store import list_scans as list_stored
    from comply.report import build_cross_framework_matrix

    fw_list = [f.strip() for f in frameworks.split(",") if f.strip()]
    reports = []
    for fw in fw_list:
        scans = list_stored(framework=fw, limit=1)
        if scans and scans[0].get("report"):
            reports.append(scans[0]["report"])

    if not reports:
        raise HTTPException(404, "No scans found for the requested frameworks")

    matrix = build_cross_framework_matrix(reports)
    return matrix


# -- Static mapping + jurisdictions --------------------------------------------


@router.get("/jurisdictions")
def get_jurisdictions():
    """Return available jurisdiction profiles."""
    from comply.mapping import get_jurisdiction_profiles
    return get_jurisdiction_profiles()


@router.get("/mapping/priorities")
def get_mapping_priorities():
    """Return remediation priorities from latest scans."""
    from comply.store import list_scans as list_stored
    from comply.mapping import get_remediation_priorities

    scans = list_stored(limit=50)
    reports = []
    seen = set()
    for s in scans:
        fw = s.get("framework", "")
        if fw not in seen and s.get("report"):
            seen.add(fw)
            reports.append(s["report"])
    if not reports:
        return []
    return get_remediation_priorities(reports)


@router.get("/mapping/{evidence_fn}")
def get_mapping_detail(evidence_fn: str):
    """Return detail for one capability across all frameworks."""
    from comply.mapping import get_capability_detail
    cap = get_capability_detail(evidence_fn)
    if cap is None:
        raise HTTPException(404, f"Capability '{evidence_fn}' not found")
    return cap


@router.get("/mapping")
def get_mapping(frameworks: Optional[str] = None):
    """Return static control mapping (no scan needed).

    Pass comma-separated framework IDs, or omit for all frameworks.
    """
    from comply.mapping import build_control_mapping
    fw_ids = None
    if frameworks:
        fw_ids = [f.strip() for f in frameworks.split(",") if f.strip()]
    return build_control_mapping(framework_ids=fw_ids)


# -- Scan statistics (public) -------------------------------------------------


@router.get("/audit/stats")
def get_audit_statistics():
    """Public aggregate scan statistics.

    Powers the "100 repos scanned" report. No authentication required.
    Returns total scans, average score, gap distribution by framework.
    """
    from comply.store import get_scan_statistics
    return get_scan_statistics()
