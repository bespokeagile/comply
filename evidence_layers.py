"""Three-layer evidence aggregation engine.

Combines evidence from:
  - **Layer 1 (Code)**: Static analysis of codebase (existing scan report)
  - **Layer 2 (Process)**: Development process evidence (regression, history)
  - **Layer 3 (Traffic)**: AI agent governance (audit log records)

Each control gets a per-layer status and a combined posture.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from comply.adapters.base import NormalizedTrafficRecord

log = logging.getLogger(__name__)

# Status priority for combining: met < partial < gap
_STATUS_ORDER = {"met": 0, "partial": 1, "gap": 2}


def _make_result(status: str, evidence: List[str], gaps: Optional[List[str]] = None,
                 recommendation: str = "") -> Dict[str, Any]:
    """Standard evidence result dict."""
    return {
        "status": status,
        "evidence": evidence,
        "gaps": gaps or [],
        "recommendation": recommendation,
    }


def _worst_status(*statuses: str) -> str:
    """Return the worst status from a set (gap > partial > met)."""
    worst = "met"
    for s in statuses:
        if _STATUS_ORDER.get(s, 0) > _STATUS_ORDER.get(worst, 0):
            worst = s
    return worst


def _best_status(*statuses: str) -> str:
    """Return the best status from a set (met < partial < gap)."""
    best = "gap"
    for s in statuses:
        if _STATUS_ORDER.get(s, 2) < _STATUS_ORDER.get(best, 2):
            best = s
    return best


def _compute_recency(records, recency_days=7):
    # type: (list, int) -> tuple
    """Check if records have recent activity.

    Returns (is_recent, days_since, rate_per_day).
    """
    if not records:
        return False, None, 0.0
    timestamps = []
    for r in records:
        ts = getattr(r, "timestamp", None) or getattr(r, "created_at", "")
        if ts:
            timestamps.append(str(ts))
    if not timestamps:
        return False, None, 0.0
    most_recent = max(timestamps)
    try:
        last_dt = datetime.fromisoformat(most_recent.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_since = (now - last_dt).total_seconds() / 86400
        cutoff = (now - timedelta(days=30)).isoformat()
        recent_count = sum(1 for t in timestamps if t >= cutoff)
        rate = recent_count / 30.0
        return days_since <= recency_days, round(days_since, 1), round(rate, 2)
    except (ValueError, TypeError):
        return False, None, 0.0


# ── Layer 3 evidence functions ──────────────────────────────────────

def _l3_audit_logging(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for audit logging / record-keeping controls."""
    total = summary.get("total_records", 0)
    if total >= 100:
        is_recent, days_since, rate = _compute_recency(records)
        evidence = [f"{total} audit records captured", "Comprehensive logging active"]
        if rate > 0:
            evidence.append(f"Activity rate: {rate} records/day")
        if not is_recent:
            return _make_result("partial", evidence,
                                [f"Last audit record is {days_since} days old"],
                                "Audit logging may have stopped — investigate recency gap")
        return _make_result("met", evidence)
    elif total >= 10:
        return _make_result("partial", [f"{total} audit records captured"],
                            ["Logging coverage may be incomplete"],
                            "Increase logging coverage across all AI tool invocations")
    return _make_result("gap", [], ["No significant audit trail found"],
                        "Enable audit logging for all AI system interactions")


def _l3_access_control(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for access control / role-based controls."""
    denials = summary.get("total_denials", 0)
    unique_callers = summary.get("unique_callers", 0)
    if denials > 0 and unique_callers > 1:
        evidence = [
            f"{denials} access denials logged (policy enforcement active)",
            f"{unique_callers} distinct caller identities observed",
        ]
        # Check if denials are recent
        denial_records = [r for r in records if r.action == "deny"]
        if denial_records:
            is_recent, days_since, _ = _compute_recency(denial_records)
            if not is_recent and days_since is not None:
                evidence.append(f"Access control enforcement not recently active ({days_since}d ago)")
        return _make_result("met", evidence)
    elif unique_callers > 1:
        return _make_result("partial", [f"{unique_callers} distinct callers"],
                            ["No policy denials observed — access controls may not be enforced"],
                            "Configure and test access control policies")
    return _make_result("gap", [], ["No caller identity differentiation observed"],
                        "Implement role-based access controls for AI tool usage")


def _l3_monitoring(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for continuous monitoring controls."""
    total = summary.get("total_records", 0)
    errors = summary.get("total_errors", 0)
    if total >= 50:
        parts = [f"{total} interactions monitored"]
        if errors > 0:
            parts.append(f"{errors} errors/anomalies detected")
        is_recent, days_since, rate = _compute_recency(records)
        if rate > 0:
            parts.append(f"Activity rate: {rate} records/day")
        if not is_recent:
            return _make_result("partial", parts,
                                [f"Last monitoring record is {days_since} days old"],
                                "Monitoring may have stopped — check data pipeline recency")
        return _make_result("met", parts)
    elif total > 0:
        return _make_result("partial", [f"{total} interactions monitored"],
                            ["Monitoring coverage is limited"],
                            "Expand monitoring to cover all AI system operations")
    return _make_result("gap", [], ["No monitoring data available"],
                        "Implement continuous monitoring for AI system operations")


def _l3_transparency(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for transparency / disclosure controls."""
    total = summary.get("total_records", 0)
    unique_tools = summary.get("unique_tools", 0)
    if total > 0 and unique_tools > 0:
        return _make_result("met", [
            f"{unique_tools} distinct AI tools documented in traffic logs",
            "Tool invocation details recorded for transparency",
        ])
    return _make_result("gap", [], ["No AI tool usage transparency data"],
                        "Log all AI tool invocations with full metadata for transparency")


def _l3_risk_management(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for risk management controls."""
    denials = summary.get("total_denials", 0)
    total_cost = summary.get("total_cost", 0)
    if denials > 0:
        return _make_result("met", [
            f"{denials} policy-blocked interactions (risk controls active)",
            f"${total_cost:.2f} total AI cost tracked" if total_cost else "Cost tracking available",
        ])
    elif summary.get("total_records", 0) > 0:
        return _make_result("partial",
                            ["Traffic monitoring active but no risk policy enforcement"],
                            ["No policy denials observed"],
                            "Define and enforce risk management policies for AI tool usage")
    return _make_result("gap", [], ["No risk management evidence in traffic data"],
                        "Implement policy-based risk controls for AI system interactions")


def _l3_human_oversight(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for human oversight controls."""
    unique_callers = summary.get("unique_callers", 0)
    denials = summary.get("total_denials", 0)
    if unique_callers > 1 and denials > 0:
        return _make_result("met", [
            f"{unique_callers} human/agent identities with oversight capability",
            f"{denials} override/denial events recorded",
        ])
    elif unique_callers > 0:
        return _make_result("partial",
                            [f"{unique_callers} caller identities observed"],
                            ["Limited evidence of human override capability"],
                            "Enable and document human override mechanisms")
    return _make_result("gap", [], ["No human oversight evidence in traffic data"],
                        "Implement human-in-the-loop controls for AI tool usage")


def _l3_input_sanitization(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for input sanitization controls from traffic data."""
    denials = summary.get("total_denials", 0)
    total = summary.get("total_records", 0)
    if denials > 0 and total >= 50:
        return _make_result("met", [
            f"{denials} input validation denial(s) in {total} records",
            "Active input filtering with enforcement",
        ])
    elif denials > 0 or total >= 20:
        return _make_result("partial",
                            [f"{denials} denial(s) in {total} records"],
                            ["Input sanitization enforcement may be incomplete"],
                            "Increase input validation coverage across all LLM entry points")
    return _make_result("gap", [], ["No input sanitization evidence in traffic data"],
                        "Implement input validation that logs denial events")


def _l3_output_validation(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for output validation/filtering controls from traffic data."""
    errors = summary.get("total_errors", 0)
    total = summary.get("total_records", 0)
    unique_tools = summary.get("unique_tools", 0)
    if total >= 50 and unique_tools > 0:
        parts = [f"{total} LLM interactions monitored across {unique_tools} tool(s)"]
        if errors > 0:
            parts.append(f"{errors} output validation event(s) logged")
        return _make_result("met", parts)
    elif total > 0:
        return _make_result("partial",
                            [f"{total} interactions recorded"],
                            ["Output validation coverage is limited"],
                            "Expand output filtering to cover all LLM response paths")
    return _make_result("gap", [], ["No output validation evidence in traffic data"],
                        "Implement output filtering with logging for all LLM responses")


def _l3_consumption_limits(records: List[NormalizedTrafficRecord], summary: Dict) -> Dict:
    """Evidence for rate limiting and cost control from traffic data."""
    denials = summary.get("total_denials", 0)
    total_cost = summary.get("total_cost", 0)
    total = summary.get("total_records", 0)
    if denials > 0 and total_cost > 0:
        evidence = [
            f"{denials} rate limit/quota enforcement(s)",
            f"${total_cost:.2f} total cost tracked across {total} calls",
        ]
        # Compute denial rate for windowed insight
        denial_records = [r for r in records if r.action == "deny"]
        if denial_records:
            _, _, rate = _compute_recency(denial_records)
            if rate > 0:
                evidence.append(f"{rate} denials/day")
            if rate > 1.0:
                evidence.append("Active rate limiting")
        return _make_result("met", evidence)
    elif total_cost > 0:
        return _make_result("partial",
                            [f"${total_cost:.2f} cost tracked but no limit enforcement observed"],
                            ["Rate limiting may not be active"],
                            "Implement and test rate limits, token budgets, and cost caps")
    elif total > 0:
        return _make_result("partial",
                            [f"{total} API calls logged without cost tracking"],
                            ["No cost tracking or rate limiting observed"],
                            "Add cost tracking and consumption limits for LLM API calls")
    return _make_result("gap", [], ["No consumption limit evidence in traffic data"],
                        "Implement rate limits, token budgets, and cost tracking")


# Map evidence function names to Layer 3 evaluators
_L3_FN_MAP = {
    "evidence_audit_logging": _l3_audit_logging,
    "evidence_traceability": _l3_audit_logging,
    "evidence_logical_access": _l3_access_control,
    "evidence_continuous_monitoring": _l3_monitoring,
    "evidence_transparency_disclosure": _l3_transparency,
    "evidence_transparency_logging": _l3_transparency,
    "evidence_risk_assessment_gateway": _l3_risk_management,
    "evidence_risk_categorization": _l3_risk_management,
    "evidence_risk_register_auto": _l3_risk_management,
    "evidence_governance_policy": _l3_risk_management,
    "evidence_human_oversight_gateway": _l3_human_oversight,
    "evidence_performance_measurement": _l3_monitoring,
    "evidence_change_management": _l3_audit_logging,
    "evidence_incident_response": _l3_risk_management,
    "evidence_ai_system_inventory": _l3_transparency,
    "evidence_impact_documentation": _l3_risk_management,
    "evidence_data_handling": _l3_access_control,
    "evidence_consumer_notification": _l3_transparency,
    "evidence_availability_controls": _l3_monitoring,
    "evidence_retention_compliance": _l3_audit_logging,
    # OWASP LLM Top 10
    "evidence_input_sanitization": _l3_input_sanitization,
    "evidence_output_validation": _l3_output_validation,
    "evidence_consumption_limits": _l3_consumption_limits,
    "evidence_model_provenance": _l3_audit_logging,
    "evidence_prompt_protection": _l3_access_control,
    "evidence_embedding_security": _l3_access_control,
    "evidence_access_control": _l3_access_control,
    # Phase 9: MCP security + AI supply chain
    "evidence_mcp_server_security": _l3_access_control,
    "evidence_ai_supply_chain": _l3_audit_logging,
}


# ── Layer 2 evidence functions (CI/CD) ─────────────────────────────

def _l2_testing(
    cicd_records: List[Dict[str, Any]],
    has_baseline: bool,
    regression_detected: bool,
    resolved_count: int,
) -> Dict[str, Any]:
    """L2 evidence for testing controls using CI/CD test suite records."""
    test_records = [r for r in cicd_records if r.get("metadata", {}).get("cicd_type") == "test_result"]
    if not test_records:
        return _l2_default(cicd_records, has_baseline, regression_detected, resolved_count)

    passing = [r for r in test_records if r.get("action") == "call"]
    failing = [r for r in test_records if r.get("action") == "error"]
    total = len(test_records)

    if len(passing) >= 3 and not failing:
        return _make_result("met", [
            f"{total} test suite runs recorded",
            f"{len(passing)} passing runs with no failures",
            "CI/CD test pipeline demonstrates active quality assurance",
        ])
    elif passing:
        evidence = [f"{total} test runs: {len(passing)} passing, {len(failing)} failing"]
        gaps = ["Some test runs have failures"] if failing else []
        return _make_result("partial", evidence, gaps,
                            "Investigate and fix failing test suites for full compliance")
    else:
        return _make_result("partial", [f"{total} test runs, all failing"],
                            ["No passing test runs recorded"],
                            "Fix test suite failures to demonstrate quality assurance")


def _l2_change_management(
    cicd_records: List[Dict[str, Any]],
    has_baseline: bool,
    regression_detected: bool,
    resolved_count: int,
) -> Dict[str, Any]:
    """L2 evidence for change management using CI/CD pipeline + deployment records."""
    pipeline_records = [r for r in cicd_records
                        if r.get("metadata", {}).get("cicd_type") in ("workflow_run", "deployment")]
    if not pipeline_records:
        return _l2_default(cicd_records, has_baseline, regression_detected, resolved_count)

    successful = [r for r in pipeline_records if r.get("action") == "call"]
    total = len(pipeline_records)

    if len(successful) >= 2 and len(successful) == total:
        return _make_result("met", [
            f"{total} CI/CD events recorded, all successful",
            "Automated change management pipeline active",
        ])
    elif successful:
        failed = total - len(successful)
        return _make_result("partial", [
            f"{total} CI/CD events: {len(successful)} successful, {failed} failed",
        ], ["Some pipeline or deployment events failed"],
           "Investigate failed deployments and ensure change management controls")
    else:
        return _make_result("partial", [f"{total} CI/CD events, all failed"],
                            ["No successful CI/CD events recorded"],
                            "Fix CI/CD pipeline to demonstrate change management")


def _l2_continuous_monitoring(
    cicd_records: List[Dict[str, Any]],
    has_baseline: bool,
    regression_detected: bool,
    resolved_count: int,
) -> Dict[str, Any]:
    """L2 evidence for continuous monitoring using all CI/CD record types."""
    if not cicd_records:
        return _l2_default(cicd_records, has_baseline, regression_detected, resolved_count)

    event_types = set(r.get("metadata", {}).get("cicd_type", "") for r in cicd_records)
    event_types.discard("")
    total = len(cicd_records)

    if total >= 5 and len(event_types) >= 2:
        return _make_result("met", [
            f"{total} CI/CD events across {len(event_types)} event types",
            f"Event types: {', '.join(sorted(event_types))}",
            "Active continuous monitoring via CI/CD pipeline",
        ])
    elif total > 0:
        evidence = [f"{total} CI/CD events recorded"]
        gaps = []
        if len(event_types) < 2:
            gaps.append("Only one event type — expand monitoring coverage")
        if total < 5:
            gaps.append("Limited monitoring history — need more CI/CD events")
        return _make_result("partial", evidence, gaps,
                            "Increase CI/CD monitoring coverage across event types")
    return _l2_default(cicd_records, has_baseline, regression_detected, resolved_count)


def _l2_default(
    cicd_records: List[Dict[str, Any]],
    has_baseline: bool,
    regression_detected: bool,
    resolved_count: int,
) -> Dict[str, Any]:
    """Default L2 evidence using baseline/regression status (original behavior)."""
    if has_baseline and not regression_detected:
        return _make_result("met", [
            "Baseline established with no regression",
            f"{resolved_count} gap(s) resolved since baseline" if resolved_count else "Stable compliance posture",
        ])
    elif has_baseline and regression_detected:
        return _make_result("partial", [
            "Baseline exists but regression detected",
        ], ["Compliance regression in development process"],
           "Review and address compliance regressions before release")
    else:
        return _make_result("partial", [],
                            ["No baseline established for regression tracking"],
                            "Set a compliance baseline to enable process evidence")


_L2_FN_MAP = {
    "evidence_performance_measurement": _l2_testing,
    "evidence_change_management": _l2_change_management,
    "evidence_continuous_monitoring": _l2_continuous_monitoring,
    "evidence_incident_response": _l2_change_management,
}


# ── Layer 4 evidence functions (active governance) ──────────────────

def _l4_human_oversight(decisions: List[Dict[str, Any]], activity_summary: Dict[str, Any]) -> Dict[str, Any]:
    """L4 evidence for human oversight controls (EU AI Act Art. 14).

    Checks decision log for override events and activity log for
    review/claim events by human roles.
    """
    override_decisions = [d for d in decisions if d.get("proceeded") and d.get("actor_type") == "human"]
    review_events = activity_summary.get("review_events", 0)
    claim_events = activity_summary.get("claim_events", 0)
    human_actions = len(override_decisions) + review_events + claim_events

    if human_actions >= 5:
        evidence = [
            f"{len(override_decisions)} human override decision(s) in governance log",
            f"{review_events + claim_events} review/claim event(s) in activity log",
        ]
        return _make_result("met", evidence)
    elif human_actions > 0:
        evidence = [f"{human_actions} human governance action(s) recorded"]
        return _make_result("partial", evidence,
                            ["Limited human oversight activity"],
                            "Increase human review and override engagement")
    return _make_result("gap", [],
                        ["No human oversight activity in governance data"],
                        "Enable human override mechanisms and document governance decisions")


def _l4_management_review(decisions: List[Dict[str, Any]], activity_summary: Dict[str, Any]) -> Dict[str, Any]:
    """L4 evidence for management review controls (ISO 42001 9.1).

    Checks for Admin/Leader role activity and strategic decisions.
    """
    admin_actions = activity_summary.get("admin_actions", 0)
    reviewed_decisions = [d for d in decisions if d.get("reviewed_by")]
    strategic_decisions = [d for d in decisions if d.get("justification")]

    if admin_actions > 0 and len(reviewed_decisions) >= 3:
        evidence = [
            f"{admin_actions} Admin/Leader action(s) in last 30 days",
            f"{len(reviewed_decisions)} decision(s) reviewed by management",
            f"{len(strategic_decisions)} decision(s) with documented justification",
        ]
        return _make_result("met", evidence)
    elif admin_actions > 0 or reviewed_decisions:
        evidence = []
        if admin_actions > 0:
            evidence.append(f"{admin_actions} Admin/Leader action(s)")
        if reviewed_decisions:
            evidence.append(f"{len(reviewed_decisions)} reviewed decision(s)")
        return _make_result("partial", evidence,
                            ["Management review coverage is incomplete"],
                            "Increase management review cadence for governance decisions")
    return _make_result("gap", [],
                        ["No management review activity detected"],
                        "Establish regular management review of AI governance decisions")


def _l4_governance_process(decisions: List[Dict[str, Any]], activity_summary: Dict[str, Any]) -> Dict[str, Any]:
    """L4 evidence for governance process controls (NIST Govern 1.3).

    Checks for decisions across multiple predicate types and multi-role engagement.
    """
    # Count distinct predicate types from check_ids (check_id format: "chk-{predicate_name}")
    predicate_types = set()
    for d in decisions:
        check_id = d.get("check_id", "")
        if check_id:
            predicate_types.add(check_id)
    unique_roles = activity_summary.get("unique_roles", 0)

    if len(predicate_types) >= 3 and unique_roles >= 2:
        evidence = [
            f"Governance decisions span {len(predicate_types)} predicate type(s)",
            f"{unique_roles} distinct role(s) engaged in governance",
            f"{len(decisions)} total governance decision(s)",
        ]
        return _make_result("met", evidence)
    elif predicate_types or unique_roles >= 2:
        evidence = []
        if predicate_types:
            evidence.append(f"Governance covers {len(predicate_types)} predicate type(s)")
        if unique_roles >= 2:
            evidence.append(f"{unique_roles} role(s) participating")
        gaps = []
        if len(predicate_types) < 3:
            gaps.append("Governance decisions cover fewer than 3 predicate types")
        if unique_roles < 2:
            gaps.append("Governance decisions lack multi-role engagement")
        return _make_result("partial", evidence, gaps,
                            "Expand governance process to cover more predicate types with multiple roles")
    return _make_result("gap", [],
                        ["No governance process evidence detected"],
                        "Establish cross-functional governance process for AI system decisions")


_L4_FN_MAP = {
    "evidence_human_oversight": _l4_human_oversight,
    "evidence_override_capability": _l4_human_oversight,
    "evidence_stop_mechanism": _l4_human_oversight,
    "evidence_governance_policy": _l4_governance_process,
    "evidence_governance_policy_full": _l4_governance_process,
    "evidence_mcp_governance": _l4_governance_process,
    "evidence_agent_governance": _l4_governance_process,
    "evidence_human_oversight_gateway": _l4_human_oversight,
    "evidence_risk_assessment_gateway": _l4_management_review,
}


def _compute_audit_summary(records: List[NormalizedTrafficRecord]) -> Dict[str, Any]:
    """Compute aggregate statistics from audit records including recency."""
    total = len(records)
    denials = sum(1 for r in records if r.action == "deny")
    errors = sum(1 for r in records if r.action == "error" or r.status in ("error", "denied"))
    callers = set(r.caller_identity for r in records if r.caller_identity)
    tools = set(r.tool_name for r in records if r.tool_name)
    cost = sum(r.cost_usd for r in records)

    # Recency data
    is_recent, days_since, rate = _compute_recency(records)
    most_recent_at = None
    if records:
        timestamps = []
        for r in records:
            ts = getattr(r, "timestamp", None) or getattr(r, "created_at", "")
            if ts:
                timestamps.append(str(ts))
        if timestamps:
            most_recent_at = max(timestamps)

    return {
        "total_records": total,
        "total_denials": denials,
        "total_errors": errors,
        "unique_callers": len(callers),
        "unique_tools": len(tools),
        "total_cost": cost,
        "callers": list(callers),
        "tools": list(tools),
        "most_recent_at": most_recent_at,
        "days_since_latest": days_since,
        "activity_rate_per_day": rate,
    }


def _build_governance_activity_summary(activity_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize activity log entries for L4 evidence evaluation."""
    review_events = 0
    claim_events = 0
    admin_actions = 0
    roles = set()
    for entry in activity_log:
        action = entry.get("action", "")
        role = entry.get("userRole", "")
        if role:
            roles.add(role)
        if role in ("Admin", "Leader", "CISO"):
            admin_actions += 1
        if action in ("review", "validate", "approve"):
            review_events += 1
        elif action in ("claim", "unclaim"):
            claim_events += 1
    return {
        "review_events": review_events,
        "claim_events": claim_events,
        "admin_actions": admin_actions,
        "unique_roles": len(roles),
        "total_actions": len(activity_log),
    }


def compute_combined_posture(
    scan_report: Dict[str, Any],
    regression_result: Optional[Dict[str, Any]],
    audit_records: List[NormalizedTrafficRecord],
    framework: str,
    cicd_records: Optional[List[Dict[str, Any]]] = None,
    governance_decisions: Optional[List[Dict[str, Any]]] = None,
    governance_activity: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute multi-layer combined compliance posture.

    Parameters
    ----------
    scan_report : dict
        The base scan report (Layer 1 evidence from code analysis).
    regression_result : dict or None
        Regression detection result against baseline (Layer 2 evidence).
    audit_records : list
        Normalised audit records from adapters (Layer 3 evidence).
    framework : str
        Framework ID for context.
    cicd_records : list of dict or None
        CI/CD records from store for enhanced Layer 2 evidence.
    governance_decisions : list of dict or None
        Decision log entries for Layer 4 evidence (active governance).
    governance_activity : list of dict or None
        Activity log entries for Layer 4 evidence.

    Returns
    -------
    dict
        Posture with per-control layer breakdown and combined scores.
    """
    audit_summary = _compute_audit_summary(audit_records)

    # Layer 2 evidence: process maturity indicators
    has_baseline = regression_result is not None
    regression_detected = regression_result.get("regressionDetected", False) if regression_result else False
    resolved_count = len(regression_result.get("resolvedGaps", [])) if regression_result else 0

    # Layer 4 evidence: active governance (optional)
    has_l4 = bool(governance_decisions or governance_activity)
    gov_decisions = governance_decisions or []
    gov_activity_summary = _build_governance_activity_summary(governance_activity or [])

    articles_out = []
    total_combined = {"met": 0, "partial": 0, "gap": 0}

    for article in scan_report.get("articles", []):
        controls_out = []
        for ctrl in article.get("controls", []):
            ctrl_id = ctrl.get("controlId", "")
            l1_status = ctrl.get("status", "gap")
            evidence_fn = ctrl.get("evidence_fn", "")

            # Layer 1: code analysis (from scan)
            l1 = _make_result(
                l1_status,
                ctrl.get("evidence", []),
                ctrl.get("gaps", []),
                ctrl.get("recommendation", ""),
            )

            # Layer 2: development process (enhanced with CI/CD data)
            l2_fn = _L2_FN_MAP.get(evidence_fn)
            if l2_fn and cicd_records:
                l2 = l2_fn(cicd_records, has_baseline, regression_detected, resolved_count)
            else:
                l2 = _l2_default(cicd_records or [], has_baseline, regression_detected, resolved_count)

            # Layer 3: traffic/governance
            l3_fn = _L3_FN_MAP.get(evidence_fn)
            if l3_fn and audit_records:
                l3 = l3_fn(audit_records, audit_summary)
            elif audit_records:
                l3 = _l3_monitoring(audit_records, audit_summary)
            else:
                l3 = _make_result("gap", [],
                                  ["No audit log data available — configure an adapter"],
                                  "Connect an audit log adapter for Layer 3 evidence")

            # Layer 4: active governance (optional, additive)
            l4 = None
            l4_fn = _L4_FN_MAP.get(evidence_fn)
            if l4_fn and has_l4:
                l4 = l4_fn(gov_decisions, gov_activity_summary)

            # Combined status: layer-aware synthesis
            # Layers 1-3 are always evaluated. Layer 4 contributes when available.
            # L4 can only improve or maintain status — never degrades.
            layer_statuses = [l1["status"], l2["status"], l3["status"]]
            met_count = sum(1 for s in layer_statuses if s == "met")
            gap_count = sum(1 for s in layer_statuses if s == "gap")

            if gap_count == 0 and met_count >= 2:
                combined_status = "met"
            elif gap_count >= 2:
                combined_status = "gap"
            elif met_count >= 2 and gap_count == 1:
                combined_status = "partial"
            else:
                combined_status = "partial"

            # L4 boost: if L4 is "met" and combined is "partial", allow upgrade
            # only when at least 2 of the 4 layers are "met"
            if l4 and l4["status"] == "met" and combined_status == "partial":
                all_statuses = layer_statuses + [l4["status"]]
                total_met = sum(1 for s in all_statuses if s == "met")
                total_gap = sum(1 for s in all_statuses if s == "gap")
                if total_met >= 3 and total_gap == 0:
                    combined_status = "met"

            total_combined[combined_status] = total_combined.get(combined_status, 0) + 1

            layers_dict = {
                "code": l1,
                "process": l2,
                "traffic": l3,
            }
            if l4 is not None:
                layers_dict["governance"] = l4

            controls_out.append({
                "controlId": ctrl_id,
                "combinedStatus": combined_status,
                "layers": layers_dict,
                "requirement": ctrl.get("requirement", ""),
                "recommendation": ctrl.get("recommendation", ""),
                "evidence_fn": evidence_fn,
            })

        articles_out.append({
            "articleId": article.get("articleId", ""),
            "label": article.get("label", ""),
            "controls": controls_out,
        })

    total_controls = sum(total_combined.values())
    combined_score = 0.0
    if total_controls > 0:
        combined_score = round(
            (total_combined["met"] + 0.5 * total_combined["partial"]) / total_controls * 100, 1
        )

    # CI/CD summary for the response
    cicd_summary = {}
    if cicd_records:
        cicd_types = set(r.get("metadata", {}).get("cicd_type", "") for r in cicd_records)
        cicd_types.discard("")
        cicd_summary = {
            "total_records": len(cicd_records),
            "event_types": sorted(cicd_types),
        }

    return {
        "framework": framework,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "combinedScore": combined_score,
        "summary": {
            "met": total_combined["met"],
            "partial": total_combined["partial"],
            "gap": total_combined["gap"],
            "total": total_controls,
            "score": combined_score,
        },
        "auditSummary": audit_summary,
        "cicdSummary": cicd_summary,
        "hasBaseline": has_baseline,
        "regressionDetected": regression_detected,
        "articles": articles_out,
    }
