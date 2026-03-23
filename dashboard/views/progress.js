/* Progress View — longitudinal compliance tracking for a repo.
   Shows score timeline, control status changes, regressions, and milestones. */
const ProgressView = {
    _repoSlug: null,

    async render(params) {
        const app = document.getElementById('app');
        const slug = params && params[0];

        if (!slug) {
            app.innerHTML = '<div class="alert alert-error">Repository slug required.</div>';
            return;
        }

        this._repoSlug = slug;

        // Gather all scans for this repo, sorted by time
        const allScans = ScanAdapter.list();
        const repoScans = allScans.filter(s => {
            const scanSlug = s.repoSlug || (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').replace(/.*\//, '');
            return scanSlug === slug;
        }).sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

        if (repoScans.length === 0) {
            app.innerHTML = '<div class="alert">No scans found for this repository.</div>';
            return;
        }

        // Load full reports
        const scanData = [];
        for (const s of repoScans) {
            const full = await ScanAdapter.getWithReport(s.id);
            if (full && full.report) {
                scanData.push({
                    id: s.id,
                    framework: s.framework || full.report.framework || '',
                    depth: s.depth || s.scan_depth || full.report.scanDepth || 'structure',
                    timestamp: s.timestamp || s.created_at || '',
                    score: (full.report.summary || {}).score || 0,
                    met: (full.report.summary || {}).met || 0,
                    partial: (full.report.summary || {}).partial || 0,
                    gap: (full.report.summary || {}).gap || 0,
                    total: (full.report.summary || {}).total || 0,
                    report: full.report,
                });
            }
        }

        if (scanData.length === 0) {
            app.innerHTML = '<div class="alert">Could not load scan reports.</div>';
            return;
        }

        const repoName = repoScans[0].repoName || slug;
        const frameworks = [...new Set(scanData.map(s => s.framework))];

        let html = `
        <div class="page-header">
            <h2>Progress: ${repoName}</h2>
            <span class="overlap-subtitle">${scanData.length} scans across ${frameworks.length} framework${frameworks.length !== 1 ? 's' : ''}</span>
        </div>`;

        // Score timeline per framework
        html += this._renderScoreTimeline(scanData, frameworks);

        // Milestones
        html += this._renderMilestones(scanData);

        // Control-level changes (regressions and improvements)
        html += this._renderControlChanges(scanData, frameworks);

        app.innerHTML = html;
    },

    _renderScoreTimeline(scanData, frameworks) {
        let html = '<div class="overlap-section"><h3>Score Timeline</h3>';

        for (const fw of frameworks) {
            const fwScans = scanData.filter(s => s.framework === fw)
                .sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

            if (fwScans.length === 0) continue;

            const chartData = fwScans.map(s => ({
                date: s.timestamp,
                score: s.score,
                label: `${s.depth.includes('semantic') ? 'sem' : 'str'} ${(s.timestamp || '').substring(5, 16).replace('T', ' ')}`,
            }));

            const latest = fwScans[fwScans.length - 1];
            const first = fwScans[0];
            const delta = latest.score - first.score;
            const deltaColor = delta >= 0 ? 'var(--green)' : 'var(--red)';
            const deltaSign = delta >= 0 ? '+' : '';

            html += `
            <div class="card" style="margin-bottom:12px">
                <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
                    <span>${fwLabel(fw)}</span>
                    <span style="font-size:13px">
                        ${first.score.toFixed(1)}%
                        <span style="color:${deltaColor}"> ${deltaSign}${delta.toFixed(1)}% </span>
                        ${latest.score.toFixed(1)}%
                        <span style="color:var(--text-muted);margin-left:8px">${fwScans.length} scan${fwScans.length !== 1 ? 's' : ''}</span>
                    </span>
                </div>
                ${fwScans.length >= 2
                    ? `<div class="chart-container">${Components.renderLineChart(chartData, 650, 140)}</div>`
                    : `<div style="padding:12px;color:var(--text-secondary);font-size:13px">Single scan at ${latest.score.toFixed(1)}%. Rescan to track progress.</div>`
                }
            </div>`;
        }

        html += '</div>';
        return html;
    },

    _renderMilestones(scanData) {
        const milestones = [];
        const fwFirstSeen = {};
        const fwFirst80 = {};

        for (const s of scanData) {
            const fw = s.framework;
            // First scan per framework
            if (!fwFirstSeen[fw]) {
                fwFirstSeen[fw] = s;
                milestones.push({
                    type: 'baseline',
                    label: `Baseline set for ${fwLabel(fw)}`,
                    detail: `${s.score.toFixed(1)}% (${s.depth.includes('semantic') ? 'semantic' : 'structure'})`,
                    timestamp: s.timestamp,
                    color: 'var(--accent)',
                });
            }
            // First 80%
            if (!fwFirst80[fw] && s.score >= 80) {
                fwFirst80[fw] = s;
                milestones.push({
                    type: 'achievement',
                    label: `${fwLabel(fw)} reached 80%`,
                    detail: `${s.score.toFixed(1)}%`,
                    timestamp: s.timestamp,
                    color: 'var(--green)',
                });
            }
        }

        // Check for regressions
        const byFw = {};
        for (const s of scanData) {
            if (!byFw[s.framework]) byFw[s.framework] = [];
            byFw[s.framework].push(s);
        }
        for (const [fw, scans] of Object.entries(byFw)) {
            for (let i = 1; i < scans.length; i++) {
                const delta = scans[i].score - scans[i - 1].score;
                if (delta < -5) {
                    milestones.push({
                        type: 'regression',
                        label: `${fwLabel(fw)} score dropped`,
                        detail: `${scans[i - 1].score.toFixed(1)}% to ${scans[i].score.toFixed(1)}% (${delta.toFixed(1)}%)`,
                        timestamp: scans[i].timestamp,
                        color: 'var(--red)',
                    });
                }
            }
        }

        milestones.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

        if (milestones.length === 0) return '';

        let html = `<div class="overlap-section"><h3>Milestones</h3>
            <div class="progress-milestones">`;

        for (const m of milestones) {
            const date = (m.timestamp || '').substring(0, 10);
            html += `
            <div class="progress-milestone">
                <span class="progress-milestone-dot" style="background:${m.color}"></span>
                <div class="progress-milestone-content">
                    <strong>${m.label}</strong>
                    <span class="progress-milestone-detail">${m.detail}</span>
                </div>
                <span class="progress-milestone-date">${date}</span>
            </div>`;
        }

        html += '</div></div>';
        return html;
    },

    _renderControlChanges(scanData, frameworks) {
        let html = '<div class="overlap-section"><h3>Control Status Changes</h3>';

        // For each framework, compare successive scans to find status changes
        let hasChanges = false;

        for (const fw of frameworks) {
            const fwScans = scanData.filter(s => s.framework === fw)
                .sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

            if (fwScans.length < 2) continue;

            const changes = [];
            for (let i = 1; i < fwScans.length; i++) {
                const prev = fwScans[i - 1].report;
                const curr = fwScans[i].report;
                const prevControls = this._extractControls(prev);
                const currControls = this._extractControls(curr);

                for (const [cid, currStatus] of Object.entries(currControls)) {
                    const prevStatus = prevControls[cid];
                    if (prevStatus && prevStatus !== currStatus) {
                        const improved = this._statusRank(currStatus) > this._statusRank(prevStatus);
                        changes.push({
                            controlId: cid,
                            from: prevStatus,
                            to: currStatus,
                            improved,
                            timestamp: fwScans[i].timestamp,
                        });
                    }
                }
            }

            if (changes.length === 0) continue;
            hasChanges = true;

            const improvements = changes.filter(c => c.improved);
            const regressions = changes.filter(c => !c.improved);

            html += `<div class="card" style="margin-bottom:12px">
                <div class="card-header">${fwLabel(fw)} - ${changes.length} change${changes.length !== 1 ? 's' : ''}</div>
                <div style="padding:8px 12px">`;

            if (improvements.length > 0) {
                html += `<div style="margin-bottom:8px;font-size:12px;color:var(--green);font-weight:600">Improved (${improvements.length})</div>`;
                for (const c of improvements) {
                    html += `<div class="progress-change-item">
                        <strong>${c.controlId}</strong>
                        <span>${Components.renderStatusBadge(c.from)} &#8594; ${Components.renderStatusBadge(c.to)}</span>
                    </div>`;
                }
            }
            if (regressions.length > 0) {
                html += `<div style="margin-bottom:8px;margin-top:8px;font-size:12px;color:var(--red);font-weight:600">Regressed (${regressions.length})</div>`;
                for (const c of regressions) {
                    html += `<div class="progress-change-item">
                        <strong>${c.controlId}</strong>
                        <span>${Components.renderStatusBadge(c.from)} &#8594; ${Components.renderStatusBadge(c.to)}</span>
                    </div>`;
                }
            }

            html += '</div></div>';
        }

        if (!hasChanges) {
            html += '<div class="alert" style="margin-top:8px">No control status changes detected yet. Rescan after making changes to track progress.</div>';
        }

        html += '</div>';
        return html;
    },

    _extractControls(report) {
        const map = {};
        for (const art of (report.articles || [])) {
            for (const ctrl of (art.controls || [])) {
                map[ctrl.controlId || ctrl.id || ''] = ctrl.status || 'gap';
            }
        }
        return map;
    },

    _statusRank(status) {
        return { met: 2, partial: 1, gap: 0 }[status] || 0;
    },
};
