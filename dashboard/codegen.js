/* codegen.js -- Remediation code patch generator.
 *
 * Generates copy-paste-ready code snippets for compliance remediation.
 * Templates are keyed by evidence_fn and parameterized with codebase context
 * (related files, repo name, language). Opens in a new tab with syntax
 * highlighting and integration instructions.
 *
 * This is a starting point for human review, NOT automatic compliance. */

const CodeGenerator = {

    /** Generate a code patch for a remediation item. Opens in new tab. */
    generate(remediation, report) {
        if (!remediation || !remediation.evidence_fn) {
            return alert('No code template available for this remediation.');
        }

        const template = this._TEMPLATES[remediation.evidence_fn];
        if (!template) {
            return alert(`No code template for ${remediation.evidence_fn}. Document templates may be available in the Export tab.`);
        }

        const lang = this._detectLanguage(report);
        const ctx = {
            repo: (report.target || '').replace(/.*\//, '') || 'your-repo',
            framework: report.framework || '',
            fwLabel: typeof fwLabel === 'function' ? fwLabel(report.framework) : report.framework,
            controlId: remediation.controlId || '',
            relatedFiles: remediation.relatedFiles || [],
            lang: lang,
            date: new Date().toISOString().split('T')[0],
        };

        const patch = template(ctx);
        this._openPatch(patch, ctx);
    },

    /** Detect primary language from codebase model. */
    _detectLanguage(report) {
        const model = report.model || {};
        const files = model.filesByType || model.languageBreakdown || {};

        // Check common indicators
        if (files.py || files.python) return 'python';
        if (files.js || files.ts || files.javascript || files.typescript) return 'javascript';
        if (files.java) return 'java';
        if (files.go) return 'go';
        if (files.rs || files.rust) return 'rust';
        if (files.rb || files.ruby) return 'ruby';

        // Fallback: check file extensions in features or scanned files
        const target = (report.target || '').toLowerCase();
        if (target.includes('python') || target.includes('.py')) return 'python';
        if (target.includes('node') || target.includes('.js')) return 'javascript';

        return 'python'; // default
    },

    /** Open the generated patch in a new tab. */
    _openPatch(patch, ctx) {
        const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Code Patch: ${this._esc(ctx.controlId)} - ${this._esc(ctx.fwLabel)}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: #1a1a2e; line-height: 1.6; background: #fff; max-width: 900px; margin: 0 auto; padding: 40px 60px; }
h1 { font-size: 24px; font-weight: 300; margin-bottom: 4px; }
h2 { font-size: 18px; font-weight: 600; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #e2e8f0; }
h3 { font-size: 14px; font-weight: 600; margin: 16px 0 8px; color: #334155; }
.brand { font-size: 12px; letter-spacing: 2px; text-transform: uppercase; color: #64748b; margin-bottom: 16px; }
.meta { font-size: 13px; color: #64748b; margin-bottom: 24px; }
.warning { background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px; padding: 12px 16px; font-size: 13px; color: #92400e; margin-bottom: 24px; }
p { font-size: 14px; color: #475569; margin-bottom: 12px; }
ul, ol { font-size: 14px; color: #475569; margin: 8px 0 16px 24px; }
li { margin-bottom: 4px; }
pre { background: #1e293b; color: #e2e8f0; padding: 20px; border-radius: 8px; overflow-x: auto; font-size: 13px; line-height: 1.5; margin-bottom: 16px; position: relative; }
code { font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; }
.inline-code { background: #f1f5f9; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; color: #334155; }
.copy-btn { position: absolute; top: 8px; right: 8px; background: #334155; color: #94a3b8; border: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; }
.copy-btn:hover { background: #475569; color: #e2e8f0; }
.file-path { font-size: 13px; color: #6366f1; font-weight: 600; margin-bottom: 4px; }
.section { margin-bottom: 32px; }
.disclaimer { font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 32px; }
@media print {
    pre { white-space: pre-wrap; font-size: 11px; }
    .copy-btn { display: none; }
}
</style>
<script>
function copyCode(id) {
    var pre = document.getElementById(id);
    if (!pre) return;
    navigator.clipboard.writeText(pre.textContent).then(function() {
        var btn = pre.parentNode.querySelector('.copy-btn');
        if (btn) { btn.textContent = 'Copied!'; setTimeout(function(){ btn.textContent = 'Copy'; }, 1500); }
    });
}
</script>
</head>
<body>
<div class="brand">BespokeAgile Comply</div>
<h1>Code Patch: ${this._esc(ctx.controlId)}</h1>
<div class="meta">${this._esc(ctx.fwLabel)} | ${this._esc(ctx.repo)} | ${ctx.date}</div>
<div class="warning">
    <strong>Review required.</strong> This code is a starting point generated from compliance analysis.
    It must be reviewed, tested, and adapted to your specific codebase before use.
    It does not constitute automatic compliance.
</div>
${patch}
<div class="disclaimer">
    Generated by BespokeAgile Comply. This is a compliance remediation aid, not a guarantee of regulatory compliance.
</div>
</body>
</html>`;

        const w = window.open('', '_blank');
        if (!w) return alert('Pop-up blocked. Please allow pop-ups for this site.');
        w.document.write(html);
        w.document.close();
    },

    _esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    },

    _codeBlock(code, id) {
        return `<div style="position:relative"><button class="copy-btn" onclick="copyCode('${id}')">Copy</button><pre><code id="${id}">${this._esc(code)}</code></pre></div>`;
    },

    // ── Templates ────────────────────────────────────────────────────────

    _TEMPLATES: {

        evidence_audit_logging: function(ctx) {
            const gen = CodeGenerator;
            const files = ctx.relatedFiles;
            const fileList = files.length > 0
                ? files.map(f => `<li><span class="inline-code">${gen._esc(f)}</span></li>`).join('')
                : '<li>No related files detected</li>';

            if (ctx.lang === 'python') {
                return `
<div class="section">
    <h2>1. Audit Logging Module</h2>
    <p>Create a structured audit logging module that records AI operations, decisions, and data access events.</p>
    <div class="file-path">New file: src/compliance/audit_logger.py</div>
    ${gen._codeBlock(`"""Compliance audit logger for AI operations.

Satisfies: ${ctx.controlId} (${ctx.fwLabel})
Records structured events for model invocations, data access,
decisions, and configuration changes.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Optional


# Dedicated audit logger -- separate from application logs
audit_logger = logging.getLogger("compliance.audit")
audit_logger.setLevel(logging.INFO)

# File handler with rotation (configure path for your environment)
_handler = logging.FileHandler("audit_trail.jsonl")
_handler.setFormatter(logging.Formatter("%(message)s"))
audit_logger.addHandler(_handler)


def log_event(
    event_type: str,
    operation: str,
    actor_id: Optional[str] = None,
    component: Optional[str] = None,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    confidence: Optional[float] = None,
    controls: Optional[list] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Record a structured audit event. Returns the event ID."""
    event_id = str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "actor": {"user_id": actor_id or "system"},
        "resource": {
            "system": "${ctx.repo}",
            "component": component or "unknown",
        },
        "action": {
            "operation": operation,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "confidence_score": confidence,
        },
        "compliance": {
            "framework": "${ctx.framework}",
            "controls_exercised": controls or [],
        },
    }
    if metadata:
        event["metadata"] = metadata

    audit_logger.info(json.dumps(event, default=str))
    return event_id


def audit_model_call(model_name: str = "", control_ids: Optional[list] = None):
    """Decorator to automatically audit model/AI invocations."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            event_id = log_event(
                event_type="model_invocation",
                operation=func.__name__,
                component=model_name or func.__module__,
                controls=control_ids,
                input_summary=f"args={len(args)}, kwargs={list(kwargs.keys())}",
            )
            try:
                result = func(*args, **kwargs)
                log_event(
                    event_type="model_invocation",
                    operation=f"{func.__name__}:complete",
                    component=model_name or func.__module__,
                    output_summary="success",
                    metadata={"parent_event": event_id},
                )
                return result
            except Exception as e:
                log_event(
                    event_type="system_error",
                    operation=f"{func.__name__}:error",
                    component=model_name or func.__module__,
                    output_summary=str(e)[:200],
                    metadata={"parent_event": event_id},
                )
                raise
        return wrapper
    return decorator`, 'audit-logger')}
</div>

<div class="section">
    <h2>2. Integration</h2>
    <p>Connect the audit logger to your existing code:</p>
    <h3>Related files in your codebase:</h3>
    <ul>${fileList}</ul>

    <h3>Usage: Decorate AI-related functions</h3>
    ${gen._codeBlock(`from compliance.audit_logger import audit_model_call, log_event

# Decorate functions that invoke AI models
@audit_model_call(model_name="risk-scorer", control_ids=["${ctx.controlId}"])
def score_risk(input_data):
    # ... existing implementation ...
    return result

# Manual logging for data access events
log_event(
    event_type="data_access",
    operation="load_training_data",
    actor_id=current_user.id,
    component="data_pipeline",
    input_summary="training dataset v2.1",
)`, 'integration')}

    <h3>Add to your application startup</h3>
    ${gen._codeBlock(`# In your main application file (e.g., app.py)
import logging

# Configure audit log handler (adjust path and rotation as needed)
audit = logging.getLogger("compliance.audit")
audit.setLevel(logging.INFO)

# For production: use RotatingFileHandler or ship to a log aggregator
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler(
    "audit_trail.jsonl",
    maxBytes=50_000_000,  # 50 MB
    backupCount=10,
)
handler.setFormatter(logging.Formatter("%(message)s"))
audit.addHandler(handler)`, 'startup')}
</div>

<div class="section">
    <h2>3. Verification</h2>
    <p>After integration, verify compliance by checking:</p>
    <ol>
        <li>Audit log file is created and populated with events</li>
        <li>Events include all required fields (event_id, timestamp, event_type, actor, action)</li>
        <li>AI model invocations are automatically logged via the decorator</li>
        <li>Log entries are append-only (not modified after creation)</li>
        <li>Re-run BespokeAgile Comply scan to verify control ${gen._esc(ctx.controlId)} status improves</li>
    </ol>
</div>`;
            }

            // JavaScript/TypeScript fallback
            return `
<div class="section">
    <h2>1. Audit Logging Module</h2>
    <p>Create a structured audit logging module for AI operations.</p>
    <div class="file-path">New file: src/compliance/auditLogger.js</div>
    ${gen._codeBlock(`/**
 * Compliance audit logger for AI operations.
 * Satisfies: ${ctx.controlId} (${ctx.fwLabel})
 */

const fs = require('fs');
const { randomUUID } = require('crypto');

const LOG_FILE = process.env.AUDIT_LOG_PATH || 'audit_trail.jsonl';

function logEvent({
  eventType, operation, actorId = 'system', component = 'unknown',
  inputSummary, outputSummary, confidence, controls = [], metadata,
}) {
  const eventId = randomUUID();
  const event = {
    event_id: eventId,
    timestamp: new Date().toISOString(),
    event_type: eventType,
    actor: { user_id: actorId },
    resource: { system: '${ctx.repo}', component },
    action: { operation, input_summary: inputSummary, output_summary: outputSummary, confidence_score: confidence },
    compliance: { framework: '${ctx.framework}', controls_exercised: controls },
  };
  if (metadata) event.metadata = metadata;
  fs.appendFileSync(LOG_FILE, JSON.stringify(event) + '\\n');
  return eventId;
}

function auditModelCall(modelName, controlIds = []) {
  return function(target, name, descriptor) {
    const original = descriptor.value;
    descriptor.value = async function(...args) {
      const eventId = logEvent({
        eventType: 'model_invocation', operation: name,
        component: modelName, controls: controlIds,
        inputSummary: \`args=\${args.length}\`,
      });
      try {
        const result = await original.apply(this, args);
        logEvent({ eventType: 'model_invocation', operation: name + ':complete',
          component: modelName, outputSummary: 'success', metadata: { parent_event: eventId } });
        return result;
      } catch (err) {
        logEvent({ eventType: 'system_error', operation: name + ':error',
          component: modelName, outputSummary: err.message?.slice(0, 200), metadata: { parent_event: eventId } });
        throw err;
      }
    };
    return descriptor;
  };
}

module.exports = { logEvent, auditModelCall };`, 'audit-logger')}
</div>

<div class="section">
    <h2>2. Integration</h2>
    <h3>Related files in your codebase:</h3>
    <ul>${fileList}</ul>
    ${gen._codeBlock(`const { logEvent } = require('./compliance/auditLogger');

// Log AI model invocations
logEvent({
  eventType: 'model_invocation',
  operation: 'scoreRisk',
  actorId: req.user?.id,
  component: 'risk-scorer',
  controls: ['${ctx.controlId}'],
});`, 'integration')}
</div>`;
        },

        evidence_risk_assessment_gateway: function(ctx) {
            const gen = CodeGenerator;
            if (ctx.lang === 'python') {
                return `
<div class="section">
    <h2>1. Risk Assessment Data Model</h2>
    <p>Create a structured risk assessment module that formalizes risk categorization and connects to existing validation.</p>
    <div class="file-path">New file: src/compliance/risk_assessment.py</div>
    ${gen._codeBlock(`"""Risk assessment and categorization module.

Satisfies: ${ctx.controlId} (${ctx.fwLabel})
Formalizes AI system risks with structured categories,
likelihood/impact scoring, and mitigation tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
import json


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(str, Enum):
    BIAS = "bias_discrimination"
    PRIVACY = "data_privacy"
    SECURITY = "security"
    SAFETY = "safety_reliability"
    TRANSPARENCY = "transparency"
    ACCOUNTABILITY = "accountability"
    PERFORMANCE = "performance_degradation"


class MitigationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"


@dataclass
class Risk:
    risk_id: str
    category: RiskCategory
    description: str
    likelihood: RiskLevel
    impact: RiskLevel
    control_id: str = ""
    mitigation: str = ""
    mitigation_status: MitigationStatus = MitigationStatus.NOT_STARTED
    owner: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def risk_score(self) -> int:
        """Compute numeric risk score from likelihood x impact."""
        levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return levels.get(self.likelihood, 0) * levels.get(self.impact, 0)

    @property
    def risk_level(self) -> RiskLevel:
        score = self.risk_score
        if score >= 12:
            return RiskLevel.CRITICAL
        if score >= 6:
            return RiskLevel.HIGH
        if score >= 3:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


class RiskRegister:
    """Central registry of identified AI system risks."""

    def __init__(self):
        self._risks: List[Risk] = []

    def add_risk(self, risk: Risk) -> None:
        self._risks.append(risk)

    def get_by_category(self, category: RiskCategory) -> List[Risk]:
        return [r for r in self._risks if r.category == category]

    def get_critical(self) -> List[Risk]:
        return [r for r in self._risks if r.risk_level == RiskLevel.CRITICAL]

    def get_unmitigated(self) -> List[Risk]:
        return [
            r for r in self._risks
            if r.mitigation_status in (MitigationStatus.NOT_STARTED, MitigationStatus.IN_PROGRESS)
        ]

    def summary(self) -> dict:
        """Generate risk summary for compliance reporting."""
        return {
            "total_risks": len(self._risks),
            "by_level": {
                level.value: len([r for r in self._risks if r.risk_level == level])
                for level in RiskLevel
            },
            "unmitigated": len(self.get_unmitigated()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "framework": "${ctx.framework}",
        }

    def export_json(self) -> str:
        """Export register as JSON for audit trail."""
        return json.dumps({
            "risks": [
                {
                    "risk_id": r.risk_id,
                    "category": r.category.value,
                    "description": r.description,
                    "likelihood": r.likelihood.value,
                    "impact": r.impact.value,
                    "risk_score": r.risk_score,
                    "risk_level": r.risk_level.value,
                    "control_id": r.control_id,
                    "mitigation": r.mitigation,
                    "mitigation_status": r.mitigation_status.value,
                    "owner": r.owner,
                }
                for r in self._risks
            ],
            "summary": self.summary(),
        }, indent=2)`, 'risk-model')}
</div>

<div class="section">
    <h2>2. Integration</h2>
    ${gen._codeBlock(`from compliance.risk_assessment import (
    RiskRegister, Risk, RiskCategory, RiskLevel
)

# Initialize the risk register
register = RiskRegister()

# Add risks identified by compliance scanning
register.add_risk(Risk(
    risk_id="R-001",
    category=RiskCategory.TRANSPARENCY,
    description="AI system lacks structured technical documentation",
    likelihood=RiskLevel.HIGH,
    impact=RiskLevel.MEDIUM,
    control_id="${ctx.controlId}",
    mitigation="Create documentation covering system architecture and data flows",
    owner="Engineering Lead",
))

# Generate compliance report
print(register.export_json())

# Check for unmitigated critical risks
critical = register.get_critical()
if critical:
    print(f"WARNING: {len(critical)} critical risks require immediate attention")`, 'risk-integration')}
</div>

<div class="section">
    <h2>3. Verification</h2>
    <ol>
        <li>Risk register contains all identified risks with categories and scores</li>
        <li>Each risk has an assigned owner and mitigation plan</li>
        <li>Risk summary can be exported for audit documentation</li>
        <li>Re-run compliance scan to verify control ${gen._esc(ctx.controlId)} status improves</li>
    </ol>
</div>`;
            }

            return `<div class="section"><p>Code generation for ${gen._esc(ctx.lang)} is not yet available for this control. Use the document templates in the Export tab.</p></div>`;
        },

        evidence_risk_categorization: function(ctx) {
            // Reuse risk_assessment_gateway template
            return CodeGenerator._TEMPLATES.evidence_risk_assessment_gateway(ctx);
        },

        evidence_governance_policy: function(ctx) {
            const gen = CodeGenerator;
            return `
<div class="section">
    <h2>1. Governance Configuration Module</h2>
    <p>Create a machine-readable governance policy that can be validated automatically.</p>
    <div class="file-path">New file: src/compliance/governance.py</div>
    ${gen._codeBlock(`"""AI governance configuration and policy enforcement.

Satisfies: ${ctx.controlId} (${ctx.fwLabel})
Machine-readable governance rules that can be validated
in CI/CD pipelines and compliance scans.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class RiskTier(str, Enum):
    HIGH = "high"
    LIMITED = "limited"
    MINIMAL = "minimal"


@dataclass
class GovernancePolicy:
    """Machine-readable governance policy for an AI system."""
    system_name: str
    risk_tier: RiskTier
    requires_human_oversight: bool
    data_retention_days: int
    audit_log_enabled: bool
    bias_monitoring_enabled: bool
    transparency_notice_url: str = ""
    review_cadence_days: int = 90
    approved_by: str = ""

    def validate(self) -> List[str]:
        """Return list of policy violations."""
        violations = []
        if self.risk_tier == RiskTier.HIGH:
            if not self.requires_human_oversight:
                violations.append("High-risk systems require human oversight")
            if not self.audit_log_enabled:
                violations.append("High-risk systems require audit logging")
            if not self.transparency_notice_url:
                violations.append("High-risk systems require transparency notice")
        if self.data_retention_days < 30:
            violations.append("Data retention must be at least 30 days")
        if not self.approved_by:
            violations.append("Policy must have an approver")
        return violations


# Default policy for ${ctx.repo}
DEFAULT_POLICY = GovernancePolicy(
    system_name="${ctx.repo}",
    risk_tier=RiskTier.HIGH,
    requires_human_oversight=True,
    data_retention_days=365,
    audit_log_enabled=True,
    bias_monitoring_enabled=True,
    review_cadence_days=90,
)`, 'governance')}
</div>

<div class="section">
    <h2>2. CI/CD Integration</h2>
    <p>Add governance validation to your deployment pipeline:</p>
    ${gen._codeBlock(`# In your CI/CD or pre-deploy hook
from compliance.governance import DEFAULT_POLICY

violations = DEFAULT_POLICY.validate()
if violations:
    print("Governance policy violations:")
    for v in violations:
        print(f"  - {v}")
    exit(1)
print("Governance policy: all checks passed")`, 'ci-integration')}
</div>`;
        },

        evidence_continuous_monitoring: function(ctx) {
            const gen = CodeGenerator;
            return `
<div class="section">
    <h2>1. Compliance Monitoring Module</h2>
    <p>Create a continuous monitoring system that tracks compliance metrics and alerts on regressions.</p>
    <div class="file-path">New file: src/compliance/monitor.py</div>
    ${gen._codeBlock(`"""Continuous compliance monitoring.

Satisfies: ${ctx.controlId} (${ctx.fwLabel})
Tracks compliance metrics over time and alerts when
thresholds are breached.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("compliance.monitor")


class ComplianceMonitor:
    """Track and alert on compliance metric changes."""

    def __init__(self, alert_threshold: float = 0.05):
        self._history: List[Dict] = []
        self._alert_threshold = alert_threshold  # 5% regression triggers alert

    def record_scan(self, framework: str, score: float, controls_met: int,
                    controls_total: int, scan_depth: str = "structure") -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "framework": framework,
            "score": score,
            "controls_met": controls_met,
            "controls_total": controls_total,
            "scan_depth": scan_depth,
        }
        self._history.append(entry)
        self._check_regression(entry)

    def _check_regression(self, current: Dict) -> None:
        """Alert if score dropped more than threshold since last scan."""
        prev = [h for h in self._history[:-1]
                if h["framework"] == current["framework"]]
        if not prev:
            return
        last = prev[-1]
        delta = current["score"] - last["score"]
        if delta < -self._alert_threshold * 100:
            logger.warning(
                f"COMPLIANCE REGRESSION: {current['framework']} "
                f"dropped {abs(delta):.1f}% "
                f"({last['score']:.1f}% -> {current['score']:.1f}%)"
            )

    def get_trend(self, framework: str) -> List[Dict]:
        return [h for h in self._history if h["framework"] == framework]

    def export_history(self) -> str:
        return json.dumps(self._history, indent=2)`, 'monitor')}
</div>

<div class="section">
    <h2>2. Integration</h2>
    ${gen._codeBlock(`from compliance.monitor import ComplianceMonitor

monitor = ComplianceMonitor(alert_threshold=0.05)

# After each compliance scan, record the result
monitor.record_scan(
    framework="${ctx.framework}",
    score=88.0,
    controls_met=6,
    controls_total=8,
    scan_depth="semantic",
)`, 'monitor-integration')}
</div>`;
        },

        evidence_performance_measurement: function(ctx) {
            return CodeGenerator._TEMPLATES.evidence_continuous_monitoring(ctx);
        },

        evidence_transparency_disclosure: function(ctx) {
            const gen = CodeGenerator;
            return `
<div class="section">
    <h2>1. Transparency Middleware</h2>
    <p>Add transparency headers and disclosure endpoints to your API.</p>
    <div class="file-path">New file: src/compliance/transparency.py</div>
    ${gen._codeBlock(`"""Transparency disclosure middleware.

Satisfies: ${ctx.controlId} (${ctx.fwLabel})
Adds AI transparency headers to API responses and provides
a disclosure endpoint describing AI system capabilities.
"""

from datetime import datetime, timezone

# System disclosure metadata
AI_DISCLOSURE = {
    "system": "${ctx.repo}",
    "version": "1.0",
    "ai_powered": True,
    "capabilities": [
        # List what the AI system does
        "Automated compliance scanning",
        "Evidence pattern matching",
        "Risk assessment assistance",
    ],
    "limitations": [
        # Be honest about limitations
        "Results are advisory, not legal certification",
        "Accuracy depends on codebase completeness",
        "May not detect all compliance gaps",
    ],
    "human_oversight": "All AI-generated results are subject to human review",
    "data_usage": "Analyzes code structure and patterns; does not store source code",
    "contact": "[compliance-team@your-org.com]",
    "last_updated": "${ctx.date}",
}


def add_transparency_headers(response):
    """Add AI disclosure headers to HTTP response."""
    response.headers["X-AI-Powered"] = "true"
    response.headers["X-AI-Disclosure"] = "/api/ai-disclosure"
    response.headers["X-AI-Version"] = AI_DISCLOSURE["version"]
    return response


def get_disclosure():
    """Return full AI system disclosure for transparency compliance."""
    return {
        **AI_DISCLOSURE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "framework": "${ctx.framework}",
    }`, 'transparency')}
</div>

<div class="section">
    <h2>2. Integration (FastAPI example)</h2>
    ${gen._codeBlock(`from fastapi import FastAPI, Request, Response
from compliance.transparency import add_transparency_headers, get_disclosure

app = FastAPI()

@app.middleware("http")
async def transparency_middleware(request: Request, call_next):
    response = await call_next(request)
    return add_transparency_headers(response)

@app.get("/api/ai-disclosure")
def ai_disclosure():
    return get_disclosure()`, 'fastapi-integration')}
</div>`;
        },

        evidence_incident_response: function(ctx) {
            return CodeGenerator._TEMPLATES.evidence_continuous_monitoring(ctx);
        },

        evidence_traceability: function(ctx) {
            const gen = CodeGenerator;
            return `
<div class="section">
    <h2>1. Traceability Module</h2>
    <p>Create a traceability system linking AI decisions to their inputs, models, and outputs.</p>
    <div class="file-path">New file: src/compliance/traceability.py</div>
    ${gen._codeBlock(`"""Decision traceability for AI operations.

Satisfies: ${ctx.controlId} (${ctx.fwLabel})
Links every AI decision to its inputs, model version,
parameters, and outputs for audit reconstruction.
"""

import uuid
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class TraceRecord:
    """Immutable record of an AI decision for audit trail."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    model_id: str = ""
    model_version: str = ""
    input_hash: str = ""     # hash of input, not raw data
    output_summary: str = ""
    confidence: Optional[float] = None
    decision: str = ""
    rationale: str = ""
    human_reviewed: bool = False
    reviewer_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TraceStore:
    """Append-only store for AI decision traces."""

    def __init__(self, path: str = "traces.jsonl"):
        self._path = path

    def record(self, trace: TraceRecord) -> str:
        with open(self._path, "a") as f:
            f.write(json.dumps(trace.to_dict(), default=str) + "\\n")
        return trace.trace_id

    def find_by_id(self, trace_id: str) -> Optional[TraceRecord]:
        with open(self._path) as f:
            for line in f:
                data = json.loads(line)
                if data.get("trace_id") == trace_id:
                    return TraceRecord(**data)
        return None`, 'traceability')}
</div>`;
        },
    },

    // ── Document Templates (for documentation/process controls) ──────

    _DOC_TEMPLATES: {

        risk_assessment_doc: function(ctx) {
            return `
<div class="section">
    <h2>AI Risk Assessment</h2>
    <p>This risk assessment template satisfies requirements for control <strong>${ctx.controlId}</strong> under ${ctx.fwLabel}. Complete each section and retain this document for audit.</p>
</div>

<div class="section">
    <h2>1. System Description</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;width:30%">System Name</td>
            <td style="padding:8px;border:1px solid #e2e8f0">${ctx.repo}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Purpose</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Describe what the AI system does and why]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Risk Tier</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[High / Limited / Minimal]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Assessment Date</td>
            <td style="padding:8px;border:1px solid #e2e8f0">${ctx.date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Assessor</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name and role]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Next Review</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Quarterly recommended]</em></td></tr>
    </table>
</div>

<div class="section">
    <h2>2. Risk Methodology</h2>
    <p>Risks are assessed using a <strong>Likelihood x Impact</strong> matrix:</p>
    <table style="width:100%;border-collapse:collapse;font-size:12px;text-align:center">
        <tr style="background:#f8fafc"><th style="padding:6px;border:1px solid #e2e8f0">Impact / Likelihood</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Low</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Medium</th>
            <th style="padding:6px;border:1px solid #e2e8f0">High</th></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">High</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#fef3c7">Medium</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#fecaca">High</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#fecaca">Critical</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">Medium</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#d1fae5">Low</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#fef3c7">Medium</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#fecaca">High</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">Low</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#d1fae5">Low</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#d1fae5">Low</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#fef3c7">Medium</td></tr>
    </table>
</div>

<div class="section">
    <h2>3. Risk Register</h2>
    <p>Identify each risk, its category, assessment, and mitigation plan:</p>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">ID</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Category</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Description</th>
            <th style="padding:6px;border:1px solid #e2e8f0">L</th>
            <th style="padding:6px;border:1px solid #e2e8f0">I</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Level</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Mitigation</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Owner</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Status</th>
        </tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">R-001</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Bias</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Describe risk]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">M</td>
            <td style="padding:6px;border:1px solid #e2e8f0">H</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#fecaca">High</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Mitigation plan]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Not started</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">R-002</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Privacy</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Describe risk]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">L</td>
            <td style="padding:6px;border:1px solid #e2e8f0">M</td>
            <td style="padding:6px;border:1px solid #e2e8f0;background:#d1fae5">Low</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Mitigation plan]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Not started</td></tr>
    </table>
    <p style="margin-top:8px;font-size:12px;color:#64748b"><em>Categories: Bias/Discrimination, Privacy, Security, Safety, Transparency, Accountability, Performance</em></p>
</div>

<div class="section">
    <h2>4. Review Schedule</h2>
    <ul>
        <li>Quarterly review of all identified risks</li>
        <li>Immediate review upon material system changes</li>
        <li>Annual comprehensive reassessment</li>
    </ul>
</div>

<div class="section">
    <h2>5. Approval</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;width:30%">Prepared by</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, Title, Date]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Reviewed by</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, Title, Date]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Approved by</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, Title, Date]</em></td></tr>
    </table>
</div>`;
        },

        risk_register_doc: function(ctx) {
            // Reuse risk_assessment_doc -- it contains the register
            return CodeGenerator._DOC_TEMPLATES.risk_assessment_doc(ctx);
        },

        ai_inventory_doc: function(ctx) {
            return `
<div class="section">
    <h2>AI System Inventory</h2>
    <p>This inventory satisfies requirements for control <strong>${ctx.controlId}</strong> under ${ctx.fwLabel}. Maintain this as a living document.</p>
</div>

<div class="section">
    <h2>Inventory Register</h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">System</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Purpose</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Data Sources</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Model Type</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Risk Tier</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Status</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Owner</th>
        </tr>
        <tr>
            <td style="padding:6px;border:1px solid #e2e8f0"><strong>${ctx.repo}</strong></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Primary purpose]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[List data sources]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[LLM / ML / Rule-based]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[High / Limited / Minimal]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Production</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
        </tr>
        <tr>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[System 2]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Purpose]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Data sources]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Type]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Tier]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Status]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
        </tr>
    </table>
</div>

<div class="section">
    <h2>For Each System, Document</h2>
    <ol>
        <li><strong>Intended use</strong> -- what decisions does it inform or make?</li>
        <li><strong>Training data</strong> -- sources, freshness, known biases</li>
        <li><strong>Users</strong> -- who interacts with it, who is affected by it</li>
        <li><strong>Dependencies</strong> -- third-party models, APIs, data providers</li>
        <li><strong>Risk classification</strong> -- per your applicable regulatory framework</li>
    </ol>
</div>

<div class="section">
    <h2>Maintenance</h2>
    <ul>
        <li>Update upon any new AI system deployment</li>
        <li>Review quarterly for accuracy</li>
        <li>Flag decommissioned systems with end date</li>
    </ul>
    <p style="font-size:12px;color:#64748b">Last updated: ${ctx.date} | Next review: <em>[date]</em></p>
</div>`;
        },

        incident_response_doc: function(ctx) {
            return `
<div class="section">
    <h2>AI Incident Response Plan</h2>
    <p>This plan satisfies requirements for control <strong>${ctx.controlId}</strong> under ${ctx.fwLabel}.</p>
</div>

<div class="section">
    <h2>1. Scope</h2>
    <p>This plan covers AI-specific incidents for <strong>${ctx.repo}</strong> including: model failures, biased outputs, data breaches involving AI systems, adversarial attacks, and unintended harmful outputs.</p>
</div>

<div class="section">
    <h2>2. Severity Levels</h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">Level</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Definition</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Response Time</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Example</th>
        </tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;background:#fecaca;font-weight:600">SEV-1 Critical</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Active harm to users or data breach</td>
            <td style="padding:6px;border:1px solid #e2e8f0">15 minutes</td>
            <td style="padding:6px;border:1px solid #e2e8f0">PII leak, discriminatory decisions</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;background:#fecaca;font-weight:600">SEV-2 High</td>
            <td style="padding:6px;border:1px solid #e2e8f0">System producing incorrect results</td>
            <td style="padding:6px;border:1px solid #e2e8f0">1 hour</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Hallucination in critical path</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;background:#fef3c7;font-weight:600">SEV-3 Medium</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Degraded quality or performance</td>
            <td style="padding:6px;border:1px solid #e2e8f0">4 hours</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Model drift, accuracy drop</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;background:#d1fae5;font-weight:600">SEV-4 Low</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Minor issue, no user impact</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Next business day</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Logging gap, cosmetic error</td></tr>
    </table>
</div>

<div class="section">
    <h2>3. Roles and Contacts</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;width:30%">Incident Lead</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, phone, email]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">AI/ML Engineer</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, phone, email]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Legal/Compliance</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, phone, email]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Executive Escalation</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, phone, email]</em></td></tr>
    </table>
</div>

<div class="section">
    <h2>4. Response Procedure</h2>
    <ol>
        <li><strong>Detect</strong> -- Identify the incident through monitoring, user reports, or automated alerts</li>
        <li><strong>Classify</strong> -- Assign severity level (SEV-1 through SEV-4)</li>
        <li><strong>Contain</strong> -- For SEV-1/2: disable or restrict AI system immediately</li>
        <li><strong>Notify</strong> -- Alert stakeholders per severity level; regulatory notification if required</li>
        <li><strong>Investigate</strong> -- Root cause analysis: what input, what model version, what output</li>
        <li><strong>Remediate</strong> -- Fix the issue; verify fix in staging before redeployment</li>
        <li><strong>Review</strong> -- Post-incident review within 5 business days; update this plan if needed</li>
    </ol>
</div>

<div class="section">
    <h2>5. Drill Schedule</h2>
    <ul>
        <li>Quarterly tabletop exercise simulating an AI incident</li>
        <li>Annual full response drill with stakeholder notification</li>
        <li>Record drill dates, participants, and findings below</li>
    </ul>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">Date</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Type</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Participants</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Findings</th>
        </tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0"><em>[Date]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Tabletop</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Names]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Key findings]</em></td></tr>
    </table>
</div>`;
        },

        governance_charter_doc: function(ctx) {
            return `
<div class="section">
    <h2>AI Governance Charter</h2>
    <p>This charter satisfies requirements for control <strong>${ctx.controlId}</strong> under ${ctx.fwLabel}.</p>
</div>

<div class="section">
    <h2>1. Purpose</h2>
    <p>This charter establishes the governance structure for AI systems at <strong>${ctx.repo}</strong>, defining accountability, decision authority, and review processes to ensure responsible AI development and deployment.</p>
</div>

<div class="section">
    <h2>2. Roles and Responsibilities</h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">Role</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Person</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Responsibilities</th>
        </tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">AI Compliance Lead</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Overall compliance posture, audit coordination, regulatory tracking</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">Technical Lead</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Implementation of controls, code review, security</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">Executive Sponsor</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Budget, strategic direction, escalation authority</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0;font-weight:600">Data Protection</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0">Privacy compliance, DPIA reviews, data handling oversight</td></tr>
    </table>
</div>

<div class="section">
    <h2>3. Decision Authority</h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">Decision</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Authority</th>
        </tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Deploy new AI system</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Executive Sponsor + AI Compliance Lead</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Update existing model</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Technical Lead (with compliance review for major changes)</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Accept compliance risk</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Executive Sponsor (documented)</td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Incident response escalation</td>
            <td style="padding:6px;border:1px solid #e2e8f0">AI Compliance Lead (per IR plan)</td></tr>
    </table>
</div>

<div class="section">
    <h2>4. Review Cadence</h2>
    <ul>
        <li><strong>Monthly</strong>: Compliance scan review (automated via BespokeAgile Comply)</li>
        <li><strong>Quarterly</strong>: Governance meeting -- review risks, controls, incidents, and score trends</li>
        <li><strong>Annually</strong>: Full governance charter review and update</li>
    </ul>
</div>

<div class="section">
    <h2>5. Decision Log</h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">Date</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Decision</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Rationale</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Decided by</th>
        </tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">${ctx.date}</td>
            <td style="padding:6px;border:1px solid #e2e8f0">Established AI governance charter</td>
            <td style="padding:6px;border:1px solid #e2e8f0">${ctx.fwLabel} compliance requirement</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Name]</em></td></tr>
    </table>
</div>

<div class="section">
    <h2>6. Approval</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;width:30%">Effective Date</td>
            <td style="padding:8px;border:1px solid #e2e8f0">${ctx.date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Approved by</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Executive Sponsor, Date]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Version</td>
            <td style="padding:8px;border:1px solid #e2e8f0">1.0</td></tr>
    </table>
</div>`;
        },

        dpia_doc: function(ctx) {
            return `
<div class="section">
    <h2>Data Protection Impact Assessment (DPIA)</h2>
    <p>This DPIA satisfies requirements for control <strong>${ctx.controlId}</strong> under ${ctx.fwLabel}.</p>
</div>

<div class="section">
    <h2>1. System Overview</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;width:30%">System</td>
            <td style="padding:8px;border:1px solid #e2e8f0">${ctx.repo}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Processing Purpose</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[What personal data is processed and why]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Data Subjects</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Who is affected: users, employees, customers]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Legal Basis</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Consent / Legitimate interest / Contract / Legal obligation]</em></td></tr>
    </table>
</div>

<div class="section">
    <h2>2. Impact Analysis</h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="background:#f8fafc">
            <th style="padding:6px;border:1px solid #e2e8f0">Impact Area</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Potential Impact</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Severity</th>
            <th style="padding:6px;border:1px solid #e2e8f0">Mitigation</th>
        </tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Privacy</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[How could AI affect privacy?]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[H/M/L]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Controls in place]</em></td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Fairness</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Bias or discrimination risks]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[H/M/L]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Controls in place]</em></td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Autonomy</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Effect on individual decision-making]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[H/M/L]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Controls in place]</em></td></tr>
        <tr><td style="padding:6px;border:1px solid #e2e8f0">Safety</td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Physical or psychological harm risks]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[H/M/L]</em></td>
            <td style="padding:6px;border:1px solid #e2e8f0"><em>[Controls in place]</em></td></tr>
    </table>
</div>

<div class="section">
    <h2>3. Conclusion</h2>
    <p><em>[State whether processing can proceed, under what conditions, and what residual risks are accepted.]</em></p>

    <h2>4. Approval</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;width:30%">Assessed by</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, Title, ${ctx.date}]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">DPO Review</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Name, Date]</em></td></tr>
        <tr><td style="padding:8px;border:1px solid #e2e8f0;font-weight:600">Decision</td>
            <td style="padding:8px;border:1px solid #e2e8f0"><em>[Proceed / Proceed with conditions / Do not proceed]</em></td></tr>
    </table>
</div>`;
        },

        transparency_notice_doc: function(ctx) {
            return `
<div class="section">
    <h2>AI Transparency Notice</h2>
    <p>This notice satisfies requirements for control <strong>${ctx.controlId}</strong> under ${ctx.fwLabel}. Publish this on your website or in your product documentation.</p>
</div>

<div class="section">
    <h2>AI System Disclosure</h2>

    <h3>What AI Does in This Product</h3>
    <p><em>[Describe in plain language what AI features your product includes and what decisions they assist or make. Be specific about which features use AI.]</em></p>

    <h3>Data We Use</h3>
    <p><em>[Describe what data the AI system collects, processes, and retains. Include: input data, training data, and output data.]</em></p>

    <h3>How Decisions Are Made</h3>
    <p><em>[Explain the general logic of AI-driven decisions. You do not need to reveal proprietary algorithms, but users should understand the factors considered.]</em></p>

    <h3>Limitations</h3>
    <ul>
        <li><em>[AI outputs are advisory and may contain errors]</em></li>
        <li><em>[The system may not perform equally across all use cases]</em></li>
        <li><em>[List any known biases or limitations]</em></li>
    </ul>

    <h3>Your Rights</h3>
    <ul>
        <li>You may request human review of any AI-assisted decision</li>
        <li>You may opt out of AI-driven features where applicable</li>
        <li>You may request an explanation of how a specific decision was made</li>
        <li>Contact: <em>[compliance-team@your-org.com]</em></li>
    </ul>

    <h3>Human Oversight</h3>
    <p>All AI-generated results are subject to human review. <em>[Describe your oversight process.]</em></p>
</div>

<div class="section">
    <p style="font-size:12px;color:#64748b">Last updated: ${ctx.date} | Version 1.0</p>
</div>`;
        },
    },

    /** Generate a document template for a non-code control. Opens in new tab. */
    generateDoc(templateId, remediation, report) {
        const template = this._DOC_TEMPLATES[templateId];
        if (!template) {
            return alert(`No document template for ${templateId}.`);
        }

        const ctx = {
            repo: (report.target || '').replace(/.*\//, '') || 'your-repo',
            framework: report.framework || '',
            fwLabel: typeof fwLabel === 'function' ? fwLabel(report.framework) : report.framework,
            controlId: remediation ? (remediation.controlId || '') : '',
            date: new Date().toISOString().split('T')[0],
        };

        const content = template(ctx);
        this._openDoc(content, ctx, templateId);
    },

    /** Open a document template in a new tab. */
    _openDoc(content, ctx, templateId) {
        const title = templateId.replace(/_doc$/, '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>${this._esc(title)}: ${this._esc(ctx.controlId)} - ${this._esc(ctx.fwLabel)}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: #1a1a2e; line-height: 1.6; background: #fff; max-width: 900px; margin: 0 auto; padding: 40px 60px; }
h1 { font-size: 24px; font-weight: 300; margin-bottom: 4px; }
h2 { font-size: 18px; font-weight: 600; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #e2e8f0; }
h3 { font-size: 14px; font-weight: 600; margin: 16px 0 8px; color: #334155; }
.brand { font-size: 12px; letter-spacing: 2px; text-transform: uppercase; color: #64748b; margin-bottom: 16px; }
.meta { font-size: 13px; color: #64748b; margin-bottom: 24px; }
.info { background: #eff6ff; border: 1px solid #93c5fd; border-radius: 8px; padding: 12px 16px; font-size: 13px; color: #1e40af; margin-bottom: 24px; }
p { font-size: 14px; color: #475569; margin-bottom: 12px; }
ul, ol { font-size: 14px; color: #475569; margin: 8px 0 16px 24px; }
li { margin-bottom: 4px; }
em { color: #94a3b8; }
.section { margin-bottom: 32px; }
.disclaimer { font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 32px; }
@media print { body { padding: 20px; } }
</style>
</head>
<body>
<div class="brand">BespokeAgile Comply</div>
<h1>${this._esc(title)}</h1>
<div class="meta">${this._esc(ctx.fwLabel)} | ${this._esc(ctx.repo)} | ${ctx.date}</div>
<div class="info">
    <strong>Template.</strong> Fill in the sections marked in <em>italics</em> with your organization's details.
    Print or save this page as your compliance documentation.
</div>
${content}
<div class="disclaimer">
    Generated by BespokeAgile Comply. This template provides structure for compliance documentation.
    It must be completed with your organization's specific details to serve as evidence.
</div>
</body>
</html>`;

        const w = window.open('', '_blank');
        if (!w) return alert('Pop-up blocked. Please allow pop-ups for this site.');
        w.document.write(html);
        w.document.close();
    },

};
