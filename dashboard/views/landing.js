/* Landing page view for demo mode — scan form only.
   Data flows through ScanAdapter (stores.js): DemoCatalog for static demo data,
   UserScans for visitor-generated scans. Browse is handled by the sidebar. */
const LandingView = {
    _costScanResult: null,
    _scanning: false,
    _byokScanning: false,
    _fundedScanning: false,
    _fundedCredits: null, // { remaining, total_credits, used_credits, email }
    _pendingImport: null, // { format, data, raw }

    async render() {
        // Capture invite token from URL before rendering
        this._captureInviteToken();
        // Check funded credits if we have a token
        await this._checkFundedCredits();

        const app = document.getElementById('app');

        app.innerHTML = `
        <div class="landing-container">
            <div class="landing-brand-bar">
                <span class="landing-logo">BespokeAgile</span>
                <span class="landing-product">Comply</span>
            </div>

            <p style="text-align:center;font-size:14px;color:var(--text-secondary);margin:8px 0 16px;max-width:480px;margin-left:auto;margin-right:auto">
                Scan any public GitHub repo against AI compliance frameworks. Free structure scan, or bring your own API key for deep semantic analysis.
            </p>

            <div class="landing-tab-panel" id="landing-tab-content">
                ${this._renderScanPanel()}
            </div>

            <div class="landing-privacy landing-privacy-compact">
                <div class="privacy-badge">
                    <span class="privacy-icon">&#128274;</span>
                    <div>
                        <strong>Your API key never touches our database</strong>
                        <p>Your key is forwarded directly to your LLM provider (Anthropic, OpenAI, etc.) for this scan only.
                        It is held in server memory for the duration of the request and never written to disk, logs, or any persistent store.
                        Scan results are encrypted and stored in your browser, not on our servers.</p>
                    </div>
                </div>
            </div>

            <div class="landing-footer landing-footer-compact">
                <p>Powered by <a href="https://bespokeagile.com" target="_blank">BespokeAgile</a> Comply</p>
            </div>
        </div>`;

        this._bindScanEvents();
        this._checkRepoParam();
    },

    _renderScanPanel() {
        return `
        <div class="card">
            <div class="form-row">
                <div class="form-group" style="flex:3">
                    <label for="scan-url">Repository URL</label>
                    <input type="url" id="scan-url" class="form-input"
                           placeholder="https://github.com/owner/repo"
                           maxlength="500">
                </div>
                <div class="form-group" style="flex:1">
                    <label for="scan-framework">Framework</label>
                    <select id="scan-framework" class="form-select">
                        <option value="eu_ai_act">EU AI Act</option>
                        <option value="soc2_ai">SOC 2 AI</option>
                        <option value="nist_ai_rmf">NIST AI RMF</option>
                        <option value="iso_42001">ISO 42001</option>
                        <option value="owasp_llm_top10">OWASP LLM Top 10</option>
                        <option value="owasp_agentic_top10">OWASP Agentic Top 10</option>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group" style="flex:1">
                    <label for="scan-key">
                        API Key <span style="color:var(--text-muted);font-weight:400">(optional - for full semantic scan)</span>
                        <span style="float:right;font-size:11px;color:var(--text-muted);font-weight:400">&#128274; sent directly to your provider, never stored</span>
                    </label>
                    <div style="position:relative">
                        <input type="password" id="scan-key" class="form-input"
                               placeholder="sk-ant-... (Anthropic) or sk-... (OpenAI)"
                               oninput="LandingView._onKeyInput()">
                        <span id="scan-provider-badge" class="provider-badge" style="display:none"></span>
                    </div>
                </div>
            </div>
            <div class="scan-actions">
                <button id="free-scan-btn" class="btn" ${this._scanning ? 'disabled' : ''}>
                    ${this._scanning ? '<span class="spinner"></span> Scanning...' : 'Run Free Scan'}
                </button>
                ${this._renderFundedButton()}
                <button id="full-scan-btn" class="btn btn-primary" disabled ${this._byokScanning ? 'disabled' : ''}>
                    ${this._byokScanning ? '<span class="spinner"></span> Scanning...' : 'Run Full Scan'}
                </button>
                <span id="scan-hint" class="cost-scan-note">${this._fundedCredits && this._fundedCredits.remaining > 0
                    ? `${this._fundedCredits.remaining} free AI scan${this._fundedCredits.remaining !== 1 ? 's' : ''} remaining`
                    : 'No API key? Free structure scan takes 30-60 seconds.'}</span>
            </div>
        </div>
        <div class="import-divider">or import existing results</div>
        <div class="card" style="padding:20px">
            <div class="drop-zone" id="import-drop-zone">
                <input type="file" id="import-file-input" accept=".sarif,.json,.xml" style="display:none">
                <div class="drop-zone-icon">&#8681;</div>
                <div class="drop-zone-text" id="import-drop-text">Drop a <strong>security scan</strong> file here, or click to browse</div>
                <div class="drop-zone-sub">
                    <strong>SARIF</strong> — Semgrep, Nuclei, Snyk, CodeQL, Trivy, Bandit &nbsp;&middot;&nbsp;
                    <strong>SBOM</strong> — CycloneDX, SPDX &nbsp;&middot;&nbsp;
                    <strong>JUnit</strong> XML
                </div>
                <div class="drop-zone-file" id="import-file-info">
                    <span class="file-badge" id="import-file-type"></span>
                    <span class="file-name" id="import-file-name"></span>
                    <span class="file-size" id="import-file-size"></span>
                    <span class="file-clear" id="import-file-clear" title="Remove">&times;</span>
                </div>
            </div>
            <div class="import-controls" id="import-controls" style="display:none">
                <div class="form-group">
                    <label>Map to Framework</label>
                    <select id="import-framework" class="form-select">
                        <option value="owasp_agentic_top10">OWASP Agentic Top 10</option>
                        <option value="owasp_llm_top10">OWASP LLM Top 10</option>
                        <option value="eu_ai_act">EU AI Act</option>
                        <option value="soc2_ai">SOC 2 AI</option>
                        <option value="nist_ai_rmf">NIST AI RMF</option>
                        <option value="iso_42001">ISO 42001</option>
                    </select>
                </div>
                <button class="btn btn-primary" id="import-btn">Map to Compliance</button>
            </div>
        </div>
        <div id="import-results"></div>
        <div id="rescan-notice" style="display:none"></div>
        <div id="repo-cards"></div>
        <div id="scan-results"></div>`;
    },

    _bindScanEvents() {
        const freeBtn = document.getElementById('free-scan-btn');
        if (freeBtn) freeBtn.addEventListener('click', () => this._runCostScan());
        const fundedBtn = document.getElementById('funded-scan-btn');
        if (fundedBtn) fundedBtn.addEventListener('click', () => this._runFundedScan());
        const fullBtn = document.getElementById('full-scan-btn');
        if (fullBtn) fullBtn.addEventListener('click', () => this._runByokScan());
        this._onKeyInput();
        this._initDropZone();

        // Rescan recognition: check URL on blur/change
        const urlInput = document.getElementById('scan-url');
        if (urlInput && ScanAdapter) {
            const checkRescan = () => {
                const url = urlInput.value.trim();
                const fw = document.getElementById('scan-framework')?.value || '';
                const notice = document.getElementById('rescan-notice');
                if (!notice || !url) { if (notice) notice.style.display = 'none'; return; }

                const prev = ScanAdapter.findByUrl(url, fw);
                if (prev.length > 0) {
                    const latest = prev[0];
                    const score = latest.score || 0;
                    // Store baseline ID for incremental scanning
                    LandingView._baselineId = latest.id;
                    notice.style.display = '';
                    // Clear stale validation errors
                    const results = document.getElementById('scan-results');
                    if (results) results.innerHTML = '';
                    notice.innerHTML = `
                    <div class="rescan-notice">
                        <div>
                            <strong>We found ${prev.length} previous scan${prev.length > 1 ? 's' : ''}</strong>
                            for this repo (latest: ${score.toFixed(1)}%).
                            Rescanning will re-evaluate only controls affected by code changes.
                        </div>
                        <div style="display:flex;gap:8px;margin-top:6px">
                            <a href="#/detail/${latest.id}" class="btn btn-sm" style="text-decoration:none">View Previous</a>
                            ${prev.length >= 2
                                ? `<a href="#/diff/${prev[1].id}/${prev[0].id}" class="btn btn-sm" style="text-decoration:none">Compare Latest</a>`
                                : ''}
                        </div>
                    </div>`;
                } else {
                    LandingView._baselineId = null;
                    notice.style.display = 'none';
                }
            };
            urlInput.addEventListener('blur', checkRescan);
            const fwSelect = document.getElementById('scan-framework');
            if (fwSelect) fwSelect.addEventListener('change', checkRescan);
        }
    },

    _renderCompactReport(report) {
        return Components.renderCompactReport(report);
    },

    /** Detect LLM provider from API key prefix. */
    _detectProvider(key) {
        if (!key) return null;
        if (key.startsWith('sk-ant-')) return 'anthropic';
        if (key.startsWith('sk-')) return 'openai';
        if (key.startsWith('AIza')) return 'gemini';
        if (key.startsWith('xai-')) return 'grok';
        return null;
    },

    /** Update UI when API key field changes. */
    _onKeyInput() {
        const key = document.getElementById('scan-key')?.value?.trim() || '';
        const fullBtn = document.getElementById('full-scan-btn');
        const freeBtn = document.getElementById('free-scan-btn');
        const badge = document.getElementById('scan-provider-badge');
        const hint = document.getElementById('scan-hint');

        const provider = this._detectProvider(key);

        // Provider badge
        if (badge) {
            if (provider) {
                const labels = { anthropic: 'Anthropic', openai: 'OpenAI', gemini: 'Gemini', grok: 'Grok' };
                badge.textContent = labels[provider] || provider;
                badge.style.display = '';
            } else if (key.length > 3) {
                badge.textContent = 'Unknown provider';
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }
        }

        // Button states
        const hasKey = key.length >= 10;
        if (fullBtn) {
            fullBtn.disabled = !hasKey || this._byokScanning;
            fullBtn.classList.toggle('btn-primary', hasKey);
        }
        if (freeBtn) {
            // Demote free scan visually when key is present
            if (hasKey) {
                freeBtn.classList.remove('btn-primary');
            } else {
                freeBtn.classList.add('btn-primary');
            }
        }

        // Hint text
        if (hint) {
            hint.textContent = hasKey
                ? 'Your key is used for this scan only and never stored.'
                : 'No API key? Free structure scan takes 30-60 seconds.';
        }
    },

    async _runCostScan() {
        const url = document.getElementById('scan-url')?.value?.trim();
        const framework = document.getElementById('scan-framework')?.value;
        const btn = document.getElementById('free-scan-btn');
        const results = document.getElementById('scan-results');

        if (!url) {
            results.innerHTML = '<div class="alert alert-warn">Please enter a repository URL.</div>';
            return;
        }

        this._scanning = true;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Scanning...';
        results.innerHTML = '<div class="loading"><span class="spinner"></span> Cloning and scanning... This may take 30-60 seconds.</div>';
        // Clear any import results so only scan results show
        const importResults = document.getElementById('import-results');
        if (importResults) importResults.innerHTML = '';

        try {
            const scanBody = { url, framework };
            if (LandingView._baselineId) scanBody.baseline_id = LandingView._baselineId;
            const report = await complyApi._fetch('/demo/cost-scan', {
                method: 'POST',
                headers: this._scanHeaders(),
                body: JSON.stringify(scanBody),
            });
            this._costScanResult = report;
            const savedId = await ScanAdapter.save(report);
            if (savedId) App.setLastResult(savedId);

            // Build expand options for accordion card
            const expandOpts = { showUpgrade: true };
            if (ScanAdapter) {
                const prevScans = ScanAdapter.findByUrl(url, framework);
                if (prevScans.length >= 2) {
                    const prev = prevScans[1];
                    expandOpts.prevScore = prev.score || 0;
                    expandOpts.compareLink = `#/diff/${prev.id}/${savedId}`;
                }
            }
            this._lastScanExpand = { fw: framework, savedId, report, opts: expandOpts };
            results.innerHTML = '';

            // Refresh sidebar and framework cards (accordion shows the result)
            if (typeof App !== 'undefined' && App.refreshSidebar) App.refreshSidebar();
            this._refreshRepoCards();
        } catch (e) {
            if (e.status === 429) {
                results.innerHTML = this._renderRateLimitError(e);
            } else {
                const msg = e.message || 'Scan failed';
                results.innerHTML = `<div class="alert alert-error">${msg}</div>`;
            }
        } finally {
            this._scanning = false;
            btn.disabled = false;
            btn.innerHTML = 'Run Free Scan';
        }
    },

    async _runByokScan() {
        const url = document.getElementById('scan-url')?.value?.trim();
        const framework = document.getElementById('scan-framework')?.value;
        const key = document.getElementById('scan-key')?.value?.trim();
        const provider = this._detectProvider(key) || 'anthropic';
        const btn = document.getElementById('full-scan-btn');
        const freeBtn = document.getElementById('free-scan-btn');
        const results = document.getElementById('scan-results');

        if (!url) {
            results.innerHTML = '<div class="alert alert-warn">Please enter a repository URL.</div>';
            return;
        }
        if (!key) {
            results.innerHTML = '<div class="alert alert-warn">Please enter your API key for a full semantic scan.</div>';
            return;
        }

        this._byokScanning = true;
        btn.disabled = true;
        freeBtn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Scanning...';
        results.innerHTML = '<div class="loading"><span class="spinner"></span> Running full semantic scan... This may take 2-5 minutes.</div>';
        const importResults2 = document.getElementById('import-results');
        if (importResults2) importResults2.innerHTML = '';

        try {
            const started = await complyApi.startScan(url, framework, 'semantic', key, provider, false, LandingView._baselineId || null);
            const scanId = started.scanId;

            const report = await this._pollScan(scanId, results);
            if (report) {
                this._costScanResult = report;
                const savedId = await ScanAdapter.save(report);
                if (savedId) App.setLastResult(savedId);

                const expandOpts = {};
                const comparePair = savedId ? App._findComparePair(savedId) : null;
                if (comparePair) {
                    expandOpts.compareLink = `#/diff/${comparePair.structureId}/${comparePair.semanticId}`;
                }
                this._lastScanExpand = { fw: framework, savedId, report, opts: expandOpts };
                results.innerHTML = '';
                // Refresh sidebar and accordion cards
                if (typeof App !== 'undefined' && App.refreshSidebar) App.refreshSidebar();
                this._refreshRepoCards();
            }
        } catch (e) {
            if (e.status === 429) {
                results.innerHTML = this._renderRateLimitError(e);
            } else {
                const msg = e.message || 'Scan failed';
                results.innerHTML = `<div class="alert alert-error">${msg}</div>`;
            }
        } finally {
            this._byokScanning = false;
            btn.disabled = false;
            freeBtn.disabled = false;
            btn.innerHTML = 'Run Full Scan';
            this._onKeyInput(); // restore button states
        }
    },

    async _pollScan(scanId, statusEl) {
        const POLL_INTERVAL = 2000;
        const MAX_POLLS = 180; // 6 minutes max

        for (let i = 0; i < MAX_POLLS; i++) {
            await new Promise(r => setTimeout(r, POLL_INTERVAL));

            try {
                const status = await complyApi.getScanProgress(scanId);

                if (status.status === 'complete') {
                    const report = await complyApi.getScanReport(scanId);
                    return report;
                }

                if (status.status === 'error') {
                    statusEl.innerHTML = `<div class="alert alert-error">Scan failed: ${status.error || 'Unknown error'}</div>`;
                    return null;
                }

                // Update progress display
                const step = status.step || status.status || 'working';
                const detail = status.detail || '';
                statusEl.innerHTML = `
                    <div class="loading">
                        <span class="spinner"></span>
                        ${Components.renderProgressStepper(
                            ['Clone', 'Scan', 'Build', 'Evaluate', 'Done'],
                            step === 'cloning' ? 'Clone' :
                            step === 'scanning' ? 'Scan' :
                            step === 'building' ? 'Build' :
                            step === 'evaluating' ? 'Evaluate' : step
                        )}
                        <p style="margin-top:8px;color:var(--text-muted)">${step}: ${detail}</p>
                    </div>`;
            } catch (e) {
                // Transient error, keep polling
            }
        }

        statusEl.innerHTML = '<div class="alert alert-warn">Scan is taking longer than expected. Check the History tab.</div>';
        return null;
    },

    _renderReport(report, prefix) {
        const summary = report.summary || {};
        const score = summary.score || 0;
        const articles = report.articles || [];
        const scoreClass = score >= 70 ? 'high' : score >= 40 ? 'mid' : 'low';
        const framework = report.framework || 'unknown';
        const pfx = prefix || 'article';

        return `
        <div class="card" style="margin-top:16px">
            <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
                <span>${fwLabel(framework)} Compliance Report</span>
                <span style="font-size:12px;color:var(--text-muted)">
                    ${report.scanDepth || 'structure'} depth
                    ${report.commitSha ? ' | ' + report.commitSha.substring(0, 8) : ''}
                </span>
            </div>

            <div class="report-summary">
                ${Components.renderScoreGauge(score, 120)}
                <div class="report-stats">
                    <div class="stat">
                        <span class="stat-value" style="color:var(--green)">${summary.met || 0}</span>
                        <span class="stat-label">Met</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--yellow)">${summary.partial || 0}</span>
                        <span class="stat-label">Partial</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--red)">${summary.gap || 0}</span>
                        <span class="stat-label">Gap</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value">${summary.total || 0}</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
            </div>

            <div style="margin-top:16px">
                ${articles.map((art, i) => Components.renderArticleAccordion(art, i, pfx)).join('')}
            </div>
        </div>`;
    },

    _downloadReport(report, format) {
        const fw = report.framework || 'scan';
        const ts = new Date().toISOString().slice(0, 10);
        const name = `comply-${fw}-${ts}`;

        if (format === 'json') {
            const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${name}.json`;
            a.click();
            URL.revokeObjectURL(a.href);
        } else if (format === 'csv') {
            const articles = report.articles || [];
            const rows = [['Article', 'Control', 'Status', 'Evidence']];
            articles.forEach(art => {
                (art.controls || []).forEach(ctrl => {
                    rows.push([
                        art.title || '',
                        ctrl.id || ctrl.title || '',
                        ctrl.status || '',
                        (ctrl.evidence || []).map(e => e.description || '').join('; '),
                    ]);
                });
            });
            const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${name}.csv`;
            a.click();
            URL.revokeObjectURL(a.href);
        }
    },

    _renderDownloadBar(report, prominent) {
        const cls = prominent ? 'download-bar download-bar-prominent' : 'download-bar';
        return `
        <div class="${cls}">
            <span class="download-bar-text">${prominent
                ? 'Your scan is complete. Download your results:'
                : 'Save these results:'}</span>
            <div class="download-bar-actions">
                <button class="btn btn-sm download-json-btn" onclick="LandingView._downloadReport(LandingView._costScanResult, 'json')">JSON</button>
                <button class="btn btn-sm download-csv-btn" onclick="LandingView._downloadReport(LandingView._costScanResult, 'csv')">CSV</button>
            </div>
        </div>`;
    },

    /** Purposeful export moment at the end of scan flow. */
    _renderExportMoment(report, scanId) {
        if (!report) return '';
        const fw = report.framework || 'scan';
        const hasRemediation = report.remediations && report.remediations.length > 0;
        const remCount = hasRemediation ? report.remediations.length : 0;
        const quickWins = hasRemediation ? report.remediations.filter(r => r.effort === 'low').length : 0;

        // Check for delta/comparison data
        let deltaText = '';
        if (ScanAdapter) {
            const prev = ScanAdapter.findByUrl(report.target || '', fw);
            if (prev.length >= 2) {
                const prevScore = prev[1].score || 0;
                const newScore = (report.summary || {}).score || 0;
                const d = newScore - prevScore;
                if (d !== 0) {
                    deltaText = d > 0
                        ? `Score improved from ${prevScore.toFixed(1)}% to ${newScore.toFixed(1)}%.`
                        : `Score changed from ${prevScore.toFixed(1)}% to ${newScore.toFixed(1)}%.`;
                }
            }
        }

        return `
        <div class="export-moment">
            <div class="export-moment-header">
                <strong>Save Your Results</strong>
                ${deltaText ? `<span style="font-size:12px;color:var(--text-secondary)">${deltaText}</span>` : ''}
            </div>
            ${hasRemediation ? `<p style="font-size:13px;color:var(--text-secondary);margin-bottom:8px">
                Includes ${remCount} remediation action${remCount !== 1 ? 's' : ''}${quickWins > 0 ? ` (${quickWins} quick wins)` : ''}.
            </p>` : ''}
            <div class="export-moment-actions">
                <button class="btn btn-primary" onclick="LandingView._downloadReport(LandingView._costScanResult, 'json')">
                    Download JSON Report
                </button>
                <button class="btn" onclick="LandingView._downloadReport(LandingView._costScanResult, 'csv')">
                    Download CSV
                </button>
                ${scanId ? `<a href="#/detail/${scanId}" class="btn" style="text-decoration:none">View Full Details</a>` : ''}
            </div>
        </div>`;
    },

    _renderCostScanResult(report) {
        const estimate = report.cost_estimate || {};
        const summary = report.summary || {};
        const score = summary.score || 0;

        // Find gap/partial controls to show what semantic would improve
        const improvable = this._findImprovableControls(report);

        return `
        <div style="margin-top:16px">
            ${this._renderDownloadBar(report, false)}
            ${this._renderReport(report, 'cost')}

            <div class="card compare-preview" style="margin-top:16px">
                <div class="card-header">What AI Analysis Would Add</div>
                <p style="color:var(--text-secondary);font-size:13px;margin-bottom:16px">
                    Structure scans match keywords and file patterns. Semantic scans use AI to read code intent,
                    catching compliance evidence that pattern matching misses.
                </p>

                ${improvable.length > 0 ? `
                <div class="compare-controls">
                    ${improvable.map(c => `
                    <div class="compare-control-card">
                        <div class="compare-control-header">
                            <span>${Components.renderStatusBadge(c.status)}</span>
                            <strong>${c.controlId}</strong>
                        </div>
                        <div class="compare-control-req">${(c.requirement || '').substring(0, 150)}</div>
                        <div class="compare-columns">
                            <div class="compare-col compare-col-structure">
                                <div class="compare-col-label">Structure scan found</div>
                                ${c.evidence && c.evidence.length > 0
                                    ? c.evidence.slice(0, 2).map(e => `<div class="compare-evidence">${e}</div>`).join('')
                                    : '<div class="compare-evidence compare-evidence-none">No pattern matches</div>'}
                            </div>
                            <div class="compare-col compare-col-semantic">
                                <div class="compare-col-label">AI would analyze</div>
                                <div class="compare-evidence compare-evidence-ai">${this._semanticHint(c)}</div>
                            </div>
                        </div>
                    </div>
                    `).join('')}
                </div>

                <div class="compare-summary">
                    <span style="color:var(--text-secondary);font-size:13px">
                        <strong>${improvable.length}</strong> controls could be re-evaluated with deeper analysis
                    </span>
                </div>
                ` : `
                <div style="color:var(--text-secondary);font-size:13px">
                    All controls passed structure checks. A semantic scan would add AI-generated evidence narratives
                    and verify that implementations match compliance intent, not just keywords.
                </div>
                `}

                <div class="compare-cta">
                    <div class="compare-cta-cost">
                        ${(estimate.model_options || []).slice(0, 1).map(opt => `
                            <span class="compare-cost-value">~$${opt.estimated_cost_usd.toFixed(2)}</span>
                            <span class="compare-cost-label">estimated with ${opt.model}</span>
                        `).join('')}
                    </div>
                    <button class="btn btn-primary" onclick="
                        document.getElementById('scan-key').focus();
                        document.getElementById('scan-key').scrollIntoView({behavior:'smooth', block:'center'});
                    ">Add API Key for Full Scan</button>
                </div>
            </div>
        </div>`;
    },

    /** Find gap/partial controls that semantic analysis could improve. */
    _findImprovableControls(report) {
        const articles = report.articles || [];
        const controls = [];
        for (const art of articles) {
            for (const c of (art.controls || [])) {
                if (c.status === 'gap' || c.status === 'partial') {
                    controls.push(c);
                }
            }
        }
        // Return top 4 most interesting (gaps first, then partial)
        controls.sort((a, b) => (a.status === 'gap' ? 0 : 1) - (b.status === 'gap' ? 0 : 1));
        return controls.slice(0, 4);
    },

    /** Check for ?repo= param in hash and pre-populate the form + render cards. */
    _checkRepoParam() {
        if (!ScanAdapter) return;
        const hash = window.location.hash || '';
        const qIdx = hash.indexOf('?');
        if (qIdx === -1) return;
        const params = new URLSearchParams(hash.slice(qIdx));
        const repoSlug = params.get('repo');
        if (!repoSlug) return;

        const repos = ScanAdapter.listRepos();
        const repo = repos.find(r => r.slug === repoSlug);
        if (!repo) return;

        // Pre-fill URL (only if it looks like a real URL, not a file import)
        const urlInput = document.getElementById('scan-url');
        const isRealUrl = repo.url && (repo.url.startsWith('http://') || repo.url.startsWith('https://'));
        if (urlInput && isRealUrl) urlInput.value = repo.url;

        // Pre-select most recent framework
        if (repo.frameworks.length > 0) {
            const fwSelect = document.getElementById('scan-framework');
            if (fwSelect) {
                const sorted = [...repo.frameworks].sort((a, b) => {
                    const tsA = a.latestScan ? (a.latestScan.timestamp || '') : '';
                    const tsB = b.latestScan ? (b.latestScan.timestamp || '') : '';
                    return tsB.localeCompare(tsA);
                });
                fwSelect.value = sorted[0].fw;
            }
        }

        // Render framework cards
        this._renderRepoCards(repo);

        // For imports (non-URL repos), scroll to show the cards
        if (!isRealUrl) {
            const cards = document.getElementById('repo-cards');
            if (cards) setTimeout(() => cards.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
        }

        // Trigger rescan detection (only for real URLs)
        if (urlInput && isRealUrl) urlInput.dispatchEvent(new Event('blur'));
    },

    /** Render framework result cards as an accordion. Most recent scan auto-expands. */
    _renderRepoCards(repo) {
        const container = document.getElementById('repo-cards');
        if (!container || !ScanAdapter) return;

        const ALL_FW = ['eu_ai_act', 'soc2_ai', 'nist_ai_rmf', 'iso_42001', 'owasp_llm_top10', 'owasp_agentic_top10'];
        const allScans = ScanAdapter.list();
        const expand = this._lastScanExpand || {};

        let html = '<div class="fw-result-cards">';

        for (const fwId of ALL_FW) {
            const label = typeof fwLabel === 'function' ? fwLabel(fwId) : fwId;
            const fwMeta = repo.frameworks.find(f => f.fw === fwId);

            if (fwMeta && fwMeta.latestScan) {
                const repoScans = allScans.filter(s =>
                    (s.repoSlug === repo.slug ||
                     (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').endsWith(repo.slug)) &&
                    s.framework === fwId
                );
                const struct = repoScans.find(s => (s.depth || '').includes('structure'));
                const sem = repoScans.find(s => (s.depth || '').includes('semantic'));
                const score = fwMeta.latestScan.score || 0;
                const scoreColor = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
                const ts = this._relativeTime(fwMeta.latestScan.timestamp);
                const isExpanded = expand.fw === fwId;
                const depth = fwMeta.latestScan.depth || 'structure';
                const depthLabel = depth.includes('semantic') ? 'semantic' : 'structure';

                // Detail link
                let detailHref, detailLabel;
                if (struct && sem) {
                    detailHref = `#/diff/${struct.id}/${sem.id}`;
                    detailLabel = 'Compare Scans';
                } else {
                    detailHref = `#/detail/${fwMeta.latestScan.id}`;
                    detailLabel = 'View Report';
                }

                // Get met/partial/gap from expand data if this is the just-scanned framework
                let met = 0, partial = 0, gap = 0;
                if (isExpanded && expand.report) {
                    const s = expand.report.summary || {};
                    met = s.met || 0;
                    partial = s.partial || 0;
                    gap = s.gap || 0;
                }

                // Upgrade hint for structure-only scans
                const showUpgrade = isExpanded && expand.opts && expand.opts.showUpgrade;

                // Compare link from expand opts
                const compareLink = isExpanded && expand.opts && expand.opts.compareLink;

                // Cost note from expand opts
                const costUsd = isExpanded && expand.opts && expand.opts.costUsd;

                // Delta from expand opts
                let deltaHtml = '';
                if (isExpanded && expand.opts && expand.opts.prevScore != null) {
                    const d = score - expand.opts.prevScore;
                    if (d !== 0) {
                        const dColor = d > 0 ? 'var(--green)' : 'var(--red)';
                        deltaHtml = `<span style="font-size:13px;font-weight:600;color:${dColor};margin-left:8px">${d > 0 ? '+' : ''}${d.toFixed(1)}%</span>`;
                    }
                }

                html += `
                <div class="fw-result-card ${isExpanded ? 'fw-expanded' : ''}" data-fw="${fwId}" onclick="LandingView._toggleFwCard('${fwId}')">
                    <div class="fw-result-card-top">
                        <span class="fw-result-card-name">${label}</span>
                        <span class="fw-result-card-right">
                            <span class="fw-result-card-dots">
                                <span class="repo-sidebar-dot ${struct ? 'structure' : 'missing'}" title="Structure"></span>
                                <span class="repo-sidebar-dot ${sem ? 'semantic' : 'missing'}" title="Semantic"></span>
                            </span>
                            <span class="fw-result-card-chevron">${isExpanded ? '&#9650;' : '&#9660;'}</span>
                        </span>
                    </div>
                    <div class="fw-result-card-summary">
                        <span class="fw-result-card-score" style="color:${scoreColor}">${score.toFixed(1)}%</span>
                        <span class="fw-result-card-time">${ts}</span>
                        <a href="${detailHref}" class="btn btn-sm" style="text-decoration:none" onclick="event.stopPropagation()">${detailLabel}</a>
                    </div>
                    <div class="fw-result-card-detail">
                        ${met || partial || gap ? `
                        <div class="fw-detail-stats">
                            <span class="receipt-stat met">${met} met</span>
                            <span class="receipt-stat-sep">&middot;</span>
                            <span class="receipt-stat partial">${partial} partial</span>
                            <span class="receipt-stat-sep">&middot;</span>
                            <span class="receipt-stat gap">${gap} gap</span>
                            ${deltaHtml}
                        </div>` : ''}
                        <div class="fw-detail-meta">${depthLabel} scan${costUsd ? ` · ~$${costUsd.toFixed(2)} cost` : ''}</div>
                        <div class="fw-detail-actions">
                            <a href="${detailHref}" class="btn btn-primary btn-sm" style="text-decoration:none" onclick="event.stopPropagation()">
                                ${detailLabel} &rarr;
                            </a>
                            ${compareLink ? `<a href="${compareLink}" class="btn btn-sm" style="text-decoration:none" onclick="event.stopPropagation()">Compare Scans</a>` : ''}
                        </div>
                        ${showUpgrade ? `
                        <div class="fw-detail-upgrade">
                            <span>Upgrade to semantic scan for deeper analysis</span>
                            <button class="btn btn-sm" onclick="event.stopPropagation(); document.getElementById('scan-key').focus(); document.getElementById('scan-key').scrollIntoView({behavior:'smooth',block:'center'})">Add API Key</button>
                        </div>` : ''}
                    </div>
                </div>`;
            } else {
                html += `
                <div class="fw-result-card fw-result-card-empty" onclick="LandingView._selectFramework('${fwId}')">
                    <div class="fw-result-card-top">
                        <span class="fw-result-card-name">${label}</span>
                    </div>
                    <div class="fw-result-card-summary">
                        <span style="color:var(--text-muted);font-size:13px">Not yet scanned</span>
                        <span class="fw-result-card-action-text">Select to scan</span>
                    </div>
                </div>`;
            }
        }

        html += '</div>';
        container.innerHTML = html;

        // Scroll expanded card into view
        if (expand.fw) {
            const el = container.querySelector(`[data-fw="${expand.fw}"]`);
            if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
        }
    },

    /** Toggle accordion expand/collapse on a framework card. */
    _toggleFwCard(fwId) {
        const cards = document.querySelectorAll('.fw-result-card[data-fw]');
        cards.forEach(card => {
            const chevron = card.querySelector('.fw-result-card-chevron');
            if (card.dataset.fw === fwId) {
                const wasExpanded = card.classList.contains('fw-expanded');
                card.classList.toggle('fw-expanded');
                if (chevron) chevron.innerHTML = wasExpanded ? '&#9660;' : '&#9650;';
            } else {
                card.classList.remove('fw-expanded');
                if (chevron) chevron.innerHTML = '&#9660;';
            }
        });
    },

    /** Refresh framework cards after a scan completes. */
    _refreshRepoCards() {
        if (!ScanAdapter) return;
        const url = document.getElementById('scan-url')?.value?.trim() || '';
        if (!url) return;
        const repos = ScanAdapter.listRepos();
        const urlLower = url.toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '');
        const slug = urlLower.replace(/.*\//, '');
        const repo = repos.find(r =>
            r.slug === slug ||
            (r.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').endsWith(slug)
        );
        if (repo) this._renderRepoCards(repo);
    },

    /** Select a framework in the dropdown and focus the URL input. */
    _selectFramework(fwId) {
        const select = document.getElementById('scan-framework');
        if (select) select.value = fwId;
        const urlInput = document.getElementById('scan-url');
        if (urlInput) {
            urlInput.focus();
            urlInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    },

    /** Format a timestamp as relative time (e.g. "2h ago"). */
    _relativeTime(timestamp) {
        if (!timestamp) return '';
        const diff = Date.now() - new Date(timestamp).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 7) return `${days}d ago`;
        return new Date(timestamp).toLocaleDateString();
    },

    // ── Funded scan methods ─────────────────────────────────────────────

    /** Capture ?invite= token from URL hash and store in localStorage. */
    _captureInviteToken() {
        const hash = window.location.hash || '';
        const qIdx = hash.indexOf('?');
        if (qIdx === -1) return;
        const params = new URLSearchParams(hash.slice(qIdx));
        const token = params.get('invite');
        if (token) {
            localStorage.setItem('comply_invite_token', token);
            // Clean the token from URL to avoid leaking in shared links
            const cleanHash = hash.slice(0, qIdx);
            history.replaceState(null, '', cleanHash || '#/landing');
        }
    },

    /** Get stored invite token. */
    _getInviteToken() {
        return localStorage.getItem('comply_invite_token') || '';
    },

    /** Build merged headers: visitor ID + invite token. */
    _scanHeaders() {
        const h = typeof VisitorId !== 'undefined' ? VisitorId.headers() : {};
        const token = this._getInviteToken();
        if (token) h['X-Invite-Token'] = token;
        return h;
    },

    /** Render a friendly rate-limit message instead of raw error. */
    _renderRateLimitError(err) {
        const retryMin = Math.ceil((err.retryAfter || 60) / 60);
        const hasInvite = !!this._getInviteToken();
        const inviteHint = hasInvite
            ? ''
            : `<p style="margin-top:8px;font-size:13px">Have an invite link? Paste it in your browser to unlock a higher scan limit.</p>`;
        return `<div class="alert alert-warn" style="line-height:1.6">
            <strong>Scan limit reached</strong>
            <p>${err.message || 'Too many scans. Try again shortly.'}</p>
            <p style="font-size:13px;color:var(--text-muted)">Try again in ~${retryMin} minute${retryMin !== 1 ? 's' : ''}.</p>
            ${inviteHint}
        </div>`;
    },

    /** Check funded credits from server. */
    async _checkFundedCredits() {
        const token = this._getInviteToken();
        if (!token) {
            this._fundedCredits = null;
            return;
        }
        try {
            const resp = await complyApi._fetch(`/demo/funded/check?token=${encodeURIComponent(token)}`);
            if (resp && resp.valid && resp.remaining > 0) {
                this._fundedCredits = resp;
            } else {
                this._fundedCredits = resp && resp.valid ? resp : null;
            }
        } catch (e) {
            this._fundedCredits = null;
        }
    },

    /** Render the funded scan button (only if credits available). */
    _renderFundedButton() {
        const credits = this._fundedCredits;
        if (!credits) return '';

        if (credits.remaining <= 0) {
            return `<button id="funded-scan-btn" class="btn btn-accent" disabled style="opacity:0.5;cursor:not-allowed">
                Free AI Scans Used
            </button>`;
        }

        if (this._fundedScanning) {
            return `<button id="funded-scan-btn" class="btn btn-accent" disabled>
                <span class="spinner"></span> AI Scanning...
            </button>`;
        }

        return `<button id="funded-scan-btn" class="btn btn-accent">
            Run Full Scan (Free)
        </button>`;
    },

    /** Run a funded semantic scan using the server's API key. */
    async _runFundedScan() {
        const url = document.getElementById('scan-url')?.value?.trim();
        const framework = document.getElementById('scan-framework')?.value;
        const btn = document.getElementById('funded-scan-btn');
        const freeBtn = document.getElementById('free-scan-btn');
        const fullBtn = document.getElementById('full-scan-btn');
        const results = document.getElementById('scan-results');
        const token = this._getInviteToken();

        if (!url) {
            results.innerHTML = '<div class="alert alert-warn">Please enter a repository URL.</div>';
            return;
        }
        if (!token) {
            results.innerHTML = '<div class="alert alert-error">No invite token found.</div>';
            return;
        }

        this._fundedScanning = true;
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> AI Scanning...'; }
        if (freeBtn) freeBtn.disabled = true;
        if (fullBtn) fullBtn.disabled = true;
        results.innerHTML = '<div class="loading"><span class="spinner"></span> Running full AI semantic scan... This may take 2-5 minutes.</div>';
        const importResults3 = document.getElementById('import-results');
        if (importResults3) importResults3.innerHTML = '';

        try {
            const started = await complyApi._fetch('/demo/funded-scan', {
                method: 'POST',
                headers: this._scanHeaders(),
                body: JSON.stringify({ url, framework, token, baseline_id: LandingView._baselineId || null }),
            });
            const scanId = started.scanId;

            const report = await this._pollScan(scanId, results);
            if (report) {
                this._costScanResult = report;
                const savedId = await ScanAdapter.save(report);
                if (savedId) App.setLastResult(savedId);

                const expandOpts = {};
                const costUsd = report._estimated_cost_usd || 0;
                if (costUsd > 0) expandOpts.costUsd = costUsd;

                const comparePair = savedId ? App._findComparePair(savedId) : null;
                if (comparePair) {
                    expandOpts.compareLink = `#/diff/${comparePair.structureId}/${comparePair.semanticId}`;
                }
                this._lastScanExpand = { fw: framework, savedId, report, opts: expandOpts };
                results.innerHTML = '';

                if (typeof App !== 'undefined' && App.refreshSidebar) App.refreshSidebar();
                this._refreshRepoCards();

                // Refresh credit count
                await this._checkFundedCredits();
                const hint = document.getElementById('scan-hint');
                if (hint && this._fundedCredits) {
                    hint.textContent = this._fundedCredits.remaining > 0
                        ? `${this._fundedCredits.remaining} free AI scan${this._fundedCredits.remaining !== 1 ? 's' : ''} remaining`
                        : 'Free scans used. Add your API key for more.';
                }
            }
        } catch (e) {
            if (e.status === 429) {
                results.innerHTML = this._renderRateLimitError(e);
            } else {
                const msg = e.message || 'Funded scan failed';
                results.innerHTML = `<div class="alert alert-error">${msg}</div>`;
            }
        } finally {
            this._fundedScanning = false;
            if (btn) { btn.disabled = false; btn.innerHTML = 'Run Full Scan (Free)'; }
            if (freeBtn) freeBtn.disabled = false;
            if (fullBtn) fullBtn.disabled = false;
            this._onKeyInput();
            // Update funded button state
            if (this._fundedCredits && this._fundedCredits.remaining <= 0) {
                const fb = document.getElementById('funded-scan-btn');
                if (fb) { fb.disabled = true; fb.style.opacity = '0.5'; fb.style.cursor = 'not-allowed'; fb.textContent = 'Free AI Scans Used'; }
            }
        }
    },

    // ── Drop zone (SARIF / SBOM / JUnit import) ──────────────────────────

    _FORMAT_DETECT: [
        { format: 'sarif', test: d => d?.runs && Array.isArray(d.runs), label: 'SARIF',
          stats: (d) => {
              const runs = d.runs || [];
              const tools = runs.map(r => r.tool?.driver?.name || 'unknown');
              const results = runs.reduce((n, r) => n + (r.results?.length || 0), 0);
              return `<strong>${tools.join(', ')}</strong> — ${results} finding${results !== 1 ? 's' : ''} detected`;
          }},
        { format: 'sbom', test: d => d?.bomFormat === 'CycloneDX' || d?.spdxVersion || (d?.components && !d?.runs), label: 'SBOM',
          stats: d => {
              const comps = d.components?.length || d.packages?.length || 0;
              const fmt = d.bomFormat === 'CycloneDX' ? 'CycloneDX' : d.spdxVersion ? 'SPDX' : 'SBOM';
              return `<strong>${fmt}</strong> — ${comps} component${comps !== 1 ? 's' : ''} detected`;
          }},
        { format: 'junit', test: (d, raw) => raw?.includes('<testsuite') || raw?.includes('<testsuites'), label: 'JUnit',
          stats: (d, raw) => {
              const m = raw?.match(/tests="(\d+)"/);
              const count = m ? m[1] : '?';
              return `<strong>JUnit XML</strong> — ${count} test${count !== '1' ? 's' : ''} detected`;
          }},
    ],

    _initDropZone() {
        const zone = document.getElementById('import-drop-zone');
        const fileInput = document.getElementById('import-file-input');
        if (!zone || !fileInput) return;

        zone.addEventListener('click', e => {
            if (e.target.closest('.file-clear')) return;
            fileInput.click();
        });
        fileInput.addEventListener('change', e => {
            if (e.target.files.length) this._handleDropFile(e.target.files[0]);
        });
        zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
        zone.addEventListener('drop', e => {
            e.preventDefault();
            zone.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file) this._handleDropFile(file);
        });

        const clearBtn = document.getElementById('import-file-clear');
        if (clearBtn) clearBtn.addEventListener('click', e => this._clearDropFile(e));

        const importBtn = document.getElementById('import-btn');
        if (importBtn) importBtn.addEventListener('click', () => this._importFile());
    },

    _handleDropFile(file) {
        const reader = new FileReader();
        reader.onload = () => {
            const raw = reader.result;
            let parsed = null;
            try { parsed = JSON.parse(raw); } catch (e) { /* may be XML */ }

            let detected = null;
            for (const fmt of this._FORMAT_DETECT) {
                if (fmt.test(parsed, raw)) { detected = fmt; break; }
            }

            if (!detected) {
                const results = document.getElementById('import-results');
                if (results) results.innerHTML = '<div class="alert alert-warn">Unrecognised file format. Supported: SARIF (.sarif/.json), SBOM (CycloneDX/SPDX), JUnit XML.</div>';
                return;
            }

            this._pendingImport = { format: detected.format, data: parsed, raw, fileName: file.name };

            // Update file info display
            const badge = document.getElementById('import-file-type');
            if (badge) { badge.textContent = detected.label; badge.className = 'file-badge ' + detected.format; }
            document.getElementById('import-file-name').textContent = file.name;
            document.getElementById('import-file-size').textContent = this._formatSize(file.size);
            document.getElementById('import-file-info').classList.add('visible');
            document.getElementById('import-drop-text').innerHTML = detected.stats(parsed, raw);

            // Show import controls — all formats now supported
            const controls = document.getElementById('import-controls');
            controls.style.display = 'flex';
            // Refresh dropdown to disable already-mapped frameworks for this file
            this._refreshImportFrameworks();
        };
        reader.readAsText(file);
    },

    _clearDropFile(e) {
        e.stopPropagation();
        this._pendingImport = null;
        document.getElementById('import-file-input').value = '';
        document.getElementById('import-file-info').classList.remove('visible');
        document.getElementById('import-controls').style.display = 'none';
        document.getElementById('import-drop-text').innerHTML =
            'Drop a <strong>security scan</strong> file here, or click to browse';
        document.getElementById('import-results').innerHTML = '';
    },

    _formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    },

    async _importFile() {
        if (!this._pendingImport) return;

        const fw = document.getElementById('import-framework').value;
        const btn = document.getElementById('import-btn');
        const results = document.getElementById('import-results');
        const fmt = this._pendingImport.format;
        const origLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Analyzing...';

        // Clear any previous scan results so only import results show
        const scanResults = document.getElementById('scan-results');
        if (scanResults) scanResults.innerHTML = '';
        const repoCards = document.getElementById('repo-cards');
        if (repoCards) repoCards.innerHTML = '';
        const rescanNotice = document.getElementById('rescan-notice');
        if (rescanNotice) rescanNotice.style.display = 'none';

        try {
            let data;
            if (fmt === 'sarif') {
                data = await complyApi.importSarif(this._pendingImport.data, fw);
            } else if (fmt === 'sbom') {
                data = await complyApi.importSbom(this._pendingImport.data, fw);
            } else if (fmt === 'junit') {
                data = await complyApi.importJunit(this._pendingImport.raw, fw);
            }

            // Save import as a scan so it appears in sidebar (with raw data for re-analysis)
            let savedId = null;
            if (data && data.report) {
                const fileName = this._pendingImport.fileName || fmt;
                const report = data.report;
                report.target = report.target || fileName;
                report.repoName = report.repoName || fileName;
                report.scanDepth = report.scanDepth || `${fmt}_import`;
                const importRaw = fmt === 'junit' ? this._pendingImport.raw : this._pendingImport.data;
                savedId = await ScanAdapter.save(report, {
                    source: 'user',
                    importRaw,
                    importFormat: fmt,
                    importFilename: fileName,
                });
                if (savedId) App.setLastResult(savedId);
                if (typeof App !== 'undefined' && App.refreshSidebar) App.refreshSidebar();
                // Append receipt card (stack multiple import analyses)
                results.insertAdjacentHTML('afterbegin', this._renderReceiptCard(report, savedId, {}));
            }
            // Update the framework dropdown to reflect what's been mapped
            this._refreshImportFrameworks();
        } catch (e) {
            results.innerHTML = `<div class="alert alert-error">${e.message || 'Import failed'}</div>`;
            btn.disabled = false;
            btn.textContent = origLabel;
        }
    },

    /** Update import framework dropdown: disable already-mapped frameworks, auto-select next. */
    _refreshImportFrameworks() {
        if (!this._pendingImport) return;
        const fileName = this._pendingImport.fileName || '';
        // Match slug derivation from UserScans.save(): target = fileName, slug = target (no '/' to strip)
        const slug = fileName.replace(/\.git$/, '');

        // Find which frameworks are already mapped for this file
        const select = document.getElementById('import-framework');
        const btn = document.getElementById('import-btn');
        if (!select || !btn) return;

        const mappedFws = new Set();
        if (ScanAdapter) {
            const allScans = ScanAdapter.list();
            for (const scan of allScans) {
                const sSlug = scan.repoSlug || (scan.url || '').replace(/.*\//, '');
                if (sSlug === slug && scan.framework) {
                    mappedFws.add(scan.framework);
                }
            }
        }

        let firstAvailable = null;
        for (const opt of select.options) {
            const isMapped = mappedFws.has(opt.value);
            opt.disabled = isMapped;
            // Strip any existing checkmark suffix before re-adding
            opt.textContent = opt.textContent.replace(/ \u2713$/, '');
            if (isMapped) opt.textContent += ' \u2713';
            if (!isMapped && !firstAvailable) firstAvailable = opt.value;
        }

        if (firstAvailable) {
            select.value = firstAvailable;
            btn.disabled = false;
            // Restore label based on format
            const fmt = this._pendingImport.format;
            if (fmt === 'sarif') btn.textContent = 'Map to Compliance';
            else if (fmt === 'sbom') btn.textContent = 'Analyze Supply Chain';
            else if (fmt === 'junit') btn.textContent = 'Analyze Test Evidence';
            else btn.textContent = 'Import';
        } else {
            btn.disabled = true;
            btn.textContent = 'All Frameworks Mapped';
        }
    },

    _renderImportReport(data, fw, container) {
        const report = data.report;
        const s = report.summary || {};
        const score = s.score || 0;
        const articles = report.articles || [];

        // Build the import summary + full report
        container.innerHTML = `
        <div class="card" style="margin-top:16px">
            <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
                <span>SARIF Import &rarr; ${fwLabel(fw)}</span>
                <span style="font-size:12px;color:var(--text-muted)">
                    ${data.tools?.join(', ') || 'security scanner'}
                </span>
            </div>
            <div class="import-stats">
                <div class="stat"><span class="val">${data.findings_count || 0}</span>findings</div>
                <div class="stat"><span class="val">${(data.cwes_found || []).length}</span>CWEs</div>
                <div class="stat"><span class="val">${(data.tools || []).length}</span>tool${(data.tools || []).length !== 1 ? 's' : ''}</div>
                <div class="stat"><span class="val">${report.totalFindings || data.findings_count || 0}</span>total</div>
            </div>
            <div class="report-summary" style="margin-top:12px">
                ${Components.renderScoreGauge(score, 100)}
                <div class="report-stats">
                    <div class="stat">
                        <span class="stat-value" style="color:var(--green)">${s.met || 0}</span>
                        <span class="stat-label">Met</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--yellow)">${s.partial || 0}</span>
                        <span class="stat-label">Partial</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--red)">${s.gap || 0}</span>
                        <span class="stat-label">Gap</span>
                    </div>
                </div>
            </div>
            ${data.architectural_enrichment ? `
            <div style="margin-top:12px;padding:12px;background:rgba(99,102,241,0.06);border-radius:6px;border-left:3px solid var(--accent)">
                <div style="font-size:13px;font-weight:600;margin-bottom:6px">
                    Architectural Analysis
                    <span style="font-size:11px;font-weight:400;color:var(--text-muted);margin-left:8px">
                        source: ${data.architectural_enrichment.source === 'merged_scan' ? 'prior scan' : 'auto structure scan'}
                    </span>
                </div>
                <div style="display:flex;gap:16px;font-size:12px;flex-wrap:wrap">
                    <span><strong style="color:var(--red)">${data.architectural_enrichment.severityDistribution?.high || 0}</strong> high centrality</span>
                    <span><strong style="color:var(--yellow)">${data.architectural_enrichment.severityDistribution?.medium || 0}</strong> medium</span>
                    <span><strong style="color:var(--green)">${data.architectural_enrichment.severityDistribution?.low || 0}</strong> low</span>
                    ${data.architectural_enrichment.upgradedFindings > 0 ? `
                    <span style="color:var(--red)">
                        &#9650; ${data.architectural_enrichment.upgradedFindings} upgraded
                        <span style="color:var(--text-muted)">(warning &rarr; error in critical files)</span>
                    </span>` : ''}
                </div>
            </div>` : ''}
            ${(report.unmappedFindings || []).length ? `
            <div style="margin-top:12px;padding:8px 12px;background:rgba(234,179,8,0.06);border-radius:6px;font-size:12px;color:var(--text-muted)">
                <strong>${report.unmappedFindings.length} unmapped finding${report.unmappedFindings.length !== 1 ? 's' : ''}</strong>
                — no CWE-to-control mapping found for these results
            </div>` : ''}
            <div style="margin-top:16px">
                ${articles.map((art, i) => Components.renderArticleAccordion(art, i, 'import')).join('')}
            </div>
        </div>`;
    },

    _renderSbomReport(data, fw, container) {
        const report = data.report;
        const s = report.summary || {};
        const score = s.score || 0;
        const meta = report.sbomMetadata || {};
        const articles = report.articles || [];

        container.innerHTML = `
        <div class="card" style="margin-top:16px">
            <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
                <span>SBOM Analysis &rarr; ${fwLabel(fw)}</span>
                <span style="font-size:12px;color:var(--text-muted)">
                    ${data.format === 'cyclonedx' ? 'CycloneDX' : 'SPDX'} ${meta.specVersion || ''}
                    ${meta.tool ? ' &middot; ' + meta.tool : ''}
                </span>
            </div>
            <div class="import-stats">
                <div class="stat"><span class="val">${data.components_count || 0}</span>components</div>
                <div class="stat"><span class="val">${data.ai_components || 0}</span>AI/ML</div>
                <div class="stat"><span class="val">${data.vulnerabilities || 0}</span>vulnerabilities</div>
                ${data.vulnerability_findings > 0 ? `<div class="stat"><span class="val">${data.vulnerability_findings}</span>CWE-mapped</div>` : ''}
            </div>
            <div class="report-summary" style="margin-top:12px">
                ${Components.renderScoreGauge(score, 100)}
                <div class="report-stats">
                    <div class="stat">
                        <span class="stat-value" style="color:var(--green)">${s.met || 0}</span>
                        <span class="stat-label">Met</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--yellow)">${s.partial || 0}</span>
                        <span class="stat-label">Partial</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--red)">${s.gap || 0}</span>
                        <span class="stat-label">Gap</span>
                    </div>
                </div>
            </div>
            ${meta.criticalVulnerabilities > 0 ? `
            <div style="margin-top:12px;padding:8px 12px;background:rgba(239,68,68,0.06);border-radius:6px;border-left:3px solid var(--red);font-size:12px">
                <strong style="color:var(--red)">${meta.criticalVulnerabilities} critical/high vulnerabilities</strong>
                — these require immediate remediation for compliance
            </div>` : ''}
            ${data.ai_components > 0 ? `
            <div style="margin-top:8px;padding:8px 12px;background:rgba(99,102,241,0.06);border-radius:6px;border-left:3px solid var(--accent);font-size:12px">
                <strong>${data.ai_components} AI/ML packages</strong> detected
                — supply chain governance is critical for AI compliance frameworks
            </div>` : ''}
            <div style="margin-top:16px">
                ${articles.map((art, i) => Components.renderArticleAccordion(art, i, 'sbom')).join('')}
            </div>
        </div>`;
    },

    _renderJunitReport(data, fw, container) {
        const report = data.report;
        const s = report.summary || {};
        const score = s.score || 0;
        const articles = report.articles || [];
        const passRate = data.pass_rate || 0;
        const failures = report.failures || [];

        container.innerHTML = `
        <div class="card" style="margin-top:16px">
            <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
                <span>Test Evidence &rarr; ${fwLabel(fw)}</span>
                <span style="font-size:12px;color:var(--text-muted)">
                    ${data.suites} suite${data.suites !== 1 ? 's' : ''}
                </span>
            </div>
            <div class="import-stats">
                <div class="stat"><span class="val">${data.total_tests || 0}</span>tests</div>
                <div class="stat"><span class="val" style="color:var(--green)">${data.passed || 0}</span>passed</div>
                <div class="stat"><span class="val" style="color:var(--red)">${data.failed || 0}</span>failed</div>
                <div class="stat"><span class="val">${passRate}%</span>pass rate</div>
                <div class="stat"><span class="val">${data.evidence_categories || 0}</span>evidence categories</div>
            </div>
            <div class="report-summary" style="margin-top:12px">
                ${Components.renderScoreGauge(score, 100)}
                <div class="report-stats">
                    <div class="stat">
                        <span class="stat-value" style="color:var(--green)">${s.met || 0}</span>
                        <span class="stat-label">Met</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--yellow)">${s.partial || 0}</span>
                        <span class="stat-label">Partial</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" style="color:var(--red)">${s.gap || 0}</span>
                        <span class="stat-label">Gap</span>
                    </div>
                </div>
            </div>
            ${failures.length > 0 ? `
            <div style="margin-top:12px;padding:8px 12px;background:rgba(239,68,68,0.06);border-radius:6px;border-left:3px solid var(--red);font-size:12px">
                <strong style="color:var(--red)">${failures.length} failed test${failures.length !== 1 ? 's' : ''}</strong>
                ${failures.slice(0, 5).map(f => `
                    <div style="margin-top:4px;color:var(--text-secondary)">
                        <code style="font-size:11px">${f.classname ? f.classname + '.' : ''}${f.test}</code>
                        ${f.message ? `<span style="margin-left:6px;color:var(--text-muted)">${f.message.substring(0, 80)}${f.message.length > 80 ? '...' : ''}</span>` : ''}
                    </div>`).join('')}
                ${failures.length > 5 ? `<div style="margin-top:4px;color:var(--text-muted)">...and ${failures.length - 5} more</div>` : ''}
            </div>` : ''}
            ${data.evidence_categories > 0 ? `
            <div style="margin-top:8px;padding:8px 12px;background:rgba(99,102,241,0.06);border-radius:6px;border-left:3px solid var(--accent);font-size:12px">
                <strong>${data.evidence_categories} compliance evidence categories</strong> detected from test names
                — tests matching audit, access control, data handling, etc. provide direct compliance evidence
            </div>` : ''}
            <div style="margin-top:16px">
                ${articles.map((art, i) => Components.renderArticleAccordion(art, i, 'junit')).join('')}
            </div>
        </div>`;
    },

    /** Compact receipt card shown on the landing page after scan/import completes.
     *  "Landing page = input + receipt. Detail view = the product." */
    _renderReceiptCard(report, savedId, opts) {
        const summary = report.summary || {};
        const score = summary.score || 0;
        const fw = report.framework || 'unknown';
        const fwName = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
        const depth = report.scanDepth || 'structure';
        const scoreColor = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
        const met = summary.met || 0;
        const partial = summary.partial || 0;
        const gap = summary.gap || 0;

        // Depth label
        let depthLabel = 'structure';
        if (depth.includes('semantic')) depthLabel = 'semantic';
        else if (depth.includes('import')) depthLabel = depth.replace('_', ' ');

        // Time
        const timeLabel = 'just now';

        // Optional: progress delta for rescans
        let deltaHtml = '';
        if (opts && opts.prevScore != null) {
            const d = score - opts.prevScore;
            if (d !== 0) {
                const dColor = d > 0 ? 'var(--green)' : 'var(--red)';
                deltaHtml = `<span class="receipt-delta" style="color:${dColor}">${d > 0 ? '+' : ''}${d.toFixed(1)}%</span>`;
            }
        }

        // Optional: compare link for rescans
        let compareHtml = '';
        if (opts && opts.compareLink) {
            compareHtml = `<a href="${opts.compareLink}" class="btn btn-sm receipt-compare-btn" style="text-decoration:none">Compare Scans</a>`;
        }

        // Optional: cost note for funded scans
        let costHtml = '';
        if (opts && opts.costUsd) {
            costHtml = `<div class="receipt-cost-note">Powered by BespokeAgile · with your own key: ~$${opts.costUsd.toFixed(2)}</div>`;
        }

        // Optional: upgrade CTA for structure scans
        let upgradeHtml = '';
        if (opts && opts.showUpgrade) {
            upgradeHtml = `
            <div class="receipt-upgrade">
                <span>Upgrade to semantic scan for deeper analysis</span>
                <button class="btn btn-sm" onclick="document.getElementById('scan-key').focus(); document.getElementById('scan-key').scrollIntoView({behavior:'smooth',block:'center'})">Add API Key</button>
            </div>`;
        }

        return `
        <div class="receipt-card" ${savedId ? `onclick="window.location.hash='#/detail/${savedId}'"` : ''}>
            <div class="receipt-card-main">
                <div class="receipt-score" style="color:${scoreColor}">${Math.round(score)}%</div>
                <div class="receipt-info">
                    <div class="receipt-title">
                        <strong>${fwName}</strong>
                        ${deltaHtml}
                    </div>
                    <div class="receipt-stats">
                        <span class="receipt-stat met">${met} met</span>
                        <span class="receipt-stat-sep">·</span>
                        <span class="receipt-stat partial">${partial} partial</span>
                        <span class="receipt-stat-sep">·</span>
                        <span class="receipt-stat gap">${gap} gap</span>
                    </div>
                    <div class="receipt-meta">
                        ${depthLabel} · ${timeLabel}
                    </div>
                </div>
                <div class="receipt-action">
                    ${savedId ? `<a href="#/detail/${savedId}" class="btn btn-primary btn-sm" style="text-decoration:none" onclick="event.stopPropagation()">View Report &rarr;</a>` : ''}
                    ${compareHtml}
                </div>
            </div>
            ${costHtml}
            ${upgradeHtml}
        </div>`;
    },

    /** Generate a hint about what semantic analysis would check for a control. */
    _semanticHint(ctrl) {
        const req = (ctrl.requirement || '').toLowerCase();
        const id = (ctrl.controlId || '').toLowerCase();
        // Map common compliance themes to what AI would look for
        if (req.includes('risk') || req.includes('assess'))
            return 'Read validation logic, error handling patterns, and defensive coding to identify implicit risk management';
        if (req.includes('log') || req.includes('audit') || req.includes('record'))
            return 'Trace event recording through decorators, middleware, and async handlers beyond named log files';
        if (req.includes('test') || req.includes('verif') || req.includes('valid'))
            return 'Analyze test coverage patterns, assertion quality, and validation depth across the codebase';
        if (req.includes('document') || req.includes('technic'))
            return 'Evaluate docstrings, README quality, inline documentation, and architectural decision records';
        if (req.includes('transparen') || req.includes('explain') || req.includes('interpret'))
            return 'Check for model explanation utilities, decision logging, and user-facing interpretability features';
        if (req.includes('data') || req.includes('privacy') || req.includes('personal'))
            return 'Trace data flows, identify PII handling patterns, and verify access control enforcement';
        if (req.includes('security') || req.includes('protect') || req.includes('access'))
            return 'Map authentication flows, authorization checks, input sanitization, and secrets management';
        if (req.includes('monitor') || req.includes('perform') || req.includes('drift'))
            return 'Identify health checks, metrics collection, alerting patterns, and performance monitoring';
        if (req.includes('human') || req.includes('oversight') || req.includes('review'))
            return 'Look for approval workflows, human-in-the-loop patterns, and override mechanisms';
        if (req.includes('bias') || req.includes('fair') || req.includes('discrim'))
            return 'Analyze data preprocessing, feature selection, and bias detection or mitigation patterns';
        // Generic fallback
        return 'Analyze code patterns, function behavior, and architectural decisions for compliance evidence beyond keyword matching';
    },

};
