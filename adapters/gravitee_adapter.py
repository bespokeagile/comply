"""Gravitee Analytics API v3 adapter (community — needs real Gravitee for production testing).

Parses ``/analytics/logs`` endpoint from the Gravitee Management API.

Configure via ``~/.comply/config.yaml``:

.. code-block:: yaml

    adapters:
      gravitee:
        management_url: http://localhost:8083/management
        environment: DEFAULT
        api_key: ""
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comply.adapters.base import AuditLogAdapter, NormalizedTrafficRecord

log = logging.getLogger(__name__)


class GraviteeAdapter(AuditLogAdapter):
    """Adapter for Gravitee API Management Analytics logs."""

    def __init__(self):
        self._mgmt_url: str = "http://localhost:8083/management"
        self._environment: str = "DEFAULT"
        self._api_key: str = ""
        self._last_fetch: str = ""

    def configure(self, config: Dict[str, Any]) -> None:
        self._mgmt_url = config.get("management_url", "http://localhost:8083/management").rstrip("/")
        self._environment = config.get("environment", "DEFAULT")
        self._api_key = config.get("api_key", "")

    def test_connection(self) -> bool:
        try:
            import httpx
            headers = self._headers()
            r = httpx.get(
                f"{self._mgmt_url}/organizations/DEFAULT/environments/{self._environment}/apis",
                headers=headers,
                timeout=5,
            )
            return r.status_code in (200, 401)  # 401 = reachable but auth needed
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
            log.warning("httpx not installed; Gravitee adapter unavailable")
            return []

        headers = self._headers()
        params: Dict[str, Any] = {"page": 1, "size": min(limit, 100)}

        # Convert ISO timestamps to epoch ms for Gravitee
        if since:
            try:
                dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                params["from"] = int(dt.timestamp() * 1000)
            except ValueError as e:
                log.debug("Invalid 'since' timestamp %r: %s", since, e)
        if until:
            try:
                dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
                params["to"] = int(dt.timestamp() * 1000)
            except ValueError as e:
                log.debug("Invalid 'until' timestamp %r: %s", until, e)

        records = []
        try:
            url = (
                f"{self._mgmt_url}/organizations/DEFAULT/"
                f"environments/{self._environment}/platform/logs"
            )
            r = httpx.get(url, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            logs = data.get("logs", data.get("content", []))

            for item in logs:
                ts_ms = item.get("timestamp", 0)
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat() if ts_ms else ""

                status_code = item.get("status", 200)
                action = "deny" if status_code == 403 else "error" if status_code >= 400 else "call"

                records.append(NormalizedTrafficRecord(
                    record_id=item.get("id", uuid.uuid4().hex[:12]),
                    timestamp=ts,
                    source_adapter="gravitee",
                    tool_name=item.get("path", "") or item.get("api", ""),
                    caller_identity=item.get("user", "") or item.get("application", ""),
                    action=action,
                    duration_ms=item.get("responseTime", 0),
                    status=str(status_code),
                    policy_matched=item.get("plan", ""),
                    cost_usd=0,
                    metadata={
                        "api": item.get("api", ""),
                        "plan": item.get("plan", ""),
                        "method": item.get("method", ""),
                    },
                ))
        except Exception as exc:
            log.warning("Gravitee analytics fetch failed: %s", exc)

        self._last_fetch = datetime.now(timezone.utc).isoformat()
        return records[:limit]

    def get_adapter_status(self) -> Dict[str, Any]:
        return {
            "name": "gravitee",
            "connected": self.test_connection(),
            "last_fetch": self._last_fetch,
            "management_url": self._mgmt_url,
        }

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
