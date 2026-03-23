"""LLM narration layer for Comply scan results.

Builds prompts from the orchestrator journey context, estimates cost before
calling the LLM, and streams narrated results via SSE.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Generator, Optional, Tuple

_log = logging.getLogger(__name__)

# Journey context document — loaded once and cached
_JOURNEY_CONTEXT: Optional[str] = None
_JOURNEY_PATH = Path(__file__).resolve().parent.parent / "docs" / "orchestrator_comply_journey.md"

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024


def _load_journey_context() -> str:
    global _JOURNEY_CONTEXT
    if _JOURNEY_CONTEXT is None:
        try:
            _JOURNEY_CONTEXT = _JOURNEY_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            _log.warning("Journey context not found at %s — using fallback", _JOURNEY_PATH)
            _JOURNEY_CONTEXT = (
                "You are an AI compliance assistant for BespokeAgile Comply. "
                "Explain scan results in plain language. Lead with actionable insights. "
                "Be direct and specific."
            )
    return _JOURNEY_CONTEXT


def _detect_phase(repo_url: str) -> str:
    """Detect journey phase from scan history count."""
    try:
        from comply.store import list_scans as list_stored
        scans = list_stored(repo=repo_url)
        count = len(scans)
    except Exception:
        count = 0

    if count == 0:
        return "A"
    elif count == 1:
        return "B"
    elif count <= 5:
        return "C"
    elif count <= 10:
        return "D"
    else:
        return "E"


def _phase_instruction(phase: str) -> str:
    """Return phase-specific system prompt addition."""
    instructions = {
        "A": (
            "This is the user's first scan. They are in Phase A (First Contact). "
            "Lead with the score, interpret it simply, and identify the top 3 gaps. "
            "Do NOT mention adapters, monitors, gates, or forecasting yet."
        ),
        "B": (
            "The user has one prior scan. They are in Phase B (Understanding the Baseline). "
            "Interpret results in context. Suggest setting this as baseline. "
            "Identify top 3 gaps by impact and explain what fixing each one means concretely."
        ),
        "C": (
            "The user has 2-5 scans. They are in Phase C (Building Momentum). "
            "Show progress since baseline. Celebrate wins. If score plateaued, "
            "suggest adapters or deeper scans. Introduce forecast if helpful."
        ),
        "D": (
            "The user has 5-10 scans. They are in Phase D (Automation). "
            "Suggest monitoring and CI/CD gates if not already set up. "
            "Tune existing automation. Consider multi-framework if appropriate."
        ),
        "E": (
            "The user has 10+ scans. They are in Phase E (Mature Compliance Program). "
            "Focus on quarterly review, cross-framework expansion, and strategic value. "
            "Do not create busywork."
        ),
    }
    return instructions.get(phase, instructions["A"])


def _summarize_report(report: dict) -> str:
    """Build a structured text summary of a scan report for the LLM prompt."""
    framework = report.get("framework", "unknown")
    score = report.get("score", 0)
    summary = report.get("summary", {})
    met = summary.get("met", 0)
    partial = summary.get("partial", 0)
    gap = summary.get("gap", 0)
    total = met + partial + gap

    lines = [
        f"Framework: {framework}",
        f"Overall score: {score}%",
        f"Controls: {total} total — {met} met, {partial} partial, {gap} gap",
        "",
    ]

    # Top gaps with evidence and recommendations
    articles = report.get("articles", [])
    gaps = []
    partials = []
    for article in articles:
        for control in article.get("controls", []):
            status = control.get("status", "")
            if status == "gap":
                gaps.append(control)
            elif status == "partial":
                partials.append(control)

    # Show top 5 gaps, then top 3 partials
    if gaps:
        lines.append("TOP GAPS:")
        for ctrl in gaps[:5]:
            cid = ctrl.get("id", ctrl.get("controlId", "?"))
            req = ctrl.get("requirement", ctrl.get("title", ""))
            lines.append(f"  - [{cid}] {req}")
            for g in ctrl.get("gaps", [])[:2]:
                lines.append(f"    Gap: {g}")
            for r in ctrl.get("recommendations", ctrl.get("recommendation", []))[:1]:
                if isinstance(r, str):
                    lines.append(f"    Recommendation: {r}")
        lines.append("")

    if partials:
        lines.append("TOP PARTIAL CONTROLS:")
        for ctrl in partials[:3]:
            cid = ctrl.get("id", ctrl.get("controlId", "?"))
            req = ctrl.get("requirement", ctrl.get("title", ""))
            lines.append(f"  - [{cid}] {req}")
            evidence = ctrl.get("evidence", [])
            if evidence:
                layers = [
                    e.get("layer", "") if isinstance(e, dict) else str(e)
                    for e in evidence
                    if (e.get("found") if isinstance(e, dict) else e)
                ]
                lines.append(f"    Evidence found in: {', '.join(layers) if layers else 'none'}")
        lines.append("")

    return "\n".join(lines)


def build_narration_prompt(
    scan_report: dict,
    framework: str = "",
    repo_url: str = "",
) -> Tuple[str, str]:
    """Build (system_prompt, user_message) for narration.

    Shared by estimate and narrate so token counts match.
    """
    journey = _load_journey_context()
    phase = _detect_phase(repo_url or scan_report.get("repo_url", ""))
    phase_instr = _phase_instruction(phase)

    system_prompt = (
        f"{journey}\n\n"
        f"---\n\n"
        f"CURRENT PHASE: {phase}\n"
        f"{phase_instr}\n\n"
        f"INSTRUCTIONS: Narrate the following scan results conversationally. "
        f"Lead with the score in context, then explain the top gaps in plain language "
        f"with concrete actions. Be direct and specific. Use markdown formatting. "
        f"Keep the response under 800 words."
    )

    report_summary = _summarize_report(scan_report)
    user_message = f"Here are my compliance scan results:\n\n{report_summary}"

    return system_prompt, user_message


def estimate_narration_cost(
    scan_report: dict,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    framework: str = "",
    repo_url: str = "",
) -> dict:
    """Estimate LLM cost without making a call."""
    from cost_tracker import estimate_call_cost

    system_prompt, user_message = build_narration_prompt(scan_report, framework, repo_url)
    full_text = system_prompt + user_message
    est_input_tokens = len(full_text) // 4

    cost = estimate_call_cost(model, est_input_tokens, max_tokens)

    return {
        "estimated_cost_usd": round(cost, 6),
        "model": model,
        "estimated_input_tokens": est_input_tokens,
        "max_output_tokens": max_tokens,
    }


def _resolve_provider(model: str, llm_api_key: Optional[str] = None,
                      llm_provider_name: Optional[str] = None):
    """Resolve an LLM provider, preferring explicit key > config > env."""
    if llm_api_key:
        # BYOK — create a one-off provider with the given key
        from llm_provider import infer_provider, AnthropicProvider, OpenAIProvider, GeminiProvider, GrokProvider
        pname = llm_provider_name or infer_provider(model)
        if pname == "anthropic":
            return AnthropicProvider(api_key=llm_api_key)
        elif pname == "openai":
            return OpenAIProvider(api_key=llm_api_key)
        elif pname == "gemini":
            return GeminiProvider(api_key=llm_api_key)
        elif pname == "grok":
            return GrokProvider(api_key=llm_api_key)
        else:
            return AnthropicProvider(api_key=llm_api_key)

    # Fall back to configured provider
    from llm_provider import get_provider
    return get_provider(model)


def narrate_scan(
    scan_report: dict,
    framework: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    llm_api_key: Optional[str] = None,
    llm_provider_name: Optional[str] = None,
    repo_url: str = "",
) -> dict:
    """Call the LLM and return narration + actual cost."""
    from cost_tracker import estimate_call_cost

    provider = _resolve_provider(model, llm_api_key, llm_provider_name)
    system_prompt, user_message = build_narration_prompt(scan_report, framework, repo_url)

    response = provider.complete(
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=max_tokens,
    )

    cost = estimate_call_cost(model, response.input_tokens, response.output_tokens)

    return {
        "narration": response.text,
        "model": model,
        "cost_usd": round(cost, 6),
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


def narrate_scan_stream(
    scan_report: dict,
    framework: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    llm_api_key: Optional[str] = None,
    llm_provider_name: Optional[str] = None,
    repo_url: str = "",
) -> Generator[str, None, None]:
    """Stream narration tokens via SSE-compatible generator.

    Falls back to non-streaming (yields full text at once) since the
    provider abstraction doesn't expose streaming yet.
    """
    result = narrate_scan(
        scan_report=scan_report,
        framework=framework,
        model=model,
        max_tokens=max_tokens,
        llm_api_key=llm_api_key,
        llm_provider_name=llm_provider_name,
        repo_url=repo_url,
    )
    text = result["narration"]

    # Simulate streaming by yielding chunks
    chunk_size = 20  # characters per SSE event
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        yield f"data: {_sse_json({'token': chunk})}\n\n"

    # Final event with metadata
    yield f"data: {_sse_json({'done': True, 'cost_usd': result['cost_usd'], 'model': result['model']})}\n\n"


def _sse_json(obj: dict) -> str:
    import json
    return json.dumps(obj)


# ── Chat (follow-up questions) ──────────────────────────────────────────────


def build_chat_prompt(
    scan_report: dict,
    user_message: str,
    repo_url: str = "",
) -> Tuple[str, str]:
    """Build (system_prompt, user_message) for follow-up chat."""
    journey = _load_journey_context()
    report_summary = _summarize_report(scan_report)

    system_prompt = (
        f"{journey}\n\n"
        f"---\n\n"
        f"You are answering a follow-up question about a compliance scan. "
        f"Here is the scan context:\n\n{report_summary}\n\n"
        f"Answer the user's question directly and specifically. Use markdown. "
        f"Reference specific control IDs and concrete actions."
    )

    return system_prompt, user_message


def estimate_chat_cost(
    scan_report: dict,
    user_message: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    repo_url: str = "",
) -> dict:
    """Estimate cost for a follow-up chat message."""
    from cost_tracker import estimate_call_cost

    system_prompt, msg = build_chat_prompt(scan_report, user_message, repo_url)
    full_text = system_prompt + msg
    est_input_tokens = len(full_text) // 4

    cost = estimate_call_cost(model, est_input_tokens, max_tokens)

    return {
        "estimated_cost_usd": round(cost, 6),
        "model": model,
        "estimated_input_tokens": est_input_tokens,
        "max_output_tokens": max_tokens,
    }


def chat_respond(
    scan_report: dict,
    user_message: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    llm_api_key: Optional[str] = None,
    llm_provider_name: Optional[str] = None,
    repo_url: str = "",
) -> dict:
    """Answer a follow-up question about a scan."""
    from cost_tracker import estimate_call_cost

    provider = _resolve_provider(model, llm_api_key, llm_provider_name)
    system_prompt, msg = build_chat_prompt(scan_report, user_message, repo_url)

    response = provider.complete(
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": msg}],
        max_tokens=max_tokens,
    )

    cost = estimate_call_cost(model, response.input_tokens, response.output_tokens)

    return {
        "response": response.text,
        "model": model,
        "cost_usd": round(cost, 6),
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }
