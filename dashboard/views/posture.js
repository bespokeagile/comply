/* Posture view — portfolio compliance dashboard.
   Shows aggregate compliance across all repos and frameworks.
   Serves as the main content for the Frameworks tab. */
const PostureView = {
    _history: null,

    async render() {
        const app = document.getElementById('app');
        app.innerHTML = '<div class="loading"><span class="spinner"></span> Loading portfolio data...</div>';

        try {
            this._history = await complyApi.getHistory(null, null, 500);
            if (!this._history || this._history.length === 0) {
                // Fallback: show welcome state for new users
                app.innerHTML = `<div class="home-container">${HomeView._renderWelcome()}</div>`;
                return;
            }
            this._renderDashboard();
        } catch (e) {
            app.innerHTML = `<div class="alert alert-error">Failed to load portfolio data: ${e.message}</div>`;
        }
    },

    _renderDashboard() {
        const app = document.getElementById('app');
        const history = this._history;

        // Normalize and compute aggregates
        const repos = {};   // slug -> { name, frameworks: { fw -> { latest, all } } }
        const fwAgg = {};   // fw -> { scores: [], repos: Set, scans: [] }
        const allScores = [];

        for (const scan of history) {
            const repoPath = scan.repo || scan.repo_url || '';
            const parts = repoPath.replace(/\/+$/, '').split('/');
            const slug = parts[parts.length - 1] || repoPath;
            if (!slug || slug === '.' || /\.(xml|sarif|json|sbom|junit)$/i.test(slug)) continue;

            const fw = typeof fwNorm === 'function' ? fwNorm(scan.framework || '') : (scan.framework || '');
            if (!fw) continue;
            const score = scan.score != null ? scan.score : null;

            // Per-repo grouping
            if (!repos[slug]) repos[slug] = { name: slug.charAt(0).toUpperCase() + slug.slice(1), slug, frameworks: {} };
            if (!repos[slug].frameworks[fw]) repos[slug].frameworks[fw] = { latest: null, all: [] };
            repos[slug].frameworks[fw].all.push(scan);
            if (!repos[slug].frameworks[fw].latest || (scan.created_at || '') > (repos[slug].frameworks[fw].latest.created_at || '')) {
                repos[slug].frameworks[fw].latest = scan;
            }

            // Per-framework aggregation
            if (!fwAgg[fw]) fwAgg[fw] = { scores: [], repos: new Set(), scans: [] };
            fwAgg[fw].scans.push(scan);
            fwAgg[fw].repos.add(slug);
            if (score !== null) {
                fwAgg[fw].scores.push(score);
                allScores.push(score);
            }
        }

        // Portfolio-wide score
        const avgScore = allScores.length > 0 ? allScores.reduce((a, b) => a + b, 0) / allScores.length : 0;
        const repoCount = Object.keys(repos).length;
        const fwCount = Object.keys(fwAgg).length;
        const scanCount = history.length;

        let html = `
        <div class="page-header">
            <h2>Compliance Posture</h2>
            <p>Portfolio-wide compliance status across ${repoCount} repositories and ${fwCount} frameworks</p>
        </div>

        <div class="card-row" style="margin-bottom:16px">
            <div class="stat-card">
                ${Components.renderScoreGauge(avgScore, 80)}
                <div class="stat-label">Portfolio Score</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${repoCount}</div>
                <div class="stat-label">Repositories</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${fwCount}</div>
                <div class="stat-label">Frameworks</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${scanCount}</div>
                <div class="stat-label">Total Scans</div>
            </div>
        </div>`;

        // Quick actions strip (self-hosted only)
        if (!(App.capabilities && App.capabilities.demo_mode)) {
            html += `<div class="posture-quick-actions">
                <a href="#/scan" class="btn btn-primary">+ New Scan</a>
                <a href="#/program" class="btn btn-secondary">Programs</a>
            </div>`;
        }

        // Per-framework readiness bars
        html += `<div class="card" style="margin-bottom:16px">
            <div class="card-header">Framework Readiness</div>`;
        const sortedFw = Object.entries(fwAgg).sort((a, b) => {
            const aAvg = a[1].scores.length > 0 ? a[1].scores.reduce((x, y) => x + y, 0) / a[1].scores.length : 0;
            const bAvg = b[1].scores.length > 0 ? b[1].scores.reduce((x, y) => x + y, 0) / b[1].scores.length : 0;
            return bAvg - aAvg;
        });

        for (const [fw, data] of sortedFw) {
            const fwAvg = data.scores.length > 0 ? data.scores.reduce((a, b) => a + b, 0) / data.scores.length : 0;
            const barColor = fwAvg >= 70 ? 'var(--green)' : fwAvg >= 40 ? 'var(--yellow)' : 'var(--red)';
            const label = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
            html += `
            <div class="posture-fw-row">
                <div class="posture-fw-label">
                    <span>${label}</span>
                    <span class="posture-fw-meta">${data.repos.size} repo${data.repos.size !== 1 ? 's' : ''}</span>
                </div>
                <div class="posture-fw-bar-track">
                    <div class="posture-fw-bar-fill" style="width:${Math.min(100, fwAvg)}%;background:${barColor}"></div>
                </div>
                <span class="posture-fw-score" style="color:${barColor}">${Math.round(fwAvg)}%</span>
            </div>`;
        }
        html += '</div>';

        // Repository grid
        html += `<div class="card" style="margin-bottom:16px">
            <div class="card-header">Repository Status</div>
            <div style="overflow-x:auto">
            <table class="data-table">
                <thead><tr>
                    <th>Repository</th>
                    <th>Framework</th>
                    <th>Score</th>
                    <th>Trend</th>
                    <th>Depth</th>
                    <th>Last Scan</th>
                </tr></thead>
                <tbody>`;

        const repoEntries = Object.values(repos).sort((a, b) => a.name.localeCompare(b.name));
        for (const repo of repoEntries) {
            const fwKeys = Object.keys(repo.frameworks);
            for (const fw of fwKeys) {
                const fwData = repo.frameworks[fw];
                const latest = fwData.latest;
                if (!latest) continue;
                const score = latest.score != null ? Math.round(latest.score) : null;
                const scoreColor = score !== null
                    ? (score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)')
                    : '';
                const depth = (latest.scan_depth || latest.depth || '').includes('semantic') ? 'Deep'
                    : (latest.scan_depth || latest.depth || '').includes('structure') ? 'Quick' : 'Standard';
                const date = (latest.created_at || '').substring(0, 10);

                // Trend
                let trend = '';
                if (fwData.all.length >= 2) {
                    const sorted = [...fwData.all].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
                    const curr = sorted[0].score || 0;
                    const prev = sorted[1].score || 0;
                    if (curr > prev) trend = '<span style="color:var(--green)">\u2191</span>';
                    else if (curr < prev) trend = '<span style="color:var(--red)">\u2193</span>';
                    else trend = '<span style="color:var(--text-muted)">\u2192</span>';
                }

                const fwDisplay = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
                html += `<tr style="cursor:pointer" onclick="window.location.hash='#/detail/${latest.id}'">
                    <td><strong>${repo.name}</strong></td>
                    <td>${fwDisplay}</td>
                    <td style="color:${scoreColor};font-weight:600">${score !== null ? score + '%' : '-'}</td>
                    <td>${trend}</td>
                    <td>${depth}</td>
                    <td style="color:var(--text-muted)">${date}</td>
                </tr>`;
            }
        }

        html += `</tbody></table></div></div>`;

        // Top gaps: most common failing controls across all repos
        html += this._renderTopGaps();

        // Improvement trend chart
        html += this._renderTrendChart();

        // Board summary section
        html += this._renderBoardSummary(avgScore, repoCount, fwCount, sortedFw, repoEntries);

        // Programs cross-link (self-hosted only)
        if (!(App.capabilities && App.capabilities.demo_mode)) {
            html += this._renderProgramsLink();
        }

        app.innerHTML = html;
    },

    /** Top gaps across all repos. */
    _renderTopGaps() {
        const controlGaps = {};  // controlId -> { count, frameworks: Set, requirement }
        for (const scan of this._history) {
            if (!scan.report_summary) continue;
            // The history endpoint may not include control details — skip if not available
        }

        // Alternative: aggregate from /posture endpoint or just use score distribution
        // For now, show score distribution as a proxy
        const scores = this._history.filter(s => s.score != null).map(s => s.score);
        if (scores.length === 0) return '';

        const low = scores.filter(s => s < 40).length;
        const mid = scores.filter(s => s >= 40 && s < 70).length;
        const high = scores.filter(s => s >= 70).length;

        return `
        <div class="card" style="margin-bottom:16px">
            <div class="card-header">Score Distribution</div>
            <div style="display:flex;gap:16px;padding:8px 0">
                <div style="flex:1;text-align:center">
                    <div style="font-size:24px;font-weight:700;color:var(--red)">${low}</div>
                    <div style="font-size:12px;color:var(--text-muted)">Below 40%</div>
                </div>
                <div style="flex:1;text-align:center">
                    <div style="font-size:24px;font-weight:700;color:var(--yellow)">${mid}</div>
                    <div style="font-size:12px;color:var(--text-muted)">40-69%</div>
                </div>
                <div style="flex:1;text-align:center">
                    <div style="font-size:24px;font-weight:700;color:var(--green)">${high}</div>
                    <div style="font-size:12px;color:var(--text-muted)">70%+</div>
                </div>
            </div>
        </div>`;
    },

    /** Portfolio score trend over time. */
    _renderTrendChart() {
        const sorted = [...this._history]
            .filter(s => s.score != null && s.created_at)
            .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));

        if (sorted.length < 2) return '';

        const chartData = sorted.map(s => ({
            date: s.created_at || '',
            score: s.score || 0,
            label: `${typeof fwLabel === 'function' ? fwLabel(s.framework || '') : s.framework} (${(s.created_at || '').substring(0, 10)})`,
        }));

        return `
        <div class="card" style="margin-bottom:16px">
            <div class="card-header">Portfolio Score Trend</div>
            <div class="chart-container">
                ${Components.renderLineChart(chartData, 700, 220)}
            </div>
        </div>`;
    },

    /** Board-ready executive summary section. */
    _renderBoardSummary(avgScore, repoCount, fwCount, sortedFw, repoEntries) {
        const scoreColor = avgScore >= 70 ? 'var(--green)' : avgScore >= 40 ? 'var(--yellow)' : 'var(--red)';
        const posture = avgScore >= 70 ? 'Strong' : avgScore >= 40 ? 'Moderate' : 'Needs Attention';

        // Find top risks (lowest scoring repo+framework combos)
        const risks = [];
        for (const repo of repoEntries) {
            for (const [fw, fwData] of Object.entries(repo.frameworks)) {
                const latest = fwData.latest;
                if (latest && latest.score != null && latest.score < 50) {
                    risks.push({ repo: repo.name, fw, score: latest.score });
                }
            }
        }
        risks.sort((a, b) => a.score - b.score);

        let riskHtml = '';
        if (risks.length > 0) {
            riskHtml = `
            <div style="margin-top:12px">
                <strong style="font-size:12px;text-transform:uppercase;color:var(--text-muted)">Key Risks</strong>
                <ul style="margin:8px 0;padding-left:20px;font-size:13px;color:var(--text-secondary)">
                    ${risks.slice(0, 5).map(r =>
                        `<li><strong>${r.repo}</strong> — ${typeof fwLabel === 'function' ? fwLabel(r.fw) : r.fw}: <span style="color:var(--red)">${Math.round(r.score)}%</span></li>`
                    ).join('')}
                </ul>
            </div>`;
        }

        return `
        <div class="card posture-board-summary">
            <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
                <span>Executive Summary</span>
                <button class="btn btn-sm btn-secondary" onclick="PostureView._printSummary()">Print / Save PDF</button>
            </div>
            <div class="posture-exec-grid">
                <div style="text-align:center">
                    ${Components.renderScoreGauge(avgScore, 100)}
                    <div style="font-size:14px;font-weight:600;color:${scoreColor};margin-top:4px">${posture}</div>
                </div>
                <div style="font-size:13px;line-height:1.8;color:var(--text-secondary)">
                    <div><strong>${repoCount}</strong> repositories scanned across <strong>${fwCount}</strong> compliance frameworks.</div>
                    <div>Portfolio compliance score: <strong style="color:${scoreColor}">${Math.round(avgScore)}%</strong></div>
                    ${sortedFw.slice(0, 4).map(([fw, data]) => {
                        const fwAvg = data.scores.length > 0 ? data.scores.reduce((a, b) => a + b, 0) / data.scores.length : 0;
                        const label = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
                        return `<div>${label}: <strong>${Math.round(fwAvg)}%</strong> (${data.repos.size} repos)</div>`;
                    }).join('')}
                    ${riskHtml}
                </div>
            </div>
        </div>`;
    },

    /** Programs cross-link: show count if programs exist. */
    _renderProgramsLink() {
        // Fetch program count (async, but render sync placeholder and fill)
        const id = 'posture-programs-link';
        setTimeout(async () => {
            try {
                const progs = await complyApi.listPrograms();
                const el = document.getElementById(id);
                if (el && progs && progs.length > 0) {
                    el.innerHTML = `<a href="#/program" class="posture-programs-crosslink">${progs.length} Program${progs.length !== 1 ? 's' : ''} configured &rarr;</a>`;
                }
            } catch (e) { /* ignore */ }
        }, 0);
        return `<div id="${id}" style="margin-bottom:16px"></div>`;
    },

    /** Open print dialog for the executive summary. */
    _printSummary() {
        window.print();
    },
};
