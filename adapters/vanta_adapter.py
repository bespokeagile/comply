"""Vanta evidence import adapter.

Imports Vanta compliance report data into Comply's evidence model to
demonstrate complementary positioning: infrastructure controls (Vanta) +
product development controls (Comply) = comprehensive coverage.

Vanta exports compliance data as JSON. This adapter reads that export and
maps Vanta's test results to NormalizedTrafficRecord entries that feed
into Comply's Layer 3 evidence.

Configuration (in ~/.comply/config.yaml):

    adapters:
      vanta:
        report_path: ./vanta-export.json    # path to Vanta JSON export
        # OR
        api_token: vat_...                  # Vanta API token
        api_base: https://api.vanta.com     # default

The adapter also provides a `merge_vanta_report()` function that produces
a combined compliance view showing which controls are covered by Vanta
(infrastructure), Comply (product development), or both.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comply.adapters.base import AuditLogAdapter, NormalizedTrafficRecord

log = logging.getLogger(__name__)

# Vanta test categories → Comply evidence function mapping
_VANTA_CATEGORY_MAP = {
    "access_control": "evidence_logical_access",
    "encryption": "evidence_data_handling",
    "logging": "evidence_audit_logging",
    "monitoring": "evidence_continuous_monitoring",
    "change_management": "evidence_change_management",
    "incident_response": "evidence_incident_response",
    "vulnerability_management": "evidence_continuous_monitoring",
    "endpoint_security": "evidence_logical_access",
    "network_security": "evidence_logical_access",
    "data_protection": "evidence_data_handling",
    "backup": "evidence_availability_controls",
    "business_continuity": "evidence_availability_controls",
    "risk_management": "evidence_risk_assessment_gateway",
    "vendor_management": "evidence_governance_policy",
    "hr_security": "evidence_governance_policy",
    "physical_security": "evidence_logical_access",
    "policy": "evidence_governance_policy",
    "awareness_training": "evidence_governance_policy",
}


class VantaAdapter(AuditLogAdapter):
    """Adapter for importing Vanta compliance evidence."""

    def __init__(self):
        self._report_path = ""
        self._api_token = ""
        self._api_base = "https://api.vanta.com"
        self._last_fetch = ""
        self._connected = False

    def configure(self, config: Dict[str, Any]) -> None:
        self._report_path = config.get("report_path", "")
        self._api_token = config.get("api_token", "")
        self._api_base = config.get("api_base", "https://api.vanta.com")

    def test_connection(self) -> bool:
        if self._report_path:
            ok = os.path.isfile(self._report_path)
            self._connected = ok
            return ok

        if self._api_token:
            try:
                import httpx
                resp = httpx.get(
                    f"{self._api_base}/v1/ping",
                    headers={"Authorization": f"Bearer {self._api_token}"},
                    timeout=10,
                )
                self._connected = resp.status_code == 200
                return self._connected
            except Exception as exc:
                log.warning("Vanta API connection failed: %s", exc)
                return False

        return False

    def fetch_records(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 1000,
    ) -> List[NormalizedTrafficRecord]:
        """Fetch records from Vanta export or API.

        Each Vanta test result is mapped to a NormalizedTrafficRecord with:
        - tool_name: the Vanta test/check name
        - action: "call" for passed, "deny" for failed
        - status: "pass" or "fail"
        - metadata: includes category, framework, evidence details
        """
        data = self._load_data()
        if not data:
            return []

        records = []
        tests = data.get("tests", data.get("checks", data.get("results", [])))

        for test in tests[:limit]:
            record = self._map_test_to_record(test)
            if record:
                records.append(record)

        self._last_fetch = datetime.now(timezone.utc).isoformat()
        return records

    def get_adapter_status(self) -> Dict[str, Any]:
        return {
            "name": "vanta",
            "connected": self._connected,
            "last_fetch": self._last_fetch,
            "mode": "file" if self._report_path else ("api" if self._api_token else "unconfigured"),
            "report_path": self._report_path,
        }

    def _load_data(self) -> dict:
        """Load Vanta data from file or API."""
        if self._report_path:
            try:
                with open(self._report_path) as f:
                    return json.load(f)
            except Exception as exc:
                log.warning("Failed to load Vanta report: %s", exc)
                return {}

        if self._api_token:
            try:
                import httpx
                resp = httpx.get(
                    f"{self._api_base}/v1/tests",
                    headers={"Authorization": f"Bearer {self._api_token}"},
                    timeout=30,
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception as exc:
                log.warning("Vanta API fetch failed: %s", exc)
            return {}

        return {}

    def _map_test_to_record(self, test: dict) -> Optional[NormalizedTrafficRecord]:
        """Map a Vanta test result to a NormalizedTrafficRecord."""
        test_name = test.get("name", test.get("title", test.get("id", "")))
        if not test_name:
            return None

        passed = test.get("passed", test.get("status", "") in ("pass", "passed", "compliant"))
        category = test.get("category", test.get("type", "")).lower().replace(" ", "_")

        return NormalizedTrafficRecord(
            record_id=test.get("id", uuid.uuid4().hex[:12]),
            timestamp=test.get("lastChecked", test.get("updated_at", datetime.now(timezone.utc).isoformat())),
            source_adapter="vanta",
            tool_name=test_name,
            caller_identity="vanta-agent",
            action="call" if passed else "deny",
            status="pass" if passed else "fail",
            policy_matched=category,
            metadata={
                "category": category,
                "framework": test.get("framework", ""),
                "description": test.get("description", "")[:200],
                "evidence_fn": _VANTA_CATEGORY_MAP.get(category, ""),
                "vanta_source": True,
            },
        )


def merge_vanta_report(comply_report: dict, vanta_records: List[NormalizedTrafficRecord]) -> dict:
    """Merge Vanta evidence with a Comply scan report.

    Produces a combined view showing:
    - Infrastructure controls (Vanta-decidable): status from Vanta
    - Product development controls (Comply): status from Comply scan
    - Coverage summary: total controls covered by each tool

    Returns
    -------
    dict
        Combined report with merged evidence.
    """
    # Build Vanta evidence map: evidence_fn -> list of records
    vanta_evidence = {}
    for rec in vanta_records:
        ev_fn = rec.metadata.get("evidence_fn", "")
        if ev_fn:
            vanta_evidence.setdefault(ev_fn, []).append(rec)

    # Count Vanta-covered controls
    vanta_met = 0
    vanta_total = len(set(r.metadata.get("evidence_fn") for r in vanta_records if r.metadata.get("evidence_fn")))

    # Merge into Comply report
    comply_met = 0
    comply_total = 0
    both_covered = 0

    for article in comply_report.get("articles", []):
        for ctrl in article.get("controls", []):
            comply_total += 1
            ev_fn = ctrl.get("evidence_fn", "")

            if ctrl.get("status") == "met":
                comply_met += 1

            # Check if Vanta has evidence for this control
            vanta_recs = vanta_evidence.get(ev_fn, [])
            if vanta_recs:
                passed = sum(1 for r in vanta_recs if r.status == "pass")
                total = len(vanta_recs)
                ctrl["vantaEvidence"] = {
                    "hasEvidence": True,
                    "passed": passed,
                    "total": total,
                    "status": "met" if passed == total else ("partial" if passed > 0 else "gap"),
                    "tests": [r.tool_name for r in vanta_recs[:5]],
                }
                if passed == total:
                    vanta_met += 1
                if ctrl.get("status") == "met":
                    both_covered += 1
            else:
                ctrl["vantaEvidence"] = {
                    "hasEvidence": False,
                    "status": "not_evaluated",
                }

    comply_report["vantaMerge"] = {
        "vantaControlsCovered": vanta_total,
        "vantaControlsMet": vanta_met,
        "complyControlsMet": comply_met,
        "complyControlsTotal": comply_total,
        "bothCovered": both_covered,
        "combinedCoverage": vanta_total + comply_total - both_covered,
        "message": (
            f"Infrastructure (Vanta): {vanta_met} controls met. "
            f"Product development (Comply): {comply_met} of {comply_total} controls assessed. "
            f"Together: {vanta_met + comply_met - both_covered} of "
            f"{vanta_total + comply_total - both_covered} covered."
        ),
    }

    return comply_report
