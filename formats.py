"""CI/CD output format converters — SARIF, JUnit XML, Markdown.

Each converter takes a report dict (from run_comply_scan) and returns
the appropriate format for native CI/CD integration.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional


# ── SARIF v2.1.0 ─────────────────────────────────────────────────────────

def to_sarif(report: dict) -> dict:
    """Convert a compliance report to SARIF v2.1.0 format.

    Maps: controls → rules, gaps/partial → results.
    """
    framework = report.get("framework", "unknown")
    scan_id = report.get("scanId", "")

    rules = []
    results = []
    rule_index = {}

    for article in report.get("articles", []):
        for ctrl in article.get("controls", []):
            ctrl_id = ctrl.get("controlId", "")
            rule_id = f"{framework}/{ctrl_id}"

            if rule_id not in rule_index:
                rule_index[rule_id] = len(rules)
                rules.append({
                    "id": rule_id,
                    "name": ctrl_id,
                    "shortDescription": {"text": ctrl.get("requirement", "")[:200]},
                    "fullDescription": {"text": ctrl.get("requirement", "")},
                    "helpUri": f"https://bespoketracker.dev/comply/{framework}/{ctrl_id}",
                    "properties": {
                        "articleId": article.get("articleId", ""),
                        "articleLabel": article.get("label", ""),
                    },
                })

            status = ctrl.get("status", "gap")
            if status == "met":
                continue  # Only report non-met controls

            level = "error" if status == "gap" else "warning"

            props = {
                "status": status,
                "evidence": ctrl.get("evidence", []),
                "gaps": ctrl.get("gaps", []),
            }

            # Include layer breakdown if available
            layers = ctrl.get("layers")
            if layers:
                props["layers"] = {
                    "code": layers.get("code", {}).get("status", ""),
                    "process": layers.get("process", {}).get("status", ""),
                    "traffic": layers.get("traffic", {}).get("status", ""),
                }
                props["combinedStatus"] = ctrl.get("combinedStatus", "")

            result = {
                "ruleId": rule_id,
                "ruleIndex": rule_index[rule_id],
                "level": level,
                "message": {
                    "text": ctrl.get("recommendation", "") or ctrl.get("requirement", ""),
                },
                "properties": props,
            }

            # Annotate regressions if present
            if report.get("regression", {}).get("regressionDetected"):
                new_gap_ids = {
                    g.get("controlId", "")
                    for g in report.get("regression", {}).get("newGaps", [])
                }
                if ctrl_id in new_gap_ids:
                    result["properties"]["isRegression"] = True

            results.append(result)

    summary = report.get("summary", {})

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "BespokeTracker Comply",
                    "version": "0.2.0",
                    "informationUri": "https://bespoketracker.dev/comply",
                    "rules": rules,
                },
            },
            "results": results,
            "invocations": [{
                "executionSuccessful": True,
                "properties": {
                    "scanId": scan_id,
                    "framework": framework,
                    "scanDepth": report.get("scanDepth", ""),
                    "score": summary.get("score", 0),
                    "met": summary.get("met", 0),
                    "partial": summary.get("partial", 0),
                    "gap": summary.get("gap", 0),
                    "total": summary.get("total", 0),
                },
            }],
        }],
    }


# ── JUnit XML ────────────────────────────────────────────────────────────

def to_junit(report: dict) -> str:
    """Convert a compliance report to JUnit XML format.

    Maps: articles → testsuites, controls → testcases.
    met = pass, partial/gap = failure.
    """
    framework = report.get("framework", "unknown")
    summary = report.get("summary", {})

    testsuites = ET.Element("testsuites")
    testsuites.set("name", f"Comply: {framework}")
    testsuites.set("tests", str(summary.get("total", 0)))
    testsuites.set("failures", str(summary.get("gap", 0) + summary.get("partial", 0)))
    testsuites.set("errors", "0")
    testsuites.set("time", "0")

    for article in report.get("articles", []):
        art_id = article.get("articleId", "")
        controls = article.get("controls", [])

        ts = ET.SubElement(testsuites, "testsuite")
        ts.set("name", f"{art_id}: {article.get('label', '')}")
        ts.set("tests", str(len(controls)))

        failures = sum(1 for c in controls if c.get("status") != "met")
        ts.set("failures", str(failures))
        ts.set("errors", "0")
        ts.set("time", "0")

        for ctrl in controls:
            tc = ET.SubElement(ts, "testcase")
            tc.set("name", ctrl.get("controlId", ""))
            tc.set("classname", f"comply.{framework}.{art_id}")

            status = ctrl.get("status", "gap")
            if status != "met":
                failure = ET.SubElement(tc, "failure")
                failure.set("type", status)
                failure.set("message", ctrl.get("requirement", ""))

                detail_parts = []
                rec = ctrl.get("recommendation", "")
                if rec:
                    detail_parts.append(f"Recommendation: {rec}")
                gaps = ctrl.get("gaps", [])
                if gaps:
                    detail_parts.append("Gaps:\n" + "\n".join(f"  - {g}" for g in gaps))
                evidence = ctrl.get("evidence", [])
                if evidence:
                    detail_parts.append("Evidence:\n" + "\n".join(f"  - {e}" for e in evidence))
                # Layer breakdown
                layers = ctrl.get("layers")
                if layers:
                    parts = []
                    for lname in ("code", "process", "traffic"):
                        ls = layers.get(lname, {}).get("status", "?")
                        parts.append(f"  {lname}: {ls}")
                    detail_parts.append("Layers:\n" + "\n".join(parts))
                failure.text = "\n\n".join(detail_parts) if detail_parts else ""

    return _xml_to_string(testsuites)


def _xml_to_string(element: ET.Element) -> str:
    """Convert an XML Element to a pretty string with declaration."""
    ET.indent(element, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        element, encoding="unicode"
    )


# ── Markdown ─────────────────────────────────────────────────────────────

def to_markdown(report: dict) -> str:
    """Convert a compliance report to Markdown (for PR comments)."""
    framework = report.get("framework", "unknown")
    summary = report.get("summary", {})
    score = summary.get("score", 0)
    met = summary.get("met", 0)
    partial = summary.get("partial", 0)
    gap = summary.get("gap", 0)
    total = summary.get("total", 0)

    lines = []
    lines.append(f"## Compliance Scan: {framework}")
    lines.append("")

    # Score badge
    if score >= 70:
        badge = "passing"
        color = "brightgreen"
    elif score >= 40:
        badge = "partial"
        color = "yellow"
    else:
        badge = "failing"
        color = "red"
    lines.append(f"**Score: {score:.1f}%** ({badge})")
    lines.append("")

    # Summary table
    lines.append(f"| Met | Partial | Gap | Total |")
    lines.append(f"|:---:|:-------:|:---:|:-----:|")
    lines.append(f"| {met} | {partial} | {gap} | {total} |")
    lines.append("")

    # Scan metadata
    lines.append(f"- **Target:** `{report.get('target', '')}`")
    lines.append(f"- **Depth:** {report.get('scanDepth', 'content')}")
    commit = report.get("commitSha", "")
    if commit:
        lines.append(f"- **Commit:** `{commit[:8]}`")
    model = report.get("model", {})
    lines.append(f"- **Files scanned:** {model.get('filesScanned', 0)}")
    lines.append("")

    # Regression info
    regression = report.get("regression")
    if regression and regression.get("regressionDetected"):
        lines.append("> **REGRESSION DETECTED**")
        new_gaps = regression.get("newGaps", [])
        lines.append(f"> {len(new_gaps)} new gap(s) introduced")
        lines.append("")

    # Per-article table
    lines.append("### Per-Article Breakdown")
    lines.append("")
    lines.append("| Article | Met | Partial | Gap |")
    lines.append("|---------|:---:|:-------:|:---:|")

    for article in report.get("articles", []):
        art_id = article.get("articleId", "")
        label = article.get("label", "")
        a_met = article.get("met", 0)
        a_partial = article.get("partial", 0)
        a_gap = article.get("gap", 0)
        lines.append(f"| {art_id}: {label} | {a_met} | {a_partial} | {a_gap} |")

    lines.append("")

    # Collapsible gap details
    gap_controls = []
    for article in report.get("articles", []):
        for ctrl in article.get("controls", []):
            if ctrl.get("status") != "met":
                gap_controls.append((article.get("articleId", ""), ctrl))

    if gap_controls:
        lines.append("<details>")
        lines.append(f"<summary>Gap Details ({len(gap_controls)} control(s))</summary>")
        lines.append("")

        for art_id, ctrl in gap_controls:
            status = ctrl.get("status", "gap").upper()
            ctrl_id = ctrl.get("controlId", "")
            req = ctrl.get("requirement", "")
            rec = ctrl.get("recommendation", "")
            layers = ctrl.get("layers")
            layer_str = ""
            if layers:
                parts = []
                for lname in ("code", "process", "traffic"):
                    ls = layers.get(lname, {}).get("status", "?")
                    parts.append(f"L{['code','process','traffic'].index(lname)+1}:{ls}")
                layer_str = f" [{' '.join(parts)}]"
            lines.append(f"**[{status}] {art_id}/{ctrl_id}**{layer_str}")
            lines.append(f"> {req}")
            if rec:
                lines.append(f">")
                lines.append(f"> *Recommendation:* {rec}")
            lines.append("")

        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by [BespokeTracker Comply](https://bespoketracker.dev/comply) "
                 f"at {report.get('generatedAt', '')[:19]}*")

    return "\n".join(lines)


def to_markdown_diff(diff: dict) -> str:
    """Convert a scan diff to Markdown (for PR regression comments)."""
    baseline = diff.get("baseline", {})
    current = diff.get("current", {})
    delta = diff.get("scoreDelta", 0)
    new_gaps = diff.get("newGaps", [])
    resolved = diff.get("resolvedGaps", [])
    regression = diff.get("regressionDetected", False)

    lines = []

    if regression:
        lines.append("## Compliance Regression Detected")
    else:
        lines.append("## Compliance Scan Comparison")
    lines.append("")

    # Score comparison
    lines.append("| | Baseline | Current | Delta |")
    lines.append("|---|:---:|:---:|:---:|")
    delta_str = f"+{delta:.1f}%" if delta > 0 else f"{delta:.1f}%"
    lines.append(f"| Score | {baseline.get('score', 0):.1f}% | {current.get('score', 0):.1f}% | {delta_str} |")
    lines.append("")

    if new_gaps:
        lines.append(f"### New Gaps ({len(new_gaps)})")
        lines.append("")
        for g in new_gaps:
            lines.append(f"- **{g.get('controlId', '')}**: {g.get('requirement', '')}")
        lines.append("")

    if resolved:
        lines.append(f"### Resolved ({len(resolved)})")
        lines.append("")
        for g in resolved:
            lines.append(f"- ~~{g.get('controlId', '')}~~: {g.get('requirement', '')}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Baseline: {baseline.get('scanId', '')} | "
                 f"Current: {current.get('scanId', '')}*")

    return "\n".join(lines)
