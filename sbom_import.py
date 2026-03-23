"""SBOM (CycloneDX + SPDX) parser for compliance mapping."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

CWE_RE = re.compile(r"CWE-(\d+)", re.IGNORECASE)

# AI/ML package indicators for supply chain analysis
AI_PACKAGES = {
    "langchain", "openai", "anthropic", "transformers", "torch", "pytorch",
    "tensorflow", "keras", "scikit-learn", "sklearn", "numpy", "pandas",
    "huggingface", "sentence-transformers", "tiktoken", "chromadb", "pinecone",
    "weaviate", "qdrant", "faiss", "llamaindex", "llama-index", "autogen",
    "crewai", "dspy", "vllm", "ollama", "litellm", "guidance", "outlines",
    "mlflow", "wandb", "comet", "neptune", "ray", "dask", "xgboost",
    "lightgbm", "catboost", "spacy", "nltk", "gensim", "fasttext",
}


@dataclass
class Vulnerability:
    """A known vulnerability in a component."""
    id: str              # CVE-2024-1234 or GHSA-xxx
    severity: str = ""   # critical, high, medium, low, unknown
    score: float = 0.0   # CVSS score
    cwes: List[str] = field(default_factory=list)
    source: str = ""


@dataclass
class Component:
    """A software component from an SBOM."""
    name: str
    version: str
    purl: Optional[str] = None
    component_type: str = "library"
    licenses: List[str] = field(default_factory=list)
    supplier: Optional[str] = None
    scope: str = "required"
    vulnerabilities: List[Vulnerability] = field(default_factory=list)

    @property
    def is_ai_package(self) -> bool:
        name_lower = self.name.lower().replace("-", "").replace("_", "")
        return any(
            ai.replace("-", "").replace("_", "") in name_lower
            for ai in AI_PACKAGES
        )


@dataclass
class SBOM:
    """Parsed SBOM with components and metadata."""
    format: str          # "cyclonedx" or "spdx"
    spec_version: str
    components: List[Component] = field(default_factory=list)
    timestamp: Optional[str] = None
    tool_name: Optional[str] = None


def parse_sbom(data: Dict[str, Any]) -> SBOM:
    """Auto-detect SBOM format and parse.

    Supports CycloneDX JSON and SPDX JSON.
    """
    if data.get("bomFormat") == "CycloneDX" or "specVersion" in data:
        return _parse_cyclonedx(data)
    if data.get("spdxVersion") or "packages" in data:
        return _parse_spdx(data)
    if data.get("components"):
        # Ambiguous but has components — try CycloneDX
        return _parse_cyclonedx(data)
    raise ValueError("Unrecognised SBOM format. Expected CycloneDX or SPDX JSON.")


def _parse_cyclonedx(data: Dict[str, Any]) -> SBOM:
    """Parse CycloneDX JSON SBOM."""
    spec_version = data.get("specVersion", "unknown")
    metadata = data.get("metadata", {})
    timestamp = metadata.get("timestamp")
    tool_name = None
    tools = metadata.get("tools")
    if isinstance(tools, list) and tools:
        tool_name = tools[0].get("name") if isinstance(tools[0], dict) else str(tools[0])
    elif isinstance(tools, dict):
        comps = tools.get("components", [])
        if comps:
            tool_name = comps[0].get("name", "")

    components = []
    for comp in data.get("components", []):
        vulns = []
        # CycloneDX 1.5+ has vulnerabilities at top level, referencing components
        # CycloneDX 1.4 may embed them in components
        for v in comp.get("vulnerabilities", []):
            cwes = []
            for cwe_ref in v.get("cwes", []):
                if isinstance(cwe_ref, int):
                    cwes.append(f"CWE-{cwe_ref}")
                elif isinstance(cwe_ref, str):
                    m = CWE_RE.search(cwe_ref)
                    if m:
                        cwes.append(f"CWE-{m.group(1)}")
            ratings = v.get("ratings", [])
            score = 0.0
            severity = v.get("severity", "unknown")
            if ratings:
                score = ratings[0].get("score", 0.0)
                severity = ratings[0].get("severity", severity)
            vulns.append(Vulnerability(
                id=v.get("id", v.get("ref", "unknown")),
                severity=severity.lower(),
                score=score,
                cwes=cwes,
                source=v.get("source", {}).get("name", ""),
            ))

        licenses = []
        for lic in comp.get("licenses", []):
            if isinstance(lic, dict):
                lid = lic.get("license", {})
                if isinstance(lid, dict):
                    licenses.append(lid.get("id", lid.get("name", "")))
                elif isinstance(lid, str):
                    licenses.append(lid)
            elif isinstance(lic, str):
                licenses.append(lic)

        components.append(Component(
            name=comp.get("name", ""),
            version=comp.get("version", ""),
            purl=comp.get("purl"),
            component_type=comp.get("type", "library"),
            licenses=[l for l in licenses if l],
            supplier=(comp.get("supplier", {}) or {}).get("name"),
            scope=comp.get("scope", "required"),
            vulnerabilities=vulns,
        ))

    # Top-level vulnerabilities (CycloneDX 1.5+)
    _attach_top_level_vulns(data.get("vulnerabilities", []), components)

    sbom = SBOM(
        format="cyclonedx",
        spec_version=spec_version,
        components=components,
        timestamp=timestamp,
        tool_name=tool_name,
    )
    log.info("Parsed CycloneDX %s: %d components", spec_version, len(components))
    return sbom


def _parse_spdx(data: Dict[str, Any]) -> SBOM:
    """Parse SPDX JSON SBOM."""
    spec_version = data.get("spdxVersion", "unknown")
    creation = data.get("creationInfo", {})
    timestamp = creation.get("created")
    tool_name = None
    creators = creation.get("creators", [])
    for c in creators:
        if isinstance(c, str) and c.startswith("Tool:"):
            tool_name = c[5:].strip()
            break

    components = []
    for pkg in data.get("packages", []):
        # Skip the document package itself
        if pkg.get("SPDXID") == "SPDXRef-DOCUMENT":
            continue

        licenses = []
        concluded = pkg.get("licenseConcluded", "")
        if concluded and concluded != "NOASSERTION":
            licenses.append(concluded)
        declared = pkg.get("licenseDeclared", "")
        if declared and declared != "NOASSERTION" and declared != concluded:
            licenses.append(declared)

        purl = None
        for ref in pkg.get("externalRefs", []):
            if ref.get("referenceType") == "purl":
                purl = ref.get("referenceLocator")
                break

        components.append(Component(
            name=pkg.get("name", ""),
            version=pkg.get("versionInfo", pkg.get("version", "")),
            purl=purl,
            component_type="library",
            licenses=licenses,
            supplier=(pkg.get("supplier") or "").replace("Organization: ", "") or None,
            scope="required",
        ))

    sbom = SBOM(
        format="spdx",
        spec_version=spec_version,
        components=components,
        timestamp=timestamp,
        tool_name=tool_name,
    )
    log.info("Parsed SPDX %s: %d packages", spec_version, len(components))
    return sbom


def _attach_top_level_vulns(
    vulns: List[Dict[str, Any]],
    components: List[Component],
) -> None:
    """Attach top-level CycloneDX vulnerabilities to their affected components."""
    if not vulns:
        return
    comp_by_ref = {}
    for c in components:
        if c.purl:
            comp_by_ref[c.purl] = c
        comp_by_ref[f"{c.name}@{c.version}"] = c

    for v in vulns:
        cwes = []
        for cwe_entry in v.get("cwes", []):
            if isinstance(cwe_entry, int):
                cwes.append(f"CWE-{cwe_entry}")
            elif isinstance(cwe_entry, dict):
                cwes.append(f"CWE-{cwe_entry.get('cweId', 0)}")
            elif isinstance(cwe_entry, str):
                m = CWE_RE.search(cwe_entry)
                if m:
                    cwes.append(f"CWE-{m.group(1)}")

        ratings = v.get("ratings", [])
        score = ratings[0].get("score", 0.0) if ratings else 0.0
        severity = ratings[0].get("severity", "unknown") if ratings else "unknown"

        vuln = Vulnerability(
            id=v.get("id", "unknown"),
            severity=severity.lower(),
            score=score,
            cwes=cwes,
            source=(v.get("source", {}) or {}).get("name", ""),
        )

        # Match to affected components
        affects = v.get("affects", [])
        matched = False
        for affect in affects:
            ref = affect.get("ref", "")
            comp = comp_by_ref.get(ref)
            if comp:
                comp.vulnerabilities.append(vuln)
                matched = True
        if not matched and components:
            # Can't match — attach to first component as fallback
            components[0].vulnerabilities.append(vuln)


def generate_sbom_report(sbom: SBOM, framework: str) -> Dict[str, Any]:
    """Generate a compliance evidence report from SBOM data.

    Maps SBOM components to supply chain, provenance, and inventory controls.
    Vulnerabilities with CWEs are passed through the CWE→control mapping pipeline.
    """
    normalised_fw = framework.replace("-", "_")

    total = len(sbom.components)
    ai_count = sum(1 for c in sbom.components if c.is_ai_package)
    with_license = sum(1 for c in sbom.components if c.licenses)
    with_supplier = sum(1 for c in sbom.components if c.supplier)
    vuln_count = sum(len(c.vulnerabilities) for c in sbom.components)
    critical_vulns = sum(
        1 for c in sbom.components
        for v in c.vulnerabilities if v.severity in ("critical", "high")
    )

    # Determine evidence status for supply chain controls
    has_inventory = total > 0
    has_licenses = with_license > total * 0.5
    has_suppliers = with_supplier > total * 0.3
    has_no_critical = critical_vulns == 0

    # Build control-level assessments
    controls = []

    # Supply chain inventory
    controls.append({
        "controlId": "sbom_inventory",
        "status": "met" if has_inventory else "gap",
        "requirement": "Maintain an inventory of AI system dependencies and components",
        "evidence": [f"SBOM contains {total} components ({ai_count} AI/ML-related)"],
        "evidence_fn": "evidence_ai_supply_chain",
    })

    # License compliance
    controls.append({
        "controlId": "sbom_licenses",
        "status": "met" if has_licenses else ("partial" if with_license > 0 else "gap"),
        "requirement": "Track and verify licenses for all dependencies",
        "evidence": [f"{with_license}/{total} components have declared licenses"],
        "evidence_fn": "evidence_ai_supply_chain",
    })

    # Supplier tracking
    controls.append({
        "controlId": "sbom_suppliers",
        "status": "met" if has_suppliers else ("partial" if with_supplier > 0 else "gap"),
        "requirement": "Identify and track suppliers for third-party components",
        "evidence": [f"{with_supplier}/{total} components have identified suppliers"],
        "evidence_fn": "evidence_model_provenance",
    })

    # Vulnerability management
    if vuln_count > 0:
        controls.append({
            "controlId": "sbom_vulnerabilities",
            "status": "gap" if critical_vulns > 0 else "partial",
            "requirement": "No critical/high vulnerabilities in dependencies",
            "evidence": [f"{vuln_count} vulnerabilities found ({critical_vulns} critical/high)"],
            "gaps": [
                f"{c.name}@{c.version}: {v.id} ({v.severity})"
                for c in sbom.components for v in c.vulnerabilities
                if v.severity in ("critical", "high")
            ][:10],
            "evidence_fn": "evidence_ai_supply_chain",
        })
    else:
        controls.append({
            "controlId": "sbom_vulnerabilities",
            "status": "met",
            "requirement": "No critical/high vulnerabilities in dependencies",
            "evidence": ["No known vulnerabilities found in SBOM components"],
            "evidence_fn": "evidence_ai_supply_chain",
        })

    met = sum(1 for c in controls if c["status"] == "met")
    partial = sum(1 for c in controls if c["status"] == "partial")
    gap = sum(1 for c in controls if c["status"] == "gap")
    score = round((met + 0.5 * partial) / len(controls) * 100, 1) if controls else 0.0

    report = {
        "framework": normalised_fw,
        "source": "sbom_import",
        "summary": {
            "met": met,
            "partial": partial,
            "gap": gap,
            "total": len(controls),
            "score": score,
        },
        "articles": [{
            "articleId": "sbom_analysis",
            "label": "Software Bill of Materials Analysis",
            "met": met,
            "partial": partial,
            "gap": gap,
            "controls": controls,
        }],
        "sbomMetadata": {
            "format": sbom.format,
            "specVersion": sbom.spec_version,
            "totalComponents": total,
            "aiComponents": ai_count,
            "withLicense": with_license,
            "withSupplier": with_supplier,
            "vulnerabilities": vuln_count,
            "criticalVulnerabilities": critical_vulns,
            "tool": sbom.tool_name,
        },
    }

    # Also produce vulnerability findings for CWE mapping pipeline
    from comply.sarif_import import Finding

    vuln_findings = []
    for comp in sbom.components:
        for v in comp.vulnerabilities:
            level = "error" if v.severity in ("critical", "high") else "warning"
            vuln_findings.append(Finding(
                tool=f"sbom:{sbom.tool_name or sbom.format}",
                rule_id=v.id,
                level=level,
                message=f"{comp.name}@{comp.version}: {v.id} ({v.severity})",
                cwes=v.cwes if v.cwes else [],
                file_path=None,
                start_line=None,
                end_line=None,
                snippet=None,
            ))

    report["vulnerabilityFindings"] = len(vuln_findings)

    return report, vuln_findings
