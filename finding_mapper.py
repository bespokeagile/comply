"""Map security findings to compliance controls via CWE classification."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from comply.sarif_import import Finding

log = logging.getLogger(__name__)

# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class ControlMapping:
    """Maps a CWE to a specific compliance control."""

    framework: str
    control_id: str
    cwe: str
    strength: str  # direct, indirect, contributing
    rationale: str


@dataclass
class ArchitecturalEnrichment:
    """Graph-derived architectural importance for a finding's file."""

    architectural_severity: str  # "high", "medium", "low", "unknown"
    pagerank: float = 0.0
    betweenness: float = 0.0
    module_boundary: float = 0.0
    in_degree: float = 0.0
    composite_score: float = 0.0  # weighted combination


@dataclass
class MappedFinding:
    """A finding mapped to compliance controls."""

    finding: Finding
    control_mappings: List[ControlMapping] = field(default_factory=list)
    enrichment: Optional[ArchitecturalEnrichment] = None
    effective_level: Optional[str] = None  # overridden level when arch weighting applies


# ── Mapping cache ─────────────────────────────────────────────────────

_CWE_MAPPING_CACHE: Optional[Dict[str, Any]] = None
_MAPPING_FILE = Path(__file__).parent / "data" / "cwe_control_mapping.yaml"


def load_cwe_mapping(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and cache the CWE-to-control mapping YAML.

    The YAML structure is expected to be::

        cwe_mappings:
          CWE-79:
            name: "Cross-site Scripting (XSS)"
            controls:
              - framework: owasp_llm_top10
                control_id: "LLM02"
                strength: direct
                rationale: "XSS is a direct injection vulnerability."
              - framework: soc2_ai
                control_id: "CC6.1"
                strength: indirect
                rationale: "Relates to logical access security."
          CWE-89:
            ...

    Parameters
    ----------
    path : Path, optional
        Override the default mapping file location.

    Returns
    -------
    dict
        The full mapping dict keyed by CWE ID (e.g. ``"CWE-79"``).
    """
    global _CWE_MAPPING_CACHE

    if _CWE_MAPPING_CACHE is not None and path is None:
        return _CWE_MAPPING_CACHE

    mapping_path = path or _MAPPING_FILE
    if not mapping_path.exists():
        log.warning("CWE mapping file not found: %s", mapping_path)
        return {}

    with open(mapping_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        return {}

    # Support both formats:
    # Format A (flat):  cwe_mappings: { CWE-79: { controls: [{framework, control_id}] } }
    # Format B (nested): mappings: { CWE-79: { frameworks: { eu_ai_act: [{controlId}] } } }
    raw_mappings = raw.get("cwe_mappings") or raw.get("mappings", {})

    mapping: Dict[str, Any] = {}
    for cwe_id, entry in raw_mappings.items():
        if not isinstance(entry, dict):
            continue
        # Normalise to flat controls list
        if "controls" in entry:
            # Format A — already flat
            mapping[cwe_id] = entry
        elif "frameworks" in entry:
            # Format B — nested by framework, flatten
            controls = []
            for fw_id, fw_controls in entry.get("frameworks", {}).items():
                if not isinstance(fw_controls, list):
                    continue
                for ctrl in fw_controls:
                    controls.append({
                        "framework": fw_id,
                        "control_id": ctrl.get("controlId", ctrl.get("control_id", "")),
                        "strength": ctrl.get("strength", "indirect"),
                        "rationale": ctrl.get("rationale", ""),
                    })
            mapping[cwe_id] = {
                "name": entry.get("name", ""),
                "owasp_top10": entry.get("owasp_top10", ""),
                "controls": controls,
            }
        else:
            mapping[cwe_id] = entry

    if path is None:
        _CWE_MAPPING_CACHE = mapping
    log.info("Loaded CWE mapping with %d entries", len(mapping))
    return mapping


# ── Architectural enrichment ──────────────────────────────────────────


def compute_architectural_severity(
    graph_metrics: Dict[str, Dict[str, float]],
    file_path: str,
) -> ArchitecturalEnrichment:
    """Compute architectural severity for a file based on graph centrality.

    Composite = 0.35*PageRank + 0.35*betweenness + 0.20*module_boundary + 0.10*in_degree.
    High >= 0.6, medium >= 0.3, low < 0.3, unknown if file not in graph.
    """
    # Normalise path: strip leading ./ and try basename fallback
    clean = (file_path or "").lstrip("./")
    metrics = graph_metrics.get(clean)
    if not metrics:
        # Try basename match (SARIF may use absolute/different paths)
        import os
        basename = os.path.basename(clean)
        for gpath, gmetrics in graph_metrics.items():
            if os.path.basename(gpath) == basename:
                metrics = gmetrics
                break
    if not metrics:
        return ArchitecturalEnrichment(architectural_severity="unknown")

    pr = metrics.get("pagerank", 0.0)
    bc = metrics.get("betweenness", 0.0)
    mb = metrics.get("module_boundary", 0.0)
    ind = metrics.get("in_degree", 0.0)

    composite = 0.35 * pr + 0.35 * bc + 0.20 * mb + 0.10 * ind

    if composite >= 0.6:
        sev = "high"
    elif composite >= 0.3:
        sev = "medium"
    else:
        sev = "low"

    return ArchitecturalEnrichment(
        architectural_severity=sev,
        pagerank=round(pr, 4),
        betweenness=round(bc, 4),
        module_boundary=round(mb, 4),
        in_degree=round(ind, 4),
        composite_score=round(composite, 4),
    )


# ── Public API ────────────────────────────────────────────────────────


def map_findings(
    findings: List[Finding],
    framework: str,
    mapping_path: Optional[Path] = None,
    graph_metrics: Optional[Dict[str, Dict[str, float]]] = None,
    architectural_weighting: bool = True,
) -> List[MappedFinding]:
    """Map parsed findings to compliance controls for a given framework.

    Only controls belonging to *framework* are included in the output.
    Findings with no CWEs or no matching controls are still returned
    (with an empty ``control_mappings`` list) so callers can report
    unmapped findings.

    Parameters
    ----------
    findings : list of Finding
        Output from ``sarif_import.parse_sarif()``.
    framework : str
        Framework ID to filter controls (e.g. ``"owasp_llm_top10"``).
        Uses underscore-normalised IDs.
    mapping_path : Path, optional
        Override the default mapping file location.

    Returns
    -------
    list of MappedFinding
    """
    cwe_map = load_cwe_mapping(mapping_path)
    normalised_fw = framework.replace("-", "_")

    mapped: List[MappedFinding] = []
    for finding in findings:
        control_mappings: List[ControlMapping] = []
        for cwe in finding.cwes:
            cwe_key = cwe.upper()
            entry = cwe_map.get(cwe_key, {})
            controls = entry.get("controls", [])
            for ctrl in controls:
                ctrl_fw = ctrl.get("framework", "").replace("-", "_")
                if ctrl_fw == normalised_fw:
                    control_mappings.append(ControlMapping(
                        framework=ctrl_fw,
                        control_id=ctrl.get("control_id", ""),
                        cwe=cwe_key,
                        strength=ctrl.get("strength", "indirect"),
                        rationale=ctrl.get("rationale", ""),
                    ))

        # Compute architectural enrichment if graph metrics available
        enrichment = None
        if graph_metrics and finding.file_path:
            enrichment = compute_architectural_severity(graph_metrics, finding.file_path)

        # Determine effective level: upgrade warning→error in high-centrality files
        effective_level = finding.level
        if (architectural_weighting and enrichment
                and enrichment.architectural_severity == "high"
                and finding.level == "warning"):
            effective_level = "error"

        mapped.append(MappedFinding(
            finding=finding,
            control_mappings=control_mappings,
            enrichment=enrichment,
            effective_level=effective_level,
        ))

    total_mappings = sum(len(m.control_mappings) for m in mapped)
    log.info(
        "Mapped %d finding(s) -> %d control mapping(s) for framework %s",
        len(findings),
        total_mappings,
        framework,
    )
    return mapped


def generate_import_report(
    mapped: List[MappedFinding],
    framework: str,
    source_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a compliance report section from security findings alone.

    The report mirrors the Comply scan report structure so it can be
    merged with ``merge_reports()``.

    Returns
    -------
    dict
        Report dict with keys: ``framework``, ``source``, ``summary``,
        ``controls``, ``findings``.
    """
    normalised_fw = framework.replace("-", "_")

    # Aggregate control statuses from findings
    # Key: control_id -> {status, findings, cwes}
    control_status: Dict[str, Dict[str, Any]] = {}

    for mf in mapped:
        for cm in mf.control_mappings:
            if cm.framework != normalised_fw:
                continue
            cid = cm.control_id
            if cid not in control_status:
                control_status[cid] = {
                    "controlId": cid,
                    "status": "met",  # will be downgraded
                    "findings": [],
                    "cwes": set(),
                    "strength": cm.strength,
                }
            entry = control_status[cid]
            entry["cwes"].add(cm.cwe)
            finding_entry = {
                "tool": mf.finding.tool,
                "rule_id": mf.finding.rule_id,
                "level": mf.finding.level,
                "message": mf.finding.message[:200],
                "file_path": mf.finding.file_path,
                "start_line": mf.finding.start_line,
                "cwe": cm.cwe,
            }
            if mf.enrichment and mf.enrichment.architectural_severity != "unknown":
                finding_entry["architectural_severity"] = mf.enrichment.architectural_severity
                finding_entry["composite_score"] = mf.enrichment.composite_score
            if mf.effective_level and mf.effective_level != mf.finding.level:
                finding_entry["effective_level"] = mf.effective_level
                finding_entry["level_upgraded"] = True
            entry["findings"].append(finding_entry)
            # Downgrade status using effective level (arch-weighted)
            level_for_downgrade = mf.effective_level or mf.finding.level
            entry["status"] = _downgrade_status(
                entry["status"], level_for_downgrade, cm.strength
            )

    # Convert sets to sorted lists for JSON serialisation
    controls_list: List[Dict[str, Any]] = []
    for cid, entry in sorted(control_status.items()):
        controls_list.append({
            "controlId": entry["controlId"],
            "status": entry["status"],
            "source": "security_import",
            "cwes": sorted(entry["cwes"]),
            "findingCount": len(entry["findings"]),
            "findings": entry["findings"],
            "strength": entry["strength"],
        })

    # Summary counts
    met = sum(1 for c in controls_list if c["status"] == "met")
    partial = sum(1 for c in controls_list if c["status"] == "partial")
    gap = sum(1 for c in controls_list if c["status"] == "gap")
    total = len(controls_list)
    score = round((met + 0.5 * partial) / total * 100, 1) if total else 100.0

    # Unmapped findings (no control mappings)
    unmapped = [
        {
            "tool": mf.finding.tool,
            "rule_id": mf.finding.rule_id,
            "level": mf.finding.level,
            "message": mf.finding.message[:200],
            "cwes": mf.finding.cwes,
            "file_path": mf.finding.file_path,
        }
        for mf in mapped
        if not mf.control_mappings
    ]

    report: Dict[str, Any] = {
        "framework": normalised_fw,
        "source": "sarif_import",
        "summary": {
            "met": met,
            "partial": partial,
            "gap": gap,
            "total": total,
            "score": score,
        },
        "securityFindings": controls_list,
        "unmappedFindings": unmapped,
        "totalFindings": len(mapped),
        "toolsUsed": sorted({mf.finding.tool for mf in mapped}),
    }
    if source_file:
        report["sourceFile"] = str(source_file)

    # Architectural enrichment summary
    enriched_count = sum(
        1 for mf in mapped
        if mf.enrichment and mf.enrichment.architectural_severity != "unknown"
    )
    upgraded_count = sum(
        1 for mf in mapped
        if mf.effective_level and mf.effective_level != mf.finding.level
    )
    if enriched_count > 0:
        severity_dist = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        for mf in mapped:
            if mf.enrichment:
                severity_dist[mf.enrichment.architectural_severity] += 1
        report["architecturalEnrichment"] = {
            "enabled": True,
            "enrichedFindings": enriched_count,
            "upgradedFindings": upgraded_count,
            "severityDistribution": severity_dist,
        }

    # Also produce an articles-style structure for format compatibility
    # Group controls by a synthetic article
    if controls_list:
        report["articles"] = [{
            "articleId": "security_findings",
            "label": "Security Findings (Imported)",
            "met": met,
            "partial": partial,
            "gap": gap,
            "controls": [
                {
                    "controlId": c["controlId"],
                    "status": c["status"],
                    "requirement": f"CWE {', '.join(c['cwes'])}: no {c['status']} findings",
                    "recommendation": f"Fix {c['findingCount']} finding(s)",
                    "evidence": [f"{f['tool']}: {f['message']}" for f in c["findings"][:3]],
                    "gaps": [f"{f['tool']}: {f['message']}" for f in c["findings"][:3]]
                    if c["status"] in ("gap", "partial") else [],
                    "evidence_fn": "security_import",
                }
                for c in controls_list
            ],
        }]

    return report


def merge_reports(
    comply_report: Dict[str, Any],
    import_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a Comply scan report with an imported security findings report.

    Merge logic: imported findings can DOWNGRADE a control's status (a
    security gap found overrides a compliance pass) but never UPGRADE it.
    The combined status is ``min(comply_status, security_status)`` using
    the ordering ``met=2, partial=1, gap=0``.

    Parameters
    ----------
    comply_report : dict
        Standard Comply scan report (with ``articles[].controls[]``).
    import_report : dict
        Report from ``generate_import_report()``.

    Returns
    -------
    dict
        A new report dict with merged statuses and annotated controls.
        The original dicts are not modified.
    """
    import copy

    merged = copy.deepcopy(comply_report)

    # Index imported controls by control_id for O(1) lookup
    imported_controls: Dict[str, Dict[str, Any]] = {}
    for ctrl in import_report.get("controls", []):
        cid = ctrl.get("controlId", "")
        if cid:
            imported_controls[cid] = ctrl

    if not imported_controls:
        # Nothing to merge — annotate and return
        merged["securityImport"] = {
            "merged": False,
            "reason": "no_matching_controls",
            "unmappedFindings": import_report.get("unmappedFindings", []),
        }
        return merged

    # Walk the Comply report and merge
    merged_count = 0
    downgraded_count = 0

    for article in merged.get("articles", []):
        for ctrl in article.get("controls", []):
            cid = ctrl.get("controlId", "")
            if cid not in imported_controls:
                continue

            imp = imported_controls[cid]
            comply_val = _status_value(ctrl.get("status", "gap"))
            import_val = _status_value(imp.get("status", "gap"))

            merged_count += 1

            # Take the worse (lower) status
            if import_val < comply_val:
                ctrl["status"] = _status_from_value(import_val)
                ctrl["statusOverriddenBy"] = "security_import"
                ctrl["originalStatus"] = _status_from_value(comply_val)
                downgraded_count += 1

            # Annotate the control with security findings regardless
            ctrl["securityFindings"] = imp.get("findings", [])
            ctrl["securityCwes"] = imp.get("cwes", [])
            ctrl["securityFindingCount"] = imp.get("findingCount", 0)

    # Recalculate summary after merging
    _recalculate_summary(merged)

    # Add merge metadata
    merged["securityImport"] = {
        "merged": True,
        "controlsMatched": merged_count,
        "controlsDowngraded": downgraded_count,
        "toolsUsed": import_report.get("toolsUsed", []),
        "totalFindings": import_report.get("totalFindings", 0),
        "unmappedFindings": import_report.get("unmappedFindings", []),
    }

    return merged


# ── Internal helpers ──────────────────────────────────────────────────


def _status_value(status: str) -> int:
    """Convert status string to numeric value for comparison.

    met=2, partial=1, gap=0.
    """
    return {"met": 2, "partial": 1, "gap": 0}.get(status, 0)


def _status_from_value(value: int) -> str:
    """Convert numeric value back to status string."""
    return {2: "met", 1: "partial", 0: "gap"}.get(value, "gap")


def _downgrade_status(current: str, level: str, strength: str) -> str:
    """Determine control status based on finding severity and mapping strength.

    Rules:
    - ``error`` + ``direct`` mapping -> ``gap``
    - ``error`` + ``indirect``/``contributing`` -> ``partial``
    - ``warning`` + ``direct`` -> ``partial``
    - ``warning`` + ``indirect``/``contributing`` -> keep current (informational)
    - ``note``/``none`` -> keep current
    """
    if level == "error":
        if strength == "direct":
            target = "gap"
        else:
            target = "partial"
    elif level == "warning":
        if strength == "direct":
            target = "partial"
        else:
            return current
    else:
        # note, none — informational, don't downgrade
        return current

    # Only downgrade, never upgrade
    if _status_value(target) < _status_value(current):
        return target
    return current


def _recalculate_summary(report: Dict[str, Any]) -> None:
    """Recalculate the summary counts after merging.

    Mutates the report dict in-place.
    """
    met = 0
    partial = 0
    gap = 0
    total = 0

    for article in report.get("articles", []):
        art_met = 0
        art_partial = 0
        art_gap = 0

        for ctrl in article.get("controls", []):
            status = ctrl.get("status", "gap")
            total += 1
            if status == "met":
                art_met += 1
                met += 1
            elif status == "partial":
                art_partial += 1
                partial += 1
            else:
                art_gap += 1
                gap += 1

        # Update per-article counts
        article["met"] = art_met
        article["partial"] = art_partial
        article["gap"] = art_gap

    score = round((met + 0.5 * partial) / total * 100, 1) if total else 0.0
    report["summary"] = {
        "met": met,
        "partial": partial,
        "gap": gap,
        "total": total,
        "score": score,
    }
