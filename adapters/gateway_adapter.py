"""Reference adapter for BespokeTracker Gateway.

Two modes:
  - **REST** — hits Gateway's ``/v1/`` endpoints via httpx (for remote gateways)
  - **SQLite** — reads ``gateway.db`` directly (for co-located deployments)

Configure via ``~/.comply/config.yaml``:

.. code-block:: yaml

    adapters:
      gateway:
        mode: sqlite          # or "rest"
        db_path: ./gateway.db # for sqlite mode
        base_url: http://localhost:9090  # for rest mode
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comply.adapters.base import AuditLogAdapter, NormalizedTrafficRecord

log = logging.getLogger(__name__)


class GatewayAdapter(AuditLogAdapter):
    """Adapter for BespokeTracker MCP Compliance Gateway."""

    def __init__(self):
        self._mode: str = "sqlite"
        self._db_path: str = ""
        self._base_url: str = ""
        self._last_fetch: str = ""

    def configure(self, config: Dict[str, Any]) -> None:
        self._mode = config.get("mode", "sqlite")
        self._db_path = config.get("db_path", "")
        self._base_url = config.get("base_url", "http://localhost:9090")

    def test_connection(self) -> bool:
        if self._mode == "sqlite":
            return self._test_sqlite()
        return self._test_rest()

    def fetch_records(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 1000,
    ) -> List[NormalizedTrafficRecord]:
        if self._mode == "sqlite":
            records = self._fetch_sqlite(since, until, limit)
        else:
            records = self._fetch_rest(since, until, limit)
        self._last_fetch = datetime.now(timezone.utc).isoformat()
        return records

    def get_adapter_status(self) -> Dict[str, Any]:
        return {
            "name": "gateway",
            "mode": self._mode,
            "connected": self.test_connection(),
            "last_fetch": self._last_fetch,
            "db_path": self._db_path if self._mode == "sqlite" else "",
            "base_url": self._base_url if self._mode == "rest" else "",
        }

    # ── SQLite mode ──────────────────────────────────────────────────

    def _test_sqlite(self) -> bool:
        import os
        if not self._db_path or not os.path.isfile(self._db_path):
            return False
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("SELECT 1 FROM calls LIMIT 1")
            conn.close()
            return True
        except Exception:
            return False

    def _fetch_sqlite(
        self, since: Optional[str], until: Optional[str], limit: int
    ) -> List[NormalizedTrafficRecord]:
        import os
        if not self._db_path or not os.path.isfile(self._db_path):
            return []

        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        records = []

        # Fetch calls
        clauses, params = [], []
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        if until:
            clauses.append("created_at <= ?")
            params.append(until)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)

        try:
            rows = conn.execute(
                f"SELECT * FROM calls {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            for row in rows:
                d = dict(row)
                records.append(NormalizedTrafficRecord(
                    record_id=d.get("id", uuid.uuid4().hex[:12]),
                    timestamp=d.get("created_at", ""),
                    source_adapter="gateway",
                    tool_name=d.get("tool_name", ""),
                    caller_identity=d.get("caller_role", ""),
                    action="call",
                    duration_ms=d.get("duration_ms", 0),
                    status=d.get("status", "ok"),
                    policy_matched="",
                    cost_usd=d.get("cost_usd", 0) or 0,
                    metadata={"server": d.get("server", "")},
                ))
        except Exception as exc:
            log.warning("Gateway SQLite calls query failed: %s", exc)

        # Fetch denials
        try:
            denial_rows = conn.execute(
                f"SELECT * FROM denials {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            for row in denial_rows:
                d = dict(row)
                records.append(NormalizedTrafficRecord(
                    record_id=d.get("id", uuid.uuid4().hex[:12]),
                    timestamp=d.get("created_at", ""),
                    source_adapter="gateway",
                    tool_name=d.get("tool_name", ""),
                    caller_identity=d.get("caller_role", ""),
                    action="deny",
                    duration_ms=0,
                    status="denied",
                    policy_matched=d.get("policy_id", ""),
                    cost_usd=0,
                    metadata={"reason": d.get("reason", "")},
                ))
        except Exception as exc:
            log.warning("Gateway SQLite denials query failed: %s", exc)

        conn.close()
        return records

    # ── REST mode ────────────────────────────────────────────────────

    def _test_rest(self) -> bool:
        try:
            import httpx
            r = httpx.get(f"{self._base_url}/v1/status", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def _fetch_rest(
        self, since: Optional[str], until: Optional[str], limit: int
    ) -> List[NormalizedTrafficRecord]:
        try:
            import httpx
        except ImportError:
            log.warning("httpx not installed; REST mode unavailable")
            return []

        records = []
        params: Dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        try:
            r = httpx.get(f"{self._base_url}/v1/traffic", params=params, timeout=10)
            r.raise_for_status()
            for item in r.json():
                records.append(NormalizedTrafficRecord(
                    record_id=item.get("id", uuid.uuid4().hex[:12]),
                    timestamp=item.get("created_at", ""),
                    source_adapter="gateway",
                    tool_name=item.get("tool_name", ""),
                    caller_identity=item.get("caller_role", ""),
                    action="call",
                    duration_ms=item.get("duration_ms", 0),
                    status=item.get("status", "ok"),
                    policy_matched="",
                    cost_usd=item.get("cost_usd", 0) or 0,
                    metadata={"server": item.get("server", "")},
                ))
        except Exception as exc:
            log.warning("Gateway REST traffic fetch failed: %s", exc)

        try:
            r = httpx.get(f"{self._base_url}/v1/denials", params=params, timeout=10)
            r.raise_for_status()
            for item in r.json():
                records.append(NormalizedTrafficRecord(
                    record_id=item.get("id", uuid.uuid4().hex[:12]),
                    timestamp=item.get("created_at", ""),
                    source_adapter="gateway",
                    tool_name=item.get("tool_name", ""),
                    caller_identity=item.get("caller_role", ""),
                    action="deny",
                    duration_ms=0,
                    status="denied",
                    policy_matched=item.get("policy_id", ""),
                    cost_usd=0,
                    metadata={"reason": item.get("reason", "")},
                ))
        except Exception as exc:
            log.warning("Gateway REST denials fetch failed: %s", exc)

        return records
