"""Dict-based compliance evaluation — no Kuzu dependency.

Evaluates a CodebaseModel dict (from codebase_scanner) against framework
controls defined in frameworks.yaml.  Returns the same report structure as
the monorepo's _evaluate_compliance() + _generate_report().
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from comply._vendor.framework_loader import get_framework, get_supported_frameworks

log = logging.getLogger(__name__)


def evaluate_compliance(
    framework_id: str,
    codebase_model: Dict[str, Any],
    semantic: bool = False,
    llm_provider: str = "anthropic",
    llm_api_key: str = "",
    llm_model: str = "",
) -> Dict[str, Any]:
    """Evaluate a codebase model against a compliance framework.

    Parameters
    ----------
    framework_id : str
        Framework ID (e.g. "eu_ai_act", "eu-ai-act").
    codebase_model : dict
        Output from codebase_scanner.scan_codebase().

    Returns
    -------
    dict
        Compliance status with articles/controls/evidence structure.
    """
    normalised = framework_id.replace("-", "_")
    fw = get_framework(normalised)
    if fw is None:
        supported = get_supported_frameworks()
        raise ValueError(f"Unknown framework '{framework_id}'. Supported: {supported}")

    # Compute graph metrics once for graph-aware file selection in semantic scans
    _graph_metrics_cache = {}
    if semantic and llm_api_key:
        try:
            from comply._vendor.graph_ranking import compute_graph_metrics
            _graph_metrics_cache = compute_graph_metrics(codebase_model)
        except Exception:
            pass  # Graceful fallback: keyword-only selection

    articles_out = []
    corrections = []  # M.2: semantic-to-structure correction log
    total_met = 0
    total_partial = 0
    total_gap = 0

    for art_key, art_data in fw.get("articles", {}).items():
        controls_out = []
        art_met = 0
        art_partial = 0
        art_gap = 0

        for ctrl in art_data.get("controls", []):
            ctrl_id = ctrl.get("id", "")
            requirement = ctrl.get("requirement", "")
            evidence_fn = ctrl.get("evidence_fn", "")

            # Evaluate this control
            result = _evaluate_control(evidence_fn, requirement, codebase_model)
            structure_status = result["status"]

            # Semantic enrichment: if enabled and control has gaps, use LLM
            if semantic and llm_api_key and result["status"] != "met":
                semantic_result = _semantic_evaluate_control(
                    ctrl_id, requirement, evidence_fn, codebase_model,
                    provider=llm_provider, api_key=llm_api_key, llm_model=llm_model,
                    graph_metrics=_graph_metrics_cache,
                )
                if semantic_result:
                    # Merge semantic evidence
                    result["evidence"].extend(semantic_result.get("evidence", []))
                    if semantic_result.get("status") == "met" and result["status"] == "gap":
                        result["status"] = "partial"
                    elif semantic_result.get("status") == "met":
                        result["status"] = "met"
                    result["semanticAnalysis"] = semantic_result.get("analysis", "")

                    # M.2: Log correction when semantic changes structure status
                    if result["status"] != structure_status:
                        semantic_evidence = semantic_result.get("evidence", [])
                        corrections.append({
                            "controlId": ctrl_id,
                            "evidence_fn": evidence_fn,
                            "structure_status": structure_status,
                            "semantic_status": result["status"],
                            "structure_evidence_count": len(result["evidence"]) - len(semantic_evidence),
                            "semantic_evidence_count": len(semantic_evidence),
                            "semantic_evidence": semantic_evidence[:5],
                        })

            controls_out.append({
                "controlId": ctrl_id,
                "status": result["status"],
                "requirement": requirement,
                "recommendation": result.get("recommendation", ""),
                "evidence": result.get("evidence", []),
                "gaps": result.get("gaps", []),
                "evidence_fn": evidence_fn,
            })

            if result["status"] == "met":
                art_met += 1
            elif result["status"] == "partial":
                art_partial += 1
            else:
                art_gap += 1

        articles_out.append({
            "articleId": art_key.split("_")[-1] if "_" in art_key else art_key,
            "label": art_data.get("label", art_key),
            "met": art_met,
            "partial": art_partial,
            "gap": art_gap,
            "controls": controls_out,
        })

        total_met += art_met
        total_partial += art_partial
        total_gap += art_gap

    total = total_met + total_partial + total_gap
    score = round((total_met + 0.5 * total_partial) / total * 100, 1) if total > 0 else 0.0

    result = {
        "framework": framework_id,
        "summary": {
            "met": total_met,
            "partial": total_partial,
            "gap": total_gap,
            "total": total,
            "score": score,
        },
        "articles": articles_out,
    }

    # M.2: Include correction log when semantic scan corrected structure findings
    if corrections:
        result["corrections"] = corrections
        log.info("M.2 correction loop: %d controls upgraded by semantic analysis", len(corrections))

    return result


def _evaluate_control(
    evidence_fn: str,
    requirement: str,
    model: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate a single control against the codebase model."""
    evaluator = _EVIDENCE_FN_MAP.get(evidence_fn, _evidence_default)
    return evaluator(requirement, model)


# ── Evidence evaluator functions ─────────────────────────────────────

def _make(status: str, evidence: List[str], gaps: Optional[List[str]] = None,
          recommendation: str = "", file_evidence: Optional[List[Dict]] = None) -> Dict[str, Any]:
    result = {"status": status, "evidence": evidence, "gaps": gaps or [], "recommendation": recommendation}
    if file_evidence:
        result["fileEvidence"] = file_evidence
    return result


def _file_evidence(path: str, reason: str, line: Optional[int] = None) -> Dict[str, Any]:
    """Create a structured file-level evidence entry."""
    entry = {"path": path, "reason": reason}
    if line:
        entry["line"] = line
    return entry


def _detect_imports(files: List[Dict], package_names: List[str]) -> List[str]:
    """Search file imports for known package names.

    Returns a list of matched package names found across all files.
    """
    found = set()
    for f in files:
        for imp in f.get("imports", []):
            imp_lower = imp.lower().replace("-", "_")
            for pkg in package_names:
                if pkg in imp_lower:
                    found.add(pkg)
    return sorted(found)


def _count_files_importing(files: List[Dict], package_names: List[str]) -> int:
    """Count how many files import any of the given packages."""
    count = 0
    for f in files:
        for imp in f.get("imports", []):
            imp_lower = imp.lower().replace("-", "_")
            if any(pkg in imp_lower for pkg in package_names):
                count += 1
                break
    return count


def _evidence_audit_logging(req: str, model: Dict) -> Dict:
    """Check for logging, audit trail, record-keeping evidence."""
    files = model.get("files", [])
    log_files = [f for f in files if _file_has_keywords(f, ["log", "audit", "trace", "record", "journal", "logging"])]

    # Also detect logging frameworks by imports
    _logging_packages = [
        "logging", "structlog", "loguru", "winston", "pino", "bunyan",
        "log4j", "slf4j", "serilog", "nlog", "zap", "zerolog",
        "spdlog", "log4net", "monolog",
    ]
    logging_imports = _detect_imports(files, _logging_packages)

    # Count files that import logging frameworks (even without "log" in path)
    files_importing_logging = _count_files_importing(files, _logging_packages)

    log_fns = []
    for f in files:
        fns = f.get("functions", [])
        fn_kws = ["log", "audit", "record", "trace"]
        for fn in fns:
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in fn_kws):
                log_fns.append(fn)

    # Use the higher of keyword-matched files or import-matched files
    effective_file_count = max(len(log_files), files_importing_logging)
    total_signals = effective_file_count + len(logging_imports) + (1 if log_fns else 0)
    evidence = []
    file_ev = []
    if effective_file_count > 0:
        evidence.append(f"{effective_file_count} files with logging/audit functionality")
        for f in log_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Contains logging/audit infrastructure"))
    if logging_imports:
        evidence.append(f"Logging frameworks detected: {', '.join(logging_imports[:3])}")
    if log_fns:
        evidence.append(f"Functions: {', '.join(log_fns[:5])}")

    if total_signals >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total_signals >= 1:
        return _make("partial", evidence,
                      ["Audit logging may not be comprehensive"],
                      "Expand audit logging to cover all system operations",
                      file_evidence=file_ev)
    return _make("gap", [], ["No audit logging infrastructure found"],
                 "Implement comprehensive audit logging for AI operations")


def _evidence_risk_assessment(req: str, model: Dict) -> Dict:
    """Check for risk assessment / management evidence."""
    files = model.get("files", [])
    risk_files = [f for f in files if _file_has_keywords(f, ["risk", "safety", "hazard", "threat", "impact"])]
    features = model.get("features", [])
    risk_features = [f for f in features if any(k in f.get("label", "").lower() for k in ["risk", "safety"])]

    if risk_files or risk_features:
        evidence = []
        if risk_files:
            evidence.append(f"{len(risk_files)} file(s) addressing risk management")
        if risk_features:
            evidence.append(f"Risk-related features: {', '.join(f['label'] for f in risk_features[:3])}")
        return _make("partial" if len(risk_files) < 2 else "met", evidence,
                      ["Formal risk assessment documentation may be incomplete"] if len(risk_files) < 2 else [],
                      "Document formal risk assessment procedures")
    return _make("gap", [], ["No risk assessment documentation found"],
                 "Create and maintain a risk management system")


def _evidence_transparency(req: str, model: Dict) -> Dict:
    """Check for transparency / disclosure evidence."""
    files = model.get("files", [])
    trans_files = [f for f in files if _file_has_keywords(f,
                   ["readme", "doc", "disclosure", "transparency", "about", "license", "notice"])]
    readme_exists = any(f["path"].lower().startswith("readme") for f in files)

    if trans_files and readme_exists:
        return _make("met", [
            f"{len(trans_files)} documentation/transparency files",
            "README present with project documentation",
        ])
    elif trans_files or readme_exists:
        return _make("partial",
                      ["Some documentation exists"],
                      ["Transparency documentation may be incomplete"],
                      "Add comprehensive transparency documentation")
    return _make("gap", [], ["No transparency documentation found"],
                 "Create transparency documentation including system purpose and limitations")


def _evidence_monitoring(req: str, model: Dict) -> Dict:
    """Check for monitoring / observability evidence."""
    files = model.get("files", [])
    mon_files = [f for f in files if _file_has_keywords(f,
                 ["monitor", "metric", "health", "alert", "dashboard", "observ",
                  "telemetry", "status", "diagnos", "watch", "probe"])]

    # Detect monitoring frameworks by imports (including ML experiment trackers)
    _mon_packages = [
        "prometheus", "datadog", "newrelic", "sentry", "opentelemetry",
        "statsd", "grafana", "elastic", "cloudwatch",
        "wandb", "aim", "comet_ml", "neptune", "ray.tune", "mlflow",
    ]
    mon_imports = _detect_imports(files, _mon_packages)

    # Count files importing monitoring frameworks
    files_importing_mon = _count_files_importing(files, _mon_packages)

    mon_fns = []
    for f in files:
        fns = f.get("functions", [])
        fn_kws = ["monitor", "health", "metric", "alert", "check",
                   "validate", "diagnose", "probe", "watch"]
        for fn in fns:
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in fn_kws):
                mon_fns.append(fn)

    evidence = []
    effective_file_count = max(len(mon_files), files_importing_mon)
    if effective_file_count > 0:
        evidence.append(f"{effective_file_count} monitoring/observability files")
    if mon_imports:
        evidence.append(f"Monitoring frameworks: {', '.join(mon_imports[:3])}")
    if mon_fns:
        evidence.append(f"Functions: {', '.join(mon_fns[:5])}")

    total_signals = effective_file_count + len(mon_imports) + (1 if mon_fns else 0)
    if total_signals >= 2:
        return _make("met", evidence)
    elif total_signals >= 1:
        return _make("partial", evidence,
                      ["Monitoring coverage may be limited"],
                      "Expand monitoring to cover all AI system operations")
    return _make("gap", [], ["No monitoring infrastructure found"],
                 "Implement continuous monitoring for AI systems")


def _evidence_testing(req: str, model: Dict) -> Dict:
    """Check for testing evidence."""
    files = model.get("files", [])
    test_files = [f for f in files if f.get("has_tests") or _is_test_file(f["path"])]
    total_tests = sum(f.get("test_count", 0) for f in test_files)

    # Also detect test frameworks by imports
    test_imports = _detect_imports(files, [
        "pytest", "unittest", "jest", "mocha", "jasmine", "vitest",
        "junit", "testng", "rspec", "minitest", "phpunit", "nunit",
        "xunit", "testing",  # Go testing package
    ])

    evidence = []
    file_ev = []
    if test_files:
        evidence.append(f"{len(test_files)} test files with {total_tests} test cases")
        for f in test_files[:5]:
            count = f.get("test_count", 0)
            file_ev.append(_file_evidence(f["path"], f"{count} test case(s)" if count else "Test file"))
    if test_imports:
        evidence.append(f"Test frameworks: {', '.join(test_imports[:3])}")

    # Substantial test infrastructure: 10+ cases, or files+imports, or 50+ test files
    if total_tests >= 10 or (test_files and test_imports) or len(test_files) >= 50:
        return _make("met", evidence, file_evidence=file_ev)
    elif test_files or test_imports:
        return _make("partial", evidence,
                      ["Test coverage may be insufficient"],
                      "Expand test coverage for comprehensive validation",
                      file_evidence=file_ev)
    return _make("gap", [], ["No test infrastructure found"],
                 "Implement testing procedures for AI system validation")


def _is_test_file(path: str) -> bool:
    """Check if a path looks like a test file (not just contains 'test' anywhere)."""
    lower = path.lower()
    base = lower.rsplit("/", 1)[-1]
    # Common test file patterns
    if base.startswith("test_") or base.startswith("test."):
        return True
    if base.endswith("_test.py") or base.endswith("_test.go") or base.endswith("_test.js"):
        return True
    if base.endswith(".test.js") or base.endswith(".test.ts") or base.endswith(".test.tsx"):
        return True
    if base.endswith(".spec.js") or base.endswith(".spec.ts") or base.endswith(".spec.tsx"):
        return True
    if base.endswith("test.java") or base.endswith("tests.py"):
        return True
    # Check for test directories
    parts = lower.split("/")
    return any(p in ("tests", "test", "__tests__", "spec", "specs") for p in parts)


def _evidence_governance(req: str, model: Dict) -> Dict:
    """Check for governance / policy evidence."""
    files = model.get("files", [])
    gov_files = [f for f in files if _file_has_keywords(f,
                 ["policy", "governance", "compliance", "govern", "rule", "regulation"])]
    config_files = [f for f in files if f.get("is_config")]

    if gov_files:
        return _make("met" if len(gov_files) >= 2 else "partial", [
            f"{len(gov_files)} governance/policy file(s)",
            f"{len(config_files)} configuration files" if config_files else "",
        ])
    return _make("gap", [], ["No governance documentation found"],
                 "Establish AI governance policies and documentation")


def _evidence_access_control(req: str, model: Dict) -> Dict:
    """Check for access control / authentication evidence."""
    files = model.get("files", [])
    auth_files = [f for f in files if _file_has_keywords(f,
                  ["auth", "permission", "rbac", "security", "login", "oauth", "jwt",
                   "credential", "token", "verify"])]

    # Detect auth libraries by imports (including cloud provider auth)
    _auth_packages = [
        "passport", "jwt", "jsonwebtoken", "bcrypt", "argon2",
        "flask_login", "django.contrib.auth", "authlib", "oauth",
        "fastapi.security", "spring.security", "devise",
        "guardian", "casbin", "keycloak",
        "boto3", "azure.identity", "google.auth", "google.oauth2",
    ]
    auth_imports = _detect_imports(files, _auth_packages)

    # Count files importing auth libraries
    files_importing_auth = _count_files_importing(files, _auth_packages)

    auth_fns = []
    for f in files:
        fns = f.get("functions", [])
        fn_kws = ["auth", "login", "permission", "check_role", "verify",
                   "authenticate", "credential", "token", "authorize"]
        for fn in fns:
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in fn_kws):
                auth_fns.append(fn)

    evidence = []
    file_ev = []
    effective_file_count = max(len(auth_files), files_importing_auth)
    if effective_file_count > 0:
        evidence.append(f"{effective_file_count} access control files")
        for f in auth_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Access control/authentication"))
    if auth_imports:
        evidence.append(f"Auth libraries: {', '.join(auth_imports[:3])}")
    if auth_fns:
        evidence.append(f"Auth functions: {', '.join(auth_fns[:5])}")

    total_signals = effective_file_count + len(auth_imports) + (1 if auth_fns else 0)
    if total_signals >= 2:
        return _make("met", evidence, file_evidence=file_ev)
    elif total_signals >= 1:
        return _make("partial", evidence,
                      ["Access control implementation may be incomplete"],
                      "Implement comprehensive role-based access controls",
                      file_evidence=file_ev)
    return _make("gap", [], ["No access control infrastructure found"],
                 "Implement access controls for AI system resources")


def _evidence_data_handling(req: str, model: Dict) -> Dict:
    """Check for data handling / privacy evidence."""
    files = model.get("files", [])
    # Use specific privacy/security terms — avoid generic "data" which matches data fixtures
    privacy_files = [f for f in files if _file_has_keywords(f,
                     ["privacy", "gdpr", "encrypt", "sanitize", "confidential", "pii",
                      "anonymize", "redact", "consent", "retention"])]

    # Detect data handling libraries
    data_imports = _detect_imports(files, [
        "cryptography", "bcrypt", "hashlib", "hmac", "pycryptodome",
        "crypto", "sodium", "gpg", "pgp",
    ])

    # Check for data handling classes/functions more specifically
    data_fns = []
    for f in files:
        fns = f.get("functions", [])
        fn_kws = ["encrypt", "decrypt", "hash", "sanitize", "redact", "anonymize", "mask", "consent"]
        for fn in fns:
            fn_lower = fn.lower()
            if any(k in fn_lower for k in fn_kws):
                data_fns.append(fn)

    evidence = []
    if privacy_files:
        evidence.append(f"{len(privacy_files)} data handling/privacy file(s)")
    if data_imports:
        evidence.append(f"Crypto/privacy libraries: {', '.join(data_imports[:3])}")
    if data_fns:
        evidence.append(f"Data handling functions: {', '.join(data_fns[:5])}")

    total_signals = len(privacy_files) + len(data_imports) + (1 if data_fns else 0)
    if total_signals >= 2:
        return _make("met", evidence)
    elif total_signals >= 1:
        return _make("partial", evidence,
                      ["Data handling controls may be incomplete"],
                      "Implement comprehensive data handling and privacy controls")
    return _make("gap", [], ["No data handling documentation found"],
                 "Implement data handling and privacy controls")


def _evidence_change_management(req: str, model: Dict) -> Dict:
    """Check for change management evidence."""
    files = model.get("files", [])
    cm_files = [f for f in files if _file_has_keywords(f,
                ["changelog", "migration", "deploy", "pipeline"])]

    # Detect CI/CD configuration files by path patterns
    ci_patterns = [
        ".github/workflows/", ".gitlab-ci.yml", "jenkinsfile",
        ".circleci/config.yml", ".travis.yml", "azure-pipelines.yml",
        "bitbucket-pipelines.yml", ".drone.yml", "cloudbuild.yaml",
        "appveyor.yml", "Makefile", "Taskfile",
    ]
    ci_files = [f for f in files if any(
        pat in f["path"].lower() for pat in ci_patterns
    )]

    # Detect version control patterns
    version_files = [f for f in files if _file_has_keywords(f, ["version", "changelog"])]

    evidence = []
    if cm_files:
        evidence.append(f"{len(cm_files)} change management file(s)")
    if ci_files:
        ci_paths = [f["path"] for f in ci_files[:3]]
        evidence.append(f"CI/CD config: {', '.join(ci_paths)}")
    if version_files:
        evidence.append(f"{len(version_files)} versioning file(s)")

    total_signals = (1 if cm_files else 0) + (1 if ci_files else 0) + (1 if version_files else 0)
    if total_signals >= 2:
        return _make("met", evidence)
    elif total_signals >= 1:
        return _make("partial", evidence,
                      ["Change management may not cover all aspects"],
                      "Ensure all AI system changes go through documented approval process")
    return _make("gap", [], ["No change management infrastructure found"],
                 "Implement change management procedures with approval workflows")


def _evidence_incident_response(req: str, model: Dict) -> Dict:
    """Check for incident response evidence."""
    files = model.get("files", [])
    ir_files = [f for f in files if _file_has_keywords(f,
                ["incident", "response", "escalat", "remediat", "rollback", "recovery"])]

    if ir_files:
        return _make("partial", [f"{len(ir_files)} incident-related file(s)"],
                      ["Formal incident response plan may not be documented"],
                      "Document formal incident response procedures for AI system failures")
    return _make("gap", [], ["No incident response documentation found"],
                 "Create incident response procedures with escalation paths")


def _evidence_impact_assessment(req: str, model: Dict) -> Dict:
    """Check for AI impact assessment documentation (Colorado SB 24-205)."""
    files = model.get("files", [])
    impact_files = [f for f in files if _file_has_keywords(f,
                    ["impact", "assessment", "pia", "dpia", "aia"])]
    risk_docs = [f for f in files if _file_has_keywords(f, ["risk", "hazard", "limitation"])]

    evidence = []
    file_ev = []
    if impact_files:
        evidence.append(f"{len(impact_files)} impact assessment file(s)")
        for f in impact_files[:3]:
            file_ev.append(_file_evidence(f["path"], "Impact assessment documentation"))
    if risk_docs:
        evidence.append(f"{len(risk_docs)} risk/limitation documentation file(s)")

    total = len(impact_files) + len(risk_docs)
    if total >= 2:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Impact assessment may not cover all required areas (purpose, use, foreseeable risks)"],
                      "Complete impact assessment covering purpose, intended use, and foreseeable risks",
                      file_evidence=file_ev)
    return _make("gap", [], ["No impact assessment documentation found"],
                 "Create impact assessment for each high-risk AI system per Colorado SB 24-205")


def _evidence_consumer_notice(req: str, model: Dict) -> Dict:
    """Check for consumer notification mechanisms (Colorado SB 24-205)."""
    files = model.get("files", [])
    notice_files = [f for f in files if _file_has_keywords(f,
                    ["notice", "notification", "disclosure", "consent", "inform"])]
    # Look for UI notification patterns
    notice_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            if any(k in fn_lower for k in ["notify", "disclose", "inform", "consent", "notice"]):
                notice_fns.append(fn)

    evidence = []
    file_ev = []
    if notice_files:
        evidence.append(f"{len(notice_files)} notification/disclosure file(s)")
        for f in notice_files[:3]:
            file_ev.append(_file_evidence(f["path"], "Consumer notification mechanism"))
    if notice_fns:
        evidence.append(f"Notification functions: {', '.join(notice_fns[:5])}")

    total = len(notice_files) + (1 if notice_fns else 0)
    if total >= 2:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Consumer notification may not cover all AI-assisted decisions"],
                      "Implement notice when consequential decisions are made by AI",
                      file_evidence=file_ev)
    return _make("gap", [], ["No consumer notification mechanism found"],
                 "Implement consumer notification for AI-assisted consequential decisions")


def _evidence_governance_program(req: str, model: Dict) -> Dict:
    """Check for governance program with risk management and accountability (Colorado)."""
    files = model.get("files", [])
    gov_files = [f for f in files if _file_has_keywords(f,
                 ["governance", "policy", "compliance", "accountab", "oversight"])]
    risk_files = [f for f in files if _file_has_keywords(f, ["risk", "management"])]
    config_files = [f for f in files if f.get("is_config")]

    evidence = []
    file_ev = []
    if gov_files:
        evidence.append(f"{len(gov_files)} governance/policy file(s)")
        for f in gov_files[:3]:
            file_ev.append(_file_evidence(f["path"], "Governance program component"))
    if risk_files:
        evidence.append(f"{len(risk_files)} risk management file(s)")
    if config_files:
        evidence.append(f"{len(config_files)} configuration files defining system behavior")

    total = len(gov_files) + (1 if risk_files else 0) + (1 if config_files else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Governance program may lack formal accountability assignment"],
                      "Establish governance program with risk management policies and accountability",
                      file_evidence=file_ev)
    return _make("gap", [], ["No governance program found"],
                 "Implement governance program with risk management and compliance accountability")


def _evidence_input_sanitization(req: str, model: Dict) -> Dict:
    """Check for prompt/input sanitization and validation evidence."""
    files = model.get("files", [])
    sanitize_files = [f for f in files if _file_has_keywords(f,
                      ["sanitize", "validate", "filter", "clean", "prompt", "input"])]

    sanitize_imports = _detect_imports(files, [
        "pydantic", "cerberus", "bleach", "marshmallow", "voluptuous",
        "wtforms", "validators", "guardrails",
    ])

    sanitize_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["sanitize", "validate", "filter", "clean"]):
                sanitize_fns.append(fn)

    evidence = []
    file_ev = []
    if sanitize_files:
        evidence.append(f"{len(sanitize_files)} input sanitization/validation file(s)")
        for f in sanitize_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Input sanitization/validation"))
    if sanitize_imports:
        evidence.append(f"Validation frameworks: {', '.join(sanitize_imports[:3])}")
    if sanitize_fns:
        evidence.append(f"Functions: {', '.join(sanitize_fns[:5])}")

    total = len(sanitize_files) + len(sanitize_imports) + (1 if sanitize_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Input sanitization coverage may be incomplete"],
                      "Implement comprehensive input sanitization for all LLM inputs",
                      file_evidence=file_ev)
    return _make("gap", [], ["No input sanitization infrastructure found"],
                 "Add input validation and sanitization for all prompts and LLM inputs")


def _evidence_output_validation(req: str, model: Dict) -> Dict:
    """Check for LLM output validation, filtering, and content moderation."""
    files = model.get("files", [])
    output_files = [f for f in files if _file_has_keywords(f,
                    ["output", "filter", "safety", "moderat", "redact", "guardrail"])]

    output_imports = _detect_imports(files, [
        "guardrails", "nemoguardrails", "langchain", "langchain_core",
        "openai", "anthropic", "content_safety",
    ])

    output_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["validate", "filter", "moderate", "redact", "output"]):
                output_fns.append(fn)

    evidence = []
    file_ev = []
    if output_files:
        evidence.append(f"{len(output_files)} output validation/filtering file(s)")
        for f in output_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Output validation/filtering"))
    if output_imports:
        evidence.append(f"LLM/guardrail frameworks: {', '.join(output_imports[:3])}")
    if output_fns:
        evidence.append(f"Functions: {', '.join(output_fns[:5])}")

    total = len(output_files) + len(output_imports) + (1 if output_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Output validation coverage may be incomplete"],
                      "Add output filtering and content moderation for all LLM responses",
                      file_evidence=file_ev)
    return _make("gap", [], ["No LLM output validation found"],
                 "Implement output validation, content filtering, and PII redaction for LLM responses")


def _evidence_model_provenance(req: str, model: Dict) -> Dict:
    """Check for model version pinning, hash verification, and provenance tracking."""
    files = model.get("files", [])
    prov_files = [f for f in files if _file_has_keywords(f,
                  ["provenance", "version", "pin", "hash", "checksum", "digest", "registry"])]

    # Lock files and manifests are strong provenance signals
    lock_files = [f for f in files if any(
        f.get("path", "").endswith(ext)
        for ext in [".lock", "requirements.txt", "poetry.lock", "Pipfile.lock",
                    "package-lock.json", "yarn.lock", "pnpm-lock.yaml"]
    )]

    prov_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            if any(k in fn_lower for k in ["verify", "hash", "checksum", "provenance", "pin"]):
                prov_fns.append(fn)

    evidence = []
    file_ev = []
    if prov_files:
        evidence.append(f"{len(prov_files)} provenance/version tracking file(s)")
        for f in prov_files[:3]:
            file_ev.append(_file_evidence(f["path"], "Model/dependency provenance"))
    if lock_files:
        evidence.append(f"{len(lock_files)} dependency lock file(s)")
        for f in lock_files[:3]:
            file_ev.append(_file_evidence(f["path"], "Dependency version pinning"))
    if prov_fns:
        evidence.append(f"Verification functions: {', '.join(prov_fns[:5])}")

    total = len(prov_files) + (1 if lock_files else 0) + (1 if prov_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Model provenance tracking may be incomplete"],
                      "Implement hash verification and version pinning for all LLM model dependencies",
                      file_evidence=file_ev)
    return _make("gap", [], ["No model provenance tracking found"],
                 "Add model version pinning, hash verification, and provenance documentation")


def _evidence_prompt_protection(req: str, model: Dict) -> Dict:
    """Check for system prompt isolation and protection patterns."""
    files = model.get("files", [])
    prompt_files = [f for f in files if _file_has_keywords(f,
                    ["prompt", "template", "instruction", "system", "boundary"])]

    prompt_imports = _detect_imports(files, [
        "langchain", "langchain_core", "guidance", "dspy",
        "promptflow", "jinja2", "mako",
    ])

    prompt_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            if any(k in fn_lower for k in ["prompt", "template", "system_message",
                                            "build_prompt", "format_prompt"]):
                prompt_fns.append(fn)

    evidence = []
    file_ev = []
    if prompt_files:
        evidence.append(f"{len(prompt_files)} prompt management file(s)")
        for f in prompt_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Prompt template/protection"))
    if prompt_imports:
        evidence.append(f"Prompt frameworks: {', '.join(prompt_imports[:3])}")
    if prompt_fns:
        evidence.append(f"Functions: {', '.join(prompt_fns[:5])}")

    total = len(prompt_files) + len(prompt_imports) + (1 if prompt_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Prompt protection may not cover all system prompt boundaries"],
                      "Implement prompt hierarchy enforcement and template isolation",
                      file_evidence=file_ev)
    return _make("gap", [], ["No prompt protection patterns found"],
                 "Add system prompt isolation, boundary separation, and template management")


def _evidence_embedding_security(req: str, model: Dict) -> Dict:
    """Check for vector store access controls and embedding pipeline security."""
    files = model.get("files", [])
    embed_files = [f for f in files if _file_has_keywords(f,
                   ["vector", "embedding", "chroma", "pinecone", "weaviate",
                    "qdrant", "milvus", "faiss", "rag"])]

    embed_imports = _detect_imports(files, [
        "chromadb", "pinecone", "weaviate", "qdrant_client",
        "pymilvus", "faiss", "langchain", "llama_index",
    ])

    embed_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            if any(k in fn_lower for k in ["embed", "vector", "index", "retrieve", "search"]):
                embed_fns.append(fn)

    evidence = []
    file_ev = []
    if embed_files:
        evidence.append(f"{len(embed_files)} vector/embedding file(s)")
        for f in embed_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Vector store / embedding pipeline"))
    if embed_imports:
        evidence.append(f"Vector DB frameworks: {', '.join(embed_imports[:3])}")
    if embed_fns:
        evidence.append(f"Functions: {', '.join(embed_fns[:5])}")

    total = len(embed_files) + len(embed_imports) + (1 if embed_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Vector store security controls may be incomplete"],
                      "Implement access controls and input validation for vector stores",
                      file_evidence=file_ev)
    return _make("gap", [], ["No vector/embedding security controls found"],
                 "Add access controls, input validation, and anomaly detection for embedding pipelines")


def _evidence_consumption_limits(req: str, model: Dict) -> Dict:
    """Check for rate limits, token budgets, and cost caps on LLM usage."""
    files = model.get("files", [])
    limit_files = [f for f in files if _file_has_keywords(f,
                   ["rate", "limit", "budget", "throttle", "quota", "cost", "cap"])]

    limit_imports = _detect_imports(files, [
        "ratelimit", "slowapi", "token_bucket", "limits",
        "tenacity", "backoff", "circuitbreaker",
    ])

    limit_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            if any(k in fn_lower for k in ["rate_limit", "throttle", "budget",
                                            "quota", "cost", "cap", "limit"]):
                limit_fns.append(fn)

    evidence = []
    file_ev = []
    if limit_files:
        evidence.append(f"{len(limit_files)} rate limiting/budget file(s)")
        for f in limit_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Rate limiting / cost control"))
    if limit_imports:
        evidence.append(f"Rate limiting frameworks: {', '.join(limit_imports[:3])}")
    if limit_fns:
        evidence.append(f"Functions: {', '.join(limit_fns[:5])}")

    total = len(limit_files) + len(limit_imports) + (1 if limit_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Consumption limits may not cover all LLM usage paths"],
                      "Implement token budgets, rate limits, and cost caps for all LLM API calls",
                      file_evidence=file_ev)
    return _make("gap", [], ["No LLM consumption limits found"],
                 "Add rate limits, token budgets, and cost caps for all LLM usage")


# ── OWASP Agentic Top 10 evidence functions ──────────────────────────


def _evidence_agent_goal_protection(req: str, model: Dict) -> Dict:
    """Check for agent goal/plan protection against instruction injection."""
    files = model.get("files", [])
    goal_files = [f for f in files if _file_has_keywords(f,
                  ["goal", "plan", "constraint", "guardrail", "boundary", "instruction", "agent"])]

    goal_imports = _detect_imports(files, [
        "guardrails", "nemoguardrails", "guidance", "instructor",
        "outlines", "lmql", "promptguard",
    ])

    goal_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["goal", "constraint", "guard", "boundary", "instruct"]):
                goal_fns.append(fn)

    evidence = []
    file_ev = []
    if goal_files:
        evidence.append(f"{len(goal_files)} agent goal/constraint protection file(s)")
        for f in goal_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Agent goal/constraint protection"))
    if goal_imports:
        evidence.append(f"Guardrail frameworks: {', '.join(goal_imports[:3])}")
    if goal_fns:
        evidence.append(f"Functions: {', '.join(goal_fns[:5])}")

    total = len(goal_files) + len(goal_imports) + (1 if goal_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Agent goal protection may be incomplete"],
                      "Implement comprehensive goal boundary enforcement and instruction injection prevention",
                      file_evidence=file_ev)
    return _make("gap", [], ["No agent goal protection infrastructure found"],
                 "Add goal constraints, prompt boundary enforcement, and instruction injection filtering for agents")


def _evidence_agent_tool_governance(req: str, model: Dict) -> Dict:
    """Check for agent tool permission governance and least-privilege enforcement."""
    files = model.get("files", [])
    tool_gov_files = [f for f in files if _file_has_keywords(f,
                      ["permission", "tool", "capability", "allow", "deny", "policy", "sandbox"])]

    tool_imports = _detect_imports(files, [
        "casbin", "opa", "rbac", "permissions", "authz",
        "docker", "podman", "firejail", "bubblewrap",
    ])

    tool_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["permission", "allow", "deny", "authorize", "sandbox", "policy"]):
                tool_fns.append(fn)

    evidence = []
    file_ev = []
    if tool_gov_files:
        evidence.append(f"{len(tool_gov_files)} tool governance/permission file(s)")
        for f in tool_gov_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Tool permission governance"))
    if tool_imports:
        evidence.append(f"Policy/sandbox frameworks: {', '.join(tool_imports[:3])}")
    if tool_fns:
        evidence.append(f"Functions: {', '.join(tool_fns[:5])}")

    total = len(tool_gov_files) + len(tool_imports) + (1 if tool_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Tool governance may not cover all agent capabilities"],
                      "Implement per-tool permission grants with least-privilege defaults",
                      file_evidence=file_ev)
    return _make("gap", [], ["No agent tool governance found"],
                 "Add per-tool permission controls, call limits, and side-effect sandboxing")


def _evidence_agent_identity(req: str, model: Dict) -> Dict:
    """Check for dedicated agent identity management and credential scoping."""
    files = model.get("files", [])
    identity_files = [f for f in files if _file_has_keywords(f,
                      ["identity", "credential", "service", "account", "token", "auth", "agent"])]

    identity_imports = _detect_imports(files, [
        "jwt", "oauth", "authlib", "python_jose", "pyjwt",
        "passlib", "bcrypt", "cryptography", "keyring",
    ])

    identity_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["identity", "credential", "service", "token", "agent"]):
                identity_fns.append(fn)

    evidence = []
    file_ev = []
    if identity_files:
        evidence.append(f"{len(identity_files)} identity/credential management file(s)")
        for f in identity_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Agent identity management"))
    if identity_imports:
        evidence.append(f"Auth/crypto frameworks: {', '.join(identity_imports[:3])}")
    if identity_fns:
        evidence.append(f"Functions: {', '.join(identity_fns[:5])}")

    total = len(identity_files) + len(identity_imports) + (1 if identity_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Agent identity management may be incomplete"],
                      "Use dedicated service identities with scoped credentials for each agent",
                      file_evidence=file_ev)
    return _make("gap", [], ["No dedicated agent identity management found"],
                 "Implement service identities, credential scoping, and delegation controls for agents")


def _evidence_code_execution_safety(req: str, model: Dict) -> Dict:
    """Check for code execution sandboxing and dangerous function prevention."""
    files = model.get("files", [])
    sandbox_files = [f for f in files if _file_has_keywords(f,
                     ["sandbox", "isolat", "container", "jail", "secure", "exec"])]

    sandbox_imports = _detect_imports(files, [
        "docker", "podman", "kubernetes", "subprocess", "shlex",
        "firejail", "bubblewrap", "nsjail", "gvisor",
        "restrictedpython", "ast",
    ])

    # Detect dangerous patterns (eval, exec, os.system) vs safe wrappers
    dangerous_fns = []
    safe_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            if any(k in fn_lower for k in ["sandbox", "isolate", "safe_exec", "restricted"]):
                safe_fns.append(fn)
            elif any(k in fn_lower for k in ["exec", "eval", "shell", "system", "popen"]):
                dangerous_fns.append(fn)

    evidence = []
    file_ev = []
    gaps = []

    if sandbox_files:
        evidence.append(f"{len(sandbox_files)} sandboxing/isolation file(s)")
        for f in sandbox_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Code execution sandboxing"))
    if sandbox_imports:
        evidence.append(f"Sandbox/process frameworks: {', '.join(sandbox_imports[:3])}")
    if safe_fns:
        evidence.append(f"Safe execution wrappers: {', '.join(safe_fns[:5])}")
    if dangerous_fns:
        gaps.append(f"Potentially dangerous functions: {', '.join(dangerous_fns[:5])}")

    safe_signals = len(sandbox_files) + len(sandbox_imports) + (1 if safe_fns else 0)
    if safe_signals >= 2 and not dangerous_fns:
        return _make("met", evidence, file_evidence=file_ev)
    elif safe_signals >= 1:
        return _make("partial", evidence, gaps,
                      "Ensure all code execution paths use sandboxed environments",
                      file_evidence=file_ev)
    if dangerous_fns:
        return _make("gap", evidence, gaps,
                      "Sandbox all agent code execution and restrict eval/exec/shell usage")
    return _make("gap", [], ["No code execution safety controls detected"],
                 "Add execution sandboxing, restrict eval/exec, and isolate agent-generated code")


def _evidence_memory_integrity(req: str, model: Dict) -> Dict:
    """Check for agent memory/context integrity protection."""
    files = model.get("files", [])
    memory_files = [f for f in files if _file_has_keywords(f,
                    ["memory", "context", "store", "persist", "cache", "session", "history"])]

    memory_imports = _detect_imports(files, [
        "redis", "memcached", "chromadb", "pinecone", "qdrant",
        "weaviate", "milvus", "faiss", "lancedb", "sqlite3",
    ])

    integrity_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["memory", "context", "persist", "store", "retrieve", "cache"]):
                integrity_fns.append(fn)

    evidence = []
    file_ev = []
    if memory_files:
        evidence.append(f"{len(memory_files)} memory/context management file(s)")
        for f in memory_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Agent memory management"))
    if memory_imports:
        evidence.append(f"Storage frameworks: {', '.join(memory_imports[:3])}")
    if integrity_fns:
        evidence.append(f"Memory functions: {', '.join(integrity_fns[:5])}")

    total = len(memory_files) + len(memory_imports) + (1 if integrity_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Memory integrity controls may be incomplete"],
                      "Add access controls, integrity checks, and provenance tracking for agent memory stores",
                      file_evidence=file_ev)
    return _make("gap", [], ["No agent memory management infrastructure found"],
                 "Implement memory integrity checks, access controls, and injection detection for agent stores")


def _evidence_agent_communication_security(req: str, model: Dict) -> Dict:
    """Check for secure inter-agent communication (TLS, signing, auth)."""
    files = model.get("files", [])
    comm_files = [f for f in files if _file_has_keywords(f,
                  ["message", "channel", "rpc", "grpc", "protocol", "queue", "broker"])]

    comm_imports = _detect_imports(files, [
        "grpc", "grpcio", "protobuf", "zmq", "pyzmq", "pika", "aio_pika",
        "celery", "dramatiq", "nats", "kafka", "confluent_kafka",
        "cryptography", "ssl", "tls", "nacl",
    ])

    comm_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["message", "send", "receive", "dispatch", "sign", "verify", "encrypt"]):
                comm_fns.append(fn)

    evidence = []
    file_ev = []
    if comm_files:
        evidence.append(f"{len(comm_files)} inter-agent communication file(s)")
        for f in comm_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Agent communication infrastructure"))
    if comm_imports:
        evidence.append(f"Messaging/crypto frameworks: {', '.join(comm_imports[:3])}")
    if comm_fns:
        evidence.append(f"Functions: {', '.join(comm_fns[:5])}")

    total = len(comm_files) + len(comm_imports) + (1 if comm_fns else 0)
    if total >= 3:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Inter-agent communication security may be incomplete"],
                      "Add mutual TLS, message signing, and replay protection for agent channels",
                      file_evidence=file_ev)
    return _make("gap", [], ["No inter-agent communication security found"],
                 "Implement encrypted, authenticated channels for all agent-to-agent communication")


def _evidence_cascade_protection(req: str, model: Dict) -> Dict:
    """Check for circuit breakers, timeouts, and bulkhead patterns."""
    files = model.get("files", [])
    cascade_files = [f for f in files if _file_has_keywords(f,
                     ["circuit", "breaker", "timeout", "retry", "bulkhead", "fallback", "resilience"])]

    cascade_imports = _detect_imports(files, [
        "tenacity", "backoff", "pybreaker", "circuitbreaker",
        "resilience4j", "polly", "hystrix", "retry",
    ])

    cascade_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["circuit", "breaker", "timeout", "retry", "fallback", "bulkhead"]):
                cascade_fns.append(fn)

    evidence = []
    file_ev = []
    if cascade_files:
        evidence.append(f"{len(cascade_files)} resilience/circuit-breaker file(s)")
        for f in cascade_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Cascade protection infrastructure"))
    if cascade_imports:
        evidence.append(f"Resilience frameworks: {', '.join(cascade_imports[:3])}")
    if cascade_fns:
        evidence.append(f"Functions: {', '.join(cascade_fns[:5])}")

    total = len(cascade_files) + len(cascade_imports) + (1 if cascade_fns else 0)
    if total >= 2:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Cascade protection may not cover all failure paths"],
                      "Add circuit breakers, timeout policies, and bulkhead isolation across agent chains",
                      file_evidence=file_ev)
    return _make("gap", [], ["No cascade protection patterns found"],
                 "Implement circuit breakers, timeout policies, and graceful degradation for agent systems")


def _evidence_agent_containment(req: str, model: Dict) -> Dict:
    """Check for agent containment controls: kill switches, resource limits, behaviour monitoring."""
    files = model.get("files", [])
    contain_files = [f for f in files if _file_has_keywords(f,
                     ["contain", "limit", "kill", "stop", "shutdown", "terminate", "bound", "monitor"])]

    contain_imports = _detect_imports(files, [
        "resource", "psutil", "signal", "atexit",
        "watchdog", "supervisor", "systemd",
    ])

    contain_fns = []
    for f in files:
        for fn in f.get("functions", []):
            fn_tokens = set(re.split(r'[_\s]+', fn.lower()))
            fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
            if any(k in fn_tokens for k in ["kill", "terminate", "shutdown", "stop", "contain", "limit", "bound"]):
                contain_fns.append(fn)

    evidence = []
    file_ev = []
    if contain_files:
        evidence.append(f"{len(contain_files)} containment/monitoring file(s)")
        for f in contain_files[:5]:
            file_ev.append(_file_evidence(f["path"], "Agent containment controls"))
    if contain_imports:
        evidence.append(f"Process/resource frameworks: {', '.join(contain_imports[:3])}")
    if contain_fns:
        evidence.append(f"Functions: {', '.join(contain_fns[:5])}")

    total = len(contain_files) + len(contain_imports) + (1 if contain_fns else 0)
    if total >= 2:
        return _make("met", evidence, file_evidence=file_ev)
    elif total >= 1:
        return _make("partial", evidence,
                      ["Agent containment controls may be incomplete"],
                      "Add kill switches, resource limits, and behavioural monitoring for all agents",
                      file_evidence=file_ev)
    return _make("gap", [], ["No agent containment controls found"],
                 "Implement kill switches, resource bounds, and goal drift detection for autonomous agents")


def _evidence_default(req: str, model: Dict) -> Dict:
    """Fallback evaluator — checks for general documentation presence."""
    files = model.get("files", [])
    features = model.get("features", [])
    if features and len(files) > 10:
        return _make("partial",
                      [f"{len(features)} features discovered across {len(files)} files"],
                      ["Specific evidence for this control not automatically detected"],
                      "Review this control manually and add supporting documentation")
    return _make("gap", [], ["Insufficient evidence for automatic evaluation"],
                 "Add documentation and implementation for this compliance requirement")


def _file_has_keywords(file_info: Dict, keywords: List[str]) -> bool:
    """Check if a file's path or content metadata matches any keywords.

    Uses word-boundary-aware matching to avoid false positives like
    "blog" matching "log" or "database" matching "data".
    """
    path_lower = file_info.get("path", "").lower()
    # Split path into meaningful tokens (by separators and case boundaries)
    path_tokens = set(re.split(r'[/_\-.\\\s]+', path_lower))
    for kw in keywords:
        # Check path tokens (word-level match)
        if kw in path_tokens:
            return True
        # Also allow substring match when the keyword is the full filename stem
        stem = path_lower.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if kw == stem:
            return True
    # Check function names (word-boundary match)
    for fn in file_info.get("functions", []):
        fn_lower = fn.lower()
        fn_tokens = set(re.split(r'[_\s]+', fn_lower))
        # Also split camelCase
        fn_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', fn))
        for kw in keywords:
            if kw in fn_tokens:
                return True
    # Check class names (word-boundary match)
    for cls in file_info.get("classes", []):
        cls_lower = cls.lower()
        cls_tokens = set(re.split(r'[_\s]+', cls_lower))
        cls_tokens.update(t.lower() for t in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', cls))
        for kw in keywords:
            if kw in cls_tokens:
                return True
    return False


# ── MCP Server Security ───────────────────────────────────────────────

_MCP_IMPORT_PATTERNS = re.compile(r'\b(?:mcp|fastmcp|modelcontextprotocol)\b', re.I)
_MCP_CLASS_PATTERNS = re.compile(r'\bMcp|MCP|FastMCP\b')

_MCP_SECURITY_CHECKS = {
    "authentication": {
        "imports": ["fastapi.security", "jwt", "passport", "oauth", "api_key"],
        "functions": ["auth", "verify", "token", "api_key", "authenticate", "authorize"],
    },
    "input_validation": {
        "imports": ["pydantic", "jsonschema", "zod", "marshmallow", "cerberus", "voluptuous"],
        "functions": ["validate", "schema", "sanitize", "parse_input"],
    },
    "credential_handling": {
        "bad_patterns": [
            re.compile(r'''(?:api_key|secret|password|token)\s*=\s*["'][^"']{8,}["']''', re.I),
        ],
        "good_patterns": [".env.example", "os.environ", "os.getenv", "environ.get"],
    },
    "logging": {
        "imports": ["logging", "structlog", "loguru", "winston", "pino"],
        "functions": ["log", "logger", "audit"],
    },
    "rate_limiting": {
        "imports": ["slowapi", "ratelimit", "throttle", "limiter"],
        "functions": ["rate_limit", "throttle", "limit"],
    },
    "error_handling": {
        "patterns": [
            re.compile(r'except\s+\w+', re.M),
            re.compile(r'try\s*:', re.M),
            re.compile(r'catch\s*\(', re.M),
        ],
        "functions": ["error_handler", "handle_error", "sanitize_error"],
    },
    "permission_scoping": {
        "functions": ["permission", "role", "capability", "scope", "can_access", "allowed"],
        "imports": ["rbac", "casbin", "permissions"],
    },
    "tls_transport": {
        "good_patterns": [re.compile(r'https://')],
        "bad_patterns": [re.compile(r'http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)')],
    },
}


def _evidence_mcp_server_security(req: str, model: Dict) -> Dict:
    """Scan for MCP server implementations and check 8 security categories."""
    files = model.get("files", [])

    # Detect MCP server files
    mcp_files = []
    for f in files:
        path_lower = f.get("path", "").lower()
        imports = f.get("imports", [])
        classes = f.get("classes", [])
        functions = f.get("functions", [])

        is_mcp = False
        # Check imports
        for imp in imports:
            if _MCP_IMPORT_PATTERNS.search(imp):
                is_mcp = True
                break
        # Check path
        if not is_mcp and "mcp" in path_lower:
            is_mcp = True
        # Check classes
        if not is_mcp:
            for cls in classes:
                if _MCP_CLASS_PATTERNS.search(cls):
                    is_mcp = True
                    break
        # Check functions for mcp/tool registration patterns
        if not is_mcp:
            for fn in functions:
                if "mcp" in fn.lower() or fn.lower() in ("register_tool", "tool_handler"):
                    is_mcp = True
                    break

        if is_mcp:
            mcp_files.append(f)

    if not mcp_files:
        return _make("met", ["No MCP server implementation detected"])

    # Evaluate 8 security categories across all MCP files
    categories_met = []
    categories_gap = []
    file_ev = []

    # Gather all content signals from MCP files
    all_imports = []
    all_functions = []
    all_classes = []
    for f in mcp_files:
        all_imports.extend(f.get("imports", []))
        all_functions.extend(f.get("functions", []))
        all_classes.extend(f.get("classes", []))
        file_ev.append(_file_evidence(f["path"], "MCP server implementation"))

    imports_lower = " ".join(all_imports).lower()
    functions_lower = [fn.lower() for fn in all_functions]

    # 1. Authentication
    check = _MCP_SECURITY_CHECKS["authentication"]
    if (any(p in imports_lower for p in check["imports"]) or
            any(any(k in fn for k in check["functions"]) for fn in functions_lower)):
        categories_met.append("Authentication")
    else:
        categories_gap.append("Authentication on tool endpoints")

    # 2. Input validation
    check = _MCP_SECURITY_CHECKS["input_validation"]
    if (any(p in imports_lower for p in check["imports"]) or
            any(any(k in fn for k in check["functions"]) for fn in functions_lower)):
        categories_met.append("Input validation")
    else:
        categories_gap.append("Schema validation on tool inputs")

    # 3. Credential handling (check for hardcoded secrets)
    check = _MCP_SECURITY_CHECKS["credential_handling"]
    has_hardcoded = False
    has_env_handling = any(p in imports_lower for p in check["good_patterns"])
    # We don't have raw content, so check function/import signals
    if not has_env_handling:
        for f in mcp_files:
            for imp in f.get("imports", []):
                if any(g in imp.lower() for g in ["os", "dotenv", "environ"]):
                    has_env_handling = True
                    break
    if has_env_handling:
        categories_met.append("Credential handling")
    else:
        categories_gap.append("No hardcoded credentials in MCP config/source")

    # 4. Logging
    check = _MCP_SECURITY_CHECKS["logging"]
    if (any(p in imports_lower for p in check["imports"]) or
            any(any(k in fn for k in check["functions"]) for fn in functions_lower)):
        categories_met.append("Logging")
    else:
        categories_gap.append("Structured logging with caller identity")

    # 5. Rate limiting
    check = _MCP_SECURITY_CHECKS["rate_limiting"]
    if (any(p in imports_lower for p in check["imports"]) or
            any(any(k in fn for k in check["functions"]) for fn in functions_lower)):
        categories_met.append("Rate limiting")
    else:
        categories_gap.append("Rate limiting and budget controls")

    # 6. Error handling
    check = _MCP_SECURITY_CHECKS["error_handling"]
    if any(any(k in fn for k in check["functions"]) for fn in functions_lower):
        categories_met.append("Error handling")
    else:
        # Most Python/JS code has exception handling; give partial credit if functions exist
        if len(all_functions) > 5:
            categories_met.append("Error handling")
        else:
            categories_gap.append("Error responses don't expose internals")

    # 7. Permission scoping
    check = _MCP_SECURITY_CHECKS["permission_scoping"]
    if (any(p in imports_lower for p in check["imports"]) or
            any(any(k in fn for k in check["functions"]) for fn in functions_lower)):
        categories_met.append("Permission scoping")
    else:
        categories_gap.append("Least-privilege tool permission scoping")

    # 8. TLS/transport
    # Check if any imports/functions reference https (good) or bare http (bad)
    has_https = any("https" in imp.lower() for imp in all_imports)
    has_http_bad = False
    for imp in all_imports:
        imp_l = imp.lower()
        if "http://" in imp_l and not any(s in imp_l for s in ["localhost", "127.0.0.1", "0.0.0.0"]):
            has_http_bad = True
    if has_https or not has_http_bad:
        categories_met.append("TLS/transport")
    else:
        categories_gap.append("TLS for remote connections")

    # Score
    met_count = len(categories_met)
    evidence = [
        f"{len(mcp_files)} MCP server file(s) detected",
        f"{met_count}/8 security categories satisfied: {', '.join(categories_met)}" if categories_met else "0/8 security categories satisfied",
    ]

    if met_count >= 6:
        return _make("met", evidence, file_evidence=file_ev)
    elif met_count >= 3:
        return _make("partial", evidence, categories_gap,
                      "Address missing MCP security categories: " + ", ".join(categories_gap[:3]),
                      file_evidence=file_ev)
    return _make("gap", evidence, categories_gap,
                  "MCP server needs security hardening across multiple categories",
                  file_evidence=file_ev)


# ── AI Supply Chain ───────────────────────────────────────────────────

_AI_PACKAGES_PYPI = frozenset({
    # LLM providers
    "anthropic", "openai", "google-generativeai", "google-cloud-aiplatform",
    "cohere", "replicate", "mistralai", "groq", "together", "fireworks-ai",
    "ai21", "aleph-alpha-client", "anyscale",
    # Frameworks
    "langchain", "langchain-core", "langchain-community", "langchain-openai",
    "langchain-anthropic", "langgraph", "llama-index", "llama-index-core",
    "haystack-ai", "guidance", "dspy-ai", "autogen", "crewai", "semantic-kernel",
    "promptflow",
    # ML / deep learning
    "torch", "torchvision", "tensorflow", "keras", "jax", "jaxlib",
    "transformers", "diffusers", "accelerate", "datasets", "tokenizers",
    "safetensors", "sentencepiece", "bitsandbytes", "peft", "trl",
    # Vector DBs
    "chromadb", "pinecone-client", "weaviate-client", "qdrant-client",
    "milvus", "pymilvus", "faiss-cpu", "faiss-gpu", "lancedb",
    # Guardrails
    "guardrails-ai", "nemoguardrails", "rebuff",
    # MCP / agents
    "mcp", "fastmcp", "modelcontextprotocol",
})

_AI_PACKAGES_NPM = frozenset({
    "openai", "@anthropic-ai/sdk", "langchain", "@langchain/core",
    "@langchain/openai", "@langchain/anthropic", "cohere-ai",
    "@google/generative-ai", "replicate", "ai", "@ai-sdk/openai",
    "@ai-sdk/anthropic", "@modelcontextprotocol/sdk",
    "chromadb", "@pinecone-database/pinecone", "weaviate-ts-client",
})


def _is_ai_package(name: str, ecosystem: str) -> bool:
    """Check if a dependency is an AI/ML package."""
    norm = name.lower().replace("_", "-")
    if ecosystem == "PyPI":
        return norm in _AI_PACKAGES_PYPI
    elif ecosystem == "npm":
        return norm in _AI_PACKAGES_NPM
    return False


def _query_osv(package_name: str, version: str, ecosystem: str) -> Optional[List[Dict]]:
    """Query OSV.dev API for known vulnerabilities. Returns list of vulns or None on failure."""
    try:
        import httpx
    except ImportError:
        return None

    # Normalize PyPI names: _ → -
    if ecosystem == "PyPI":
        package_name = package_name.replace("_", "-")

    payload = {
        "package": {"name": package_name, "ecosystem": ecosystem},
    }
    if version:
        payload["version"] = version

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post("https://api.osv.dev/v1/query", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("vulns", [])
    except Exception:
        return None


def _evidence_ai_supply_chain(req: str, model: Dict) -> Dict:
    """Check AI deps for version pinning + known CVEs via OSV API."""
    dependencies = model.get("dependencies", [])
    if not dependencies:
        return _make("met", ["No dependency manifests found to audit"])

    # Filter to AI packages
    ai_deps = [d for d in dependencies if _is_ai_package(d["name"], d["ecosystem"])]
    if not ai_deps:
        return _make("met", ["No AI/ML dependencies detected in manifests"])

    # Check pinning discipline
    pinned = [d for d in ai_deps if d.get("pinned")]
    unpinned = [d for d in ai_deps if not d.get("pinned")]

    evidence = [f"{len(ai_deps)} AI/ML dependencies found across manifests"]
    gaps = []
    file_ev = []
    vuln_count = 0
    critical_vulns = []
    checked = 0

    if unpinned:
        gaps.append(f"{len(unpinned)} AI deps not pinned: {', '.join(d['name'] for d in unpinned[:5])}")

    # Query OSV for pinned deps with versions (cap at 20 queries)
    for dep in ai_deps:
        if checked >= 20:
            break
        if not dep.get("version"):
            continue
        checked += 1
        vulns = _query_osv(dep["name"], dep["version"], dep["ecosystem"])
        if vulns is None:
            continue  # API failure — don't penalize
        if vulns:
            vuln_count += len(vulns)
            severities = []
            for v in vulns:
                sev = "unknown"
                for s in v.get("severity", []):
                    if s.get("type") == "CVSS_V3":
                        score_str = s.get("score", "")
                        # Extract base score from CVSS vector or direct score
                        try:
                            base = float(score_str) if "." in str(score_str) else 0
                        except (ValueError, TypeError):
                            base = 0
                        if base >= 9.0:
                            sev = "critical"
                        elif base >= 7.0:
                            sev = "high"
                        elif base >= 4.0:
                            sev = "medium"
                        else:
                            sev = "low"
                severities.append(sev)
            if "critical" in severities:
                critical_vulns.append(dep["name"])
            vuln_ids = [v.get("id", "?") for v in vulns[:3]]
            file_ev.append(_file_evidence(
                dep.get("source", ""),
                f"{dep['name']}=={dep['version']}: {len(vulns)} vuln(s) ({', '.join(vuln_ids)})",
            ))

    if checked > 0:
        evidence.append(f"{checked} AI deps checked against OSV vulnerability database")
    if vuln_count > 0:
        evidence.append(f"{vuln_count} known vulnerability(ies) found")
    if pinned:
        evidence.append(f"{len(pinned)}/{len(ai_deps)} AI deps are version-pinned")

    # Score
    if critical_vulns:
        gaps.append(f"Critical CVEs in: {', '.join(critical_vulns)}")
        return _make("gap", evidence, gaps,
                      "Immediately update AI dependencies with critical vulnerabilities",
                      file_evidence=file_ev)
    elif vuln_count > 0 or unpinned:
        return _make("partial", evidence, gaps,
                      "Pin all AI dependency versions and address known vulnerabilities",
                      file_evidence=file_ev)
    return _make("met", evidence, file_evidence=file_ev)


# ── Semantic (LLM-powered) evaluation ────────────────────────────────

_SEMANTIC_CALLS_MADE = 0
_SEMANTIC_MAX_CALLS = 20  # cap per scan to control cost


def _semantic_evaluate_control(
    ctrl_id: str,
    requirement: str,
    evidence_fn: str,
    model: Dict[str, Any],
    provider: str = "anthropic",
    api_key: str = "",
    llm_model: str = "",
    graph_metrics: Optional[Dict] = None,
) -> Optional[Dict]:
    """Use LLM to evaluate a single control against relevant file contents.

    Selects the most relevant files for this control, sends them to the LLM
    with the control requirement, and returns structured assessment.

    Returns None if LLM call is skipped (budget exhausted, no key, etc.).
    """
    global _SEMANTIC_CALLS_MADE

    if _SEMANTIC_CALLS_MADE >= _SEMANTIC_MAX_CALLS:
        return None
    if not api_key:
        return None

    # Select relevant files (up to 5 most relevant for this evidence function)
    files = model.get("files", [])
    relevant = _select_relevant_files(files, evidence_fn, graph_metrics=graph_metrics)
    if not relevant:
        return None

    # Build file content snippets (cap at 3000 chars per file)
    snippets = []
    for f in relevant[:5]:
        path = f.get("path", "")
        fns = f.get("functions", [])
        classes = f.get("classes", [])
        imports = f.get("imports", [])
        snippet = f"File: {path}\n"
        if classes:
            snippet += f"  Classes: {', '.join(classes[:10])}\n"
        if fns:
            snippet += f"  Functions: {', '.join(fns[:15])}\n"
        if imports:
            snippet += f"  Imports: {', '.join(imports[:10])}\n"
        snippets.append(snippet)

    file_context = "\n".join(snippets)

    prompt = (
        f"You are a compliance auditor evaluating a codebase against regulatory requirements.\n\n"
        f"Control ID: {ctrl_id}\n"
        f"Requirement: {requirement}\n\n"
        f"Relevant files found in the codebase:\n{file_context}\n\n"
        f"Based on the file metadata above, assess whether this codebase has evidence "
        f"to satisfy this compliance control.\n\n"
        f"Respond in exactly this JSON format:\n"
        f'{{"status": "met"|"partial"|"gap", "evidence": ["specific evidence found"], '
        f'"analysis": "2-3 sentence assessment"}}'
    )

    try:
        from comply._vendor.llm_client import call_llm
        response = call_llm(prompt, provider=provider, api_key=api_key, model=llm_model, max_tokens=500)
        _SEMANTIC_CALLS_MADE += 1

        if not response:
            return None

        # Parse JSON from response
        import json
        # Try to extract JSON from response (may have markdown code fences)
        json_str = response.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        result = json.loads(json_str)
        if isinstance(result, dict) and "status" in result:
            result["evidence"] = [f"[Semantic] {e}" for e in result.get("evidence", [])]
            return result
    except Exception as exc:
        log.debug("Semantic evaluation failed for %s: %s", ctrl_id, exc)

    return None


def _select_relevant_files(
    files: List[Dict],
    evidence_fn: str,
    graph_metrics: Optional[Dict] = None,
) -> List[Dict]:
    """Select files most relevant to a given evidence function.

    When graph_metrics are provided, uses graph-aware ranking:
    keyword-matched files are reordered by structural importance,
    and graph-ranked files supplement when keyword matches are sparse.
    """
    relevance_keywords = {
        "evidence_audit_logging": ["log", "audit", "trace", "record"],
        "evidence_traceability": ["log", "audit", "trace"],
        "evidence_risk_assessment_gateway": ["risk", "safety", "hazard"],
        "evidence_risk_categorization": ["risk", "category", "classify"],
        "evidence_risk_register_auto": ["risk", "register"],
        "evidence_transparency_disclosure": ["readme", "doc", "disclosure", "about"],
        "evidence_transparency_logging": ["readme", "doc", "transparency"],
        "evidence_continuous_monitoring": ["monitor", "metric", "health", "alert"],
        "evidence_performance_measurement": ["test", "benchmark", "performance"],
        "evidence_governance_policy": ["policy", "governance", "compliance"],
        "evidence_logical_access": ["auth", "permission", "security", "login"],
        "evidence_data_handling": ["privacy", "gdpr", "encrypt", "data"],
        "evidence_change_management": ["changelog", "ci", "deploy", "pipeline"],
        "evidence_incident_response": ["incident", "response", "escalat"],
        "evidence_human_oversight_gateway": ["auth", "oversight", "approval"],
        "evidence_input_sanitization": ["sanitize", "validate", "filter", "prompt", "input", "clean"],
        "evidence_output_validation": ["output", "filter", "safety", "moderate", "redact", "guardrail"],
        "evidence_model_provenance": ["provenance", "version", "hash", "checksum", "model", "registry"],
        "evidence_prompt_protection": ["prompt", "template", "instruction", "system", "boundary"],
        "evidence_embedding_security": ["vector", "embedding", "chroma", "pinecone", "faiss", "rag"],
        "evidence_consumption_limits": ["rate", "limit", "budget", "throttle", "quota", "cost"],
        "evidence_access_control": ["auth", "permission", "security", "access", "control"],
        "evidence_mcp_server_security": ["mcp", "server", "tool", "auth", "security", "rate", "limit"],
        "evidence_ai_supply_chain": ["requirements", "pyproject", "package", "dependency", "version"],
        # OWASP Agentic Top 10
        "evidence_agent_goal_protection": ["goal", "plan", "constraint", "guardrail", "boundary", "agent"],
        "evidence_agent_tool_governance": ["permission", "tool", "capability", "allow", "deny", "policy", "sandbox"],
        "evidence_agent_identity": ["identity", "credential", "service", "account", "token", "auth", "agent"],
        "evidence_code_execution_safety": ["sandbox", "exec", "eval", "shell", "isolate", "container", "restrict"],
        "evidence_memory_integrity": ["memory", "context", "store", "persist", "cache", "session", "history"],
        "evidence_agent_communication_security": ["message", "channel", "rpc", "grpc", "protocol", "queue", "sign"],
        "evidence_cascade_protection": ["circuit", "breaker", "timeout", "retry", "fallback", "resilience"],
        "evidence_agent_containment": ["contain", "limit", "kill", "stop", "shutdown", "terminate", "monitor"],
    }

    keywords = relevance_keywords.get(evidence_fn, [])
    if not keywords:
        # Return files with most code density
        scored = sorted(files, key=lambda f: len(f.get("functions", [])) + len(f.get("classes", [])), reverse=True)
        return scored[:5]

    # Score files by keyword relevance
    kw_scores = {}
    for f in files:
        score = 0
        path_lower = f.get("path", "").lower()
        for kw in keywords:
            if kw in path_lower:
                score += 2
            for fn in f.get("functions", []):
                if kw in fn.lower():
                    score += 1
            for cls in f.get("classes", []):
                if kw in cls.lower():
                    score += 1
        kw_scores[f.get("path", "")] = score

    # Graph-enhanced ranking when metrics available
    if graph_metrics:
        try:
            from comply._vendor.graph_ranking import rank_files_for_evidence
            return rank_files_for_evidence(
                files, evidence_fn, graph_metrics, kw_scores, top_n=5,
            )
        except Exception:
            pass  # Fallback to keyword-only

    # Keyword-only fallback
    scored = [(kw_scores.get(f.get("path", ""), 0), f) for f in files if kw_scores.get(f.get("path", ""), 0) > 0]
    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:5]]


def reset_semantic_counter():
    """Reset the per-scan semantic call counter."""
    global _SEMANTIC_CALLS_MADE
    _SEMANTIC_CALLS_MADE = 0


# Map evidence_fn names from frameworks.yaml to evaluator functions
_EVIDENCE_FN_MAP = {
    "evidence_audit_logging": _evidence_audit_logging,
    "evidence_traceability": _evidence_audit_logging,
    "evidence_risk_assessment_gateway": _evidence_risk_assessment,
    "evidence_risk_categorization": _evidence_risk_assessment,
    "evidence_risk_register_auto": _evidence_risk_assessment,
    "evidence_transparency_disclosure": _evidence_transparency,
    "evidence_transparency_logging": _evidence_transparency,
    "evidence_continuous_monitoring": _evidence_monitoring,
    "evidence_performance_measurement": _evidence_testing,
    "evidence_governance_policy": _evidence_governance,
    "evidence_logical_access": _evidence_access_control,
    "evidence_data_handling": _evidence_data_handling,
    "evidence_change_management": _evidence_change_management,
    "evidence_incident_response": _evidence_incident_response,
    "evidence_human_oversight_gateway": _evidence_access_control,
    "evidence_ai_system_inventory": _evidence_transparency,
    "evidence_impact_documentation": _evidence_impact_assessment,
    "evidence_consumer_notification": _evidence_consumer_notice,
    "evidence_availability_controls": _evidence_monitoring,
    "evidence_retention_compliance": _evidence_audit_logging,
    # Colorado SB 24-205 specific
    "evidence_governance_program": _evidence_governance_program,
    # OWASP LLM Top 10
    "evidence_input_sanitization": _evidence_input_sanitization,
    "evidence_output_validation": _evidence_output_validation,
    "evidence_model_provenance": _evidence_model_provenance,
    "evidence_prompt_protection": _evidence_prompt_protection,
    "evidence_embedding_security": _evidence_embedding_security,
    "evidence_consumption_limits": _evidence_consumption_limits,
    "evidence_access_control": _evidence_access_control,
    # Phase 9: MCP security + AI supply chain
    "evidence_mcp_server_security": _evidence_mcp_server_security,
    "evidence_ai_supply_chain": _evidence_ai_supply_chain,
    # OWASP Agentic Top 10
    "evidence_agent_goal_protection": _evidence_agent_goal_protection,
    "evidence_agent_tool_governance": _evidence_agent_tool_governance,
    "evidence_agent_identity": _evidence_agent_identity,
    "evidence_code_execution_safety": _evidence_code_execution_safety,
    "evidence_memory_integrity": _evidence_memory_integrity,
    "evidence_agent_communication_security": _evidence_agent_communication_security,
    "evidence_cascade_protection": _evidence_cascade_protection,
    "evidence_agent_containment": _evidence_agent_containment,
}
