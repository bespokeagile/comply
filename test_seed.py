"""Test data seeder — create named SQLite databases for UI testing.

Usage:
    python3 -m comply.test_seed <persona>       # seed ~/.comply/scans.db
    python3 -m comply.test_seed <persona> --dir /tmp/comply-test  # seed custom dir
    python3 -m comply.test_seed list             # show available personas
    python3 -m comply.test_seed clean            # reset to empty DB

Personas:
    new_user     — Empty. First-time install, no scans yet.
    single_repo  — 1 repo, 3 frameworks, 2 scans each, 1 gate, 1 monitor.
    multi_repo   — 5 repos, mixed frameworks, gates, monitors, events.
    power_user   — 12 repos, all frameworks, many gates, monitors, alerts.
    journey      — 1 repo progressing through full compliance journey
                   (initial scan → remediate → rescan → gate → monitor).

Set COMPLY_DATA_DIR to point the running server at the seeded DB.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Framework definitions (must match comply/frameworks/*.yaml)
# ---------------------------------------------------------------------------
FRAMEWORKS = [
    {"id": "eu-ai-act", "label": "EU AI Act", "articles": 5, "controls": 13},
    {"id": "nist-ai-rmf", "label": "NIST AI RMF", "articles": 5, "controls": 12},
    {"id": "iso-42001", "label": "ISO/IEC 42001", "articles": 4, "controls": 10},
    {"id": "soc2-ai", "label": "SOC 2 (AI)", "articles": 3, "controls": 6},
    {"id": "california-ab-2013", "label": "California AB 2013", "articles": 2, "controls": 3},
    {"id": "california-sb-942", "label": "California SB 942", "articles": 2, "controls": 4},
    {"id": "colorado-sb-24-205", "label": "Colorado SB 24-205", "articles": 3, "controls": 5},
    {"id": "insurance-attestation", "label": "AI Insurance Attestation", "articles": 3, "controls": 5},
    {"id": "owasp-llm-top10", "label": "OWASP LLM Top 10", "articles": 10, "controls": 30},
    {"id": "owasp-agentic-top10", "label": "OWASP Agentic Top 10", "articles": 10, "controls": 30},
]

# Repo templates (realistic GitHub repos)
REPOS = [
    {"name": "acme-ml-platform", "url": "https://github.com/acme-corp/ml-platform", "path": "/repos/acme-ml-platform"},
    {"name": "fraud-detection-api", "url": "https://github.com/acme-corp/fraud-detection-api", "path": "/repos/fraud-detection-api"},
    {"name": "customer-churn-model", "url": "https://github.com/acme-corp/customer-churn-model", "path": "/repos/customer-churn-model"},
    {"name": "llm-chatbot-service", "url": "https://github.com/acme-corp/llm-chatbot-service", "path": "/repos/llm-chatbot-service"},
    {"name": "recommendation-engine", "url": "https://github.com/acme-corp/recommendation-engine", "path": "/repos/recommendation-engine"},
    {"name": "risk-scoring-pipeline", "url": "https://github.com/acme-corp/risk-scoring-pipeline", "path": "/repos/risk-scoring-pipeline"},
    {"name": "document-extraction-ai", "url": "https://github.com/acme-corp/document-extraction-ai", "path": "/repos/document-extraction-ai"},
    {"name": "autonomous-agent-framework", "url": "https://github.com/acme-corp/autonomous-agent-framework", "path": "/repos/autonomous-agent-framework"},
    {"name": "model-registry", "url": "https://github.com/acme-corp/model-registry", "path": "/repos/model-registry"},
    {"name": "data-pipeline-orchestrator", "url": "https://github.com/acme-corp/data-pipeline-orchestrator", "path": "/repos/data-pipeline-orchestrator"},
    {"name": "ai-safety-toolkit", "url": "https://github.com/acme-corp/ai-safety-toolkit", "path": "/repos/ai-safety-toolkit"},
    {"name": "compliance-dashboard", "url": "https://github.com/acme-corp/compliance-dashboard", "path": "/repos/compliance-dashboard"},
]

# Evidence function names per framework article pattern
EVIDENCE_FNS = [
    "evidence_risk_assessment_gateway", "evidence_data_governance",
    "evidence_technical_documentation", "evidence_human_oversight_gateway",
    "evidence_accuracy_metrics", "evidence_transparency_disclosure",
    "evidence_bias_detection", "evidence_logging_traceability",
    "evidence_incident_monitoring", "evidence_model_validation",
    "evidence_data_quality", "evidence_security_controls",
    "evidence_privacy_by_design", "evidence_explainability",
]

# ---------------------------------------------------------------------------
# Deterministic seeding context
# ---------------------------------------------------------------------------
PERSONA_SEEDS = {
    "new_user": 1,
    "single_repo": 10,
    "multi_repo": 42,
    "power_user": 99,
    "journey": 100,
}


class SeedContext:
    """Deterministic context for reproducible test persona seeding.

    Provides seeded random number generation, deterministic unique IDs,
    SHA hex strings, and timestamps.  Same seed produces identical database
    every time.
    """

    # Fixed base time so timestamps are identical across runs
    BASE_TIME = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def uid(self, prefix: str = "") -> str:
        h = format(self.rng.getrandbits(48), '012x')
        return (prefix + "-" if prefix else "") + h

    def sha(self) -> str:
        return format(self.rng.getrandbits(160), '040x')

    def ts(self, days_ago: float = 0) -> str:
        dt = self.BASE_TIME - timedelta(days=days_ago)
        return dt.isoformat()

    # Convenience wrappers around self.rng
    def random(self) -> float:
        return self.rng.random()

    def uniform(self, a: float, b: float) -> float:
        return self.rng.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self.rng.randint(a, b)

    def choice(self, seq):
        return self.rng.choice(seq)

    def sample(self, population, k):
        return self.rng.sample(population, k)


# ---------------------------------------------------------------------------
# Report generator — builds realistic-looking compliance reports
# ---------------------------------------------------------------------------
def _make_report(
    ctx: SeedContext,
    repo: dict,
    framework: dict,
    score: float,
    depth: str = "content",
    days_ago: float = 0,
) -> dict:
    """Generate a synthetic compliance scan report (deterministic)."""
    scan_id = ctx.uid("scan")
    total = framework["controls"]
    met = int(total * score / 100)
    gap = int(total * (1 - score / 100) * 0.6)
    partial = total - met - gap
    if partial < 0:
        partial = 0
        gap = total - met

    articles = []
    ctrl_idx = 0
    for a_idx in range(framework["articles"]):
        ctrls_in_article = max(1, total // framework["articles"])
        if a_idx == framework["articles"] - 1:
            ctrls_in_article = total - ctrl_idx
        controls = []
        for c in range(ctrls_in_article):
            r = ctx.random()
            if r < score / 100:
                status = "met"
            elif r < (score / 100 + 0.2):
                status = "partial"
            else:
                status = "gap"
            controls.append({
                "controlId": f"{a_idx + 1}.{c + 1}",
                "status": status,
                "requirement": f"Control requirement {a_idx + 1}.{c + 1} for {framework['label']}",
                "recommendation": f"Implement {status} control" if status != "met" else "",
                "evidence": [f"Found in {repo['name']}/src/"] if status != "gap" else [],
                "gaps": [f"Missing implementation for {a_idx + 1}.{c + 1}"] if status == "gap" else [],
                "evidence_fn": EVIDENCE_FNS[ctrl_idx % len(EVIDENCE_FNS)],
            })
            ctrl_idx += 1

        a_met = sum(1 for c in controls if c["status"] == "met")
        a_gap = sum(1 for c in controls if c["status"] == "gap")
        a_partial = len(controls) - a_met - a_gap
        articles.append({
            "articleId": f"art_{a_idx + 1}",
            "label": f"Article {a_idx + 1} — {framework['label']}",
            "met": a_met,
            "partial": a_partial,
            "gap": a_gap,
            "controls": controls,
        })

    actual_met = sum(a["met"] for a in articles)
    actual_partial = sum(a["partial"] for a in articles)
    actual_gap = sum(a["gap"] for a in articles)
    actual_score = round((actual_met + actual_partial * 0.5) / total * 100, 1) if total else 0

    return {
        "reportType": "comply_scan",
        "scanId": scan_id,
        "generatedAt": ctx.ts(days_ago),
        "target": repo["url"],
        "repoPath": repo["path"],
        "framework": framework["id"],
        "scanDepth": depth,
        "commitSha": ctx.sha(),
        "summary": {
            "met": actual_met,
            "partial": actual_partial,
            "gap": actual_gap,
            "total": total,
            "score": actual_score,
        },
        "articles": articles,
        "model": {"provider": "test", "model": "test-seed"},
    }


# ---------------------------------------------------------------------------
# DB writer
# ---------------------------------------------------------------------------
def _init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

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
            summary_json  TEXT NOT NULL DEFAULT '{}',
            visitor_id    TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_scans_repo_fw_date
            ON scans (repo_path, framework, created_at DESC);

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
    conn.commit()
    return conn


def _insert_scan(conn: sqlite3.Connection, report: dict):
    s = report["summary"]
    conn.execute(
        """INSERT OR REPLACE INTO scans
           (id, repo_path, repo_url, framework, scan_depth, commit_sha,
            score, status, is_baseline, created_at, completed_at,
            report_json, summary_json, visitor_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            report["scanId"], report["repoPath"], report["target"],
            report["framework"], report["scanDepth"], report["commitSha"],
            s["score"], "complete", 0,
            report["generatedAt"], report["generatedAt"],
            json.dumps(report, default=str),
            json.dumps(s, default=str), "",
        ),
    )


def _insert_gate(ctx: SeedContext, conn: sqlite3.Connection, repo: dict,
                  fw: dict, scan_id: str, score: float, threshold: float,
                  days_ago: float = 0):
    decision = "pass" if score >= threshold else "fail"
    gap_count = int(fw["controls"] * (1 - score / 100) * 0.6)
    conn.execute(
        """INSERT INTO gate_decisions
           (id, repo_path, framework, scan_id, commit_sha,
            decision, exit_code, score, threshold_score,
            regression_detected, fail_on_regression,
            max_critical_gaps, critical_gap_count, reason, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ctx.uid("gate"), repo["path"], fw["id"], scan_id, ctx.sha(),
            decision, 0 if decision == "pass" else 1,
            score, threshold, 0, 0, -1, gap_count,
            f"Score {score:.1f}% {'meets' if decision == 'pass' else 'below'} threshold {threshold:.1f}%",
            ctx.ts(days_ago),
        ),
    )


def _insert_monitor(ctx: SeedContext, conn: sqlite3.Connection, repo: dict,
                     fw: dict, status: str = "running",
                     last_score: float = 0, days_ago: float = 0) -> str:
    mid = ctx.uid()
    fw_norm = fw["id"].replace("-", "_")
    conn.execute(
        """INSERT INTO monitors
           (id, repo_path, framework, scan_depth, interval_secs,
            max_files, webhook_url, status, last_sha, last_scan_id,
            last_score, last_error, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            mid, repo["path"], fw_norm, "content", 300,
            500, "", status, ctx.sha(), "",
            last_score, "", ctx.ts(days_ago), ctx.ts(days_ago * 0.5),
        ),
    )
    return mid


def _insert_monitor_event(ctx: SeedContext, conn: sqlite3.Connection,
                           monitor_id: str, event_type: str, score: float,
                           delta: float = 0, days_ago: float = 0,
                           scan_id: str = ""):
    conn.execute(
        """INSERT INTO monitor_events
           (id, monitor_id, event_type, commit_sha, prev_sha,
            scan_id, score, score_delta, changed_files,
            regression_json, error_msg, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ctx.uid(), monitor_id, event_type, ctx.sha(), ctx.sha(),
            scan_id or ctx.uid("scan"), score, delta,
            json.dumps(["src/main.py", "tests/test_core.py"]),
            json.dumps({"regressionDetected": delta < -5}),
            "", ctx.ts(days_ago),
        ),
    )


def _insert_alert(ctx: SeedContext, conn: sqlite3.Connection,
                   monitor_id: str, alert_type: str,
                   severity: str = "medium", days_ago: float = 0):
    conn.execute(
        """INSERT OR IGNORE INTO monitor_alerts
           (id, monitor_id, event_id, alert_type, severity,
            webhook_url, dispatched, dedup_key, response_code, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            ctx.uid(), monitor_id, "", alert_type, severity,
            "", 0, ctx.uid("dedup"), 0, ctx.ts(days_ago),
        ),
    )


def _insert_program(ctx: SeedContext, conn: sqlite3.Connection, name: str,
                     description: str, repos: list, frameworks: list,
                     days_ago: float = 0) -> str:
    pid = ctx.uid("prog")
    conn.execute(
        """INSERT INTO programs
           (id, name, description, repos_json, frameworks_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            pid, name, description,
            json.dumps(repos), json.dumps(frameworks),
            ctx.ts(days_ago), ctx.ts(days_ago * 0.5),
        ),
    )
    return pid


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------
def seed_new_user(conn: sqlite3.Connection,
                  ctx: Optional[SeedContext] = None):
    """Empty DB -- first-time user with no data at all."""
    pass  # Schema already created, that's it


def seed_single_repo(conn: sqlite3.Connection,
                     ctx: Optional[SeedContext] = None):
    """One repo, 3 frameworks, 2 scans each, 1 gate, 1 monitor.
    Represents a focused user evaluating one project."""
    ctx = ctx or SeedContext(PERSONA_SEEDS["single_repo"])
    repo = REPOS[3]  # llm-chatbot-service
    fws = [FRAMEWORKS[0], FRAMEWORKS[1], FRAMEWORKS[3]]  # EU AI Act, NIST, SOC2

    for fw in fws:
        # First scan (older, lower score)
        r1 = _make_report(ctx, repo, fw, score=ctx.uniform(30, 50), days_ago=14)
        _insert_scan(conn, r1)

        # Second scan (recent, improved)
        r2 = _make_report(ctx, repo, fw, score=ctx.uniform(55, 75), days_ago=2)
        _insert_scan(conn, r2)

    # Gate check on EU AI Act
    _insert_gate(ctx, conn, repo, fws[0], r2["scanId"],
                 r2["summary"]["score"], 70.0, days_ago=1)

    # Monitor on EU AI Act
    mid = _insert_monitor(ctx, conn, repo, fws[0], status="running",
                          last_score=r2["summary"]["score"], days_ago=7)
    _insert_monitor_event(ctx, conn, mid, "scan_complete",
                          r2["summary"]["score"], delta=5.0, days_ago=2)

    conn.commit()
    print(f"  Seeded: 1 repo, 3 frameworks, 6 scans, 1 gate, 1 monitor")


def seed_multi_repo(conn: sqlite3.Connection,
                    ctx: Optional[SeedContext] = None):
    """5 repos with mixed frameworks, gates, monitors. Average team scenario."""
    ctx = ctx or SeedContext(PERSONA_SEEDS["multi_repo"])
    repos = REPOS[:5]

    total_scans = 0
    total_gates = 0
    total_monitors = 0

    for i, repo in enumerate(repos):
        # Each repo gets 1-3 frameworks
        num_fws = ctx.randint(1, 3)
        repo_fws = ctx.sample(FRAMEWORKS[:6], num_fws)

        for fw in repo_fws:
            # 2-4 scans over time showing progression
            num_scans = ctx.randint(2, 4)
            base_score = ctx.uniform(25, 55)
            last_scan = None

            for s in range(num_scans):
                score = min(95, base_score + s * ctx.uniform(5, 15))
                days = 30 - s * (25 / num_scans)
                r = _make_report(ctx, repo, fw, score=score, days_ago=days)
                _insert_scan(conn, r)
                last_scan = r
                total_scans += 1

            # Gate check for repos with score > 50
            if last_scan and last_scan["summary"]["score"] > 50:
                threshold = ctx.choice([60.0, 70.0, 80.0])
                _insert_gate(ctx, conn, repo, fw, last_scan["scanId"],
                             last_scan["summary"]["score"], threshold,
                             days_ago=ctx.uniform(0.5, 5))
                total_gates += 1

            # Monitor for some repo+fw combos
            if ctx.random() > 0.4:
                status = ctx.choice(["running", "running", "stopped"])
                mid = _insert_monitor(
                    ctx, conn, repo, fw, status=status,
                    last_score=last_scan["summary"]["score"] if last_scan else 0,
                    days_ago=ctx.uniform(5, 20))
                total_monitors += 1

                # Monitor events
                num_events = ctx.randint(2, 6)
                for e in range(num_events):
                    delta = ctx.uniform(-8, 12)
                    evt_score = max(0, min(100, base_score + e * 5 + delta))
                    _insert_monitor_event(
                        ctx, conn, mid, "scan_complete", evt_score,
                        delta=delta, days_ago=20 - e * 3,
                    )

                # Some alerts
                if ctx.random() > 0.6:
                    _insert_alert(ctx, conn, mid, "score_drop", "medium",
                                  days_ago=ctx.uniform(1, 10))

    # Programs — group repos into logical programs
    _insert_program(ctx, conn, "Customer AI Suite",
                    "Customer-facing AI services compliance tracking",
                    [repos[0]["url"], repos[1]["url"], repos[2]["url"]],
                    ["eu-ai-act", "nist-ai-rmf"], days_ago=20)
    _insert_program(ctx, conn, "Internal Tools",
                    "Internal tooling compliance",
                    [repos[3]["url"], repos[4]["url"]],
                    ["soc2-ai"], days_ago=15)

    conn.commit()
    print(f"  Seeded: {len(repos)} repos, {total_scans} scans, "
          f"{total_gates} gates, {total_monitors} monitors, 2 programs")


def seed_power_user(conn: sqlite3.Connection,
                    ctx: Optional[SeedContext] = None):
    """12 repos, all frameworks, heavy usage. Enterprise scenario."""
    ctx = ctx or SeedContext(PERSONA_SEEDS["power_user"])

    total_scans = 0
    total_gates = 0
    total_monitors = 0

    for repo in REPOS:
        # Each repo gets 2-5 frameworks
        num_fws = ctx.randint(2, 5)
        repo_fws = ctx.sample(FRAMEWORKS, min(num_fws, len(FRAMEWORKS)))

        for fw in repo_fws:
            # 3-8 scans with progression
            num_scans = ctx.randint(3, 8)
            base_score = ctx.uniform(20, 60)

            for s in range(num_scans):
                improvement = s * ctx.uniform(3, 10)
                noise = ctx.uniform(-5, 5)
                score = min(98, base_score + improvement + noise)
                depth = "semantic" if s >= num_scans - 2 else "content"
                days = 60 - s * (55 / num_scans)
                r = _make_report(ctx, repo, fw, score=score, depth=depth,
                                 days_ago=days)
                _insert_scan(conn, r)
                total_scans += 1

            # Most repos have gate checks
            threshold = ctx.choice([60.0, 70.0, 75.0, 80.0])
            for g in range(ctx.randint(1, 4)):
                gscore = min(98, base_score + num_scans * 5
                             + ctx.uniform(-10, 10))
                _insert_gate(ctx, conn, repo, fw, ctx.uid("scan"), gscore,
                             threshold, days_ago=ctx.uniform(0.1, 15))
                total_gates += 1

            # Most have monitors
            if ctx.random() > 0.2:
                status = ctx.choice(
                    ["running", "running", "running", "stopped"])
                last = base_score + num_scans * 6
                mid = _insert_monitor(
                    ctx, conn, repo, fw, status=status,
                    last_score=min(98, last),
                    days_ago=ctx.uniform(10, 40))
                total_monitors += 1

                for e in range(ctx.randint(3, 10)):
                    delta = ctx.uniform(-10, 15)
                    _insert_monitor_event(
                        ctx, conn, mid, "scan_complete",
                        max(0, min(100, last + delta)), delta=delta,
                        days_ago=40 - e * 4,
                    )

                if ctx.random() > 0.5:
                    sev = ctx.choice(["low", "medium", "high"])
                    _insert_alert(ctx, conn, mid, "score_drop", sev,
                                  days_ago=ctx.uniform(0.5, 15))

    # Programs — enterprise program groupings
    _insert_program(ctx, conn, "Production AI Services",
                    "All customer-facing AI services requiring EU AI Act compliance",
                    [r["url"] for r in REPOS[:4]],
                    ["eu-ai-act", "nist-ai-rmf", "soc2-ai"], days_ago=30)
    _insert_program(ctx, conn, "Data Infrastructure",
                    "Data pipeline and model registry compliance",
                    [r["url"] for r in REPOS[4:8]],
                    ["iso-42001", "soc2-ai"], days_ago=25)
    _insert_program(ctx, conn, "Research & Safety",
                    "AI safety and compliance tooling",
                    [r["url"] for r in REPOS[8:]],
                    ["eu-ai-act", "owasp-llm-top10"], days_ago=20)

    conn.commit()
    print(f"  Seeded: {len(REPOS)} repos, {total_scans} scans, "
          f"{total_gates} gates, {total_monitors} monitors, 3 programs")


def seed_journey(conn: sqlite3.Connection,
                 ctx: Optional[SeedContext] = None):
    """Single repo progressing through the full compliance journey.
    Shows the ideal user path: scan -> understand -> remediate -> rescan -> gate -> monitor."""
    ctx = ctx or SeedContext(PERSONA_SEEDS["journey"])
    repo = REPOS[0]  # acme-ml-platform
    fw = FRAMEWORKS[0]  # EU AI Act

    # Day 30: Initial structure scan (low score)
    r1 = _make_report(ctx, repo, fw, score=28.5, depth="structure", days_ago=30)
    _insert_scan(conn, r1)

    # Day 25: Content scan after reading results (moderate improvement)
    r2 = _make_report(ctx, repo, fw, score=42.3, depth="content", days_ago=25)
    _insert_scan(conn, r2)

    # Day 20: First remediation pass, rescan (noticeable improvement)
    r3 = _make_report(ctx, repo, fw, score=61.7, depth="content", days_ago=20)
    _insert_scan(conn, r3)

    # Day 20: Gate check at 70% threshold -- FAILS
    _insert_gate(ctx, conn, repo, fw, r3["scanId"], 61.7, 70.0, days_ago=20)

    # Day 15: Second remediation, semantic scan (significant improvement)
    r4 = _make_report(ctx, repo, fw, score=78.4, depth="semantic", days_ago=15)
    _insert_scan(conn, r4)

    # Day 15: Gate check -- PASSES
    _insert_gate(ctx, conn, repo, fw, r4["scanId"], 78.4, 70.0, days_ago=15)

    # Day 14: Set up monitor to watch for drift
    mid = _insert_monitor(ctx, conn, repo, fw, status="running",
                          last_score=78.4, days_ago=14)

    # Monitor events showing stability + one dip
    _insert_monitor_event(ctx, conn, mid, "started", 78.4, days_ago=14)
    _insert_monitor_event(ctx, conn, mid, "scan_complete", 78.4,
                          delta=0, days_ago=12)
    _insert_monitor_event(ctx, conn, mid, "scan_complete", 76.1,
                          delta=-2.3, days_ago=9)
    _insert_monitor_event(ctx, conn, mid, "scan_complete", 72.8,
                          delta=-3.3, days_ago=6)

    # Day 6: Score dip triggers alert
    _insert_alert(ctx, conn, mid, "score_drop", "medium", days_ago=6)

    # Day 4: Fix applied, score recovers
    _insert_monitor_event(ctx, conn, mid, "scan_complete", 80.2,
                          delta=7.4, days_ago=4)

    # Day 1: Latest -- stable and healthy
    r5 = _make_report(ctx, repo, fw, score=82.1, depth="content", days_ago=1)
    _insert_scan(conn, r5)
    _insert_monitor_event(ctx, conn, mid, "scan_complete", 82.1, delta=1.9,
                          days_ago=1, scan_id=r5["scanId"])

    # Also scan against NIST for cross-framework view
    fw2 = FRAMEWORKS[1]  # NIST
    r6 = _make_report(ctx, repo, fw2, score=55.0, depth="content", days_ago=10)
    _insert_scan(conn, r6)
    r7 = _make_report(ctx, repo, fw2, score=68.3, depth="content", days_ago=3)
    _insert_scan(conn, r7)

    # Program grouping
    _insert_program(ctx, conn, "ML Platform Compliance",
                    "Track compliance for the core ML platform",
                    [repo["url"]], [fw["id"], fw2["id"]], days_ago=25)

    conn.commit()
    print(f"  Seeded: 1 repo, 2 frameworks, 7 scans, 2 gates, "
          f"1 monitor (6 events, 1 alert), 1 program")
    print(f"  Journey: structure(28%) -> content(42%) -> remediate(62%) "
          f"-> gate fail -> semantic(78%) -> gate pass -> monitor -> stable(82%)")


PERSONAS = {
    "new_user": seed_new_user,
    "single_repo": seed_single_repo,
    "multi_repo": seed_multi_repo,
    "power_user": seed_power_user,
    "journey": seed_journey,
}


def main():
    parser = argparse.ArgumentParser(
        description="Seed test data for Comply UI testing")
    parser.add_argument(
        "persona", choices=list(PERSONAS.keys()) + ["list", "clean"],
        help="Persona to seed (or 'list'/'clean')")
    parser.add_argument("--dir", default=None,
                        help="Data directory (default: ~/.comply)")
    args = parser.parse_args()

    if args.persona == "list":
        print("\nAvailable personas:")
        for name, fn in PERSONAS.items():
            doc = (fn.__doc__ or "").strip().split("\n")[0]
            print(f"  {name:15s} {doc}")
        return

    data_dir = args.dir or os.path.expanduser("~/.comply")
    db_path = os.path.join(data_dir, "scans.db")

    # Always start fresh for the persona
    if os.path.exists(db_path):
        os.remove(db_path)
        # Also remove WAL/SHM files
        for ext in ["-wal", "-shm"]:
            p = db_path + ext
            if os.path.exists(p):
                os.remove(p)

    if args.persona == "clean":
        print(f"Cleaned: {db_path}")
        return

    print(f"Seeding persona '{args.persona}' into {db_path}")
    conn = _init_db(db_path)
    PERSONAS[args.persona](conn)
    conn.close()
    print(f"Done. Restart the server to pick up changes.")
    print(f"  Tip: COMPLY_DATA_DIR={data_dir} bespoketracker-comply serve "
          f"--port 8001")


if __name__ == "__main__":
    main()
