"""Minimal LLM abstraction for standalone Comply.

Supports Anthropic, OpenAI, Gemini, and Grok SDKs.
No config singleton or provider cache — just a plain function call.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)


def call_llm(
    prompt: str,
    provider: str = "anthropic",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 2000,
) -> str:
    """Call an LLM and return the text response.

    Parameters
    ----------
    prompt : str
        The user prompt to send.
    provider : str
        One of: anthropic, openai, gemini, grok.
    api_key : str or None
        API key. Falls back to standard env vars.
    model : str or None
        Model ID. Uses sensible defaults per provider.
    max_tokens : int
        Max response tokens.

    Returns
    -------
    str
        Model response text, or empty string on failure.
    """
    provider = provider.lower()
    if provider == "anthropic":
        return _call_anthropic(prompt, api_key, model, max_tokens)
    elif provider == "openai":
        return _call_openai(prompt, api_key, model, max_tokens)
    elif provider == "gemini":
        return _call_gemini(prompt, api_key, model, max_tokens)
    elif provider == "grok":
        return _call_grok(prompt, api_key, model, max_tokens)
    else:
        log.warning("Unknown LLM provider: %s", provider)
        return ""


def _call_anthropic(prompt: str, api_key: Optional[str], model: Optional[str], max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed")
        return ""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return ""
    client = anthropic.Anthropic(api_key=key)
    try:
        resp = client.messages.create(
            model=model or "claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text if resp.content else ""
    except Exception as exc:
        log.warning("Anthropic call failed: %s", exc)
        return ""


def _call_openai(prompt: str, api_key: Optional[str], model: Optional[str], max_tokens: int) -> str:
    try:
        import openai
    except ImportError:
        log.warning("openai SDK not installed")
        return ""
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return ""
    client = openai.OpenAI(api_key=key)
    try:
        resp = client.chat.completions.create(
            model=model or "gpt-4o",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        log.warning("OpenAI call failed: %s", exc)
        return ""


def _call_gemini(prompt: str, api_key: Optional[str], model: Optional[str], max_tokens: int) -> str:
    try:
        import openai
    except ImportError:
        log.warning("openai SDK not installed (needed for Gemini)")
        return ""
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return ""
    client = openai.OpenAI(api_key=key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    try:
        resp = client.chat.completions.create(
            model=model or "gemini-2.0-flash",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        log.warning("Gemini call failed: %s", exc)
        return ""


def _call_grok(prompt: str, api_key: Optional[str], model: Optional[str], max_tokens: int) -> str:
    try:
        import openai
    except ImportError:
        log.warning("openai SDK not installed (needed for Grok)")
        return ""
    key = api_key or os.environ.get("XAI_API_KEY", "")
    if not key:
        return ""
    client = openai.OpenAI(api_key=key, base_url="https://api.x.ai/v1")
    try:
        resp = client.chat.completions.create(
            model=model or "grok-3-mini",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        log.warning("Grok call failed: %s", exc)
        return ""
