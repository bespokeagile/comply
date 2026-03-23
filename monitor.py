"""Continuous Compliance Monitor Daemon — background polling + auto-scan.

A single MonitorDaemon thread manages all active monitors. Monitors poll
git repos for commit changes, auto-trigger scans, detect regressions, and
dispatch webhook alerts.

Usage (programmatic):
    from comply.monitor import get_daemon, create_monitor, start_monitor
    mon = create_monitor("/path/to/repo", "eu_ai_act", interval_secs=300)
    start_monitor(mon["id"])
    daemon = get_daemon()
    daemon.start()
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Singleton ─────────────────────────────────────────────────────────────

_daemon_instance = None
_daemon_lock = threading.Lock()


def get_daemon() -> "MonitorDaemon":
    """Return (or create) the global MonitorDaemon singleton."""
    global _daemon_instance
    with _daemon_lock:
        if _daemon_instance is None:
            _daemon_instance = MonitorDaemon()
        return _daemon_instance


# ── MonitorDaemon ─────────────────────────────────────────────────────────

class MonitorDaemon:
    """Background daemon that polls running monitors and processes scan jobs."""

    TICK_SECS = 5  # main loop sleep interval

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._queue: deque = deque()
        self._active_job: Optional[dict] = None

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Start the daemon thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="comply-monitor")
        self._thread.start()
        log.info("Monitor daemon started")

    def stop(self):
        """Signal the daemon to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None
        log.info("Monitor daemon stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> dict:
        running_monitors = _list_running_monitors()
        return {
            "running": self.is_running(),
            "activeMonitors": len(running_monitors),
            "queueDepth": len(self._queue),
            "activeJob": self._active_job.get("monitor_id") if self._active_job else None,
        }

    # ── main loop ─────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._poll_all()
                self._process_queue()
            except Exception as exc:
                log.error("Monitor daemon error: %s", exc)

            # Sleep in small increments for responsive shutdown
            for _ in range(self.TICK_SECS):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _poll_all(self):
        now = time.time()
        for mon in _list_running_monitors():
            try:
                if self._should_poll(mon, now):
                    self._poll_monitor(mon)
            except Exception as exc:
                log.warning("Poll error for monitor %s: %s", mon["id"], exc)
                _update_monitor_error(mon["id"], str(exc))

    def _should_poll(self, mon: dict, now: float) -> bool:
        """Check if enough time has elapsed since the last update."""
        updated_at = mon.get("updated_at", "")
        if not updated_at:
            return True
        try:
            last = datetime.fromisoformat(updated_at).timestamp()
            return (now - last) >= mon.get("interval_secs", 300)
        except (ValueError, TypeError):
            return True

    def _poll_monitor(self, mon: dict):
        """Check git HEAD and enqueue a scan job if the SHA changed."""
        repo_path = mon["repo_path"]
        current_sha = _get_commit_sha(repo_path)
        if not current_sha:
            return

        last_sha = mon.get("last_sha", "")
        if current_sha == last_sha:
            _touch_monitor(mon["id"])
            return

        # SHA changed — gather changed files and enqueue
        changed_files = _get_changed_files(repo_path, last_sha, current_sha) if last_sha else []

        job = {
            "monitor_id": mon["id"],
            "repo_path": repo_path,
            "framework": mon.get("framework", "eu_ai_act"),
            "scan_depth": mon.get("scan_depth", "content"),
            "max_files": mon.get("max_files", 500),
            "webhook_url": mon.get("webhook_url", ""),
            "commit_sha": current_sha,
            "prev_sha": last_sha,
            "changed_files": changed_files,
        }
        self._queue.append(job)
        log.info("Enqueued scan job for monitor %s (SHA %s)", mon["id"], current_sha[:8])

    # ── scan processing ───────────────────────────────────────────────

    def _process_queue(self):
        """Process one job from the queue (serial execution)."""
        if not self._queue:
            return
        job = self._queue.popleft()
        self._active_job = job
        try:
            self._run_scan_job(job)
        except Exception as exc:
            log.error("Scan job failed for monitor %s: %s", job["monitor_id"], exc)
            _update_monitor_error(job["monitor_id"], str(exc))
            _record_event(
                monitor_id=job["monitor_id"],
                event_type="error",
                commit_sha=job.get("commit_sha", ""),
                prev_sha=job.get("prev_sha", ""),
                error_msg=str(exc),
                changed_files=job.get("changed_files", []),
            )
        finally:
            self._active_job = None

    def _run_scan_job(self, job: dict):
        """Execute a scan, record event, check regression, dispatch alerts."""
        from comply.scanner import run_comply_scan

        monitor_id = job["monitor_id"]
        repo_path = job["repo_path"]
        framework = job["framework"]
        commit_sha = job["commit_sha"]
        prev_sha = job.get("prev_sha", "")
        changed_files = job.get("changed_files", [])

        # Run the scan
        report = run_comply_scan(
            target=repo_path,
            framework=framework,
            scan_depth=job.get("scan_depth", "content"),
            max_files=job.get("max_files", 500),
            use_cache=False,
        )

        score = report.get("summary", {}).get("score", 0)
        scan_id = report.get("scanId", "")

        # Check regression
        regression = None
        try:
            from comply.regression import detect_regression
            regression = detect_regression(repo_path, framework, report)
        except Exception as e:
            log.debug("Regression detection failed for monitor %s: %s", monitor_id, e)

        score_delta = 0.0
        if regression:
            score_delta = regression.get("scoreDelta", 0)

        # Update monitor state
        _update_monitor_after_scan(monitor_id, commit_sha, scan_id, score)

        # Record scan_complete event
        event_id = _record_event(
            monitor_id=monitor_id,
            event_type="scan_complete",
            commit_sha=commit_sha,
            prev_sha=prev_sha,
            scan_id=scan_id,
            score=score,
            score_delta=score_delta,
            changed_files=changed_files,
            regression_json=regression or {},
        )

        # Record regression event + dispatch alert
        if regression and regression.get("regressionDetected"):
            reg_event_id = _record_event(
                monitor_id=monitor_id,
                event_type="regression",
                commit_sha=commit_sha,
                prev_sha=prev_sha,
                scan_id=scan_id,
                score=score,
                score_delta=score_delta,
                changed_files=changed_files,
                regression_json=regression,
            )

            severity = regression.get("severity", "low")
            webhook_url = job.get("webhook_url", "")
            if webhook_url:
                _dispatch_alert(
                    monitor_id=monitor_id,
                    event_id=reg_event_id,
                    alert_type="regression",
                    severity=severity,
                    webhook_url=webhook_url,
                    commit_sha=commit_sha,
                    framework=framework,
                    score=score,
                    regression=regression,
                )

        log.info("Scan complete for monitor %s: score=%.1f%%, sha=%s",
                 monitor_id, score, commit_sha[:8])


# ── Git helpers ───────────────────────────────────────────────────────────

def _get_commit_sha(repo_path: str) -> str:
    """Get the current HEAD commit SHA for a repo."""
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


def _get_changed_files(repo_path: str, old_sha: str, new_sha: str) -> list:
    """Get list of files changed between two commits."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", old_sha, new_sha],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("git diff failed for %s (%s..%s): %s", repo_path, old_sha[:8], new_sha[:8], e)
    return []


# ── Alert dispatch ────────────────────────────────────────────────────────

def _dispatch_alert(
    monitor_id: str,
    event_id: str,
    alert_type: str,
    severity: str,
    webhook_url: str,
    commit_sha: str,
    framework: str,
    score: float,
    regression: Optional[dict] = None,
):
    """Dispatch a webhook alert with deduplication."""
    # Dedup key: hash of (monitor_id, alert_type, commit_sha)
    raw = f"{monitor_id}:{alert_type}:{commit_sha}"
    dedup_key = hashlib.sha256(raw.encode()).hexdigest()[:32]

    # Check if already dispatched
    from comply.store import _get_conn
    conn = _get_conn()
    existing = conn.execute(
        "SELECT id FROM monitor_alerts WHERE dedup_key = ?", (dedup_key,)
    ).fetchone()
    if existing:
        return

    new_gaps = regression.get("newGaps", []) if regression else []
    payload = {
        "text": (
            f"Comply alert: {alert_type} in {framework}\n"
            f"Score: {score:.1f}%\n"
            f"Commit: {commit_sha[:8]}\n"
            f"New gaps: {len(new_gaps)}"
        ),
        "comply_alert": {
            "monitorId": monitor_id,
            "alertType": alert_type,
            "severity": severity,
            "framework": framework,
            "score": score,
            "commitSha": commit_sha,
            "newGapCount": len(new_gaps),
        },
    }

    response_code = 0
    dispatched = 0
    try:
        import httpx
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        response_code = resp.status_code
        dispatched = 1 if resp.is_success else 0
    except Exception as exc:
        log.warning("Alert dispatch failed: %s", exc)

    _save_alert(
        monitor_id=monitor_id,
        event_id=event_id,
        alert_type=alert_type,
        severity=severity,
        webhook_url=webhook_url,
        dispatched=dispatched,
        dedup_key=dedup_key,
        response_code=response_code,
    )


# ── Store CRUD ────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_monitor(
    repo_path: str,
    framework: str = "eu_ai_act",
    scan_depth: str = "content",
    interval_secs: int = 300,
    max_files: int = 500,
    webhook_url: str = "",
) -> dict:
    """Create a new monitor and return its dict."""
    from comply.store import _get_conn
    conn = _get_conn()
    mid = uuid.uuid4().hex[:12]
    now = _now_iso()
    abs_path = os.path.abspath(repo_path)

    conn.execute(
        """INSERT INTO monitors
           (id, repo_path, framework, scan_depth, interval_secs, max_files,
            webhook_url, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'stopped', ?, ?)""",
        (mid, abs_path, framework, scan_depth, interval_secs, max_files,
         webhook_url, now, now),
    )
    conn.commit()
    return get_monitor(mid)


def get_monitor(monitor_id: str) -> Optional[dict]:
    """Get a monitor by ID."""
    from comply.store import _get_conn
    conn = _get_conn()
    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def list_monitors(status: Optional[str] = None) -> list:
    """List all monitors, optionally filtered by status."""
    from comply.store import _get_conn
    conn = _get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM monitors WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM monitors ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_monitor(monitor_id: str, **kwargs) -> Optional[dict]:
    """Update monitor fields. Returns updated monitor or None."""
    from comply.store import _get_conn
    conn = _get_conn()
    allowed = {"framework", "scan_depth", "interval_secs", "max_files", "webhook_url"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_monitor(monitor_id)

    updates["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [monitor_id]
    conn.execute(f"UPDATE monitors SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return get_monitor(monitor_id)


def delete_monitor(monitor_id: str) -> bool:
    """Delete a monitor and its events/alerts. Returns True if deleted."""
    from comply.store import _get_conn
    conn = _get_conn()

    # Stop it first if running
    mon = get_monitor(monitor_id)
    if mon and mon.get("status") == "running":
        stop_monitor(monitor_id)

    conn.execute("DELETE FROM monitor_alerts WHERE monitor_id = ?", (monitor_id,))
    conn.execute("DELETE FROM monitor_events WHERE monitor_id = ?", (monitor_id,))
    cursor = conn.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
    conn.commit()
    return cursor.rowcount > 0


def start_monitor(monitor_id: str) -> Optional[dict]:
    """Set monitor status to running. Starts daemon if needed."""
    from comply.store import _get_conn
    conn = _get_conn()
    now = _now_iso()
    conn.execute(
        "UPDATE monitors SET status = 'running', updated_at = ? WHERE id = ?",
        (now, monitor_id),
    )
    conn.commit()

    _record_event(monitor_id=monitor_id, event_type="started")

    # Auto-start daemon
    daemon = get_daemon()
    if not daemon.is_running():
        daemon.start()

    return get_monitor(monitor_id)


def stop_monitor(monitor_id: str) -> Optional[dict]:
    """Set monitor status to stopped. Stops daemon if no monitors running."""
    from comply.store import _get_conn
    conn = _get_conn()
    now = _now_iso()
    conn.execute(
        "UPDATE monitors SET status = 'stopped', updated_at = ? WHERE id = ?",
        (now, monitor_id),
    )
    conn.commit()

    _record_event(monitor_id=monitor_id, event_type="stopped")

    # Auto-stop daemon if no running monitors left
    remaining = _list_running_monitors()
    if not remaining:
        daemon = get_daemon()
        if daemon.is_running():
            daemon.stop()

    return get_monitor(monitor_id)


# ── Internal store helpers ────────────────────────────────────────────────

def _list_running_monitors() -> list:
    """List monitors with status='running'."""
    from comply.store import _get_conn
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM monitors WHERE status = 'running' ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


def _touch_monitor(monitor_id: str):
    """Update the updated_at timestamp."""
    from comply.store import _get_conn
    conn = _get_conn()
    conn.execute(
        "UPDATE monitors SET updated_at = ? WHERE id = ?", (_now_iso(), monitor_id)
    )
    conn.commit()


def _update_monitor_after_scan(monitor_id: str, sha: str, scan_id: str, score: float):
    """Update monitor with scan results."""
    from comply.store import _get_conn
    conn = _get_conn()
    conn.execute(
        """UPDATE monitors
           SET last_sha = ?, last_scan_id = ?, last_score = ?,
               last_error = '', updated_at = ?
           WHERE id = ?""",
        (sha, scan_id, score, _now_iso(), monitor_id),
    )
    conn.commit()


def _update_monitor_error(monitor_id: str, error: str):
    """Record an error on a monitor."""
    from comply.store import _get_conn
    conn = _get_conn()
    conn.execute(
        "UPDATE monitors SET last_error = ?, status = 'error', updated_at = ? WHERE id = ?",
        (error, _now_iso(), monitor_id),
    )
    conn.commit()


def _record_event(
    monitor_id: str,
    event_type: str,
    commit_sha: str = "",
    prev_sha: str = "",
    scan_id: str = "",
    score: float = 0,
    score_delta: float = 0,
    changed_files: Optional[list] = None,
    regression_json: Optional[dict] = None,
    error_msg: str = "",
) -> str:
    """Record a monitor event. Returns event ID."""
    from comply.store import _get_conn
    conn = _get_conn()
    eid = uuid.uuid4().hex[:12]
    now = _now_iso()
    conn.execute(
        """INSERT INTO monitor_events
           (id, monitor_id, event_type, commit_sha, prev_sha, scan_id,
            score, score_delta, changed_files, regression_json, error_msg, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            eid, monitor_id, event_type, commit_sha, prev_sha, scan_id,
            score, score_delta,
            json.dumps(changed_files or []),
            json.dumps(regression_json or {}),
            error_msg, now,
        ),
    )
    conn.commit()
    return eid


def list_monitor_events(monitor_id: str, limit: int = 50) -> list:
    """List events for a specific monitor."""
    from comply.store import _get_conn
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM monitor_events WHERE monitor_id = ? ORDER BY created_at DESC LIMIT ?",
        (monitor_id, limit),
    ).fetchall()
    return [_event_to_dict(r) for r in rows]


def list_recent_events(limit: int = 50) -> list:
    """List recent events across all monitors."""
    from comply.store import _get_conn
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM monitor_events ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_event_to_dict(r) for r in rows]


def _save_alert(
    monitor_id: str,
    event_id: str,
    alert_type: str,
    severity: str,
    webhook_url: str,
    dispatched: int,
    dedup_key: str,
    response_code: int,
):
    """Persist an alert record."""
    from comply.store import _get_conn
    conn = _get_conn()
    aid = uuid.uuid4().hex[:12]
    now = _now_iso()
    try:
        conn.execute(
            """INSERT INTO monitor_alerts
               (id, monitor_id, event_id, alert_type, severity, webhook_url,
                dispatched, dedup_key, response_code, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, monitor_id, event_id, alert_type, severity, webhook_url,
             dispatched, dedup_key, response_code, now),
        )
        conn.commit()
    except Exception as exc:
        log.warning("Failed to save alert: %s", exc)


def list_monitor_alerts(monitor_id: Optional[str] = None, limit: int = 50) -> list:
    """List alerts, optionally filtered by monitor."""
    from comply.store import _get_conn
    conn = _get_conn()
    if monitor_id:
        rows = conn.execute(
            "SELECT * FROM monitor_alerts WHERE monitor_id = ? ORDER BY created_at DESC LIMIT ?",
            (monitor_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM monitor_alerts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Dict conversion ──────────────────────────────────────────────────────

def _event_to_dict(row) -> dict:
    """Convert an event row to a dict with parsed JSON fields."""
    d = dict(row)
    try:
        d["changed_files"] = json.loads(d.get("changed_files", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["changed_files"] = []
    try:
        d["regression"] = json.loads(d.pop("regression_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        d["regression"] = {}
    return d
