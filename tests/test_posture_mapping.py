"""Section 5: Posture & mapping."""
import pytest

from conftest import assert_snapshot

pytestmark = [pytest.mark.comply, pytest.mark.snapshot]


class TestPostureMapping:
    def test_global_posture(self, multi_repo_client, update_snapshots):
        r = multi_repo_client.get("/posture")
        assert r.status_code == 200
        d = r.json()
        fws = d.get("frameworks", [])
        assert len(fws) > 0
        # Snapshot the framework count and names (deterministic)
        summary = {
            "framework_count": len(fws),
            "framework_ids": sorted(f.get("framework", f.get("id", ""))
                                    for f in fws),
        }
        assert_snapshot(summary, "multi_repo_posture_summary",
                        update=update_snapshots)

    def test_framework_posture(self, multi_repo_client):
        r = multi_repo_client.get("/posture/eu-ai-act")
        assert r.status_code == 200

    def test_control_mapping(self, multi_repo_client):
        r = multi_repo_client.get("/mapping")
        assert r.status_code == 200
        d = r.json()
        caps = (d if isinstance(d, list)
                else d.get("capabilities", d.get("mappings", [])))
        assert len(caps) > 0

    def test_compliance_matrix(self, multi_repo_client):
        r = multi_repo_client.get("/matrix")
        assert r.status_code == 200

    def test_jurisdictions(self, multi_repo_client):
        r = multi_repo_client.get("/jurisdictions")
        assert r.status_code == 200

    def test_mapping_priorities(self, multi_repo_client):
        r = multi_repo_client.get("/mapping/priorities")
        assert r.status_code == 200
