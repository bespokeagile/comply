"""Narration & chat endpoints with mocked LLM provider."""
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.comply]

try:
    import cost_tracker  # noqa: F401
    HAS_COST_TRACKER = True
except ImportError:
    HAS_COST_TRACKER = False

needs_cost_tracker = pytest.mark.skipif(
    not HAS_COST_TRACKER, reason="requires monorepo cost_tracker module")

from comply.test_seed import FRAMEWORKS, REPOS, SeedContext, _make_report


def _create_completed_scan(client):
    """Create an in-memory completed scan and return its ID.

    Uses scan_state directly (narration endpoints only work with
    in-memory scans, not stored scans).
    """
    from comply.scan_state import create_scan, update_scan

    ctx = SeedContext(777)
    report = _make_report(ctx, REPOS[0], FRAMEWORKS[0], score=65.0)

    scan = create_scan(
        url="https://github.com/acme-corp/ml-platform",
        framework="eu-ai-act",
        depth="content",
        output_dir="/tmp/test-narration",
    )
    update_scan(scan.id, status="complete", report=report)
    return scan.id


MOCK_NARRATION = {
    "narration": "This repository shows moderate compliance with the EU AI Act. "
                 "Key gaps include risk assessment documentation and bias detection.",
    "model": "mock-model",
    "cost_usd": 0.003,
    "input_tokens": 2000,
    "output_tokens": 150,
}

MOCK_CHAT_RESPONSE = {
    "response": "The main gap is in Article 3 — risk assessment documentation. "
                "You should add a MODEL_CARD.md file.",
    "model": "mock-model",
    "cost_usd": 0.002,
    "input_tokens": 2500,
    "output_tokens": 100,
}


class TestNarrationEstimate:
    @needs_cost_tracker
    def test_estimate_no_llm_call(self, new_user_client):
        """Cost estimate endpoint should work without an LLM key."""
        scan_id = _create_completed_scan(new_user_client)
        r = new_user_client.get(f"/scan/{scan_id}/narrate/estimate")
        assert r.status_code == 200
        d = r.json()
        # Estimate should have cost fields
        assert "estimated_cost_usd" in d or "cost_usd" in d or "tokens" in d

    def test_estimate_not_found(self, new_user_client):
        r = new_user_client.get("/scan/nonexistent-id/narrate/estimate")
        assert r.status_code == 404


class TestNarration:
    def test_narrate_full(self, new_user_client):
        """One-shot narration with mocked LLM."""
        scan_id = _create_completed_scan(new_user_client)

        with patch("comply.narration.narrate_scan",
                    return_value=MOCK_NARRATION):
            r = new_user_client.get(
                f"/scan/{scan_id}/narrate?llm_key=test-key")
            assert r.status_code == 200
            d = r.json()
            assert "narration" in d
            assert d["cached"] is False
            assert "EU AI Act" in d["narration"]

    def test_narrate_cached(self, new_user_client):
        """Second call returns cached narration without LLM call."""
        scan_id = _create_completed_scan(new_user_client)

        with patch("comply.narration.narrate_scan",
                    return_value=MOCK_NARRATION) as mock_fn:
            # First call
            new_user_client.get(
                f"/scan/{scan_id}/narrate?llm_key=test-key")
            # Second call — should be cached
            r = new_user_client.get(
                f"/scan/{scan_id}/narrate?llm_key=test-key")
            assert r.status_code == 200
            assert r.json()["cached"] is True
            # LLM should only be called once
            assert mock_fn.call_count == 1

    def test_narrate_no_key_returns_401(self, new_user_client):
        """Missing LLM key should return 401 with helpful message."""
        scan_id = _create_completed_scan(new_user_client)

        def _raise_auth(*args, **kwargs):
            raise Exception("No api_key provided")

        with patch("comply.narration.narrate_scan",
                    side_effect=_raise_auth):
            r = new_user_client.get(f"/scan/{scan_id}/narrate")
            assert r.status_code == 401
            assert "API key" in r.json()["detail"]

    def test_narrate_not_found(self, new_user_client):
        r = new_user_client.get("/scan/nonexistent-id/narrate")
        assert r.status_code == 404


class TestNarrationStream:
    def test_stream_narration(self, new_user_client):
        """SSE streaming endpoint returns event stream."""
        scan_id = _create_completed_scan(new_user_client)

        def _mock_stream(**kwargs):
            import json
            yield f"data: {json.dumps({'token': 'Hello '})}\n\n"
            yield f"data: {json.dumps({'token': 'world.'})}\n\n"
            yield f"data: {json.dumps({'done': True, 'model': 'mock', 'cost_usd': 0.001})}\n\n"

        with patch("comply.narration.narrate_scan_stream",
                    return_value=_mock_stream()):
            r = new_user_client.get(
                f"/scan/{scan_id}/narrate/stream?llm_key=test-key")
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            # Body should contain SSE data lines
            assert "data:" in r.text

    def test_stream_cached(self, new_user_client):
        """After a full narration, streaming returns cached text."""
        scan_id = _create_completed_scan(new_user_client)

        # First: cache via one-shot
        with patch("comply.narration.narrate_scan",
                    return_value=MOCK_NARRATION):
            new_user_client.get(
                f"/scan/{scan_id}/narrate?llm_key=test-key")

        # Now stream should serve from cache
        r = new_user_client.get(
            f"/scan/{scan_id}/narrate/stream?llm_key=test-key")
        assert r.status_code == 200
        assert "data:" in r.text


class TestChat:
    def test_chat_respond(self, new_user_client):
        """Chat follow-up with mocked LLM."""
        scan_id = _create_completed_scan(new_user_client)

        with patch("comply.narration.chat_respond",
                    return_value=MOCK_CHAT_RESPONSE):
            r = new_user_client.post("/chat", json={
                "scan_id": scan_id,
                "message": "What's the biggest gap?",
                "llm_key": "test-key",
            })
            assert r.status_code == 200
            d = r.json()
            assert "response" in d
            assert "MODEL_CARD" in d["response"]

    def test_chat_no_key_returns_401(self, new_user_client):
        scan_id = _create_completed_scan(new_user_client)

        def _raise_auth(*args, **kwargs):
            raise Exception("No api_key provided")

        with patch("comply.narration.chat_respond",
                    side_effect=_raise_auth):
            r = new_user_client.post("/chat", json={
                "scan_id": scan_id,
                "message": "What's the biggest gap?",
            })
            assert r.status_code == 401

    def test_chat_scan_not_found(self, new_user_client):
        r = new_user_client.post("/chat", json={
            "scan_id": "nonexistent-id",
            "message": "Hello",
        })
        assert r.status_code == 404


class TestChatEstimate:
    @needs_cost_tracker
    def test_chat_estimate(self, new_user_client):
        scan_id = _create_completed_scan(new_user_client)
        r = new_user_client.post("/chat/estimate", json={
            "scan_id": scan_id,
            "message": "What's the biggest gap?",
        })
        assert r.status_code == 200
