"""Kong Admin API adapter (community — needs real Kong for production testing).

Parses ``/audit/objects`` and ``/audit/requests`` endpoints from the Kong
Admin API.  Enable the audit log plugin in Kong before using this adapter.

Configure via ``~/.comply/config.yaml``:

.. code-block:: yaml

    adapters:
      kong:
        admin_url: http://localhost:8001
        api_key: ""           # optional admin API key
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comply.adapters.base import AuditLogAdapter, NormalizedTrafficRecord

log = logging.getLogger(__name__)


class KongAdapter(AuditLogAdapter):
    """Adapter for Kong Gateway Admin API audit logs."""

    def __init__(self):
        self._admin_url: str = "http://localhost:8001"
        self._api_key: str = ""
        self._last_fetch: str = ""

    def configure(self, config: Dict[str, Any]) -> None:
        self._admin_url = config.get("admin_url", "http://localhost:8001").rstrip("/")
        self._api_key = config.get("api_key", "")

    def test_connection(self) -> bool:
        try:
            import httpx
            headers = {}
            if self._api_key:
                headers["Kong-Admin-Token"] = self._api_key
            r = httpx.get(f"{self._admin_url}/", headers=headers, timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def fetch_records(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 1000,
    ) -> List[NormalizedTrafficRecord]:
        try:
            import httpx
        except ImportError:
            log.warning("httpx not installed; Kong adapter unavailable")
            return []

        headers = {}
        if self._api_key:
            headers["Kong-Admin-Token"] = self._api_key

        records = []
        try:
            r = httpx.get(
                f"{self._admin_url}/audit/requests",
                headers=headers,
                params={"size": min(limit, 500)},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            for item in data:
                ts = item.get("request_timestamp")
                if ts and isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                elif not ts:
                    ts = ""

                # Apply time filters
                if since and ts and ts < since:
                    continue
                if until and ts and ts > until:
                    continue

                status_code = item.get("status", 200)
                action = "deny" if status_code == 403 else "error" if status_code >= 400 else "call"

                records.append(NormalizedTrafficRecord(
                    record_id=item.get("request_id", uuid.uuid4().hex[:12]),
                    timestamp=ts,
                    source_adapter="kong",
                    tool_name=item.get("path", "") or item.get("method", ""),
                    caller_identity=item.get("client_ip", ""),
                    action=action,
                    duration_ms=item.get("latency", 0),
                    status=str(status_code),
                    policy_matched="",
                    cost_usd=0,
                    metadata={
                        "method": item.get("method", ""),
                        "path": item.get("path", ""),
                        "workspace": item.get("workspace", ""),
                    },
                ))
        except Exception as exc:
            log.warning("Kong audit/requests fetch failed: %s", exc)

        self._last_fetch = datetime.now(timezone.utc).isoformat()
        return records[:limit]

    def get_adapter_status(self) -> Dict[str, Any]:
        return {
            "name": "kong",
            "connected": self.test_connection(),
            "last_fetch": self._last_fetch,
            "admin_url": self._admin_url,
        }
