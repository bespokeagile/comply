"""
Comply MCP Server — exposes compliance scanning via Model Context Protocol.

Usage:
    python -m comply.mcp_server
    # Or via wrapper: bash comply/run_mcp.sh

Registers ~13 tools for scanning, history, remediation, gating, and more.
All tools return JSON strings suitable for LLM consumption.
"""

import json
import traceback
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Comply",
    instructions="""\
Comply is an AI compliance scanner. It scans codebases against 10 compliance \
frameworks (117 controls) and produces evidence-backed posture reports with \
remediation guidance.

## How to guide the user

1. **Scope discovery**: When a user mentions compliance, ask what kind of \
software they build and infer applicable frameworks. Don't assume -- a \
healthcare app needs HIPAA, not EU AI Act. If unsure, use comply_frameworks \
to show all options.

2. **Prerequisites**: If the target is a remote repo, the user needs a local \
clone or a GitHub MCP server configured. Walk them through setup if needed.

3. **Progressive refinement**: Start with one repo and one framework. Expand \
after first success. Don't overwhelm with multi-framework scans upfront.

4. **Plain language results**: Explain findings in business terms, not control \
IDs. "Your AI system lacks a human oversight mechanism" is better than \
"Article 14, Control 14.1: gap".

5. **Remediation guidance**: After showing results, proactively offer \
comply_remediate to generate a prioritized fix list. Explain what "compliant" \
looks like concretely for each gap.

6. **Next steps**: After a scan, suggest: remediation roadmap (comply_remediate), \
cross-framework comparison (comply_overlap), baseline setting \
(comply_baseline_set) for tracking progress, or CI/CD gating (comply_gate).

## Recommended tool chains

- **Quick check**: comply_frameworks -> comply_scan -> summarize results
- **Deep dive**: comply_scan -> comply_get_scan (full details) -> comply_remediate
- **Progress tracking**: comply_scan -> comply_baseline_set -> (later) comply_scan \
-> comply_diff to see what changed
- **CI/CD integration**: comply_gate for pass/fail decisions
- **Export**: comply_export with format=sarif for GitHub/GitLab, junit for CI, \
markdown for PR comments
""",
)


def _json(obj: object) -> str:
    """Serialize to compact JSON, handling non-serializable types."""
    def _default(o):
        if hasattr(o, "isoformat"):
            return o.isoformat()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)
    return json.dumps(obj, default=_default, indent=2)


def _err(e: Exception) -> str:
    return _json({"error": str(e), "type": type(e).__name__})


# ---------------------------------------------------------------------------
# Tool 1: List frameworks
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_frameworks() -> str:
    """List all supported compliance frameworks with control counts and descriptions."""
    try:
        from comply.scanner import list_frameworks
        frameworks = list_frameworks()
        return _json({"frameworks": frameworks, "count": len(frameworks)})
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 1b: Suggest frameworks by jurisdiction or domain
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_suggest_frameworks(description: str) -> str:
    """Suggest compliance frameworks based on a jurisdiction or domain description.

    Examples:
        "I build healthcare AI in the EU" -> eu_ai_act, iso_42001
        "California-based AI chatbot" -> california_sb_942, california_ab_2013, soc2_ai
        "AI security review" -> owasp_llm_top10, owasp_agentic_top10, nist_ai_rmf

    Args:
        description: Natural language description of jurisdiction, industry, or domain.
    """
    try:
        from comply.mapping import JURISDICTION_PROFILES, resolve_frameworks

        desc_lower = description.lower()
        matches = []

        # Check each profile for keyword matches
        for pid, profile in JURISDICTION_PROFILES.items():
            keywords = [pid] + profile["label"].lower().split()
            if any(kw in desc_lower for kw in keywords):
                matches.append({
                    "profile": pid,
                    "label": profile["label"],
                    "frameworks": profile["frameworks"],
                    "description": profile["description"],
                })

        # Also check for specific framework mentions
        framework_keywords = {
            "owasp": "security",
            "llm": "security",
            "agentic": "security",
            "soc": "us",
            "nist": "us",
            "iso": "eu",
            "ai act": "eu",
            "hipaa": "insurance",
            "healthcare": "insurance",
            "insurance": "insurance",
            "california": "us_california",
            "colorado": "us_colorado",
            "global": "global",
            "multinational": "global",
        }
        for keyword, profile_id in framework_keywords.items():
            if keyword in desc_lower and not any(m["profile"] == profile_id for m in matches):
                profile = JURISDICTION_PROFILES.get(profile_id)
                if profile:
                    matches.append({
                        "profile": profile_id,
                        "label": profile["label"],
                        "frameworks": profile["frameworks"],
                        "description": profile["description"],
                    })

        if not matches:
            # Default to global if nothing matches
            profile = JURISDICTION_PROFILES["global"]
            matches.append({
                "profile": "global",
                "label": profile["label"],
                "frameworks": profile["frameworks"],
                "description": profile["description"],
                "note": "No specific jurisdiction matched; showing comprehensive global coverage.",
            })

        return _json({"suggestions": matches, "count": len(matches)})
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 2: Run a scan
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_scan(
    target: str,
    framework: str = "eu-ai-act",
    depth: str = "content",
    max_files: int = 500,
) -> str:
    """Run a compliance scan on a codebase.

    Args:
        target: Path to repo or git URL to scan.
        framework: Framework ID (e.g. eu-ai-act, nist-ai-rmf, iso-42001). Comma-separated for multi-framework.
        depth: Scan depth — structure, content, or semantic. Semantic requires an LLM key.
        max_files: Maximum files to analyze (default 500).

    Returns:
        Scan ID, score summary, and per-article breakdown. For long scans, this may take 1-2 minutes.
    """
    try:
        from comply.scanner import run_comply_scan, run_comply_scan_multi

        frameworks = [f.strip() for f in framework.split(",")]
        if len(frameworks) > 1:
            reports = run_comply_scan_multi(
                target=target,
                frameworks=frameworks,
                scan_depth=depth,
                max_files=max_files,
            )
            summaries = []
            for r in reports:
                summaries.append({
                    "scanId": r.get("scanId"),
                    "framework": r.get("framework"),
                    "score": r.get("summary", {}).get("score"),
                    "met": r.get("summary", {}).get("met"),
                    "partial": r.get("summary", {}).get("partial"),
                    "gap": r.get("summary", {}).get("gap"),
                    "total": r.get("summary", {}).get("total"),
                })
            return _json({"scans": summaries, "count": len(summaries)})
        else:
            report = run_comply_scan(
                target=target,
                framework=frameworks[0],
                scan_depth=depth,
                max_files=max_files,
            )
            summary = report.get("summary", {})
            scan_id = report.get("scanId")
            articles = []
            for a in report.get("articles", []):
                articles.append({
                    "articleId": a.get("articleId"),
                    "label": a.get("label"),
                    "met": a.get("met"),
                    "partial": a.get("partial"),
                    "gap": a.get("gap"),
                })

            # Notify dashboard (fire-and-forget)
            try:
                from comply.bridge import notify_dashboard
                notify_dashboard("scan-complete", {"scanId": scan_id})
            except Exception:
                pass

            import os as _os
            port = int(_os.environ.get("COMPLY_PORT", "8001"))
            dashboard_url = f"http://127.0.0.1:{port}/#/detail/{scan_id}"

            # Only include dashboardUrl if server is reachable
            result = {
                "scanId": scan_id,
                "framework": report.get("framework"),
                "target": report.get("target"),
                "score": summary.get("score"),
                "met": summary.get("met"),
                "partial": summary.get("partial"),
                "gap": summary.get("gap"),
                "total": summary.get("total"),
                "articles": articles,
            }
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                result["dashboardUrl"] = dashboard_url
            except Exception:
                pass  # Server not running; omit dashboardUrl
            return _json(result)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 3: Scan history
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_history(
    repo: str = "",
    framework: str = "",
    limit: int = 10,
) -> str:
    """Show past scan results, optionally filtered by repo or framework.

    Args:
        repo: Filter by repository path (optional).
        framework: Filter by framework ID (optional).
        limit: Max results to return (default 10).
    """
    try:
        from comply.store import list_scans
        scans = list_scans(
            repo=repo or None,
            framework=framework or None,
            limit=limit,
        )
        results = []
        for s in scans:
            results.append({
                "scanId": s.get("id") or s.get("scan_id") or s.get("scanId"),
                "framework": s.get("framework"),
                "repo": s.get("repo_path") or s.get("repo") or s.get("target"),
                "score": s.get("score"),
                "createdAt": s.get("created_at") or s.get("createdAt"),
            })
        return _json({"scans": results, "count": len(results)})
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 4: Get scan details
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_get_scan(scan_id: str) -> str:
    """Get full details of a specific scan by its ID.

    Args:
        scan_id: The scan ID (returned from comply_scan or comply_history).
    """
    try:
        from comply.store import get_scan
        scan = get_scan(scan_id)
        if not scan:
            return _json({"error": f"Scan {scan_id} not found"})
        report = scan.get("report", scan) if isinstance(scan, dict) else {}
        summary = scan.get("summary", {}) or report.get("summary", {})
        articles = []
        for a in report.get("articles", []):
            controls = []
            for c in a.get("controls", []):
                controls.append({
                    "controlId": c.get("controlId"),
                    "status": c.get("status") or c.get("combinedStatus"),
                    "requirement": c.get("requirement", "")[:200],
                    "recommendation": c.get("recommendation", "")[:200],
                })
            articles.append({
                "articleId": a.get("articleId"),
                "label": a.get("label"),
                "met": a.get("met"),
                "partial": a.get("partial"),
                "gap": a.get("gap"),
                "controls": controls,
            })
        return _json({
            "scanId": report.get("scanId") or scan.get("id"),
            "framework": scan.get("framework") or report.get("framework"),
            "target": report.get("target") or scan.get("repo_path"),
            "generatedAt": report.get("generatedAt"),
            "score": summary.get("score"),
            "met": summary.get("met"),
            "partial": summary.get("partial"),
            "gap": summary.get("gap"),
            "total": summary.get("total"),
            "articles": articles,
        })
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 5: Diff two scans
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_diff(scan_id_1: str, scan_id_2: str) -> str:
    """Compare two scans and show what changed (score delta, control changes).

    Args:
        scan_id_1: The earlier/baseline scan ID.
        scan_id_2: The later/current scan ID.
    """
    try:
        from comply.store import get_scan
        from comply.diff_utils import _compute_diff

        s1 = get_scan(scan_id_1)
        s2 = get_scan(scan_id_2)
        if not s1:
            return _json({"error": f"Scan {scan_id_1} not found"})
        if not s2:
            return _json({"error": f"Scan {scan_id_2} not found"})

        diff = _compute_diff(s1.get("report", s1), s2.get("report", s2))
        return _json(diff)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 6: Remediation roadmap
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_remediate(scan_id: str) -> str:
    """Generate a prioritized remediation roadmap for a scan — what to fix first and why.

    Args:
        scan_id: The scan ID to generate remediation for.
    """
    try:
        from comply.store import get_scan
        from comply.remediation import generate_remediations

        scan = get_scan(scan_id)
        if not scan:
            return _json({"error": f"Scan {scan_id} not found"})

        report = scan.get("report", {})
        articles = report.get("articles", [])
        codebase_graph = report.get("model", {}).get("codebaseGraph", {})
        framework = scan.get("framework", "") or report.get("framework", "")
        summary = scan.get("summary", {}) or report.get("summary", {})

        remediations = generate_remediations(
            articles=articles,
            codebase_graph=codebase_graph,
            framework=framework,
            summary=summary,
        )

        items = []
        for r in remediations:
            items.append({
                "controlId": r.get("controlId"),
                "effort": r.get("effort"),
                "scoreDelta": r.get("score_delta"),
                "action": r.get("action", "")[:300],
                "summary": r.get("summary", "")[:200],
                "strategy": r.get("strategy"),
            })

        # Notify dashboard to show remediation tab (fire-and-forget)
        try:
            from comply.bridge import notify_dashboard
            notify_dashboard("navigate", {"route": f"#/detail/{scan_id}"})
        except Exception:
            pass

        return _json({
            "scanId": scan_id,
            "framework": framework,
            "remediations": items,
            "count": len(items),
        })
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 7: CI/CD gate
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_gate(
    target: str,
    framework: str = "eu-ai-act",
    min_score: float = 0,
    fail_on_regression: bool = False,
    max_gaps: int = -1,
) -> str:
    """Run a compliance gate check — pass/fail decision for CI/CD pipelines.

    Args:
        target: Path to repo to evaluate.
        framework: Framework ID (default eu-ai-act).
        min_score: Minimum score to pass (0-100).
        fail_on_regression: Fail if score regressed vs baseline.
        max_gaps: Maximum critical gaps allowed (-1 = unlimited).
    """
    try:
        from comply.gate import run_gate
        decision = run_gate(
            repo_path=target,
            framework=framework,
            threshold_score=min_score,
            fail_on_regression=fail_on_regression,
            max_critical_gaps=max_gaps,
        )
        return _json(decision)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 8: Cross-framework overlap
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_overlap(frameworks: str = "") -> str:
    """Show control overlap between compliance frameworks — fix once, satisfy many.

    Args:
        frameworks: Comma-separated framework IDs (empty = all frameworks).
    """
    try:
        from comply.scanner import list_frameworks
        from comply.report import build_cross_framework_matrix

        fw_list = [f.strip() for f in frameworks.split(",") if f.strip()] if frameworks else None

        all_fw = list_frameworks()
        if fw_list:
            all_fw = [f for f in all_fw if f.get("id") in fw_list]

        # Build overlap from framework definitions
        matrix = build_cross_framework_matrix([])
        # If no scans, return framework-level info
        result = {
            "frameworks": [f.get("id") for f in all_fw],
            "count": len(all_fw),
        }
        if matrix:
            result["matrix"] = matrix
        return _json(result)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 9: Forecast
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_forecast(
    repo: str,
    framework: str = "eu-ai-act",
    weeks: int = 8,
    target_score: float = 80.0,
) -> str:
    """Project compliance score trends based on scan history.

    Args:
        repo: Repository path to forecast.
        framework: Framework ID (default eu-ai-act).
        weeks: Projection horizon in weeks (default 8).
        target_score: Target score for timeline estimation (default 80).
    """
    try:
        from comply.forecast import forecast_score
        result = forecast_score(
            repo=repo,
            framework=framework,
            weeks=weeks,
            target_score=target_score,
        )
        return _json(result)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 10: Baseline management
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_baseline_set(scan_id: str) -> str:
    """Set a scan as the baseline for future regression detection.

    Args:
        scan_id: Scan ID to set as baseline.
    """
    try:
        from comply.store import set_baseline
        ok = set_baseline(scan_id)
        if ok:
            return _json({"status": "ok", "message": f"Baseline set to {scan_id}"})
        return _json({"error": f"Failed to set baseline for scan {scan_id}"})
    except Exception as e:
        return _err(e)


@mcp.tool()
def comply_baseline_show(repo: str, framework: str) -> str:
    """Show the current baseline for a repo+framework combination.

    Args:
        repo: Repository path.
        framework: Framework ID.
    """
    try:
        from comply.store import get_baseline
        baseline = get_baseline(repo, framework)
        if not baseline:
            return _json({"status": "none", "message": f"No baseline set for {repo} / {framework}"})
        return _json({
            "scanId": baseline.get("scan_id") or baseline.get("scanId"),
            "score": baseline.get("score"),
            "createdAt": baseline.get("created_at") or baseline.get("createdAt"),
        })
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 11: Export
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_export(scan_id: str, format: str = "json") -> str:
    """Export a scan report in a specific format.

    Args:
        scan_id: Scan ID to export.
        format: Output format — json, sarif, junit, or markdown.
    """
    try:
        from comply.store import get_scan
        scan = get_scan(scan_id)
        if not scan:
            return _json({"error": f"Scan {scan_id} not found"})

        report = scan.get("report", scan)
        if format == "json":
            return _json(scan)
        elif format == "sarif":
            from comply.formats import to_sarif
            return _json(to_sarif(report))
        elif format == "junit":
            from comply.formats import to_junit
            return to_junit(report)
        elif format == "markdown":
            from comply.formats import to_markdown
            return to_markdown(report)
        else:
            return _json({"error": f"Unknown format: {format}. Use json, sarif, junit, or markdown."})
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 12: Posture
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_posture(framework: str = "") -> str:
    """Get overall compliance posture — latest scores across all scanned repos.

    Args:
        framework: Filter by framework ID (optional, empty = all).
    """
    try:
        from comply.store import list_scans, get_scan_statistics

        stats = get_scan_statistics()
        recent = list_scans(
            framework=framework or None,
            limit=20,
        )
        repos = {}
        for s in recent:
            repo = s.get("repo_path") or s.get("repo") or s.get("target") or "unknown"
            fw = s.get("framework", "unknown")
            key = f"{repo}::{fw}"
            if key not in repos:
                repos[key] = {
                    "repo": repo,
                    "framework": fw,
                    "score": s.get("score"),
                    "scanId": s.get("id") or s.get("scan_id") or s.get("scanId"),
                    "createdAt": s.get("created_at") or s.get("createdAt"),
                }
        return _json({
            "statistics": stats,
            "latestByRepo": list(repos.values()),
        })
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 13: Narrate
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_narrate(scan_id: str) -> str:
    """Generate an LLM-powered narrative summary of a scan — human-readable compliance story.

    Args:
        scan_id: Scan ID to narrate. Requires an LLM key to be configured.
    """
    try:
        from comply.store import get_scan
        from comply.narration import narrate_scan, estimate_narration_cost

        scan = get_scan(scan_id)
        if not scan:
            return _json({"error": f"Scan {scan_id} not found"})

        report = scan.get("report", scan)
        cost = estimate_narration_cost(report)
        narrative = narrate_scan(report)
        return _json({
            "scanId": scan_id,
            "narrative": narrative,
            "estimatedCost": cost,
        })
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tool 14: Show in dashboard (co-pilot)
# ---------------------------------------------------------------------------

@mcp.tool()
def comply_show(
    scan_id: str,
    control_id: str = "",
    article_id: str = "",
) -> str:
    """Open a scan in the Comply dashboard, optionally highlighting a specific control.

    Use this to visually point a developer to the exact control or article
    being discussed. Requires the Comply server to be running with the
    dashboard open in a browser.

    Args:
        scan_id: Scan ID to display in the dashboard.
        control_id: Optional control ID to highlight (e.g. "14.1").
        article_id: Optional article ID to expand (e.g. "Article 14").
    """
    try:
        from comply.bridge import notify_dashboard
        import os

        port = int(os.environ.get("COMPLY_PORT", "8001"))
        base = f"http://127.0.0.1:{port}"

        if control_id or article_id:
            notify_dashboard("highlight", {
                "scanId": scan_id,
                "controlId": control_id,
                "articleId": article_id,
            })
        else:
            notify_dashboard("navigate", {
                "route": f"#/detail/{scan_id}",
            })

        # Build deep link URL
        params = []
        if control_id:
            params.append(f"control={control_id}")
        if article_id:
            params.append(f"article={article_id}")
        qs = f"?{'&'.join(params)}" if params else ""
        dashboard_url = f"{base}/#/detail/{scan_id}{qs}"

        # Check if server is reachable before claiming navigation
        server_up = False
        try:
            import urllib.request
            urllib.request.urlopen(f"{base}/health", timeout=1)
            server_up = True
        except Exception:
            pass

        result = {"status": "ok" if server_up else "server_not_running"}
        if server_up:
            result["dashboardUrl"] = dashboard_url
            result["message"] = f"Dashboard navigated to scan {scan_id}" + (
                f", highlighting {control_id}" if control_id else ""
            )
        else:
            result["message"] = (
                "Comply server is not running. Start it with: bespoketracker-comply serve\n"
                f"Then visit: {dashboard_url}"
            )
        return _json(result)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _seed_demo_scans():
    """Seed demo catalog scans into the store if it's empty.

    Reads from comply/dashboard/catalog/*.json and persists each scan
    so that comply_history and comply_posture return useful data on first
    MCP connection without requiring a real scan.
    """
    import os

    try:
        from comply.store import list_scans, save_scan
        existing = list_scans(limit=1)
        if existing:
            return  # store already has data

        catalog_dir = os.path.join(
            os.path.dirname(__file__), "dashboard", "catalog",
        )
        index_path = os.path.join(catalog_dir, "catalog_index.json")
        if not os.path.isfile(index_path):
            return

        with open(index_path) as f:
            index = json.load(f)

        seeded = 0
        for fw_key, fw_info in index.get("frameworks", {}).items():
            fw_file = os.path.join(catalog_dir, fw_info["file"])
            if not os.path.isfile(fw_file):
                continue
            with open(fw_file) as f:
                fw_data = json.load(f)
            for scan in fw_data.get("scans", []):
                report = scan.get("report", {})
                if not report:
                    continue
                # Ensure required fields exist
                report.setdefault("scanId", scan.get("id", ""))
                report.setdefault("framework", scan.get("framework", fw_key))
                report.setdefault("repoPath", scan.get("url", ""))
                report.setdefault("target", scan.get("url", ""))
                report.setdefault("scanDepth", scan.get("depth", "content"))
                report.setdefault("generatedAt", scan.get("timestamp", ""))
                save_scan(report)
                seeded += 1

        if seeded:
            import logging
            logging.getLogger(__name__).info(
                "Seeded %d demo scans from catalog", seeded,
            )
    except Exception:
        pass  # non-fatal — MCP works fine without demo data


def _run_mcp_server():
    """Start the Comply MCP server."""
    _seed_demo_scans()
    mcp.run()


if __name__ == "__main__":
    _run_mcp_server()
