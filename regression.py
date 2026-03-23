"""Regression detection — compare scans against baselines.

JSON-based (no Kuzu dependency). Uses the SQLite store for baseline lookup.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


def compare_scans(baseline: dict, current: dict) -> dict:
    """Compare two scan reports and return a regression analysis.

    Args:
        baseline: The baseline report dict.
        current: The current report dict.

    Returns:
        Dict with regressionDetected, newGaps, resolvedGaps, scoreDelta, severity.
    """
    b_summary = baseline.get("summary", {})
    c_summary = current.get("summary", {})

    # Build control maps
    b_controls = {}
    for art in baseline.get("articles", []):
        art_id = art.get("articleId", "")
        for ctrl in art.get("controls", []):
            cid = ctrl.get("controlId", "")
            b_controls[cid] = {**ctrl, "_articleId": art_id}

    c_controls = {}
    for art in current.get("articles", []):
        art_id = art.get("articleId", "")
        for ctrl in art.get("controls", []):
            cid = ctrl.get("controlId", "")
            c_controls[cid] = {**ctrl, "_articleId": art_id}

    new_gaps = []
    resolved_gaps = []
    changed = []

    for cid, ctrl in c_controls.items():
        old = b_controls.get(cid)
        if old is None:
            # New control not in baseline
            if ctrl.get("status") != "met":
                new_gaps.append(_clean_ctrl(ctrl))
        elif old.get("status") != ctrl.get("status"):
            change = {
                "controlId": cid,
                "oldStatus": old.get("status"),
                "newStatus": ctrl.get("status"),
                "articleId": ctrl.get("_articleId", ""),
                "requirement": ctrl.get("requirement", ""),
            }
            changed.append(change)

            # Regression: status got worse
            if _is_worse(old.get("status", ""), ctrl.get("status", "")):
                new_gaps.append(_clean_ctrl(ctrl))
            # Improvement: status got better
            elif _is_better(old.get("status", ""), ctrl.get("status", "")):
                resolved_gaps.append(_clean_ctrl(ctrl))

    # Controls removed from current (resolved)
    for cid, ctrl in b_controls.items():
        if cid not in c_controls and ctrl.get("status") != "met":
            resolved_gaps.append(_clean_ctrl(ctrl))

    score_delta = round(
        c_summary.get("score", 0) - b_summary.get("score", 0), 1
    )

    # Severity assessment
    if not new_gaps:
        severity = "none"
    elif len(new_gaps) <= 2:
        severity = "low"
    elif len(new_gaps) <= 5:
        severity = "medium"
    else:
        severity = "high"

    return {
        "regressionDetected": len(new_gaps) > 0,
        "severity": severity,
        "scoreDelta": score_delta,
        "baselineScore": b_summary.get("score", 0),
        "currentScore": c_summary.get("score", 0),
        "baselineScanId": baseline.get("scanId", ""),
        "currentScanId": current.get("scanId", ""),
        "newGaps": new_gaps,
        "resolvedGaps": resolved_gaps,
        "changed": changed,
        "summary": {
            "newGapCount": len(new_gaps),
            "resolvedCount": len(resolved_gaps),
            "changedCount": len(changed),
        },
    }


def detect_regression(
    repo_path: str,
    framework: str,
    current_report: dict,
) -> Optional[dict]:
    """Auto-load baseline from store and compare against current report.

    Returns None if no baseline exists.
    """
    try:
        from comply.store import get_baseline
        baseline_scan = get_baseline(repo_path, framework)
    except Exception as exc:
        log.warning("Failed to load baseline: %s", exc)
        return None

    if baseline_scan is None:
        return None

    baseline_report = baseline_scan.get("report", {})
    if not baseline_report:
        return None

    return compare_scans(baseline_report, current_report)


def set_baseline(scan_id: str) -> bool:
    """Set a scan as the baseline."""
    from comply.store import set_baseline as store_set_baseline
    return store_set_baseline(scan_id)


def get_baseline(repo_path: str, framework: str) -> Optional[dict]:
    """Get the current baseline for a repo+framework."""
    from comply.store import get_baseline as store_get_baseline
    return store_get_baseline(repo_path, framework)


# ── Helpers ──────────────────────────────────────────────────────────────

_STATUS_ORDER = {"met": 0, "partial": 1, "gap": 2}


def _is_worse(old_status: str, new_status: str) -> bool:
    """Return True if new_status is worse than old_status."""
    return _STATUS_ORDER.get(new_status, 2) > _STATUS_ORDER.get(old_status, 2)


def _is_better(old_status: str, new_status: str) -> bool:
    """Return True if new_status is better than old_status."""
    return _STATUS_ORDER.get(new_status, 2) < _STATUS_ORDER.get(old_status, 2)


def _clean_ctrl(ctrl: dict) -> dict:
    """Remove internal fields from a control dict."""
    return {k: v for k, v in ctrl.items() if not k.startswith("_")}
