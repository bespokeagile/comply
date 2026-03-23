"""SQLite scan history — persists scan results in ~/.comply/scans.db.

No graph queries needed: flat JSON blobs for history, diff, and regression.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

_DB_DIR = os.environ.get("COMPLY_DATA_DIR", os.path.expanduser("~/.comply"))
_DB_PATH = os.path.join(_DB_DIR, "scans.db")
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection (auto-creates DB on first use)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(_DB_DIR, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
        _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id            TEXT PRIMARY KEY,
            repo_path     TEXT NOT NULL,
            repo_url      TEXT NOT NULL DEFAULT '',
            framework     TEXT NOT NULL,
            scan_depth    TEXT NOT NULL DEFAULT 'content',
            commit_sha    TEXT NOT NULL DEFAULT '',
            score         REAL NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'complete',
            is_baseline   INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL,
            completed_at  TEXT NOT NULL DEFAULT '',
            report_json   TEXT NOT NULL DEFAULT '{}',
            summary_json  TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_scans_repo_fw_date
            ON scans (repo_path, framework, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_scans_status
            ON scans (status);

        CREATE TABLE IF NOT EXISTS audit_records (
            id              TEXT PRIMARY KEY,
            adapter_name    TEXT NOT NULL,
            timestamp       TEXT NOT NULL DEFAULT '',
            tool_name       TEXT NOT NULL DEFAULT '',
            caller_identity TEXT NOT NULL DEFAULT '',
            action          TEXT NOT NULL DEFAULT 'call',
            duration_ms     REAL NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'ok',
            policy_matched  TEXT NOT NULL DEFAULT '',
            cost_usd        REAL NOT NULL DEFAULT 0,
            metadata_json   TEXT NOT NULL DEFAULT '{}',
            ingested_at     TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_adapter_ts
            ON audit_records (adapter_name, timestamp DESC);

        CREATE TABLE IF NOT EXISTS monitors (
            id              TEXT PRIMARY KEY,
            repo_path       TEXT NOT NULL,
            framework       TEXT NOT NULL DEFAULT 'eu_ai_act',
            scan_depth      TEXT NOT NULL DEFAULT 'content',
            interval_secs   INTEGER NOT NULL DEFAULT 300,
            max_files       INTEGER NOT NULL DEFAULT 500,
            webhook_url     TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'stopped',
            last_sha        TEXT NOT NULL DEFAULT '',
            last_scan_id    TEXT NOT NULL DEFAULT '',
            last_score      REAL NOT NULL DEFAULT 0,
            last_error      TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS monitor_events (
            id              TEXT PRIMARY KEY,
            monitor_id      TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            commit_sha      TEXT NOT NULL DEFAULT '',
            prev_sha        TEXT NOT NULL DEFAULT '',
            scan_id         TEXT NOT NULL DEFAULT '',
            score           REAL NOT NULL DEFAULT 0,
            score_delta     REAL NOT NULL DEFAULT 0,
            changed_files   TEXT NOT NULL DEFAULT '[]',
            regression_json TEXT NOT NULL DEFAULT '{}',
            error_msg       TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_monitor_events_monitor
            ON monitor_events (monitor_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS monitor_alerts (
            id              TEXT PRIMARY KEY,
            monitor_id      TEXT NOT NULL,
            event_id        TEXT NOT NULL DEFAULT '',
            alert_type      TEXT NOT NULL,
            severity        TEXT NOT NULL DEFAULT 'low',
            webhook_url     TEXT NOT NULL DEFAULT '',
            dispatched      INTEGER NOT NULL DEFAULT 0,
            dedup_key       TEXT UNIQUE,
            response_code   INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_monitor_alerts_monitor
            ON monitor_alerts (monitor_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS gate_decisions (
            id                  TEXT PRIMARY KEY,
            repo_path           TEXT NOT NULL,
            framework           TEXT NOT NULL,
            scan_id             TEXT NOT NULL DEFAULT '',
            commit_sha          TEXT NOT NULL DEFAULT '',
            decision            TEXT NOT NULL,
            exit_code           INTEGER NOT NULL DEFAULT 0,
            score               REAL NOT NULL DEFAULT 0,
            threshold_score     REAL NOT NULL DEFAULT 0,
            regression_detected INTEGER NOT NULL DEFAULT 0,
            fail_on_regression  INTEGER NOT NULL DEFAULT 0,
            max_critical_gaps   INTEGER NOT NULL DEFAULT -1,
            critical_gap_count  INTEGER NOT NULL DEFAULT 0,
            reason              TEXT NOT NULL DEFAULT '',
            created_at          TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_gate_repo_fw
            ON gate_decisions (repo_path, framework, created_at DESC);

        CREATE TABLE IF NOT EXISTS demo_counters (
            metric  TEXT PRIMARY KEY,
            value   REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS programs (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            description     TEXT NOT NULL DEFAULT '',
            repos_json      TEXT NOT NULL DEFAULT '[]',
            frameworks_json TEXT NOT NULL DEFAULT '[]',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );
    """)
    # Add visitor_id column (safe for existing DBs)
    try:
        conn.execute("ALTER TABLE scans ADD COLUMN visitor_id TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_visitor ON scans (visitor_id, created_at DESC)")
    conn.commit()


def init_db():
    """Explicitly initialize the DB (idempotent)."""
    _get_conn()


def save_scan(report: dict, visitor_id: str = "") -> str:
    """Persist a completed scan report. Returns the scan ID."""
    conn = _get_conn()
    scan_id = report.get("scanId", "")
    summary = report.get("summary", {})

    # Strip internal fields before storing
    clean = {k: v for k, v in report.items() if not k.startswith("_")}

    conn.execute(
        """INSERT OR REPLACE INTO scans
           (id, repo_path, repo_url, framework, scan_depth, commit_sha,
            score, status, created_at, completed_at, report_json, summary_json,
            visitor_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scan_id,
            report.get("repoPath", ""),
            report.get("target", ""),
            report.get("framework", ""),
            report.get("scanDepth", "content"),
            report.get("commitSha", ""),
            summary.get("score", 0),
            "complete",
            report.get("generatedAt", datetime.now(timezone.utc).isoformat()),
            report.get("generatedAt", ""),
            json.dumps(clean, default=str),
            json.dumps(summary, default=str),
            visitor_id,
        ),
    )
    conn.commit()
    return scan_id


def get_scan(scan_id: str) -> Optional[dict]:
    """Retrieve a single scan by ID. Returns None if not found."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_scans(
    repo: Optional[str] = None,
    framework: Optional[str] = None,
    limit: int = 20,
) -> list:
    """List scans, optionally filtered by repo path and/or framework."""
    conn = _get_conn()
    clauses = []
    params = []

    if repo:
        # Match by suffix so both absolute and relative paths work
        clauses.append("(repo_path = ? OR repo_path LIKE ?)")
        params.extend([os.path.abspath(repo), "%" + repo.rstrip("/") + "%"])
    if framework:
        clauses.append("framework = ?")
        params.append(framework)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)

    rows = conn.execute(
        f"SELECT * FROM scans {where} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_latest_scan(repo: str, framework: str) -> Optional[dict]:
    """Get the most recent scan for a repo+framework combo."""
    conn = _get_conn()
    repo_stripped = repo.rstrip("/")
    row = conn.execute(
        """SELECT * FROM scans
           WHERE ((repo_path = ? OR repo_path LIKE ?)
                  OR (repo_url = ? OR repo_url LIKE ?))
             AND framework = ?
           ORDER BY created_at DESC LIMIT 1""",
        (os.path.abspath(repo), "%" + repo_stripped + "%",
         repo_stripped, "%" + repo_stripped + "%", framework),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def delete_scan(scan_id: str) -> bool:
    """Delete a scan by ID. Returns True if deleted."""
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    conn.commit()
    return cursor.rowcount > 0


def list_visitor_scans(visitor_id: str, limit: int = 50) -> list:
    """List scans for a visitor (summary only, no full report_json)."""
    if not visitor_id:
        return []
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, repo_path, repo_url, framework, scan_depth, commit_sha,
                  score, status, created_at, visitor_id
           FROM scans WHERE visitor_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (visitor_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def delete_visitor_scans(visitor_id: str) -> int:
    """Delete all scans for a visitor. Returns number deleted."""
    if not visitor_id:
        return 0
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM scans WHERE visitor_id = ?", (visitor_id,))
    conn.commit()
    return cursor.rowcount


def set_baseline(scan_id: str) -> bool:
    """Mark a scan as the baseline for its repo+framework. Clears previous baseline."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT repo_path, framework FROM scans WHERE id = ?", (scan_id,)
    ).fetchone()
    if row is None:
        return False

    # Clear previous baseline for same repo+framework
    conn.execute(
        "UPDATE scans SET is_baseline = 0 WHERE repo_path = ? AND framework = ?",
        (row["repo_path"], row["framework"]),
    )
    conn.execute("UPDATE scans SET is_baseline = 1 WHERE id = ?", (scan_id,))
    conn.commit()
    return True


def get_baseline(repo: str, framework: str) -> Optional[dict]:
    """Get the baseline scan for a repo+framework combo."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT * FROM scans
           WHERE (repo_path = ? OR repo_path LIKE ?) AND framework = ? AND is_baseline = 1
           LIMIT 1""",
        (os.path.abspath(repo), "%" + repo.rstrip("/") + "%", framework),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def ingest_audit_records(records: list) -> int:
    """Ingest a list of NormalizedTrafficRecord dicts into the audit_records table.

    Returns the number of records inserted.
    """
    conn = _get_conn()
    count = 0
    now = datetime.now(timezone.utc).isoformat()
    for rec in records:
        d = rec if isinstance(rec, dict) else rec.to_dict()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO audit_records
                   (id, adapter_name, timestamp, tool_name, caller_identity,
                    action, duration_ms, status, policy_matched, cost_usd,
                    metadata_json, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    d.get("record_id", ""),
                    d.get("source_adapter", ""),
                    d.get("timestamp", ""),
                    d.get("tool_name", ""),
                    d.get("caller_identity", ""),
                    d.get("action", "call"),
                    d.get("duration_ms", 0),
                    d.get("status", "ok"),
                    d.get("policy_matched", ""),
                    d.get("cost_usd", 0),
                    json.dumps(d.get("metadata", {}), default=str),
                    now,
                ),
            )
            count += 1
        except sqlite3.Error as e:
            log.debug("Failed to ingest audit record %s: %s", d.get("record_id", ""), e)
    conn.commit()
    return count


def query_audit_records(
    adapter: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
) -> list:
    """Query audit records with optional filters."""
    conn = _get_conn()
    clauses = []
    params = []

    if adapter:
        clauses.append("adapter_name = ?")
        params.append(adapter)
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("timestamp <= ?")
        params.append(until)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)

    rows = conn.execute(
        f"SELECT * FROM audit_records {where} ORDER BY timestamp DESC LIMIT ?",
        params,
    ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d.pop("metadata_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            d["metadata"] = {}
        result.append(d)
    return result


def get_audit_summary(adapter: Optional[str] = None) -> dict:
    """Return aggregate statistics for ingested audit records."""
    conn = _get_conn()
    clause = "WHERE adapter_name = ?" if adapter else ""
    params = [adapter] if adapter else []

    row = conn.execute(
        f"""SELECT
            COUNT(*) as total,
            SUM(CASE WHEN action = 'deny' THEN 1 ELSE 0 END) as denials,
            SUM(CASE WHEN action = 'error' OR status = 'error' THEN 1 ELSE 0 END) as errors,
            SUM(cost_usd) as total_cost,
            COUNT(DISTINCT caller_identity) as unique_callers,
            COUNT(DISTINCT tool_name) as unique_tools
        FROM audit_records {clause}""",
        params,
    ).fetchone()

    d = dict(row) if row else {}
    return {
        "total_records": d.get("total", 0),
        "total_denials": d.get("denials", 0),
        "total_errors": d.get("errors", 0),
        "total_cost": d.get("total_cost", 0) or 0,
        "unique_callers": d.get("unique_callers", 0),
        "unique_tools": d.get("unique_tools", 0),
    }


CICD_ADAPTER_NAMES = ("github_actions", "gitlab_ci")


def query_cicd_records(
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 500,
    cicd_type: Optional[str] = None,
) -> list:
    """Query audit records from CI/CD adapters only.

    Parameters
    ----------
    since, until : str or None
        ISO-8601 time bounds.
    limit : int
        Max records to return.
    cicd_type : str or None
        Filter by metadata cicd_type (workflow_run, test_result, deployment).
    """
    conn = _get_conn()
    placeholders = ",".join("?" for _ in CICD_ADAPTER_NAMES)
    clauses = [f"adapter_name IN ({placeholders})"]
    params: list = list(CICD_ADAPTER_NAMES)

    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("timestamp <= ?")
        params.append(until)
    if cicd_type:
        clauses.append("metadata_json LIKE ?")
        params.append(f'%"cicd_type": "{cicd_type}"%')

    where = "WHERE " + " AND ".join(clauses)
    params.append(limit)

    rows = conn.execute(
        f"SELECT * FROM audit_records {where} ORDER BY timestamp DESC LIMIT ?",
        params,
    ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d.pop("metadata_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            d["metadata"] = {}
        result.append(d)
    return result


def get_cicd_summary() -> dict:
    """Aggregate CI/CD statistics from ingested records."""
    conn = _get_conn()
    placeholders = ",".join("?" for _ in CICD_ADAPTER_NAMES)
    params: list = list(CICD_ADAPTER_NAMES)

    row = conn.execute(
        f"""SELECT
            COUNT(*) as total,
            SUM(CASE WHEN action = 'error' THEN 1 ELSE 0 END) as failures,
            SUM(CASE WHEN action = 'call' THEN 1 ELSE 0 END) as successes
        FROM audit_records
        WHERE adapter_name IN ({placeholders})""",
        params,
    ).fetchone()

    d = dict(row) if row else {}
    total = d.get("total", 0) or 0
    failures = d.get("failures", 0) or 0
    successes = d.get("successes", 0) or 0

    # Count by cicd_type from metadata
    all_rows = conn.execute(
        f"SELECT metadata_json FROM audit_records WHERE adapter_name IN ({placeholders})",
        list(CICD_ADAPTER_NAMES),
    ).fetchall()

    type_counts = {"workflow_run": 0, "test_result": 0, "deployment": 0}
    for r in all_rows:
        try:
            meta = json.loads(r["metadata_json"])
            ct = meta.get("cicd_type", "")
            if ct in type_counts:
                type_counts[ct] += 1
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "total_records": total,
        "pipelines": type_counts["workflow_run"],
        "test_runs": type_counts["test_result"],
        "deployments": type_counts["deployment"],
        "failures": failures,
        "successes": successes,
        "pass_rate": round(successes / max(total, 1) * 100, 1),
    }


def get_scan_statistics() -> dict:
    """Return aggregate scan statistics for public reporting.

    Powers the "100 repos scanned" report and /audit/stats endpoint.
    """
    conn = _get_conn()

    # Overall stats
    overall = conn.execute("""
        SELECT
            COUNT(*) as total_scans,
            COUNT(DISTINCT repo_path) as unique_repos,
            AVG(score) as avg_score,
            MIN(score) as min_score,
            MAX(score) as max_score,
            MIN(created_at) as first_scan,
            MAX(created_at) as last_scan
        FROM scans WHERE status = 'complete'
    """).fetchone()
    overall = dict(overall) if overall else {}

    # Per-framework breakdown
    fw_rows = conn.execute("""
        SELECT
            framework,
            COUNT(*) as scan_count,
            AVG(score) as avg_score,
            MIN(score) as min_score,
            MAX(score) as max_score
        FROM scans WHERE status = 'complete'
        GROUP BY framework
        ORDER BY scan_count DESC
    """).fetchall()
    frameworks = [dict(r) for r in fw_rows]

    # Score distribution (buckets: 0-20, 20-40, 40-60, 60-80, 80-100)
    dist_rows = conn.execute("""
        SELECT
            CASE
                WHEN score < 20 THEN '0-20'
                WHEN score < 40 THEN '20-40'
                WHEN score < 60 THEN '40-60'
                WHEN score < 80 THEN '60-80'
                ELSE '80-100'
            END as bucket,
            COUNT(*) as count
        FROM scans WHERE status = 'complete'
        GROUP BY bucket
        ORDER BY bucket
    """).fetchall()
    distribution = {r["bucket"]: r["count"] for r in dist_rows}

    # Most common gap controls (from summary_json)
    gap_counts: dict = {}
    scan_rows = conn.execute(
        "SELECT summary_json FROM scans WHERE status = 'complete' LIMIT 500"
    ).fetchall()
    for row in scan_rows:
        try:
            summary = json.loads(row["summary_json"])
            gap = summary.get("gap", 0)
            if gap > 0:
                gap_counts["has_gaps"] = gap_counts.get("has_gaps", 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass

    total_scans = overall.get("total_scans", 0)
    return {
        "totalScans": total_scans,
        "uniqueRepos": overall.get("unique_repos", 0),
        "averageScore": round(overall.get("avg_score", 0) or 0, 1),
        "minScore": round(overall.get("min_score", 0) or 0, 1),
        "maxScore": round(overall.get("max_score", 0) or 0, 1),
        "firstScan": overall.get("first_scan", ""),
        "lastScan": overall.get("last_scan", ""),
        "frameworks": frameworks,
        "scoreDistribution": distribution,
        "reposWithGaps": gap_counts.get("has_gaps", 0),
        "gapRate": round(gap_counts.get("has_gaps", 0) / max(total_scans, 1) * 100, 1),
    }


# ── Gate decisions ────────────────────────────────────────────────────────


def save_gate_decision(decision: dict) -> str:
    """Persist a gate decision. Returns the decision ID."""
    conn = _get_conn()
    did = decision.get("decisionId", "")
    conn.execute(
        """INSERT OR REPLACE INTO gate_decisions
           (id, repo_path, framework, scan_id, commit_sha, decision, exit_code,
            score, threshold_score, regression_detected, fail_on_regression,
            max_critical_gaps, critical_gap_count, reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            did,
            decision.get("repoPath", ""),
            decision.get("framework", ""),
            decision.get("scanId", ""),
            decision.get("commitSha", ""),
            decision.get("decision", "fail"),
            decision.get("exitCode", 1),
            decision.get("score", 0),
            decision.get("thresholdScore", 0),
            1 if decision.get("regressionDetected") else 0,
            1 if decision.get("failOnRegression") else 0,
            decision.get("maxCriticalGaps", -1),
            decision.get("criticalGapCount", 0),
            decision.get("reason", ""),
            decision.get("createdAt", datetime.now(timezone.utc).isoformat()),
        ),
    )
    conn.commit()
    return did


def get_gate_decision(decision_id: str) -> Optional[dict]:
    """Retrieve a single gate decision by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM gate_decisions WHERE id = ?", (decision_id,)
    ).fetchone()
    if row is None:
        return None
    return _gate_row_to_dict(row)


def list_gate_decisions(
    repo: Optional[str] = None,
    framework: Optional[str] = None,
    limit: int = 50,
) -> list:
    """List gate decisions with optional filters."""
    conn = _get_conn()
    clauses = []
    params = []

    if repo:
        clauses.append("(repo_path = ? OR repo_path LIKE ?)")
        params.extend([os.path.abspath(repo), "%" + repo.rstrip("/") + "%"])
    if framework:
        clauses.append("framework = ?")
        params.append(framework)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)

    rows = conn.execute(
        f"SELECT * FROM gate_decisions {where} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [_gate_row_to_dict(row) for row in rows]


def get_gate_summary(
    repo: Optional[str] = None,
    framework: Optional[str] = None,
) -> dict:
    """Aggregate gate decision statistics."""
    conn = _get_conn()
    clauses = []
    params = []

    if repo:
        clauses.append("(repo_path = ? OR repo_path LIKE ?)")
        params.extend([os.path.abspath(repo), "%" + repo.rstrip("/") + "%"])
    if framework:
        clauses.append("framework = ?")
        params.append(framework)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    row = conn.execute(
        f"""SELECT
            COUNT(*) as total,
            SUM(CASE WHEN decision = 'pass' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN decision = 'fail' THEN 1 ELSE 0 END) as failed,
            AVG(score) as avg_score
        FROM gate_decisions {where}""",
        params,
    ).fetchone()

    d = dict(row) if row else {}
    total = d.get("total", 0) or 0
    passed = d.get("passed", 0) or 0
    failed = d.get("failed", 0) or 0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "passRate": round(passed / max(total, 1) * 100, 1),
        "avgScore": round(d.get("avg_score", 0) or 0, 1),
    }


def _gate_row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a gate_decisions row to a dict."""
    d = dict(row)
    return {
        "decisionId": d.get("id", ""),
        "repoPath": d.get("repo_path", ""),
        "framework": d.get("framework", ""),
        "scanId": d.get("scan_id", ""),
        "commitSha": d.get("commit_sha", ""),
        "decision": d.get("decision", ""),
        "exitCode": d.get("exit_code", 0),
        "score": d.get("score", 0),
        "thresholdScore": d.get("threshold_score", 0),
        "regressionDetected": bool(d.get("regression_detected", 0)),
        "failOnRegression": bool(d.get("fail_on_regression", 0)),
        "maxCriticalGaps": d.get("max_critical_gaps", -1),
        "criticalGapCount": d.get("critical_gap_count", 0),
        "reason": d.get("reason", ""),
        "createdAt": d.get("created_at", ""),
    }


def save_scan_metadata(report: dict, visitor_id: str = "") -> str:
    """Persist scan metadata only (no plaintext report). Returns the scan ID.

    Used by cost_scan: server runs the scan but does not retain the full report.
    The client encrypts the report and pushes it back via save_encrypted_scan().
    """
    conn = _get_conn()
    scan_id = report.get("scanId", "")
    summary = report.get("summary", {})

    conn.execute(
        """INSERT OR REPLACE INTO scans
           (id, repo_path, repo_url, framework, scan_depth, commit_sha,
            score, status, created_at, completed_at, report_json, summary_json,
            visitor_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scan_id,
            report.get("repoPath", ""),
            report.get("target", ""),
            report.get("framework", ""),
            report.get("scanDepth", "content"),
            report.get("commitSha", ""),
            summary.get("score", 0),
            "complete",
            report.get("generatedAt", datetime.now(timezone.utc).isoformat()),
            report.get("generatedAt", ""),
            "{}",  # no plaintext report stored
            json.dumps(summary, default=str),
            visitor_id,
        ),
    )
    conn.commit()
    return scan_id


def save_encrypted_scan(
    scan_id: str, visitor_id: str, iv: str, ciphertext: str, metadata: dict
) -> bool:
    """Store an encrypted report blob for an existing scan.

    The client encrypts the full report client-side (AES-256-GCM) and pushes
    the opaque {iv, ciphertext} pair. Server stores it but cannot read it.
    Returns True if updated, False if scan not found or ownership mismatch.
    """
    conn = _get_conn()
    row = conn.execute("SELECT visitor_id FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        # No existing metadata row -- insert a new one from metadata
        conn.execute(
            """INSERT OR REPLACE INTO scans
               (id, repo_path, repo_url, framework, scan_depth, commit_sha,
                score, status, created_at, completed_at, report_json, summary_json,
                visitor_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scan_id,
                "",
                metadata.get("url", ""),
                metadata.get("framework", ""),
                metadata.get("depth", "structure"),
                "",
                metadata.get("score", 0),
                "complete",
                metadata.get("timestamp", datetime.now(timezone.utc).isoformat()),
                metadata.get("timestamp", ""),
                json.dumps({"iv": iv, "ciphertext": ciphertext}),
                "{}",
                visitor_id,
            ),
        )
        conn.commit()
        return True

    # Verify ownership
    existing_vid = row["visitor_id"] if row else ""
    if existing_vid and visitor_id and existing_vid != visitor_id:
        return False

    encrypted_blob = json.dumps({"iv": iv, "ciphertext": ciphertext})
    conn.execute(
        "UPDATE scans SET report_json = ? WHERE id = ?",
        (encrypted_blob, scan_id),
    )
    conn.commit()
    return True


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a DB row to a scan summary dict (with parsed JSON fields)."""
    d = dict(row)
    d["is_baseline"] = bool(d.get("is_baseline", 0))
    try:
        report = json.loads(d.pop("report_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        report = {}
    # Detect encrypted blobs: only iv + ciphertext keys
    if set(report.keys()) == {"iv", "ciphertext"}:
        d["encrypted"] = True
        d["report"] = report  # pass through opaque blob
    else:
        d["encrypted"] = False
        d["report"] = report
    try:
        d["summary"] = json.loads(d.pop("summary_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        d["summary"] = {}
    return d


# ── Anonymous demo counters ──────────────────────────────────────────────


def increment_demo_counter(metric: str, amount: float = 1.0):
    """Atomically increment an anonymous demo counter."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO demo_counters (metric, value) VALUES (?, ?)
           ON CONFLICT(metric) DO UPDATE SET value = value + excluded.value""",
        (metric, amount),
    )
    conn.commit()


def get_demo_counters() -> dict:
    """Return all anonymous demo counters as {metric: value}."""
    conn = _get_conn()
    rows = conn.execute("SELECT metric, value FROM demo_counters").fetchall()
    return {r["metric"]: r["value"] for r in rows}


# -- Programs (portfolio grouping) --------------------------------------------


def save_program(program: dict) -> str:
    """Create or update a program. Returns the program ID."""
    import uuid
    conn = _get_conn()
    pid = program.get("id") or str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()
    repos = json.dumps(program.get("repos", []))
    frameworks = json.dumps(program.get("frameworks", []))

    conn.execute(
        """INSERT OR REPLACE INTO programs
           (id, name, description, repos_json, frameworks_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pid, program.get("name", ""), program.get("description", ""),
         repos, frameworks,
         program.get("created_at", now), now),
    )
    conn.commit()
    return pid


def get_program(program_id: str) -> Optional[dict]:
    """Return a single program by ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone()
    if not row:
        return None
    return _program_row_to_dict(row)


def list_programs() -> list:
    """Return all programs, newest first."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM programs ORDER BY created_at DESC").fetchall()
    return [_program_row_to_dict(r) for r in rows]


def delete_program(program_id: str) -> bool:
    """Delete a program. Returns True if deleted."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM programs WHERE id = ?", (program_id,))
    conn.commit()
    return cur.rowcount > 0


def get_program_posture(program_id: str) -> dict:
    """Compute aggregate posture for a program from its latest scans."""
    prog = get_program(program_id)
    if not prog:
        return {"error": "Program not found"}

    repos = prog.get("repos", [])
    frameworks = prog.get("frameworks", [])
    repo_results = []

    for repo_entry in repos:
        repo_url = repo_entry if isinstance(repo_entry, str) else repo_entry.get("url", "")
        repo_label = repo_url.rstrip("/").rsplit("/", 1)[-1] if "/" in repo_url else repo_url
        if isinstance(repo_entry, dict):
            repo_label = repo_entry.get("label", repo_label)

        fw_results = []
        for fw in frameworks:
            scan = get_latest_scan(repo_url, fw)
            if scan:
                fw_results.append({
                    "framework": fw,
                    "score": scan.get("score", 0),
                    "scan_id": scan.get("id", ""),
                    "scan_depth": scan.get("scan_depth", ""),
                    "created_at": scan.get("created_at", ""),
                })
            else:
                fw_results.append({"framework": fw, "score": None, "scan_id": None})
        repo_results.append({"url": repo_url, "label": repo_label, "frameworks": fw_results})

    # Aggregate scores
    all_scores = [fw["score"] for r in repo_results for fw in r["frameworks"] if fw["score"] is not None]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    scanned = len(all_scores)
    total_cells = len(repos) * len(frameworks)

    return {
        "program_id": program_id,
        "name": prog.get("name", ""),
        "repos": repo_results,
        "avg_score": round(avg_score, 1),
        "scanned": scanned,
        "total": total_cells,
        "coverage": round(scanned / total_cells * 100, 1) if total_cells else 0,
    }


def _program_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "repos": json.loads(row["repos_json"]),
        "frameworks": json.loads(row["frameworks_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
