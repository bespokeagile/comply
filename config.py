"""Local configuration: ``~/.comply/config.yaml``.

This holds the user's LLM provider, model, API key, and adapter settings. It is
local-install plumbing and has nothing to do with tiers -- it lived inside
``tiers.py`` only because the removed licensing code read a license key out of
the same file. That colocation is what broke the carve-out: whoever removed the
tier logic did so correctly and could not see that config was riding along, so
four call sites and one CLI command went with it.

Accessors are FUNCTIONS, not module constants, deliberately. ``store.py:17``
resolves ``COMPLY_DATA_DIR`` once at import, which freezes the path for the life
of the process and makes it unsettable from a test. This module is the canonical
config accessor for four call sites, so it resolves per call instead. The
divergence from ``store.py`` is intentional and noted rather than silent; the
same repair there is separate work.
"""
from __future__ import annotations

import logging
import os

import yaml

log = logging.getLogger(__name__)

_DEFAULT_DIR = "~/.comply"


def config_dir() -> str:
    """Directory holding local Comply state. Honors ``COMPLY_DATA_DIR``."""
    return os.environ.get("COMPLY_DATA_DIR", os.path.expanduser(_DEFAULT_DIR))


def config_path() -> str:
    """Full path to ``config.yaml``."""
    return os.path.join(config_dir(), "config.yaml")


def load_config() -> dict:
    """Return the config mapping, or ``{}`` if absent or unreadable.

    The default is an EMPTY dict. The previous implementation returned
    ``{"tier": "free"}``, which made every caller carry a tier key that no
    longer means anything, and made "no config file" indistinguishable from
    "config file that happens to say free".
    """
    path = config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as fh:
            cfg = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        log.debug("Failed to load comply config from %s: %s", path, exc)
        return {}
    return cfg if isinstance(cfg, dict) else {}


def save_config(cfg: dict) -> None:
    """Write the config mapping, with owner-only permissions.

    This file stores ``llm_api_key`` in plaintext, so the directory is created
    0700 and the file forced to 0600. The implementation this replaces did
    neither, leaving an API key world-readable under a default umask.
    """
    directory = config_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError as exc:  # e.g. a directory owned by another user
        log.debug("Could not tighten permissions on %s: %s", directory, exc)

    path = config_path()
    with open(path, "w") as fh:
        yaml.dump(cfg, fh)
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        log.debug("Could not tighten permissions on %s: %s", path, exc)
