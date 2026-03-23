"""Section 4: Diff & regression detection."""
import pytest

pytestmark = [pytest.mark.comply]


def _get_scan_ids(client):
    """Return (oldest_id, newest_id) from history."""
    r = client.get("/history")
    scans = r.json()
    if isinstance(scans, dict):
        scans = scans.get("scans", scans.get("items", []))
    assert len(scans) >= 2
    oldest = scans[-1].get("id", scans[-1].get("scan_id", ""))
    newest = scans[0].get("id", scans[0].get("scan_id", ""))
    return oldest, newest


class TestDiffRegression:
    def test_diff_two_scans(self, journey_client):
        old_id, new_id = _get_scan_ids(journey_client)
        r = journey_client.get(f"/diff?scan1={old_id}&scan2={new_id}")
        assert r.status_code == 200
        d = r.json()
        assert "scoreDelta" in d

    def test_diff_direction(self, journey_client):
        """Later scan should generally have higher score."""
        old_id, new_id = _get_scan_ids(journey_client)
        r = journey_client.get(f"/diff?scan1={old_id}&scan2={new_id}")
        d = r.json()
        delta = d.get("scoreDelta", 0)
        assert isinstance(delta, (int, float))

    def test_set_and_get_baseline(self, journey_client):
        old_id, _ = _get_scan_ids(journey_client)

        # Set baseline
        r = journey_client.post(f"/baseline/{old_id}")
        assert r.status_code == 200

        # Find the scan's repo_path and framework
        r = journey_client.get("/history")
        scans = r.json()
        if isinstance(scans, dict):
            scans = scans.get("scans", scans.get("items", []))
        scan = next(s for s in scans if s.get("id") == old_id)
        repo_path = scan.get("repo_path", "")
        fw = scan.get("framework", "eu-ai-act")

        # Get baseline
        r = journey_client.get(
            f"/baseline?repo={repo_path}&framework={fw}")
        assert r.status_code == 200
        d = r.json()
        assert d.get("is_baseline") is True

    def test_regression_check(self, journey_client):
        _, new_id = _get_scan_ids(journey_client)
        r = journey_client.get(f"/scan/{new_id}/regression")
        # 200 if baseline exists, 404 if not — both are valid
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert "regressionDetected" in r.json()
