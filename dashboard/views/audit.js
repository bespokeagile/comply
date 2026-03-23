/* Predicate Audit view — free compliance gap analysis landing page */
const AuditView = {
    _scanning: false,

    async render() {
        const app = document.getElementById('app');
        let frameworks = [];
        try {
            frameworks = await complyApi.getFrameworks();
        } catch (e) { /* use defaults */ }

        const fwOptions = (frameworks || []).map(fw => {
            const id = fw.framework || fw.id || '';
            const label = fw.label || fw.name || id;
            return `<option value="${id}">${label}</option>`;
        }).join('');

        // Enforcement countdown
        const euDeadline = new Date('2026-08-02T00:00:00Z');
        const coDeadline = new Date('2026-06-30T00:00:00Z');
        const now = new Date();
        const euDays = Math.max(0, Math.ceil((euDeadline - now) / 86400000));
        const coDays = Math.max(0, Math.ceil((coDeadline - now) / 86400000));

        const urgencyBanner = (euDays > 0 || coDays > 0) ? `
            <div class="enforcement-banner">
                <div class="enforcement-deadlines">
                    ${coDays > 0 ? `<div class="deadline-item">
                        <span class="deadline-days">${coDays}</span>
                        <span class="deadline-label">days to Colorado SB 24-205</span>
                    </div>` : `<div class="deadline-item deadline-enforced">
                        <span class="deadline-days">NOW</span>
                        <span class="deadline-label">Colorado SB 24-205 in effect</span>
                    </div>`}
                    ${euDays > 0 ? `<div class="deadline-item">
                        <span class="deadline-days">${euDays}</span>
                        <span class="deadline-label">days to EU AI Act</span>
                    </div>` : `<div class="deadline-item deadline-enforced">
                        <span class="deadline-days">NOW</span>
                        <span class="deadline-label">EU AI Act in effect</span>
                    </div>`}
                </div>
            </div>` : '';

        app.innerHTML = `
        <div class="audit-landing">
            ${urgencyBanner}
            <div class="audit-hero">
                <h1>Are You Compliant?</h1>
                <p class="audit-subtitle">
                    Discover which compliance controls your existing tools <em>cannot</em> evaluate.
                </p>
                <p class="audit-desc">
                    Infrastructure scanners (Vanta) and CI/CD tools (GitLab) cover some controls.
                    But regulatory frameworks like the EU AI Act require evidence from
                    <strong>product model graph traversals</strong> that no infrastructure tool can produce.
                </p>
            </div>

            <div class="card" id="audit-form-card">
                <div class="form-group">
                    <label>Repository URL or local path</label>
                    <input class="form-input" id="audit-url"
                           placeholder="https://github.com/your-org/your-repo"
                           autofocus>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Framework</label>
                        <select class="form-select" id="audit-framework">
                            ${fwOptions || '<option value="eu-ai-act">EU AI Act</option>'}
                        </select>
                    </div>
                </div>
                <div class="form-group" id="audit-email-row">
                    <label>Email (optional) — get the full report sent to you</label>
                    <input class="form-input" id="audit-email" type="email"
                           placeholder="you@company.com">
                </div>
                <div class="btn-group">
                    <button class="btn btn-primary" id="audit-btn"
                            onclick="AuditView.runAudit()">
                        Run Free Audit
                    </button>
                </div>
            </div>

            <div id="audit-progress" style="display:none">
                <div class="card">
                    <div class="card-header">Scanning repository...</div>
                    <div id="audit-progress-detail" class="loading">
                        <span class="spinner"></span> Analysing codebase...
                    </div>
                </div>
            </div>

            <div id="audit-result" style="display:none"></div>
        </div>`;
    },

    async runAudit() {
        if (this._scanning) return;
        const url = document.getElementById('audit-url').value.trim();
        if (!url) return;

        this._scanning = true;
        const framework = document.getElementById('audit-framework').value;
        const email = document.getElementById('audit-email')?.value.trim() || null;

        document.getElementById('audit-btn').disabled = true;
        document.getElementById('audit-progress').style.display = 'block';
        document.getElementById('audit-result').style.display = 'none';

        try {
            const result = await complyApi.runAudit(url, framework, email);
            this._renderResult(result);
        } catch (e) {
            document.getElementById('audit-progress').innerHTML =
                `<div class="card"><div class="alert alert-error">Error: ${e.message}</div></div>`;
        } finally {
            this._scanning = false;
            document.getElementById('audit-btn').disabled = false;
        }
    },

    _renderResult(result) {
        document.getElementById('audit-progress').style.display = 'none';
        const el = document.getElementById('audit-result');
        el.style.display = 'block';

        const gap = result.predicateGap || {};
        const sections = result.sections || {};
        const score = result.scanScore || 0;

        el.innerHTML = `
        <div class="audit-result-header card">
            <div class="audit-scores">
                <div class="audit-score-main">
                    ${Components.renderScoreGauge(score)}
                    <p>Compliance Score</p>
                </div>
                <div class="audit-gap-highlight">
                    <div class="gap-number">${gap.graphRequired || 0}</div>
                    <div class="gap-label">of ${gap.totalControls || 0} controls</div>
                    <div class="gap-desc">require graph traversal</div>
                    <div class="gap-pct">${gap.graphRequiredPercent || 0}% undecidable by infrastructure tools</div>
                </div>
            </div>
            <div class="alert alert-info">
                ${gap.message || ''}
            </div>
        </div>

        <div class="audit-sections">
            ${this._renderSection(sections.infrastructure, 'infra')}
            ${this._renderSection(sections.pipeline, 'pipeline')}
            ${this._renderSection(sections.product_model, 'model')}
        </div>

        <div class="card audit-cta">
            <h3>Close the Predicate Gap</h3>
            <p>
                Install <strong>BespokeAgile Comply</strong> to evaluate all ${gap.totalControls || 0} controls,
                including the ${gap.graphRequired || 0} that require product model graph traversal.
            </p>
            <div class="btn-group">
                <a class="btn btn-primary" href="https://pypi.org/project/bespoketracker-comply/"
                   target="_blank">Install via pip</a>
                <a class="btn btn-outline" href="https://github.com/bespoketracker/comply"
                   target="_blank">View on GitHub</a>
            </div>
            <pre class="install-cmd">pip install bespoketracker-comply</pre>
        </div>`;
    },

    _renderSection(section, cssClass) {
        if (!section) return '';
        const controls = section.controls || [];
        const met = controls.filter(c => c.status === 'met').length;
        const partial = controls.filter(c => c.status === 'partial').length;
        const gap = controls.filter(c => c.status === 'gap').length;

        const rows = controls.map(ctrl => `
            <tr>
                <td><code>${ctrl.controlId || ''}</code></td>
                <td>${(ctrl.requirement || '').substring(0, 120)}${ctrl.requirement?.length > 120 ? '...' : ''}</td>
                <td>${Components.renderStatusBadge(ctrl.status)}</td>
                <td>
                    <span class="eval-method ${ctrl.evaluationMethod === 'graph_required' ? 'eval-graph' : 'eval-keyword'}">
                        ${ctrl.evaluationMethod === 'graph_required' ? 'Graph Required' : 'Pattern Match'}
                    </span>
                </td>
            </tr>
        `).join('');

        return `
        <div class="card audit-section audit-section-${cssClass}">
            <div class="card-header">
                <span>${section.label}</span>
                <span class="section-counts">
                    <span class="badge badge-met">${met} met</span>
                    <span class="badge badge-partial">${partial} partial</span>
                    <span class="badge badge-gap">${gap} gap</span>
                </span>
            </div>
            <p class="section-desc">${section.description || ''}</p>
            <table class="table">
                <thead>
                    <tr><th>Control</th><th>Requirement</th><th>Status</th><th>Method</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    },
};
