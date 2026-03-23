"""SARIF v2.1.0 import: parse security tool findings for compliance mapping."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Regex to extract CWE identifiers (e.g. "CWE-79", "cwe-116")
_CWE_RE = re.compile(r"CWE-(\d+)", re.IGNORECASE)


@dataclass
class Finding:
    """A single security finding extracted from SARIF."""

    tool: str
    rule_id: str
    level: str  # error, warning, note, none
    message: str
    cwes: List[str] = field(default_factory=list)  # e.g. ["CWE-79", "CWE-116"]
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    snippet: Optional[str] = None


# ── Public API ────────────────────────────────────────────────────────


def parse_sarif(data: Dict[str, Any]) -> List[Finding]:
    """Parse a SARIF v2.1.0 dict and return extracted findings.

    Parameters
    ----------
    data : dict
        Parsed SARIF JSON (top-level object with ``$schema``, ``version``,
        ``runs``).

    Returns
    -------
    list of Finding
        One Finding per result entry across all runs.
    """
    version = data.get("version", "")
    if version and not version.startswith("2.1"):
        log.warning("SARIF version %s may not be fully supported", version)

    findings: List[Finding] = []
    for run in data.get("runs", []):
        tool_name = _extract_tool_name(run)
        rule_index = _build_rule_index(run)
        taxonomies = _build_taxonomy_index(run)

        for result in run.get("results", []):
            finding = _parse_result(result, tool_name, rule_index, taxonomies)
            if finding is not None:
                findings.append(finding)

    log.info(
        "Parsed %d finding(s) from SARIF (%d run(s))",
        len(findings),
        len(data.get("runs", [])),
    )
    return findings


def parse_sarif_file(path: Path) -> List[Finding]:
    """Convenience wrapper: read a SARIF JSON file and parse it.

    Parameters
    ----------
    path : Path
        Path to a ``.sarif`` or ``.json`` file.

    Returns
    -------
    list of Finding
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return parse_sarif(data)


# ── Internal helpers ──────────────────────────────────────────────────


def _extract_tool_name(run: Dict[str, Any]) -> str:
    """Return the tool driver name from a SARIF run, or 'unknown'."""
    tool = run.get("tool", {})
    driver = tool.get("driver", {})
    return driver.get("name", "unknown")


def _build_rule_index(run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a lookup from rule ID to rule descriptor.

    Checks both ``tool.driver.rules`` and ``tool.extensions[].rules``.
    """
    index: Dict[str, Dict[str, Any]] = {}
    driver = run.get("tool", {}).get("driver", {})
    for rule in driver.get("rules", []):
        rid = rule.get("id", "")
        if rid:
            index[rid] = rule

    # Some tools (e.g. CodeQL) put rules in extensions
    for ext in run.get("tool", {}).get("extensions", []):
        for rule in ext.get("rules", []):
            rid = rule.get("id", "")
            if rid:
                index.setdefault(rid, rule)

    return index


def _build_taxonomy_index(run: Dict[str, Any]) -> Dict[str, List[str]]:
    """Build a mapping from rule ID to CWE IDs via SARIF taxonomies.

    SARIF spec-compliant tools express CWE references through
    ``rule.relationships[].target`` where the target references a taxonomy
    entry whose ``id`` contains the CWE number.
    """
    # First build taxonomy ID -> CWE mapping
    taxon_map: Dict[str, str] = {}  # taxonomy guid/name + taxon id -> CWE-xxx
    for taxonomy in run.get("taxonomies", []):
        tax_name = taxonomy.get("name", "")
        for taxon in taxonomy.get("taxa", []):
            taxon_id = taxon.get("id", "")
            # Taxon IDs are typically the CWE number (e.g. "79")
            match = _CWE_RE.search(taxon_id)
            if match:
                taxon_map[taxon_id] = f"CWE-{match.group(1)}"
            elif taxon_id.isdigit():
                # Bare number — assume CWE
                taxon_map[taxon_id] = f"CWE-{taxon_id}"
            # Also check the taxon name
            if not match:
                match = _CWE_RE.search(taxon.get("name", ""))
                if match:
                    taxon_map[taxon_id] = f"CWE-{match.group(1)}"

    # Now map rule IDs to CWEs via relationships
    rule_cwes: Dict[str, List[str]] = {}
    driver = run.get("tool", {}).get("driver", {})
    for rule in driver.get("rules", []):
        rid = rule.get("id", "")
        cwes = _cwes_from_relationships(rule, taxon_map)
        if cwes:
            rule_cwes[rid] = cwes

    for ext in run.get("tool", {}).get("extensions", []):
        for rule in ext.get("rules", []):
            rid = rule.get("id", "")
            cwes = _cwes_from_relationships(rule, taxon_map)
            if cwes and rid not in rule_cwes:
                rule_cwes[rid] = cwes

    return rule_cwes


def _cwes_from_relationships(
    rule: Dict[str, Any],
    taxon_map: Dict[str, str],
) -> List[str]:
    """Extract CWE IDs from rule.relationships[].target."""
    cwes: List[str] = []
    for rel in rule.get("relationships", []):
        target = rel.get("target", {})
        target_id = target.get("id", "")
        if target_id in taxon_map:
            cwes.append(taxon_map[target_id])
        else:
            # Try regex on the target ID directly
            match = _CWE_RE.search(target_id)
            if match:
                cwes.append(f"CWE-{match.group(1)}")
    return _dedupe(cwes)


def _extract_cwes(
    rule: Optional[Dict[str, Any]],
    result: Dict[str, Any],
    taxonomy_cwes: Dict[str, List[str]],
) -> List[str]:
    """Extract CWE IDs from all three locations.

    1. SARIF taxonomies (spec-compliant: pre-built in taxonomy_cwes).
    2. Properties tags (Semgrep convention: ``rule.properties.tags``
       containing items like ``"CWE-79: ..."``).
    3. Result-level properties (some tools put CWEs on results).
    """
    cwes: List[str] = []

    rule_id = result.get("ruleId", "")

    # 1. Taxonomy-derived CWEs (already resolved by _build_taxonomy_index)
    if rule_id in taxonomy_cwes:
        cwes.extend(taxonomy_cwes[rule_id])

    # 2. Rule properties tags (Semgrep, Bandit, etc.)
    if rule is not None:
        props = rule.get("properties", {})
        tags = props.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str):
                    match = _CWE_RE.search(tag)
                    if match:
                        cwes.append(f"CWE-{match.group(1)}")
        # Some tools put CWE directly in properties.cwe
        cwe_prop = props.get("cwe", props.get("CWE", ""))
        if isinstance(cwe_prop, str) and cwe_prop:
            match = _CWE_RE.search(cwe_prop)
            if match:
                cwes.append(f"CWE-{match.group(1)}")
        elif isinstance(cwe_prop, list):
            for item in cwe_prop:
                if isinstance(item, str):
                    match = _CWE_RE.search(item)
                    if match:
                        cwes.append(f"CWE-{match.group(1)}")

    # 3. Result-level properties
    result_props = result.get("properties", {})
    result_tags = result_props.get("tags", [])
    if isinstance(result_tags, list):
        for tag in result_tags:
            if isinstance(tag, str):
                match = _CWE_RE.search(tag)
                if match:
                    cwes.append(f"CWE-{match.group(1)}")
    result_cwe = result_props.get("cwe", result_props.get("CWE", ""))
    if isinstance(result_cwe, str) and result_cwe:
        match = _CWE_RE.search(result_cwe)
        if match:
            cwes.append(f"CWE-{match.group(1)}")
    elif isinstance(result_cwe, list):
        for item in result_cwe:
            if isinstance(item, str):
                match = _CWE_RE.search(item)
                if match:
                    cwes.append(f"CWE-{match.group(1)}")

    return _dedupe(cwes)


def _extract_location(result: Dict[str, Any]) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[str]]:
    """Extract file path, start line, end line, and snippet from a result.

    Returns
    -------
    tuple
        (file_path, start_line, end_line, snippet) — any may be None.
    """
    locations = result.get("locations", [])
    if not locations:
        return None, None, None, None

    loc = locations[0]
    phys = loc.get("physicalLocation", {})
    artifact = phys.get("artifactLocation", {})
    file_path = artifact.get("uri", artifact.get("uriBaseId"))

    region = phys.get("region", {})
    start_line = region.get("startLine")
    end_line = region.get("endLine")

    snippet = None
    snippet_obj = region.get("snippet", {})
    if isinstance(snippet_obj, dict):
        snippet = snippet_obj.get("text")

    return file_path, start_line, end_line, snippet


def _extract_message(result: Dict[str, Any]) -> str:
    """Extract the human-readable message from a result."""
    msg = result.get("message", {})
    if isinstance(msg, dict):
        return msg.get("text", msg.get("markdown", ""))
    if isinstance(msg, str):
        return msg
    return ""


def _parse_result(
    result: Dict[str, Any],
    tool_name: str,
    rule_index: Dict[str, Dict[str, Any]],
    taxonomy_cwes: Dict[str, List[str]],
) -> Optional[Finding]:
    """Parse a single SARIF result into a Finding."""
    rule_id = result.get("ruleId", "")
    if not rule_id:
        # Some tools use ruleIndex instead of ruleId
        rule_idx = result.get("ruleIndex")
        if rule_idx is not None:
            # Try to resolve from the rule_index keys by position —
            # not reliable, but better than nothing
            keys = list(rule_index.keys())
            if 0 <= rule_idx < len(keys):
                rule_id = keys[rule_idx]

    rule = rule_index.get(rule_id)
    level = result.get("level", "warning")
    message = _extract_message(result)
    cwes = _extract_cwes(rule, result, taxonomy_cwes)
    file_path, start_line, end_line, snippet = _extract_location(result)

    return Finding(
        tool=tool_name,
        rule_id=rule_id,
        level=level,
        message=message,
        cwes=cwes,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        snippet=snippet,
    )


def _dedupe(items: List[str]) -> List[str]:
    """Remove duplicates while preserving order."""
    seen: set = set()
    out: List[str] = []
    for item in items:
        normalised = item.upper()
        if normalised not in seen:
            seen.add(normalised)
            out.append(item.upper())  # Normalize to uppercase CWE-XXX
    return out
