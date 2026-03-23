"""Cross-framework control mapping and jurisdiction profiles."""
from __future__ import annotations

from typing import Dict, List, Optional


# ── Jurisdiction profiles ──────────────────────────────────────────────
# Framework IDs use underscores (matching YAML). Normalization at boundary.

JURISDICTION_PROFILES: Dict[str, dict] = {
    "eu": {
        "label": "European Union",
        "frameworks": ["eu_ai_act", "iso_42001"],
        "description": "EU AI Act and ISO 42001 for organisations operating in the European Union.",
    },
    "us": {
        "label": "United States (General)",
        "frameworks": ["nist_ai_rmf", "soc2_ai"],
        "description": "NIST AI RMF and SOC 2 AI for general US compliance.",
    },
    "us_california": {
        "label": "California",
        "frameworks": ["california_sb_942", "california_ab_2013", "soc2_ai"],
        "description": "California SB 942, AB 2013, and SOC 2 AI for California-regulated entities.",
    },
    "us_colorado": {
        "label": "Colorado",
        "frameworks": ["colorado_sb_24_205", "nist_ai_rmf"],
        "description": "Colorado SB 24-205 and NIST AI RMF for Colorado-regulated entities.",
    },
    "insurance": {
        "label": "Insurance Industry",
        "frameworks": ["insurance_attestation", "nist_ai_rmf", "soc2_ai"],
        "description": "Insurance attestation, NIST AI RMF, and SOC 2 AI for insurance carriers.",
    },
    "global": {
        "label": "Global Enterprise",
        "frameworks": ["eu_ai_act", "nist_ai_rmf", "iso_42001", "soc2_ai"],
        "description": "Comprehensive coverage for multinational organisations.",
    },
    "security": {
        "label": "AI Security",
        "frameworks": ["owasp_llm_top10", "owasp_agentic_top10", "nist_ai_rmf"],
        "description": "OWASP LLM Top 10, Agentic Top 10, and NIST AI RMF for AI security posture.",
    },
}


def get_jurisdiction_profiles() -> List[dict]:
    """Return all jurisdiction profiles with metadata."""
    result = []
    for pid, profile in JURISDICTION_PROFILES.items():
        result.append({
            "id": pid,
            "label": profile["label"],
            "description": profile["description"],
            "frameworks": profile["frameworks"],
            "frameworkCount": len(profile["frameworks"]),
        })
    return result


def get_jurisdiction(profile_id: str) -> Optional[dict]:
    """Return a single jurisdiction profile or None."""
    profile = JURISDICTION_PROFILES.get(profile_id)
    if profile is None:
        return None
    return {
        "id": profile_id,
        "label": profile["label"],
        "description": profile["description"],
        "frameworks": profile["frameworks"],
        "frameworkCount": len(profile["frameworks"]),
    }


def resolve_frameworks(framework_or_jurisdiction: str) -> List[str]:
    """Resolve a string to a list of framework IDs.

    If it matches a jurisdiction profile, returns that profile's framework list.
    Otherwise returns the input as a single-element list (with dash→underscore
    normalization).
    """
    profile = JURISDICTION_PROFILES.get(framework_or_jurisdiction)
    if profile is not None:
        return list(profile["frameworks"])
    # Not a jurisdiction — treat as a framework ID
    return [framework_or_jurisdiction.replace("-", "_")]


# ── Control mapping ────────────────────────────────────────────────────

def build_control_mapping(framework_ids: Optional[List[str]] = None) -> dict:
    """Build the evidence_fn → controls mapping from framework YAML definitions.

    No scan data needed — this is purely structural.

    Parameters
    ----------
    framework_ids : list of str, optional
        Specific framework IDs to include. None means all frameworks.

    Returns
    -------
    dict
        {capabilities, frameworks, totalCapabilities, totalControls}
    """
    from comply._vendor.framework_loader import load_frameworks
    from comply.report import CAPABILITY_NAMES

    all_frameworks = load_frameworks()

    if framework_ids is not None:
        # Normalise IDs (dashes → underscores) and filter
        normalised = [fid.replace("-", "_") for fid in framework_ids]
        selected = {
            fid: fdata for fid, fdata in all_frameworks.items()
            if fid in normalised
        }
    else:
        selected = all_frameworks

    # Group controls by evidence_fn
    capability_map = {}  # evidence_fn -> {name, evidence_fn, controls}
    total_controls = 0
    framework_list = []

    for fid, fdata in selected.items():
        framework_list.append(fid)
        articles = fdata.get("articles", {})
        # articles can be dict (keyed by article ID) or list
        if isinstance(articles, dict):
            articles_iter = articles.values()
        else:
            articles_iter = articles

        for article in articles_iter:
            for ctrl in article.get("controls", []):
                evidence_fn = ctrl.get("evidence_fn", "")
                if not evidence_fn:
                    continue
                total_controls += 1
                if evidence_fn not in capability_map:
                    name = CAPABILITY_NAMES.get(
                        evidence_fn,
                        evidence_fn.replace("evidence_", "").replace("_", " ").title(),
                    )
                    capability_map[evidence_fn] = {
                        "name": name,
                        "evidence_fn": evidence_fn,
                        "controls": [],
                    }
                capability_map[evidence_fn]["controls"].append({
                    "framework": fid,
                    "controlId": ctrl.get("id", ""),
                    "requirement": ctrl.get("requirement", ""),
                })

    # Add framework_count to each capability
    capabilities = []
    for cap in sorted(capability_map.values(), key=lambda c: c["name"]):
        fw_set = {c["framework"] for c in cap["controls"]}
        cap["framework_count"] = len(fw_set)
        capabilities.append(cap)

    return {
        "capabilities": capabilities,
        "frameworks": framework_list,
        "totalCapabilities": len(capabilities),
        "totalControls": total_controls,
    }


def get_capability_detail(evidence_fn: str) -> Optional[dict]:
    """Return detail for one capability (evidence function) across all frameworks."""
    mapping = build_control_mapping()
    for cap in mapping["capabilities"]:
        if cap["evidence_fn"] == evidence_fn:
            return cap
    return None


def get_remediation_priorities(scan_reports: List[dict]) -> List[dict]:
    """Find evidence functions that are gap/partial across multiple frameworks.

    Returns a sorted list of priorities: fixing one capability improves N frameworks.
    """
    from comply.report import CAPABILITY_NAMES

    # Collect gaps/partials grouped by evidence_fn
    fn_impacts = {}  # evidence_fn -> {frameworks: set, controls: list}

    for report in scan_reports:
        fw = report.get("framework", "")
        for article in report.get("articles", []):
            for ctrl in article.get("controls", []):
                status = ctrl.get("status", "gap")
                if status == "met":
                    continue
                evidence_fn = ctrl.get("evidence_fn", "")
                if not evidence_fn:
                    continue
                if evidence_fn not in fn_impacts:
                    fn_impacts[evidence_fn] = {"frameworks": set(), "controls": []}
                fn_impacts[evidence_fn]["frameworks"].add(fw)
                fn_impacts[evidence_fn]["controls"].append({
                    "framework": fw,
                    "controlId": ctrl.get("controlId", ""),
                    "status": status,
                    "requirement": ctrl.get("requirement", "")[:120],
                })

    # Build priority list sorted by impact_count desc
    priorities = []
    for evidence_fn, data in fn_impacts.items():
        name = CAPABILITY_NAMES.get(
            evidence_fn,
            evidence_fn.replace("evidence_", "").replace("_", " ").title(),
        )
        priorities.append({
            "evidence_fn": evidence_fn,
            "name": name,
            "impact_count": len(data["frameworks"]),
            "frameworks": sorted(data["frameworks"]),
            "controls": data["controls"],
        })

    priorities.sort(key=lambda p: (-p["impact_count"], p["name"]))
    return priorities
