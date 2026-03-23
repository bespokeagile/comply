"""Section 2: Report access & export formats."""
import pytest

from conftest import assert_snapshot

pytestmark = [pytest.mark.comply, pytest.mark.snapshot]


def _first_scan_id(client):
    """Get the first scan ID from history."""
    r = client.get("/history")
    scans = r.json()
    if isinstance(scans, dict):
        scans = scans.get("scans", scans.get("items", []))
    assert len(scans) > 0, "Precondition: persona must have scans"
    return scans[0].get("id", scans[0].get("scan_id", ""))


class TestExport:
    def test_json_download(self, journey_client, update_snapshots):
        scan_id = _first_scan_id(journey_client)
        r = journey_client.get(f"/scan/{scan_id}/download?fmt=json")
        assert r.status_code == 200
        d = r.json()
        assert "framework" in d
        assert_snapshot(d["summary"], "journey_export_json_summary",
                        update=update_snapshots)

    def test_sarif_export(self, journey_client):
        scan_id = _first_scan_id(journey_client)
        r = journey_client.get(f"/scan/{scan_id}/download?fmt=sarif")
        assert r.status_code == 200
        d = r.json()
        assert d["version"] == "2.1.0"
        assert len(d.get("runs", [])) > 0

    def test_junit_export(self, journey_client):
        scan_id = _first_scan_id(journey_client)
        r = journey_client.get(f"/scan/{scan_id}/download?fmt=junit")
        assert r.status_code == 200
        assert "<testsuites" in r.text

    def test_markdown_export(self, journey_client):
        scan_id = _first_scan_id(journey_client)
        r = journey_client.get(f"/scan/{scan_id}/download?fmt=markdown")
        assert r.status_code == 200
        assert "## Compliance Scan" in r.text

    def test_report_not_found(self, journey_client):
        r = journey_client.get("/scan/bad-id-nonexistent/report")
        assert r.status_code == 404

    def test_download_not_found(self, journey_client):
        r = journey_client.get("/scan/bad-id-nonexistent/download?fmt=json")
        assert r.status_code == 404
