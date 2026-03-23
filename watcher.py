"""Continuous compliance monitoring — watch a repo for changes and rescan.

Polls the git HEAD commit SHA at a configurable interval.  When the SHA
changes, a compliance scan is triggered automatically.  Results are
posted to the local dashboard (via scan history) and optionally to
a webhook URL.

Usage:
    comply watch /path/to/repo --interval 60
    comply watch . --webhook https://hooks.slack.com/services/...
    comply watch . --fail-on-regression --interval 30
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


def watch_repo(
    target: str,
    framework: str = "eu-ai-act",
    scan_depth: str = "content",
    interval: int = 60,
    max_files: int = 500,
    webhook_url: Optional[str] = None,
    fail_on_regression: bool = False,
    on_scan_complete: Optional[callable] = None,
) -> None:
    """Watch a repository for changes and rescan on each new commit.

    This function blocks and runs until interrupted (Ctrl-C / SIGINT).

    Parameters
    ----------
    target : str
        Local path to the repository.
    framework : str
        Compliance framework to scan against.
    scan_depth : str
        Scan depth (structure/content/semantic).
    interval : int
        Polling interval in seconds.
    max_files : int
        Max files per scan.
    webhook_url : str, optional
        URL to POST scan results to (Slack, Discord, generic webhook).
    fail_on_regression : bool
        If True, exit with code 1 on regression.
    on_scan_complete : callable, optional
        Callback(report, regression_result) after each scan.
    """
    repo_path = os.path.abspath(target)
    if not os.path.isdir(repo_path):
        print(f"Error: {repo_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    _print_banner(repo_path, framework, scan_depth, interval)

    last_sha = ""
    scan_count = 0
    running = True

    def _stop(signum, frame):
        nonlocal running
        running = False
        print("\n  Stopping watcher...")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        current_sha = _get_commit_sha(repo_path)

        if current_sha and current_sha != last_sha:
            if last_sha:
                print(f"\n  Commit changed: {last_sha[:8]} -> {current_sha[:8]}")
            else:
                print(f"  Initial commit: {current_sha[:8]}")

            scan_count += 1
            print(f"  [{scan_count}] Scanning... ({framework}, {scan_depth})")

            try:
                report, regression = _run_scan(
                    repo_path, framework, scan_depth, max_files,
                    fail_on_regression,
                )

                score = report.get("summary", {}).get("score", 0)
                met = report.get("summary", {}).get("met", 0)
                gap = report.get("summary", {}).get("gap", 0)
                total = report.get("summary", {}).get("total", 0)

                print(f"  [{scan_count}] Score: {score:.1f}%  "
                      f"({met} met, {gap} gap / {total})")

                if regression and regression.get("regressionDetected"):
                    new_gaps = regression.get("newGaps", [])
                    print(f"  [{scan_count}] REGRESSION: {len(new_gaps)} new gap(s)")
                    if fail_on_regression:
                        print("  Exiting due to --fail-on-regression")
                        sys.exit(1)

                if webhook_url:
                    _post_webhook(webhook_url, report, regression, current_sha)

                if on_scan_complete:
                    on_scan_complete(report, regression)

            except Exception as exc:
                print(f"  [{scan_count}] Scan error: {exc}")

            last_sha = current_sha

        # Sleep in small increments for responsive shutdown
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    print(f"  Watcher stopped. {scan_count} scan(s) completed.\n")


def _get_commit_sha(repo_path: str) -> str:
    """Get the current HEAD commit SHA."""
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


def _run_scan(
    repo_path: str,
    framework: str,
    scan_depth: str,
    max_files: int,
    check_regression: bool,
) -> tuple:
    """Run a compliance scan and optionally check for regression.

    Returns (report, regression_result or None).
    """
    from comply.scanner import run_comply_scan

    report = run_comply_scan(
        target=repo_path,
        framework=framework,
        scan_depth=scan_depth,
        max_files=max_files,
        use_cache=False,  # always rescan on commit change
    )

    regression = None
    if check_regression:
        try:
            from comply.regression import detect_regression
            regression = detect_regression(repo_path, framework, report)
        except Exception as e:
            log.debug("Regression detection failed for %s: %s", repo_path, e)

    return report, regression


def _post_webhook(url: str, report: dict, regression: Optional[dict], commit_sha: str):
    """POST scan results to a webhook URL."""
    summary = report.get("summary", {})
    framework = report.get("framework", "")

    payload = {
        "text": (
            f"Comply scan complete: {framework}\n"
            f"Score: {summary.get('score', 0):.1f}% "
            f"({summary.get('met', 0)} met, "
            f"{summary.get('gap', 0)} gap / {summary.get('total', 0)})\n"
            f"Commit: {commit_sha[:8]}"
        ),
        "comply_report": {
            "framework": framework,
            "score": summary.get("score", 0),
            "met": summary.get("met", 0),
            "partial": summary.get("partial", 0),
            "gap": summary.get("gap", 0),
            "commitSha": commit_sha,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    if regression and regression.get("regressionDetected"):
        new_gaps = regression.get("newGaps", [])
        payload["text"] += f"\nREGRESSION: {len(new_gaps)} new gap(s)"
        payload["comply_report"]["regressionDetected"] = True
        payload["comply_report"]["newGapCount"] = len(new_gaps)

    try:
        import httpx
        httpx.post(url, json=payload, timeout=10)
    except Exception as exc:
        log.warning("Webhook POST failed: %s", exc)


def _print_banner(repo_path: str, framework: str, depth: str, interval: int):
    """Print the watcher startup banner."""
    print()
    print("  BespokeTracker Comply — Continuous Monitoring")
    print(f"  Repository: {repo_path}")
    print(f"  Framework:  {framework}")
    print(f"  Depth:      {depth}")
    print(f"  Interval:   {interval}s")
    print(f"  Press Ctrl-C to stop")
    print()
