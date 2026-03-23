"""Report formatting — terminal, JSON, DOCX output."""
from __future__ import annotations

import json
import os
import sys
from typing import Optional


# ANSI color codes (disabled if not a TTY)
_USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    if _USE_COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text

def _green(t: str) -> str: return _c("32", t)
def _yellow(t: str) -> str: return _c("33", t)
def _red(t: str) -> str: return _c("31", t)
def _bold(t: str) -> str: return _c("1", t)
def _dim(t: str) -> str: return _c("2", t)

_STATUS_FN = {"met": _green, "partial": _yellow, "gap": _red}


def print_terminal_report(report: dict) -> None:
    """Print a colored summary to stdout."""
    summary = report.get("summary", {})
    framework = report.get("framework", "unknown")
    target = report.get("target", "")
    model = report.get("model", {})

    print()
    print(_bold(f"  BespokeTracker Comply — {framework}"))
    print(_dim(f"  Target: {target}"))
    print(_dim(f"  Scan depth: {report.get('scanDepth', 'content')}"))
    print(_dim(f"  Files scanned: {model.get('filesScanned', 0)}  |  "
              f"Features discovered: {model.get('featuresDiscovered', 0)}"))
    print()

    # Summary bar
    met = summary.get("met", 0)
    partial = summary.get("partial", 0)
    gap = summary.get("gap", 0)
    total = summary.get("total", 0)
    score = summary.get("score", 0)

    print(f"  Score: {_bold(f'{score}%')}  "
          f"({_green(f'{met} met')}  "
          f"{_yellow(f'{partial} partial')}  "
          f"{_red(f'{gap} gap')}  "
          f"/ {total} controls)")
    print()

    # Per-article breakdown
    for article in report.get("articles", []):
        art_id = article.get("articleId", "")
        art_label = article.get("label", "")
        art_met = article.get("met", 0)
        art_partial = article.get("partial", 0)
        art_gap = article.get("gap", 0)

        header = f"  Article {art_id}: {art_label}"
        counts = (f"{_green(str(art_met))} met  "
                  f"{_yellow(str(art_partial))} partial  "
                  f"{_red(str(art_gap))} gap")
        print(f"{_bold(header)}  [{counts}]")

        for ctrl in article.get("controls", []):
            status = ctrl.get("status", "gap")
            color_fn = _STATUS_FN.get(status, _red)
            badge = color_fn(f"[{status.upper():>7s}]")
            ctrl_id = ctrl.get("controlId", "")
            req = ctrl.get("requirement", "")
            # Truncate long requirements
            if len(req) > 80:
                req = req[:77] + "..."
            # Layer indicators if available
            layers = ctrl.get("layers")
            if layers:
                l1 = layers.get("code", {}).get("status", "?")
                l2 = layers.get("process", {}).get("status", "?")
                l3 = layers.get("traffic", {}).get("status", "?")
                layer_str = (
                    f" [{_STATUS_FN.get(l1, _dim)(f'L1:{l1}')} "
                    f"{_STATUS_FN.get(l2, _dim)(f'L2:{l2}')} "
                    f"{_STATUS_FN.get(l3, _dim)(f'L3:{l3}')}]"
                )
            else:
                layer_str = ""

            print(f"    {badge}  {ctrl_id} — {req}{layer_str}")

            # Show evidence summary for non-met controls
            if status != "met":
                rec = ctrl.get("recommendation", "")
                if rec:
                    print(f"             {_dim('→ ' + rec)}")

        print()

    # Footer
    report_path = report.get("_reportPath", "")
    if report_path:
        print(_dim(f"  Full report: {report_path}"))
    print()


def print_multi_framework_report(reports: list) -> None:
    """Print a combined summary for multi-framework scans, then per-framework details."""
    if not reports:
        return

    target = reports[0].get("target", "")
    depth = reports[0].get("scanDepth", "content")
    model = reports[0].get("model", {})

    print()
    print(_bold("  BespokeTracker Comply — Multi-Framework Scan"))
    print(_dim(f"  Target: {target}"))
    print(_dim(f"  Scan depth: {depth}"))
    print(_dim(f"  Files scanned: {model.get('filesScanned', 0)}  |  "
              f"Features discovered: {model.get('featuresDiscovered', 0)}"))
    print(_dim(f"  Frameworks: {len(reports)}"))
    print()

    # Summary table
    print(_bold("  Framework Summary"))
    print(_dim(f"  {'Framework':<20s} {'Score':>7s}  {'Met':>4s}  {'Partial':>7s}  {'Gap':>4s}  {'Total':>5s}"))
    print(_dim("  " + "-" * 55))

    for report in reports:
        fw = report.get("framework", "")
        summary = report.get("summary", {})
        score = summary.get("score", 0)
        met = summary.get("met", 0)
        partial = summary.get("partial", 0)
        gap = summary.get("gap", 0)
        total = summary.get("total", 0)

        if score >= 70:
            score_str = _green(f"{score:5.1f}%")
        elif score >= 40:
            score_str = _yellow(f"{score:5.1f}%")
        else:
            score_str = _red(f"{score:5.1f}%")

        print(f"  {fw:<20s} {score_str}  {_green(str(met)):>4s}  {_yellow(str(partial)):>7s}  {_red(str(gap)):>4s}  {total:>5d}")

    print()

    # Per-framework detail
    for report in reports:
        print(_bold(f"  --- {report.get('framework', '')} ---"))
        # Reuse single-framework report body (articles only)
        for article in report.get("articles", []):
            art_id = article.get("articleId", "")
            art_label = article.get("label", "")
            art_gap = article.get("gap", 0)
            if art_gap == 0:
                continue  # Only show articles with gaps in multi-report
            print(f"  {_bold(art_id)}: {art_label}  [{_red(str(art_gap))} gap(s)]")
            for ctrl in article.get("controls", []):
                if ctrl.get("status") != "met":
                    status = ctrl.get("status", "gap")
                    color_fn = _STATUS_FN.get(status, _red)
                    badge = color_fn(f"[{status.upper():>7s}]")
                    req = ctrl.get("requirement", "")
                    if len(req) > 70:
                        req = req[:67] + "..."
                    print(f"    {badge}  {ctrl.get('controlId', '')} — {req}")
        print()


def print_regression_summary(regression: dict) -> None:
    """Print a concise regression summary."""
    if not regression:
        return

    detected = regression.get("regressionDetected", False)
    new_gaps = regression.get("newGaps", [])
    resolved = regression.get("resolvedGaps", [])
    delta = regression.get("scoreDelta", 0)

    print()
    if detected:
        print(_red(_bold("  REGRESSION DETECTED")))
        print(f"  Score change: {_red(f'{delta:+.1f}%')}  |  "
              f"{_red(f'{len(new_gaps)} new gap(s)')}  |  "
              f"{_green(f'{len(resolved)} resolved')}")
        for g in new_gaps[:5]:
            print(f"    {_red('[NEW]')}  {g.get('controlId', '')} — {g.get('requirement', '')[:60]}")
        if len(new_gaps) > 5:
            print(f"    ... and {len(new_gaps) - 5} more")
    else:
        print(_green("  No regressions detected"))
        if resolved:
            print(f"  {_green(f'{len(resolved)} gap(s) resolved')}")
    print()


def print_frameworks_list(frameworks: list) -> None:
    """Print the list of supported frameworks."""
    print()
    print(_bold("  Supported Compliance Frameworks"))
    print()
    for fw in frameworks:
        fid = fw.get("framework", fw.get("id", ""))
        name = fw.get("label", fw.get("name", fid))
        version = fw.get("version", "")
        # controlCount from get_framework_details, or count from articles
        control_count = fw.get("controlCount", None)
        if control_count is None:
            articles = fw.get("articles", [])
            control_count = sum(len(a.get("controls", [])) for a in articles) if articles else "?"
        print(f"  {_bold(fid):30s}  {name} {_dim(version)}")
        print(f"  {'':30s}  {control_count} controls")
        print()


def print_history_table(scans: list) -> None:
    """Print a table of past scans."""
    print()
    print(_bold("  Scan History"))
    print()

    # Header
    hdr = f"  {'ID':<14s} {'Score':>6s}  {'Framework':<16s} {'Depth':<10s} {'Date':<20s} {'Repo'}"
    print(_dim(hdr))
    print(_dim("  " + "-" * 90))

    for s in scans:
        scan_id = s.get("id", "")[:12]
        score = s.get("score", 0)
        framework = s.get("framework", "")
        depth = s.get("scan_depth", "")
        created = s.get("created_at", "")[:19]
        repo = s.get("repo_url", "") or s.get("repo_path", "")
        baseline = " *" if s.get("is_baseline") else ""

        # Color score
        if score >= 70:
            score_str = _green(f"{score:5.1f}%")
        elif score >= 40:
            score_str = _yellow(f"{score:5.1f}%")
        else:
            score_str = _red(f"{score:5.1f}%")

        # Truncate repo path
        if len(repo) > 40:
            repo = "..." + repo[-37:]

        print(f"  {scan_id:<14s} {score_str}  {framework:<16s} {depth:<10s} {created:<20s} {repo}{baseline}")

    print()
    print(_dim(f"  {len(scans)} scan(s) shown. * = baseline"))
    print()


def print_diff_report(diff: dict) -> None:
    """Print a colored diff between two scans."""
    baseline = diff.get("baseline", {})
    current = diff.get("current", {})
    delta = diff.get("scoreDelta", 0)

    print()
    print(_bold("  Scan Diff"))
    print()
    print(f"  Baseline:  {baseline.get('scanId', ''):<14s}  score: {baseline.get('score', 0):.1f}%  ({baseline.get('generatedAt', '')[:19]})")
    print(f"  Current:   {current.get('scanId', ''):<14s}  score: {current.get('score', 0):.1f}%  ({current.get('generatedAt', '')[:19]})")
    print()

    # Score delta
    if delta > 0:
        print(f"  Score change: {_green(f'+{delta:.1f}%')}")
    elif delta < 0:
        print(f"  Score change: {_red(f'{delta:.1f}%')}")
    else:
        print(f"  Score change: {_dim('no change')}")
    print()

    # New gaps
    new_gaps = diff.get("newGaps", [])
    if new_gaps:
        print(_red(f"  New gaps ({len(new_gaps)}):"))
        for g in new_gaps:
            cid = g.get("controlId", "")
            req = g.get("requirement", "")
            if len(req) > 70:
                req = req[:67] + "..."
            print(f"    {_red('[NEW GAP]')}  {cid} — {req}")
        print()

    # Resolved gaps
    resolved = diff.get("resolvedGaps", [])
    if resolved:
        print(_green(f"  Resolved ({len(resolved)}):"))
        for g in resolved:
            cid = g.get("controlId", "")
            req = g.get("requirement", "")
            if len(req) > 70:
                req = req[:67] + "..."
            print(f"    {_green('[RESOLVED]')}  {cid} — {req}")
        print()

    # Changed controls
    changed = diff.get("changed", [])
    other_changes = [c for c in changed if c not in new_gaps and c not in resolved]
    if other_changes:
        print(f"  Changed ({len(other_changes)}):")
        for c in other_changes:
            cid = c.get("controlId", "")
            old = c.get("old", "")
            new = c.get("new", "")
            color_fn = _STATUS_FN.get(new, _dim)
            print(f"    {cid}: {old} -> {color_fn(new)}")
        print()

    if diff.get("regressionDetected"):
        print(_red(_bold("  REGRESSION DETECTED")))
    else:
        print(_green("  No regressions"))
    print()


def build_cross_framework_matrix(reports: list) -> dict:
    """Build a cross-framework compliance matrix showing control overlap.

    Groups controls by evidence function (the underlying capability being tested)
    and shows which frameworks each capability satisfies.

    Returns
    -------
    dict
        {capabilities: [{name, evidence_fn, frameworks: [{id, control, status}]}],
         summary: {totalCapabilities, frameworkScores}}
    """
    # Group controls by evidence_fn across all frameworks
    capability_map = {}  # evidence_fn -> {name, frameworks: [{id, control, status}]}

    for report in reports:
        fw = report.get("framework", "")
        for article in report.get("articles", []):
            for ctrl in article.get("controls", []):
                evidence_fn = ctrl.get("evidence_fn", "")
                if not evidence_fn:
                    continue
                if evidence_fn not in capability_map:
                    capability_map[evidence_fn] = {
                        "name": _capability_name(evidence_fn),
                        "evidence_fn": evidence_fn,
                        "frameworks": [],
                    }
                capability_map[evidence_fn]["frameworks"].append({
                    "framework": fw,
                    "controlId": ctrl.get("controlId", ""),
                    "status": ctrl.get("status", "gap"),
                    "requirement": ctrl.get("requirement", "")[:120],
                })

    capabilities = sorted(capability_map.values(), key=lambda c: c["name"])

    # Build per-framework scores
    fw_scores = {}
    for report in reports:
        fw = report.get("framework", "")
        summary = report.get("summary", {})
        fw_scores[fw] = {
            "framework": fw,
            "score": summary.get("score", 0),
            "met": summary.get("met", 0),
            "partial": summary.get("partial", 0),
            "gap": summary.get("gap", 0),
            "total": summary.get("total", 0),
        }

    return {
        "capabilities": capabilities,
        "frameworkScores": fw_scores,
        "totalCapabilities": len(capabilities),
        "frameworks": [r.get("framework", "") for r in reports],
    }


def print_cross_framework_matrix(matrix: dict) -> None:
    """Print the cross-framework matrix to terminal."""
    frameworks = matrix.get("frameworks", [])
    capabilities = matrix.get("capabilities", [])
    fw_scores = matrix.get("frameworkScores", {})

    print()
    print(_bold("  Cross-Framework Compliance Matrix"))
    print()

    # Header
    fw_headers = "  ".join(f"{fw[:12]:>12s}" for fw in frameworks)
    print(f"  {'Capability':<30s}  {fw_headers}")
    print(_dim("  " + "-" * (32 + 14 * len(frameworks))))

    # Rows
    for cap in capabilities:
        name = cap["name"][:28]
        statuses = []
        for fw in frameworks:
            fw_ctrls = [c for c in cap["frameworks"] if c["framework"] == fw]
            if fw_ctrls:
                status = fw_ctrls[0]["status"]
                color_fn = _STATUS_FN.get(status, _dim)
                statuses.append(color_fn(f"{status:>12s}"))
            else:
                statuses.append(_dim(f"{'n/a':>12s}"))
        row = "  ".join(statuses)
        print(f"  {name:<30s}  {row}")

    print()

    # Summary row
    print(_bold("  Scores"))
    scores = []
    for fw in frameworks:
        score = fw_scores.get(fw, {}).get("score", 0)
        if score >= 70:
            scores.append(_green(f"{score:>11.1f}%"))
        elif score >= 40:
            scores.append(_yellow(f"{score:>11.1f}%"))
        else:
            scores.append(_red(f"{score:>11.1f}%"))
    print(f"  {'':30s}  {'  '.join(scores)}")
    print()


# Public alias — imported by comply.mapping
CAPABILITY_NAMES = _CAPABILITY_NAMES = {
    "evidence_audit_logging": "Audit Logging",
    "evidence_traceability": "Traceability",
    "evidence_risk_assessment_gateway": "Risk Assessment",
    "evidence_risk_categorization": "Risk Categorization",
    "evidence_risk_register_auto": "Risk Register",
    "evidence_transparency_disclosure": "Transparency",
    "evidence_transparency_logging": "Transparency Logging",
    "evidence_continuous_monitoring": "Continuous Monitoring",
    "evidence_performance_measurement": "Testing & Measurement",
    "evidence_governance_policy": "Governance Policy",
    "evidence_governance_program": "Governance Program",
    "evidence_logical_access": "Access Control",
    "evidence_data_handling": "Data Handling",
    "evidence_change_management": "Change Management",
    "evidence_incident_response": "Incident Response",
    "evidence_human_oversight_gateway": "Human Oversight",
    "evidence_ai_system_inventory": "AI System Inventory",
    "evidence_impact_documentation": "Impact Assessment",
    "evidence_consumer_notification": "Consumer Notification",
    "evidence_availability_controls": "Availability Controls",
    "evidence_retention_compliance": "Data Retention",
}


def _capability_name(evidence_fn: str) -> str:
    return _CAPABILITY_NAMES.get(evidence_fn, evidence_fn.replace("evidence_", "").replace("_", " ").title())


def print_mapping_table(mapping: dict) -> None:
    """Print the static control mapping table (no scan data needed)."""
    capabilities = mapping.get("capabilities", [])
    frameworks = mapping.get("frameworks", [])

    print()
    print(_bold("  Cross-Framework Control Mapping"))
    print(_dim(f"  {mapping.get('totalCapabilities', 0)} capabilities across "
              f"{len(frameworks)} frameworks, "
              f"{mapping.get('totalControls', 0)} controls total"))
    print()

    for cap in capabilities:
        name = cap["name"]
        fw_count = cap.get("framework_count", 0)
        header = f"  {_bold(name)}  ({fw_count} framework{'s' if fw_count != 1 else ''})"
        print(header)
        for ctrl in cap.get("controls", []):
            fw = ctrl.get("framework", "")
            cid = ctrl.get("controlId", "")
            req = ctrl.get("requirement", "")
            if len(req) > 70:
                req = req[:67] + "..."
            print(f"    {_dim(fw + ':')} {cid} — {req}")
        print()


def print_remediation_priorities(priorities: list) -> None:
    """Print remediation priorities — 'fix X to improve N frameworks'."""
    if not priorities:
        print()
        print(_green("  No remediation priorities — all controls met."))
        print()
        return

    print()
    print(_bold("  Remediation Priorities"))
    print(_dim("  Fix one capability to improve multiple frameworks"))
    print()

    for i, p in enumerate(priorities, 1):
        name = p["name"]
        impact = p["impact_count"]
        fws = ", ".join(p["frameworks"])

        if impact >= 3:
            badge = _red(f"[{impact} frameworks]")
        elif impact >= 2:
            badge = _yellow(f"[{impact} frameworks]")
        else:
            badge = _dim(f"[{impact} framework]")

        print(f"  {i}. {_bold(name)}  {badge}")
        print(f"     {_dim(fws)}")
        for ctrl in p.get("controls", [])[:3]:
            status = ctrl.get("status", "gap")
            color_fn = _STATUS_FN.get(status, _red)
            print(f"     {color_fn(f'[{status.upper():>7s}]')}  "
                  f"{ctrl.get('framework', '')}:{ctrl.get('controlId', '')}")
        extra = len(p.get("controls", [])) - 3
        if extra > 0:
            print(f"     {_dim(f'... and {extra} more')}")
        print()


def write_json_report(report: dict, output_path: str) -> str:
    """Write the JSON report. Returns the file path."""
    clean = {k: v for k, v in report.items() if not k.startswith("_")}
    with open(output_path, "w") as f:
        json.dump(clean, f, indent=2, default=str)
    return output_path


def write_audit_bundle(framework: str, output_dir: str) -> Optional[str]:
    """Write a ZIP audit bundle. Returns path or None."""
    from comply.scanner import generate_audit_bundle
    bundle = generate_audit_bundle(framework)
    if bundle is None:
        return None
    path = os.path.join(output_dir, f"audit_bundle_{framework}.zip")
    with open(path, "wb") as f:
        f.write(bundle)
    return path


def write_docx_report(framework: str, output_dir: str) -> Optional[str]:
    """Write a DOCX report. Returns path or None."""
    from comply.scanner import generate_docx_report
    docx_bytes = generate_docx_report(framework)
    if docx_bytes is None:
        return None
    path = os.path.join(output_dir, f"compliance_report_{framework}.docx")
    with open(path, "wb") as f:
        f.write(docx_bytes)
    return path
