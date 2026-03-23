"""Section 1 + 11: Health, frameworks, config, capabilities, cache."""
import pytest

pytestmark = [pytest.mark.comply]


class TestHealthCheck:
    def test_health_returns_ok(self, new_user_client):
        r = new_user_client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert "db" in d

    def test_framework_list(self, new_user_client):
        r = new_user_client.get("/frameworks")
        fws = r.json()
        fw_list = fws if isinstance(fws, list) else fws.get("frameworks", [])
        assert len(fw_list) >= 8

    def test_empty_history(self, new_user_client):
        r = new_user_client.get("/history")
        scans = r.json()
        if isinstance(scans, dict):
            scans = scans.get("scans", scans.get("items", []))
        assert len(scans) == 0


class TestConfig:
    def test_get_tier(self, new_user_client):
        r = new_user_client.get("/tier")
        assert r.status_code == 200

    def test_get_config(self, new_user_client):
        r = new_user_client.get("/config")
        assert r.status_code == 200

    def test_capabilities(self, new_user_client):
        r = new_user_client.get("/capabilities")
        assert r.status_code == 200

    def test_cache_stats(self, new_user_client):
        r = new_user_client.get("/cache/stats")
        assert r.status_code == 200
