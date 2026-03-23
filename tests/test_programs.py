"""Section 6: Programs / Portfolio CRUD."""
import pytest

pytestmark = [pytest.mark.comply]


class TestProgramsCRUD:
    def test_list_programs(self, journey_client):
        r = journey_client.get("/programs")
        programs = r.json()
        if isinstance(programs, dict):
            programs = programs.get("programs", [])
        assert len(programs) == 1  # journey has 1 program

    def test_create_program(self, journey_client):
        r = journey_client.post("/programs", json={
            "name": "Test Program",
            "description": "Created by test",
            "repos": ["https://github.com/acme-corp/ml-platform"],
            "frameworks": ["eu-ai-act"],
        })
        assert r.status_code == 200
        d = r.json()
        prog_id = d.get("id", d.get("program_id", ""))
        assert prog_id

    def test_create_get_update_delete(self, journey_client):
        """Full CRUD lifecycle."""
        # Create
        r = journey_client.post("/programs", json={
            "name": "Lifecycle Test",
            "description": "Test CRUD",
            "repos": ["https://github.com/acme-corp/ml-platform"],
            "frameworks": ["eu-ai-act"],
        })
        assert r.status_code == 200
        d = r.json()
        prog_id = d.get("id", d.get("program_id", ""))
        assert prog_id

        # Read
        r = journey_client.get(f"/programs/{prog_id}")
        assert r.status_code == 200
        assert r.json().get("name") == "Lifecycle Test"

        # Update
        r = journey_client.put(f"/programs/{prog_id}", json={
            "name": "Updated Name",
            "description": "Updated",
            "repos": ["https://github.com/acme-corp/ml-platform"],
            "frameworks": ["eu-ai-act", "nist-ai-rmf"],
        })
        assert r.status_code == 200

        # Verify update
        r = journey_client.get(f"/programs/{prog_id}")
        assert r.json().get("name") == "Updated Name"

        # Delete
        r = journey_client.delete(f"/programs/{prog_id}")
        assert r.status_code == 200

        # Verify deletion
        r = journey_client.get(f"/programs/{prog_id}")
        assert r.status_code == 404

    def test_program_posture(self, journey_client):
        """Program posture endpoint returns data."""
        r = journey_client.get("/programs")
        programs = r.json()
        if isinstance(programs, dict):
            programs = programs.get("programs", [])
        assert len(programs) > 0
        prog_id = programs[0].get("id", "")
        r = journey_client.get(f"/programs/{prog_id}/posture")
        assert r.status_code == 200

    def test_multi_repo_programs(self, multi_repo_client):
        """Multi-repo persona has 2 programs."""
        r = multi_repo_client.get("/programs")
        programs = r.json()
        if isinstance(programs, dict):
            programs = programs.get("programs", [])
        assert len(programs) == 2
