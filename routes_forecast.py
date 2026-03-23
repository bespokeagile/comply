"""Comply causal forecasting, narration, and chat endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from comply.scan_state import get_scan, update_scan

log = logging.getLogger(__name__)

router = APIRouter()


# -- Causal compliance forecasting (Wolfram Gap 6) -----------------------------

@router.get("/compliance/confidence")
def confidence_decay(repo: str = "", framework: str = "eu-ai-act"):
    """Confidence decay: how stale is each control's last-evaluated status?

    Query params:
        repo      -- repository path (uses latest scan)
        framework -- framework ID
    """
    from comply.causal_forecast import compute_confidence_decay
    from comply.store import list_scans
    import json as _json

    fw = framework.replace("-", "_")
    scans = list_scans(repo=repo, framework=fw, limit=1)
    if not scans:
        scans = list_scans(repo=repo, framework=framework, limit=1)
    if not scans:
        raise HTTPException(404, "No scans found for this repo/framework")

    scan = scans[0]
    report = scan.get("report", {})
    if isinstance(report, str):
        try:
            report = _json.loads(report)
        except (ValueError, TypeError):
            report = {}

    return JSONResponse(compute_confidence_decay(report))


class PlannedChangesRequest(BaseModel):
    feature_ids: list
    repo: str = ""
    framework: str = "eu-ai-act"


@router.post("/compliance/forecast/changes")
def forecast_changes(req: PlannedChangesRequest):
    """Predict which controls need re-evaluation after planned feature changes."""
    from comply.causal_forecast import forecast_from_planned_changes
    from comply.store import list_scans
    import json as _json

    fw = req.framework.replace("-", "_")
    scans = list_scans(repo=req.repo, framework=fw, limit=1)
    if not scans:
        scans = list_scans(repo=req.repo, framework=req.framework, limit=1)
    if not scans:
        raise HTTPException(404, "No scans found for this repo/framework")

    scan = scans[0]
    report = scan.get("report", {})
    if isinstance(report, str):
        try:
            report = _json.loads(report)
        except (ValueError, TypeError):
            report = {}

    return JSONResponse(forecast_from_planned_changes(req.feature_ids, report))


# -- Narration & Chat ---------------------------------------------------------


@router.get("/scan/{scan_id}/narrate/estimate")
def narrate_estimate(scan_id: str, model: str = "claude-sonnet-4-6"):
    """Pre-flight cost estimate for narration -- no LLM call."""
    scan = get_scan(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    if scan.status != "complete" or scan.report is None:
        raise HTTPException(400, "Scan not yet complete")

    from comply.narration import estimate_narration_cost
    return estimate_narration_cost(scan.report, model=model, repo_url=scan.url)


@router.get("/scan/{scan_id}/narrate")
def narrate_full(scan_id: str, model: str = "claude-sonnet-4-6",
                 llm_key: Optional[str] = None, llm_provider: Optional[str] = None):
    """One-shot narration (cached after first call)."""
    scan = get_scan(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    if scan.status != "complete" or scan.report is None:
        raise HTTPException(400, "Scan not yet complete")

    # Return cached narration if available
    if scan.narration is not None:
        return {
            "narration": scan.narration,
            "cached": True,
            **(scan.narration_cost or {}),
        }

    from comply.narration import narrate_scan
    try:
        result = narrate_scan(
            scan_report=scan.report,
            framework=scan.framework,
            model=model,
            llm_api_key=llm_key,
            llm_provider_name=llm_provider,
            repo_url=scan.url,
        )
    except Exception as exc:
        msg = str(exc)
        if "api_key" in msg.lower() or "auth" in msg.lower() or "apikey" in msg.lower():
            raise HTTPException(
                401,
                "Configure an LLM API key to enable AI narration. "
                "Set ANTHROPIC_API_KEY (or another provider key) in your environment, "
                "or pass llm_key as a query parameter."
            )
        raise HTTPException(500, f"Narration failed: {msg}")

    # Cache the result
    update_scan(scan_id, narration=result["narration"], narration_cost={
        "model": result["model"],
        "cost_usd": result["cost_usd"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    })

    return {
        "narration": result["narration"],
        "cached": False,
        "model": result["model"],
        "cost_usd": result["cost_usd"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }


@router.get("/scan/{scan_id}/narrate/stream")
def narrate_stream(scan_id: str, model: str = "claude-sonnet-4-6",
                   llm_key: Optional[str] = None, llm_provider: Optional[str] = None):
    """SSE streaming narration."""
    from fastapi.responses import StreamingResponse

    scan = get_scan(scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    if scan.status != "complete" or scan.report is None:
        raise HTTPException(400, "Scan not yet complete")

    # If cached, stream the cached text
    if scan.narration is not None:
        import json as _json

        def _cached_stream():
            text = scan.narration
            chunk_size = 20
            for i in range(0, len(text), chunk_size):
                yield f"data: {_json.dumps({'token': text[i:i+chunk_size]})}\n\n"
            yield f"data: {_json.dumps({'done': True, 'cached': True, **(scan.narration_cost or {})})}\n\n"

        return StreamingResponse(_cached_stream(), media_type="text/event-stream")

    from comply.narration import narrate_scan_stream

    def _stream():
        try:
            full_text = []
            cost_info = {}
            for event in narrate_scan_stream(
                scan_report=scan.report,
                framework=scan.framework,
                model=model,
                llm_api_key=llm_key,
                llm_provider_name=llm_provider,
                repo_url=scan.url,
            ):
                yield event
                # Parse to capture text and cost for caching
                import json as _json
                try:
                    line = event.strip()
                    if line.startswith("data: "):
                        payload = _json.loads(line[6:])
                        if "token" in payload:
                            full_text.append(payload["token"])
                        if payload.get("done"):
                            cost_info = {k: v for k, v in payload.items() if k != "done"}
                except (ValueError, KeyError) as e:
                    log.debug("Failed to parse SSE payload: %s", e)

            # Cache after streaming completes
            narration_text = "".join(full_text)
            if narration_text:
                update_scan(scan_id, narration=narration_text, narration_cost=cost_info)

        except Exception as exc:
            import json as _json
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


class ChatRequest(BaseModel):
    message: str
    scan_id: str
    framework: Optional[str] = None
    model: str = "claude-sonnet-4-6"
    llm_key: Optional[str] = None
    llm_provider: Optional[str] = None


@router.post("/chat")
def chat(req: ChatRequest):
    """Follow-up question about a scan."""
    scan = get_scan(req.scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    if scan.status != "complete" or scan.report is None:
        raise HTTPException(400, "Scan not yet complete")

    from comply.narration import chat_respond
    try:
        result = chat_respond(
            scan_report=scan.report,
            user_message=req.message,
            model=req.model,
            llm_api_key=req.llm_key,
            llm_provider_name=req.llm_provider,
            repo_url=scan.url,
        )
    except Exception as exc:
        msg = str(exc)
        if "api_key" in msg.lower() or "auth" in msg.lower():
            raise HTTPException(
                401,
                "Configure an LLM API key to enable AI chat."
            )
        raise HTTPException(500, f"Chat failed: {msg}")

    return result


class ChatEstimateRequest(BaseModel):
    message: str
    scan_id: str
    model: str = "claude-sonnet-4-6"


@router.post("/chat/estimate")
def chat_estimate(req: ChatEstimateRequest):
    """Pre-flight cost estimate for a follow-up question."""
    scan = get_scan(req.scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    if scan.status != "complete" or scan.report is None:
        raise HTTPException(400, "Scan not yet complete")

    from comply.narration import estimate_chat_cost
    return estimate_chat_cost(
        scan_report=scan.report,
        user_message=req.message,
        model=req.model,
        repo_url=scan.url,
    )
