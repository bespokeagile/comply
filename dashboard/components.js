/* Framework ID → human-friendly label */
const FW_LABELS = {
    'eu_ai_act': 'EU AI Act',
    'soc2_ai': 'SOC 2 AI',
    'nist_ai_rmf': 'NIST AI RMF',
    'iso_42001': 'ISO 42001',
    'california_ab_2013': 'California AB 2013',
    'california_sb_942': 'California SB 942',
    'colorado_sb_24_205': 'Colorado SB 24-205',
    'insurance_attestation': 'Insurance Attestation',
    'owasp_llm_top10': 'OWASP LLM Top 10',
    'owasp_agentic_top10': 'OWASP Agentic Top 10',
};

/** Normalize framework ID: hyphens → underscores for consistent grouping. */
function fwNorm(fw) {
    return (fw || '').replace(/-/g, '_');
}

function fwLabel(fw) {
    return FW_LABELS[fwNorm(fw)] || fw;
}

/* Per-evidence-function guidance: what auditors expect and regulatory context. */
const CONTROL_GUIDANCE = {
    // ── Code controls (gap = write/modify code) ────────────────────────
    evidence_audit_logging: {
        category: 'code',
        auditorExpects: 'Structured audit logs capturing who did what, when, and why. Logs should be tamper-evident, retained per policy, and include AI-specific events (model invocations, data access, decision outputs).',
        context: 'Audit logging is foundational across nearly all compliance frameworks. It provides the evidence trail that proves other controls are functioning.',
    },
    evidence_traceability: {
        category: 'code',
        auditorExpects: 'End-to-end traceability from data input through model processing to output. Ability to reconstruct any AI decision after the fact.',
        context: 'Traceability enables accountability. Regulators want to know that AI decisions can be explained and reproduced when challenged.',
    },
    evidence_transparency_logging: {
        category: 'code',
        auditorExpects: 'Logs that capture what was disclosed to users, when, and through which channel. Proof that transparency obligations were met for each interaction.',
        context: 'Logging transparency events proves compliance with disclosure requirements and provides evidence in disputes.',
    },
    evidence_continuous_monitoring: {
        category: 'code',
        auditorExpects: 'Active monitoring of AI system performance, drift detection, anomaly alerting, and documented response procedures when thresholds are breached.',
        context: 'AI systems degrade over time. Continuous monitoring ensures that compliance posture does not silently erode after initial deployment.',
    },
    evidence_performance_measurement: {
        category: 'code',
        auditorExpects: 'Defined performance metrics (accuracy, fairness, latency), test suites that measure them, and evidence of regular testing against benchmarks.',
        context: 'Performance measurement validates that AI systems work as intended. Without it, compliance claims are unsubstantiated.',
    },
    evidence_logical_access: {
        category: 'code',
        auditorExpects: 'Role-based access controls, authentication mechanisms, access logs, and periodic access reviews for AI systems and their data.',
        context: 'Access control prevents unauthorized use or modification of AI systems. It is a baseline security control required by virtually all frameworks.',
    },
    evidence_data_handling: {
        category: 'code',
        auditorExpects: 'Data classification, handling procedures, retention policies, consent tracking, and evidence of data minimization for AI training and inference.',
        context: 'AI systems consume and produce data. Proper handling ensures privacy compliance and reduces risk of data breaches or misuse.',
    },
    evidence_change_management: {
        category: 'code',
        auditorExpects: 'A documented change management process covering model updates, data changes, and infrastructure modifications. Approval workflows, rollback procedures, and impact assessments.',
        context: 'Uncontrolled changes to AI systems can introduce bias, errors, or security vulnerabilities. Change management ensures modifications are deliberate and reviewed.',
    },
    evidence_human_oversight_gateway: {
        category: 'code',
        auditorExpects: 'Mechanisms for human review of AI decisions, escalation paths, override capabilities, and evidence that human oversight is exercised in practice.',
        context: 'Human oversight is a core requirement of the EU AI Act and many other frameworks. The key is demonstrating that oversight is real, not theoretical.',
    },
    evidence_consumer_notification: {
        category: 'code',
        auditorExpects: 'Notification mechanisms that inform affected individuals about AI-driven decisions, their rights to contest, and how to request human review.',
        context: 'Consumer notification requirements are growing. Many jurisdictions now require proactive disclosure when AI affects consumer outcomes.',
    },
    evidence_availability_controls: {
        category: 'code',
        auditorExpects: 'Redundancy, failover mechanisms, SLAs, and evidence that AI systems maintain availability targets. Graceful degradation when AI components fail.',
        context: 'AI system availability matters when downstream processes depend on it. Controls ensure that AI failures do not cascade into business disruptions.',
    },
    evidence_retention_compliance: {
        category: 'code',
        auditorExpects: 'Data retention policies, automated enforcement, and evidence that AI training data and outputs are retained or purged per regulatory requirements.',
        context: 'Retention compliance balances keeping data long enough for auditing with deleting it when required by privacy regulations.',
    },
    evidence_input_sanitization: {
        category: 'code',
        auditorExpects: 'Input validation, sanitization routines, and evidence that AI systems reject or handle malformed, adversarial, or out-of-distribution inputs safely.',
        context: 'Input sanitization prevents prompt injection, data poisoning, and adversarial attacks. It is a security-critical control for LLM-based systems.',
    },
    evidence_output_validation: {
        category: 'code',
        auditorExpects: 'Output filtering, content safety checks, and validation that AI outputs meet quality and safety standards before reaching users.',
        context: 'Output validation ensures AI systems do not produce harmful, biased, or incorrect responses. Critical for customer-facing applications.',
    },
    evidence_model_provenance: {
        category: 'code',
        auditorExpects: 'Documentation of model origin, training data sources, fine-tuning history, and a chain of custody from development through deployment.',
        context: 'Model provenance establishes trust in the AI supply chain. It answers: where did this model come from, and can we trust it?',
    },
    evidence_prompt_protection: {
        category: 'code',
        auditorExpects: 'Defenses against prompt injection, jailbreaking, and prompt leaking. Testing evidence showing resistance to common attack patterns.',
        context: 'Prompt protection is specific to LLM-based systems. Without it, users can manipulate AI behavior in unintended and potentially harmful ways.',
    },
    evidence_embedding_security: {
        category: 'code',
        auditorExpects: 'Security controls on vector databases, embedding pipelines, and retrieval-augmented generation (RAG) systems. Access controls and data isolation.',
        context: 'Embeddings can leak sensitive information. Securing the embedding pipeline prevents unauthorized data access through similarity search.',
    },
    evidence_consumption_limits: {
        category: 'code',
        auditorExpects: 'Rate limiting, token budgets, cost controls, and evidence that AI resource consumption is monitored and bounded.',
        context: 'Consumption limits prevent denial-of-wallet attacks and ensure AI systems operate within budgeted resource constraints.',
    },
    evidence_access_control: {
        category: 'code',
        auditorExpects: 'Fine-grained access control for LLM endpoints, API key management, and authorization checks on AI-specific operations.',
        context: 'LLM access control goes beyond traditional RBAC. It includes controlling who can invoke models, with what parameters, and at what cost.',
    },
    evidence_mcp_server_security: {
        category: 'code',
        auditorExpects: 'Security controls on MCP (Model Context Protocol) servers, tool authorization, sandboxing, and audit logging of tool invocations.',
        context: 'MCP servers extend LLM capabilities with external tools. Each tool is an attack surface that requires authorization and monitoring.',
    },
    evidence_ai_supply_chain: {
        category: 'code',
        auditorExpects: 'Inventory of AI dependencies (models, libraries, data sources), vulnerability scanning, and vendor risk assessment for third-party AI components.',
        context: 'AI supply chain security addresses risks from dependencies you did not build. Compromised models or libraries can undermine all other controls.',
    },

    // ── Documentation controls (gap = create a document) ──────────────
    evidence_risk_assessment_gateway: {
        category: 'documentation',
        quickStart: 'Create a risk assessment listing your AI systems, their risk levels, and mitigations. Use the template below as a starting point.',
        templateId: 'risk_assessment_doc',
        auditorExpects: 'A documented risk assessment methodology, a risk register with identified risks, likelihood/impact ratings, and evidence of periodic review.',
        context: 'Risk assessment is the starting point for most AI governance frameworks. Without it, other controls lack a foundation for prioritization.',
    },
    evidence_risk_categorization: {
        category: 'documentation',
        quickStart: 'Document your risk classification criteria (high/medium/low) and which category each AI system falls into.',
        templateId: 'risk_assessment_doc',
        auditorExpects: 'A classification system for AI risks (e.g., high/medium/low), criteria for categorization, and documentation of which category each system falls into.',
        context: 'Risk categorization determines which controls apply. EU AI Act explicitly requires high-risk classification before other obligations trigger.',
    },
    evidence_risk_register_auto: {
        category: 'documentation',
        quickStart: 'Start a risk register with the gaps found in this scan. Assign an owner and mitigation plan to each risk.',
        templateId: 'risk_register_doc',
        auditorExpects: 'A maintained risk register with identified risks, owners, mitigations, status, and review dates. Automated detection of new risks from code changes is a strong signal.',
        context: 'The risk register is a living document. Auditors check that it is actively maintained, not just created and forgotten.',
    },
    evidence_governance_policy: {
        category: 'documentation',
        quickStart: 'Write a one-page AI governance policy naming roles, responsibilities, and a quarterly review cadence.',
        templateId: 'governance_charter_doc',
        auditorExpects: 'A formal AI governance policy document defining roles, responsibilities, decision authority, review cadence, and escalation procedures.',
        context: 'Governance policy is the organizational commitment to responsible AI. It creates the framework within which all other controls operate.',
    },
    evidence_ai_system_inventory: {
        category: 'documentation',
        quickStart: 'List every AI system your organization uses: its purpose, data sources, model type, and who owns it.',
        templateId: 'ai_inventory_doc',
        auditorExpects: 'A complete inventory of AI systems including purpose, data sources, model type, deployment status, risk classification, and responsible owner.',
        context: 'You cannot govern what you do not know exists. An AI system inventory is the foundation for any compliance program.',
    },
    evidence_impact_documentation: {
        category: 'documentation',
        quickStart: 'Complete a Data Protection Impact Assessment (DPIA) covering your AI system\'s effects on individuals and groups.',
        templateId: 'dpia_doc',
        auditorExpects: 'Impact assessments documenting potential effects on individuals and groups, fairness analysis, and mitigation measures for identified harms.',
        context: 'Impact documentation demonstrates due diligence. It shows that potential harms were considered before deployment, not discovered after.',
    },
    evidence_transparency_disclosure: {
        category: 'documentation',
        quickStart: 'Write a public disclosure statement explaining what AI does in your product, what data it uses, and how users can request human review.',
        templateId: 'transparency_notice_doc',
        auditorExpects: 'User-facing disclosure that they are interacting with AI, what data is collected, how decisions are made, and how to request human review.',
        context: 'Transparency requirements are expanding globally. Users must know when AI is involved in decisions that affect them.',
    },

    // ── Process controls (gap = establish organizational practice) ─────
    evidence_incident_response: {
        category: 'process',
        quickStart: 'Name an incident response lead, define 4 severity levels, write a one-page response playbook, and schedule a quarterly drill.',
        templateId: 'incident_response_doc',
        auditorExpects: 'An incident response plan specific to AI failures, defined severity levels, notification procedures, root cause analysis templates, and evidence of drills or past responses.',
        context: 'When AI systems fail, the response must be swift and documented. Regulators increasingly require AI-specific incident response capabilities.',
    },
    evidence_governance_program: {
        category: 'process',
        quickStart: 'Designate an AI compliance lead, schedule quarterly governance reviews, and start a decision log.',
        templateId: 'governance_charter_doc',
        auditorExpects: 'An active governance program with designated leadership, regular meetings, documented decisions, and evidence of organizational commitment beyond policy.',
        context: 'A governance program demonstrates that policy is implemented, not just written. Auditors look for meeting minutes, decision logs, and resource allocation.',
    },
};

/* Reusable UI components */
const Components = {

    CONTROL_GUIDANCE,

    renderScoreGauge(score, size = 100) {
        const r = (size - 10) / 2;
        const circ = 2 * Math.PI * r;
        const pct = Math.min(100, Math.max(0, score));
        const offset = circ - (pct / 100) * circ;
        const color = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';

        return `
        <div class="score-gauge" role="img" aria-label="Compliance score: ${Math.round(score)} percent">
            <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
                <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none"
                    stroke="var(--border)" stroke-width="6"/>
                <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none"
                    stroke="${color}" stroke-width="6"
                    stroke-dasharray="${circ}" stroke-dashoffset="${offset}"
                    stroke-linecap="round"
                    transform="rotate(-90 ${size/2} ${size/2})"
                    style="transition: stroke-dashoffset 0.6s ease"/>
                <text x="${size/2}" y="${size/2 + 6}" text-anchor="middle"
                    fill="${color}" font-size="${size/4}" font-weight="700">${Math.round(score)}%</text>
            </svg>
        </div>`;
    },

    /** Compute per-category (code/documentation/process) breakdown from report. */
    computeCategoryBreakdown(report) {
        const cats = { code: { met: 0, total: 0 }, documentation: { met: 0, total: 0 }, process: { met: 0, total: 0 } };
        const articles = report.articles || [];
        for (const art of articles) {
            for (const ctrl of (art.controls || [])) {
                const g = CONTROL_GUIDANCE[ctrl.evidence_fn] || {};
                const cat = g.category || 'code';
                cats[cat].total++;
                if (ctrl.status === 'met') cats[cat].met++;
                else if (ctrl.status === 'partial') cats[cat].met += 0.5;
            }
        }
        return cats;
    },

    /** Render compact category breakdown bars. */
    renderCategoryBreakdown(report) {
        const cats = this.computeCategoryBreakdown(report);
        const items = [
            { key: 'code', label: 'Code', color: 'var(--accent)' },
            { key: 'documentation', label: 'Documentation', color: 'var(--yellow)' },
            { key: 'process', label: 'Process', color: 'var(--purple, #a78bfa)' },
        ];

        let html = '<div class="category-breakdown">';
        for (const item of items) {
            const c = cats[item.key];
            if (c.total === 0) continue;
            const pct = Math.round((c.met / c.total) * 100);
            const barWidth = Math.max(2, pct);
            html += `
            <div class="category-row">
                <span class="category-label">${item.label}</span>
                <div class="category-bar-track">
                    <div class="category-bar-fill" style="width:${barWidth}%;background:${item.color}"></div>
                </div>
                <span class="category-score">${Math.round(c.met)}/${c.total}</span>
            </div>`;
        }
        html += '</div>';
        return html;
    },

    renderStatusBadge(status) {
        const cls = `status-${status || 'gap'}`;
        const label = status === 'met' ? 'Requirement met' : status === 'partial' ? 'Partially met' : 'Gap identified';
        return `<span class="status-badge ${cls}" role="status" aria-label="${label}">${(status || 'gap').toUpperCase()}</span>`;
    },

    renderLayerPills(layers) {
        if (!layers) return '';
        const names = { code: 'L1', process: 'L2', traffic: 'L3' };
        let html = '<div class="layer-pills">';
        for (const [key, label] of Object.entries(names)) {
            const status = layers[key]?.status || 'gap';
            html += `<span class="layer-pill ${status}">${label}:${status}</span>`;
        }
        html += '</div>';
        return html;
    },

    // Map evidence_fn to artifact template IDs (for template linkage)
    _EVIDENCE_TEMPLATE_MAP: {
        evidence_risk_assessment_gateway: 'risk-assessment',
        evidence_risk_categorization: 'risk-assessment',
        evidence_risk_register_auto: 'risk-assessment',
        evidence_governance_policy: 'governance-policy',
        evidence_governance_program: 'governance-policy',
        evidence_transparency_disclosure: 'transparency-notice',
        evidence_transparency_logging: 'transparency-notice',
        evidence_consumer_notification: 'transparency-notice',
        evidence_audit_logging: 'audit-log-schema',
        evidence_traceability: 'audit-log-schema',
        evidence_performance_measurement: 'testing-plan',
        evidence_continuous_monitoring: 'testing-plan',
    },

    renderControlRow(ctrl, options) {
        const status = ctrl.status || ctrl.combinedStatus || 'gap';
        const layers = ctrl.layers;
        const opts = options || {};
        const evidenceFn = ctrl.evidence_fn || '';
        const guidance = evidenceFn ? (this.CONTROL_GUIDANCE[evidenceFn] || null) : null;
        const hasSemantic = ctrl.semanticAnalysis && ctrl.semanticAnalysis.length > 0;
        const hasDetail = guidance || (ctrl.evidence && ctrl.evidence.length > 0) || ctrl.recommendation || hasSemantic;
        const uid = 'ctrl-' + (ctrl.controlId || '').replace(/[^a-zA-Z0-9]/g, '-');

        // Find related remediation if available
        const remediation = opts.remediations
            ? opts.remediations.find(r => r.controlId === ctrl.controlId)
            : null;

        let detailHtml = '';
        if (hasDetail) {
            detailHtml = `<tr class="control-detail-row" id="${uid}-detail" style="display:none"><td colspan="4"><div class="control-detail">`;

            // Semantic analysis (codebase-specific insight from LLM) -- shown first when present
            if (hasSemantic) {
                detailHtml += `<div class="control-detail-section control-semantic-section">
                    <div class="control-detail-label">Codebase analysis</div>
                    <div class="control-detail-text">${ctrl.semanticAnalysis}</div>
                </div>`;
            }

            // Requirement (full text)
            if (ctrl.requirement && ctrl.requirement.length > 120) {
                detailHtml += `<div class="control-detail-section"><strong>Requirement:</strong> ${ctrl.requirement}</div>`;
            }

            // Auditor guidance
            if (guidance) {
                detailHtml += `<div class="control-detail-section">
                    <div class="control-detail-label">What auditors look for</div>
                    <div class="control-detail-text">${guidance.auditorExpects}</div>
                </div>`;
                if (guidance.context) {
                    detailHtml += `<div class="control-detail-section">
                        <div class="control-detail-label">Regulatory context</div>
                        <div class="control-detail-text">${guidance.context}</div>
                    </div>`;
                }
            }

            // Evidence found with quality indicator
            if (ctrl.evidence && ctrl.evidence.length > 0) {
                const evCount = ctrl.evidence.length;
                const qualityClass = evCount >= 3 ? 'strong' : evCount >= 2 ? 'moderate' : 'weak';
                const qualityLabel = evCount >= 3 ? 'Strong' : evCount >= 2 ? 'Moderate' : 'Weak';
                detailHtml += `<div class="control-detail-section">
                    <div class="control-detail-label">Evidence found <span class="evidence-quality ${qualityClass}">${qualityLabel}</span></div>
                    ${ctrl.evidence.map(e => `<div class="control-evidence-item">${typeof e === 'string' ? e : (e.description || e.file || JSON.stringify(e))}</div>`).join('')}
                </div>`;
            }

            // Gaps
            if (ctrl.gaps && ctrl.gaps.length > 0) {
                detailHtml += `<div class="control-detail-section">
                    <div class="control-detail-label" style="color:var(--red)">Gaps</div>
                    ${ctrl.gaps.map(g => `<div class="control-evidence-item">${g}</div>`).join('')}
                </div>`;
            }

            // Remediation action (from graph-aware remediation)
            if (remediation) {
                detailHtml += `<div class="control-detail-section">
                    <div class="control-detail-label" style="color:var(--green)">Suggested action</div>
                    <div class="control-detail-text">${remediation.action || remediation.summary || ''}</div>
                    ${(remediation.relatedFiles || []).length > 0
                        ? `<div class="control-detail-files">${remediation.relatedFiles.map(f => `<code>${f}</code>`).join(' ')}</div>`
                        : ''}
                </div>`;
            } else if (ctrl.recommendation) {
                detailHtml += `<div class="control-detail-section">
                    <div class="control-detail-label">Recommendation</div>
                    <div class="control-detail-text">${ctrl.recommendation}</div>
                </div>`;
            }

            // Template linkage for gap/partial controls
            if ((status === 'gap' || status === 'partial') && evidenceFn) {
                const templateId = this._EVIDENCE_TEMPLATE_MAP[evidenceFn];
                if (templateId && typeof DetailView !== 'undefined') {
                    const templateNames = {
                        'risk-assessment': 'Risk Assessment Template',
                        'governance-policy': 'AI Governance Policy',
                        'transparency-notice': 'Transparency Notice',
                        'audit-log-schema': 'Audit Log Schema',
                        'testing-plan': 'Compliance Test Plan',
                    };
                    detailHtml += `<div class="control-detail-section control-template-link">
                        <button class="btn btn-sm" onclick="event.stopPropagation(); DetailView._downloadArtifact('${templateId}')">
                            Generate ${templateNames[templateId] || 'Template'}
                        </button>
                    </div>`;
                }
            }

            // Cross-framework reference
            if (evidenceFn && opts.overlapMatrix) {
                const cap = opts.overlapMatrix.capabilities.find(c => c.evidence_fn === evidenceFn);
                if (cap && cap.frameworkCount > 1) {
                    const otherFws = Object.keys(cap.frameworks)
                        .filter(fw => fw !== opts.currentFramework)
                        .map(fw => {
                            const ctrls = cap.frameworks[fw].controls || [cap.frameworks[fw]];
                            const ids = ctrls.map(c => c.controlId).join(', ');
                            const fwName = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
                            return `${fwName} (${ids})`;
                        });
                    if (otherFws.length > 0) {
                        detailHtml += `<div class="control-detail-section control-cross-fw">
                            <div class="control-detail-label">Also satisfies</div>
                            <div class="control-detail-text">${otherFws.join(', ')}</div>
                        </div>`;
                    }
                }
            }

            detailHtml += '</div></td></tr>';
        }

        const carriedFwd = ctrl.evaluation_source === 'carried_forward';

        return `
        <tr class="${hasDetail ? 'control-expandable' : ''}" data-control-id="${ctrl.controlId || ''}" ${hasDetail ? `onclick="Components.toggleControlDetail('${uid}')"` : ''}>
            <td>${Components.renderStatusBadge(status)}</td>
            <td><strong>${ctrl.controlId || ''}</strong>${carriedFwd ? '<span class="carried-fwd-badge" title="Carried forward from baseline scan">baseline</span>' : ''}</td>
            <td>${(ctrl.requirement || '').substring(0, 120)}${(ctrl.requirement || '').length > 120 ? '...' : ''}${hasDetail ? ' <span class="control-expand-hint">&#9656;</span>' : ''}</td>
            <td>${layers ? Components.renderLayerPills(layers) : ''}</td>
        </tr>${detailHtml}`;
    },

    toggleControlDetail(uid) {
        const row = document.getElementById(uid + '-detail');
        if (row) {
            const visible = row.style.display !== 'none';
            row.style.display = visible ? 'none' : 'table-row';
            // Toggle chevron on parent row
            const trigger = row.previousElementSibling;
            if (trigger) trigger.classList.toggle('control-expanded', !visible);
        }
    },

    renderArticleAccordion(article, index, prefix, remediations) {
        const controls = article.controls || [];
        const met = article.met || 0;
        const partial = article.partial || 0;
        const gap = article.gap || 0;
        const id = (prefix || 'article') + '-' + index;
        const rowOpts = remediations ? { remediations } : {};

        return `
        <div class="accordion-item" id="${id}" data-article-id="${article.articleId || ''}">
            <div class="accordion-header" onclick="Components.toggleAccordion('${id}')">
                <span>
                    <strong>${article.articleId || ''}</strong>: ${article.label || ''}
                    <span style="margin-left:12px;font-size:12px;color:var(--text-muted)">
                        <span style="color:var(--green)">${met} met</span>
                        <span style="color:var(--yellow)">${partial} partial</span>
                        <span style="color:var(--red)">${gap} gap</span>
                    </span>
                </span>
                <span class="accordion-chevron">&#9656;</span>
            </div>
            <div class="accordion-body">
                <table class="data-table">
                    <thead>
                        <tr><th>Status</th><th>Control</th><th>Requirement</th><th>Layers</th></tr>
                    </thead>
                    <tbody>
                        ${controls.map(c => Components.renderControlRow(c, rowOpts)).join('')}
                    </tbody>
                </table>
            </div>
        </div>`;
    },

    toggleAccordion(id) {
        document.getElementById(id)?.classList.toggle('open');
    },

    renderLineChart(data, width = 600, height = 200) {
        if (!data || data.length === 0) return '<div class="empty-state">No data to chart</div>';

        const padding = { top: 20, right: 20, bottom: 30, left: 40 };
        const w = width - padding.left - padding.right;
        const h = height - padding.top - padding.bottom;

        const scores = data.map(d => d.score || 0);
        const maxScore = Math.max(100, ...scores);
        const minScore = Math.min(0, ...scores);
        const range = maxScore - minScore || 1;

        const points = data.map((d, i) => {
            const x = padding.left + (i / Math.max(1, data.length - 1)) * w;
            const y = padding.top + h - ((d.score - minScore) / range) * h;
            return { x, y, d };
        });

        const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

        let svg = `<svg width="${width}" height="${height}" class="line-chart">`;
        // Grid lines
        for (let i = 0; i <= 4; i++) {
            const y = padding.top + (i / 4) * h;
            const val = Math.round(maxScore - (i / 4) * range);
            svg += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"
                     stroke="var(--border)" stroke-dasharray="4,4"/>`;
            svg += `<text x="${padding.left - 8}" y="${y + 4}" text-anchor="end"
                     fill="var(--text-muted)" font-size="10">${val}</text>`;
        }
        // Line
        svg += `<path d="${pathD}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
        // Points
        for (const p of points) {
            const color = p.d.score >= 70 ? 'var(--green)' : p.d.score >= 40 ? 'var(--yellow)' : 'var(--red)';
            svg += `<circle cx="${p.x}" cy="${p.y}" r="4" fill="${color}" stroke="var(--bg-secondary)" stroke-width="2">
                <title>${p.d.label || ''}: ${p.d.score}%</title></circle>`;
        }
        // X-axis labels
        const step = Math.max(1, Math.floor(data.length / 6));
        for (let i = 0; i < data.length; i += step) {
            const p = points[i];
            const label = (data[i].date || '').substring(5, 10);
            svg += `<text x="${p.x}" y="${height - 5}" text-anchor="middle"
                     fill="var(--text-muted)" font-size="10">${label}</text>`;
        }
        svg += '</svg>';
        return svg;
    },

    renderTable(headers, rows) {
        let html = '<table class="data-table"><thead><tr>';
        headers.forEach(h => { html += `<th>${h}</th>`; });
        html += '</tr></thead><tbody>';
        rows.forEach(row => {
            html += '<tr>';
            row.forEach(cell => { html += `<td>${cell}</td>`; });
            html += '</tr>';
        });
        html += '</tbody></table>';
        return html;
    },

    renderProgressStepper(steps, currentStep) {
        let html = '<div class="progress-stepper" role="progressbar" aria-label="Scan progress">';
        const stepNames = steps || ['Clone', 'Scan', 'Build', 'Evaluate', 'Done'];
        const idx = stepNames.findIndex(s => s.toLowerCase() === (currentStep || '').toLowerCase());
        const pct = idx >= 0 ? Math.round((idx / (stepNames.length - 1)) * 100) : 0;
        html = `<div class="progress-stepper" role="progressbar" aria-label="Scan progress" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">`;
        stepNames.forEach((name, i) => {
            const cls = i < idx ? 'done' : i === idx ? 'active' : '';
            html += `<div class="step ${cls}" aria-current="${i === idx ? 'step' : 'false'}">${name}</div>`;
        });
        html += '</div>';
        return html;
    },

    /** Compact report: gauge left, article stacked-bar chart right. */
    renderCompactReport(report) {
        const summary = report.summary || {};
        const score = summary.score || 0;
        const articles = report.articles || [];
        const framework = report.framework || 'unknown';

        return `
        <div class="browse-report-compact">
            <div class="browse-report-gauge">
                ${Components.renderScoreGauge(score, 80)}
                <div class="browse-report-meta">
                    <span style="font-size:12px;color:var(--text-muted)">${fwLabel(framework)}</span>
                    <span style="font-size:11px;color:var(--text-muted)">${report.scanDepth || 'structure'} depth</span>
                </div>
            </div>
            <div class="browse-report-articles">
                ${articles.map(art => {
                    const total = (art.met || 0) + (art.partial || 0) + (art.gap || 0);
                    if (total === 0) return '';
                    const metPct = ((art.met || 0) / total * 100).toFixed(0);
                    const partialPct = ((art.partial || 0) / total * 100).toFixed(0);
                    const gapPct = ((art.gap || 0) / total * 100).toFixed(0);
                    return `
                    <div class="article-bar-row">
                        <span class="article-bar-label">${art.label || art.articleId || ''}</span>
                        <div class="article-bar-track">
                            ${art.met ? `<div class="article-bar-seg met" style="width:${metPct}%"></div>` : ''}
                            ${art.partial ? `<div class="article-bar-seg partial" style="width:${partialPct}%"></div>` : ''}
                            ${art.gap ? `<div class="article-bar-seg gap" style="width:${gapPct}%"></div>` : ''}
                        </div>
                        <span class="article-bar-counts">${art.met || 0}/${art.partial || 0}/${art.gap || 0}</span>
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    },

    /** Compare score header: two score boxes with arrow and delta badge. */
    renderCompareScoreHeader({ score1, score2, id1, id2, label1, label2, class1, class2, delta }) {
        const d = delta != null ? delta : score2 - score1;
        return `
        <div class="compare-view-header">
            <a href="#/detail/${id1}" class="compare-score-box ${class1 || ''}" style="text-decoration:none;color:inherit">
                <div class="compare-score-label">${label1}</div>
                ${Components.renderScoreGauge(score1, 80)}
                <div class="compare-detail-link">View details &#8250;</div>
            </a>
            <div>
                <div class="compare-arrow">&#8594;</div>
                <div class="compare-delta ${d > 0 ? 'positive' : d < 0 ? 'negative' : 'neutral'}">
                    ${d > 0 ? '+' : ''}${d.toFixed(1)}%
                </div>
            </div>
            <a href="#/detail/${id2}" class="compare-score-box ${class2 || ''}" style="text-decoration:none;color:inherit">
                <div class="compare-score-label">${label2}</div>
                ${Components.renderScoreGauge(score2, 80)}
                <div class="compare-detail-link">View details &#8250;</div>
            </a>
        </div>`;
    },

    /** Source badge: "Demo" or "Your Scan" chip. */
    renderSourceBadge(source) {
        if (source === 'demo') return '<span class="scan-source-badge demo">Demo</span>';
        if (source === 'user') return '<span class="scan-source-badge user">Your Scan</span>';
        return '';
    },

    // ── Code Generation ─────────────────────────────────────────────
    _activeReport: null,

    _generateCode(controlId) {
        if (typeof CodeGenerator === 'undefined') return alert('Code generator not available.');
        const state = this._whatIfState;
        const rem = state.remediations.find(r => r.controlId === controlId);
        if (!rem) return alert('Remediation not found.');
        // Get active report from DetailView or CompareView
        const report = this._activeReport
            || (typeof DetailView !== 'undefined' && DetailView._report)
            || (typeof CompareView !== 'undefined' && (CompareView._report2 || CompareView._report1))
            || {};
        CodeGenerator.generate(rem, report);
    },

    // ── What-If Simulator State ────────────────────────────────────
    _whatIfState: { remediations: [], nonCodeItems: [], currentScore: 0, selected: new Set(), summary: {}, scanId: '' },

    initWhatIf(remediations, currentScore, summary, nonCodeItems, scanId) {
        const done = this.getDoneControls(scanId);
        const selected = new Set();
        // Auto-select done items
        for (const item of (nonCodeItems || [])) {
            if (done.has(item.controlId)) selected.add(item.controlId);
        }
        this._whatIfState = {
            remediations, nonCodeItems: nonCodeItems || [],
            currentScore, selected, summary: summary || {}, scanId: scanId || '',
        };
    },

    toggleWhatIf(controlId) {
        const s = this._whatIfState.selected;
        if (s.has(controlId)) s.delete(controlId);
        else s.add(controlId);
        this._syncCheckboxes();
        this._updateWhatIfDisplay();
    },

    selectQuickWins() {
        const state = this._whatIfState;
        state.remediations.filter(r => r.effort === 'low').forEach(r => state.selected.add(r.controlId));
        this._syncCheckboxes();
        this._updateWhatIfDisplay();
    },

    selectAllWhatIf() {
        const state = this._whatIfState;
        state.remediations.forEach(r => state.selected.add(r.controlId));
        (state.nonCodeItems || []).forEach(r => state.selected.add(r.controlId));
        this._syncCheckboxes();
        this._updateWhatIfDisplay();
    },

    clearWhatIf() {
        this._whatIfState.selected.clear();
        this._syncCheckboxes();
        this._updateWhatIfDisplay();
    },

    _syncCheckboxes() {
        const selected = this._whatIfState.selected;
        document.querySelectorAll('.rem-whatif-check').forEach(cb => {
            cb.checked = selected.has(cb.dataset.controlId);
        });
        document.querySelectorAll('.remediation-card[data-control-id]').forEach(card => {
            card.classList.toggle('rem-selected', selected.has(card.dataset.controlId));
        });
    },

    _updateWhatIfDisplay() {
        const { remediations, nonCodeItems, currentScore, selected, summary } = this._whatIfState;
        const el = document.getElementById('rem-whatif-projection');
        if (!el) return;

        const allItems = [...remediations, ...(nonCodeItems || [])];
        const totalDelta = allItems
            .filter(r => selected.has(r.controlId))
            .reduce((sum, r) => sum + (r.score_delta || 0), 0);
        const projected = Math.min(100, currentScore + totalDelta);
        const hasSelection = selected.size > 0;
        const totalCount = allItems.length;

        // Context: how many controls are met vs total
        const met = summary.met || 0;
        const total = summary.total || 0;
        const gap = summary.gap || 0;
        const partial = summary.partial || 0;
        const contextHtml = total > 0
            ? `<div class="rem-whatif-context">${met} of ${total} controls met, ${gap + partial} addressable</div>`
            : '';

        el.innerHTML = `
            <div class="rem-projection-row rem-whatif-row">
                <span class="rem-projection-label">
                    Your plan (${selected.size} of ${totalCount})
                </span>
                <span class="rem-projection-value">
                    ${currentScore.toFixed(1)}%
                    ${hasSelection
                        ? `<span style="color:var(--green)">&#8594; ${projected.toFixed(1)}%</span>
                           <span class="rem-whatif-delta">+${totalDelta.toFixed(1)}%</span>`
                        : `<span style="color:var(--text-muted)">&#8594; ${currentScore.toFixed(1)}%</span>`
                    }
                </span>
            </div>
            ${contextHtml}`;
    },

    // ── Phase C: Dependency Hints ─────────────────────────────────

    /** Known prerequisite relationships between evidence functions. */
    _EVIDENCE_PREREQUISITES: {
        'evidence_continuous_monitoring': ['evidence_audit_logging', 'evidence_performance_measurement'],
        'evidence_performance_measurement': ['evidence_audit_logging'],
        'evidence_transparency_logging': ['evidence_audit_logging'],
        'evidence_incident_response': ['evidence_audit_logging', 'evidence_continuous_monitoring'],
        'evidence_change_management': ['evidence_audit_logging'],
        'evidence_output_validation': ['evidence_input_sanitization'],
        'evidence_governance_program': ['evidence_governance_policy'],
        'evidence_retention_compliance': ['evidence_data_handling'],
        'evidence_embedding_security': ['evidence_access_control'],
        'evidence_mcp_server_security': ['evidence_access_control'],
    },

    /** Detect dependency hints for a remediation item. */
    _getDependencyHints(rem, allRemediations) {
        const hints = [];
        const efn = rem.evidence_fn || '';
        const allControlIds = new Set(allRemediations.map(r => r.controlId));

        // Check prerequisite relationships
        const prereqs = this._EVIDENCE_PREREQUISITES[efn] || [];
        for (const prereq of prereqs) {
            const prereqRem = allRemediations.find(r => r.evidence_fn === prereq);
            if (prereqRem) {
                hints.push({ type: 'prereq', text: `Consider completing ${prereqRem.controlId} first`, controlId: prereqRem.controlId });
            }
        }

        // Check shared files (items touching the same files should be done together)
        const myFiles = new Set(rem.relatedFiles || []);
        if (myFiles.size > 0) {
            for (const other of allRemediations) {
                if (other.controlId === rem.controlId) continue;
                const shared = (other.relatedFiles || []).filter(f => myFiles.has(f));
                if (shared.length > 0) {
                    hints.push({ type: 'related', text: `Shares files with ${other.controlId}`, controlId: other.controlId });
                    break; // Show at most one shared-file hint
                }
            }
        }

        return hints;
    },

    /** Remediation card: effort badge, summary, action, related files, impact, score delta, dependency hints. */
    /** Render "Also satisfies" cross-framework annotation for a remediation item. */
    _renderCrossFwAnnotation(evidenceFn, crossFwMap) {
        if (!evidenceFn || !crossFwMap) return '';
        const others = crossFwMap[evidenceFn];
        if (!others || others.length === 0) return '';

        // Group by framework to avoid repeating the same fw name
        const byFw = {};
        for (const o of others) {
            if (!byFw[o.label]) byFw[o.label] = [];
            byFw[o.label].push(o.controlId);
        }
        const fwCount = Object.keys(byFw).length;
        const parts = Object.entries(byFw).map(([label, ids]) => `${label} (${ids.join(', ')})`);
        const isHighImpact = fwCount >= 3;

        return `<div class="rem-cross-fw">
            <span class="rem-cross-fw-label">Also satisfies</span>${isHighImpact ? '<span class="rem-high-impact">High Impact</span>' : ''}
            <span class="rem-cross-fw-list">${parts.join(' &middot; ')}</span>
        </div>`;
    },

    renderRemediationCard(rem, rank, allRemediations, crossFwMap) {
        const effortColors = { low: 'var(--green)', medium: 'var(--yellow)', high: 'var(--red)' };
        const effortLabels = { low: 'Quick Win', medium: 'Medium Effort', high: 'Major Work' };
        const effort = rem.effort || 'medium';
        const color = effortColors[effort] || 'var(--yellow)';
        const label = effortLabels[effort] || effort;
        const controlId = rem.controlId || '';

        const filesHtml = (rem.relatedFiles || []).length > 0
            ? `<div class="rem-files">
                ${rem.relatedFiles.map(f => `<code class="rem-file-path">${f}</code>`).join('')}
               </div>`
            : '';

        const connHtml = rem.missingConnection
            ? `<div class="rem-connection">Missing link: <code>${rem.missingConnection}</code></div>`
            : '';

        const delta = rem.score_delta || 0;
        const deltaHtml = delta > 0
            ? `<span class="rem-score-delta" style="color:var(--green)">+${delta}%</span>`
            : '';

        const rankHtml = rank > 0
            ? `<span class="rem-rank">#${rank}</span>`
            : '';

        // Phase C: dependency hints
        const hints = allRemediations ? this._getDependencyHints(rem, allRemediations) : [];
        const hintsHtml = hints.length > 0
            ? `<div class="rem-dep-hints">${hints.map(h =>
                `<span class="rem-dep-hint rem-dep-${h.type}">${h.type === 'prereq' ? '&#9650;' : '&#8596;'} ${h.text}</span>`
              ).join('')}</div>`
            : '';

        // Cross-framework insight
        const crossFwHtml = this._renderCrossFwAnnotation(rem.evidence_fn, crossFwMap);

        return `
        <div class="remediation-card" data-control-id="${controlId}">
            <div class="rem-header">
                <label class="rem-whatif-label" onclick="event.stopPropagation()">
                    <input type="checkbox" class="rem-whatif-check" data-control-id="${controlId}"
                           onchange="Components.toggleWhatIf('${controlId}')">
                </label>
                ${rankHtml}
                <span class="rem-effort-badge" style="color:${color};border-color:${color}">${label}</span>
                <strong>${controlId}</strong>
                ${rem.impact > 1 ? `<span class="rem-impact">Addresses ${rem.impact} controls</span>` : ''}
                ${deltaHtml}
            </div>
            <div class="rem-summary">${rem.summary || ''}</div>
            <div class="rem-action">${rem.action || ''}</div>
            ${filesHtml}
            ${connHtml}
            ${hintsHtml}
            ${crossFwHtml}
            ${rem.evidence_fn && typeof CodeGenerator !== 'undefined' && CodeGenerator._TEMPLATES[rem.evidence_fn]
                ? `<button class="btn btn-sm rem-codegen-btn" onclick="event.stopPropagation(); Components._generateCode('${controlId}')">View Code Patch</button>`
                : ''}
        </div>`;
    },

    // ── Phase B: Roadmap with Phase Lanes ──────────────────────────

    /** Render a small cumulative score step chart for the remediation roadmap. */
    renderScoreCurve(remediations, currentScore, width = 500, height = 100) {
        if (!remediations || remediations.length === 0 || !currentScore) return '';

        const padding = { top: 12, right: 16, bottom: 20, left: 40 };
        const w = width - padding.left - padding.right;
        const h = height - padding.top - padding.bottom;

        // Build data points: start at current score, step up after each item
        const points = [{ score: currentScore, label: 'Current' }];
        let cumulative = currentScore;
        for (const r of remediations) {
            cumulative = Math.min(100, cumulative + (r.score_delta || 0));
            points.push({ score: cumulative, label: r.controlId || '' });
        }

        const maxScore = 100;
        const minScore = Math.max(0, currentScore - 5);
        const range = maxScore - minScore || 1;

        const coords = points.map((p, i) => ({
            x: padding.left + (i / Math.max(1, points.length - 1)) * w,
            y: padding.top + h - ((p.score - minScore) / range) * h,
            ...p,
        }));

        // Build step path (horizontal then vertical for each step)
        let pathD = `M ${coords[0].x} ${coords[0].y}`;
        for (let i = 1; i < coords.length; i++) {
            pathD += ` H ${coords[i].x} V ${coords[i].y}`;
        }

        let svg = `<svg width="${width}" height="${height}" class="rem-score-curve">`;
        // Grid
        for (let v = 0; v <= 2; v++) {
            const val = Math.round(minScore + (v / 2) * range);
            const y = padding.top + h - (v / 2) * h;
            svg += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--border)" stroke-dasharray="3,3"/>`;
            svg += `<text x="${padding.left - 6}" y="${y + 3}" text-anchor="end" fill="var(--text-muted)" font-size="9">${val}%</text>`;
        }
        // Area fill
        svg += `<path d="${pathD} V ${padding.top + h} H ${coords[0].x} Z" fill="rgba(88,166,255,0.08)"/>`;
        // Step line
        svg += `<path d="${pathD}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
        // Points with effort color
        const effortColors = { low: 'var(--green)', medium: 'var(--yellow)', high: 'var(--red)' };
        for (let i = 0; i < coords.length; i++) {
            const color = i === 0 ? 'var(--text-muted)' : (effortColors[remediations[i - 1]?.effort] || 'var(--accent)');
            svg += `<circle cx="${coords[i].x}" cy="${coords[i].y}" r="3.5" fill="${color}" stroke="var(--bg-secondary)" stroke-width="1.5">
                <title>${coords[i].label}: ${coords[i].score.toFixed(1)}%</title></circle>`;
        }
        svg += '</svg>';
        return `<div class="rem-score-curve-wrap">${svg}</div>`;
    },

    /** Render remediation items as collapsible phase lanes. */
    renderRemediationPhases(remediations, currentScore, rankMap, nonCodeItems, scanId, crossFwMap) {
        const quick = remediations.filter(r => r.effort === 'low');
        const medium = remediations.filter(r => r.effort === 'medium');
        const major = remediations.filter(r => r.effort === 'high');

        let html = '';
        const nc = nonCodeItems || [];
        const done = this.getDoneControls(scanId);

        const phases = [
            { items: quick, id: 'phase-quick', num: 1, label: 'Quick Wins',
              color: 'var(--green)', icon: '&#9889;' },
            { items: medium, id: 'phase-medium', num: 2, label: 'Medium Effort',
              color: 'var(--yellow)', icon: '&#9881;' },
            { items: major, id: 'phase-major', num: 3, label: 'Major Work',
              color: 'var(--red)', icon: '&#9878;' },
        ];

        for (const phase of phases) {
            const empty = phase.items.length === 0;
            const phaseDelta = phase.items.reduce((s, r) => s + (r.score_delta || 0), 0);
            html += `
            <div class="rem-phase-lane${empty ? ' rem-phase-empty' : ''}" id="${phase.id}">
                <div class="rem-phase-header" onclick="Components.togglePhase('${phase.id}')" style="cursor:pointer">
                    <span class="rem-phase-arrow" id="arrow-${phase.id}">${empty ? '' : '&#9660;'}</span>
                    <span class="rem-phase-badge" style="background:${phase.color}">Phase ${phase.num}</span>
                    <span class="rem-phase-title">${phase.icon} ${phase.label}</span>
                    ${empty
                        ? '<span class="rem-phase-count" style="opacity:0.5">0 items</span>'
                        : `<span class="rem-phase-delta" style="color:var(--green)">+${phaseDelta.toFixed(1)}%</span>
                           <span class="rem-phase-count">${phase.items.length} item${phase.items.length !== 1 ? 's' : ''}</span>`
                    }
                </div>
                ${empty ? '' : `<div class="rem-phase-body" id="body-${phase.id}">
                    ${phase.items.map(r => this.renderRemediationCard(r, rankMap.get(r) || 0, remediations, crossFwMap)).join('')}
                </div>`}
            </div>`;
        }

        // Phase 4: Documentation & Process (always shown)
        const ncDelta = nc.reduce((s, r) => s + (r.score_delta || 0), 0);
        const doneCount = nc.filter(r => done.has(r.controlId)).length;
        const ncEmpty = nc.length === 0;
        const phaseId = 'phase-docs';
        html += `
        <div class="rem-phase-lane${ncEmpty ? ' rem-phase-empty' : ''}" id="${phaseId}">
            <div class="rem-phase-header" onclick="Components.togglePhase('${phaseId}')" style="cursor:pointer">
                <span class="rem-phase-arrow" id="arrow-${phaseId}">${ncEmpty ? '' : '&#9660;'}</span>
                <span class="rem-phase-badge" style="background:var(--yellow)">Phase 4</span>
                <span class="rem-phase-title">&#128196; Documentation &amp; Process</span>
                ${ncEmpty
                    ? '<span class="rem-phase-count" style="opacity:0.5">0 items</span>'
                    : `<span class="rem-phase-delta" style="color:var(--green)">+${ncDelta.toFixed(1)}%</span>
                       <span class="rem-phase-count">${nc.length} item${nc.length !== 1 ? 's' : ''}${doneCount > 0 ? ` (${doneCount} done)` : ''}</span>`
                }
            </div>
            ${ncEmpty ? '' : `<div class="rem-phase-body" id="body-${phaseId}">
                ${nc.map(r => this._renderNonCodeCard(r, done, scanId, crossFwMap)).join('')}
            </div>`}
        </div>`;

        return html;
    },

    togglePhase(phaseId) {
        const body = document.getElementById('body-' + phaseId);
        const arrow = document.getElementById('arrow-' + phaseId);
        if (!body) return;
        const open = body.style.display !== 'none';
        body.style.display = open ? 'none' : '';
        if (arrow) arrow.innerHTML = open ? '&#9654;' : '&#9660;';
    },

    /** Render a non-code remediation card (documentation/process). */
    _renderNonCodeCard(item, doneSet, scanId, crossFwMap) {
        const controlId = item.controlId || '';
        const isDone = doneSet.has(controlId);
        const catLabel = item.category === 'process' ? 'Process' : 'Documentation';
        const catColor = item.category === 'process' ? 'var(--purple, #a78bfa)' : 'var(--yellow)';
        const delta = item.score_delta || 0;
        const deltaHtml = delta > 0
            ? `<span class="rem-score-delta" style="color:var(--green)">+${delta.toFixed(1)}%</span>` : '';

        const reportRef = `(typeof DetailView!=='undefined'&&DetailView._report)||(typeof CompareView!=='undefined'&&(CompareView._report2||CompareView._report1))||{}`;
        const templateBtn = item.templateId
            ? `<button class="btn btn-sm rem-template-btn" onclick="event.stopPropagation(); CodeGenerator.generateDoc('${item.templateId}', {controlId:'${controlId}'}, ${reportRef})">Open Template</button>`
            : '';

        return `
        <div class="remediation-card${isDone ? ' rem-done' : ''}" data-control-id="${controlId}">
            <div class="rem-header">
                <label class="rem-whatif-label" onclick="event.stopPropagation()">
                    <input type="checkbox" class="rem-whatif-check" data-control-id="${controlId}"
                           ${isDone ? 'checked' : ''}
                           onchange="Components.toggleWhatIf('${controlId}')">
                </label>
                <span class="rem-effort-badge" style="color:${catColor};border-color:${catColor}">${catLabel}</span>
                <strong>${controlId}</strong>
                ${deltaHtml}
                <button class="btn btn-sm rem-done-btn" onclick="event.stopPropagation(); Components.toggleDone('${scanId}','${controlId}')">${isDone ? 'Undo' : 'Done'}</button>
            </div>
            <div class="rem-summary">${item.summary || ''}</div>
            <div class="rem-action">${item.action || ''}</div>
            ${this._renderCrossFwAnnotation(item.evidence_fn, crossFwMap)}
            ${templateBtn}
        </div>`;
    },

    /** Build synthetic remediation items for non-code control gaps. */
    buildNonCodeItems(report) {
        const articles = report.articles || [];
        const total = (report.summary || {}).total || 1;
        const items = [];
        for (const art of articles) {
            for (const ctrl of (art.controls || [])) {
                if (ctrl.status === 'met') continue;
                const g = CONTROL_GUIDANCE[ctrl.evidence_fn] || {};
                if (g.category !== 'documentation' && g.category !== 'process') continue;
                const scoreDelta = ctrl.status === 'gap' ? (1 / total) * 100 : (0.5 / total) * 100;
                items.push({
                    controlId: ctrl.controlId,
                    evidence_fn: ctrl.evidence_fn,
                    effort: 'doc',
                    score_delta: parseFloat(scoreDelta.toFixed(2)),
                    category: g.category,
                    summary: g.quickStart || 'Complete the required documentation.',
                    action: g.auditorExpects || '',
                    templateId: g.templateId || '',
                    _isNonCode: true,
                });
            }
        }
        return items;
    },

    // ── Done State (non-code controls) ────────────────────────────
    _doneStorageKey(scanId) { return 'comply_done_' + (scanId || 'default'); },

    getDoneControls(scanId) {
        try {
            return new Set(JSON.parse(localStorage.getItem(this._doneStorageKey(scanId)) || '[]'));
        } catch { return new Set(); }
    },

    toggleDone(scanId, controlId) {
        const done = this.getDoneControls(scanId);
        if (done.has(controlId)) done.delete(controlId);
        else done.add(controlId);
        localStorage.setItem(this._doneStorageKey(scanId), JSON.stringify([...done]));
        // Update UI
        const card = document.querySelector(`.remediation-card[data-control-id="${controlId}"]`);
        const isDone = done.has(controlId);
        if (card) {
            card.classList.toggle('rem-done', isDone);
            const cb = card.querySelector('.rem-whatif-check');
            if (cb) { cb.checked = isDone; if (isDone) this._whatIfState.selected.add(controlId); }
            const btn = card.querySelector('.rem-done-btn');
            if (btn) btn.textContent = isDone ? 'Undo' : 'Done';
        }
        this._updateWhatIfDisplay();
    },

    /** Remediation summary banner with score projection and what-if controls. */
    renderRemediationSummary(remediations, currentScore, summary, nonCodeItems, scanId) {
        const allCount = (remediations || []).length + (nonCodeItems || []).length;
        if (allCount === 0) return '';
        this.initWhatIf(remediations || [], currentScore, summary, nonCodeItems, scanId);

        const quick = (remediations || []).filter(r => r.effort === 'low').length;
        const medium = (remediations || []).filter(r => r.effort === 'medium').length;
        const major = (remediations || []).filter(r => r.effort === 'high').length;
        const docs = (nonCodeItems || []).length;
        const total = allCount;

        // Score projection from last remediation's projected_score_after + non-code deltas
        const codeProjected = (remediations || []).length > 0
            ? (remediations[remediations.length - 1]?.projected_score_after || 0) : currentScore;
        const ncDelta = (nonCodeItems || []).reduce((s, r) => s + (r.score_delta || 0), 0);
        const projectedScore = Math.min(100, codeProjected + ncDelta);
        const hasProjection = projectedScore > 0 && currentScore !== undefined;

        return `
        <div class="rem-summary-banner">
            <div>
                <strong>${total} remediation action${total !== 1 ? 's' : ''}</strong>
                <div class="rem-summary-counts">
                    ${quick > 0 ? `<span style="color:var(--green)">${quick} quick win${quick !== 1 ? 's' : ''}</span>` : ''}
                    ${medium > 0 ? `<span style="color:var(--yellow)">${medium} medium</span>` : ''}
                    ${major > 0 ? `<span style="color:var(--red)">${major} major</span>` : ''}
                    ${docs > 0 ? `<span style="color:var(--yellow)">${docs} doc/process</span>` : ''}
                </div>
            </div>
            <div class="rem-projection">
                ${hasProjection ? `
                <div class="rem-projection-row">
                    <span class="rem-projection-label">All items complete</span>
                    <span class="rem-projection-value">${currentScore.toFixed(1)}% <span style="color:var(--green)">&#8594; ${projectedScore.toFixed(1)}%</span></span>
                </div>` : ''}
                <div id="rem-whatif-projection"></div>
            </div>
            <div class="rem-whatif-actions">
                <button class="btn btn-sm" onclick="Components.selectQuickWins()" title="Select all quick wins">Quick Wins</button>
                <button class="btn btn-sm" onclick="Components.selectAllWhatIf()" title="Select all items">All</button>
                <button class="btn btn-sm" onclick="Components.clearWhatIf()" title="Clear selection">Clear</button>
                <button class="btn btn-sm rem-export-btn" onclick="Components.downloadRoadmap()">Export Roadmap</button>
            </div>
        </div>`;
    },

    /** Download remediation roadmap as Markdown. Finds report from active view. */
    downloadRoadmap() {
        // Find the active report -- try DetailView first, then CompareView
        let report = null;
        if (typeof DetailView !== 'undefined' && DetailView._report) {
            report = DetailView._report;
        } else if (typeof CompareView !== 'undefined' && CompareView._report2) {
            report = CompareView._report2;
        }
        if (!report) return;

        const framework = report.framework || 'scan';
        const repo = (report.target || '').replace(/.*\//, '') || 'repo';
        const score = (report.summary || {}).score || 0;
        const scanId = this._whatIfState.scanId || '';

        // Filter code remediations to selected items if what-if has selections
        let remediations = report.remediations || [];
        const selected = this._whatIfState.selected;
        if (selected.size > 0) {
            remediations = remediations.filter(r => selected.has(r.controlId));
        }

        // Build non-code items, excluding done ones
        const nonCodeItems = this.buildNonCodeItems(report);
        const doneSet = this.getDoneControls(scanId);
        const activeNonCode = nonCodeItems.filter(nc => !doneSet.has(nc.controlId));

        if (remediations.length === 0 && activeNonCode.length === 0) return;

        const md = this._generateRoadmapMarkdown(remediations, framework, repo, score, activeNonCode);

        const blob = new Blob([md], { type: 'text/markdown' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `comply-roadmap-${framework}-${new Date().toISOString().slice(0, 10)}.md`;
        a.click();
        URL.revokeObjectURL(a.href);
    },

    /** Generate Markdown roadmap from remediation data. */
    _generateRoadmapMarkdown(remediations, framework, repo, currentScore, nonCodeItems) {
        const fwName = typeof fwLabel === 'function' ? fwLabel(framework) : framework;
        const date = new Date().toISOString().slice(0, 10);
        const projected = remediations.length > 0 ? (remediations[remediations.length - 1].projected_score_after || 0) : 0;
        const nc = nonCodeItems || [];

        const quick = remediations.filter(r => r.effort === 'low');
        const medium = remediations.filter(r => r.effort === 'medium');
        const major = remediations.filter(r => r.effort === 'high');
        const ncDelta = nc.reduce((s, i) => s + (i.score_delta || 0), 0);

        let md = `# Compliance Remediation Roadmap\n\n`;
        md += `**Repository:** ${repo}\n`;
        md += `**Framework:** ${fwName}\n`;
        md += `**Generated:** ${date}\n`;
        md += `**Current Score:** ${currentScore.toFixed(1)}%\n`;
        const totalProjected = (projected > 0 ? projected : currentScore) + ncDelta;
        if (remediations.length > 0 || nc.length > 0) {
            md += `**Projected Score (all items):** ${totalProjected.toFixed(1)}%\n`;
        }
        md += `\n---\n\n`;

        // Summary
        md += `## Summary\n\n`;
        md += `| Category | Count |\n|----------|-------|\n`;
        if (quick.length) md += `| Quick Wins (Code) | ${quick.length} |\n`;
        if (medium.length) md += `| Medium Effort (Code) | ${medium.length} |\n`;
        if (major.length) md += `| Major Work (Code) | ${major.length} |\n`;
        if (nc.length) md += `| Documentation & Process | ${nc.length} |\n`;
        md += `| **Total** | **${remediations.length + nc.length}** |\n\n`;

        md += `---\n\n`;

        // Sections by effort
        const sections = [
            { items: quick, title: 'Phase 1: Quick Wins', desc: 'Low effort, high impact code changes' },
            { items: medium, title: 'Phase 2: Medium Effort', desc: 'Moderate code work required' },
            { items: major, title: 'Phase 3: Major Work', desc: 'Significant code implementation needed' },
        ];

        for (const sec of sections) {
            if (sec.items.length === 0) continue;
            md += `## ${sec.title}\n\n*${sec.desc}*\n\n`;

            for (let i = 0; i < sec.items.length; i++) {
                const r = sec.items[i];
                const rank = remediations.indexOf(r) + 1;
                const delta = r.score_delta || 0;
                md += `### #${rank}. ${r.controlId || 'Control'}\n\n`;
                md += `${r.summary || ''}\n\n`;
                md += `**Action:** ${r.action || ''}\n`;
                if (delta > 0) md += `**Score Impact:** +${delta}%\n`;
                if (r.impact > 1) md += `**Cross-control Impact:** Addresses ${r.impact} controls\n`;
                if (r.relatedFiles && r.relatedFiles.length > 0) {
                    md += `**Related Files:** ${r.relatedFiles.map(f => '`' + f + '`').join(', ')}\n`;
                }
                if (r.missingConnection) {
                    md += `**Missing Connection:** \`${r.missingConnection}\`\n`;
                }
                md += `\n`;
            }
        }

        // Phase 4: Documentation & Process
        if (nc.length > 0) {
            md += `## Phase 4: Documentation & Process\n\n`;
            md += `*Non-code controls requiring documents or organizational processes (+${ncDelta.toFixed(1)}%)*\n\n`;
            const docs = nc.filter(i => i.category === 'documentation');
            const procs = nc.filter(i => i.category === 'process');
            if (docs.length > 0) {
                md += `### Documentation\n\n`;
                for (const item of docs) {
                    md += `- [ ] **${item.controlId}** -- ${item.summary}`;
                    if (item.score_delta > 0) md += ` (+${item.score_delta}%)`;
                    md += `\n`;
                }
                md += `\n`;
            }
            if (procs.length > 0) {
                md += `### Process\n\n`;
                for (const item of procs) {
                    md += `- [ ] **${item.controlId}** -- ${item.summary}`;
                    if (item.score_delta > 0) md += ` (+${item.score_delta}%)`;
                    md += `\n`;
                }
                md += `\n`;
            }
        }

        md += `---\n\n*Generated by [BespokeAgile Comply](https://comply-demo.bespokeagile.com)*\n`;
        return md;
    },

    // ── Overlap Matrix ──────────────────────────────────────────────────

    /** Capability names for evidence functions. */
    CAPABILITY_NAMES: {
        evidence_audit_logging: 'Audit Logging',
        evidence_traceability: 'Traceability',
        evidence_risk_assessment_gateway: 'Risk Assessment',
        evidence_risk_categorization: 'Risk Categorization',
        evidence_risk_register_auto: 'Risk Register',
        evidence_transparency_disclosure: 'Transparency',
        evidence_transparency_logging: 'Transparency Logging',
        evidence_continuous_monitoring: 'Continuous Monitoring',
        evidence_performance_measurement: 'Testing & Measurement',
        evidence_governance_policy: 'Governance Policy',
        evidence_governance_program: 'Governance Program',
        evidence_logical_access: 'Access Control',
        evidence_data_handling: 'Data Handling',
        evidence_change_management: 'Change Management',
        evidence_incident_response: 'Incident Response',
        evidence_human_oversight_gateway: 'Human Oversight',
        evidence_ai_system_inventory: 'AI System Inventory',
        evidence_impact_documentation: 'Impact Assessment',
        evidence_consumer_notification: 'Consumer Notification',
        evidence_availability_controls: 'Availability Controls',
        evidence_retention_compliance: 'Data Retention',
        evidence_input_sanitization: 'Input Sanitization',
        evidence_output_validation: 'Output Validation',
        evidence_model_provenance: 'Model Provenance',
        evidence_prompt_protection: 'Prompt Protection',
        evidence_embedding_security: 'Embedding Security',
        evidence_consumption_limits: 'Consumption Limits',
        evidence_access_control: 'Access Control (LLM)',
        evidence_mcp_server_security: 'MCP Server Security',
        evidence_ai_supply_chain: 'AI Supply Chain',
    },

    capabilityName(evidenceFn) {
        return this.CAPABILITY_NAMES[evidenceFn]
            || evidenceFn.replace('evidence_', '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    },

    /**
     * Build overlap matrix from multiple scan reports for one repo.
     * Returns { capabilities[], frameworks[], priorities[], fwScores, efficiency, scanOrder }
     */
    buildOverlapMatrix(reports) {
        const capMap = {};  // evidence_fn -> { name, evidence_fn, frameworks: {fw -> {controlId, status, controls[]}} }
        const fwSet = new Set();
        const fwScores = {};

        for (const report of reports) {
            const fw = report.framework || '';
            if (!fw) continue;
            fwSet.add(fw);
            fwScores[fw] = {
                score: (report.summary || {}).score || 0,
                met: (report.summary || {}).met || 0,
                partial: (report.summary || {}).partial || 0,
                gap: (report.summary || {}).gap || 0,
                total: (report.summary || {}).total || 0,
                depth: report.scanDepth || 'structure',
            };

            for (const art of (report.articles || [])) {
                for (const ctrl of (art.controls || [])) {
                    const efn = ctrl.evidence_fn || '';
                    if (!efn) continue;
                    if (!capMap[efn]) {
                        capMap[efn] = {
                            name: this.capabilityName(efn),
                            evidence_fn: efn,
                            frameworks: {},
                        };
                    }
                    const existing = capMap[efn].frameworks[fw];
                    const rank = { met: 2, partial: 1, gap: 0 };
                    if (!existing) {
                        capMap[efn].frameworks[fw] = {
                            controlId: ctrl.controlId,
                            status: ctrl.status || 'gap',
                            controls: [{ controlId: ctrl.controlId, status: ctrl.status || 'gap' }],
                        };
                    } else {
                        existing.controls.push({ controlId: ctrl.controlId, status: ctrl.status || 'gap' });
                        if ((rank[ctrl.status] || 0) > (rank[existing.status] || 0)) {
                            existing.controlId = ctrl.controlId;
                            existing.status = ctrl.status || 'gap';
                        }
                    }
                }
            }
        }

        const frameworks = [...fwSet].sort();

        // Build capabilities with framework count and sort by sharing (most shared first)
        const capabilities = Object.values(capMap).map(cap => {
            const fws = Object.keys(cap.frameworks);
            const gapCount = fws.filter(f => cap.frameworks[f].status === 'gap').length;
            const partialCount = fws.filter(f => cap.frameworks[f].status === 'partial').length;
            const totalControlCount = fws.reduce((sum, f) => sum + (cap.frameworks[f].controls || []).length, 0);
            return {
                ...cap,
                frameworkCount: fws.length,
                gapCount,
                partialCount,
                metCount: fws.length - gapCount - partialCount,
                totalControlCount,
            };
        });
        capabilities.sort((a, b) => b.frameworkCount - a.frameworkCount || a.name.localeCompare(b.name));

        // Build priorities: capabilities with gaps/partials, sorted by impact
        const priorities = capabilities
            .filter(c => c.gapCount > 0 || c.partialCount > 0)
            .map(c => ({
                ...c,
                impactScore: c.frameworkCount * (c.gapCount + c.partialCount),
            }))
            .sort((a, b) => b.impactScore - a.impactScore);

        // Efficiency stats
        const totalControlsNaive = Object.values(fwScores).reduce((sum, s) => sum + s.total, 0);
        const sharedCaps = capabilities.filter(c => c.frameworkCount > 1);
        const sharedControlCount = sharedCaps.reduce((sum, c) => sum + c.totalControlCount, 0);
        const efficiency = {
            totalCapabilities: capabilities.length,
            sharedCapabilities: sharedCaps.length,
            uniqueCapabilities: capabilities.length - sharedCaps.length,
            totalControlsNaive,
            sharedControlCount,
            efficiencyPct: totalControlsNaive > 0
                ? Math.round((1 - capabilities.length / totalControlsNaive) * 100) : 0,
        };

        // Scan order: greedy set-cover
        const scanOrder = this._computeScanOrder(capabilities, frameworks, fwScores);

        return { capabilities, frameworks, priorities, fwScores, efficiency, scanOrder };
    },

    /** Greedy set-cover: pick framework covering the most new capabilities each step. */
    _computeScanOrder(capabilities, frameworks, fwScores) {
        const fwCaps = {};
        for (const fw of frameworks) fwCaps[fw] = new Set();
        for (const cap of capabilities) {
            for (const fw of Object.keys(cap.frameworks)) fwCaps[fw].add(cap.evidence_fn);
        }
        const covered = new Set();
        const order = [];
        const remaining = new Set(frameworks);

        while (remaining.size > 0) {
            let bestFw = null, bestNew = 0, bestTotal = 0;
            for (const fw of remaining) {
                const newCount = [...fwCaps[fw]].filter(c => !covered.has(c)).length;
                if (newCount > bestNew || (newCount === bestNew && fwCaps[fw].size > bestTotal)) {
                    bestFw = fw;
                    bestNew = newCount;
                    bestTotal = fwCaps[fw].size;
                }
            }
            if (!bestFw) break;
            const reused = [...fwCaps[bestFw]].filter(c => covered.has(c)).length;
            for (const c of fwCaps[bestFw]) covered.add(c);
            order.push({
                framework: bestFw,
                score: (fwScores[bestFw] || {}).score || 0,
                totalControls: (fwScores[bestFw] || {}).total || 0,
                newCapabilities: bestNew,
                reusedCapabilities: reused,
                totalCapabilities: fwCaps[bestFw].size,
                cumulativeCoverage: covered.size,
            });
            remaining.delete(bestFw);
        }
        return order;
    },

    /** Render efficiency insights banner. */
    renderEfficiencyInsights(matrix) {
        const { efficiency, frameworks, capabilities } = matrix;
        if (frameworks.length < 2) return '';

        const topShared = capabilities.filter(c => c.frameworkCount > 1)
            .sort((a, b) => b.totalControlCount - a.totalControlCount)[0];

        let html = '<div class="overlap-efficiency">';
        html += `<div class="overlap-efficiency-stat">
            <div class="overlap-efficiency-number">${efficiency.sharedCapabilities}</div>
            <div class="overlap-efficiency-label">capabilities shared across ${frameworks.length} frameworks</div>
        </div>`;
        html += `<div class="overlap-efficiency-stat">
            <div class="overlap-efficiency-number">${efficiency.efficiencyPct}%</div>
            <div class="overlap-efficiency-label">effort reduction vs scanning independently</div>
        </div>`;
        html += `<div class="overlap-efficiency-stat">
            <div class="overlap-efficiency-number">${efficiency.sharedControlCount}</div>
            <div class="overlap-efficiency-label">controls covered by shared capabilities</div>
        </div>`;
        html += '</div>';
        return html;
    },

    /** Render recommended scan order. */
    renderScanOrder(matrix) {
        const { scanOrder, capabilities } = matrix;
        if (scanOrder.length < 2) return '';

        const totalCaps = capabilities.length;
        let html = '<div class="overlap-scan-order">';
        for (let i = 0; i < scanOrder.length; i++) {
            const step = scanOrder[i];
            const pctCovered = totalCaps > 0 ? Math.round(step.cumulativeCoverage / totalCaps * 100) : 0;

            html += `<div class="overlap-scan-step">
                <div class="overlap-scan-step-num">${i + 1}</div>
                <div class="overlap-scan-step-body">
                    <div class="overlap-scan-step-fw">${typeof fwLabel === 'function' ? fwLabel(step.framework) : step.framework}</div>
                    <div class="overlap-scan-step-detail">
                        ${i === 0
                            ? `${step.newCapabilities} capabilities, ${step.totalControls} controls`
                            : `${step.newCapabilities} new + ${step.reusedCapabilities} already covered`
                        }
                    </div>
                </div>
                <div class="overlap-scan-step-bar">
                    <div class="overlap-scan-step-fill" style="width:${pctCovered}%"></div>
                </div>
                <div class="overlap-scan-step-pct">${pctCovered}%</div>
            </div>`;
        }
        html += '</div>';
        return html;
    },

    /** Render unified cross-framework remediation. */
    renderUnifiedRemediation(reports, matrix) {
        const remByEfn = {};
        for (const report of reports) {
            const fw = report.framework || '';
            for (const rem of (report.remediations || [])) {
                const efn = rem.evidence_fn || '';
                if (!efn) continue;
                if (!remByEfn[efn]) {
                    remByEfn[efn] = {
                        name: this.capabilityName(efn),
                        evidence_fn: efn,
                        frameworks: {},
                        action: rem.action || '',
                        effort: rem.effort || 'medium',
                    };
                }
                if (!remByEfn[efn].frameworks[fw]) remByEfn[efn].frameworks[fw] = [];
                remByEfn[efn].frameworks[fw].push({
                    controlId: rem.controlId,
                    status: rem.current_status || 'gap',
                    scoreDelta: rem.score_delta || 0,
                });
            }
        }

        const unified = Object.values(remByEfn);
        if (unified.length === 0) {
            return '<div class="alert alert-success">No remediations needed -- all controls are met across all frameworks.</div>';
        }

        // Enrich with cross-framework context
        for (const item of unified) {
            const cap = matrix.capabilities.find(c => c.evidence_fn === item.evidence_fn);
            item.frameworkCount = cap ? cap.frameworkCount : Object.keys(item.frameworks).length;
            item.totalControlCount = cap ? cap.totalControlCount : 0;
            item.totalDelta = Object.values(item.frameworks).reduce((s, arr) =>
                s + arr.reduce((ss, c) => ss + c.scoreDelta, 0), 0);
        }

        unified.sort((a, b) => {
            const aFw = Object.keys(a.frameworks).length;
            const bFw = Object.keys(b.frameworks).length;
            return bFw - aFw || b.totalDelta - a.totalDelta;
        });

        let html = '<div class="overlap-unified-rems">';
        for (const item of unified) {
            const fws = Object.keys(item.frameworks);
            const effortBadge = `<span class="rem-effort-badge ${item.effort}">${item.effort}</span>`;
            const crossFw = item.frameworkCount > 1
                ? `<span class="overlap-cross-fw-badge">${item.frameworkCount} frameworks</span>` : '';

            // Active remediation rows
            let fwBreakdown = fws.map(fw => {
                const controls = item.frameworks[fw];
                const controlIds = controls.map(c => c.controlId).join(', ');
                const delta = controls.reduce((s, c) => s + c.scoreDelta, 0);
                return `<div class="overlap-unified-fw-row">
                    <span class="overlap-unified-fw-name">${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</span>
                    <span class="overlap-unified-fw-controls">${controlIds}</span>
                    <span class="overlap-unified-fw-delta" style="color:var(--green)">+${delta.toFixed(1)}%</span>
                </div>`;
            }).join('');

            // Show "already met" rows for frameworks where this capability exists but has no remediation
            const cap = matrix.capabilities.find(c => c.evidence_fn === item.evidence_fn);
            if (cap) {
                const metFws = Object.keys(cap.frameworks).filter(fw =>
                    !item.frameworks[fw] && cap.frameworks[fw].status === 'met');
                if (metFws.length > 0) {
                    fwBreakdown += metFws.map(fw => {
                        const ctrls = cap.frameworks[fw].controls || [cap.frameworks[fw]];
                        const ids = ctrls.map(c => c.controlId).join(', ');
                        return `<div class="overlap-unified-fw-row overlap-unified-met">
                            <span class="overlap-unified-fw-name">${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</span>
                            <span class="overlap-unified-fw-controls">${ids}</span>
                            <span class="overlap-unified-fw-delta" style="color:var(--green)">already met</span>
                        </div>`;
                    }).join('');
                }
            }

            html += `<div class="overlap-unified-card">
                <div class="overlap-unified-header">
                    <strong>${item.name}</strong>
                    ${crossFw}
                    ${effortBadge}
                </div>
                <div class="overlap-unified-action">${item.action}</div>
                <div class="overlap-unified-breakdown">${fwBreakdown}</div>
            </div>`;
        }
        html += '</div>';
        return html;
    },

    /** Render the overlap matrix as an HTML table. */
    renderOverlapMatrix(matrix) {
        const { capabilities, frameworks, fwScores } = matrix;
        if (capabilities.length === 0) return '<div class="alert">No capabilities found.</div>';

        const statusDot = (status) => {
            const colors = { met: 'var(--green)', partial: 'var(--yellow)', gap: 'var(--red)' };
            const labels = { met: 'Met', partial: 'Partial', gap: 'Gap' };
            return `<span class="overlap-dot" style="background:${colors[status] || 'var(--text-muted)'}" title="${labels[status] || 'N/A'}"></span>`;
        };

        let html = '<div class="overlap-matrix-wrap"><table class="overlap-matrix"><thead><tr>';
        html += '<th class="overlap-cap-header">Capability</th>';
        html += '<th class="overlap-shared-header">Shared</th>';
        for (const fw of frameworks) {
            const score = (fwScores[fw] || {}).score || 0;
            const scoreColor = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
            html += `<th class="overlap-fw-header"><div>${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</div><div style="color:${scoreColor};font-size:11px">${score.toFixed(0)}%</div></th>`;
        }
        html += '</tr></thead><tbody>';

        for (const cap of capabilities) {
            const shared = cap.frameworkCount > 1
                ? `<span class="overlap-shared-badge">${cap.frameworkCount}</span>`
                : '<span class="overlap-shared-single">1</span>';
            const rowClass = cap.frameworkCount > 1 ? ' overlap-shared-row' : '';

            html += `<tr class="${rowClass}">`;
            html += `<td class="overlap-cap-name">${cap.name}</td>`;
            html += `<td class="overlap-shared-cell">${shared}</td>`;
            for (const fw of frameworks) {
                const entry = cap.frameworks[fw];
                if (entry) {
                    const controls = entry.controls || [entry];
                    const controlIds = controls.map(c => c.controlId).join(', ');
                    html += `<td class="overlap-status-cell">${statusDot(entry.status)} <span class="overlap-control-id">${controlIds}</span></td>`;
                } else {
                    html += '<td class="overlap-status-cell"><span class="overlap-na">--</span></td>';
                }
            }
            html += '</tr>';
        }

        html += '</tbody></table></div>';
        return html;
    },

    /** Render priority actions -- capabilities whose fix addresses the most frameworks. */
    renderOverlapPriorities(priorities) {
        if (priorities.length === 0) {
            return '<div class="alert alert-success">All shared capabilities are met across all frameworks.</div>';
        }

        let html = '<div class="overlap-priorities">';
        for (let i = 0; i < Math.min(priorities.length, 10); i++) {
            const p = priorities[i];
            const fwList = Object.keys(p.frameworks).map(fw => typeof fwLabel === 'function' ? fwLabel(fw) : fw).join(', ');
            const statusCounts = [];
            if (p.gapCount > 0) statusCounts.push(`<span style="color:var(--red)">${p.gapCount} gap</span>`);
            if (p.partialCount > 0) statusCounts.push(`<span style="color:var(--yellow)">${p.partialCount} partial</span>`);
            if (p.metCount > 0) statusCounts.push(`<span style="color:var(--green)">${p.metCount} met</span>`);

            html += `
            <div class="overlap-priority-card">
                <div class="overlap-priority-header">
                    <span class="overlap-priority-rank">#${i + 1}</span>
                    <strong>${p.name}</strong>
                    <span class="overlap-priority-impact">${p.totalControlCount} control${p.totalControlCount !== 1 ? 's' : ''} across ${p.frameworkCount} framework${p.frameworkCount !== 1 ? 's' : ''}</span>
                </div>
                <div class="overlap-priority-status">${statusCounts.join(' / ')}</div>
                <div class="overlap-priority-frameworks">${fwList}</div>
            </div>`;
        }
        html += '</div>';
        return html;
    },

    /** Timeline group card: expandable row with score, repo, framework, depth badges, timeline steps. */
    renderTimelineGroup(timeline, opts) {
        const options = opts || {};
        const maxSteps = options.maxSteps || 3;
        const showCompare = options.showCompare !== false;

        const latest = timeline[timeline.length - 1];
        const repo = (latest.repo_url || latest.repo_path || latest.url || '').replace(/.*\//, '');
        const fw = typeof fwLabel === 'function' ? fwLabel(latest.framework || '') : (latest.framework || '');
        const score = latest.score || 0;
        const color = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
        const uid = 'hist-g-' + (latest.id || '').substring(0, 12);

        const depths = [...new Set(timeline.map(s =>
            (s.scan_depth || s.depth || '').includes('semantic') ? 'semantic' : 'structure'
        ))];
        const depthBadges = depths.map(d =>
            `<span class="hist-single-depth ${d}">${d}</span>`
        ).join('');

        const allDemo = timeline.every(s => s.source === 'demo');
        const sourceBadge = allDemo ? Components.renderSourceBadge('demo') : '';

        const count = timeline.length;
        const countLabel = count > 1 ? `${count} scans` : '1 scan';

        const hasCompare = showCompare && count >= 2;
        const prev = hasCompare ? timeline[timeline.length - 2] : null;
        const compareBtnHtml = hasCompare
            ? `<a href="#/diff/${prev.id}/${latest.id}" class="btn btn-sm btn-primary" style="text-decoration:none" onclick="event.stopPropagation()">Compare Latest</a>`
            : '';

        const shown = count > maxSteps ? timeline.slice(-maxSteps) : timeline;
        const skipped = count - shown.length;

        const steps = shown.map((s, i) => {
            const sc = s.score || 0;
            const c = sc >= 70 ? 'var(--green)' : sc >= 40 ? 'var(--yellow)' : 'var(--red)';
            const depth = (s.scan_depth || s.depth || '').includes('semantic') ? 'semantic' : 'structure';
            const commit = (s.commit_sha || s.commitSha || '').substring(0, 7);
            const date = (s.created_at || s.timestamp || '').substring(5, 16).replace('T', ' ');

            let deltaHtml = '';
            if (i > 0) {
                const prevScore = shown[i - 1].score || 0;
                const dd = sc - prevScore;
                const dColor = dd > 0 ? 'var(--green)' : dd < 0 ? 'var(--red)' : 'var(--text-muted)';
                deltaHtml = `<div class="timeline-arrow" style="color:${dColor}">
                    &#8594; <span>${dd > 0 ? '+' : ''}${dd.toFixed(1)}%</span>
                </div>`;
            }

            return `${deltaHtml}
            <a href="#/detail/${s.id}" class="timeline-step" style="text-decoration:none" onclick="event.stopPropagation()">
                <div class="timeline-step-score" style="color:${c}">${sc.toFixed(1)}%</div>
                <div class="timeline-step-depth">${depth}</div>
                <div class="timeline-step-meta">${date}${commit ? ` · ${commit}` : ''}</div>
            </a>`;
        }).join('');

        return `
        <div class="hist-timeline-card hist-expandable">
            <div class="hist-timeline-header" id="${uid}" onclick="this.classList.toggle('expanded')">
                <div style="display:flex;align-items:center;gap:12px">
                    <span class="hist-expand-arrow">&#9656;</span>
                    <span style="color:${color};font-weight:700;font-size:18px">${score.toFixed(1)}%</span>
                    <strong>${repo}</strong>
                    <span style="color:var(--text-muted)">${fw}</span>
                    ${sourceBadge}
                    <span style="color:var(--text-muted);font-size:12px">${countLabel}</span>
                </div>
                <div style="display:flex;align-items:center;gap:10px">
                    ${depthBadges}
                    ${compareBtnHtml}
                </div>
            </div>
            <div class="hist-expand-body">
                <div class="timeline-steps">
                    ${skipped > 0 ? `<div class="timeline-skipped">${skipped} earlier</div>` : ''}
                    ${steps}
                </div>
            </div>
        </div>`;
    },
};
