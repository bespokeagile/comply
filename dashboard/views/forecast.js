/* Forecast view — compliance score trend analysis and projection */
const ForecastView = {
    async render() {
        const app = document.getElementById('app');
        app.innerHTML = `
            <div class="view-header">
                <h2>Compliance Forecast</h2>
                <p class="subtitle">Score trend analysis and target date projection</p>
            </div>

            <div class="card" style="margin-bottom:1.5rem">
                <h3>Generate Forecast</h3>
                <form id="forecast-form" class="gate-form">
                    <div class="gate-form-row">
                        <label class="gate-field gate-field-grow">
                            <span>Repository</span>
                            <input type="text" id="forecast-repo" list="forecast-repo-list" placeholder="Select or type a repository" class="input" />
                            <datalist id="forecast-repo-list"></datalist>
                        </label>
                        <label class="gate-field">
                            <span>Framework</span>
                            <select id="forecast-framework" class="input">
                                <option value="eu_ai_act">EU AI Act</option>
                            </select>
                        </label>
                        <label class="gate-field gate-field-sm">
                            <span>Target</span>
                            <input type="number" id="forecast-target" value="80" min="0" max="100" step="0.1" class="input" />
                        </label>
                        <label class="gate-field gate-field-sm">
                            <span>Weeks</span>
                            <input type="number" id="forecast-weeks" value="8" min="1" max="52" class="input" />
                        </label>
                        <label class="gate-field" style="align-self:flex-end">
                            <button type="submit" class="btn btn-primary" id="forecast-btn">Forecast</button>
                        </label>
                    </div>
                </form>
            </div>

            <div id="forecast-result"></div>
        `;

        this._bindForm();
        this._loadFrameworks();
        _loadRepoOptions('forecast-repo-list');
        // Pre-fill from URL params (e.g. ?repo=X from sidebar context)
        this._applyUrlParams();
        // Auto-run on load
        this._runForecast();
    },

    _bindForm() {
        document.getElementById('forecast-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this._runForecast();
        });
    },

    /** Parse URL hash params and pre-fill the form. */
    _applyUrlParams() {
        const hashParts = window.location.hash.split('?');
        if (hashParts.length < 2) return;
        const params = new URLSearchParams(hashParts[1]);

        const repo = params.get('repo');
        if (repo) {
            const input = document.getElementById('forecast-repo');
            if (input) input.value = decodeURIComponent(repo);
        }
    },

    async _loadFrameworks() {
        try {
            const fws = await complyApi.getFrameworks();
            const sel = document.getElementById('forecast-framework');
            sel.innerHTML = '';
            for (const fw of fws) {
                const opt = document.createElement('option');
                opt.value = fw.id.replace(/-/g, '_');
                opt.textContent = fw.name || fw.id;
                sel.appendChild(opt);
            }
        } catch (e) { /* keep default */ }
    },

    async _runForecast() {
        const btn = document.getElementById('forecast-btn');
        const container = document.getElementById('forecast-result');
        btn.disabled = true;
        btn.textContent = 'Analyzing...';
        container.innerHTML = '<div class="loading"><span class="spinner"></span> Generating forecast...</div>';

        try {
            const repo = document.getElementById('forecast-repo').value;
            const framework = document.getElementById('forecast-framework').value;
            const targetScore = parseFloat(document.getElementById('forecast-target').value) || 80;
            const weeks = parseInt(document.getElementById('forecast-weeks').value, 10) || 8;

            const data = await complyApi.getForecast(repo, framework, weeks, targetScore);

            if (data.status === 'insufficient_data') {
                const repo = document.getElementById('forecast-repo').value;
                const hint = (!repo || repo === '.')
                    ? 'Select a repository from the dropdown to see its forecast.'
                    : `${data.message || 'Need at least 2 scans for forecasting.'} Run more scans to enable forecasting.`;
                container.innerHTML = `
                    <div class="card">
                        <div class="empty-state">
                            <h3>Insufficient Data</h3>
                            <p>${hint}</p>
                        </div>
                    </div>`;
                return;
            }

            this._renderResult(data);
        } catch (e) {
            container.innerHTML = `<div class="alert alert-error">Error: ${e.message}</div>`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Forecast';
        }
    },

    _renderResult(data) {
        const container = document.getElementById('forecast-result');

        const trendColor = data.trend === 'improving' ? 'var(--green,#22c55e)'
            : data.trend === 'declining' ? 'var(--red,#ef4444)'
            : 'var(--yellow,#eab308)';
        const trendIcon = data.trend === 'improving' ? '\u2191'
            : data.trend === 'declining' ? '\u2193' : '\u2192';
        const riskColor = data.riskLevel === 'low' ? 'var(--green,#22c55e)'
            : data.riskLevel === 'high' ? 'var(--red,#ef4444)'
            : 'var(--yellow,#eab308)';
        const velSign = data.velocity >= 0 ? '+' : '';
        const projStr = data.projectedDate
            ? `${data.projectedDate} (~${Math.ceil((data.daysToTarget || 0) / 7)} wks)`
            : 'N/A';

        let html = '';

        // Summary cards
        html += `<div class="card-row" style="margin-bottom:1.5rem">
            <div class="stat-card">
                <div class="stat-value">${(data.currentScore || 0).toFixed(1)}%</div>
                <div class="stat-label">Current Score</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:${trendColor}">${trendIcon} ${data.trend || 'stable'}</div>
                <div class="stat-label">${velSign}${(data.velocity || 0).toFixed(1)} pts/week</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:${riskColor}">${(data.riskLevel || 'medium').toUpperCase()}</div>
                <div class="stat-label">Risk Level</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${projStr}</div>
                <div class="stat-label">Projected @ ${(data.targetScore || 80)}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${(data.rSquared || 0).toFixed(2)}</div>
                <div class="stat-label">R\u00b2 Fit</div>
            </div>
        </div>`;

        // Chart: history + forecast + target line
        html += `<div class="card" style="margin-bottom:1.5rem">
            <div class="card-header">Score Trajectory</div>
            <div class="chart-container">
                ${this._renderForecastChart(data)}
            </div>
            <div style="padding:0.5rem 1rem;font-size:0.8rem;color:var(--text-muted)">
                <span style="color:var(--accent)">\u2501\u2501</span> Historical &nbsp;
                <span style="color:var(--accent);opacity:0.5">\u2504\u2504</span> Forecast &nbsp;
                <span style="color:var(--yellow)">\u2501\u2501</span> Target (${(data.targetScore || 80)}%)
            </div>
        </div>`;

        // Control trends table
        const ct = data.controlTrends || {};
        const improving = ct.improving || [];
        const declining = ct.declining || [];
        const stuck = ct.stuck || [];

        if (improving.length || declining.length || stuck.length) {
            html += `<div class="card">
                <div class="card-header">Control Trends (Last 2 Scans)</div>`;

            if (improving.length) {
                html += `<h4 style="margin:1rem 1rem 0.5rem;color:var(--green,#22c55e)">\u2191 Improving (${improving.length})</h4>`;
                html += this._controlTable(improving, true);
            }
            if (declining.length) {
                html += `<h4 style="margin:1rem 1rem 0.5rem;color:var(--red,#ef4444)">\u2193 Declining (${declining.length})</h4>`;
                html += this._controlTable(declining, true);
            }
            if (stuck.length) {
                html += `<h4 style="margin:1rem 1rem 0.5rem;color:var(--text-muted)">\u2500 Stuck Gaps (${stuck.length})</h4>`;
                html += `<table class="data-table"><thead><tr><th>Control</th><th>Status</th></tr></thead><tbody>`;
                for (const c of stuck) {
                    html += `<tr><td><code>${c.controlId}</code></td><td><span class="status-badge status-gap">GAP</span></td></tr>`;
                }
                html += '</tbody></table>';
            }
            html += '</div>';
        }

        // Data summary
        html += `<div class="card" style="margin-top:1.5rem">
            <div class="card-header">Data Summary</div>
            <div style="padding:1rem;font-family:monospace;font-size:0.85rem;line-height:1.8">
                Data Points: ${data.dataPoints || 0} scans<br/>
                First Scan: ${data.firstScanDate || '-'}<br/>
                Last Scan: ${data.lastScanDate || '-'}<br/>
                Framework: ${data.framework || '-'}
            </div>
        </div>`;

        container.innerHTML = html;
    },

    _controlTable(controls, showTransition) {
        let html = '<table class="data-table"><thead><tr><th>Control</th><th>From</th><th>To</th></tr></thead><tbody>';
        for (const c of controls) {
            const fromCls = `status-${c.from || 'gap'}`;
            const toCls = `status-${c.to || 'gap'}`;
            html += `<tr>
                <td><code>${c.controlId}</code></td>
                <td><span class="status-badge ${fromCls}">${(c.from || 'gap').toUpperCase()}</span></td>
                <td><span class="status-badge ${toCls}">${(c.to || 'gap').toUpperCase()}</span></td>
            </tr>`;
        }
        html += '</tbody></table>';
        return html;
    },

    _renderForecastChart(data) {
        const history = data.history || [];
        const forecast = data.forecast || [];
        const target = data.targetScore || 80;

        if (!history.length) return '<div class="empty-state">No data to chart</div>';

        const width = 700;
        const height = 250;
        const padding = { top: 20, right: 20, bottom: 30, left: 45 };
        const w = width - padding.left - padding.right;
        const h = height - padding.top - padding.bottom;

        // Combine all data for scale
        const allScores = [
            ...history.map(d => d.score),
            ...forecast.map(d => d.score),
            target,
        ];
        const maxScore = Math.min(100, Math.max(...allScores) + 5);
        const minScore = Math.max(0, Math.min(...allScores) - 5);
        const range = maxScore - minScore || 1;

        // Parse dates for x-axis
        const allDates = [
            ...history.map(d => d.date),
            ...forecast.map(d => d.date),
        ];
        const dateToX = (date, i, total) => {
            return padding.left + (i / Math.max(1, total - 1)) * w;
        };
        const scoreToY = (score) => {
            return padding.top + h - ((score - minScore) / range) * h;
        };

        const totalPoints = history.length + forecast.length;

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

        // Target line
        const targetY = scoreToY(target);
        svg += `<line x1="${padding.left}" y1="${targetY}" x2="${width - padding.right}" y2="${targetY}"
                 stroke="var(--yellow,#eab308)" stroke-width="1.5" stroke-dasharray="6,4"/>`;
        svg += `<text x="${width - padding.right + 2}" y="${targetY + 3}" fill="var(--yellow,#eab308)"
                 font-size="10">${target}%</text>`;

        // History line
        const histPoints = history.map((d, i) => ({
            x: dateToX(d.date, i, totalPoints),
            y: scoreToY(d.score),
            d: d,
        }));
        if (histPoints.length > 1) {
            const pathD = histPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
            svg += `<path d="${pathD}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
        }

        // Forecast line (dashed, from last history point)
        if (forecast.length > 0 && histPoints.length > 0) {
            const forePoints = forecast.map((d, i) => ({
                x: dateToX(d.date, history.length + i, totalPoints),
                y: scoreToY(d.score),
                d: d,
            }));
            const lastHist = histPoints[histPoints.length - 1];
            const forePathD = [`M ${lastHist.x} ${lastHist.y}`, ...forePoints.map(p => `L ${p.x} ${p.y}`)].join(' ');
            svg += `<path d="${forePathD}" fill="none" stroke="var(--accent)" stroke-width="2"
                     stroke-dasharray="6,4" opacity="0.5"/>`;

            // Forecast dots
            for (const p of forePoints) {
                svg += `<circle cx="${p.x}" cy="${p.y}" r="3" fill="var(--accent)" opacity="0.4">
                    <title>${p.d.date}: ${p.d.score}% (projected)</title></circle>`;
            }
        }

        // History dots
        for (const p of histPoints) {
            const color = p.d.score >= 70 ? 'var(--green)' : p.d.score >= 40 ? 'var(--yellow)' : 'var(--red)';
            svg += `<circle cx="${p.x}" cy="${p.y}" r="4" fill="${color}" stroke="var(--bg-secondary)" stroke-width="2">
                <title>${p.d.date}: ${p.d.score}%</title></circle>`;
        }

        // X-axis labels
        const step = Math.max(1, Math.floor(totalPoints / 8));
        for (let i = 0; i < totalPoints; i += step) {
            const date = allDates[i] || '';
            const x = dateToX(date, i, totalPoints);
            const label = date.substring(5, 10);
            svg += `<text x="${x}" y="${height - 5}" text-anchor="middle"
                     fill="var(--text-muted)" font-size="10">${label}</text>`;
        }

        svg += '</svg>';
        return svg;
    },
};
