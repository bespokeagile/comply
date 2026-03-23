"""CI/CD Compliance Gate — pass/fail decision endpoint for deployment pipelines.

Wraps the existing scan + regression infrastructure with configurable rules
and persists every gate decision to SQLite for audit trails.
"""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


def run_gate(
    repo_path: str,
    framework: str = "eu_ai_act",
    scan_depth: str = "content",
    max_files: int = 500,
    threshold_score: float = 0.0,
    fail_on_regression: bool = False,
    max_critical_gaps: int = -1,
    use_cache: bool = False,
) -> dict:
    """Run a compliance gate check and return a structured pass/fail decision.

    Args:
        repo_path: Local path to the repository.
        framework: Compliance framework ID (underscore form, e.g. "eu_ai_act").
        scan_depth: "structure", "content", or "semantic".
        max_files: Max files to scan.
        threshold_score: Minimum score to pass (0 = always passes on score).
        fail_on_regression: Whether to fail if regression detected vs baseline.
        max_critical_gaps: Max allowed critical gaps (-1 = disabled).
        use_cache: Whether to use scan model cache (default False for accuracy).

    Returns:
        Structured gate decision dict.
    """
    from comply.scanner import run_comply_scan
    from comply.store import save_gate_decision

    decision_id = "gate-" + uuid.uuid4().hex[:10]
    created_at = datetime.now(timezone.utc).isoformat()
    commit_sha = _get_commit_sha(repo_path)

    # Normalise framework ID: scanner/tier system expects dashes
    fw_scan = framework.replace("_", "-")
    # Store format uses underscores
    fw_norm = framework.replace("-", "_")

    # 1. Run fresh scan
    try:
        report = run_comply_scan(
            target=repo_path,
            framework=fw_scan,
            scan_depth=scan_depth,
            max_files=max_files,
            use_cache=use_cache,
        )
    except Exception as exc:
        # Scan error → fail with reason
        result = _build_result(
            decision_id=decision_id,
            decision="fail",
            exit_code=2,
            score=0,
            threshold_score=threshold_score,
            passed_score=False,
            regression_detected=False,
            fail_on_regression=fail_on_regression,
            passed_regression=True,
            critical_gap_count=0,
            max_critical_gaps=max_critical_gaps,
            passed_gaps=True,
            reason=f"Scan error: {exc}",
            scan_id="",
            commit_sha=commit_sha,
            framework=fw_norm,
            repo_path=repo_path,
            created_at=created_at,
        )
        save_gate_decision(result)
        return result

    # 2. Extract score and scan ID
    summary = report.get("summary", {})
    score = summary.get("score", 0)
    scan_id = report.get("scanId", "")

    # 3. Count critical gaps (controls with status == "gap")
    critical_gap_count = 0
    for art in report.get("articles", []):
        for ctrl in art.get("controls", []):
            if ctrl.get("status") == "gap":
                critical_gap_count += 1

    # 4. Regression check
    regression_detected = False
    if fail_on_regression:
        try:
            from comply.regression import detect_regression
            reg = detect_regression(repo_path, fw_norm, report)
            if reg and reg.get("regressionDetected"):
                regression_detected = True
        except Exception as exc:
            log.warning("Regression check failed: %s", exc)

    # 5. Evaluate rules
    passed_score = score >= threshold_score
    passed_regression = not (fail_on_regression and regression_detected)
    passed_gaps = max_critical_gaps < 0 or critical_gap_count <= max_critical_gaps
    passed = passed_score and passed_regression and passed_gaps

    # 6. Build reason string
    reasons = []
    if passed_score:
        reasons.append(f"Score {score:.1f} >= {threshold_score:.1f}")
    else:
        reasons.append(f"Score {score:.1f} < {threshold_score:.1f}")
    if fail_on_regression:
        if regression_detected:
            reasons.append("regression detected")
        else:
            reasons.append("no regression")
    if max_critical_gaps >= 0:
        if passed_gaps:
            reasons.append(f"{critical_gap_count} gaps <= {max_critical_gaps} limit")
        else:
            reasons.append(f"{critical_gap_count} gaps > {max_critical_gaps} limit")
    reason = "; ".join(reasons)

    # 7. Build and persist result
    result = _build_result(
        decision_id=decision_id,
        decision="pass" if passed else "fail",
        exit_code=0 if passed else 1,
        score=score,
        threshold_score=threshold_score,
        passed_score=passed_score,
        regression_detected=regression_detected,
        fail_on_regression=fail_on_regression,
        passed_regression=passed_regression,
        critical_gap_count=critical_gap_count,
        max_critical_gaps=max_critical_gaps,
        passed_gaps=passed_gaps,
        reason=reason,
        scan_id=scan_id,
        commit_sha=commit_sha,
        framework=fw_norm,
        repo_path=repo_path,
        created_at=created_at,
    )
    save_gate_decision(result)

    return result


def _build_result(
    decision_id: str,
    decision: str,
    exit_code: int,
    score: float,
    threshold_score: float,
    passed_score: bool,
    regression_detected: bool,
    fail_on_regression: bool,
    passed_regression: bool,
    critical_gap_count: int,
    max_critical_gaps: int,
    passed_gaps: bool,
    reason: str,
    scan_id: str,
    commit_sha: str,
    framework: str,
    repo_path: str,
    created_at: str,
) -> dict:
    return {
        "decisionId": decision_id,
        "decision": decision,
        "exitCode": exit_code,
        "score": score,
        "thresholdScore": threshold_score,
        "passedScore": passed_score,
        "regressionDetected": regression_detected,
        "failOnRegression": fail_on_regression,
        "passedRegression": passed_regression,
        "criticalGapCount": critical_gap_count,
        "maxCriticalGaps": max_critical_gaps,
        "passedGaps": passed_gaps,
        "reason": reason,
        "scanId": scan_id,
        "commitSha": commit_sha,
        "framework": framework,
        "repoPath": repo_path,
        "createdAt": created_at,
    }


def _get_commit_sha(repo_path: str) -> str:
    """Try to get the current git commit SHA."""
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
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("git rev-parse failed for %s: %s", repo_path, e)
    return ""
