"""Compliance forecasting — trend analysis and score projection.

Pure-Python time-series analysis over existing scan history.
No new dependencies — linear regression is ~20 LOC.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional


def forecast_score(
    repo: str,
    framework: str = "eu-ai-act",
    weeks: int = 8,
    target_score: float = 80.0,
    min_scans: int = 2,
) -> dict:
    """Generate a compliance score forecast from scan history.

    Parameters
    ----------
    repo : str
        Repository path.
    framework : str
        Framework ID (e.g. "eu-ai-act", "eu_ai_act").
    weeks : int
        Number of weeks to project forward.
    target_score : float
        Target compliance score (0-100).
    min_scans : int
        Minimum data points required for forecasting.

    Returns
    -------
    dict with trend, velocity, projection, controlTrends, riskLevel, etc.
    """
    from comply.store import list_scans

    # Normalize framework ID
    fw = framework.replace("-", "_")

    scans = list_scans(repo=repo, framework=fw, limit=200)
    if not scans:
        scans = list_scans(repo=repo, framework=framework, limit=200)

    if len(scans) < min_scans:
        return {
            "repo": repo,
            "framework": framework,
            "status": "insufficient_data",
            "dataPoints": len(scans),
            "message": f"Need at least {min_scans} scans for forecasting, found {len(scans)}.",
        }

    # Sort chronologically (oldest first)
    scans.sort(key=lambda s: s.get("created_at", ""))

    # Build time series: (days_since_first, score)
    first_dt = _parse_dt(scans[0].get("created_at", ""))
    points = []
    history = []
    for s in scans:
        dt = _parse_dt(s.get("created_at", ""))
        days = (dt - first_dt).total_seconds() / 86400.0
        score = s.get("score", 0)
        points.append((days, score))
        history.append({
            "date": s.get("created_at", "")[:10],
            "score": round(score, 1),
            "scanId": s.get("id", ""),
        })

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    slope, intercept, r_squared = _linear_regression(xs, ys)

    # Velocity: points per week
    velocity = slope * 7.0

    # Classify trend
    if slope > 0.1:
        trend = "improving"
    elif slope < -0.1:
        trend = "declining"
    else:
        trend = "stable"

    # Current score (most recent)
    current_score = ys[-1]
    last_day = xs[-1]
    last_dt = _parse_dt(scans[-1].get("created_at", ""))

    # Project target date
    projected_date = None
    days_to_target = None
    if trend == "improving" and current_score < target_score and slope > 0:
        days_needed = (target_score - current_score) / slope
        projected_dt = last_dt + timedelta(days=days_needed)
        projected_date = projected_dt.strftime("%Y-%m-%d")
        days_to_target = int(days_needed)

    # Generate forecast points (weekly projections)
    forecast_points = []
    for w in range(1, weeks + 1):
        future_day = last_day + w * 7
        projected = slope * future_day + intercept
        projected = max(0.0, min(100.0, projected))
        forecast_dt = last_dt + timedelta(weeks=w)
        forecast_points.append({
            "date": forecast_dt.strftime("%Y-%m-%d"),
            "score": round(projected, 1),
        })

    # Per-control trend analysis (compare two most recent reports)
    control_trends = _analyze_control_trends(scans)

    # Risk level
    recent_regression = _has_recent_regression(scans)
    if trend == "declining" or (trend == "stable" and recent_regression):
        risk_level = "high"
    elif trend == "stable" or velocity < 1.0:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "repo": repo,
        "framework": framework,
        "status": "ok",
        "currentScore": round(current_score, 1),
        "dataPoints": len(scans),
        "firstScanDate": scans[0].get("created_at", "")[:10],
        "lastScanDate": scans[-1].get("created_at", "")[:10],
        "trend": trend,
        "velocity": round(velocity, 2),
        "rSquared": round(r_squared, 3),
        "riskLevel": risk_level,
        "targetScore": target_score,
        "projectedDate": projected_date,
        "daysToTarget": days_to_target,
        "forecast": forecast_points,
        "history": history,
        "controlTrends": control_trends,
    }


def _linear_regression(xs: list, ys: list):
    """Ordinary least squares. Returns (slope, intercept, r_squared)."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0, 0.0
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0, sum_y / max(n, 1), 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    # R-squared
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r_squared


def _parse_dt(s: str) -> datetime:
    """Parse an ISO-8601-ish timestamp, falling back to epoch."""
    if not s:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)
    try:
        # Handle common formats
        s = s.replace("Z", "+00:00")
        if "T" in s:
            # Try full ISO
            try:
                return datetime.fromisoformat(s)
            except ValueError:
                pass
            # Try without timezone
            try:
                return datetime.fromisoformat(s.split("+")[0].split("-")[0:3] and s[:19])
            except ValueError:
                pass
        return datetime.fromisoformat(s[:10])
    except Exception:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)


def _extract_control_map(scan: dict) -> dict:
    """Extract {controlId: status} from a scan's report_json or report."""
    controls = {}
    report = scan.get("report", {})
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except (json.JSONDecodeError, TypeError):
            report = {}

    for article in report.get("articles", []):
        for ctrl in article.get("controls", []):
            cid = ctrl.get("controlId", "")
            status = ctrl.get("status", ctrl.get("combinedStatus", "gap"))
            if cid:
                controls[cid] = status
    return controls


_STATUS_RANK = {"met": 3, "partial": 2, "gap": 1}


def _analyze_control_trends(scans: list) -> dict:
    """Compare control statuses across the two most recent scans."""
    result = {"improving": [], "declining": [], "stuck": []}

    if len(scans) < 2:
        return result

    prev_map = _extract_control_map(scans[-2])
    curr_map = _extract_control_map(scans[-1])

    if not prev_map or not curr_map:
        return result

    all_ids = set(prev_map.keys()) | set(curr_map.keys())
    for cid in sorted(all_ids):
        prev_status = prev_map.get(cid, "gap")
        curr_status = curr_map.get(cid, "gap")

        prev_rank = _STATUS_RANK.get(prev_status, 1)
        curr_rank = _STATUS_RANK.get(curr_status, 1)

        if curr_rank > prev_rank:
            result["improving"].append({
                "controlId": cid,
                "from": prev_status,
                "to": curr_status,
            })
        elif curr_rank < prev_rank:
            result["declining"].append({
                "controlId": cid,
                "from": prev_status,
                "to": curr_status,
            })
        elif curr_status == "gap":
            result["stuck"].append({
                "controlId": cid,
                "status": curr_status,
            })

    return result


def _has_recent_regression(scans: list) -> bool:
    """Check if the most recent scan shows a score drop."""
    if len(scans) < 2:
        return False
    prev_score = scans[-2].get("score", 0)
    curr_score = scans[-1].get("score", 0)
    return curr_score < prev_score - 0.5
