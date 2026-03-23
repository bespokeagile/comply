"""API routes for SARIF, SBOM, and JUnit import and compliance mapping."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(tags=["import"])


class SarifImportRequest(BaseModel):
    sarif: Dict[str, Any]
    framework: str = "eu-ai-act"
    merge_with_scan_id: Optional[str] = None
    no_architectural_weighting: bool = False


class SarifImportResponse(BaseModel):
    findings_count: int
    cwes_found: List[str]
    tools: List[str]
    report: Dict[str, Any]
    merged: bool = False
    architectural_enrichment: Optional[Dict[str, Any]] = None


@router.post("/import-sarif", response_model=SarifImportResponse)
async def import_sarif(req: SarifImportRequest):
    """Import SARIF findings and map to compliance controls."""
    try:
        from comply.sarif_import import parse_sarif
        from comply.finding_mapper import map_findings, generate_import_report, merge_reports
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Import modules not available: {e}")

    # Parse SARIF
    findings = parse_sarif(req.sarif)
    if not findings:
        raise HTTPException(status_code=400, detail="No findings extracted from SARIF data")

    # Graph enrichment: try to get codebase model from merge target
    graph_metrics: Dict[str, Dict[str, float]] = {}
    enrichment_source = None

    if not req.no_architectural_weighting and req.merge_with_scan_id:
        try:
            from comply.store import get_scan
            scan = get_scan(req.merge_with_scan_id)
            if scan and scan.get("report"):
                codebase_graph = scan["report"].get("model", {}).get("codebaseGraph", {})
                if codebase_graph and codebase_graph.get("files"):
                    from comply._vendor.graph_ranking import compute_graph_metrics
                    graph_metrics = compute_graph_metrics(codebase_graph)
                    enrichment_source = "merged_scan"
                    log.info("Graph enrichment from merged scan: %d files", len(graph_metrics))
        except Exception as e:
            log.warning("Could not load codebase model from scan: %s", e)

    # Map to compliance controls with architectural weighting
    mapped = map_findings(
        findings, req.framework,
        graph_metrics=graph_metrics if graph_metrics else None,
        architectural_weighting=not req.no_architectural_weighting,
    )
    report = generate_import_report(mapped, req.framework)

    # Merge with existing scan if requested
    merged = False
    if req.merge_with_scan_id:
        try:
            from comply.store import get_scan
            scan = get_scan(req.merge_with_scan_id)
            if scan and scan.get("report"):
                report = merge_reports(scan["report"], report)
                merged = True
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Scan '{req.merge_with_scan_id}' not found",
                )
        except ImportError:
            log.warning("comply.store not available for merge")

    # Collect metadata
    tools = sorted(set(f.tool for f in findings))
    cwes = sorted(set(cwe for f in findings for cwe in f.cwes))

    # Enrichment info for response
    enrichment_info = None
    arch_data = report.get("architecturalEnrichment")
    if arch_data:
        enrichment_info = {**arch_data, "source": enrichment_source or "unknown"}

    return SarifImportResponse(
        findings_count=len(findings),
        cwes_found=cwes,
        tools=tools,
        report=report,
        merged=merged,
        architectural_enrichment=enrichment_info,
    )


# ── SBOM import ──────────────────────────────────────────────────────


class SBOMImportRequest(BaseModel):
    sbom: Dict[str, Any]
    framework: str = "nist-ai-rmf"


class SBOMImportResponse(BaseModel):
    format: str
    components_count: int
    ai_components: int
    vulnerabilities: int
    report: Dict[str, Any]
    vulnerability_findings: int = 0


@router.post("/import-sbom", response_model=SBOMImportResponse)
async def import_sbom(req: SBOMImportRequest):
    """Import SBOM (CycloneDX or SPDX) and generate supply chain compliance report."""
    try:
        from comply.sbom_import import parse_sbom, generate_sbom_report
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"SBOM import modules not available: {e}")

    try:
        sbom = parse_sbom(req.sbom)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not sbom.components:
        raise HTTPException(status_code=400, detail="No components found in SBOM")

    report, vuln_findings = generate_sbom_report(sbom, req.framework)

    # If there are vulnerability findings with CWEs, also run them through
    # the CWE→control mapping pipeline for the target framework
    cwe_findings = [f for f in vuln_findings if f.cwes]
    if cwe_findings:
        try:
            from comply.finding_mapper import map_findings, generate_import_report
            mapped = map_findings(cwe_findings, req.framework)
            sec_report = generate_import_report(mapped, req.framework)
            report["securityFindings"] = sec_report.get("securityFindings", [])
        except Exception as e:
            log.warning("CWE mapping for SBOM vulns failed: %s", e)

    ai_count = sum(1 for c in sbom.components if c.is_ai_package)
    vuln_count = sum(len(c.vulnerabilities) for c in sbom.components)

    return SBOMImportResponse(
        format=sbom.format,
        components_count=len(sbom.components),
        ai_components=ai_count,
        vulnerabilities=vuln_count,
        report=report,
        vulnerability_findings=len(vuln_findings),
    )


# ── JUnit import ─────────────────────────────────────────────────────


class JUnitImportRequest(BaseModel):
    junit_xml: str  # Raw XML string
    framework: str = "nist-ai-rmf"


class JUnitImportResponse(BaseModel):
    suites: int
    total_tests: int
    passed: int
    failed: int
    pass_rate: float
    evidence_categories: int
    report: Dict[str, Any]


@router.post("/import-junit", response_model=JUnitImportResponse)
async def import_junit(req: JUnitImportRequest):
    """Import JUnit XML test results and generate test evidence compliance report."""
    try:
        from comply.junit_import import parse_junit, generate_junit_report
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"JUnit import modules not available: {e}")

    suites = parse_junit(req.junit_xml)
    if not suites:
        raise HTTPException(status_code=400, detail="No test suites found in JUnit XML")

    report = generate_junit_report(suites, req.framework)
    meta = report.get("junitMetadata", {})

    return JUnitImportResponse(
        suites=meta.get("suites", len(suites)),
        total_tests=meta.get("totalTests", 0),
        passed=meta.get("passed", 0),
        failed=meta.get("failed", 0) + meta.get("errors", 0),
        pass_rate=meta.get("passRate", 0.0),
        evidence_categories=meta.get("evidenceCategories", 0),
        report=report,
    )
