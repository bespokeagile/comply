"""Tier definitions for Comply OSS.

Open-source edition -- everything is unlocked. No restrictions.
All check_* functions return True unconditionally.
"""
from __future__ import annotations

from typing import Optional


def get_tier() -> str:
    """Return the current tier name. Always 'oss' in the open-source edition."""
    return "oss"


def get_tier_config() -> dict:
    """Return the tier configuration. Everything unlocked."""
    return {
        "label": "OSS",
        "max_projects": -1,
        "frameworks": [],
        "max_frameworks_per_scan": -1,
        "max_depth": "semantic",
        "exports": ["json", "docx", "zip", "sarif", "junit", "markdown"],
    }


def set_tier(tier: str, license_key: Optional[str] = None):
    """No-op in the open-source edition."""
    pass


def check_framework_allowed(framework: str) -> bool:
    """All frameworks are allowed."""
    return True


def check_depth_allowed(depth: str) -> bool:
    """All scan depths are allowed."""
    return True


def check_multi_framework_allowed(count: int) -> bool:
    """Multi-framework scanning is always allowed."""
    return True


def check_export_allowed(fmt: str) -> bool:
    """All export formats are allowed."""
    return True
