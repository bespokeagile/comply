"""Graph-aware remediation generator (Level 3).

For each gap/partial control, queries the persisted codebase graph to produce
specific, file-path-aware remediation actions.  No LLM cost -- pure structure.
"""

import re
from typing import Dict, List, Optional


# ── Evidence function -> graph query strategy mapping ─────────────────

# Each key is an evidence_fn name from _EVIDENCE_FN_MAP in compliance_eval.py.
# The value describes what to search for in the codebase graph and what to suggest.
_STRATEGY_MAP = {
    "evidence_audit_logging": {
        "keywords": ["log", "audit", "trace", "record", "journal", "logging"],
        "import_hints": ["logging", "structlog", "loguru", "winston", "pino", "bunyan",
                         "log4j", "slf4j", "serilog", "zap", "zerolog"],
        "fn_hints": ["log", "audit", "record", "trace"],
        "gap_action": "Add structured audit logging for all AI operations.",
        "partial_action": "Expand audit logging to cover all system operations.",
        "create_hint": "logging/audit module",
    },
    "evidence_traceability": {
        "keywords": ["log", "audit", "trace", "traceability"],
        "import_hints": ["logging", "opentelemetry"],
        "fn_hints": ["trace", "log"],
        "gap_action": "Implement traceability logging for AI decision chains.",
        "partial_action": "Extend existing logging to capture full decision traces.",
        "create_hint": "traceability module",
    },
    "evidence_risk_assessment_gateway": {
        "keywords": ["risk", "safety", "hazard", "threat", "impact"],
        "import_hints": [],
        "fn_hints": ["risk", "safety", "assess"],
        "gap_action": "Create a risk assessment document referencing your validation pipeline.",
        "partial_action": "Formalize risk categories and connect to existing validation.",
        "create_hint": "docs/risk-assessment.md",
    },
    "evidence_risk_categorization": {
        "keywords": ["risk", "category", "classify", "tier", "level"],
        "import_hints": [],
        "fn_hints": ["risk", "categorize", "classify"],
        "gap_action": "Create risk categorization schema for AI system components.",
        "partial_action": "Complete risk categorization with formal severity levels.",
        "create_hint": "docs/risk-categories.md",
    },
    "evidence_risk_register_auto": {
        "keywords": ["risk", "register", "inventory"],
        "import_hints": [],
        "fn_hints": ["risk", "register"],
        "gap_action": "Create a risk register documenting identified risks and mitigations.",
        "partial_action": "Expand risk register with mitigation tracking.",
        "create_hint": "docs/risk-register.md",
    },
    "evidence_transparency_disclosure": {
        "keywords": ["readme", "doc", "disclosure", "transparency", "about", "license", "notice"],
        "import_hints": [],
        "fn_hints": [],
        "gap_action": "Create transparency documentation including system purpose and limitations.",
        "partial_action": "Add AI-specific disclosures to existing documentation.",
        "create_hint": "docs/ai-transparency.md",
    },
    "evidence_transparency_logging": {
        "keywords": ["readme", "doc", "disclosure", "transparency"],
        "import_hints": [],
        "fn_hints": [],
        "gap_action": "Document AI system transparency requirements.",
        "partial_action": "Expand transparency documentation.",
        "create_hint": "docs/transparency.md",
    },
    "evidence_continuous_monitoring": {
        "keywords": ["monitor", "metric", "health", "alert", "dashboard", "observ", "telemetry"],
        "import_hints": ["prometheus", "datadog", "newrelic", "sentry", "opentelemetry",
                         "statsd", "grafana"],
        "fn_hints": ["monitor", "health", "metric", "alert", "check"],
        "gap_action": "Implement continuous monitoring for AI system operations.",
        "partial_action": "Expand monitoring coverage to all AI-critical paths.",
        "create_hint": "monitoring module",
    },
    "evidence_performance_measurement": {
        "keywords": ["test", "spec", "assert", "expect", "benchmark", "perf"],
        "import_hints": ["pytest", "unittest", "jest", "mocha", "vitest", "junit"],
        "fn_hints": ["test", "assert", "validate", "benchmark"],
        "gap_action": "Implement testing procedures for AI system validation.",
        "partial_action": "Expand test coverage for comprehensive validation.",
        "create_hint": "tests/ directory",
    },
    "evidence_governance_policy": {
        "keywords": ["governance", "policy", "compliance", "standard", "procedure"],
        "import_hints": [],
        "fn_hints": ["govern", "policy", "comply"],
        "gap_action": "Create an AI governance policy document.",
        "partial_action": "Formalize governance procedures and assign accountability.",
        "create_hint": "docs/ai-governance-policy.md",
    },
    "evidence_logical_access": {
        "keywords": ["auth", "access", "permission", "role", "rbac", "acl", "login", "session"],
        "import_hints": ["passport", "bcrypt", "jsonwebtoken", "jwt", "oauth",
                         "authlib", "django.contrib.auth"],
        "fn_hints": ["auth", "login", "permission", "access", "role"],
        "gap_action": "Implement access control for AI system operations.",
        "partial_action": "Expand access controls to cover all AI endpoints.",
        "create_hint": "auth/access control module",
    },
    "evidence_data_handling": {
        "keywords": ["data", "privacy", "gdpr", "encrypt", "pii", "anonymize", "mask"],
        "import_hints": ["cryptography", "crypto", "bcrypt", "hashlib"],
        "fn_hints": ["encrypt", "anonymize", "mask", "sanitize", "hash"],
        "gap_action": "Implement data handling procedures for sensitive information.",
        "partial_action": "Expand data protection to cover all PII paths.",
        "create_hint": "data protection module",
    },
    "evidence_change_management": {
        "keywords": ["changelog", "version", "migration", "deploy", "release", "ci", "cd"],
        "import_hints": [],
        "fn_hints": ["migrate", "deploy", "release", "version"],
        "gap_action": "Implement change management procedures and maintain a changelog.",
        "partial_action": "Formalize change management with approval workflows.",
        "create_hint": "CHANGELOG.md",
    },
    "evidence_incident_response": {
        "keywords": ["incident", "alert", "escalat", "respond", "recover", "backup", "disaster"],
        "import_hints": ["sentry", "pagerduty", "opsgenie"],
        "fn_hints": ["incident", "alert", "escalate", "recover"],
        "gap_action": "Create an incident response plan for AI system failures.",
        "partial_action": "Expand incident response to cover AI-specific failure modes.",
        "create_hint": "docs/incident-response-plan.md",
    },
    "evidence_human_oversight_gateway": {
        "keywords": ["auth", "access", "approval", "review", "human", "manual", "override"],
        "import_hints": [],
        "fn_hints": ["approve", "review", "override", "human"],
        "gap_action": "Implement human oversight controls for AI decisions.",
        "partial_action": "Expand human-in-the-loop to cover high-risk decisions.",
        "create_hint": "human oversight module",
    },
    "evidence_ai_system_inventory": {
        "keywords": ["readme", "doc", "inventory", "registry", "catalog"],
        "import_hints": [],
        "fn_hints": [],
        "gap_action": "Create an AI system inventory documenting all AI components.",
        "partial_action": "Complete the AI system inventory with all components.",
        "create_hint": "docs/ai-system-inventory.md",
    },
    "evidence_impact_documentation": {
        "keywords": ["impact", "assessment", "evaluation", "bias", "fairness"],
        "import_hints": [],
        "fn_hints": ["impact", "assess", "evaluate", "bias"],
        "gap_action": "Create an impact assessment for AI system deployment.",
        "partial_action": "Complete impact assessment with stakeholder analysis.",
        "create_hint": "docs/impact-assessment.md",
    },
    "evidence_consumer_notification": {
        "keywords": ["notice", "notification", "consent", "disclosure", "terms"],
        "import_hints": [],
        "fn_hints": ["notify", "consent", "disclose"],
        "gap_action": "Implement consumer notification when AI is used in decisions.",
        "partial_action": "Expand consumer notification to all AI touchpoints.",
        "create_hint": "consumer notification module",
    },
    "evidence_availability_controls": {
        "keywords": ["monitor", "health", "uptime", "availability", "redundan", "failover"],
        "import_hints": ["prometheus", "datadog", "newrelic"],
        "fn_hints": ["health", "monitor", "failover"],
        "gap_action": "Implement availability monitoring and failover controls.",
        "partial_action": "Expand availability controls with automated failover.",
        "create_hint": "availability/health module",
    },
    "evidence_retention_compliance": {
        "keywords": ["retention", "archive", "purge", "lifecycle", "expire", "ttl"],
        "import_hints": [],
        "fn_hints": ["retain", "purge", "archive", "expire"],
        "gap_action": "Implement data retention policies for AI logs and records.",
        "partial_action": "Formalize retention periods and automate purging.",
        "create_hint": "docs/data-retention-policy.md",
    },
    "evidence_governance_program": {
        "keywords": ["governance", "program", "committee", "board", "oversight"],
        "import_hints": [],
        "fn_hints": [],
        "gap_action": "Establish a formal AI governance program.",
        "partial_action": "Expand governance program with defined roles and cadence.",
        "create_hint": "docs/governance-program.md",
    },
    "evidence_input_sanitization": {
        "keywords": ["sanitize", "validate", "filter", "escape", "input", "clean"],
        "import_hints": ["bleach", "validator", "sanitize", "dompurify", "xss"],
        "fn_hints": ["sanitize", "validate", "filter", "escape", "clean"],
        "gap_action": "Implement input sanitization for all AI model inputs.",
        "partial_action": "Expand input validation to cover all injection vectors.",
        "create_hint": "input sanitization module",
    },
    "evidence_output_validation": {
        "keywords": ["output", "validate", "filter", "sanitize", "response"],
        "import_hints": [],
        "fn_hints": ["validate_output", "filter_output", "sanitize_response"],
        "gap_action": "Implement output validation for AI model responses.",
        "partial_action": "Expand output validation to catch unsafe content.",
        "create_hint": "output validation module",
    },
    "evidence_model_provenance": {
        "keywords": ["model", "version", "provenance", "registry", "artifact", "mlflow"],
        "import_hints": ["mlflow", "wandb", "dvc", "huggingface"],
        "fn_hints": ["model", "version", "registry"],
        "gap_action": "Implement model provenance tracking for all AI models.",
        "partial_action": "Expand provenance tracking with full lineage.",
        "create_hint": "model registry/tracking",
    },
    "evidence_prompt_protection": {
        "keywords": ["prompt", "injection", "guard", "template", "sanitize"],
        "import_hints": ["guardrails", "nemo_guardrails", "rebuff"],
        "fn_hints": ["prompt", "guard", "inject", "template"],
        "gap_action": "Implement prompt injection protection for LLM inputs.",
        "partial_action": "Expand prompt protection with multi-layer guards.",
        "create_hint": "prompt security module",
    },
    "evidence_embedding_security": {
        "keywords": ["embedding", "vector", "index", "similarity", "search"],
        "import_hints": ["faiss", "pinecone", "chromadb", "weaviate", "qdrant", "pgvector"],
        "fn_hints": ["embed", "vector", "index", "search"],
        "gap_action": "Implement security controls for vector embeddings.",
        "partial_action": "Add access controls and poisoning detection for embeddings.",
        "create_hint": "embedding security controls",
    },
    "evidence_consumption_limits": {
        "keywords": ["rate", "limit", "throttle", "quota", "budget", "cost"],
        "import_hints": ["ratelimit", "throttle"],
        "fn_hints": ["rate_limit", "throttle", "quota", "budget"],
        "gap_action": "Implement consumption limits for AI API usage.",
        "partial_action": "Expand rate limiting with per-user quotas.",
        "create_hint": "rate limiting/quota module",
    },
    "evidence_access_control": {
        "keywords": ["auth", "access", "permission", "role", "rbac", "acl"],
        "import_hints": ["passport", "bcrypt", "jsonwebtoken", "jwt", "oauth"],
        "fn_hints": ["auth", "login", "permission", "access", "role"],
        "gap_action": "Implement access control for AI system endpoints.",
        "partial_action": "Expand RBAC to cover all AI operations.",
        "create_hint": "access control module",
    },
    "evidence_mcp_server_security": {
        "keywords": ["mcp", "server", "tool", "capability", "sandbox"],
        "import_hints": ["mcp"],
        "fn_hints": ["mcp", "tool", "capability"],
        "gap_action": "Implement security controls for MCP server integrations.",
        "partial_action": "Add capability restrictions and sandboxing for MCP tools.",
        "create_hint": "MCP security module",
    },
    "evidence_ai_supply_chain": {
        "keywords": ["supply", "chain", "dependency", "sbom", "vendor", "third-party"],
        "import_hints": [],
        "fn_hints": [],
        "gap_action": "Create an AI supply chain inventory (SBOM) for all AI dependencies.",
        "partial_action": "Expand SBOM to cover all transitive AI dependencies.",
        "create_hint": "docs/ai-sbom.md",
    },
}


def generate_remediations(articles: List[Dict], codebase_graph: Dict,
                          framework: str,
                          summary: Optional[Dict] = None) -> List[Dict]:
    """For each gap/partial control, produce a graph-aware remediation.

    Returns a list of remediation dicts sorted by (effort ASC, impact DESC),
    each annotated with score_delta and projected_score_after.

    Args:
        articles: List of article dicts with controls.
        codebase_graph: Codebase model graph dict.
        framework: Framework ID.
        summary: Report summary dict with met/partial/gap/total/score counts.
    """
    if not codebase_graph or not codebase_graph.get("files"):
        return []

    files = codebase_graph.get("files", [])
    relationships = codebase_graph.get("relationships", [])
    dependencies = codebase_graph.get("dependencies", [])

    # Build lookup indices
    file_by_path = {f["path"]: f for f in files}
    files_by_lang = {}
    for f in files:
        lang = f.get("language", "other")
        files_by_lang.setdefault(lang, []).append(f)

    # Collect all gap/partial controls
    gap_controls = []
    for art in articles:
        for ctrl in art.get("controls", []):
            status = ctrl.get("status", "gap")
            if status in ("gap", "partial"):
                gap_controls.append({
                    **ctrl,
                    "articleId": art.get("articleId", ""),
                    "articleLabel": art.get("label", ""),
                })

    if not gap_controls:
        return []

    remediations = []
    for ctrl in gap_controls:
        rem = _remediate_control(ctrl, files, relationships, dependencies,
                                 files_by_lang, framework)
        if rem:
            remediations.append(rem)

    # Add score projections (needs to run before priority scoring)
    _add_score_projections(remediations, summary)

    # Sort by priority: highest score-per-effort first
    _sort_by_priority(remediations)

    return remediations


def _add_score_projections(remediations: List[Dict],
                           summary: Optional[Dict] = None):
    """Annotate each remediation with score_delta and projected_score_after.

    score_delta: how much fixing this single item would improve the score.
    projected_score_after: cumulative score if all items up to and including
    this one are fixed (in the current sort order).

    Fixing a gap control -> met adds 1.0 to the numerator.
    Fixing a partial control -> met adds 0.5 to the numerator.
    Score formula: (met + 0.5 * partial) / total * 100.
    """
    if not summary:
        # No summary available -- set zeros and return
        for rem in remediations:
            rem["score_delta"] = 0
            rem["projected_score_after"] = 0
            rem["current_status"] = rem.get("current_status", "gap")
        return

    total = summary.get("total", 0)
    if total == 0:
        for rem in remediations:
            rem["score_delta"] = 0
            rem["projected_score_after"] = 0
        return

    current_score = summary.get("score", 0)

    # Calculate per-item delta based on current control status
    # gap -> met: adds 1.0 to numerator = +100/total points
    # partial -> met: adds 0.5 to numerator = +50/total points
    cumulative_score = current_score
    for rem in remediations:
        status = rem.get("current_status", "gap")
        if status == "gap":
            delta = round(100.0 / total, 1)
        elif status == "partial":
            delta = round(50.0 / total, 1)
        else:
            delta = 0

        rem["score_delta"] = delta
        cumulative_score = min(100.0, round(cumulative_score + delta, 1))
        rem["projected_score_after"] = cumulative_score


# Relative effort hours for priority scoring
_EFFORT_HOURS = {"low": 1, "medium": 4, "high": 16}


def _sort_by_priority(remediations: List[Dict]):
    """Sort by priority score: score_delta * impact / effort_hours.

    Higher priority = more score improvement per hour of work.
    After sorting, recalculate cumulative projected_score_after and
    annotate each item with its priority_score.
    """
    for rem in remediations:
        delta = rem.get("score_delta", 0)
        impact = rem.get("impact", 1)
        hours = _EFFORT_HOURS.get(rem.get("effort", "medium"), 4)
        rem["priority_score"] = round(delta * impact / hours, 2)

    remediations.sort(key=lambda r: -r["priority_score"])

    # Recalculate cumulative projections in new order
    if remediations and remediations[0].get("projected_score_after", 0) > 0:
        # Recover base score: first item's projected - first item's delta
        base = remediations[0]["projected_score_after"] - remediations[0]["score_delta"]
        # But that only works if the original order's first item is still first.
        # Safer: recompute from scratch using any item's delta sum.
        total_delta = sum(r.get("score_delta", 0) for r in remediations)
        last_projected = remediations[-1].get("projected_score_after", 0) if remediations else 0
        # base_score = last_projected - total_delta (but capped)
        # More robust: use the projected_score_after and score_delta to find base
        base_score = round(last_projected - total_delta, 1)
        if base_score < 0:
            base_score = 0

        cumulative = base_score
        for rem in remediations:
            cumulative = min(100.0, round(cumulative + rem.get("score_delta", 0), 1))
            rem["projected_score_after"] = cumulative


def _remediate_control(ctrl: Dict, files: List[Dict],
                       relationships: List[Dict], dependencies: List[Dict],
                       files_by_lang: Dict, framework: str) -> Optional[Dict]:
    """Produce a single remediation for a gap/partial control."""
    evidence_fn = ctrl.get("evidence_fn", "")
    status = ctrl.get("status", "gap")
    strategy = _STRATEGY_MAP.get(evidence_fn)

    if not strategy:
        # Fallback: generic remediation from the control's own recommendation
        rec = ctrl.get("recommendation", "")
        if not rec:
            return None
        return {
            "controlId": ctrl.get("controlId", ""),
            "articleId": ctrl.get("articleId", ""),
            "current_status": status,
            "level": 3,
            "evidence_fn": evidence_fn,
            "summary": rec,
            "action": rec,
            "relatedFiles": [],
            "missingConnection": "",
            "effort": "medium",
            "impact": 1,
        }

    # Find related files using strategy keywords
    related = _find_related_files(files, strategy["keywords"],
                                  strategy["import_hints"], strategy["fn_hints"])

    # Determine effort and build action
    if status == "partial":
        action = strategy["partial_action"]
        effort = "low" if related else "medium"
    else:
        action = strategy["gap_action"]
        effort = "medium" if not related else "low"

    # Build summary with file context
    related_paths = [f["path"] for f in related[:5]]
    if related and status == "gap":
        summary = (f"Your codebase has related infrastructure in "
                   f"{_describe_files(related[:3])} but lacks explicit "
                   f"{_describe_gap(strategy)}.")
        effort = "low"
    elif related and status == "partial":
        summary = (f"Found {len(related)} related file(s) "
                   f"({', '.join(related_paths[:2])}). "
                   f"Expand to fully satisfy this control.")
        effort = "low"
    else:
        summary = f"No existing {_describe_gap(strategy)} found. {strategy['create_hint']} needed."
        effort = "medium" if status == "gap" else "low"

    # Find missing connections (files that should reference each other)
    missing_conn = _find_missing_connection(related, relationships, strategy)

    # Count how many other controls this evidence_fn serves
    impact = _count_impact(evidence_fn)

    return {
        "controlId": ctrl.get("controlId", ""),
        "articleId": ctrl.get("articleId", ""),
        "current_status": status,
        "level": 3,
        "evidence_fn": evidence_fn,
        "summary": summary,
        "action": action,
        "relatedFiles": related_paths,
        "missingConnection": missing_conn,
        "effort": effort,
        "impact": impact,
    }


def _find_related_files(files: List[Dict], keywords: List[str],
                        import_hints: List[str], fn_hints: List[str]) -> List[Dict]:
    """Find files related to a remediation strategy."""
    scored = []
    for f in files:
        score = 0
        path_lower = f.get("path", "").lower()

        # Keyword match in path
        for kw in keywords:
            if kw in path_lower:
                score += 2
                break

        # Import match
        for imp in f.get("imports", []):
            imp_lower = imp.lower().replace("-", "_")
            for hint in import_hints:
                if hint in imp_lower:
                    score += 1
                    break

        # Function name match
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            fn_tokens = set(re.split(r'[_\s]+', fn_lower))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            for hint in fn_hints:
                if hint in fn_tokens:
                    score += 1
                    break

        # Class name match
        for cls in f.get("classes", []):
            cls_lower = cls.lower()
            for kw in keywords[:3]:
                if kw in cls_lower:
                    score += 1
                    break

        if score > 0:
            scored.append((score, f))

    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:5]]


def _find_missing_connection(related: List[Dict], relationships: List[Dict],
                             strategy: Dict) -> str:
    """Identify a missing connection between related files."""
    if len(related) < 2:
        return ""

    # Build a set of existing connections
    connected = set()
    for rel in relationships:
        connected.add((rel.get("from", ""), rel.get("to", "")))

    # Check if the top related files are connected
    top_paths = [f["path"] for f in related[:3]]
    for i, p1 in enumerate(top_paths):
        for p2 in top_paths[i + 1:]:
            if (p1, p2) not in connected and (p2, p1) not in connected:
                return f"{p1} <-> {p2}"

    return ""


def _describe_files(files: List[Dict]) -> str:
    """Describe a short list of files for a summary string."""
    paths = [f["path"] for f in files]
    if len(paths) == 1:
        return paths[0]
    if len(paths) == 2:
        return f"{paths[0]} and {paths[1]}"
    return f"{paths[0]}, {paths[1]}, and {len(paths) - 2} more"


def _describe_gap(strategy: Dict) -> str:
    """Describe what's missing based on the strategy's create_hint."""
    hint = strategy.get("create_hint", "")
    if hint:
        return hint
    return "required documentation"


# Map evidence_fn -> count of controls it serves (across typical frameworks)
_EVIDENCE_FN_IMPACT = {
    "evidence_audit_logging": 3,
    "evidence_traceability": 2,
    "evidence_risk_assessment_gateway": 3,
    "evidence_risk_categorization": 2,
    "evidence_risk_register_auto": 2,
    "evidence_transparency_disclosure": 2,
    "evidence_transparency_logging": 1,
    "evidence_continuous_monitoring": 2,
    "evidence_performance_measurement": 2,
    "evidence_governance_policy": 2,
    "evidence_logical_access": 2,
    "evidence_data_handling": 2,
    "evidence_change_management": 1,
    "evidence_incident_response": 1,
    "evidence_human_oversight_gateway": 2,
    "evidence_ai_system_inventory": 1,
    "evidence_impact_documentation": 2,
    "evidence_consumer_notification": 2,
    "evidence_availability_controls": 1,
    "evidence_retention_compliance": 1,
    "evidence_governance_program": 2,
    "evidence_input_sanitization": 1,
    "evidence_output_validation": 1,
    "evidence_model_provenance": 1,
    "evidence_prompt_protection": 1,
    "evidence_embedding_security": 1,
    "evidence_consumption_limits": 1,
    "evidence_access_control": 2,
    "evidence_mcp_server_security": 1,
    "evidence_ai_supply_chain": 1,
}


def _count_impact(evidence_fn: str) -> int:
    """How many controls does addressing this evidence function typically fix?"""
    return _EVIDENCE_FN_IMPACT.get(evidence_fn, 1)
