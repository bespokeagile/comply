"""GitLab CI/CD adapter — ingests pipelines, test reports, and deployments.

Fetches data via the GitLab REST API and normalises events into
``NormalizedTrafficRecord`` instances for Layer 2 (Process) evidence.

Configure via ``~/.comply/config.yaml``:

.. code-block:: yaml

    adapters:
      gitlab_ci:
        project_id: "12345"
        token: glpat-...
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comply.adapters.base import AuditLogAdapter, NormalizedTrafficRecord

log = logging.getLogger(__name__)


class GitLabCIAdapter(AuditLogAdapter):
    """Adapter for GitLab CI/CD data."""

    def __init__(self):
        self._project_id: str = ""
        self._token: str = ""
        self._api_base: str = "https://gitlab.com/api/v4"
        self._last_fetch: str = ""

    def configure(self, config: Dict[str, Any]) -> None:
        self._project_id = str(config.get("project_id", ""))
        self._token = config.get("token", "")
        api_url = config.get("api_base", config.get("url", "https://gitlab.com"))
        self._api_base = api_url.rstrip("/").rstrip("/api/v4") + "/api/v4"

    def test_connection(self) -> bool:
        try:
            import httpx
            r = httpx.get(
                f"{self._api_base}/projects/{self._project_id}/pipelines",
                headers=self._headers(),
                params={"per_page": 1},
                timeout=10,
            )
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
            import httpx  # noqa: F811
        except ImportError:
            log.warning("httpx not installed; GitLab CI adapter unavailable")
            return []

        records: List[NormalizedTrafficRecord] = []
        try:
            records.extend(self._fetch_pipelines(httpx, since, until, limit))
            records.extend(self._fetch_deployments(httpx, since, until, limit))
        except Exception as exc:
            log.warning("GitLab CI fetch failed: %s", exc)

        self._last_fetch = datetime.now(timezone.utc).isoformat()
        return records[:limit]

    def get_adapter_status(self) -> Dict[str, Any]:
        return {
            "name": "gitlab_ci",
            "type": "cicd",
            "connected": self.test_connection() if self._project_id else False,
            "last_fetch": self._last_fetch,
            "project_id": self._project_id,
        }

    # ── Internal methods ────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self._token:
            h["PRIVATE-TOKEN"] = self._token
        return h

    def _fetch_pipelines(
        self, httpx_mod: Any, since: Optional[str], until: Optional[str], limit: int,
    ) -> List[NormalizedTrafficRecord]:
        records: List[NormalizedTrafficRecord] = []
        params: Dict[str, Any] = {"per_page": min(limit, 100), "order_by": "updated_at", "sort": "desc"}
        if since:
            params["updated_after"] = since
        if until:
            params["updated_before"] = until

        r = httpx_mod.get(
            f"{self._api_base}/projects/{self._project_id}/pipelines",
            headers=self._headers(),
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        pipelines = r.json()

        for pipeline in pipelines:
            ts = pipeline.get("created_at", "") or pipeline.get("updated_at", "")
            status = pipeline.get("status", "")
            action = "error" if status in ("failed", "canceled") else "call"

            records.append(NormalizedTrafficRecord(
                record_id=f"gl-pipeline-{pipeline.get('id', uuid.uuid4().hex[:8])}",
                timestamp=ts,
                source_adapter="gitlab_ci",
                tool_name="ci_pipeline",
                caller_identity=pipeline.get("user", {}).get("username", "") if isinstance(pipeline.get("user"), dict) else "",
                action=action,
                status=status,
                metadata={
                    "cicd_type": "workflow_run",
                    "ref": pipeline.get("ref", ""),
                    "sha": pipeline.get("sha", ""),
                    "source": pipeline.get("source", ""),
                    "pipeline_id": pipeline.get("id", 0),
                },
            ))

            # Fetch test report for this pipeline (GitLab built-in)
            test_records = self._fetch_test_report(
                httpx_mod, pipeline.get("id", 0), ts,
                pipeline.get("ref", ""), pipeline.get("sha", ""),
            )
            records.extend(test_records)

        return records

    def _fetch_test_report(
        self, httpx_mod: Any, pipeline_id: int,
        timestamp: str, ref: str, sha: str,
    ) -> List[NormalizedTrafficRecord]:
        """Fetch test report from GitLab's built-in test report API."""
        records: List[NormalizedTrafficRecord] = []
        try:
            r = httpx_mod.get(
                f"{self._api_base}/projects/{self._project_id}/pipelines/{pipeline_id}/test_report",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return records

            report = r.json()
            total = report.get("total_count", 0)
            if total == 0:
                return records

            failures = report.get("failed_count", 0)
            errors = report.get("error_count", 0)
            skipped = report.get("skipped_count", 0)
            success = report.get("success_count", 0)
            pass_rate = round(success / max(total, 1) * 100, 1)
            action = "error" if (failures + errors) > 0 else "call"

            records.append(NormalizedTrafficRecord(
                record_id=f"gl-test-{pipeline_id}",
                timestamp=timestamp,
                source_adapter="gitlab_ci",
                tool_name="test_suite",
                action=action,
                status="pass" if action == "call" else "fail",
                metadata={
                    "cicd_type": "test_result",
                    "tests": total,
                    "failures": failures,
                    "errors": errors,
                    "skipped": skipped,
                    "success": success,
                    "pass_rate": pass_rate,
                    "ref": ref,
                    "sha": sha,
                    "total_time": report.get("total_time", 0),
                },
            ))

            # Also add per-suite records if available
            for suite in report.get("test_suites", []):
                suite_total = suite.get("total_count", 0)
                if suite_total == 0:
                    continue
                suite_failures = suite.get("failed_count", 0)
                suite_errors = suite.get("error_count", 0)
                suite_skipped = suite.get("skipped_count", 0)
                suite_success = suite.get("success_count", 0)
                suite_pass_rate = round(suite_success / max(suite_total, 1) * 100, 1)
                suite_action = "error" if (suite_failures + suite_errors) > 0 else "call"

                records.append(NormalizedTrafficRecord(
                    record_id=f"gl-test-{pipeline_id}-{uuid.uuid4().hex[:6]}",
                    timestamp=timestamp,
                    source_adapter="gitlab_ci",
                    tool_name="test_suite",
                    action=suite_action,
                    status="pass" if suite_action == "call" else "fail",
                    metadata={
                        "cicd_type": "test_result",
                        "suite_name": suite.get("name", ""),
                        "tests": suite_total,
                        "failures": suite_failures,
                        "errors": suite_errors,
                        "skipped": suite_skipped,
                        "pass_rate": suite_pass_rate,
                    },
                ))

        except Exception as exc:
            log.debug("GitLab test report fetch failed for pipeline %s: %s", pipeline_id, exc)
        return records

    def _fetch_deployments(
        self, httpx_mod: Any, since: Optional[str], until: Optional[str], limit: int,
    ) -> List[NormalizedTrafficRecord]:
        """Fetch deployment events from GitLab."""
        records: List[NormalizedTrafficRecord] = []
        try:
            params: Dict[str, Any] = {"per_page": min(limit, 100), "order_by": "created_at", "sort": "desc"}
            if since:
                params["updated_after"] = since
            if until:
                params["updated_before"] = until

            r = httpx_mod.get(
                f"{self._api_base}/projects/{self._project_id}/deployments",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            if r.status_code != 200:
                return records

            deployments = r.json()
            for dep in deployments:
                ts = dep.get("created_at", "")
                status = dep.get("status", "")
                action = "error" if status in ("failed", "canceled") else "call"

                user = dep.get("user", {})
                username = user.get("username", "") if isinstance(user, dict) else ""

                records.append(NormalizedTrafficRecord(
                    record_id=f"gl-deploy-{dep.get('id', uuid.uuid4().hex[:8])}",
                    timestamp=ts,
                    source_adapter="gitlab_ci",
                    tool_name="deploy",
                    caller_identity=username,
                    action=action,
                    status=status,
                    metadata={
                        "cicd_type": "deployment",
                        "environment": dep.get("environment", ""),
                        "ref": dep.get("ref", ""),
                        "sha": dep.get("sha", ""),
                        "iid": dep.get("iid", 0),
                    },
                ))
        except Exception as exc:
            log.debug("GitLab deployments fetch failed: %s", exc)
        return records
