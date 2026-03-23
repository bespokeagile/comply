"""Section 13: Performance benchmarks (power_user persona)."""
import time

import pytest

pytestmark = [pytest.mark.comply, pytest.mark.slow]


def _timed_get(client, path):
    t0 = time.time()
    r = client.get(path)
    ms = (time.time() - t0) * 1000
    return r, ms


class TestPerformance:
    def test_health_under_100ms(self, power_user_client):
        r, ms = _timed_get(power_user_client, "/health")
        assert r.status_code == 200
        assert ms < 200, f"Health took {ms:.0f}ms (limit 200ms)"

    def test_history_under_500ms(self, power_user_client):
        r, ms = _timed_get(power_user_client, "/history?limit=100")
        assert r.status_code == 200
        assert ms < 500, f"History took {ms:.0f}ms (limit 500ms)"

    def test_posture_under_500ms(self, power_user_client):
        r, ms = _timed_get(power_user_client, "/posture")
        assert r.status_code == 200
        assert ms < 500, f"Posture took {ms:.0f}ms (limit 500ms)"

    def test_frameworks_under_100ms(self, power_user_client):
        r, ms = _timed_get(power_user_client, "/frameworks")
        assert r.status_code == 200
        assert ms < 200, f"Frameworks took {ms:.0f}ms (limit 200ms)"

    def test_mapping_under_200ms(self, power_user_client):
        r, ms = _timed_get(power_user_client, "/mapping")
        assert r.status_code == 200
        assert ms < 200, f"Mapping took {ms:.0f}ms (limit 200ms)"
