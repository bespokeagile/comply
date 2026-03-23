"""Section 3: Persistence — stored scan access (Bug #2 regression tests)."""
import pytest

from conftest import assert_snapshot

pytestmark = [pytest.mark.comply, pytest.mark.snapshot]


def _get_history(client):
    r = client.get("/history")
    scans = r.json()
    if isinstance(scans, dict):
        scans = scans.get("scans", scans.get("items", []))
    return scans


class TestPersistence:
    def test_history_has_scans(self, journey_client):
        scans = _get_history(journey_client)
        assert len(scans) == 7  # journey persona: 7 scans

    def test_stored_scan_poll(self, journey_client):
        """Stored scans are accessible via poll endpoint (Bug #2 fix)."""
        scans = _get_history(journey_client)
        scan_id = scans[0]["id"]
        r = journey_client.get(f"/scan/{scan_id}")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "complete"

    def test_stored_scan_report(self, journey_client):
        """Full report accessible for stored scans."""
        scans = _get_history(journey_client)
        scan_id = scans[0]["id"]
        r = journey_client.get(f"/scan/{scan_id}/report")
        assert r.status_code == 200
        d = r.json()
        assert "framework" in d

    def test_stored_scan_json_download(self, journey_client):
        """JSON download works on stored scans (Bug #2b fix)."""
        scans = _get_history(journey_client)
        scan_id = scans[0]["id"]
        r = journey_client.get(f"/scan/{scan_id}/download?fmt=json")
        assert r.status_code == 200
        d = r.json()
        assert "framework" in d

    def test_stored_scan_sarif(self, journey_client):
        """SARIF download works on stored scans."""
        scans = _get_history(journey_client)
        scan_id = scans[0]["id"]
        r = journey_client.get(f"/scan/{scan_id}/download?fmt=sarif")
        assert r.status_code == 200
        d = r.json()
        assert d.get("version") == "2.1.0"

    def test_deterministic_scan_count(self, journey_client, update_snapshots):
        """Journey persona always produces exactly 7 scans with deterministic data."""
        scans = _get_history(journey_client)
        summary = {
            "count": len(scans),
            "frameworks": sorted(set(s.get("framework", "") for s in scans)),
            "scores": [s.get("score", 0) for s in scans],
        }
        assert_snapshot(summary, "journey_persistence_summary",
                        update=update_snapshots)
