"""Funded scans: admin credit management + funded scan with mocked scanner."""
import time
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.comply, pytest.mark.slow]

from comply.test_seed import FRAMEWORKS, REPOS, SeedContext, _make_report


ADMIN_TOKEN = "test-admin-token-xyz"
FUNDED_API_KEY = "sk-ant-test-funded-key"


@pytest.fixture
def funded_client(tmp_path, monkeypatch):
    """TestClient with funded scans fully enabled."""
    from conftest import _make_client, _patch_store

    # Enable funded scans via env
    monkeypatch.setenv("COMPLY_FUNDED_SCANS", "true")
    monkeypatch.setenv("COMPLY_FUNDED_API_KEY", FUNDED_API_KEY)
    monkeypatch.setenv("COMPLY_FUNDED_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("COMPLY_FUNDED_DAILY_CAP", "100")

    client = _make_client("new_user", tmp_path, monkeypatch)
    return client


def _admin_headers():
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


class TestFundedAdmin:
    """Admin grant/revoke/users/usage — pure SQLite, no scanning."""

    def test_grant_credits(self, funded_client):
        r = funded_client.post("/admin/funded/grant",
                               json={"email": "test@example.com", "credits": 5},
                               headers=_admin_headers())
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == "test@example.com"
        assert d["total_credits"] == 5
        assert d["remaining"] == 5
        assert "invite_token" in d

    def test_grant_additional_credits(self, funded_client):
        """Granting twice adds credits."""
        funded_client.post("/admin/funded/grant",
                           json={"email": "add@test.com", "credits": 3},
                           headers=_admin_headers())
        r = funded_client.post("/admin/funded/grant",
                               json={"email": "add@test.com", "credits": 2},
                               headers=_admin_headers())
        assert r.status_code == 200
        assert r.json()["total_credits"] == 5

    def test_list_users(self, funded_client):
        funded_client.post("/admin/funded/grant",
                           json={"email": "user1@test.com", "credits": 3},
                           headers=_admin_headers())
        funded_client.post("/admin/funded/grant",
                           json={"email": "user2@test.com", "credits": 5},
                           headers=_admin_headers())
        r = funded_client.get("/admin/funded/users",
                              headers=_admin_headers())
        assert r.status_code == 200
        users = r.json()
        assert len(users) == 2

    def test_revoke_credits(self, funded_client):
        r = funded_client.post("/admin/funded/grant",
                               json={"email": "revoke@test.com", "credits": 5},
                               headers=_admin_headers())
        funded_client.post("/admin/funded/revoke",
                           json={"email": "revoke@test.com"},
                           headers=_admin_headers())
        # After full revoke, remaining should be 0
        token = r.json()["invite_token"]
        r = funded_client.get(f"/demo/funded/check?token={token}")
        assert r.json()["remaining"] == 0

    def test_reduce_credits(self, funded_client):
        r = funded_client.post("/admin/funded/grant",
                               json={"email": "reduce@test.com", "credits": 10},
                               headers=_admin_headers())
        funded_client.post("/admin/funded/revoke",
                           json={"email": "reduce@test.com", "reduce_by": 3},
                           headers=_admin_headers())
        token = r.json()["invite_token"]
        r = funded_client.get(f"/demo/funded/check?token={token}")
        assert r.json()["remaining"] == 7

    def test_usage_stats(self, funded_client):
        r = funded_client.get("/admin/funded/usage",
                              headers=_admin_headers())
        assert r.status_code == 200
        d = r.json()
        assert "today" in d
        assert "month" in d
        assert d["enabled"] is True

    def test_admin_requires_auth(self, funded_client):
        r = funded_client.get("/admin/funded/users")
        assert r.status_code == 401

    def test_admin_wrong_token(self, funded_client):
        r = funded_client.get("/admin/funded/users",
                              headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_revoke_nonexistent(self, funded_client):
        r = funded_client.post("/admin/funded/revoke",
                               json={"email": "nobody@test.com"},
                               headers=_admin_headers())
        assert r.status_code == 404


class TestFundedCheck:
    """User-facing credit check endpoint."""

    def test_check_valid_token(self, funded_client):
        r = funded_client.post("/admin/funded/grant",
                               json={"email": "check@test.com", "credits": 3},
                               headers=_admin_headers())
        token = r.json()["invite_token"]

        r = funded_client.get(f"/demo/funded/check?token={token}")
        assert r.status_code == 200
        d = r.json()
        assert d["valid"] is True
        assert d["remaining"] == 3
        assert d["email"] == "check@test.com"

    def test_check_invalid_token(self, funded_client):
        r = funded_client.get("/demo/funded/check?token=bogus-token")
        assert r.status_code == 200
        d = r.json()
        assert d["valid"] is False
        assert d["remaining"] == 0

    def test_check_empty_token(self, funded_client):
        r = funded_client.get("/demo/funded/check?token=")
        assert r.status_code == 200
        assert r.json()["remaining"] == 0


class TestFundedScan:
    """Funded scan endpoint with mocked scanner."""

    def test_funded_scan_uses_credit(self, funded_client):
        """Full flow: grant -> scan (mocked) -> credit consumed."""
        # Grant credits
        r = funded_client.post("/admin/funded/grant",
                               json={"email": "scan@test.com", "credits": 3},
                               headers=_admin_headers())
        token = r.json()["invite_token"]

        # Mock the scanner to return a canned report
        ctx = SeedContext(999)
        fake_report = _make_report(ctx, REPOS[0], FRAMEWORKS[0], score=72.0)
        fake_report["_model_info"] = {
            "input_tokens": 1000, "output_tokens": 500}

        with patch("comply.scanner.run_comply_scan", return_value=fake_report):
            r = funded_client.post("/demo/funded-scan", json={
                "url": "https://github.com/pallets/flask",
                "framework": "eu_ai_act",
                "token": token,
            })
            assert r.status_code == 200
            d = r.json()
            assert d["funded"] is True
            scan_id = d["scanId"]

            # Wait for background thread to complete
            for _ in range(20):
                time.sleep(0.2)
                r = funded_client.get(f"/scan/{scan_id}")
                if r.json().get("status") in ("complete", "error"):
                    break

        # Verify credit was consumed
        r = funded_client.get(f"/demo/funded/check?token={token}")
        assert r.json()["remaining"] == 2

    def test_funded_scan_invalid_token(self, funded_client):
        r = funded_client.post("/demo/funded-scan", json={
            "url": "https://github.com/pallets/flask",
            "framework": "eu_ai_act",
            "token": "invalid-token",
        })
        assert r.status_code == 401

    def test_funded_scan_no_credits(self, funded_client):
        """Token with 0 remaining credits should be rejected."""
        r = funded_client.post("/admin/funded/grant",
                               json={"email": "empty@test.com", "credits": 1},
                               headers=_admin_headers())
        token = r.json()["invite_token"]

        # Use up the one credit
        ctx = SeedContext(888)
        fake_report = _make_report(ctx, REPOS[0], FRAMEWORKS[0], score=50.0)
        fake_report["_model_info"] = {"input_tokens": 100, "output_tokens": 50}

        with patch("comply.scanner.run_comply_scan", return_value=fake_report):
            funded_client.post("/demo/funded-scan", json={
                "url": "https://github.com/pallets/flask",
                "framework": "eu_ai_act",
                "token": token,
            })
            # Wait for completion
            time.sleep(2)

        # Second scan should be rejected — no credits left
        r = funded_client.post("/demo/funded-scan", json={
            "url": "https://github.com/pallets/flask",
            "framework": "eu_ai_act",
            "token": token,
        })
        assert r.status_code == 403


class TestFundedDisabled:
    """Funded scan endpoints when feature is disabled."""

    def test_check_when_disabled(self, new_user_client):
        r = new_user_client.get("/demo/funded/check?token=any")
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_scan_when_disabled(self, new_user_client):
        r = new_user_client.post("/demo/funded-scan", json={
            "url": "https://github.com/pallets/flask",
            "framework": "eu_ai_act",
            "token": "any",
        })
        assert r.status_code == 503

    def test_admin_when_no_token_configured(self, new_user_client):
        r = new_user_client.get("/admin/funded/users",
                                headers={"Authorization": "Bearer anything"})
        assert r.status_code == 503
