"""REST endpoints for compliance forecasting."""
from __future__ import annotations

from fastapi import APIRouter

forecast_router = APIRouter(prefix="/forecast", tags=["forecast"])


@forecast_router.get("")
def get_forecast(
    repo: str = ".",
    framework: str = "eu-ai-act",
    weeks: int = 8,
    target_score: float = 80.0,
):
    """Generate a compliance score forecast from scan history.

    Query params:
        repo         — repository path (default ".")
        framework    — framework ID (default "eu-ai-act")
        weeks        — weeks to project forward (default 8)
        target_score — target compliance score (default 80)
    """
    from comply.forecast import forecast_score

    return forecast_score(
        repo=repo,
        framework=framework,
        weeks=weeks,
        target_score=target_score,
    )
