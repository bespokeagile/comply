/* Scan view — start a new compliance scan */
const ScanView = {
    _pollTimer: null,
    _scanId: null,

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

        app.innerHTML = `
        <div class="page-header">
            <h2>New Compliance Scan</h2>
            <p>Analyse a codebase against regulatory frameworks</p>
        </div>
        <div class="card" id="scan-form-card">
            <div class="form-group">
                <label for="scan-url">Repository URL or path</label>
                <input class="form-input" id="scan-url" list="scan-repo-list" placeholder="https://github.com/org/repo or /path/to/code" autofocus aria-describedby="scan-url-hint">
                <datalist id="scan-repo-list"></datalist>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="scan-framework">Framework</label>
                    <select class="form-select" id="scan-framework">
                        ${fwOptions || '<option value="eu-ai-act">EU AI Act</option>'}
                    </select>
                </div>
                <div class="form-group">
                    <label for="scan-depth">Scan Depth</label>
                    <select class="form-select" id="scan-depth">
                        <option value="structure">Quick (Structure)</option>
                        <option value="content" selected>Standard (Content)</option>
                        <option value="semantic">Deep (AI-Assisted)</option>
                    </select>
                </div>
            </div>
            <div class="form-group" id="llm-row" style="display:none">
                <label for="scan-llm-key">LLM API Key (for deep analysis)</label>
                <input class="form-input" type="password" id="scan-llm-key" placeholder="sk-...">
            </div>
            <div class="btn-group">
                <button class="btn btn-primary" id="scan-btn" onclick="ScanView.startScan()">Start Scan</button>
            </div>
        </div>
        <div id="scan-progress" style="display:none">
            <div class="card">
                <div class="card-header">Scan Progress</div>
                <div id="progress-stepper"></div>
                <div id="progress-detail" class="loading"><span class="spinner"></span> Starting...</div>
            </div>
        </div>
        <div id="scan-result-card" style="display:none"></div>`;

        document.getElementById('scan-depth').addEventListener('change', (e) => {
            document.getElementById('llm-row').style.display = e.target.value === 'semantic' ? 'block' : 'none';
        });

        // Pre-fill from URL params (e.g. ?repo=X&framework=Y&depth=Z)
        this._applyUrlParams();
        _loadRepoOptions('scan-repo-list');
    },

    /** Parse URL params and pre-fill the scan form. */
    _applyUrlParams() {
        const hashParts = window.location.hash.split('?');
        if (hashParts.length < 2) return;
        const params = new URLSearchParams(hashParts[1]);

        const repo = params.get('repo');
        const fw = params.get('framework');
        const depth = params.get('depth');

        if (repo) {
            const input = document.getElementById('scan-url');
            if (input) input.value = decodeURIComponent(repo);
        }
        if (fw) {
            const sel = document.getElementById('scan-framework');
            if (sel) sel.value = fw;
        }
        if (depth) {
            const sel = document.getElementById('scan-depth');
            if (sel) {
                sel.value = depth;
                // Show LLM key row if semantic
                if (depth === 'semantic') {
                    document.getElementById('llm-row').style.display = 'block';
                }
            }
        }
    },

    async startScan() {
        const url = document.getElementById('scan-url').value.trim();
        if (!url) return;

        const framework = document.getElementById('scan-framework').value;
        const depth = document.getElementById('scan-depth').value;
        const llmKey = document.getElementById('scan-llm-key')?.value || '';

        // Store scan params for post-scan card
        this._scanParams = { url, framework, depth };

        document.getElementById('scan-btn').disabled = true;
        document.getElementById('scan-progress').style.display = 'block';
        document.getElementById('scan-result-card').style.display = 'none';

        // Auto-detect baseline for incremental scanning
        let baselineId = null;
        try {
            const bl = await complyApi._fetch(`/baseline?repo=${encodeURIComponent(url)}&framework=${encodeURIComponent(framework)}`);
            if (bl && bl.id) baselineId = bl.id;
        } catch (_) { /* no baseline, full scan */ }

        try {
            const result = await complyApi.startScan(url, framework, depth, llmKey, null, false, baselineId);
            this._scanId = result.scanId;
            this._startPolling();
        } catch (e) {
            document.getElementById('progress-detail').innerHTML =
                `<div class="alert alert-error">Error: ${e.message}</div>`;
            document.getElementById('scan-btn').disabled = false;
        }
    },

    _startPolling() {
        const stepMap = {
            pending: 'Clone', cloning: 'Clone', scanning: 'Scan',
            building: 'Build', evaluating: 'Evaluate', complete: 'Done',
        };
        const startTime = Date.now();
        let slowWarningShown = false;

        this._pollTimer = setInterval(async () => {
            try {
                const status = await complyApi.getScanStatus(this._scanId);
                const step = stepMap[status.status] || status.status;
                document.getElementById('progress-stepper').innerHTML =
                    Components.renderProgressStepper(null, step);

                const elapsed = Math.round((Date.now() - startTime) / 1000);
                let detailHtml = `<span class="spinner"></span> ${status.progress_step || status.status}: ${status.progress_detail || ''}`;
                // Slow scan warning after 60s
                if (elapsed > 60 && !slowWarningShown) {
                    slowWarningShown = true;
                    detailHtml += `<div class="scan-slow-warning">Taking longer than expected (${elapsed}s). Large repos can take a few minutes.</div>`;
                }
                document.getElementById('progress-detail').innerHTML = detailHtml;

                if (status.status === 'complete') {
                    clearInterval(this._pollTimer);
                    App.setLastResult(this._scanId);
                    App.refreshScanSidebar();
                    this._showPostScanCard();
                } else if (status.status === 'error') {
                    clearInterval(this._pollTimer);
                    const reason = status.error || 'Scan failed';
                    document.getElementById('progress-detail').innerHTML = this._renderScanError(reason);
                    document.getElementById('scan-btn').disabled = false;
                }
            } catch (e) {
                clearInterval(this._pollTimer);
                document.getElementById('progress-detail').innerHTML = this._renderScanError(e.message);
            }
        }, 2000);
    },

    /** Render a scan failure with recovery options. */
    _renderScanError(reason) {
        const scanBtn = document.getElementById('scan-btn');
        if (scanBtn) scanBtn.disabled = false;
        return `
        <div class="scan-error-card">
            <div class="alert alert-error">${reason}</div>
            <div class="scan-error-actions">
                <button class="btn btn-primary btn-sm" onclick="document.getElementById('scan-btn').click()">Retry</button>
                <button class="btn btn-secondary btn-sm" onclick="document.getElementById('scan-depth').value='structure'; document.getElementById('scan-btn').click()">Try Structure Scan</button>
            </div>
            <p class="scan-error-hint">Structure scans are faster and don't require an API key. If the error persists, check that the repository URL is accessible.</p>
        </div>`;
    },

    /** Set a scan as the baseline for future incremental scans. */
    async _setBaseline(scanId, btnEl) {
        try {
            await complyApi.setBaseline(scanId);
            if (btnEl) { btnEl.textContent = 'Baseline Set'; btnEl.disabled = true; }
        } catch (e) {
            if (btnEl) btnEl.textContent = 'Failed';
        }
    },

    /** Show a post-scan result card with score and next-step actions. */
    async _showPostScanCard() {
        const container = document.getElementById('scan-result-card');
        if (!container) return;

        // Hide progress, show result
        document.getElementById('scan-progress').style.display = 'none';

        let report;
        try {
            report = await complyApi.getScanReport(this._scanId);
        } catch (e) {
            // Fall back to navigating to detail
            Router.navigate(`/detail/${this._scanId}`);
            return;
        }

        const summary = report.summary || {};
        const score = Math.round(summary.compliance_score || report.score || 0);
        const scoreColor = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';

        const met = summary.met || 0;
        const partial = summary.partial || 0;
        const gaps = summary.gap || summary.gaps || 0;

        const repoPath = report.target || this._scanParams?.url || '';
        const repoName = repoPath.replace(/.*\//, '').replace(/\.git$/, '') || repoPath;
        const fw = report.framework || this._scanParams?.framework || '';
        const fwDisplay = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
        const depth = report.scanDepth || this._scanParams?.depth || '';
        const depthLabel = depth === 'structure' ? 'Quick Scan' : depth === 'semantic' ? 'Deep Scan' : 'Standard Scan';
        const isStructure = depth === 'structure' || depth === 'content';

        // Encode params for CTA links
        const repoEnc = encodeURIComponent(repoPath);
        const fwEnc = encodeURIComponent(fw);

        container.innerHTML = `
        <div class="post-scan-card">
            <div class="post-scan-header">
                <div class="post-scan-score" style="color:${scoreColor}">${score}%</div>
                <div class="post-scan-info">
                    <div class="post-scan-repo">${repoName}</div>
                    <div class="post-scan-meta">${fwDisplay} &middot; ${depthLabel}</div>
                </div>
            </div>
            <div class="post-scan-stats">
                <span class="status-badge status-met">${met} met</span>
                <span class="status-badge status-partial">${partial} partial</span>
                <span class="status-badge status-gap">${gaps} gaps</span>
            </div>
            ${report.incremental ? `<div class="card" style="margin-bottom:12px;padding:10px 14px;font-size:12px;color:var(--text-secondary)">Incremental: ${report.incremental.controls_reevaluated} re-evaluated, ${report.incremental.controls_carried_forward} carried forward</div>` : ''}
            <div class="post-scan-actions">
                <a href="#/detail/${this._scanId}" class="btn btn-primary">View Report</a>
                <button class="btn btn-secondary" onclick="ReportGenerator.fromScan('${this._scanId}')">Download PDF</button>
                <button class="btn btn-secondary" onclick="ScanView._setBaseline('${this._scanId}', this)">Set as Baseline</button>
                <a href="#/scan?repo=${repoEnc}" class="btn btn-secondary">Scan Another Framework</a>
                ${isStructure ? `<a href="#/scan?repo=${repoEnc}&framework=${fwEnc}&depth=semantic" class="btn btn-secondary">Scan Deeper</a>` : ''}
                ${!(App.capabilities && App.capabilities.demo_mode) ? `<button class="btn btn-secondary" onclick="ScanView._addToProgram('${repoPath.replace(/'/g, "\\'")}', '${fw}')">Add to Program</button>` : ''}
            </div>
            <div id="program-picker" style="display:none"></div>
        </div>`;

        container.style.display = '';
    },

    /** Show program picker or navigate to create. */
    async _addToProgram(repoUrl, fw) {
        let programs = [];
        try { programs = await complyApi.listPrograms() || []; } catch (e) { /* ignore */ }

        if (programs.length === 0) {
            // No programs: navigate to create with pre-fill params
            window.location.hash = '#/program?newRepo=' + encodeURIComponent(repoUrl) + '&newFw=' + encodeURIComponent(fw);
            return;
        }

        // Show inline picker
        const picker = document.getElementById('program-picker');
        if (!picker) return;

        let html = '<div class="card" style="margin-top:12px;padding:12px">' +
            '<strong style="font-size:13px">Add to Program</strong>';
        for (const prog of programs) {
            html += '<div class="program-picker-row" onclick="ScanView._addRepoToProgram(\'' + prog.id + '\', \'' +
                repoUrl.replace(/'/g, "\\'") + '\', \'' + fw + '\')">' +
                '<span>' + (prog.name || 'Untitled') + '</span>' +
                '<span class="sidebar-program-meta">' + (prog.repos || []).length + ' repos</span></div>';
        }
        html += '<div class="program-picker-row" onclick="window.location.hash=\'#/program?newRepo=' +
            encodeURIComponent(repoUrl) + '&newFw=' + encodeURIComponent(fw) + '\'">' +
            '<span style="color:var(--accent)">+ Create New Program</span></div></div>';
        picker.innerHTML = html;
        picker.style.display = '';
    },

    /** Add repo+fw to an existing program and navigate to it. */
    async _addRepoToProgram(progId, repoUrl, fw) {
        try {
            const prog = await complyApi.getProgram(progId);
            const repos = prog.repos || [];
            const frameworks = prog.frameworks || [];
            // Add repo if not present
            const repoUrls = repos.map(r => typeof r === 'string' ? r : (r.url || r));
            if (!repoUrls.includes(repoUrl)) repos.push(repoUrl);
            // Add framework if not present
            const normFw = typeof fwNorm === 'function' ? fwNorm(fw) : fw;
            if (!frameworks.includes(normFw)) frameworks.push(normFw);
            await complyApi.updateProgram(progId, { name: prog.name, description: prog.description, repos, frameworks });
            window.location.hash = '#/program/' + progId;
        } catch (e) {
            alert('Failed to add to program: ' + e.message);
        }
    },
};
