"""Diff utilities for comparing two Comply scan reports."""
from __future__ import annotations


def _compute_diff(baseline: dict, current: dict) -> dict:
    """Compute the diff between two scan reports."""
    b_summary = baseline.get("summary", {})
    c_summary = current.get("summary", {})

    b_controls = {}
    for art in baseline.get("articles", []):
        for ctrl in art.get("controls", []):
            b_controls[ctrl.get("controlId", "")] = ctrl

    c_controls = {}
    for art in current.get("articles", []):
        for ctrl in art.get("controls", []):
            c_controls[ctrl.get("controlId", "")] = ctrl

    new_gaps = []
    resolved_gaps = []
    changed = []

    for cid, ctrl in c_controls.items():
        old = b_controls.get(cid)
        if old is None:
            if ctrl.get("status") != "met":
                new_gaps.append(ctrl)
        elif old.get("status") != ctrl.get("status"):
            changed.append({"controlId": cid, "old": old.get("status"), "new": ctrl.get("status"), **ctrl})
            if ctrl.get("status") == "gap" and old.get("status") != "gap":
                new_gaps.append(ctrl)
            elif old.get("status") != "met" and ctrl.get("status") == "met":
                resolved_gaps.append(ctrl)

    for cid, ctrl in b_controls.items():
        if cid not in c_controls:
            resolved_gaps.append(ctrl)

    return {
        "baseline": {
            "scanId": baseline.get("scanId", ""),
            "framework": baseline.get("framework", ""),
            "score": b_summary.get("score", 0),
            "generatedAt": baseline.get("generatedAt", ""),
        },
        "current": {
            "scanId": current.get("scanId", ""),
            "framework": current.get("framework", ""),
            "score": c_summary.get("score", 0),
            "generatedAt": current.get("generatedAt", ""),
        },
        "scoreDelta": round(c_summary.get("score", 0) - b_summary.get("score", 0), 1),
        "newGaps": new_gaps,
        "resolvedGaps": resolved_gaps,
        "changed": changed,
        "regressionDetected": len(new_gaps) > 0,
    }
