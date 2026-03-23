"""Sections 7 + 8: Gates and monitors."""
import pytest

pytestmark = [pytest.mark.comply]


class TestGates:
    def test_list_gate_decisions(self, journey_client):
        r = journey_client.get("/gate/decisions")
        d = r.json()
        decisions = d if isinstance(d, list) else d.get("decisions", [])
        assert r.status_code == 200
        assert len(decisions) == 2  # journey: 1 fail + 1 pass

    def test_gate_summary(self, journey_client):
        r = journey_client.get("/gate/summary")
        assert r.status_code == 200

    def test_get_single_decision(self, journey_client):
        r = journey_client.get("/gate/decisions")
        d = r.json()
        decisions = d if isinstance(d, list) else d.get("decisions", [])
        dec_id = decisions[0].get("decisionId", decisions[0].get("id", ""))
        r = journey_client.get(f"/gate/{dec_id}")
        assert r.status_code == 200
        assert "decision" in r.json() or "decisionId" in r.json()

    def test_badge_svg(self, journey_client):
        r = journey_client.get("/gate/badge/eu-ai-act")
        assert r.status_code == 200
        assert "svg" in r.headers.get("content-type", "") or "<svg" in r.text


class TestMonitors:
    def test_list_monitors(self, journey_client):
        r = journey_client.get("/monitors")
        monitors = r.json()
        if isinstance(monitors, dict):
            monitors = monitors.get("monitors", [])
        assert r.status_code == 200
        assert len(monitors) == 1  # journey: 1 monitor

    def test_monitor_detail(self, journey_client):
        r = journey_client.get("/monitors")
        monitors = r.json()
        if isinstance(monitors, dict):
            monitors = monitors.get("monitors", [])
        mon_id = monitors[0]["id"]
        r = journey_client.get(f"/monitors/{mon_id}")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_monitor_events(self, journey_client):
        r = journey_client.get("/monitors")
        monitors = r.json()
        if isinstance(monitors, dict):
            monitors = monitors.get("monitors", [])
        mon_id = monitors[0]["id"]
        r = journey_client.get(f"/monitors/{mon_id}/events")
        events = r.json()
        if isinstance(events, dict):
            events = events.get("events", [])
        assert r.status_code == 200
        assert len(events) == 6  # journey: 6 monitor events

    def test_monitor_alerts(self, journey_client):
        r = journey_client.get("/monitors")
        monitors = r.json()
        if isinstance(monitors, dict):
            monitors = monitors.get("monitors", [])
        mon_id = monitors[0]["id"]
        r = journey_client.get(f"/monitors/{mon_id}/alerts")
        assert r.status_code == 200

    def test_recent_events(self, journey_client):
        r = journey_client.get("/monitors/events/recent")
        assert r.status_code == 200

    def test_recent_alerts(self, journey_client):
        r = journey_client.get("/monitors/alerts/recent")
        assert r.status_code == 200

    def test_daemon_status(self, journey_client):
        r = journey_client.get("/monitors/daemon/status")
        assert r.status_code == 200
        assert "running" in r.json()
