/* Gate view — CI/CD compliance gate decisions and runner */
const GateView = {
    async render() {
        const app = document.getElementById('app');
        app.innerHTML = `
            <div class="view-header" style="margin-bottom: 20px;">
                <h2>Compliance Gate</h2>
                <p class="subtitle">Block non-compliant deploys in your CI/CD pipeline</p>
            </div>

            <div class="card" style="margin-bottom:1.5rem">
                <div class="gate-top">
                    <div class="gate-form-wrap">
                        <h3>Run Gate Check</h3>
                        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
                            Scans a repository against compliance rules and returns pass/fail.
                            Use this form to test your thresholds, then automate with the CLI:
                        </p>
                        <pre class="gate-cli-hint"><code>bespoketracker-comply gate --repo . --framework eu_ai_act --threshold 70</code></pre>
                        <form id="gate-form" class="gate-form">
                            <div class="gate-form-row">
                                <label class="gate-field gate-field-grow">
                                    <span>Repository</span>
                                    <input type="text" id="gate-repo" list="gate-repo-list" placeholder="Select or type a repository" class="input" />
                                    <datalist id="gate-repo-list"></datalist>
                                </label>
                                <label class="gate-field">
                                    <span>Framework</span>
                                    <select id="gate-framework" class="input">
                                        <option value="eu_ai_act">EU AI Act</option>
                                    </select>
                                </label>
                                <label class="gate-field gate-field-sm">
                                    <span>Min Score</span>
                                    <input type="number" id="gate-threshold" value="0" min="0" max="100" step="0.1" class="input" />
                                </label>
                                <label class="gate-field gate-field-sm">
                                    <span>Max Gaps</span>
                                    <input type="number" id="gate-max-gaps" value="-1" min="-1" class="input" />
                                </label>
                            </div>
                            <div class="gate-form-row">
                                <label class="gate-check">
                                    <input type="checkbox" id="gate-regression" />
                                    <span>Fail on Regression</span>
                                </label>
                                <button type="submit" class="btn btn-primary" id="gate-run-btn">Run Gate</button>
                            </div>
                        </form>
                    </div>
                </div>
                <div id="gate-result" style="margin-top:16px"></div>
            </div>

            <div id="gate-summary" style="margin-bottom:1.5rem"></div>

            <div class="card">
                <h3>Decision History</h3>
                <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
                    Every gate check (manual or CI/CD) is recorded here for audit.
                </p>
                <div id="gate-decisions" class="table-wrap">
                    <div class="loading">Loading...</div>
                </div>
            </div>
        `;

        this._bindForm();
        this._loadFrameworks();
        this._loadRepoList();
        this._loadSummary();
        this._loadDecisions();
        this._applyUrlParams();
    },

    /** Pre-fill gate form from URL params (e.g. ?repo=X&framework=Y). */
    _applyUrlParams() {
        const hashParts = window.location.hash.split('?');
        if (hashParts.length < 2) return;
        const params = new URLSearchParams(hashParts[1]);
        const repo = params.get('repo');
        const fw = params.get('framework');
        if (repo) {
            const input = document.getElementById('gate-repo');
            if (input) input.value = decodeURIComponent(repo);
        }
        if (fw) {
            const sel = document.getElementById('gate-framework');
            if (sel) sel.value = fw;
        }
    },

    _bindForm() {
        const form = document.getElementById('gate-form');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('gate-run-btn');
            const resultDiv = document.getElementById('gate-result');
            btn.disabled = true;
            btn.textContent = 'Scanning...';
            resultDiv.innerHTML = '<div class="loading">Running gate check...</div>';

            try {
                const result = await complyApi.runGate(
                    document.getElementById('gate-repo').value,
                    document.getElementById('gate-framework').value,
                    parseFloat(document.getElementById('gate-threshold').value) || 0,
                    document.getElementById('gate-regression').checked,
                    parseInt(document.getElementById('gate-max-gaps').value, 10),
                );
                this._showResult(result);
                this._loadSummary();
                this._loadDecisions();
            } catch (err) {
                resultDiv.innerHTML = `<div class="alert alert-error">Error: ${err.message}</div>`;
            } finally {
                btn.disabled = false;
                btn.textContent = 'Run Gate';
            }
        });
    },

    _showResult(r) {
        const div = document.getElementById('gate-result');
        const cls = r.decision === 'pass' ? 'alert-success' : 'alert-error';
        const icon = r.decision === 'pass' ? '\u2713' : '\u2717';
        const sha = (r.commitSha || '').substring(0, 8) || '-';
        const maxG = r.maxCriticalGaps < 0 ? 'unlimited' : r.maxCriticalGaps;
        const repoEnc = encodeURIComponent(r.repoPath || '');
        const fwEnc = encodeURIComponent(r.framework || '');

        // Cross-link CTAs
        let nextStepHtml = '';
        if (r.decision === 'fail') {
            nextStepHtml = `
                <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
                    ${r.scanId ? `<a href="#/detail/${r.scanId}" class="btn btn-sm btn-secondary" style="text-decoration:none">View Scan Details</a>` : ''}
                    <a href="#/monitor?repo=${repoEnc}&framework=${fwEnc}" class="btn btn-sm btn-secondary" style="text-decoration:none">Set Up Monitoring</a>
                </div>
                <div style="margin-top:6px;font-size:12px;color:var(--text-muted)">
                    Monitor this repo to get alerted when compliance improves enough to pass.
                </div>`;
        } else {
            nextStepHtml = `
                <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
                    ${r.scanId ? `<a href="#/detail/${r.scanId}" class="btn btn-sm btn-secondary" style="text-decoration:none">View Scan Details</a>` : ''}
                    <a href="#/monitor?repo=${repoEnc}&framework=${fwEnc}" class="btn btn-sm btn-secondary" style="text-decoration:none">Watch for Drift</a>
                </div>`;
        }

        div.innerHTML = `
            <div class="alert ${cls}" style="font-family:monospace;line-height:1.8">
                <strong>${r.decision.toUpperCase()} ${icon}</strong><br/>
                Score: ${(r.score || 0).toFixed(1)}% (threshold: ${(r.thresholdScore || 0).toFixed(1)}%)<br/>
                Regression: ${r.regressionDetected ? 'DETECTED' : 'none'}<br/>
                Gaps: ${r.criticalGapCount} (limit: ${maxG})<br/>
                Commit: ${sha} &middot; Scan: ${r.scanId || '-'}<br/>
                <em>${r.reason}</em>
                ${nextStepHtml}
            </div>
        `;
    },

    async _loadRepoList() {
        await _loadRepoOptions('gate-repo-list');
    },

    async _loadFrameworks() {
        try {
            const fws = await complyApi.getFrameworks();
            const sel = document.getElementById('gate-framework');
            sel.innerHTML = '';
            for (const fw of fws) {
                const opt = document.createElement('option');
                opt.value = fw.id.replace(/-/g, '_');
                opt.textContent = fw.name || fw.id;
                sel.appendChild(opt);
            }
        } catch (e) { /* keep default */ }
    },

    async _loadSummary() {
        const div = document.getElementById('gate-summary');
        if (!div) return;
        try {
            const s = await complyApi.getGateSummary();
            if (!s || !(s.total || 0)) { div.innerHTML = ''; return; }
            div.innerHTML = `
            <div class="gate-summary-bar">
                <div class="gate-summary-stat">
                    <span class="gate-summary-num">${s.total || 0}</span>
                    <span class="gate-summary-label">Checks</span>
                </div>
                <div class="gate-summary-stat">
                    <span class="gate-summary-num" style="color:var(--green)">${s.passed || 0}</span>
                    <span class="gate-summary-label">Passed</span>
                </div>
                <div class="gate-summary-stat">
                    <span class="gate-summary-num" style="color:var(--red)">${s.failed || 0}</span>
                    <span class="gate-summary-label">Failed</span>
                </div>
                <div class="gate-summary-stat">
                    <span class="gate-summary-num">${s.passRate || 0}%</span>
                    <span class="gate-summary-label">Pass Rate</span>
                </div>
                <div class="gate-summary-stat">
                    <span class="gate-summary-num">${(s.avgScore || 0).toFixed(0)}%</span>
                    <span class="gate-summary-label">Avg Score</span>
                </div>
            </div>`;
        } catch (e) {
            div.innerHTML = '';
        }
    },

    async _loadDecisions() {
        const container = document.getElementById('gate-decisions');
        try {
            const decisions = await complyApi.listGateDecisions(null, null, 50);
            if (!decisions.length) {
                container.innerHTML = '<p class="empty">No gate decisions yet. Run a gate check above.</p>';
                return;
            }
            let html = `<table class="data-table"><thead><tr>
                <th>Time</th><th>Framework</th><th>Decision</th><th>Score</th>
                <th>Threshold</th><th>Gaps</th><th>Regression</th><th>Commit</th>
            </tr></thead><tbody>`;
            for (const d of decisions) {
                const ts = (d.createdAt || '').substring(0, 19).replace('T', ' ');
                const badge = d.decision === 'pass'
                    ? '<span class="badge badge-success">PASS</span>'
                    : '<span class="badge badge-error">FAIL</span>';
                const sha = (d.commitSha || '').substring(0, 8) || '-';
                const reg = d.regressionDetected ? 'Yes' : '-';
                const maxG = d.maxCriticalGaps < 0 ? '-' : d.maxCriticalGaps;
                const scoreLink = d.scanId
                    ? `<a href="#/detail/${d.scanId}" style="color:inherit;text-decoration:underline">${(d.score || 0).toFixed(1)}%</a>`
                    : `${(d.score || 0).toFixed(1)}%`;
                html += `<tr>
                    <td>${ts}</td>
                    <td>${typeof fwLabel === 'function' ? fwLabel(d.framework || '') : (d.framework || '')}</td>
                    <td>${badge}</td>
                    <td>${scoreLink}</td>
                    <td>${(d.thresholdScore || 0).toFixed(1)}%</td>
                    <td>${d.criticalGapCount || 0}${maxG !== '-' ? ' / ' + maxG : ''}</td>
                    <td>${reg}</td>
                    <td><code>${sha}</code></td>
                </tr>`;
            }
            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<p class="error">Failed to load decisions: ${e.message}</p>`;
        }
    },
};
