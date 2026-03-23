"""Section 12: Edge cases & error handling."""
import pytest

pytestmark = [pytest.mark.comply]


class TestEdgeCases:
    def test_bad_scan_id(self, new_user_client):
        r = new_user_client.get("/scan/nonexistent-id-xyz")
        assert r.status_code == 404

    def test_missing_body_on_scan(self, new_user_client):
        r = new_user_client.post("/scan")
        assert r.status_code == 422

    def test_bad_program_id(self, new_user_client):
        r = new_user_client.get("/programs/nonexistent-id-xyz")
        assert r.status_code == 404

    def test_bad_gate_id(self, new_user_client):
        r = new_user_client.get("/gate/nonexistent-id-xyz")
        assert r.status_code == 404

    def test_bad_monitor_id(self, new_user_client):
        r = new_user_client.get("/monitors/nonexistent-id-xyz")
        assert r.status_code == 404
