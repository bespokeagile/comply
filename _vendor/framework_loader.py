"""Load compliance framework definitions from bundled YAML."""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def load_frameworks() -> Dict[str, Any]:
    """Load framework definitions from the bundled frameworks.yaml.

    Returns
    -------
    dict
        Framework ID -> framework definition dict.
    """
    import yaml

    # Try package data first
    yaml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "frameworks.yaml")
    if not os.path.isfile(yaml_path):
        # Fallback: gateway copy
        yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "gateway", "compliance", "frameworks.yaml",
        )

    if not os.path.isfile(yaml_path):
        log.warning("frameworks.yaml not found")
        return {}

    with open(yaml_path) as f:
        data = yaml.safe_load(f) or {}

    return data.get("frameworks", {})


def get_framework(framework_id: str) -> Optional[Dict[str, Any]]:
    """Get a single framework definition by ID."""
    frameworks = load_frameworks()
    # Try exact match, then with underscores
    normalised = framework_id.replace("-", "_")
    return frameworks.get(framework_id) or frameworks.get(normalised)


def get_supported_frameworks() -> List[str]:
    """Return list of supported framework IDs."""
    frameworks = load_frameworks()
    return list(frameworks.keys())


def get_framework_details() -> List[Dict[str, Any]]:
    """Return metadata for all frameworks."""
    frameworks = load_frameworks()
    result = []
    for fid, fdata in frameworks.items():
        articles = fdata.get("articles", {})
        control_count = 0
        for art_data in articles.values():
            control_count += len(art_data.get("controls", []))
        result.append({
            "id": fid,
            "framework": fid,
            "label": fdata.get("label", fid),
            "name": fdata.get("label", fid),
            "version": fdata.get("version", ""),
            "description": fdata.get("description", ""),
            "controlCount": control_count,
        })
    return result
