/* Unified Compare Panel — repo+framework selection renders compare with
   Graph / Evidence / Remediation toggle and timeline filmstrip. */
const CompareView = {
    _activeMode: 'graph',
    _scan1: null,
    _scan2: null,
    _report1: null,
    _report2: null,
    _allScans: [],  // all scans for this repo+framework

    /** Render compare panel for two scan IDs (delegates from #/diff/:id1/:id2). */
    async render(params) {
        const app = document.getElementById('app');
        const id1 = params[0];
        const id2 = params[1];

        if (!id1 || !id2) {
            app.innerHTML = '<div class="alert alert-error">Two scan IDs required.</div>';
            return;
        }

        /* ScanAdapter always available — try client-side data first */

        const s1 = await ScanAdapter.getWithReport(id1);
        const s2 = await ScanAdapter.getWithReport(id2);
        if (!s1 || !s2 || !s1.report || !s2.report) {
            return DiffView.render(params);
        }

        this._scan1 = s1;
        this._scan2 = s2;
        this._report1 = s1.report;
        this._report2 = s2.report;

        // Gather all scans for this repo+framework for filmstrip
        const url = (s2.url || s2.repo_url || '').toLowerCase();
        const fw = s2.framework || '';
        const allScans = ScanAdapter.list();
        this._allScans = allScans.filter(s =>
            s.framework === fw &&
            (s.url || s.repo_url || '').toLowerCase() === url
        ).sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

        this._renderPanel(id1, id2);
    },

    /** Render for a repo slug and framework (from sidebar). */
    async renderForRepo(slug, framework) {
        if (!ScanAdapter) return;
        const allScans = ScanAdapter.list();
        const repoScans = allScans.filter(s =>
            (s.repoSlug === slug || (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').endsWith(slug)) &&
            s.framework === framework
        ).sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

        if (repoScans.length === 0) return;

        this._allScans = repoScans;
        const latest = repoScans[repoScans.length - 1];

        if (repoScans.length >= 2) {
            const prev = repoScans[repoScans.length - 2];
            this._scan1 = prev;
            this._scan2 = latest;
            this._report1 = prev.report;
            this._report2 = latest.report;
            this._renderPanel(prev.id, latest.id);
        } else {
            // Single scan: show detail
            window.location.hash = `/detail/${latest.id}`;
        }
    },

    _renderPanel(id1, id2) {
        const app = document.getElementById('app');
        const r1 = this._report1;
        const r2 = this._report2;
        const isDepthCompare = (r1.scanDepth || '') !== (r2.scanDepth || '');

        const diff = DiffView._computeLocalDiff(r1, r2);
        const fw = r2.framework || r1.framework || '';
        const repo = (r2.target || r1.target || '').replace(/.*\//, '');

        // Score header
        let label1, label2, class1, class2;
        if (isDepthCompare) {
            const isR1Struct = (r1.scanDepth || '').includes('structure');
            label1 = isR1Struct ? 'Structure' : 'Semantic';
            label2 = isR1Struct ? 'Semantic' : 'Structure';
            class1 = isR1Struct ? 'structure' : 'semantic';
            class2 = isR1Struct ? 'semantic' : 'structure';
        } else {
            const date1 = (r1.generatedAt || '').substring(5, 16).replace('T', ' ');
            const date2 = (r2.generatedAt || '').substring(5, 16).replace('T', ' ');
            label1 = 'Previous' + (date1 ? ` (${date1})` : '');
            label2 = 'Latest' + (date2 ? ` (${date2})` : '');
            class1 = '';
            class2 = '';
        }

        // Check if remediation data is available
        const hasRemediation = (r2.remediations && r2.remediations.length > 0) ||
                               (r1.remediations && r1.remediations.length > 0);

        let html = `
        <div class="page-header">
            <h2>${typeof fwLabel === 'function' ? fwLabel(fw) : fw}: ${repo}</h2>
        </div>

        ${Components.renderCompareScoreHeader({
            score1: diff.score1, score2: diff.score2,
            id1, id2, label1, label2, class1, class2, delta: diff.delta,
        })}

        <div class="compare-panel-toggle">
            <button class="compare-mode-btn${this._activeMode === 'graph' ? ' active' : ''}"
                data-compare-mode="graph" onclick="CompareView.switchMode('graph')">Graph</button>
            <button class="compare-mode-btn${this._activeMode === 'evidence' ? ' active' : ''}"
                data-compare-mode="evidence" onclick="CompareView.switchMode('evidence')">Evidence</button>
            <button class="compare-mode-btn${this._activeMode === 'remediation' ? ' active' : ''}"
                data-compare-mode="remediation" onclick="CompareView.switchMode('remediation')">Remediation</button>
            <button class="compare-report-btn" onclick="ReportGenerator.fromCompare('${id1}','${id2}')" title="Generate compliance report">Report</button>
        </div>

        <div id="compare-body">
            ${this._renderBody(diff)}
        </div>

        ${this._renderFilmstrip(id1, id2)}`;

        app.innerHTML = html;
    },

    switchMode(mode) {
        this._activeMode = mode;
        // Update buttons
        document.querySelectorAll('.compare-panel-toggle .compare-mode-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.compareMode === mode);
        });
        // Re-render body
        const body = document.getElementById('compare-body');
        if (body && this._report1 && this._report2) {
            const diff = DiffView._computeLocalDiff(this._report1, this._report2);
            body.innerHTML = this._renderBody(diff);
        }
    },

    _renderBody(diff) {
        switch (this._activeMode) {
            case 'graph': return this._renderGraphBody();
            case 'evidence': return this._renderEvidenceBody(diff);
            case 'remediation': { const h = this._renderRemediationBody(); setTimeout(() => Components._updateWhatIfDisplay(), 0); return h; }
            default: return this._renderGraphBody();
        }
    },

    _renderGraphBody() {
        // Always show newest scan on top
        const t1 = this._report1.generatedAt || this._scan1?.timestamp || '';
        const t2 = this._report2.generatedAt || this._scan2?.timestamp || '';
        const newerFirst = t2 >= t1;
        const topReport = newerFirst ? this._report2 : this._report1;
        const botReport = newerFirst ? this._report1 : this._report2;

        const isDepthCompare = (topReport.scanDepth || '') !== (botReport.scanDepth || '');

        const topDepth = (topReport.scanDepth || '').includes('semantic') ? 'Semantic' : 'Structure';
        const botDepth = (botReport.scanDepth || '').includes('semantic') ? 'Semantic' : 'Structure';
        const topColor = topDepth === 'Semantic' ? 'color:#a78bfa' : '';
        const botColor = botDepth === 'Semantic' ? 'color:#a78bfa' : '';

        const topLabel = isDepthCompare ? `${topDepth} Scan` : 'Latest';
        const botLabel = isDepthCompare ? `${botDepth} Scan` : 'Previous';

        return `
        <div class="compare-stacked-graph">
            <div>
                <div class="compare-graph-label" style="${topColor}">${topLabel}</div>
                ${Components.renderCompactReport(topReport)}
            </div>
            <div>
                <div class="compare-graph-label" style="${botColor}">${botLabel}</div>
                ${Components.renderCompactReport(botReport)}
            </div>
        </div>
        <div class="card" style="margin-top:16px">
            <div class="card-header">Control Categories (${topLabel})</div>
            ${Components.renderCategoryBreakdown(topReport)}
        </div>`;
    },

    _renderEvidenceBody(diff) {
        const isDepthCompare = (this._report1.scanDepth || '') !== (this._report2.scanDepth || '');
        const depthLabels = isDepthCompare
            ? { old: 'Structure found', new: 'Semantic found' }
            : { old: 'Previous scan', new: 'Latest scan' };

        let html = `
        <div class="card" style="margin-bottom:16px">
            <div style="display:flex;gap:24px;justify-content:center;padding:8px 0;font-size:14px">
                ${diff.improved.length > 0
                    ? `<span style="color:var(--green)"><strong>${diff.improved.length}</strong> improved</span>` : ''}
                <span style="color:var(--text-muted)"><strong>${diff.unchanged.length}</strong> unchanged</span>
                ${diff.regressed.length > 0
                    ? `<span style="color:var(--red)"><strong>${diff.regressed.length}</strong> regressed</span>` : ''}
            </div>
        </div>`;

        let sectionIdx = 0;

        if (diff.improved.length > 0) {
            const id = 'compare-improved';
            const isFirst = sectionIdx === 0;
            sectionIdx++;
            let body = '';
            for (const c of diff.improved) {
                body += DiffView._renderControlComparison(c, depthLabels);
            }
            html += `
            <div class="accordion-item${isFirst ? ' open' : ''}" id="${id}">
                <div class="accordion-header" onclick="Components.toggleAccordion('${id}')">
                    <span style="color:var(--green)">Improved (${diff.improved.length})</span>
                    <span class="accordion-chevron">&#9656;</span>
                </div>
                <div class="accordion-body">${body}</div>
            </div>`;
        }

        if (diff.regressed.length > 0) {
            const id = 'compare-regressed';
            const isFirst = sectionIdx === 0;
            sectionIdx++;
            let body = '';
            for (const c of diff.regressed) {
                body += DiffView._renderControlComparison(c, depthLabels);
            }
            html += `
            <div class="accordion-item${isFirst ? ' open' : ''}" id="${id}">
                <div class="accordion-header" onclick="Components.toggleAccordion('${id}')">
                    <span style="color:var(--red)">Regressed (${diff.regressed.length})</span>
                    <span class="accordion-chevron">&#9656;</span>
                </div>
                <div class="accordion-body">${body}</div>
            </div>`;
        }

        if (diff.unchanged.length > 0) {
            const id = 'compare-unchanged';
            const isFirst = sectionIdx === 0;
            html += `
            <div class="accordion-item${isFirst ? ' open' : ''}" id="${id}">
                <div class="accordion-header" onclick="Components.toggleAccordion('${id}')">
                    <span>Unchanged (${diff.unchanged.length})</span>
                    <span class="accordion-chevron">&#9656;</span>
                </div>
                <div class="accordion-body">
                    ${Components.renderTable(
                        ['Control', 'Status', 'Article'],
                        diff.unchanged.map(c => [
                            `<strong>${c.controlId}</strong>`,
                            Components.renderStatusBadge(c.newStatus),
                            c.articleLabel || '',
                        ])
                    )}
                </div>
            </div>`;
        }

        return html;
    },

    _renderRemediationBody() {
        // Use remediation from the latest report
        const remediations = this._report2.remediations || this._report1.remediations || [];
        if (remediations.length === 0) {
            // Fallback to control recommendations
            const articles = (this._report2 || this._report1 || {}).articles || [];
            const gaps = [];
            for (const art of articles) {
                for (const ctrl of (art.controls || [])) {
                    if ((ctrl.status === 'gap' || ctrl.status === 'partial') && ctrl.recommendation) {
                        gaps.push(ctrl);
                    }
                }
            }
            if (gaps.length === 0) {
                return '<div class="alert alert-success">All controls met. No remediation needed.</div>';
            }
            let html = `<div class="alert alert-info" style="margin-bottom:16px">
                Graph-aware remediation not available for these scans. Showing basic recommendations.
            </div>`;
            for (const ctrl of gaps.slice(0, 10)) {
                html += `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">
                    ${Components.renderStatusBadge(ctrl.status)}
                    <strong>${ctrl.controlId}</strong>: ${ctrl.recommendation}
                </div>`;
            }
            return html;
        }

        // Build rank map: priority order from backend (index = rank)
        const rankMap = new Map();
        remediations.forEach((r, i) => rankMap.set(r, i + 1));

        const latestReport = this._report2 || this._report1;
        const summary = latestReport.summary || {};
        const currentScore = summary.score || 0;
        const nonCodeItems = Components.buildNonCodeItems(latestReport);
        const scanId = this._scan2?.id || this._scan1?.id || '';
        let html = Components.renderRemediationSummary(remediations, currentScore, summary, nonCodeItems, scanId);
        html += Components.renderRemediationPhases(remediations, currentScore, rankMap, nonCodeItems, scanId);

        return html;
    },

    /** Select a filmstrip scan for comparison. Cycles through adjacent pairs. */
    async selectFilmstripItem(scanId) {
        if (!scanId) return;
        const id1 = this._scan1?.id;
        const id2 = this._scan2?.id;
        if (scanId === id1 || scanId === id2) return; // already selected

        const newScan = await ScanAdapter.getWithReport(scanId);
        if (!newScan || !newScan.report) return;

        // Build the new pair: clicked scan + its nearest neighbor in the filmstrip
        const idx = this._allScans.findIndex(s => s.id === scanId);
        const newTime = newScan.timestamp || newScan.report?.generatedAt || '';
        const time1 = this._scan1?.timestamp || '';
        const time2 = this._scan2?.timestamp || '';

        // Keep whichever current scan is closer in the filmstrip to the clicked one
        const dist1 = Math.abs(this._allScans.findIndex(s => s.id === id1) - idx);
        const dist2 = Math.abs(this._allScans.findIndex(s => s.id === id2) - idx);
        const keepId = dist1 <= dist2 ? id1 : id2;
        const keepScan = keepId === id1 ? this._scan1 : this._scan2;
        const keepReport = keepId === id1 ? this._report1 : this._report2;
        const keepTime = keepScan?.timestamp || '';

        // Older scan on left, newer on right
        if (newTime >= keepTime) {
            this._scan1 = keepScan;
            this._report1 = keepReport;
            this._scan2 = newScan;
            this._report2 = newScan.report;
        } else {
            this._scan1 = newScan;
            this._report1 = newScan.report;
            this._scan2 = keepScan;
            this._report2 = keepReport;
        }

        // Update URL without triggering re-render
        const newId1 = this._scan1.id;
        const newId2 = this._scan2.id;
        history.replaceState(null, '', `#/diff/${newId1}/${newId2}`);

        this._renderPanel(newId1, newId2);
        // Re-highlight sidebar (replaceState doesn't fire hashchange)
        App.highlightCurrentRoute();
    },

    _renderFilmstrip(activeId1, activeId2) {
        if (this._allScans.length < 2) return '';

        let html = '<div class="compare-filmstrip">';
        for (let i = 0; i < this._allScans.length; i++) {
            const s = this._allScans[i];
            const score = s.score || 0;
            const color = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
            const depth = (s.scan_depth || s.depth || '').includes('semantic') ? 'sem' : 'str';
            const date = (s.timestamp || s.created_at || '').substring(5, 10);
            const isActive = s.id === activeId1 || s.id === activeId2;

            if (i > 0) {
                html += '<span class="filmstrip-arrow">&#8594;</span>';
            }

            html += `
            <div class="filmstrip-item${isActive ? ' active' : ''}"
               onclick="CompareView.selectFilmstripItem('${s.id}')"
               style="cursor:pointer">
                <span class="filmstrip-score" style="color:${color}">${score.toFixed(0)}%</span>
                <span class="filmstrip-depth">${depth}</span>
                <span class="filmstrip-date">${date}</span>
            </div>`;
        }
        html += '</div>';
        return html;
    },
};
