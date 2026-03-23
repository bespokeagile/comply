"""Demo-mode security: URL validation, clone sandboxing, rate limiting helpers."""
from __future__ import annotations

import ipaddress
import logging
import os
import re
import shutil
from typing import List, Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# Allowed hosts for demo repo scanning
_ALLOWED_HOSTS = {"github.com", "gitlab.com"}

# Known framework IDs (must match frameworks.yaml)
ALLOWED_FRAMEWORKS = {
    "eu_ai_act", "nist_ai_rmf", "iso_42001", "soc2_ai",
    "california_ab_2013", "california_sb_942", "colorado_sb_24_205",
    "insurance_attestation", "owasp_llm_top10", "owasp_agentic_top10",
}

MAX_URL_LENGTH = 500
MAX_CLONE_SIZE_MB = 200


def is_demo_mode() -> bool:
    """Check if running in demo mode via environment variable."""
    return os.environ.get("COMPLY_DEMO_MODE", "").lower() in ("true", "1", "yes")


def validate_demo_url(url: str) -> Optional[str]:
    """Validate a URL for demo scanning. Returns error message or None if valid."""
    if not url or not isinstance(url, str):
        return "URL is required"

    if len(url) > MAX_URL_LENGTH:
        return f"URL exceeds maximum length ({MAX_URL_LENGTH} characters)"

    url = url.strip()

    # Reject non-HTTPS protocols
    if url.startswith("git@") or url.startswith("ssh://"):
        return "SSH URLs are not allowed in demo mode. Use HTTPS URLs only."

    if url.startswith("file://"):
        return "Local file URLs are not allowed in demo mode."

    # Must be HTTPS
    if not url.startswith("https://"):
        return "Only HTTPS URLs are allowed in demo mode."

    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"

    # Host must be in allowlist
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        return f"Only GitHub and GitLab URLs are allowed. Got: {host}"

    # Reject URLs with credentials
    if parsed.username or parsed.password:
        return "URLs with credentials are not allowed"

    # Reject private/localhost IPs
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return "Private, loopback, and reserved IPs are not allowed"
    except ValueError:
        pass  # Not an IP -- hostname is fine

    # Basic path validation: should look like a repo path
    path = parsed.path.strip("/")
    if not path or "/" not in path:
        return "URL must point to a specific repository (e.g. https://github.com/owner/repo)"

    return None


def validate_framework(framework: str) -> Optional[str]:
    """Validate framework ID. Returns error message or None if valid."""
    if not framework:
        return "Framework is required"
    if framework not in ALLOWED_FRAMEWORKS:
        return f"Unknown framework '{framework}'. Allowed: {', '.join(sorted(ALLOWED_FRAMEWORKS))}"
    return None


def check_clone_size(path: str) -> Optional[str]:
    """Check clone size doesn't exceed limit. Returns error or None."""
    try:
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
                if total > MAX_CLONE_SIZE_MB * 1024 * 1024:
                    # Clean up the clone
                    shutil.rmtree(path, ignore_errors=True)
                    return f"Repository exceeds {MAX_CLONE_SIZE_MB}MB size limit"
    except OSError as exc:
        log.warning("Clone size check failed: %s", exc)
    return None
