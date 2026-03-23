/* Monitor view — daemon status, monitor CRUD, events, alerts */
const MonitorView = {
    async render() {
        const app = document.getElementById('app');
        app.innerHTML = '<div class="loading">Loading monitors...</div>';

        try {
            const [daemonStatus, monitors, recentEvents, recentAlerts] = await Promise.all([
                complyApi.getMonitorDaemonStatus(),
                complyApi.getMonitors(),
                complyApi.getMonitorRecentEvents(20),
                complyApi.getMonitorRecentAlerts(20),
            ]);

            app.innerHTML = `
                <div class="view-header" style="margin-bottom: 20px;">
                    <h2>Compliance Watches</h2>
                    ${this._renderDaemonBanner(daemonStatus)}
                </div>
                ${await this._renderCreateForm()}
                ${this._renderMonitorCards(monitors)}
                ${this._renderEventsTable(recentEvents, monitors)}
                ${this._renderAlertsTable(recentAlerts, monitors)}
            `;

            this._bindEvents();
            _loadRepoOptions('mon-repo-list');
            this._applyUrlParams();
        } catch (err) {
            app.innerHTML = `<div class="error-box">Failed to load monitors: ${err.message}</div>`;
        }
    },

    _renderDaemonBanner(status) {
        const running = status.running;
        const cls = running ? 'banner-ok' : 'banner-warn';
        const label = running ? 'Running' : 'Stopped';
        return `
            <div class="banner ${cls}">
                <span class="banner-dot ${running ? 'dot-green' : 'dot-gray'}"></span>
                <strong>Daemon: ${label}</strong>
                <span class="banner-detail">
                    Active monitors: ${status.activeMonitors} &middot;
                    Queue: ${status.queueDepth}
                </span>
            </div>
        `;
    },

    async _renderCreateForm() {
        const repoOptions = ''; // populated async after render

        return `
            <div class="card" id="create-monitor-card">
                <h3>Watch a Repository</h3>
                <form id="create-monitor-form" class="monitor-form">
                    <div class="monitor-form-row">
                        <div class="monitor-form-field monitor-form-repo">
                            <label for="mon-repo">Repository</label>
                            <input type="text" id="mon-repo" list="mon-repo-list"
                                   placeholder="Path or URL" required class="input" />
                            <datalist id="mon-repo-list">${repoOptions}</datalist>
                        </div>
                        <div class="monitor-form-field">
                            <label for="mon-framework">Framework</label>
                            <select id="mon-framework" class="input">
                                <option value="eu_ai_act">EU AI Act</option>
                                <option value="nist_ai_rmf">NIST AI RMF</option>
                                <option value="iso_42001">ISO 42001</option>
                                <option value="soc2_ai">SOC 2 AI</option>
                                <option value="owasp_llm_top10">OWASP LLM Top 10</option>
                            </select>
                        </div>
                        <div class="monitor-form-field monitor-form-sm">
                            <label for="mon-interval">Interval (s)</label>
                            <input type="number" id="mon-interval" value="300" min="30" class="input" />
                        </div>
                    </div>
                    <div class="monitor-form-row">
                        <div class="monitor-form-field" style="flex:1">
                            <label for="mon-webhook">Webhook URL (optional)</label>
                            <input type="text" id="mon-webhook" placeholder="https://..." class="input" />
                        </div>
                        <div class="monitor-form-field monitor-form-btn">
                            <label>&nbsp;</label>
                            <button type="submit" class="btn btn-primary">Create</button>
                        </div>
                    </div>
                </form>
            </div>
        `;
    },

    _renderMonitorCards(monitors) {
        if (!monitors || monitors.length === 0) {
            return '<div class="card"><p class="muted">No monitors configured yet. Create one above to start watching for compliance drift.</p></div>';
        }
        const cards = monitors.map(m => {
            const statusCls = m.status === 'running' ? 'status-running'
                : m.status === 'error' ? 'status-error' : 'status-stopped';
            const score = m.last_scan_id ? `${m.last_score.toFixed(1)}%` : '-';
            const scoreColor = m.last_score != null
                ? (m.last_score >= 70 ? 'var(--green)' : m.last_score >= 40 ? 'var(--yellow)' : 'var(--red)')
                : '';
            const sha = m.last_sha ? m.last_sha.substring(0, 8) : '-';
            const repoName = m.repo_path.split('/').filter(Boolean).pop() || m.repo_path;
            const fwDisplay = m.framework.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            const repoEnc = encodeURIComponent(m.repo_path);
            const fwEnc = encodeURIComponent(m.framework);

            // Gate cross-link
            const gateLink = `<a href="#/gate?repo=${repoEnc}&framework=${fwEnc}" class="btn btn-sm btn-secondary" style="text-decoration:none;font-size:11px">Run Gate Check</a>`;
            // Detail link
            const detailLink = m.last_scan_id
                ? `<a href="#/detail/${m.last_scan_id}" class="btn btn-sm btn-secondary" style="text-decoration:none;font-size:11px">View Last Scan</a>`
                : '';

            return `
                <div class="card monitor-card" data-id="${m.id}">
                    <div class="monitor-row">
                        <div class="monitor-left">
                            <div class="monitor-header">
                                <span class="monitor-name">${repoName}</span>
                                <span class="monitor-fw">${fwDisplay}</span>
                                <span class="badge ${statusCls}">${m.status}</span>
                            </div>
                            <div class="monitor-meta">
                                <span class="monitor-path">${m.repo_path}</span>
                                ${m.last_error ? `<br><span class="error-text">${m.last_error}</span>` : ''}
                            </div>
                        </div>
                        <div class="monitor-stats">
                            <div class="monitor-stat"><span class="monitor-stat-label">Interval</span><span>${m.interval_secs}s</span></div>
                            <div class="monitor-stat"><span class="monitor-stat-label">Score</span><span style="color:${scoreColor};font-weight:600">${score}</span></div>
                            <div class="monitor-stat"><span class="monitor-stat-label">SHA</span><span><code>${sha}</code></span></div>
                        </div>
                        <div class="monitor-actions">
                            ${m.status !== 'running'
                                ? `<button class="btn btn-sm btn-success mon-start" data-id="${m.id}">Start</button>`
                                : `<button class="btn btn-sm btn-warn mon-stop" data-id="${m.id}">Stop</button>`
                            }
                            <button class="btn btn-sm btn-danger mon-delete" data-id="${m.id}">Delete</button>
                        </div>
                    </div>
                    <div style="display:flex;gap:6px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
                        ${detailLink}
                        ${gateLink}
                    </div>
                </div>
            `;
        }).join('');

        return `<div class="card-grid">${cards}</div>`;
    },

    _monitorLabel(id, monitors) {
        const m = (monitors || []).find(mon => mon.id === id);
        if (!m) return '<span class="text-muted">deleted</span>';
        const name = m.repo_path.split('/').filter(Boolean).pop() || m.repo_path;
        const fw = m.framework.replace(/_/g, ' ');
        return `${name} (${fw})`;
    },

    _renderEventsTable(events, monitors) {
        if (!events || events.length === 0) {
            return '';
        }
        const rows = events.map(e => {
            const ts = (e.created_at || '').substring(0, 19);
            const sha = (e.commit_sha || '').substring(0, 8) || '-';
            const score = e.scan_id ? `${e.score.toFixed(1)}%` : '-';
            const typeCls = e.event_type === 'regression' ? 'text-danger'
                : e.event_type === 'error' ? 'text-warn' : '';
            const label = this._monitorLabel(e.monitor_id, monitors);
            // Link score to scan detail if available
            const scoreLink = e.scan_id
                ? `<a href="#/detail/${e.scan_id}" style="color:inherit;text-decoration:underline">${score}</a>`
                : score;
            return `<tr>
                <td>${ts}</td>
                <td>${label}</td>
                <td class="${typeCls}">${e.event_type}</td>
                <td><code>${sha}</code></td>
                <td>${scoreLink}</td>
            </tr>`;
        }).join('');

        return `
            <div class="card">
                <h3>Recent Events</h3>
                <table class="data-table">
                    <thead><tr>
                        <th>Time</th><th>Monitor</th><th>Type</th><th>SHA</th><th>Score</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    },

    _renderAlertsTable(alerts, monitors) {
        if (!alerts || alerts.length === 0) {
            return '';
        }
        const rows = alerts.map(a => {
            const ts = (a.created_at || '').substring(0, 19);
            const dispatched = a.dispatched ? 'Yes' : 'No';
            const sevCls = a.severity === 'high' ? 'text-danger'
                : a.severity === 'medium' ? 'text-warn' : '';
            const label = this._monitorLabel(a.monitor_id, monitors);
            return `<tr>
                <td>${ts}</td>
                <td>${label}</td>
                <td>${a.alert_type}</td>
                <td class="${sevCls}">${a.severity}</td>
                <td>${dispatched}</td>
                <td>${a.response_code || '-'}</td>
            </tr>`;
        }).join('');

        return `
            <div class="card">
                <h3>Alert History</h3>
                <table class="data-table">
                    <thead><tr>
                        <th>Time</th><th>Monitor</th><th>Type</th><th>Severity</th><th>Sent</th><th>Code</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    },

    /** Pre-fill create form from URL params (e.g. ?repo=X&framework=Y). */
    _applyUrlParams() {
        const hashParts = window.location.hash.split('?');
        if (hashParts.length < 2) return;
        const params = new URLSearchParams(hashParts[1]);
        const repo = params.get('repo');
        const fw = params.get('framework');
        if (repo) {
            const input = document.getElementById('mon-repo');
            if (input) input.value = decodeURIComponent(repo);
        }
        if (fw) {
            const sel = document.getElementById('mon-framework');
            if (sel) sel.value = fw;
        }
    },

    _bindEvents() {
        // Create form
        const form = document.getElementById('create-monitor-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const repo = document.getElementById('mon-repo').value;
                const fw = document.getElementById('mon-framework').value;
                const interval = parseInt(document.getElementById('mon-interval').value) || 300;
                const webhook = document.getElementById('mon-webhook').value;
                try {
                    await complyApi.createMonitor(repo, fw, 'content', interval, 500, webhook);
                    this.render();
                } catch (err) {
                    alert('Failed to create monitor: ' + err.message);
                }
            });
        }

        // Start buttons
        document.querySelectorAll('.mon-start').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    await complyApi.startMonitor(btn.dataset.id);
                    this.render();
                } catch (err) {
                    alert('Failed to start: ' + err.message);
                }
            });
        });

        // Stop buttons
        document.querySelectorAll('.mon-stop').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    await complyApi.stopMonitor(btn.dataset.id);
                    this.render();
                } catch (err) {
                    alert('Failed to stop: ' + err.message);
                }
            });
        });

        // Delete buttons
        document.querySelectorAll('.mon-delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm('Delete this monitor and all its history?')) return;
                try {
                    await complyApi.deleteMonitor(btn.dataset.id);
                    this.render();
                } catch (err) {
                    alert('Failed to delete: ' + err.message);
                }
            });
        });
    },
};

/* Compliance Watch Detail — unified view for a repo+framework pair.
   Shows monitoring status, gate decisions, score trend, and next steps. */
const MonitorDetailView = {
    _monitor: null,
    _events: null,
    _alerts: null,
    _gateDecisions: null,

    async render(monitorId) {
        const app = document.getElementById('app');
        app.innerHTML = '<div class="loading">Loading...</div>';

        try {
            const [monitor, events, alerts] = await Promise.all([
                complyApi.getMonitor(monitorId),
                complyApi.getMonitorEvents(monitorId, 30),
                complyApi.getMonitorAlerts(monitorId, 10),
            ]);

            if (!monitor) {
                app.innerHTML = '<div class="error-box">Monitor not found. <a href="#/monitor">Back</a></div>';
                return;
            }

            this._monitor = monitor;
            this._events = events || [];
            this._alerts = alerts || [];

            // Fetch gate decisions for same repo+framework
            try {
                this._gateDecisions = await complyApi.listGateDecisions(
                    monitor.repo_path, monitor.framework, 20
                ) || [];
            } catch (e) { this._gateDecisions = []; }

            const m = monitor;
            const repoName = m.repo_path.split('/').filter(Boolean).pop() || m.repo_path;
            const fwDisplay = typeof fwLabel === 'function' ? fwLabel(m.framework) : m.framework.replace(/_/g, ' ');
            const statusCls = m.status === 'running' ? 'status-running' : m.status === 'error' ? 'status-error' : 'status-stopped';
            const repoEnc = encodeURIComponent(m.repo_path);
            const fwEnc = encodeURIComponent(m.framework);

            app.innerHTML = `
                <div class="view-header" style="margin-bottom:20px">
                    <div style="display:flex;align-items:center;gap:12px">
                        <a href="#/monitor" style="color:var(--text-muted);text-decoration:none;font-size:18px" title="All watches">&larr;</a>
                        <div>
                            <h2 style="margin:0">${repoName}</h2>
                            <p class="subtitle">${fwDisplay}</p>
                        </div>
                    </div>
                </div>

                ${this._renderStatusRow(m, statusCls)}
                ${this._renderScoreTrend()}
                ${this._renderNextSteps(m, repoEnc, fwEnc)}
                ${this._renderTimeline()}
                ${this._renderAlerts()}
            `;

            this._bindActions(monitorId, m);
        } catch (err) {
            app.innerHTML = `<div class="error-box">Failed to load: ${err.message}. <a href="#/monitor">Back</a></div>`;
        }
    },

    _renderStatusRow(m, statusCls) {
        const sha = m.last_sha ? m.last_sha.substring(0, 8) : '-';
        const interval = m.interval_secs >= 3600
            ? (m.interval_secs / 3600).toFixed(1) + 'h'
            : m.interval_secs >= 60
                ? Math.round(m.interval_secs / 60) + 'm'
                : m.interval_secs + 's';
        const gateCount = this._gateDecisions.length;
        const lastGate = gateCount > 0 ? this._gateDecisions[0] : null;
        const lastGateBadge = lastGate
            ? (lastGate.decision === 'pass'
                ? '<span class="badge badge-success">PASS</span>'
                : '<span class="badge badge-error">FAIL</span>')
            : '<span style="color:var(--text-muted)">No checks yet</span>';

        return `
        <div class="card" style="margin-bottom:1.5rem">
            <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap">
                <div style="text-align:center">
                    ${Components.renderScoreGauge(m.last_score || 0, 80)}
                    <div style="font-size:11px;color:var(--text-muted);margin-top:4px">Current Score</div>
                </div>
                <div style="flex:1;min-width:0">
                    <div class="watch-status-grid">
                        <div class="watch-status-section">
                            <div class="watch-status-label">Continuous Monitoring</div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span class="badge ${statusCls}">${m.status}</span>
                                <span style="font-size:12px;color:var(--text-muted)">every ${interval}</span>
                            </div>
                            <div style="font-size:12px;color:var(--text-muted);margin-top:2px">
                                Commit: <code>${sha}</code>
                                ${m.last_error ? `<br><span style="color:var(--red)">${m.last_error}</span>` : ''}
                            </div>
                        </div>
                        <div class="watch-status-section">
                            <div class="watch-status-label">CI/CD Gate</div>
                            <div style="display:flex;align-items:center;gap:8px">
                                ${lastGateBadge}
                                ${gateCount > 0 ? `<span style="font-size:12px;color:var(--text-muted)">${gateCount} checks</span>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
                <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">
                    ${m.status !== 'running'
                        ? '<button class="btn btn-sm btn-success mon-detail-start">Start Monitor</button>'
                        : '<button class="btn btn-sm btn-warn mon-detail-stop">Stop Monitor</button>'
                    }
                    <button class="btn btn-sm btn-primary watch-run-gate">Run Gate Check</button>
                    ${m.last_scan_id ? `<a href="#/detail/${m.last_scan_id}" class="btn btn-sm btn-secondary" style="text-decoration:none;text-align:center">View Scan</a>` : ''}
                </div>
            </div>
        </div>`;
    },

    _renderScoreTrend() {
        // Merge monitor events and gate decisions into one timeline
        const monScores = this._events
            .filter(e => e.event_type === 'scan' || e.event_type === 'regression')
            .map(e => ({ ts: e.created_at || '', score: e.score || 0, source: 'monitor' }));
        const gateScores = this._gateDecisions
            .map(d => ({ ts: d.createdAt || '', score: d.score || 0, source: 'gate' }));

        const all = [...monScores, ...gateScores]
            .sort((a, b) => a.ts.localeCompare(b.ts));

        if (all.length < 2) return '';

        const series = all.map(e => ({
            label: e.ts.substring(5, 16),
            value: e.score,
        }));

        return `
        <div class="card" style="margin-bottom:1.5rem">
            <div class="card-header">Compliance Score Over Time</div>
            ${Components.renderLineChart(series, { height: 120, showDots: true })}
            <div style="font-size:11px;color:var(--text-muted);margin-top:8px;text-align:right">
                Combines monitor scans and gate checks
            </div>
        </div>`;
    },

    _renderNextSteps(m, repoEnc, fwEnc) {
        const steps = [];
        const gateCount = this._gateDecisions.length;
        const lastGate = gateCount > 0 ? this._gateDecisions[0] : null;

        // Priority 1: score is low
        if (m.last_score != null && m.last_score < 70) {
            steps.push({
                icon: '&#9888;',
                label: 'Score is below 70% — review gaps',
                desc: 'Open the scan report to see which controls are failing and what to fix first.',
                href: m.last_scan_id ? `#/detail/${m.last_scan_id}` : null,
                btnText: 'View Report',
            });
        }

        // Priority 2: last gate failed
        if (lastGate && lastGate.decision === 'fail') {
            steps.push({
                icon: '&#10060;',
                label: 'Last gate check failed',
                desc: `${lastGate.reason || 'Score or gap threshold not met.'}`,
                href: lastGate.scanId ? `#/detail/${lastGate.scanId}` : null,
                btnText: 'See Why',
            });
        }

        // Priority 3: no gate configured yet
        if (gateCount === 0) {
            steps.push({
                icon: '&#9881;',
                label: 'Add a CI/CD gate to your pipeline',
                desc: 'Block non-compliant deploys automatically.',
                href: null,
                btnText: null,
                cliHint: `bespoketracker-comply gate --repo ${m.repo_path} --framework ${m.framework} --threshold 70`,
            });
        }

        // Priority 4: monitoring stopped
        if (m.status !== 'running') {
            steps.push({
                icon: '&#9208;',
                label: 'Monitoring is paused',
                desc: 'Start the monitor to detect compliance drift automatically.',
                href: null,
                btnText: null,
            });
        }

        // Always: scan report link if available
        if (m.last_scan_id && m.last_score >= 70) {
            steps.push({
                icon: '&#9989;',
                label: 'Looking good — keep it up',
                desc: 'Your compliance score is healthy. Review the full report for details.',
                href: `#/detail/${m.last_scan_id}`,
                btnText: 'View Report',
            });
        }

        if (!steps.length) return '';

        return `
        <div class="card" style="margin-bottom:1.5rem">
            <div class="card-header">What to Do Next</div>
            ${steps.map(s => `
                <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
                    <span style="font-size:16px;flex-shrink:0;width:22px;text-align:center">${s.icon}</span>
                    <div style="flex:1;min-width:0">
                        <strong style="font-size:13px">${s.label}</strong>
                        <div style="font-size:12px;color:var(--text-muted);margin-top:2px">${s.desc}</div>
                        ${s.cliHint ? `<pre class="gate-cli-hint" style="margin-top:6px;margin-bottom:0"><code>${s.cliHint}</code></pre>` : ''}
                    </div>
                    ${s.href && s.btnText ? `<a href="${s.href}" class="btn btn-sm btn-secondary" style="text-decoration:none;flex-shrink:0">${s.btnText}</a>` : ''}
                </div>
            `).join('')}
        </div>`;
    },

    /** Unified timeline: monitor events + gate decisions, sorted newest first. */
    _renderTimeline() {
        const items = [];

        for (const e of this._events) {
            const ts = e.created_at || '';
            const sha = (e.commit_sha || '').substring(0, 8) || '-';
            const typeCls = e.event_type === 'regression' ? 'style="color:var(--red);font-weight:600"'
                : e.event_type === 'error' ? 'style="color:var(--yellow)"' : '';
            const delta = e.score_delta
                ? (e.score_delta > 0 ? `<span style="color:var(--green)">+${e.score_delta.toFixed(1)}</span>` : `<span style="color:var(--red)">${e.score_delta.toFixed(1)}</span>`)
                : '';
            const scoreLink = e.scan_id
                ? `<a href="#/detail/${e.scan_id}" style="color:inherit;text-decoration:underline">${(e.score || 0).toFixed(1)}%</a>`
                : `${(e.score || 0).toFixed(1)}%`;
            items.push({
                ts,
                html: `<tr>
                    <td>${ts.substring(0, 19).replace('T', ' ')}</td>
                    <td><span class="badge badge-muted">Monitor</span></td>
                    <td ${typeCls}>${e.event_type}</td>
                    <td>${scoreLink}</td>
                    <td>${delta}</td>
                    <td><code>${sha}</code></td>
                </tr>`,
            });
        }

        for (const d of this._gateDecisions) {
            const ts = d.createdAt || '';
            const sha = (d.commitSha || '').substring(0, 8) || '-';
            const badge = d.decision === 'pass'
                ? '<span class="badge badge-success">PASS</span>'
                : '<span class="badge badge-error">FAIL</span>';
            const scoreLink = d.scanId
                ? `<a href="#/detail/${d.scanId}" style="color:inherit;text-decoration:underline">${(d.score || 0).toFixed(1)}%</a>`
                : `${(d.score || 0).toFixed(1)}%`;
            items.push({
                ts,
                html: `<tr>
                    <td>${ts.substring(0, 19).replace('T', ' ')}</td>
                    <td><span class="badge badge-accent">Gate</span></td>
                    <td>${badge}</td>
                    <td>${scoreLink}</td>
                    <td></td>
                    <td><code>${sha}</code></td>
                </tr>`,
            });
        }

        if (!items.length) return '';

        // Sort newest first
        items.sort((a, b) => b.ts.localeCompare(a.ts));

        return `
        <div class="card" style="margin-bottom:1.5rem">
            <div class="card-header">Activity</div>
            <div class="table-wrap">
                <table class="data-table"><thead><tr>
                    <th>Time</th><th>Source</th><th>Result</th><th>Score</th><th>Delta</th><th>Commit</th>
                </tr></thead><tbody>${items.map(i => i.html).join('')}</tbody></table>
            </div>
        </div>`;
    },

    _renderAlerts() {
        if (!this._alerts.length) return '';

        const rows = this._alerts.map(a => {
            const ts = (a.created_at || '').substring(0, 19).replace('T', ' ');
            const sevCls = a.severity === 'high' ? 'style="color:var(--red);font-weight:600"'
                : a.severity === 'medium' ? 'style="color:var(--yellow)"' : '';
            return `<tr>
                <td>${ts}</td>
                <td>${a.alert_type}</td>
                <td ${sevCls}>${a.severity}</td>
                <td>${a.dispatched ? 'Yes' : 'No'}</td>
                <td>${a.response_code || '-'}</td>
            </tr>`;
        }).join('');

        return `
        <div class="card">
            <div class="card-header">Alerts</div>
            <div class="table-wrap">
                <table class="data-table"><thead><tr>
                    <th>Time</th><th>Type</th><th>Severity</th><th>Sent</th><th>Code</th>
                </tr></thead><tbody>${rows}</tbody></table>
            </div>
        </div>`;
    },

    _bindActions(monitorId, m) {
        const startBtn = document.querySelector('.mon-detail-start');
        if (startBtn) {
            startBtn.addEventListener('click', async () => {
                try { await complyApi.startMonitor(monitorId); this.render(monitorId); }
                catch (e) { alert('Failed to start: ' + e.message); }
            });
        }
        const stopBtn = document.querySelector('.mon-detail-stop');
        if (stopBtn) {
            stopBtn.addEventListener('click', async () => {
                try { await complyApi.stopMonitor(monitorId); this.render(monitorId); }
                catch (e) { alert('Failed to stop: ' + e.message); }
            });
        }
        const deleteBtn = document.querySelector('.mon-detail-delete');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', async () => {
                if (!confirm('Delete this compliance watch and all its history?')) return;
                try { await complyApi.deleteMonitor(monitorId); window.location.hash = '#/monitor'; }
                catch (e) { alert('Failed to delete: ' + e.message); }
            });
        }
        // Run Gate inline
        const gateBtn = document.querySelector('.watch-run-gate');
        if (gateBtn) {
            gateBtn.addEventListener('click', async () => {
                gateBtn.disabled = true;
                gateBtn.textContent = 'Running...';
                try {
                    await complyApi.runGate(m.repo_path, m.framework, 0, false, -1);
                    this.render(monitorId); // Refresh to show new gate decision
                } catch (e) {
                    alert('Gate check failed: ' + e.message);
                    gateBtn.disabled = false;
                    gateBtn.textContent = 'Run Gate Check';
                }
            });
        }
    },
};
