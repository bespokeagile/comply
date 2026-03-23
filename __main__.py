"""CLI entry point: python -m comply [scan|serve|import|export|remediate|overlap|...]"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from comply import __version__

log = logging.getLogger(__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="comply",
        description="BespokeAgile Comply -- open-source compliance gap analysis for any codebase",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    # ── scan ──────────────────────────────────────────────────────────────
    scan_p = sub.add_parser("scan", help="Scan a repo for compliance gaps")
    scan_p.add_argument("target", help="Local path or git URL to scan")
    scan_p.add_argument(
        "--framework", "-f",
        default="eu-ai-act",
        help="Compliance framework(s), comma-separated (default: eu-ai-act)",
    )
    scan_p.add_argument(
        "--depth", "-d",
        choices=["structure", "content", "semantic"],
        default="content",
        help="Scan depth (default: content)",
    )
    scan_p.add_argument("--output", "-o", help="Output directory for reports")
    scan_p.add_argument("--llm-key", help="LLM API key for semantic analysis")
    scan_p.add_argument(
        "--llm-provider",
        choices=["anthropic", "openai", "gemini", "grok"],
        help="LLM provider (default: anthropic)",
    )
    scan_p.add_argument("--max-files", type=int, default=500, help="Max files to scan (default: 500)")
    scan_p.add_argument("--json", action="store_true", help="Output only JSON (no terminal summary)")
    scan_p.add_argument("--audit-bundle", action="store_true", help="Also generate ZIP audit bundle")
    scan_p.add_argument("--no-cache", action="store_true", help="Skip scan model cache")
    scan_p.add_argument(
        "--format",
        choices=["terminal", "json", "sarif", "junit", "markdown"],
        default="terminal",
        help="Output format (default: terminal)",
    )
    scan_p.add_argument(
        "--export-formats",
        default="",
        help="Additional export formats (comma-separated: sarif,junit,markdown). "
             "Written to --output dir. Runs one scan, exports multiple formats.",
    )
    scan_p.add_argument(
        "--jurisdiction", "-j",
        default=None,
        help="Jurisdiction profile (e.g. eu, us, us_california). "
             "Expands to the profile's framework list. Mutually exclusive with --framework.",
    )
    scan_p.add_argument(
        "--fail-below", type=float, default=None, metavar="N",
        help="Exit code 1 if score < N (for CI/CD)",
    )
    scan_p.add_argument(
        "--fail-on-regression", action="store_true",
        help="Exit code 1 if regression detected vs baseline",
    )

    # ── serve ─────────────────────────────────────────────────────────────
    serve_p = sub.add_parser("serve", help="Start the Comply web server")
    serve_p.add_argument("--port", type=int, default=8001, help="Port (default: 8001)")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    serve_p.add_argument("--background", "-b", action="store_true",
                         help="Run server in background and return to shell")

    # ── stop ──────────────────────────────────────────────────────────────
    sub.add_parser("stop", help="Stop a running background server")

    # ── frameworks ────────────────────────────────────────────────────────
    sub.add_parser("frameworks", help="List supported compliance frameworks")

    # ── history ────────────────────────────────────────────────────────
    hist_p = sub.add_parser("history", help="Show past scan results")
    hist_p.add_argument("--repo", help="Filter by repo path")
    hist_p.add_argument("--framework", help="Filter by framework")
    hist_p.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")

    # ── diff ───────────────────────────────────────────────────────────
    diff_p = sub.add_parser("diff", help="Compare two scans")
    diff_p.add_argument("scan1", help="First scan ID (baseline)")
    diff_p.add_argument("scan2", help="Second scan ID (current)")

    # ── cache ──────────────────────────────────────────────────────────
    cache_p = sub.add_parser("cache", help="Manage scan model cache")
    cache_sub = cache_p.add_subparsers(dest="cache_action")
    cache_sub.add_parser("stats", help="Show cache stats")
    cache_sub.add_parser("clear", help="Clear all cached entries")

    # ── cicd ──────────────────────────────────────────────────────────
    cicd_p = sub.add_parser("cicd", help="CI/CD test result ingestion and evidence")
    cicd_sub = cicd_p.add_subparsers(dest="cicd_action")
    cicd_sub.add_parser("status", help="Show CI/CD adapter status and summary")
    cicd_ingest_p = cicd_sub.add_parser("ingest", help="Ingest records from CI/CD adapters")
    cicd_ingest_p.add_argument("--adapter", help="Specific adapter (github_actions or gitlab_ci)")
    cicd_ingest_p.add_argument("--since", help="ISO-8601 lower bound")
    cicd_ingest_p.add_argument("--limit", type=int, default=1000, help="Max records (default: 1000)")
    cicd_records_p = cicd_sub.add_parser("records", help="Show recent CI/CD records")
    cicd_records_p.add_argument("--limit", type=int, default=20, help="Max records (default: 20)")
    cicd_records_p.add_argument("--type", dest="cicd_type", help="Filter: workflow_run, test_result, deployment")

    # ── adapters ──────────────────────────────────────────────────────
    adapt_p = sub.add_parser("adapters", help="Manage audit log adapters")
    adapt_sub = adapt_p.add_subparsers(dest="adapter_action")
    adapt_sub.add_parser("list", help="List registered adapters")
    adapt_test_p = adapt_sub.add_parser("test", help="Test adapter connection")
    adapt_test_p.add_argument("adapter_name", help="Adapter name")
    adapt_ingest_p = adapt_sub.add_parser("ingest", help="Ingest records from adapter")
    adapt_ingest_p.add_argument("adapter_name", help="Adapter name")
    adapt_ingest_p.add_argument("--limit", type=int, default=1000, help="Max records to fetch")
    adapt_ingest_p.add_argument("--since", help="ISO-8601 lower bound")

    # ── baseline ───────────────────────────────────────────────────────
    base_p = sub.add_parser("baseline", help="Manage compliance baselines")
    base_p.add_argument("--set", dest="set_id", metavar="SCAN_ID", help="Set a scan as baseline")
    base_p.add_argument("--auto", action="store_true", help="Set the latest scan as baseline")
    base_p.add_argument("--repo", help="Repo path (for --auto)")
    base_p.add_argument("--framework", default="eu-ai-act", help="Framework (default: eu-ai-act)")
    base_p.add_argument("--show", action="store_true", help="Show current baseline")

    # ── mapping ───────────────────────────────────────────────────────
    map_p = sub.add_parser("mapping", help="Cross-framework control mapping and jurisdiction profiles")
    map_sub = map_p.add_subparsers(dest="mapping_action")
    map_show_p = map_sub.add_parser("show", help="Show evidence function → control mapping")
    map_show_p.add_argument("--frameworks", help="Comma-separated framework IDs (default: all)")
    map_prio_p = map_sub.add_parser("priorities", help="Show remediation priorities from latest scans")
    map_prio_p.add_argument("--frameworks", help="Comma-separated framework IDs (default: all scanned)")
    map_sub.add_parser("jurisdictions", help="List available jurisdiction profiles")

    # ── monitor (daemon-managed continuous monitoring) ──────────────
    mon_p = sub.add_parser("monitor", help="Manage continuous compliance monitors")
    mon_sub = mon_p.add_subparsers(dest="monitor_action")
    mon_create_p = mon_sub.add_parser("create", help="Create a new monitor")
    mon_create_p.add_argument("repo_path", help="Repository path to monitor")
    mon_create_p.add_argument("--framework", "-f", default="eu-ai-act", help="Framework (default: eu-ai-act)")
    mon_create_p.add_argument("--depth", "-d", default="content", help="Scan depth (default: content)")
    mon_create_p.add_argument("--interval", type=int, default=300, help="Poll interval in seconds (default: 300)")
    mon_create_p.add_argument("--max-files", type=int, default=500, help="Max files per scan (default: 500)")
    mon_create_p.add_argument("--webhook", default="", help="Webhook URL for alerts")
    mon_sub.add_parser("list", help="List all monitors")
    mon_start_p = mon_sub.add_parser("start", help="Start a monitor")
    mon_start_p.add_argument("monitor_id", help="Monitor ID")
    mon_stop_p = mon_sub.add_parser("stop", help="Stop a monitor")
    mon_stop_p.add_argument("monitor_id", help="Monitor ID")
    mon_status_p = mon_sub.add_parser("status", help="Show monitor status")
    mon_status_p.add_argument("monitor_id", nargs="?", help="Monitor ID (optional, shows daemon status if omitted)")
    mon_delete_p = mon_sub.add_parser("delete", help="Delete a monitor")
    mon_delete_p.add_argument("monitor_id", help="Monitor ID")
    mon_events_p = mon_sub.add_parser("events", help="Show monitor events")
    mon_events_p.add_argument("--monitor", help="Filter by monitor ID")
    mon_events_p.add_argument("--limit", type=int, default=20, help="Max events (default: 20)")

    # ── gate (CI/CD compliance gate) ──────────────────────────────────
    # `comply gate <target>` runs a check; `comply gate decisions` lists history
    gate_p = sub.add_parser("gate", help="CI/CD compliance gate — pass/fail decision")
    gate_p.add_argument("target", help="Repository path to check, or 'decisions' to list history")
    gate_p.add_argument("--framework", "-f", default="eu-ai-act", help="Framework (default: eu-ai-act)")
    gate_p.add_argument("--min-score", type=float, default=0.0, help="Minimum score to pass (default: 0)")
    gate_p.add_argument("--no-regression", action="store_true", help="Fail on regression vs baseline")
    gate_p.add_argument("--max-gaps", type=int, default=-1, help="Max critical gaps (-1 = unlimited)")
    gate_p.add_argument("--depth", "-d", default="content", help="Scan depth (default: content)")
    gate_p.add_argument("--max-files", type=int, default=500, help="Max files to scan (default: 500)")
    gate_p.add_argument("--use-cache", action="store_true", help="Use scan cache (default: fresh scan)")
    gate_p.add_argument("--json", action="store_true", help="Output JSON instead of terminal summary")
    gate_p.add_argument("--repo", help="Filter by repo (for 'decisions')")
    gate_p.add_argument("--limit", type=int, default=20, help="Max results for 'decisions' (default: 20)")

    # ── forecast ──────────────────────────────────────────────────────
    fore_p = sub.add_parser("forecast", help="Compliance score forecasting and trend analysis")
    fore_p.add_argument("target", nargs="?", default=".", help="Repository path (default: .)")
    fore_p.add_argument("--framework", "-f", default="eu-ai-act", help="Framework (default: eu-ai-act)")
    fore_p.add_argument("--weeks", type=int, default=8, help="Weeks to project forward (default: 8)")
    fore_p.add_argument("--target-score", type=float, default=80.0, help="Target score (default: 80)")
    fore_p.add_argument("--json", action="store_true", help="Output JSON instead of terminal summary")

    # ── watch (continuous monitoring) ─────────────────────────────────
    watch_p = sub.add_parser("watch", help="Watch a repo and rescan on each commit")
    watch_p.add_argument("target", nargs="?", default=".", help="Repository path (default: .)")
    watch_p.add_argument("--framework", "-f", default="eu-ai-act", help="Framework (default: eu-ai-act)")
    watch_p.add_argument("--depth", "-d", default="content", help="Scan depth (default: content)")
    watch_p.add_argument("--interval", type=int, default=60, help="Poll interval in seconds (default: 60)")
    watch_p.add_argument("--max-files", type=int, default=500, help="Max files per scan")
    watch_p.add_argument("--webhook", help="URL to POST results to (Slack, Discord, etc.)")
    watch_p.add_argument("--fail-on-regression", action="store_true",
                         help="Exit with code 1 if regression detected")

    # ── import (SARIF) ──────────────────────────────────────────────────
    imp_p = sub.add_parser("import", help="Import SARIF findings and map to compliance controls")
    imp_p.add_argument("sarif_file", help="Path to SARIF v2.1.0 file (or - for stdin)")
    imp_p.add_argument(
        "--framework", "-f",
        default="eu-ai-act",
        help="Compliance framework(s), comma-separated (default: eu-ai-act)",
    )
    imp_p.add_argument(
        "--merge-with",
        default=None,
        help="Scan ID or JSON file to merge imported findings with",
    )
    imp_p.add_argument(
        "--format",
        choices=["terminal", "json", "sarif", "markdown"],
        default="terminal",
        help="Output format (default: terminal)",
    )
    imp_p.add_argument("--output", "-o", help="Output directory for reports")
    imp_p.add_argument(
        "--repo", "-r",
        default=None,
        help="Repository path for architectural enrichment (auto-triggers structure scan)",
    )
    imp_p.add_argument(
        "--no-arch-weight",
        action="store_true",
        help="Disable architectural severity weighting",
    )

    # ── export ────────────────────────────────────────────────────────────
    exp_p = sub.add_parser("export", help="Export a past scan in any format")
    exp_p.add_argument("scan_id", help="Scan ID to export")
    exp_p.add_argument(
        "--format",
        choices=["json", "sarif", "junit", "markdown", "docx"],
        default="json",
        help="Export format (default: json)",
    )
    exp_p.add_argument("--output", "-o", help="Output file path (default: stdout)")

    # ── remediate ─────────────────────────────────────────────────────────
    rem_p = sub.add_parser("remediate", help="Show remediation roadmap for a scan")
    rem_p.add_argument("scan_id", help="Scan ID to generate remediation plan for")
    rem_p.add_argument(
        "--format",
        choices=["terminal", "json", "markdown"],
        default="terminal",
        help="Output format (default: terminal)",
    )

    # ── overlap ───────────────────────────────────────────────────────────
    over_p = sub.add_parser("overlap", help="Show cross-framework control overlap matrix")
    over_p.add_argument(
        "--frameworks",
        help="Comma-separated framework IDs (default: all scanned)",
    )
    over_p.add_argument(
        "--format",
        choices=["terminal", "json"],
        default="terminal",
        help="Output format (default: terminal)",
    )

    # ── config ─────────────────────────────────────────────────────────────
    config_p = sub.add_parser("config", help="View or set configuration (~/.comply/config.yaml)")
    config_sub = config_p.add_subparsers(dest="config_action")
    config_sub.add_parser("show", help="Show current configuration")
    config_set_p = config_sub.add_parser("set", help="Set a config key")
    config_set_p.add_argument("key", help="Config key (e.g. llm_api_key, llm_provider, default_framework)")
    config_set_p.add_argument("value", help="Value to set")
    config_sub.add_parser("path", help="Print config file path")

    # ── report ────────────────────────────────────────────────────────────
    report_p = sub.add_parser("report", help="Report a problem (opens GitHub issue or copies to clipboard)")
    report_p.add_argument("--copy", action="store_true", help="Copy report to clipboard instead of opening browser")
    report_p.add_argument("--description", "-m", help="Brief description of the problem")

    # ── mcp ────────────────────────────────────────────────────────────
    sub.add_parser("mcp", help="Start the Comply MCP server (stdio transport for Claude Code, Cursor, etc.)")

    args = parser.parse_args(argv)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "scan":
        _run_scan(args)
    elif args.command == "serve":
        _run_serve(args)
    elif args.command == "stop":
        _run_stop()
    elif args.command == "frameworks":
        _run_frameworks()
    elif args.command == "history":
        _run_history(args)
    elif args.command == "diff":
        _run_diff(args)
    elif args.command == "cache":
        _run_cache(args)
    elif args.command == "cicd":
        _run_cicd(args)
    elif args.command == "adapters":
        _run_adapters(args)
    elif args.command == "baseline":
        _run_baseline(args)
    elif args.command == "mapping":
        _run_mapping(args)
    elif args.command == "gate":
        _run_gate(args)
    elif args.command == "monitor":
        _run_monitor(args)
    elif args.command == "forecast":
        _run_forecast(args)
    elif args.command == "watch":
        _run_watch(args)
    elif args.command == "import":
        _run_import(args)
    elif args.command == "export":
        _run_export(args)
    elif args.command == "remediate":
        _run_remediate(args)
    elif args.command == "overlap":
        _run_overlap(args)
    elif args.command == "report":
        _run_report(args)
    elif args.command == "config":
        _run_config(args)
    elif args.command == "mcp":
        _run_mcp()


def _run_scan(args):
    import json as json_mod

    # --jurisdiction is mutually exclusive with --framework
    if args.jurisdiction:
        if args.framework != "eu-ai-act":
            # User explicitly passed --framework too
            print("\nError: --jurisdiction and --framework are mutually exclusive.", file=sys.stderr)
            sys.exit(1)
        from comply.mapping import resolve_frameworks
        frameworks = resolve_frameworks(args.jurisdiction)
        if not frameworks:
            print(f"\nError: Unknown jurisdiction '{args.jurisdiction}'", file=sys.stderr)
            sys.exit(1)
    else:
        frameworks = [fw.strip() for fw in args.framework.split(",") if fw.strip()]
    # If --json flag is used, override format
    fmt = "json" if args.json else args.format

    def on_progress(step, detail=""):
        if fmt == "terminal":
            print(f"  [{step}] {detail}", flush=True)

    try:
        if len(frameworks) == 1:
            from comply.scanner import run_comply_scan
            reports = [run_comply_scan(
                target=args.target,
                framework=frameworks[0],
                scan_depth=args.depth,
                output_dir=args.output,
                llm_api_key=args.llm_key,
                llm_provider=args.llm_provider,
                max_files=args.max_files,
                on_progress=on_progress,
                use_cache=not args.no_cache,
            )]
        else:
            from comply.scanner import run_comply_scan_multi
            reports = run_comply_scan_multi(
                target=args.target,
                frameworks=frameworks,
                scan_depth=args.depth,
                output_dir=args.output,
                llm_api_key=args.llm_key,
                llm_provider=args.llm_provider,
                max_files=args.max_files,
                on_progress=on_progress,
                use_cache=not args.no_cache,
            )
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(2)

    # Check regression if requested
    regression_detected = False
    if args.fail_on_regression:
        from comply.regression import detect_regression
        for report in reports:
            reg = detect_regression(
                report.get("repoPath", ""),
                report.get("framework", ""),
                report,
            )
            if reg and reg.get("regressionDetected"):
                regression_detected = True
                report["regression"] = reg

    # Output
    _output_reports(reports, fmt, args)

    # Exit code logic
    exit_code = 0
    if args.fail_below is not None:
        for report in reports:
            if report.get("summary", {}).get("score", 0) < args.fail_below:
                exit_code = 1
                break
    if args.fail_on_regression and regression_detected:
        exit_code = 1

    if exit_code != 0:
        sys.exit(exit_code)


def _output_reports(reports, fmt, args):
    """Output reports in the requested format."""
    import json as json_mod

    if fmt == "json":
        for report in reports:
            clean = {k: v for k, v in report.items() if not k.startswith("_")}
            print(json_mod.dumps(clean, indent=2, default=str))

    elif fmt == "terminal":
        from comply.report import print_terminal_report, print_multi_framework_report
        if len(reports) == 1:
            print_terminal_report(reports[0])
        else:
            print_multi_framework_report(reports)
            # Print cross-framework matrix for multi-framework scans
            from comply.report import build_cross_framework_matrix, print_cross_framework_matrix
            matrix = build_cross_framework_matrix(reports)
            print_cross_framework_matrix(matrix)

        # Regression summary if present
        from comply.report import print_regression_summary
        for report in reports:
            reg = report.get("regression")
            if reg:
                print_regression_summary(reg)

    elif fmt in ("sarif", "junit", "markdown"):
        from comply.formats import to_sarif, to_junit, to_markdown
        for report in reports:
            if fmt == "sarif":
                print(json_mod.dumps(to_sarif(report), indent=2))
            elif fmt == "junit":
                print(to_junit(report))
            elif fmt == "markdown":
                print(to_markdown(report))

    # Write to output dir if specified
    if args.output:
        import os
        from comply.report import write_json_report, write_audit_bundle
        for report in reports:
            fw = report.get("framework", "unknown")
            path = write_json_report(report, os.path.join(args.output, f"compliance_report_{fw}.json"))
            if fmt == "terminal":
                print(f"  Report written to {path}")

        if args.audit_bundle:
            for report in reports:
                bundle_path = write_audit_bundle(report.get("framework", "eu-ai-act"), args.output)
                if bundle_path and fmt == "terminal":
                    print(f"  Audit bundle written to {bundle_path}")

        # Write format-specific files to output dir (primary format)
        if fmt in ("sarif", "junit", "markdown"):
            _write_format_files(reports, [fmt], args.output, fmt == "terminal")

        # Write additional export formats (--export-formats)
        extra_fmts = [f.strip() for f in getattr(args, "export_formats", "").split(",") if f.strip()]
        if extra_fmts:
            _write_format_files(reports, extra_fmts, args.output, fmt == "terminal")


def _write_format_files(reports, formats, output_dir, verbose=False):
    """Write reports in specified formats to output_dir."""
    import os
    import json as json_mod2
    from comply.formats import to_sarif, to_junit, to_markdown

    for report in reports:
        fw = report.get("framework", "unknown")
        for out_fmt in formats:
            if out_fmt == "sarif":
                p = os.path.join(output_dir, f"comply-{fw}.sarif")
                with open(p, "w") as f:
                    json_mod2.dump(to_sarif(report), f, indent=2)
                if verbose:
                    print(f"  SARIF written to {p}")
            elif out_fmt == "junit":
                p = os.path.join(output_dir, f"comply-{fw}.xml")
                with open(p, "w") as f:
                    f.write(to_junit(report))
                if verbose:
                    print(f"  JUnit written to {p}")
            elif out_fmt == "markdown":
                p = os.path.join(output_dir, f"comply-{fw}.md")
                with open(p, "w") as f:
                    f.write(to_markdown(report))
                if verbose:
                    print(f"  Markdown written to {p}")


def _pid_file_path():
    data_dir = os.environ.get("COMPLY_DATA_DIR", os.path.expanduser("~/.comply"))
    return os.path.join(data_dir, "server.pid")


def _run_serve(args):
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is required. Install it with: pip install uvicorn[standard]",
              file=sys.stderr)
        sys.exit(1)

    from comply.app import create_comply_app
    app = create_comply_app()

    # First-run welcome
    from comply.store import list_scans
    history = list_scans(limit=1)
    url = f"http://{args.host}:{args.port}"

    if getattr(args, "background", False):
        import subprocess
        import time

        pid_path = _pid_file_path()
        log_path = os.path.join(os.path.dirname(pid_path), "server.log")
        os.makedirs(os.path.dirname(pid_path), exist_ok=True)

        log_fd = open(log_path, "w")
        proc = subprocess.Popen(
            [sys.executable, "-m", "comply", "serve",
             "--port", str(args.port), "--host", args.host],
            stdout=log_fd, stderr=log_fd,
            start_new_session=True,
        )
        with open(pid_path, "w") as f:
            f.write(str(proc.pid))

        # Wait for health check
        import httpx
        for _ in range(20):
            time.sleep(0.5)
            try:
                r = httpx.get(f"{url}/health", timeout=2)
                if r.status_code == 200:
                    break
            except Exception:
                pass

        print(f"\n  BespokeAgile Comply v{__version__} running in background (PID {proc.pid})")
        print(f"  Dashboard: {url}")
        print(f"  Log:       tail -f {log_path}")
        print(f"  Stop:      bespoke-comply stop\n")
        return

    # Foreground mode
    if not history:
        print(f"""
  ┌──────────────────────────────────────────────┐
  │  BespokeAgile Comply v{__version__}                  │
  │  Compliance gap analysis for any codebase    │
  │                                              │
  │  Dashboard: {url:<33}│
  │                                              │
  │  Quick start:                                │
  │    1. Open the dashboard above               │
  │    2. Enter a repo path or GitHub URL        │
  │    3. Click Scan                             │
  │                                              │
  │  For semantic depth, configure an LLM key:   │
  │    comply config set llm_api_key sk-...      │
  └──────────────────────────────────────────────┘
""")
    else:
        print(f"\n  BespokeAgile Comply v{__version__} — {url}\n")

    uvicorn.run(app, host=args.host, port=args.port)


def _run_stop():
    import signal
    pid_path = _pid_file_path()
    if not os.path.exists(pid_path):
        print("No running server found (no PID file).")
        sys.exit(1)

    with open(pid_path) as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Comply server (PID {pid}).")
    except ProcessLookupError:
        print(f"Server (PID {pid}) was not running.")
    finally:
        try:
            os.unlink(pid_path)
        except FileNotFoundError:
            pass


def _run_frameworks():
    from comply.scanner import list_frameworks
    from comply.report import print_frameworks_list

    try:
        frameworks = list_frameworks()
    except Exception as e:
        log.debug("list_frameworks() failed, using minimal fallback: %s", e)
        frameworks = _load_frameworks_minimal()
    print_frameworks_list(frameworks)


def _run_history(args):
    from comply.store import list_scans
    from comply.report import print_history_table

    scans = list_scans(repo=args.repo, framework=args.framework, limit=args.limit)
    if not scans:
        print("\n  No scans found.\n")
        return
    print_history_table(scans)


def _run_diff(args):
    from comply.store import get_scan
    from comply.report import print_diff_report

    s1 = get_scan(args.scan1)
    if s1 is None:
        print(f"\nError: Scan '{args.scan1}' not found", file=sys.stderr)
        sys.exit(1)
    s2 = get_scan(args.scan2)
    if s2 is None:
        print(f"\nError: Scan '{args.scan2}' not found", file=sys.stderr)
        sys.exit(1)

    diff = _compute_diff(s1["report"], s2["report"])
    print_diff_report(diff)


def _run_cache(args):
    from comply.cache import get_cache_stats, clear_cache

    action = getattr(args, "cache_action", None)
    if action == "stats":
        stats = get_cache_stats()
        print(f"\n  Cache Stats")
        print(f"  Entries:     {stats['entries']} / {stats.get('max_entries', 10)}")
        print(f"  Total size:  {stats['total_bytes']:,} bytes")
        print(f"  TTL:         {stats.get('ttl_hours', 24)}h")
        print()
    elif action == "clear":
        count = clear_cache()
        print(f"\n  Cleared {count} cache entries.\n")
    else:
        print("\n  Usage: comply cache [stats|clear]\n")


def _run_baseline(args):
    from comply.store import set_baseline, get_baseline, get_latest_scan

    if args.show:
        bl = get_baseline(args.repo or ".", args.framework)
        if bl is None:
            print(f"\n  No baseline set for framework '{args.framework}'.\n")
        else:
            print(f"\n  Baseline: {bl['id']}")
            print(f"  Framework: {bl['framework']}")
            print(f"  Score: {bl.get('score', 0):.1f}%")
            print(f"  Date: {bl.get('created_at', '')[:19]}")
            print()
        return

    if args.set_id:
        ok = set_baseline(args.set_id)
        if ok:
            print(f"\n  Baseline set to scan {args.set_id}\n")
        else:
            print(f"\nError: Scan '{args.set_id}' not found", file=sys.stderr)
            sys.exit(1)
        return

    if args.auto:
        latest = get_latest_scan(args.repo or ".", args.framework)
        if latest is None:
            print(f"\nError: No scans found for framework '{args.framework}'", file=sys.stderr)
            sys.exit(1)
        ok = set_baseline(latest["id"])
        if ok:
            print(f"\n  Baseline set to latest scan {latest['id']} (score: {latest.get('score', 0):.1f}%)\n")
        else:
            print(f"\nError: Failed to set baseline", file=sys.stderr)
            sys.exit(1)
        return

    print("\n  Usage: comply baseline [--set SCAN_ID | --auto] [--framework FRAMEWORK]\n")


def _run_mapping(args):
    action = getattr(args, "mapping_action", None)

    if action == "show":
        from comply.mapping import build_control_mapping
        from comply.report import print_mapping_table

        fw_ids = None
        if args.frameworks:
            fw_ids = [f.strip() for f in args.frameworks.split(",") if f.strip()]
        mapping = build_control_mapping(framework_ids=fw_ids)
        print_mapping_table(mapping)

    elif action == "priorities":
        from comply.mapping import get_remediation_priorities
        from comply.report import print_remediation_priorities
        from comply.store import list_scans

        fw_filter = None
        if args.frameworks:
            fw_filter = [f.strip() for f in args.frameworks.split(",") if f.strip()]

        # Collect latest scan report per framework
        reports = []
        if fw_filter:
            for fw in fw_filter:
                scans = list_scans(framework=fw, limit=1)
                if scans and scans[0].get("report"):
                    reports.append(scans[0]["report"])
        else:
            scans = list_scans(limit=50)
            seen = set()
            for s in scans:
                fw = s.get("framework", "")
                if fw not in seen and s.get("report"):
                    seen.add(fw)
                    reports.append(s["report"])

        if not reports:
            print("\n  No scan data found. Run scans first, then check priorities.\n")
            return

        priorities = get_remediation_priorities(reports)
        print_remediation_priorities(priorities)

    elif action == "jurisdictions":
        from comply.mapping import get_jurisdiction_profiles

        profiles = get_jurisdiction_profiles()
        print()
        print("  Jurisdiction Profiles")
        print()
        for p in profiles:
            fws = ", ".join(p["frameworks"])
            print(f"  {p['id']:<16s}  {p['label']}")
            print(f"  {'':16s}  {fws}")
            print(f"  {'':16s}  {p['description']}")
            print()

    else:
        print("\n  Usage: comply mapping [show|priorities|jurisdictions]\n")


def _run_cicd(args):
    from comply.adapters.registry import list_adapters, get_adapter, auto_configure_from_config
    from comply.store import CICD_ADAPTER_NAMES

    auto_configure_from_config()

    action = getattr(args, "cicd_action", None)
    if action == "status":
        # Show CI/CD adapter status
        adapters = list_adapters()
        cicd_adapters = [a for a in adapters if a.get("name") in CICD_ADAPTER_NAMES]

        print("\n  CI/CD Adapters")
        print("  " + "-" * 50)
        if not cicd_adapters:
            print("  No CI/CD adapters registered.")
        else:
            for a in cicd_adapters:
                name = a.get("name", "?")
                configured = a.get("configured", False)
                connected = a.get("connected", False)
                status = "connected" if connected else ("configured" if configured else "not configured")
                print(f"  {name:<20s}  {status}")

        # Show CI/CD summary
        from comply.store import get_cicd_summary
        summary = get_cicd_summary()
        print(f"\n  CI/CD Summary")
        print("  " + "-" * 50)
        print(f"  Total records:  {summary.get('total_records', 0)}")
        print(f"  Pipelines:      {summary.get('pipelines', 0)}")
        print(f"  Test runs:      {summary.get('test_runs', 0)}")
        print(f"  Deployments:    {summary.get('deployments', 0)}")
        print(f"  Successes:      {summary.get('successes', 0)}")
        print(f"  Failures:       {summary.get('failures', 0)}")
        print(f"  Pass rate:      {summary.get('pass_rate', 0)}%")
        print()

    elif action == "ingest":
        adapter_names = [args.adapter] if args.adapter else list(CICD_ADAPTER_NAMES)
        from comply.store import ingest_audit_records

        total_fetched = 0
        total_ingested = 0
        for name in adapter_names:
            adapter = get_adapter(name)
            if adapter is None:
                print(f"  {name}: not configured (skipping)")
                continue
            try:
                records = adapter.fetch_records(
                    since=getattr(args, "since", None),
                    limit=args.limit,
                )
                count = ingest_audit_records(records)
                print(f"  {name}: fetched {len(records)}, ingested {count}")
                total_fetched += len(records)
                total_ingested += count
            except Exception as exc:
                print(f"  {name}: error — {exc}")

        print(f"\n  Total: fetched {total_fetched}, ingested {total_ingested}\n")

    elif action == "records":
        from comply.store import query_cicd_records
        records = query_cicd_records(
            limit=args.limit,
            cicd_type=getattr(args, "cicd_type", None),
        )
        if not records:
            print("\n  No CI/CD records found.\n")
            return
        print(f"\n  CI/CD Records (showing {len(records)})")
        print("  " + "-" * 80)
        print(f"  {'Timestamp':<22s} {'Adapter':<16s} {'Type':<14s} {'Tool':<14s} {'Status':<8s}")
        print("  " + "-" * 80)
        for r in records:
            ts = r.get("timestamp", "")[:19]
            adapter = r.get("adapter_name", "")
            cicd_type = r.get("metadata", {}).get("cicd_type", "")
            tool = r.get("tool_name", "")
            action_str = r.get("action", "")
            print(f"  {ts:<22s} {adapter:<16s} {cicd_type:<14s} {tool:<14s} {action_str:<8s}")
        print()

    else:
        print("\n  Usage: comply cicd [status|ingest|records]\n")


def _run_adapters(args):
    from comply.adapters.registry import list_adapters, get_adapter, auto_configure_from_config, configure_adapter

    auto_configure_from_config()

    action = getattr(args, "adapter_action", None)
    if action == "list":
        adapters = list_adapters()
        if not adapters:
            print("\n  No adapters registered.\n")
            return
        print("\n  Registered Adapters")
        print("  " + "-" * 50)
        for a in adapters:
            name = a.get("name", "?")
            configured = a.get("configured", False)
            connected = a.get("connected", False)
            status = "connected" if connected else ("configured" if configured else "not configured")
            print(f"  {name:<15s}  {status}")
        print()

    elif action == "test":
        name = args.adapter_name
        adapter = get_adapter(name)
        if adapter is None:
            print(f"\nError: Adapter '{name}' is not configured. Add it to ~/.comply/config.yaml", file=sys.stderr)
            sys.exit(1)
        ok = adapter.test_connection()
        if ok:
            print(f"\n  Adapter '{name}' — connection OK\n")
        else:
            print(f"\n  Adapter '{name}' — connection FAILED\n")
            sys.exit(1)

    elif action == "ingest":
        name = args.adapter_name
        adapter = get_adapter(name)
        if adapter is None:
            print(f"\nError: Adapter '{name}' is not configured.", file=sys.stderr)
            sys.exit(1)
        records = adapter.fetch_records(since=getattr(args, "since", None), limit=args.limit)
        from comply.store import ingest_audit_records
        count = ingest_audit_records(records)
        print(f"\n  Fetched {len(records)} records, ingested {count}\n")

    else:
        print("\n  Usage: comply adapters [list|test|ingest]\n")


from comply.diff_utils import _compute_diff  # noqa: F401


def _run_gate(args):
    target = args.target

    if target == "decisions":
        # List past gate decisions
        from comply.store import list_gate_decisions

        decisions = list_gate_decisions(
            repo=getattr(args, "repo", None),
            framework=getattr(args, "framework", "eu-ai-act") if getattr(args, "repo", None) else None,
            limit=args.limit,
        )
        if not decisions:
            print("\n  No gate decisions found.\n")
            return

        print(f"\n  Gate Decisions (showing {len(decisions)})")
        print("  " + "-" * 80)
        print(f"  {'Time':<22s} {'Framework':<16s} {'Decision':<10s} {'Score':<10s} {'Threshold':<10s} {'Commit'}")
        print("  " + "-" * 80)
        for d in decisions:
            ts = d.get("createdAt", "")[:19]
            fw = d.get("framework", "")
            dec = d.get("decision", "").upper()
            score = f"{d.get('score', 0):.1f}%"
            thresh = f"{d.get('thresholdScore', 0):.1f}%"
            sha = d.get("commitSha", "")[:8] or "-"
            print(f"  {ts:<22s} {fw:<16s} {dec:<10s} {score:<10s} {thresh:<10s} {sha}")
        print()
        return

    # Run gate check
    import json as json_mod
    from comply.gate import run_gate

    fw = args.framework.replace("-", "_")

    try:
        result = run_gate(
            repo_path=target,
            framework=fw,
            scan_depth=args.depth,
            max_files=args.max_files,
            threshold_score=args.min_score,
            fail_on_regression=args.no_regression,
            max_critical_gaps=args.max_gaps,
            use_cache=args.use_cache,
        )
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json_mod.dumps(result, indent=2, default=str))
    else:
        fw_display = result.get("framework", fw).replace("_", " ").title()
        decision = result["decision"].upper()
        marker = "\u2713" if result["decision"] == "pass" else "\u2717"
        sha = result.get("commitSha", "")[:8] or "-"
        threshold = result.get("thresholdScore", 0)
        score = result.get("score", 0)
        gaps = result.get("criticalGapCount", 0)
        max_g = result.get("maxCriticalGaps", -1)
        gap_limit = "unlimited" if max_g < 0 else str(max_g)
        reg = "none detected" if not result.get("regressionDetected") else "DETECTED"

        print()
        print(f"  Comply Gate \u2014 {fw_display}")
        print("  " + "\u2500" * 36)
        print(f"  Decision:   {decision} {marker}")
        print(f"  Score:      {score:.1f}% (threshold: {threshold:.1f}%)")
        print(f"  Regression: {reg}")
        print(f"  Gaps:       {gaps} (limit: {gap_limit})")
        print(f"  Commit:     {sha}")
        print(f"  Scan ID:    {result.get('scanId', '-')}")
        print(f"  Reason:     {result.get('reason', '')}")
        print()

    sys.exit(result.get("exitCode", 0))


def _run_monitor(args):
    action = getattr(args, "monitor_action", None)

    if action == "create":
        from comply.monitor import create_monitor
        fw = args.framework.replace("-", "_")
        mon = create_monitor(
            repo_path=args.repo_path,
            framework=fw,
            scan_depth=args.depth,
            interval_secs=args.interval,
            max_files=args.max_files,
            webhook_url=args.webhook,
        )
        print(f"\n  Monitor created: {mon['id']}")
        print(f"  Repo:      {mon['repo_path']}")
        print(f"  Framework: {mon['framework']}")
        print(f"  Interval:  {mon['interval_secs']}s")
        if mon.get("webhook_url"):
            print(f"  Webhook:   {mon['webhook_url']}")
        print(f"\n  Start with: comply monitor start {mon['id']}\n")

    elif action == "list":
        from comply.monitor import list_monitors
        monitors = list_monitors()
        if not monitors:
            print("\n  No monitors configured.\n")
            return
        print(f"\n  Monitors ({len(monitors)})")
        print("  " + "-" * 74)
        print(f"  {'ID':<14s} {'Status':<10s} {'Framework':<16s} {'Score':<8s} {'Repo'}")
        print("  " + "-" * 74)
        for m in monitors:
            score_str = f"{m.get('last_score', 0):.0f}%" if m.get("last_scan_id") else "-"
            repo = m.get("repo_path", "")
            if len(repo) > 30:
                repo = "..." + repo[-27:]
            print(f"  {m['id']:<14s} {m['status']:<10s} {m['framework']:<16s} {score_str:<8s} {repo}")
        print()

    elif action == "start":
        from comply.monitor import get_monitor, start_monitor
        mon = get_monitor(args.monitor_id)
        if mon is None:
            print(f"\nError: Monitor '{args.monitor_id}' not found", file=sys.stderr)
            sys.exit(1)
        start_monitor(args.monitor_id)
        print(f"\n  Monitor {args.monitor_id} started.\n")

    elif action == "stop":
        from comply.monitor import get_monitor, stop_monitor
        mon = get_monitor(args.monitor_id)
        if mon is None:
            print(f"\nError: Monitor '{args.monitor_id}' not found", file=sys.stderr)
            sys.exit(1)
        stop_monitor(args.monitor_id)
        print(f"\n  Monitor {args.monitor_id} stopped.\n")

    elif action == "status":
        mid = getattr(args, "monitor_id", None)
        if mid:
            from comply.monitor import get_monitor
            mon = get_monitor(mid)
            if mon is None:
                print(f"\nError: Monitor '{mid}' not found", file=sys.stderr)
                sys.exit(1)
            print(f"\n  Monitor {mon['id']}")
            print(f"  Status:    {mon['status']}")
            print(f"  Repo:      {mon['repo_path']}")
            print(f"  Framework: {mon['framework']}")
            print(f"  Interval:  {mon['interval_secs']}s")
            print(f"  Depth:     {mon['scan_depth']}")
            if mon.get("last_scan_id"):
                print(f"  Last scan: {mon['last_scan_id']}")
                print(f"  Last score: {mon['last_score']:.1f}%")
            if mon.get("last_sha"):
                print(f"  Last SHA:  {mon['last_sha'][:8]}")
            if mon.get("last_error"):
                print(f"  Error:     {mon['last_error']}")
            if mon.get("webhook_url"):
                print(f"  Webhook:   {mon['webhook_url']}")
            print()
        else:
            # Show daemon overview
            from comply.monitor import get_daemon, list_monitors
            daemon = get_daemon()
            status = daemon.get_status()
            monitors = list_monitors()
            running = [m for m in monitors if m.get("status") == "running"]
            print(f"\n  Monitor Daemon")
            print("  " + "-" * 40)
            print(f"  Daemon running:   {status['running']}")
            print(f"  Active monitors:  {status['activeMonitors']}")
            print(f"  Queue depth:      {status['queueDepth']}")
            print(f"  Total monitors:   {len(monitors)}")
            print(f"  Running monitors: {len(running)}")
            print()

    elif action == "delete":
        from comply.monitor import delete_monitor
        ok = delete_monitor(args.monitor_id)
        if ok:
            print(f"\n  Monitor {args.monitor_id} deleted.\n")
        else:
            print(f"\nError: Monitor '{args.monitor_id}' not found", file=sys.stderr)
            sys.exit(1)

    elif action == "events":
        monitor_id = getattr(args, "monitor", None)
        limit = args.limit
        if monitor_id:
            from comply.monitor import list_monitor_events
            events = list_monitor_events(monitor_id, limit=limit)
        else:
            from comply.monitor import list_recent_events
            events = list_recent_events(limit=limit)

        if not events:
            print("\n  No events found.\n")
            return
        print(f"\n  Monitor Events (showing {len(events)})")
        print("  " + "-" * 80)
        print(f"  {'Time':<22s} {'Monitor':<14s} {'Type':<16s} {'SHA':<10s} {'Score'}")
        print("  " + "-" * 80)
        for e in events:
            ts = e.get("created_at", "")[:19]
            sha = e.get("commit_sha", "")[:8] or "-"
            score = f"{e.get('score', 0):.1f}%" if e.get("scan_id") else "-"
            print(f"  {ts:<22s} {e['monitor_id']:<14s} {e['event_type']:<16s} {sha:<10s} {score}")
        print()

    else:
        print("\n  Usage: comply monitor [create|list|start|stop|status|delete|events]\n")


def _run_forecast(args):
    import json as json_mod
    from comply.forecast import forecast_score

    result = forecast_score(
        repo=args.target,
        framework=args.framework,
        weeks=args.weeks,
        target_score=args.target_score,
    )

    if args.json:
        print(json_mod.dumps(result, indent=2, default=str))
        return

    if result.get("status") == "insufficient_data":
        print(f"\n  {result.get('message', 'Insufficient data')}")
        print(f"  Data points: {result.get('dataPoints', 0)}\n")
        return

    fw_display = result.get("framework", "").replace("_", " ").replace("-", " ").title()
    trend = result.get("trend", "stable").upper()
    vel = result.get("velocity", 0)
    vel_sign = "+" if vel >= 0 else ""
    r2 = result.get("rSquared", 0)
    risk = result.get("riskLevel", "medium")
    target = result.get("targetScore", 80)
    current = result.get("currentScore", 0)
    proj_date = result.get("projectedDate")
    days = result.get("daysToTarget")
    n_scans = result.get("dataPoints", 0)
    first = result.get("firstScanDate", "")
    last = result.get("lastScanDate", "")

    # Compute span
    span_days = 0
    if first and last:
        try:
            from datetime import datetime as _dt
            d1 = _dt.fromisoformat(first)
            d2 = _dt.fromisoformat(last)
            span_days = (d2 - d1).days
        except ValueError as e:
            log.debug("Failed to parse forecast date range: %s", e)

    proj_str = f"{proj_date} (~{days // 7} weeks)" if proj_date and days else "N/A (not improving)"

    print()
    print(f"  Comply Forecast \u2014 {fw_display}")
    print("  " + "\u2500" * 36)
    print(f"  Current Score:  {current:.1f}%")
    print(f"  Trend:          {trend} ({vel_sign}{vel:.1f} pts/week)")
    print(f"  Fit (R\u00b2):       {r2:.2f}")
    print(f"  Risk Level:     {risk}")
    print(f"  Target:         {target:.1f}%")
    print(f"  Projected Date: {proj_str}")
    print(f"  Data Points:    {n_scans} scans over {span_days} days")

    # Control trends
    ct = result.get("controlTrends", {})
    improving = ct.get("improving", [])
    declining = ct.get("declining", [])
    stuck = ct.get("stuck", [])

    if improving or declining or stuck:
        print()
        print("  Control Trends (last 2 scans):")
        print(f"    \u2191 Improving: {len(improving)} controls")
        print(f"    \u2193 Declining: {len(declining)} controls")
        print(f"    \u2500 Stuck gaps: {len(stuck)} controls")

    print()


def _run_watch(args):
    from comply.watcher import watch_repo
    watch_repo(
        target=args.target,
        framework=args.framework,
        scan_depth=args.depth,
        interval=args.interval,
        max_files=args.max_files,
        webhook_url=args.webhook,
        fail_on_regression=args.fail_on_regression,
    )


def _run_report(args):
    """Collect diagnostic context and let the user report a problem."""
    import platform
    import subprocess
    from urllib.parse import quote

    from comply import __version__

    # Collect context
    py_version = platform.python_version()
    os_info = f"{platform.system()} {platform.release()}"

    # Last scan info from history
    last_scan_info = "No scans found"
    try:
        from comply.store import list_scans
        scans = list_scans(limit=1)
        if scans:
            s = scans[0]
            last_scan_info = (
                f"{s.get('framework', '?')} / {s.get('scan_depth', '?')} / "
                f"score: {s.get('score', 0):.1f}% / {s.get('created_at', '')[:19]}"
            )
            if s.get('status') == 'error':
                last_scan_info += f" / error"
    except Exception:
        last_scan_info = "Could not read scan history"

    # Installed optional dependencies
    extras = []
    for pkg in ["anthropic", "openai", "stripe", "python-docx", "slowapi"]:
        try:
            __import__(pkg.replace("-", "_"))
            extras.append(pkg)
        except ImportError:
            pass

    description = args.description or ""

    # Build report
    report_lines = [
        f"Comply Version: {__version__}",
        f"Python: {py_version}",
        f"OS: {os_info}",
        f"Extras: {', '.join(extras) if extras else 'none'}",
        f"Last scan: {last_scan_info}",
    ]
    if description:
        report_lines.insert(0, f"Description: {description}")

    report_text = "\n".join(report_lines)

    # Show the user what will be shared
    print()
    print("  Collected context (this is what will be shared):")
    print("  " + "-" * 50)
    for line in report_lines:
        print(f"    {line}")
    print("  " + "-" * 50)
    print()

    if args.copy:
        # Copy to clipboard
        md_report = "## Comply Bug Report\n\n```\n" + report_text + "\n```\n"
        if description:
            md_report = f"## Comply Bug Report\n\n{description}\n\n### Environment\n\n```\n" + report_text + "\n```\n"
        try:
            proc = subprocess.Popen(
                ["pbcopy"] if platform.system() == "Darwin" else ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
            )
            proc.communicate(md_report.encode())
            print("  Copied to clipboard. Paste into a GitHub issue or email.")
            print("  https://github.com/atdash/BespokeTracker/issues/new")
        except (FileNotFoundError, OSError):
            # Fallback: just print it
            print("  Could not copy to clipboard. Here is the report to paste manually:")
            print()
            print(md_report)
        print()
        return

    # Open GitHub issue in browser
    title = quote(description or "Comply bug report")
    body_md = f"## Description\n\n{description or '(describe the problem here)'}\n\n"
    body_md += "## Environment\n\n```\n" + report_text + "\n```\n\n"
    body_md += "## Steps to Reproduce\n\n1. \n2. \n3. \n\n"
    body_md += "## Expected Behavior\n\n\n\n## Actual Behavior\n\n"
    body = quote(body_md)

    url = f"https://github.com/atdash/BespokeTracker/issues/new?title={title}&body={body}&labels=comply,bug"

    print("  Opening GitHub issue in your browser...")
    print()

    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        print(f"  Could not open browser. Use this URL:")
        print(f"  {url}")
        print()


def _run_import(args):
    """Import SARIF findings and map to compliance controls."""
    import json as json_mod

    # Read SARIF from file or stdin
    sarif_path = args.sarif_file
    if sarif_path == "-":
        sarif_data = json_mod.load(sys.stdin)
    else:
        import os
        if not os.path.isfile(sarif_path):
            print(f"\nError: File not found: {sarif_path}", file=sys.stderr)
            sys.exit(1)
        with open(sarif_path) as f:
            sarif_data = json_mod.load(f)

    # Parse SARIF
    from comply.sarif_import import parse_sarif
    findings = parse_sarif(sarif_data)

    if not findings:
        print("\n  No findings extracted from SARIF file.\n")
        return

    # Map to compliance controls
    frameworks = [fw.strip() for fw in args.framework.split(",") if fw.strip()]
    from comply.finding_mapper import map_findings, generate_import_report, merge_reports

    fmt = args.format
    all_reports = []
    arch_weighting = not getattr(args, "no_arch_weight", False)

    # Graph enrichment: compute metrics from merge target or repo path
    graph_metrics = {}
    enrichment_source = None
    if arch_weighting:
        # Strategy 1: get codebase model from merge target
        if args.merge_with:
            base_report = _load_report_for_merge(args.merge_with)
            if base_report:
                codebase_graph = base_report.get("model", {}).get("codebaseGraph", {})
                if codebase_graph and codebase_graph.get("files"):
                    try:
                        from comply._vendor.graph_ranking import compute_graph_metrics
                        graph_metrics = compute_graph_metrics(codebase_graph)
                        enrichment_source = "merged_scan"
                        if fmt == "terminal":
                            print(f"  [enrichment] Graph from merged scan: {len(graph_metrics)} files")
                    except Exception:
                        pass

        # Strategy 2: auto structure scan on repo path
        repo_path = getattr(args, "repo", None)
        if not graph_metrics and repo_path:
            import os
            repo_path = os.path.abspath(repo_path)
            if os.path.isdir(repo_path):
                if fmt == "terminal":
                    print(f"  [enrichment] Running structure scan on {repo_path}...")
                try:
                    from comply._vendor.codebase_scanner import scan_codebase
                    codebase_model = scan_codebase(
                        repo_path=repo_path,
                        scan_depth="structure",
                        max_files=500,
                    )
                    from comply._vendor.graph_ranking import compute_graph_metrics
                    graph_metrics = compute_graph_metrics(codebase_model)
                    enrichment_source = "auto_structure_scan"
                    if fmt == "terminal":
                        print(f"  [enrichment] Graph built: {len(graph_metrics)} files")
                except Exception as exc:
                    if fmt == "terminal":
                        print(f"  [enrichment] Structure scan failed: {exc}")

    for fw in frameworks:
        mapped = map_findings(
            findings, fw,
            graph_metrics=graph_metrics if graph_metrics else None,
            architectural_weighting=arch_weighting,
        )
        report = generate_import_report(mapped, fw, source_file=sarif_path)
        if enrichment_source and report.get("architecturalEnrichment"):
            report["architecturalEnrichment"]["source"] = enrichment_source

        # Merge with existing scan if requested
        if args.merge_with:
            base_report = _load_report_for_merge(args.merge_with)
            if base_report is None:
                print(f"\nError: Could not load scan '{args.merge_with}' for merging", file=sys.stderr)
                sys.exit(1)
            report = merge_reports(base_report, report)

        all_reports.append(report)

    # Output
    if fmt == "json":
        for report in all_reports:
            print(json_mod.dumps(report, indent=2, default=str))
    elif fmt == "terminal":
        _print_import_report(all_reports, findings)
    elif fmt == "sarif":
        from comply.formats import to_sarif
        for report in all_reports:
            print(json_mod.dumps(to_sarif(report), indent=2))
    elif fmt == "markdown":
        from comply.formats import to_markdown
        for report in all_reports:
            print(to_markdown(report))

    # Write to output dir if specified
    if args.output:
        import os
        os.makedirs(args.output, exist_ok=True)
        for report in all_reports:
            fw = report.get("framework", "unknown")
            path = os.path.join(args.output, f"comply-import-{fw}.json")
            with open(path, "w") as f:
                json_mod.dump(report, f, indent=2, default=str)
            if fmt == "terminal":
                print(f"  Report written to {path}")

    # Summary stats
    total_mapped = sum(1 for f in findings if f.cwes)
    unmapped = sum(1 for f in findings if not f.cwes)
    if fmt == "terminal" and unmapped > 0:
        print(f"\n  Note: {unmapped} findings had no CWE and could not be mapped to controls.")


def _load_report_for_merge(ref: str):
    """Load a scan report by ID or JSON file path."""
    import json as json_mod
    import os

    # Try as file path first
    if os.path.isfile(ref):
        with open(ref) as f:
            return json_mod.load(f)

    # Try as scan ID
    try:
        from comply.store import get_scan
        scan = get_scan(ref)
        if scan and scan.get("report"):
            return scan["report"]
    except Exception:
        pass

    return None


def _print_import_report(reports, findings):
    """Print a terminal-formatted import report."""
    from comply.sarif_import import Finding  # noqa: F811

    # Summary of imported findings
    tools = set()
    cwes_found = set()
    for f in findings:
        tools.add(f.tool)
        cwes_found.update(f.cwes)

    print()
    print("  SARIF Import Summary")
    print("  " + "\u2500" * 50)
    print(f"  Tools:       {', '.join(sorted(tools))}")
    print(f"  Findings:    {len(findings)}")
    print(f"  Unique CWEs: {len(cwes_found)}")
    if cwes_found:
        print(f"  CWEs:        {', '.join(sorted(cwes_found)[:10])}"
              + (f" (+{len(cwes_found) - 10} more)" if len(cwes_found) > 10 else ""))
    print()

    for report in reports:
        fw = report.get("framework", "unknown").replace("_", " ").replace("-", " ").title()
        summary = report.get("summary", {})
        score = summary.get("score", 0)
        met = summary.get("met", 0)
        partial = summary.get("partial", 0)
        gap = summary.get("gap", 0)
        total = summary.get("total", 0)

        print(f"  {fw}")
        print("  " + "\u2500" * 50)
        print(f"  Score:   {score:.1f}%")
        print(f"  Met: {met}  Partial: {partial}  Gap: {gap}  Total: {total}")

        # Show security-impacted controls
        sec_controls = report.get("securityFindings", [])
        if sec_controls:
            print()
            print("  Security-impacted controls:")
            for sc in sec_controls[:15]:
                cid = sc.get("controlId", "?")
                status = sc.get("status", "?")
                count = sc.get("findingCount", 0)
                marker = "\u2717" if status == "gap" else "\u25CB"
                print(f"    {marker} {cid}: {status} ({count} finding{'s' if count != 1 else ''})")
            if len(sec_controls) > 15:
                print(f"    ... and {len(sec_controls) - 15} more")

        # Architectural enrichment summary
        arch = report.get("architecturalEnrichment")
        if arch and arch.get("enabled"):
            print()
            print("  Architectural Enrichment")
            print("  " + "\u2500" * 50)
            dist = arch.get("severityDistribution", {})
            print(f"  Enriched: {arch.get('enrichedFindings', 0)} findings")
            print(f"  Upgraded: {arch.get('upgradedFindings', 0)} (warning \u2192 error in critical files)")
            print(f"  High centrality: {dist.get('high', 0)}  "
                  f"Medium: {dist.get('medium', 0)}  "
                  f"Low: {dist.get('low', 0)}  "
                  f"Unknown: {dist.get('unknown', 0)}")

        print()


def _run_export(args):
    """Export a past scan in any format."""
    import json as json_mod

    from comply.store import get_scan
    scan = get_scan(args.scan_id)
    if scan is None:
        print(f"\nError: Scan '{args.scan_id}' not found", file=sys.stderr)
        sys.exit(1)

    report = scan.get("report", {})
    fmt = args.format

    if fmt == "json":
        content = json_mod.dumps(report, indent=2, default=str)
    elif fmt == "sarif":
        from comply.formats import to_sarif
        content = json_mod.dumps(to_sarif(report), indent=2)
    elif fmt == "junit":
        from comply.formats import to_junit
        content = to_junit(report)
    elif fmt == "markdown":
        from comply.formats import to_markdown
        content = to_markdown(report)
    elif fmt == "docx":
        from comply.docx_report import generate_comply_docx
        docx_bytes = generate_comply_docx(report)
        out_path = args.output or f"comply-{report.get('framework', 'report')}.docx"
        with open(out_path, "wb") as f:
            f.write(docx_bytes)
        print(f"  DOCX written to {out_path}")
        return
    else:
        print(f"\nError: Unknown format '{fmt}'", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w") as f:
            f.write(content)
        print(f"  Exported to {args.output}")
    else:
        print(content)


def _run_remediate(args):
    """Show remediation roadmap for a scan."""
    import json as json_mod

    from comply.store import get_scan
    scan = get_scan(args.scan_id)
    if scan is None:
        print(f"\nError: Scan '{args.scan_id}' not found", file=sys.stderr)
        sys.exit(1)

    report = scan.get("report", {})
    remediations = report.get("remediations", [])

    if not remediations:
        # Try generating on the fly
        try:
            from comply.remediation import generate_remediations
            codebase_model = report.get("_codebase_model", {})
            remediations = generate_remediations(report, codebase_model)
        except Exception:
            pass

    if not remediations:
        print("\n  No remediation data available for this scan.\n")
        return

    fmt = args.format

    if fmt == "json":
        print(json_mod.dumps(remediations, indent=2, default=str))
        return

    if fmt == "markdown":
        _print_remediation_markdown(remediations, report)
        return

    # Terminal format
    fw = report.get("framework", "").replace("_", " ").replace("-", " ").title()
    score = report.get("summary", {}).get("score", 0)

    print()
    print(f"  Remediation Roadmap \u2014 {fw}")
    print("  " + "\u2500" * 50)
    print(f"  Current score: {score:.1f}%")
    print(f"  Actions: {len(remediations)}")
    print()

    # Group by effort
    for effort in ["low", "medium", "high"]:
        items = [r for r in remediations if r.get("effort") == effort]
        if not items:
            continue
        label = {"low": "Quick Wins", "medium": "Medium Effort", "high": "Major Work"}[effort]
        print(f"  {label} ({len(items)} items)")
        print("  " + "-" * 46)
        for r in items:
            cid = r.get("controlId", "?")
            delta = r.get("score_delta", 0)
            summary = r.get("summary", r.get("action", ""))
            if len(summary) > 60:
                summary = summary[:57] + "..."
            print(f"    {cid:<12s} +{delta:.1f}%  {summary}")
        print()

    # Projected score
    if remediations:
        total_delta = sum(r.get("score_delta", 0) for r in remediations)
        print(f"  Projected score if all fixed: {min(score + total_delta, 100):.1f}%")
        print()


def _print_remediation_markdown(remediations, report):
    """Print remediation roadmap as markdown."""
    fw = report.get("framework", "unknown")
    score = report.get("summary", {}).get("score", 0)

    print(f"# Remediation Roadmap — {fw}")
    print()
    print(f"**Current score**: {score:.1f}%")
    print(f"**Actions**: {len(remediations)}")
    print()

    for effort in ["low", "medium", "high"]:
        items = [r for r in remediations if r.get("effort") == effort]
        if not items:
            continue
        label = {"low": "Quick Wins", "medium": "Medium Effort", "high": "Major Work"}[effort]
        print(f"## {label}")
        print()
        print("| Control | Impact | Action |")
        print("|---------|--------|--------|")
        for r in items:
            cid = r.get("controlId", "?")
            delta = r.get("score_delta", 0)
            action = r.get("action", r.get("summary", "")).replace("|", "/")
            print(f"| {cid} | +{delta:.1f}% | {action} |")
        print()

    total_delta = sum(r.get("score_delta", 0) for r in remediations)
    print(f"**Projected score if all fixed**: {min(score + total_delta, 100):.1f}%")


def _run_overlap(args):
    """Show cross-framework control overlap matrix."""
    import json as json_mod
    from comply.store import list_scans

    # Collect latest scan report per framework
    fw_filter = None
    if args.frameworks:
        fw_filter = [f.strip() for f in args.frameworks.split(",") if f.strip()]

    reports = []
    if fw_filter:
        for fw in fw_filter:
            scans = list_scans(framework=fw, limit=1)
            if scans and scans[0].get("report"):
                reports.append(scans[0]["report"])
    else:
        scans = list_scans(limit=50)
        seen = set()
        for s in scans:
            fw = s.get("framework", "")
            if fw not in seen and s.get("report"):
                seen.add(fw)
                reports.append(s["report"])

    if len(reports) < 2:
        print("\n  Need at least 2 framework scans for overlap analysis.")
        print("  Run: comply scan <repo> --framework eu-ai-act,soc2-ai,iso-42001\n")
        return

    from comply.report import build_cross_framework_matrix

    matrix = build_cross_framework_matrix(reports)

    fmt = args.format
    if fmt == "json":
        print(json_mod.dumps(matrix, indent=2, default=str))
        return

    # Terminal format
    from comply.report import print_cross_framework_matrix
    print_cross_framework_matrix(matrix)


def _load_frameworks_minimal() -> list:
    """Load frameworks from YAML without needing a full DB init."""
    import os
    import yaml

    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "graph", "compliance_frameworks.yaml"
    )
    if not os.path.isfile(yaml_path):
        yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "gateway", "compliance", "frameworks.yaml"
        )
    if not os.path.isfile(yaml_path):
        return [{"id": "eu-ai-act", "name": "EU AI Act"}]

    try:
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        frameworks = data.get("frameworks", {})
        result = []
        for fid, fdata in frameworks.items():
            articles = fdata.get("articles", [])
            control_count = sum(len(a.get("controls", [])) for a in articles)
            result.append({
                "id": fid,
                "name": fdata.get("name", fid),
                "version": fdata.get("version", ""),
                "articles": articles,
                "controlCount": control_count,
            })
        return result
    except (OSError, yaml.YAMLError) as e:
        log.debug("Failed to load frameworks from %s: %s", yaml_path, e)
        return [{"id": "eu-ai-act", "name": "EU AI Act"}]


def _run_config(args):
    """View or set configuration values."""
    from comply.tiers import _load_config, _save_config, _CONFIG_FILE

    if args.config_action == "path":
        print(_CONFIG_FILE)
        return

    if args.config_action == "set":
        cfg = _load_config()
        # Mask the LLM key in output
        display_val = args.value
        if "key" in args.key.lower() and len(args.value) > 8:
            display_val = args.value[:4] + "..." + args.value[-4:]
        cfg[args.key] = args.value
        _save_config(cfg)
        print(f"  {args.key} = {display_val}")
        print(f"\n  Saved to {_CONFIG_FILE}")
        return

    # Default: show
    cfg = _load_config()
    print(f"\n  Config: {_CONFIG_FILE}\n")
    if not cfg or cfg == {"tier": "free"}:
        print("  (default configuration — no custom settings)")
        print(f"\n  Set values with: comply config set <key> <value>")
        print("  Common keys: llm_api_key, llm_provider, default_framework")
    else:
        for k, v in sorted(cfg.items()):
            # Mask sensitive values
            if "key" in k.lower() and isinstance(v, str) and len(v) > 8:
                v = v[:4] + "..." + v[-4:]
            print(f"  {k} = {v}")
    print()


def _run_mcp():
    """Start the Comply MCP server (stdio transport)."""
    try:
        from comply.mcp_server import mcp
    except ImportError:
        print(
            "MCP support requires the 'mcp' package.\n"
            "Install it with: pip install bespoke-comply[mcp]",
            file=sys.stderr,
        )
        sys.exit(1)
    mcp.run()


def _run_mcp_entry():
    """Console script entry point for bespoke-comply-mcp."""
    _run_mcp()


if __name__ == "__main__":
    main()
