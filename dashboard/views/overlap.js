/* Overlap View — multi-framework capability matrix for a repo.
   Shows which capabilities are shared across frameworks and where
   fixing one gap addresses multiple frameworks at once. */
const OverlapView = {
    _repoSlug: null,
    _matrix: null,
    _reports: null,

    async render(params) {
        const app = document.getElementById('app');
        const slug = params && params[0];

        if (!slug) {
            app.innerHTML = '<div class="alert alert-error">Repository slug required.</div>';
            return;
        }

        this._repoSlug = slug;

        // Gather all scans for this repo across all frameworks
        const allScans = ScanAdapter.list();
        const repoScans = allScans.filter(s => {
            const scanSlug = s.repoSlug || (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').replace(/.*\//, '');
            return scanSlug === slug;
        });

        if (repoScans.length === 0) {
            app.innerHTML = '<div class="alert">No scans found for this repository.</div>';
            return;
        }

        // Get the best scan per framework (prefer semantic over structure, latest over older)
        const bestByFw = {};
        for (const s of repoScans) {
            const fw = s.framework || '';
            if (!fw) continue;
            const isSemantic = (s.scan_depth || s.depth || '').includes('semantic');
            const existing = bestByFw[fw];
            if (!existing) {
                bestByFw[fw] = s;
            } else {
                const existIsSemantic = (existing.scan_depth || existing.depth || '').includes('semantic');
                if (isSemantic && !existIsSemantic) {
                    bestByFw[fw] = s;
                } else if (isSemantic === existIsSemantic) {
                    const existTs = existing.timestamp || existing.created_at || '';
                    const newTs = s.timestamp || s.created_at || '';
                    if (newTs > existTs) bestByFw[fw] = s;
                }
            }
        }

        const scanEntries = Object.values(bestByFw);
        if (scanEntries.length < 2) {
            app.innerHTML = `
                <div class="page-header"><h2>Framework Overlap: ${slug}</h2></div>
                <div class="alert">Need scans in at least 2 frameworks to show overlap. Currently have ${scanEntries.length} framework.</div>
                <p style="margin-top:12px"><a href="#/landing" class="btn">Scan Another Framework</a></p>`;
            return;
        }

        // Load full reports for each scan
        const reports = [];
        for (const s of scanEntries) {
            const full = await ScanAdapter.getWithReport(s.id);
            if (full && full.report) {
                reports.push(full.report);
            }
        }

        if (reports.length < 2) {
            app.innerHTML = '<div class="alert">Could not load reports for overlap analysis.</div>';
            return;
        }

        this._reports = reports;
        this._matrix = Components.buildOverlapMatrix(reports);
        const repoName = repoScans[0].repoName || slug;

        const { capabilities, frameworks, priorities, fwScores, efficiency } = this._matrix;
        const sharedCount = capabilities.filter(c => c.frameworkCount > 1).length;
        const totalCaps = capabilities.length;

        let html = `
        <div class="page-header">
            <h2>Framework Overlap: ${repoName}</h2>
            <span class="overlap-subtitle">${frameworks.length} frameworks, ${totalCaps} capabilities, ${sharedCount} shared</span>
            <button class="overlap-report-btn" onclick="ReportGenerator.fromOverlap('${slug}')" title="Generate cross-framework compliance report">Report</button>
        </div>

        ${Components.renderEfficiencyInsights(this._matrix)}

        <div class="overlap-summary-cards">
            ${frameworks.map(fw => {
                const s = fwScores[fw] || {};
                const score = s.score || 0;
                const color = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
                const depthLabel = (s.depth || '').includes('semantic') ? 'semantic' : 'structure';
                return `<div class="overlap-fw-card">
                    <div class="overlap-fw-card-name">${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</div>
                    <div class="overlap-fw-card-score" style="color:${color}">${score.toFixed(1)}%</div>
                    <div class="overlap-fw-card-counts">${s.met || 0} met, ${s.partial || 0} partial, ${s.gap || 0} gap</div>
                    <div class="overlap-fw-card-depth">${depthLabel} scan</div>
                </div>`;
            }).join('')}
        </div>

        <div class="overlap-section">
            <h3>Recommended Scan Order</h3>
            <p class="overlap-section-desc">Maximize coverage efficiency. Each step shows incremental capability coverage.</p>
            ${Components.renderScanOrder(this._matrix)}
        </div>

        <div class="overlap-section">
            <h3>Unified Remediation</h3>
            <p class="overlap-section-desc">All remediation actions across frameworks in one view. Items addressing multiple frameworks are highlighted.</p>
            ${Components.renderUnifiedRemediation(reports, this._matrix)}
        </div>

        <div class="overlap-section">
            <h3>Gap Analysis</h3>
            <p class="overlap-section-desc">Capabilities with gaps or partial compliance, sorted by cross-framework impact.</p>
            ${Components.renderOverlapPriorities(priorities)}
        </div>

        <div class="overlap-section">
            <h3>Capability Matrix</h3>
            <p class="overlap-section-desc">Each row is a compliance capability. Shared capabilities (2+ frameworks) are highlighted.</p>
            ${Components.renderOverlapMatrix(this._matrix)}
        </div>`;

        app.innerHTML = html;
    },
};
