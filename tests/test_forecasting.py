"""Section 10: Forecasting & confidence endpoints."""
import pytest

pytestmark = [pytest.mark.comply]

try:
    import graph  # noqa: F401
    HAS_GRAPH = True
except ImportError:
    HAS_GRAPH = False

needs_graph = pytest.mark.skipif(not HAS_GRAPH, reason="requires monorepo graph module")


class TestForecasting:
    @needs_graph
    def test_confidence_decay(self, multi_repo_client):
        r = multi_repo_client.get("/compliance/confidence")
        assert r.status_code == 200

    @needs_graph
    def test_entanglement_forecast(self, multi_repo_client):
        r = multi_repo_client.get("/compliance/forecast/entanglement")
        assert r.status_code == 200

    def test_forecast_endpoint(self, multi_repo_client):
        r = multi_repo_client.get("/forecast")
        # May require query params — 200 or 422 both valid
        assert r.status_code in (200, 422)
