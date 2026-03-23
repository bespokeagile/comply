"""JUnit XML parser for compliance evidence mapping."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class TestResult:
    """A single test case result."""
    name: str
    classname: str
    time: float = 0.0
    status: str = "passed"  # passed, failed, error, skipped
    failure_message: Optional[str] = None
    failure_type: Optional[str] = None
    error_message: Optional[str] = None
    skipped_reason: Optional[str] = None


@dataclass
class TestSuite:
    """A JUnit test suite with aggregate stats."""
    name: str
    tests: int
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    time: float = 0.0
    results: List[TestResult] = field(default_factory=list)
    timestamp: Optional[str] = None

    @property
    def passed(self) -> int:
        return self.tests - self.failures - self.errors - self.skipped


def parse_junit(raw_xml: str) -> List[TestSuite]:
    """Parse JUnit XML string into test suites.

    Handles both <testsuites> (multiple) and <testsuite> (single) root elements.
    """
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        log.warning("Failed to parse JUnit XML: %s", e)
        return []

    suites = []

    if root.tag == "testsuites":
        for ts_el in root.findall("testsuite"):
            suites.append(_parse_suite(ts_el))
    elif root.tag == "testsuite":
        suites.append(_parse_suite(root))
    else:
        log.warning("Unexpected JUnit root element: %s", root.tag)
        return []

    total_tests = sum(s.tests for s in suites)
    log.info("Parsed JUnit: %d suites, %d tests", len(suites), total_tests)
    return suites


def _parse_suite(el: ET.Element) -> TestSuite:
    """Parse a <testsuite> element."""
    name = el.get("name", "unnamed")
    tests = int(el.get("tests", "0"))
    failures = int(el.get("failures", "0"))
    errors = int(el.get("errors", "0"))
    skipped = int(el.get("skipped", "0"))
    time_s = float(el.get("time", "0"))
    timestamp = el.get("timestamp")

    results = []
    for tc in el.findall("testcase"):
        result = _parse_testcase(tc)
        results.append(result)

    # Reconcile counts from attributes vs actual children
    if results and tests == 0:
        tests = len(results)
        failures = sum(1 for r in results if r.status == "failed")
        errors = sum(1 for r in results if r.status == "error")
        skipped = sum(1 for r in results if r.status == "skipped")

    return TestSuite(
        name=name,
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        time=time_s,
        results=results,
        timestamp=timestamp,
    )


def _parse_testcase(el: ET.Element) -> TestResult:
    """Parse a <testcase> element."""
    name = el.get("name", "unnamed")
    classname = el.get("classname", "")
    time_s = float(el.get("time", "0"))

    status = "passed"
    failure_message = None
    failure_type = None
    error_message = None
    skipped_reason = None

    fail_el = el.find("failure")
    if fail_el is not None:
        status = "failed"
        failure_message = fail_el.get("message", fail_el.text or "")
        failure_type = fail_el.get("type", "")

    err_el = el.find("error")
    if err_el is not None:
        status = "error"
        error_message = err_el.get("message", err_el.text or "")

    skip_el = el.find("skipped")
    if skip_el is not None:
        status = "skipped"
        skipped_reason = skip_el.get("message", skip_el.text or "")

    return TestResult(
        name=name,
        classname=classname,
        time=time_s,
        status=status,
        failure_message=failure_message,
        failure_type=failure_type,
        error_message=error_message,
        skipped_reason=skipped_reason,
    )


# ── Compliance evidence categories ────────────────────────────────────

# Patterns to classify test names into compliance-relevant categories
_EVIDENCE_PATTERNS = {
    "evidence_audit_logging": re.compile(
        r"(audit|log|trace|record|event)", re.IGNORECASE),
    "evidence_access_control": re.compile(
        r"(auth|access|permission|role|rbac|login|credential)", re.IGNORECASE),
    "evidence_input_sanitization": re.compile(
        r"(sanitiz|inject|xss|escape|valid|filter)", re.IGNORECASE),
    "evidence_output_validation": re.compile(
        r"(output|response|render|format|schema)", re.IGNORECASE),
    "evidence_data_handling": re.compile(
        r"(data|privacy|pii|encrypt|gdpr|consent|anonym)", re.IGNORECASE),
    "evidence_prompt_protection": re.compile(
        r"(prompt|inject|jailbreak|guard|safety)", re.IGNORECASE),
    "evidence_human_oversight_gateway": re.compile(
        r"(human|oversight|review|approval|escalat)", re.IGNORECASE),
    "evidence_continuous_monitoring": re.compile(
        r"(monitor|metric|health|alert|drift|anomal)", re.IGNORECASE),
    "evidence_incident_response": re.compile(
        r"(incident|recover|failover|backup|resilien)", re.IGNORECASE),
}


def _classify_test(name: str, classname: str) -> Optional[str]:
    """Classify a test into a compliance evidence category by name/classname."""
    text = f"{classname}.{name}"
    for evidence_fn, pattern in _EVIDENCE_PATTERNS.items():
        if pattern.search(text):
            return evidence_fn
    return None


def generate_junit_report(
    suites: List[TestSuite], framework: str,
) -> Dict[str, Any]:
    """Generate a compliance evidence report from JUnit test results.

    Maps test outcomes to testing/measurement controls.
    Tests with names matching compliance categories provide
    direct evidence for those controls.
    """
    normalised_fw = framework.replace("-", "_")

    total_tests = sum(s.tests for s in suites)
    total_passed = sum(s.passed for s in suites)
    total_failed = sum(s.failures for s in suites)
    total_errors = sum(s.errors for s in suites)
    total_skipped = sum(s.skipped for s in suites)
    total_time = sum(s.time for s in suites)
    pass_rate = round(total_passed / total_tests * 100, 1) if total_tests else 0.0

    # Classify tests by compliance evidence category
    evidence_map: Dict[str, Dict[str, Any]] = {}
    for suite in suites:
        for result in suite.results:
            cat = _classify_test(result.name, result.classname)
            if cat:
                if cat not in evidence_map:
                    evidence_map[cat] = {"passed": 0, "failed": 0, "total": 0, "tests": []}
                evidence_map[cat]["total"] += 1
                if result.status == "passed":
                    evidence_map[cat]["passed"] += 1
                elif result.status in ("failed", "error"):
                    evidence_map[cat]["failed"] += 1
                evidence_map[cat]["tests"].append({
                    "name": result.name,
                    "classname": result.classname,
                    "status": result.status,
                    "message": result.failure_message or result.error_message or "",
                })

    # Build controls
    controls = []

    # Overall test coverage
    if total_tests >= 10:
        test_status = "met" if pass_rate >= 90 else ("partial" if pass_rate >= 60 else "gap")
    elif total_tests > 0:
        test_status = "partial"
    else:
        test_status = "gap"

    controls.append({
        "controlId": "junit_test_coverage",
        "status": test_status,
        "requirement": "Automated test suites validate AI system behavior",
        "evidence": [
            f"{total_passed}/{total_tests} tests passed ({pass_rate}%)",
            f"{len(suites)} test suite{'s' if len(suites) != 1 else ''}",
            f"Execution time: {total_time:.1f}s",
        ],
        "evidence_fn": "evidence_performance_measurement",
    })

    # Per-category evidence controls
    for evidence_fn, data in sorted(evidence_map.items()):
        fn_label = evidence_fn.replace("evidence_", "").replace("_", " ").title()
        cat_rate = round(data["passed"] / data["total"] * 100, 1) if data["total"] else 0.0

        if data["failed"] > 0:
            status = "gap" if cat_rate < 50 else "partial"
        elif data["total"] > 0:
            status = "met"
        else:
            status = "gap"

        evidence_list = [f"{data['passed']}/{data['total']} {fn_label.lower()} tests passed"]
        gaps = [
            f"{t['classname']}.{t['name']}: {t['message'][:100]}"
            for t in data["tests"] if t["status"] in ("failed", "error")
        ][:5]

        controls.append({
            "controlId": f"junit_{evidence_fn}",
            "status": status,
            "requirement": f"Tests verify {fn_label.lower()} functionality",
            "evidence": evidence_list,
            "gaps": gaps,
            "evidence_fn": evidence_fn,
        })

    met = sum(1 for c in controls if c["status"] == "met")
    partial = sum(1 for c in controls if c["status"] == "partial")
    gap = sum(1 for c in controls if c["status"] == "gap")
    score = round((met + 0.5 * partial) / len(controls) * 100, 1) if controls else 0.0

    # Failed tests as specific findings
    failures = []
    for suite in suites:
        for r in suite.results:
            if r.status in ("failed", "error"):
                failures.append({
                    "suite": suite.name,
                    "test": r.name,
                    "classname": r.classname,
                    "status": r.status,
                    "message": (r.failure_message or r.error_message or "")[:200],
                })

    report = {
        "framework": normalised_fw,
        "source": "junit_import",
        "summary": {
            "met": met,
            "partial": partial,
            "gap": gap,
            "total": len(controls),
            "score": score,
        },
        "articles": [{
            "articleId": "junit_analysis",
            "label": "Test Results Analysis",
            "met": met,
            "partial": partial,
            "gap": gap,
            "controls": controls,
        }],
        "junitMetadata": {
            "suites": len(suites),
            "totalTests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "errors": total_errors,
            "skipped": total_skipped,
            "passRate": pass_rate,
            "executionTime": round(total_time, 2),
            "evidenceCategories": len(evidence_map),
        },
        "failures": failures[:50],
    }

    return report
