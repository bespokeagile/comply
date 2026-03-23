"""GitHub Actions CI/CD adapter — ingests workflow runs, test results, and deployments.

Fetches data via the GitHub REST API and normalises events into
``NormalizedTrafficRecord`` instances for Layer 2 (Process) evidence.

Configure via ``~/.comply/config.yaml``:

.. code-block:: yaml

    adapters:
      github_actions:
        owner: myorg
        repo: myrepo
        token: ghp_...
"""
from __future__ import annotations

import io
import logging
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comply.adapters.base import AuditLogAdapter, NormalizedTrafficRecord

log = logging.getLogger(__name__)


class GitHubActionsAdapter(AuditLogAdapter):
    """Adapter for GitHub Actions CI/CD data."""

    def __init__(self):
        self._owner: str = ""
        self._repo: str = ""
        self._token: str = ""
        self._api_base: str = "https://api.github.com"
        self._last_fetch: str = ""

    def configure(self, config: Dict[str, Any]) -> None:
        self._owner = config.get("owner", "")
        self._repo = config.get("repo", "")
        self._token = config.get("token", "")
        self._api_base = config.get("api_base", "https://api.github.com").rstrip("/")

    def test_connection(self) -> bool:
        try:
            import httpx
            r = httpx.get(
                f"{self._api_base}/repos/{self._owner}/{self._repo}/actions/runs",
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
            log.warning("httpx not installed; GitHub Actions adapter unavailable")
            return []

        records: List[NormalizedTrafficRecord] = []
        try:
            records.extend(self._fetch_workflow_runs(httpx, since, until, limit))
            records.extend(self._fetch_deployments(httpx, since, until, limit))
        except Exception as exc:
            log.warning("GitHub Actions fetch failed: %s", exc)

        self._last_fetch = datetime.now(timezone.utc).isoformat()
        return records[:limit]

    def get_adapter_status(self) -> Dict[str, Any]:
        return {
            "name": "github_actions",
            "type": "cicd",
            "connected": self.test_connection() if self._owner and self._repo else False,
            "last_fetch": self._last_fetch,
            "owner": self._owner,
            "repo": self._repo,
        }

    # ── Internal methods ────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _fetch_workflow_runs(
        self, httpx_mod: Any, since: Optional[str], until: Optional[str], limit: int,
    ) -> List[NormalizedTrafficRecord]:
        records: List[NormalizedTrafficRecord] = []
        params: Dict[str, Any] = {"per_page": min(limit, 100)}
        if since:
            params["created"] = f">={since[:10]}"

        r = httpx_mod.get(
            f"{self._api_base}/repos/{self._owner}/{self._repo}/actions/runs",
            headers=self._headers(),
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        runs = r.json().get("workflow_runs", [])

        for run in runs:
            ts = run.get("created_at", "")
            if since and ts and ts < since:
                continue
            if until and ts and ts > until:
                continue

            conclusion = run.get("conclusion", "")
            action = "error" if conclusion in ("failure", "cancelled", "timed_out") else "call"

            records.append(NormalizedTrafficRecord(
                record_id=f"gha-run-{run.get('id', uuid.uuid4().hex[:8])}",
                timestamp=ts,
                source_adapter="github_actions",
                tool_name="ci_pipeline",
                caller_identity=run.get("actor", {}).get("login", ""),
                action=action,
                status=conclusion or "unknown",
                metadata={
                    "cicd_type": "workflow_run",
                    "workflow_name": run.get("name", ""),
                    "head_branch": run.get("head_branch", ""),
                    "head_sha": run.get("head_sha", ""),
                    "event": run.get("event", ""),
                    "run_number": run.get("run_number", 0),
                    "conclusion": conclusion,
                },
            ))

            # Try to fetch test artifacts for this run
            if conclusion == "success" or conclusion == "failure":
                test_records = self._fetch_test_artifacts(
                    httpx_mod, run.get("id", 0),
                    ts, run.get("head_branch", ""), run.get("head_sha", ""),
                )
                records.extend(test_records)

        return records

    def _fetch_test_artifacts(
        self, httpx_mod: Any, run_id: int,
        timestamp: str, branch: str, sha: str,
    ) -> List[NormalizedTrafficRecord]:
        """Fetch JUnit XML artifacts from a workflow run."""
        records: List[NormalizedTrafficRecord] = []
        try:
            r = httpx_mod.get(
                f"{self._api_base}/repos/{self._owner}/{self._repo}/actions/runs/{run_id}/artifacts",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return records

            artifacts = r.json().get("artifacts", [])
            for artifact in artifacts:
                name_lower = artifact.get("name", "").lower()
                if not any(k in name_lower for k in ("test", "junit", "surefire", "report")):
                    continue

                dl_url = artifact.get("archive_download_url", "")
                if not dl_url:
                    continue

                try:
                    dl = httpx_mod.get(dl_url, headers=self._headers(), timeout=30, follow_redirects=True)
                    if dl.status_code != 200:
                        continue
                    parsed = self._parse_junit_zip(dl.content)
                    for suite in parsed:
                        tests = suite.get("tests", 0)
                        failures = suite.get("failures", 0)
                        errors = suite.get("errors", 0)
                        skipped = suite.get("skipped", 0)
                        passed = tests - failures - errors - skipped
                        pass_rate = round(passed / max(tests, 1) * 100, 1)
                        action = "error" if (failures + errors) > 0 else "call"

                        records.append(NormalizedTrafficRecord(
                            record_id=f"gha-test-{run_id}-{uuid.uuid4().hex[:6]}",
                            timestamp=timestamp,
                            source_adapter="github_actions",
                            tool_name="test_suite",
                            action=action,
                            status="pass" if action == "call" else "fail",
                            metadata={
                                "cicd_type": "test_result",
                                "suite_name": suite.get("name", ""),
                                "tests": tests,
                                "failures": failures,
                                "errors": errors,
                                "skipped": skipped,
                                "pass_rate": pass_rate,
                                "head_branch": branch,
                                "head_sha": sha,
                            },
                        ))
                except Exception as exc:
                    log.debug("Failed to parse test artifact: %s", exc)

        except Exception as exc:
            log.debug("Failed to fetch artifacts for run %s: %s", run_id, exc)
        return records

    def _parse_junit_zip(self, zip_bytes: bytes) -> List[Dict[str, Any]]:
        """Parse JUnit XML files from a ZIP archive."""
        suites: List[Dict[str, Any]] = []
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        xml_bytes = zf.read(name)
                        suites.extend(self._parse_junit_xml(xml_bytes))
        except Exception as exc:
            log.debug("ZIP parse error: %s", exc)
        return suites

    def _parse_junit_xml(self, xml_bytes: bytes) -> List[Dict[str, Any]]:
        """Parse a JUnit XML file, handling both <testsuite> and <testsuites> roots."""
        suites: List[Dict[str, Any]] = []
        try:
            root = ET.fromstring(xml_bytes)
            suite_elements = []
            if root.tag == "testsuites":
                suite_elements = root.findall("testsuite")
            elif root.tag == "testsuite":
                suite_elements = [root]

            for elem in suite_elements:
                suites.append({
                    "name": elem.get("name", ""),
                    "tests": int(elem.get("tests", 0)),
                    "failures": int(elem.get("failures", 0)),
                    "errors": int(elem.get("errors", 0)),
                    "skipped": int(elem.get("skipped", 0)),
                    "time": float(elem.get("time", 0)),
                })
        except Exception as exc:
            log.debug("JUnit XML parse error: %s", exc)
        return suites

    def _fetch_deployments(
        self, httpx_mod: Any, since: Optional[str], until: Optional[str], limit: int,
    ) -> List[NormalizedTrafficRecord]:
        """Fetch deployment events from GitHub."""
        records: List[NormalizedTrafficRecord] = []
        try:
            r = httpx_mod.get(
                f"{self._api_base}/repos/{self._owner}/{self._repo}/deployments",
                headers=self._headers(),
                params={"per_page": min(limit, 100)},
                timeout=10,
            )
            if r.status_code != 200:
                return records

            deployments = r.json()
            for dep in deployments:
                ts = dep.get("created_at", "")
                if since and ts and ts < since:
                    continue
                if until and ts and ts > until:
                    continue

                # Fetch deployment status
                dep_status = "unknown"
                try:
                    sr = httpx_mod.get(
                        dep.get("statuses_url", ""),
                        headers=self._headers(),
                        timeout=10,
                    )
                    if sr.status_code == 200:
                        statuses = sr.json()
                        if statuses:
                            dep_status = statuses[0].get("state", "unknown")
                except (OSError, ValueError, KeyError) as e:
                    log.debug("Failed to fetch deployment status for %s: %s", dep.get("id"), e)

                action = "error" if dep_status in ("failure", "error") else "call"
                records.append(NormalizedTrafficRecord(
                    record_id=f"gha-deploy-{dep.get('id', uuid.uuid4().hex[:8])}",
                    timestamp=ts,
                    source_adapter="github_actions",
                    tool_name="deploy",
                    caller_identity=dep.get("creator", {}).get("login", ""),
                    action=action,
                    status=dep_status,
                    metadata={
                        "cicd_type": "deployment",
                        "environment": dep.get("environment", ""),
                        "ref": dep.get("ref", ""),
                        "sha": dep.get("sha", ""),
                        "description": dep.get("description", ""),
                    },
                ))
        except Exception as exc:
            log.debug("GitHub deployments fetch failed: %s", exc)
        return records
