"""Adapter registry — discovers, registers, and manages audit log adapters."""
from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from comply.adapters.base import AuditLogAdapter

log = logging.getLogger(__name__)

_REGISTRY: Dict[str, Type[AuditLogAdapter]] = {}
_INSTANCES: Dict[str, AuditLogAdapter] = {}


def register_adapter(name: str, cls: Type[AuditLogAdapter]) -> None:
    """Register an adapter class by name."""
    _REGISTRY[name] = cls


def get_adapter(name: str) -> Optional[AuditLogAdapter]:
    """Return a configured adapter instance, or None if unknown."""
    return _INSTANCES.get(name)


def list_adapters() -> list:
    """Return metadata for all registered adapters."""
    result = []
    for name, cls in _REGISTRY.items():
        instance = _INSTANCES.get(name)
        status = instance.get_adapter_status() if instance else {"name": name, "connected": False, "last_fetch": ""}
        status["registered"] = True
        status["configured"] = instance is not None
        result.append(status)
    return result


def configure_adapter(name: str, config: dict) -> AuditLogAdapter:
    """Create, configure, and cache an adapter instance."""
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown adapter: {name}. Registered: {list(_REGISTRY.keys())}")
    instance = cls()
    instance.configure(config)
    _INSTANCES[name] = instance
    return instance


def auto_configure_from_config() -> None:
    """Load adapter configs from ~/.comply/config.yaml and configure them."""
    import os
    import yaml

    config_path = os.path.expanduser("~/.comply/config.yaml")
    if not os.path.isfile(config_path):
        return

    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning("Failed to load adapter config: %s", exc)
        return

    adapters_cfg = cfg.get("adapters", {})
    for name, adapter_cfg in adapters_cfg.items():
        if name in _REGISTRY:
            try:
                configure_adapter(name, adapter_cfg or {})
                log.info("Configured adapter: %s", name)
            except Exception as exc:
                log.warning("Failed to configure adapter %s: %s", name, exc)


def _auto_register_builtins() -> None:
    """Register all built-in adapters."""
    try:
        from comply.adapters.gateway_adapter import GatewayAdapter
        register_adapter("gateway", GatewayAdapter)
    except ImportError:
        pass

    try:
        from comply.adapters.kong_adapter import KongAdapter
        register_adapter("kong", KongAdapter)
    except ImportError:
        pass

    try:
        from comply.adapters.gravitee_adapter import GraviteeAdapter
        register_adapter("gravitee", GraviteeAdapter)
    except ImportError:
        pass

    try:
        from comply.adapters.file_adapter import FileAdapter
        register_adapter("file", FileAdapter)
    except ImportError:
        pass

    try:
        from comply.adapters.vanta_adapter import VantaAdapter
        register_adapter("vanta", VantaAdapter)
    except ImportError:
        pass

    try:
        from comply.adapters.github_actions import GitHubActionsAdapter
        register_adapter("github_actions", GitHubActionsAdapter)
    except ImportError:
        pass

    try:
        from comply.adapters.gitlab_ci import GitLabCIAdapter
        register_adapter("gitlab_ci", GitLabCIAdapter)
    except ImportError:
        pass


# Auto-register on import
_auto_register_builtins()
