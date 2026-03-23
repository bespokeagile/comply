/* Detail view — scan result with tabs: Overview, Controls, Layers, Regression, Export */
const DetailView = {
    _report: null,
    _scanId: null,
    _activeTab: 'overview',
    _mappingData: null,

    // --- Mode helpers: centralize all demo vs self-hosted rendering decisions ---

    /** Demo badge HTML for the header (empty string in self-hosted). */
    _modeBadge() {
        return this._isDemo ? '<span class="scan-source-badge demo">Demo</span>' : '';
    },

    /** Rescan button (hidden in demo mode). */
    _modeRescanBtn(repoEnc, fwEnc, depth) {
        if (this._isDemo) return '';
        return `<a href="#/scan?repo=${repoEnc}&framework=${fwEnc}&depth=${encodeURIComponent(depth || 'content')}" class="btn btn-secondary btn-sm">Rescan</a>`;
    },

    /** Semantic upgrade CTA — disabled with hint in demo, functional in self-hosted. */
    _modeUpgradeBtn(target, fw) {
        if (this._isDemo) {
            return `<button class="btn btn-primary" disabled style="opacity:0.5;cursor:not-allowed">Run Full Semantic Scan</button>
                <div style="font-size:11px;color:var(--text-muted);margin-top:6px">Scan your own repo to try semantic analysis</div>`;
        }
        return `<button class="btn btn-primary" onclick="DetailView._upgradeToSemantic('${target}', '${fw}')">Run Full Semantic Scan</button>`;
    },

    /** "Scan Against Another Framework" card (self-hosted only). */
    _modeRemapCard(report) {
        if (this._isDemo) return '';
        const r = report;
        const fw = r.framework || '';
        const target = r.target || r.repoUrl || '';
        const isImport = (r.scanDepth || '').includes('_import');
        const allFw = [
            { id: 'owasp_agentic_top10', label: 'OWASP Agentic Top 10' },
            { id: 'owasp_llm_top10', label: 'OWASP LLM Top 10' },
            { id: 'eu_ai_act', label: 'EU AI Act' },
            { id: 'soc2_ai', label: 'SOC 2 AI' },
            { id: 'nist_ai_rmf', label: 'NIST AI RMF' },
            { id: 'iso_42001', label: 'ISO 42001' },
        ];
        const repoSlug = r.repoSlug || (target || '').replace(/.*\//, '');
        const mappedFws = new Set();
        const allScans = ScanAdapter.list();
        for (const scan of allScans) {
            const sSlug = scan.repoSlug || (scan.url || '').replace(/.*\//, '');
            if (sSlug === repoSlug && scan.framework) mappedFws.add(scan.framework);
        }
        const available = allFw.filter(f => f.id !== fw && !mappedFws.has(f.id));
        if (available.length > 0) {
            const options = available.map(f => `<option value="${f.id}">${f.label}</option>`).join('');
            const mappedList = allFw.filter(f => f.id === fw || mappedFws.has(f.id))
                .map(f => `<span class="inline-badge">&#10003; ${f.label}${f.id === fw ? ' (current)' : ''}</span>`).join('');
            const actionBtn = isImport
                ? `<button class="btn btn-primary" id="remap-btn" onclick="DetailView._handleRemap()">Analyze</button>`
                : `<button class="btn btn-primary" id="remap-btn" onclick="DetailView._handleRescan()">Scan</button>`;
            const subtitle = isImport
                ? 'Re-analyze this imported file against a different compliance framework.'
                : 'Scan this repository against a different compliance framework.';
            return `
            <div class="card card-info">
                <div class="card-header">Scan Against Another Framework</div>
                <p class="text-desc mb-8">${subtitle}</p>
                ${mappedList ? `<div style="margin-bottom:10px">${mappedList}</div>` : ''}
                <div style="display:flex;gap:12px;align-items:center">
                    <select id="remap-framework" class="form-select" style="flex:1;max-width:280px">${options}</select>
                    ${actionBtn}
                </div>
                <div id="remap-status" style="margin-top:8px"></div>
            </div>`;
        }
        const mappedList = allFw.filter(f => mappedFws.has(f.id))
            .map(f => `<span class="inline-badge-success">&#10003; ${f.label}${f.id === fw ? ' (current)' : ''}</span>`).join('');
        return `
        <div class="card card-success">
            <div class="card-header">All Frameworks Scanned</div>
            <p class="text-desc mb-8">${isImport ? 'This file has been analyzed' : 'This repository has been scanned'} against all available frameworks.</p>
            <div>${mappedList}</div>
        </div>`;
    },

    /** Monitor + CI/CD gate CTAs (self-hosted only). */
    _modePhase4Ctas(target, fw) {
        if (this._isDemo) return '';
        return `<div class="phase4-ctas">
            <a href="#/monitor?repo=${encodeURIComponent(target)}&framework=${encodeURIComponent(fw)}" class="phase4-cta">
                <span class="phase4-cta-icon">&#128065;</span>
                <div>
                    <strong>Watch for drift</strong>
                    <span>Set up continuous monitoring to detect compliance changes</span>
                </div>
            </a>
            <a href="#/gate?repo=${encodeURIComponent(target)}&framework=${encodeURIComponent(fw)}" class="phase4-cta">
                <span class="phase4-cta-icon">&#9881;</span>
                <div>
                    <strong>Add CI/CD gate</strong>
                    <span>Block non-compliant deploys in your pipeline</span>
                </div>
            </a>
        </div>`;
    },

    async render(params) {
        this._scanId = params[0];
        const app = document.getElementById('app');

        // Default to most recent scan if no ID provided
        if (!this._scanId) {
            const scans = ScanAdapter.list();
            if (scans.length > 0) {
                this._scanId = scans[0].id;
            } else {
                app.innerHTML = '<div class="empty-state"><h3>No scans yet</h3><p>Run a scan from the Home page to see results here.</p></div>';
                return;
            }
        }

        app.innerHTML = '<div class="loading"><span class="spinner"></span> Loading report...</div>';

        try {
            // Pre-fetch mapping data for cross-framework insights (non-blocking)
            this._fetchMappingData();

            // Try client-side storage first (ScanAdapter merges catalog + user scans)
            const local = await ScanAdapter.getWithReport(this._scanId);
            if (local && local.report) {
                this._report = local.report;
                this._renderReport();
                return;
            }
            // Try server-side (pre-scanned results or non-demo mode)
            try {
                this._report = await complyApi.getScanReport(this._scanId);
            } catch (e) {
                const stored = await complyApi.getHistoryScan(this._scanId);
                this._report = stored.report || stored;
            }
            App.setLastResult(this._scanId);
            this._renderReport();
        } catch (e) {
            app.innerHTML = `<div class="alert alert-error">Failed to load report: ${e.message}</div>`;
        }
    },

    _renderReport() {
        const r = this._report;
        const summary = r.summary || {};
        const app = document.getElementById('app');
        this._isDemo = ScanAdapter.isDemo(this._scanId);

        const repoName = (r.target || '').replace(/.*\//, '').replace(/\.git$/, '') || '';

        const depthLabel = (r.scanDepth || '').includes('structure') ? 'Quick Scan'
            : (r.scanDepth || '').includes('semantic') ? 'Deep Scan' : 'Standard Scan';
        const target = r.target || r.repoUrl || '';
        const fw = r.framework || '';
        const repoEnc = encodeURIComponent(target);
        const fwEnc = encodeURIComponent(fw);

        app.innerHTML = `
        <div class="page-header page-header-flex">
            <div>
                ${repoName ? `<div class="page-header-subtitle">${repoName}</div>` : ''}
                <h2>
                    ${typeof fwLabel === 'function' ? fwLabel(fw) : (fw || 'Compliance')} Scan
                    ${this._modeBadge()}
                </h2>
                <p>${depthLabel} &middot; ${(r.generatedAt || '').substring(0, 19)}</p>
            </div>
            <div class="detail-header-actions">
                <button class="btn btn-primary btn-sm" onclick="ReportGenerator.fromScan('${this._scanId}')" title="Generate governance report">Report</button>
                ${this._modeRescanBtn(repoEnc, fwEnc, r.scanDepth)}
            </div>
        </div>

        <div class="detail-breadcrumb">
            <a href="#/landing">Home</a>
            <span class="breadcrumb-sep">&rsaquo;</span>
            ${repoName ? `<span class="breadcrumb-repo">${repoName}</span><span class="breadcrumb-sep">&rsaquo;</span>` : ''}
            <span>${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</span>
        </div>

        <div class="tab-bar">
            <div class="tab active" data-tab="overview" onclick="DetailView.switchTab('overview')">Overview</div>
            <div class="tab" data-tab="remediation" onclick="DetailView.switchTab('remediation')">Remediation</div>
            <div class="tab" data-tab="controls" onclick="DetailView.switchTab('controls')">Controls</div>
            <div class="tab" data-tab="export" onclick="DetailView.switchTab('export')">Export</div>
            ${this._hasRegression() ? `<div class="tab" data-tab="regression" onclick="DetailView.switchTab('regression')">Regression</div>` : ''}
        </div>

        <div id="tab-content"></div>`;

        // Check for deep-link query params (e.g. ?control=14.1&article=Article%2014)
        const qp = Router.getQueryParams();
        if (qp.control || qp.article) {
            this.switchTab('controls');
            setTimeout(() => this._highlightControl(qp.article, qp.control), 150);
        } else {
            this.switchTab('overview');
        }
    },

    /** Highlight a specific control from deep link or co-pilot event. */
    _highlightControl(articleId, controlId) {
        if (articleId) {
            const accordion = document.querySelector(`[data-article-id="${articleId}"]`);
            if (accordion && !accordion.classList.contains('open')) {
                accordion.classList.add('open');
            }
        }
        if (controlId) {
            const row = document.querySelector(`[data-control-id="${controlId}"]`);
            if (row) {
                row.classList.add('ai-highlight');
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                const uid = 'ctrl-' + controlId.replace(/[^a-zA-Z0-9]/g, '-');
                const detail = document.getElementById(uid + '-detail');
                if (detail) detail.style.display = 'table-row';
                setTimeout(() => row.classList.remove('ai-highlight'), 5000);
            }
        }
    },

    /** Check if regression data might be available (baseline set or multiple scans). */
    _hasRegression() {
        const posture = this._report.posture || {};
        return posture.hasBaseline || false;
    },

    switchTab(tab) {
        this._activeTab = tab;
        document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));

        const content = document.getElementById('tab-content');
        switch (tab) {
            case 'overview': content.innerHTML = this._renderOverview(); break;
            case 'controls': content.innerHTML = this._renderControls(); break;
            case 'remediation': content.innerHTML = this._renderRemediation(); Components._updateWhatIfDisplay(); break;
            case 'regression': this._renderRegression(content); break;
            case 'export': content.innerHTML = this._renderExport(); break;
        }
    },

    _renderOverview() {
        const r = this._report;
        const s = r.summary || {};
        const m = r.model || {};
        const posture = r.posture || {};

        let postureHtml = '';
        if (posture.combinedScore !== undefined) {
            postureHtml = `
            <div class="card">
                <div class="card-header">Three-Layer Posture</div>
                <div class="grid-2">
                    <div>
                        ${Components.renderScoreGauge(posture.combinedScore, 80)}
                        <div style="font-size:12px;color:var(--text-muted);margin-top:4px">Combined score</div>
                    </div>
                    <div style="font-size:13px">
                        <p>Baseline: ${posture.hasBaseline ? 'Set' : 'Not set'}</p>
                        <p>Regression: ${posture.regressionDetected ? '<span style="color:var(--red)">Detected</span>' : '<span style="color:var(--green)">None</span>'}</p>
                        ${posture.auditSummary ? `<p>Audit records: ${posture.auditSummary.total_records || 0}</p>` : ''}
                    </div>
                </div>
            </div>`;
        }

        // Verification loop: detect score improvement vs previous scans
        let verificationHtml = '';
        const target = r.target || r.repoUrl || '';
        const fw = r.framework || '';
        const currentScore = s.score || 0;
        {
            const allScans = ScanAdapter.list();
            const repoSlug = (target || '').replace(/.*\//, '').toLowerCase();
            // Find same-repo + same-framework scans, sorted oldest first
            const relatedScans = allScans.filter(scan => {
                if (scan.id === this._scanId) return false;
                const scanSlug = (scan.url || '').replace(/.*\//, '').toLowerCase();
                return scanSlug === repoSlug && fwNorm(scan.framework) === fwNorm(fw);
            }).sort((a, b) => (a.date || '') < (b.date || '') ? -1 : 1);

            if (relatedScans.length > 0) {
                const previous = relatedScans[relatedScans.length - 1];
                const prevScore = previous.score || 0;
                const delta = currentScore - prevScore;

                // Compute streak: count consecutive improvements going backwards
                let streak = 0;
                if (delta > 0) {
                    streak = 1;
                    const allSorted = [...relatedScans, { id: this._scanId, score: currentScore }];
                    for (let i = allSorted.length - 1; i > 0; i--) {
                        if (allSorted[i].score > allSorted[i - 1].score) streak++;
                        else break;
                    }
                }

                if (delta > 0) {
                    verificationHtml = `
                    <div class="verification-banner verification-improved">
                        <div class="verification-icon">&#9650;</div>
                        <div class="verification-text">
                            <strong>Score improved: ${prevScore.toFixed(1)}% &rarr; ${currentScore.toFixed(1)}%</strong>
                            <span>(+${delta.toFixed(1)}% since previous scan)</span>
                            ${streak >= 2 ? `<span class="verification-streak">${streak} consecutive improvements</span>` : ''}
                        </div>
                        <a href="#/diff/${previous.id}/${this._scanId}" class="btn btn-sm btn-secondary">Compare</a>
                    </div>`;
                } else if (delta < 0) {
                    verificationHtml = `
                    <div class="verification-banner verification-regressed">
                        <div class="verification-icon">&#9660;</div>
                        <div class="verification-text">
                            <strong>Score decreased: ${prevScore.toFixed(1)}% &rarr; ${currentScore.toFixed(1)}%</strong>
                            <span>(${delta.toFixed(1)}% since previous scan)</span>
                        </div>
                        <a href="#/diff/${previous.id}/${this._scanId}" class="btn btn-sm btn-secondary">Compare</a>
                    </div>`;
                } else {
                    verificationHtml = `
                    <div class="verification-banner verification-stable">
                        <div class="verification-icon">&rarr;</div>
                        <div class="verification-text">
                            <strong>Score stable at ${currentScore.toFixed(1)}%</strong>
                        </div>
                        <a href="#/diff/${previous.id}/${this._scanId}" class="btn btn-sm btn-secondary">Compare</a>
                    </div>`;
                }
            }
        }

        // CTA: upgrade for structure scans, download for semantic scans
        let ctaHtml = '';
        const isStructure = (r.scanDepth || '').includes('structure');
        const isContent = (r.scanDepth || '').includes('content');
        const isSemantic = (r.scanDepth || '').includes('semantic');
        const gapCount = s.gap || 0;

        if (isStructure) {
            // Check if a matching semantic scan exists for compare
            const allScans = ScanAdapter.list();
            const matchingSemantic = allScans.find(scan =>
                scan.framework === fw && scan.depth && scan.depth.includes('semantic') &&
                scan.url && target && scan.url.toLowerCase() === target.toLowerCase()
            );

            const est = r.cost_estimate || {};
            const options = est.model_options || [];
            const costStr = options.length > 0
                ? `~$${options[0].estimated_cost_usd.toFixed(2)}`
                : '';

            if (matchingSemantic) {
                ctaHtml = `
                <div class="detail-upgrade-cta card-success">
                    <div class="upgrade-cta-text">
                        <strong>You have both structure and semantic scans</strong>
                        <p>Compare what AI analysis found beyond pattern matching for this repository.</p>
                    </div>
                    <a href="#/diff/${this._scanId}/${matchingSemantic.id}" class="btn btn-primary" class="no-decoration">
                        Compare Scans
                    </a>
                </div>`;
            } else {
                ctaHtml = `
                <div class="detail-upgrade-cta">
                    <div class="upgrade-cta-text">
                        <strong>Go deeper with AI analysis</strong>
                        <p>This structure scan found ${s.total || 0} controls across ${m.filesScanned || 0} files.
                        A semantic scan uses AI to analyze code intent, not just patterns.
                        ${costStr ? `Estimated cost: <strong style="color:var(--accent)">${costStr}</strong>` : ''}</p>
                    </div>
                    <div style="text-align:right">
                        ${this._modeUpgradeBtn(target, fw)}
                    </div>
                </div>`;
            }
        } else if (isSemantic) {
            // Check if a matching structure scan exists for compare
            const allScans = ScanAdapter.list();
            const matchingStructure = allScans.find(scan =>
                scan.framework === fw && scan.depth && scan.depth.includes('structure') &&
                scan.url && target && scan.url.toLowerCase() === target.toLowerCase()
            );

            if (matchingStructure) {
                ctaHtml = `
                <div class="detail-upgrade-cta card-success">
                    <div class="upgrade-cta-text">
                        <strong>You have both structure and semantic scans</strong>
                        <p>Compare what AI analysis found beyond pattern matching for this repository.</p>
                    </div>
                    <a href="#/diff/${matchingStructure.id}/${this._scanId}" class="btn btn-primary" class="no-decoration">
                        Compare Scans
                    </a>
                </div>`;
            }
        }

        // Fallback "Scan Deeper" CTA when no compare pair exists
        if (!ctaHtml && (isStructure || isContent) && !isSemantic) {
            const repoEnc = encodeURIComponent(target);
            const fwEnc = encodeURIComponent(fw);
            ctaHtml = `
            <div class="detail-upgrade-cta">
                <div class="upgrade-cta-text">
                    <strong>Scan deeper for hidden gaps</strong>
                    <p>This scan found ${s.total || 0} controls using pattern matching.
                    A deep scan uses AI to analyze code intent and uncover gaps that patterns miss.</p>
                </div>
                <a href="#/scan?repo=${repoEnc}&framework=${fwEnc}&depth=semantic" class="btn btn-primary" class="no-decoration">
                    Scan Deeper
                </a>
            </div>`;
        }

        // Remediation Roadmap CTA (shown when there are gaps)
        let remediationCtaHtml = '';
        if (gapCount > 0) {
            remediationCtaHtml = `
            <div class="remediation-cta" onclick="DetailView.switchTab('remediation')" style="cursor:pointer">
                <div class="remediation-cta-icon">&#9888;</div>
                <div class="remediation-cta-text">
                    <strong>${gapCount} gap${gapCount !== 1 ? 's' : ''} identified</strong>
                    <span>View the Remediation Roadmap to prioritize fixes</span>
                </div>
                <span class="remediation-cta-arrow">&#8594;</span>
            </div>`;
        }

        // Incremental scan metadata
        const inc = r.incremental || null;
        let incrementalHtml = '';
        if (inc) {
            const pct = inc.controls_carried_forward && (inc.controls_reevaluated + inc.controls_carried_forward) > 0
                ? Math.round(inc.controls_carried_forward / (inc.controls_reevaluated + inc.controls_carried_forward) * 100)
                : 0;
            incrementalHtml = `
            <div class="card incremental-card">
                <div class="card-header">Incremental Scan</div>
                <div class="incremental-stats">
                    <div class="incremental-stat">
                        <div class="incremental-stat-value">${inc.files_changed}</div>
                        <div class="incremental-stat-label">files changed</div>
                    </div>
                    <div class="incremental-stat">
                        <div class="incremental-stat-value">${inc.controls_reevaluated}</div>
                        <div class="incremental-stat-label">re-evaluated</div>
                    </div>
                    <div class="incremental-stat">
                        <div class="incremental-stat-value">${inc.controls_carried_forward}</div>
                        <div class="incremental-stat-label">carried forward</div>
                    </div>
                    <div class="incremental-stat">
                        <div class="incremental-stat-value">${pct}%</div>
                        <div class="incremental-stat-label">reused</div>
                    </div>
                </div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:8px">
                    Baseline: <code>${(inc.baseline_sha || '').substring(0, 8)}</code> &rarr;
                    Current: <code>${(inc.current_sha || '').substring(0, 8)}</code>
                </div>
            </div>`;
        }

        const remapHtml = this._modeRemapCard(r);

        return `
        ${verificationHtml}
        ${ctaHtml}
        ${remediationCtaHtml}
        <div class="grid-2">
            <div class="card">
                <div class="card-header">Compliance Score</div>
                ${Components.renderScoreGauge(s.score || 0, 120)}
                <div style="margin-top:12px;font-size:13px">
                    <span style="color:var(--green)">${s.met || 0} met</span> &middot;
                    <span style="color:var(--yellow)">${s.partial || 0} partial</span> &middot;
                    <span style="color:var(--red)">${s.gap || 0} gap</span> &middot;
                    ${s.total || 0} total
                </div>
                ${Components.renderCategoryBreakdown(r)}
            </div>
            <div class="card">
                <div class="card-header">Scan Details</div>
                <div style="font-size:13px;line-height:2">
                    <div>Framework: <strong>${typeof fwLabel === 'function' ? fwLabel(r.framework || '') : (r.framework || '')}</strong></div>
                    <div>Depth: <strong>${(r.scanDepth || '').includes('structure') ? 'Quick' : (r.scanDepth || '').includes('semantic') ? 'Deep' : 'Standard'}</strong></div>
                    <div>Files: <strong>${m.filesScanned || 0}</strong></div>
                    <div>Features: <strong>${m.featuresDiscovered || 0}</strong></div>
                    <div>Commit: <code>${(r.commitSha || '').substring(0, 8)}</code></div>
                </div>
            </div>
        </div>
        ${remapHtml}
        ${incrementalHtml}
        ${postureHtml}
        <div class="card">
            <div class="card-header">Per-Article Summary</div>
            ${Components.renderTable(
                ['Article', 'Met', 'Partial', 'Gap'],
                (r.articles || []).map(a => [
                    `${a.articleId || ''}: ${a.label || ''}`,
                    `<span style="color:var(--green)">${a.met || 0}</span>`,
                    `<span style="color:var(--yellow)">${a.partial || 0}</span>`,
                    `<span style="color:var(--red)">${a.gap || 0}</span>`,
                ])
            )}
        </div>
        ${this._modePhase4Ctas(target, fw)}`;
    },

    _renderControls() {
        const articles = this._report.articles || [];
        const remediations = this._report.remediations || [];
        let html = articles.map((a, i) => Components.renderArticleAccordion(a, i, 'detail', remediations)).join('');

        // Fold Layers view into Controls as a collapsible section
        const layerHtml = this._renderLayers();
        if (layerHtml) {
            html += `
            <div class="accordion-item" id="layers-section">
                <div class="accordion-header" onclick="Components.toggleAccordion('layers-section')">
                    <span>Three-Layer Posture Breakdown</span>
                    <span class="accordion-chevron">&#9656;</span>
                </div>
                <div class="accordion-body">${layerHtml}</div>
            </div>`;
        }

        return html;
    },

    async _fetchMappingData() {
        if (this._mappingData) return; // already cached
        try {
            this._mappingData = await complyApi.getMapping();
        } catch (e) {
            this._mappingData = null;
        }
    },

    /** Build cross-framework lookup: evidence_fn → [{framework, controlId, label}] excluding current fw. */
    _buildCrossFwMap() {
        if (!this._mappingData || !this._mappingData.capabilities) return null;
        const currentFw = (this._report.framework || '').replace(/-/g, '_');
        const map = {};
        for (const cap of this._mappingData.capabilities) {
            const others = (cap.controls || [])
                .filter(c => c.framework.replace(/-/g, '_') !== currentFw)
                .map(c => ({
                    framework: c.framework,
                    controlId: c.controlId,
                    label: typeof fwLabel === 'function' ? fwLabel(c.framework) : c.framework,
                }));
            if (others.length > 0) {
                map[cap.evidence_fn] = others;
            }
        }
        return map;
    },

    _renderRemediation() {
        const remediations = this._report.remediations || [];
        if (remediations.length === 0) {
            // Fallback for older scans: show recommendations from controls
            const articles = this._report.articles || [];
            const recs = [];
            for (const art of articles) {
                for (const ctrl of (art.controls || [])) {
                    if ((ctrl.status === 'gap' || ctrl.status === 'partial') && ctrl.recommendation) {
                        recs.push(ctrl);
                    }
                }
            }
            if (recs.length === 0) {
                return '<div class="alert alert-success">All controls met. No remediation needed.</div>';
            }
            let html = `<div class="alert alert-info" class="mb-16">
                This scan does not include graph-aware remediation. Showing control recommendations instead.
                Re-scan to get specific, file-path-aware action items.
            </div>`;
            html += `<div class="card"><div class="card-header">Recommendations (${recs.length})</div>`;
            for (const ctrl of recs) {
                html += `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">
                    ${Components.renderStatusBadge(ctrl.status)}
                    <strong>${ctrl.controlId}</strong>: ${ctrl.recommendation}
                </div>`;
            }
            html += '</div>';
            return html;
        }

        const currentScore = (this._report.summary || {}).score || 0;
        // Build rank map: priority order from backend (index = rank)
        const rankMap = new Map();
        remediations.forEach((r, i) => rankMap.set(r, i + 1));

        const summary = this._report.summary || {};
        const nonCodeItems = Components.buildNonCodeItems(this._report);
        const scanId = this._scanId || '';
        const crossFwMap = this._buildCrossFwMap();
        let html = Components.renderRemediationSummary(remediations, currentScore, summary, nonCodeItems, scanId);
        html += Components.renderRemediationPhases(remediations, currentScore, rankMap, nonCodeItems, scanId, crossFwMap);

        return html;
    },

    _renderLayers() {
        const articles = this._report.articles || [];
        let hasLayers = false;

        let html = '<div class="grid-3">';
        const layerNames = ['code', 'process', 'traffic'];
        const layerLabels = ['Layer 1: Code', 'Layer 2: Process', 'Layer 3: Traffic'];

        layerNames.forEach((ln, li) => {
            html += `<div class="card"><div class="card-header">${layerLabels[li]}</div>`;
            let items = '';
            for (const art of articles) {
                for (const ctrl of (art.controls || [])) {
                    const layers = ctrl.layers;
                    if (layers && layers[ln]) {
                        hasLayers = true;
                        const ls = layers[ln];
                        items += `<div style="margin-bottom:8px;font-size:12px">
                            ${Components.renderStatusBadge(ls.status)}
                            <strong>${ctrl.controlId}</strong>
                            ${(ls.evidence || []).map(e => `<div style="color:var(--text-muted);margin-left:16px">${e}</div>`).join('')}
                        </div>`;
                    }
                }
            }
            html += items || '<div class="empty-state" style="padding:16px">No data</div>';
            html += '</div>';
        });
        html += '</div>';

        if (!hasLayers) {
            return `
            <div class="alert alert-info" class="mb-16">
                Three-layer posture analysis is available when self-hosting Comply.
            </div>
            <div class="grid-3">
                <div class="card" class="card-muted">
                    <div class="card-header">Layer 1: Code</div>
                    <div style="font-size:13px;color:var(--text-muted);padding:12px 0">
                        Static analysis of source code for compliance-relevant patterns, configurations, and documentation.
                    </div>
                </div>
                <div class="card" class="card-muted">
                    <div class="card-header">Layer 2: Process</div>
                    <div style="font-size:13px;color:var(--text-muted);padding:12px 0">
                        CI/CD pipeline checks, review gates, and workflow evidence from your development process.
                    </div>
                </div>
                <div class="card" class="card-muted">
                    <div class="card-header">Layer 3: Traffic</div>
                    <div style="font-size:13px;color:var(--text-muted);padding:12px 0">
                        Runtime audit logs, monitoring data, and operational evidence from production systems.
                    </div>
                </div>
            </div>
            <div style="text-align:center;margin-top:16px;font-size:13px;color:var(--text-muted)">
                Connect audit log adapters and set a baseline to populate all three layers.
            </div>`;
        }
        return html;
    },

    async _renderRegression(container) {
        // Demo/catalog scans: no server-side regression data
        if (this._isDemo) {
            container.innerHTML = `
            <div class="alert alert-info" class="mb-16">
                Regression tracking is available when self-hosting Comply with scheduled scans.
            </div>
            <div class="card" class="card-muted">
                <div class="card-header">How Regression Works</div>
                <div style="font-size:13px;color:var(--text-muted);padding:4px 0;line-height:1.8">
                    <div><strong style="color:var(--text-primary)">1. Set a baseline</strong> -- lock in your current compliance posture as the reference point</div>
                    <div><strong style="color:var(--text-primary)">2. Schedule scans</strong> -- automatic re-scans via CI/CD or the monitor daemon</div>
                    <div><strong style="color:var(--text-primary)">3. Detect drift</strong> -- new gaps flagged immediately, resolved gaps tracked</div>
                    <div><strong style="color:var(--text-primary)">4. Gate deployments</strong> -- block releases that introduce compliance regressions</div>
                </div>
            </div>`;
            return;
        }
        container.innerHTML = '<div class="loading"><span class="spinner"></span> Checking regression...</div>';
        try {
            const reg = await complyApi.getScanRegression(this._scanId);
            if (!reg.regressionDetected && reg.message) {
                container.innerHTML = `<div class="alert alert-info">${reg.message}</div>`;
                return;
            }

            const newGaps = reg.newGaps || [];
            const resolved = reg.resolvedGaps || [];
            const delta = reg.scoreDelta || 0;

            let html = '';
            if (reg.regressionDetected) {
                html += `<div class="alert alert-error">Regression detected: score ${delta > 0 ? '+' : ''}${delta.toFixed(1)}%</div>`;
            } else {
                html += `<div class="alert alert-success">No regression detected</div>`;
            }

            if (newGaps.length) {
                html += `<div class="card"><div class="card-header" style="color:var(--red)">New Gaps (${newGaps.length})</div>`;
                html += newGaps.map(g => `<div style="font-size:13px;margin-bottom:6px">
                    ${Components.renderStatusBadge('gap')} <strong>${g.controlId || ''}</strong>: ${(g.requirement || '').substring(0, 100)}
                </div>`).join('');
                html += '</div>';
            }

            if (resolved.length) {
                html += `<div class="card"><div class="card-header" style="color:var(--green)">Resolved (${resolved.length})</div>`;
                html += resolved.map(g => `<div style="font-size:13px;margin-bottom:6px">
                    ${Components.renderStatusBadge('met')} <strong>${g.controlId || ''}</strong>: ${(g.requirement || '').substring(0, 100)}
                </div>`).join('');
                html += '</div>';
            }

            container.innerHTML = html || '<div class="alert alert-info">No regression data available</div>';
        } catch (e) {
            container.innerHTML = `<div class="alert alert-info">${e.message}</div>`;
        }
    },

    _renderExport() {
        const id = this._scanId;
        const isLocal = ScanAdapter.get(id);

        // Hero: Governance Reports (always shown, always first)
        let html = `
        <div class="export-hero">
            <div class="card export-report-card">
                <div class="card-header">Generate Governance Report</div>
                <p class="export-desc">
                    Audit-ready compliance report with executive summary, control scorecard, evidence, and remediation plan. Opens in a new tab — print to PDF.
                </p>
                <button class="btn btn-primary export-hero-btn" onclick="ReportGenerator.fromScan('${id}')">
                    Full Compliance Report
                </button>
                <div class="export-report-variants">
                    <button class="btn btn-sm" onclick="ReportGenerator.boardSummary('${id}')">
                        Board Summary (1 page)
                    </button>
                    <button class="btn btn-sm" onclick="ReportGenerator.evidenceBinder('${id}')">
                        Evidence Binder
                    </button>
                </div>
            </div>
        </div>`;

        // Data Export
        if (isLocal) {
            html += `
            <div class="card export-section">
                <div class="card-header">Data Export</div>
                <div class="export-formats">
                    <button class="btn export-fmt-btn" onclick="DetailView._downloadLocal('json')">
                        <span class="export-fmt-icon">{}</span> JSON
                    </button>
                    <button class="btn export-fmt-btn" onclick="DetailView._downloadLocal('csv')">
                        <span class="export-fmt-icon">&#9776;</span> CSV
                    </button>
                </div>
            </div>`;
        } else {
            const formats = [
                { fmt: 'json', label: 'JSON', icon: '{}' },
                { fmt: 'sarif', label: 'SARIF', icon: 'S' },
                { fmt: 'junit', label: 'JUnit', icon: 'X' },
                { fmt: 'markdown', label: 'Markdown', icon: 'M' },
                { fmt: 'docx', label: 'DOCX', icon: 'D' },
                { fmt: 'zip', label: 'Audit Bundle', icon: 'Z' },
            ];
            html += `
            <div class="card export-section">
                <div class="card-header">Download Formats</div>
                <div class="export-formats">
                    ${formats.map(f => `
                        <a href="${complyApi.getDownloadUrl(id, f.fmt)}" class="btn export-fmt-btn" download>
                            <span class="export-fmt-icon">${f.icon}</span> ${f.label}
                        </a>
                    `).join('')}
                </div>
            </div>`;
        }

        // CI/CD & Artifacts (always available)
        html += this._renderCiCdSnippets();
        html += this._renderArtifactTemplates();

        return html;
    },

    _renderCiCdSnippets() {
        const r = this._report;
        if (!r) return '';
        const fw = r.framework || '';
        const repo = r.target || '';
        const score = Math.round((r.summary || {}).score || 0);

        const ghAction = `name: Compliance Check
on: [push, pull_request]
jobs:
  comply:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Comply scan
        run: |
          pip install bespoketracker-comply
          comply scan \\
            --framework ${fw} \\
            --format sarif \\
            --output comply-results.sarif
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: comply-results.sarif
      - name: Gate check
        run: comply gate --min-score ${score}`;

        const preCommit = `# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: comply-check
        name: Compliance check
        entry: comply scan --framework ${fw} --quiet
        language: system
        pass_filenames: false
        always_run: true`;

        const badge = `![Comply ${fwLabel(fw)}](https://img.shields.io/badge/comply-${score}%25-${score >= 80 ? 'brightgreen' : score >= 50 ? 'yellow' : 'red'})`;

        return `
            <div class="card" class="mb-16">
                <div class="card-header">CI/CD Integration <span class="card-header-note">self-hosted</span></div>
                <p class="text-desc mb-16">
                    Add compliance checks to your development workflow. Copy these snippets for your self-hosted Comply instance.
                </p>
                <div class="cicd-snippet-group">
                    <div class="cicd-snippet-label" onclick="DetailView._toggleSnippet('gh-action')">
                        <span class="cicd-snippet-arrow" id="arrow-gh-action">&#9654;</span>
                        GitHub Action
                    </div>
                    <div class="cicd-snippet-body" id="snippet-gh-action" style="display:none">
                        <pre class="cicd-pre">${this._escHtml(ghAction)}</pre>
                        <button class="btn btn-sm" onclick="DetailView._copySnippet('gh-action')">Copy</button>
                    </div>
                </div>
                <div class="cicd-snippet-group">
                    <div class="cicd-snippet-label" onclick="DetailView._toggleSnippet('pre-commit')">
                        <span class="cicd-snippet-arrow" id="arrow-pre-commit">&#9654;</span>
                        Pre-commit Hook
                    </div>
                    <div class="cicd-snippet-body" id="snippet-pre-commit" style="display:none">
                        <pre class="cicd-pre">${this._escHtml(preCommit)}</pre>
                        <button class="btn btn-sm" onclick="DetailView._copySnippet('pre-commit')">Copy</button>
                    </div>
                </div>
                <div class="cicd-snippet-group">
                    <div class="cicd-snippet-label" onclick="DetailView._toggleSnippet('badge')">
                        <span class="cicd-snippet-arrow" id="arrow-badge">&#9654;</span>
                        README Badge
                    </div>
                    <div class="cicd-snippet-body" id="snippet-badge" style="display:none">
                        <pre class="cicd-pre">${this._escHtml(badge)}</pre>
                        <div style="margin:8px 0">${badge.replace(/!\[([^\]]+)\]\(([^)]+)\)/, '<img src="$2" alt="$1" style="height:20px">')}</div>
                        <button class="btn btn-sm" onclick="DetailView._copySnippet('badge')">Copy</button>
                    </div>
                </div>
            </div>`;
    },

    _renderArtifactTemplates() {
        const r = this._report;
        if (!r) return '';
        const fw = fwLabel(r.framework || '');
        const s = r.summary || {};
        const repo = (r.target || '').replace(/.*\//, '') || 'your-repo';

        // Determine which artifacts are relevant based on gap controls
        const gapControls = [];
        (r.articles || []).forEach(a => {
            (a.controls || []).forEach(c => {
                if (c.status === 'gap' || c.status === 'partial') gapControls.push(c);
            });
        });

        const artifacts = [
            {
                id: 'risk-assessment',
                title: 'Risk Assessment Template',
                desc: 'Document AI system risks, likelihood, impact, and mitigation strategies.',
                relevant: true,
            },
            {
                id: 'governance-policy',
                title: 'AI Governance Policy',
                desc: 'Organizational policy for AI development, deployment, and monitoring.',
                relevant: true,
            },
            {
                id: 'transparency-notice',
                title: 'Transparency Notice',
                desc: 'User-facing disclosure of AI system capabilities, limitations, and data usage.',
                relevant: gapControls.some(c => (c.controlId || '').toLowerCase().includes('transparen') || (c.requirement || '').toLowerCase().includes('transparen')),
            },
            {
                id: 'audit-log-schema',
                title: 'Audit Log Schema',
                desc: 'Structured logging format for AI system events, decisions, and data access.',
                relevant: gapControls.some(c => (c.requirement || '').toLowerCase().includes('log') || (c.requirement || '').toLowerCase().includes('audit') || (c.requirement || '').toLowerCase().includes('record')),
            },
            {
                id: 'testing-plan',
                title: 'Compliance Test Plan',
                desc: 'Test cases mapped to compliance controls for ongoing verification.',
                relevant: gapControls.some(c => (c.requirement || '').toLowerCase().includes('test') || (c.requirement || '').toLowerCase().includes('validat') || (c.requirement || '').toLowerCase().includes('monitor')),
            },
            {
                id: 'raci-matrix',
                title: 'RACI Matrix',
                desc: 'Responsibility assignment for all compliance controls and activities.',
                relevant: true,
            },
            {
                id: 'dpia',
                title: 'Data Protection Impact Assessment',
                desc: 'DPIA template for AI systems processing personal data.',
                relevant: gapControls.some(c => (c.requirement || '').toLowerCase().includes('data') || (c.requirement || '').toLowerCase().includes('privacy') || (c.requirement || '').toLowerCase().includes('personal')) || (this._report.framework || '').includes('eu'),
            },
        ];

        const relevant = artifacts.filter(a => a.relevant);
        if (relevant.length === 0) return '';

        return `
            <div class="card" class="mb-16">
                <div class="card-header">Compliance Artifacts</div>
                <p class="text-desc mb-16">
                    Template documents pre-filled from your scan results. Download and customize for your organization.
                </p>
                <div class="artifact-grid">
                    ${relevant.map(a => `
                        <div class="artifact-card">
                            <div class="artifact-title">${a.title}</div>
                            <div class="artifact-desc">${a.desc}</div>
                            <button class="btn btn-sm" onclick="DetailView._downloadArtifact('${a.id}')">Download Template</button>
                        </div>
                    `).join('')}
                </div>
            </div>`;
    },

    _toggleSnippet(id) {
        const body = document.getElementById('snippet-' + id);
        const arrow = document.getElementById('arrow-' + id);
        if (!body) return;
        const open = body.style.display !== 'none';
        body.style.display = open ? 'none' : 'block';
        if (arrow) arrow.innerHTML = open ? '&#9654;' : '&#9660;';
    },

    _copySnippet(id) {
        const pre = document.querySelector('#snippet-' + id + ' pre');
        if (!pre) return;
        navigator.clipboard.writeText(pre.textContent).then(() => {
            const btn = document.querySelector('#snippet-' + id + ' .btn');
            if (btn) { btn.textContent = 'Copied!'; setTimeout(() => btn.textContent = 'Copy', 1500); }
        });
    },

    _escHtml(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    },

    _downloadArtifact(type) {
        const r = this._report;
        if (!r) return;
        const fw = fwLabel(r.framework || '');
        const repo = (r.target || '').replace(/.*\//, '') || 'your-repo';
        const date = new Date().toISOString().split('T')[0];
        const s = r.summary || {};
        const score = Math.round(s.score || 0);

        // Gather gap controls for context
        const gaps = [];
        (r.articles || []).forEach(a => {
            (a.controls || []).forEach(c => {
                if (c.status === 'gap') gaps.push(c);
                if (c.status === 'partial') gaps.push(c);
            });
        });

        let content = '';
        let filename = '';

        if (type === 'risk-assessment') {
            filename = `risk-assessment-${repo}.md`;
            content = this._genRiskAssessment(fw, repo, date, gaps);
        } else if (type === 'governance-policy') {
            filename = `ai-governance-policy-${repo}.md`;
            content = this._genGovernancePolicy(fw, repo, date, s);
        } else if (type === 'transparency-notice') {
            filename = `transparency-notice-${repo}.md`;
            content = this._genTransparencyNotice(fw, repo, date);
        } else if (type === 'audit-log-schema') {
            filename = `audit-log-schema-${repo}.md`;
            content = this._genAuditLogSchema(fw, repo, date);
        } else if (type === 'testing-plan') {
            filename = `compliance-test-plan-${repo}.md`;
            content = this._genTestingPlan(fw, repo, date, gaps);
        } else if (type === 'raci-matrix') {
            filename = `raci-matrix-${repo}.md`;
            content = this._genRaciMatrix(fw, repo, date, gaps);
        } else if (type === 'dpia') {
            filename = `dpia-${repo}.md`;
            content = this._genDpia(fw, repo, date, gaps);
        }

        if (!content) return;
        const blob = new Blob([content], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        URL.revokeObjectURL(url);
    },

    _genRiskAssessment(fw, repo, date, gaps) {
        const riskRows = gaps.slice(0, 10).map((g, i) =>
            `| R-${String(i+1).padStart(3,'0')} | ${g.controlId || 'Unknown'} | ${(g.requirement || '').substring(0, 60)}... | Medium | Medium | Medium | [TODO] |`
        ).join('\n');

        return `# AI Risk Assessment

**System:** ${repo}
**Framework:** ${fw}
**Date:** ${date}
**Version:** 1.0 (DRAFT)
**Owner:** [Name, Title]
**Reviewer:** [Name, Title]
**Next Review:** [Date]

---

## 1. System Description

| Attribute | Value |
|-----------|-------|
| System Name | ${repo} |
| Purpose | [Describe the AI system's purpose] |
| Users | [Who uses this system] |
| Data Sources | [What data does it process] |
| Decision Impact | [What decisions does it influence] |
| Risk Classification | [High / Limited / Minimal] |

## 2. Risk Identification

The following risks were identified through automated compliance scanning and manual assessment:

| Risk ID | Control | Description | Likelihood | Impact | Risk Level | Mitigation |
|---------|---------|-------------|------------|--------|------------|------------|
${riskRows || '| R-001 | [Control ID] | [Description] | [L/M/H] | [L/M/H] | [L/M/H] | [Action] |'}

## 3. Risk Assessment Methodology

- **Likelihood:** Low (unlikely), Medium (possible), High (probable)
- **Impact:** Low (minor), Medium (significant), High (severe)
- **Risk Level:** Derived from likelihood x impact matrix
- **Residual Risk:** Risk remaining after mitigation measures

## 4. Mitigation Plan

| Risk ID | Mitigation Action | Owner | Target Date | Status |
|---------|-------------------|-------|-------------|--------|
| R-001 | [Action] | [Owner] | [Date] | Not Started |

## 5. Monitoring and Review

- This assessment will be reviewed [quarterly / after significant changes]
- Automated compliance scanning via BespokeAgile Comply
- Risk register updated upon each review cycle

## 6. Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| System Owner | | | |
| Risk Reviewer | | | |
| Compliance Officer | | | |

---
*Generated by BespokeAgile Comply on ${date}*
`;
    },

    _genGovernancePolicy(fw, repo, date, summary) {
        return `# AI Governance Policy

**Organization:** [Organization Name]
**Effective Date:** ${date}
**Version:** 1.0 (DRAFT)
**Framework:** ${fw}
**Approved By:** [Name, Title]

---

## 1. Purpose

This policy establishes the governance framework for the development, deployment, and monitoring of AI systems within [Organization Name]. It ensures compliance with ${fw} and promotes responsible AI practices.

## 2. Scope

This policy applies to all AI and machine learning systems developed, deployed, or operated by [Organization Name], including but not limited to:
- ${repo}
- [Additional systems]

## 3. Principles

1. **Transparency:** AI systems must be explainable and their limitations disclosed
2. **Fairness:** AI systems must not discriminate or produce biased outcomes
3. **Accountability:** Clear ownership and responsibility for all AI systems
4. **Privacy:** Personal data must be protected in accordance with applicable laws
5. **Safety:** AI systems must operate safely and as intended
6. **Human Oversight:** Appropriate human review for high-impact decisions

## 4. Roles and Responsibilities

| Role | Responsibilities |
|------|-----------------|
| AI System Owner | Overall accountability for system compliance |
| Development Team | Implement controls, maintain documentation |
| Compliance Officer | Monitor regulatory requirements, conduct assessments |
| Data Protection Officer | Ensure data privacy requirements are met |
| Executive Sponsor | Strategic oversight, resource allocation |

## 5. AI System Lifecycle

### 5.1 Design Phase
- [ ] Risk assessment completed
- [ ] Data requirements documented
- [ ] Fairness criteria defined
- [ ] Human oversight mechanisms designed

### 5.2 Development Phase
- [ ] Input validation implemented
- [ ] Audit logging enabled
- [ ] Testing plan executed
- [ ] Security review completed

### 5.3 Deployment Phase
- [ ] Transparency notice published
- [ ] Monitoring dashboards active
- [ ] Incident response plan in place
- [ ] User training completed

### 5.4 Monitoring Phase
- [ ] Performance metrics tracked
- [ ] Bias monitoring active
- [ ] Compliance scans scheduled
- [ ] Periodic reviews conducted

## 6. Compliance Monitoring

- Automated scanning via BespokeAgile Comply (current score: ${Math.round(summary.score || 0)}%)
- ${summary.met || 0} controls met, ${summary.partial || 0} partially met, ${summary.gap || 0} gaps identified
- Quarterly compliance reviews
- Annual third-party assessment

## 7. Incident Response

1. **Detection:** Automated monitoring and user reports
2. **Assessment:** Severity classification (Critical/High/Medium/Low)
3. **Response:** Containment, investigation, remediation
4. **Communication:** Stakeholder notification per severity
5. **Review:** Root cause analysis and preventive measures

## 8. Training and Awareness

- All staff involved in AI systems must complete governance training
- Annual refresher training required
- New system onboarding includes compliance briefing

## 9. Review and Updates

This policy is reviewed annually or upon:
- Significant regulatory changes
- Major AI system deployments
- Compliance incidents

---
*Generated by BespokeAgile Comply on ${date}*
`;
    },

    _genTransparencyNotice(fw, repo, date) {
        return `# AI System Transparency Notice

**System:** ${repo}
**Date:** ${date}
**Framework:** ${fw}

---

## About This AI System

### What It Does
[Describe what the AI system does in plain language]

### How It Works
[Explain the general approach -- e.g., "uses machine learning to analyze..." without revealing proprietary details]

### What Data It Uses
- **Input data:** [What data the system processes]
- **Training data:** [General description of training data sources]
- **Output data:** [What the system produces]

### Limitations
- [Known limitation 1]
- [Known limitation 2]
- [Scenarios where the system may not perform well]

### Human Oversight
- [How humans are involved in the system's decisions]
- [How to request human review of an AI decision]

### Your Rights
- **Right to explanation:** You may request an explanation of how the system reached a decision
- **Right to contest:** You may contest decisions made with the assistance of this system
- **Right to opt-out:** [If applicable, how to opt out of AI processing]

### Contact
For questions about this AI system, contact: [contact information]

---
*Generated by BespokeAgile Comply on ${date}*
`;
    },

    _genAuditLogSchema(fw, repo, date) {
        return `# Audit Log Schema

**System:** ${repo}
**Date:** ${date}
**Framework:** ${fw}

---

## Log Event Schema

\`\`\`json
{
  "event_id": "uuid",
  "timestamp": "ISO 8601",
  "event_type": "enum: model_invocation | data_access | decision_output | config_change | user_action | system_error",
  "severity": "enum: info | warning | error | critical",

  "actor": {
    "user_id": "string",
    "role": "string",
    "ip_address": "string (hashed for privacy)"
  },

  "resource": {
    "system": "${repo}",
    "component": "string",
    "model_id": "string (if applicable)",
    "model_version": "string"
  },

  "action": {
    "operation": "string",
    "input_summary": "string (no PII)",
    "output_summary": "string (no PII)",
    "confidence_score": "float (if applicable)",
    "decision_rationale": "string"
  },

  "context": {
    "session_id": "string",
    "request_id": "string",
    "data_subjects_affected": "integer",
    "consent_status": "enum: granted | denied | not_applicable"
  },

  "compliance": {
    "framework": "${fw}",
    "controls_exercised": ["control_id_1", "control_id_2"],
    "data_classification": "enum: public | internal | confidential | restricted"
  }
}
\`\`\`

## Required Events

| Event Type | When to Log | Retention |
|-----------|-------------|-----------|
| model_invocation | Every AI model call | 90 days |
| data_access | Access to training/inference data | 1 year |
| decision_output | AI-assisted decisions affecting users | 3 years |
| config_change | Model parameters, thresholds, rules | 5 years |
| user_action | User interactions with AI features | 90 days |
| system_error | Failures, timeouts, unexpected behavior | 1 year |

## Implementation Notes

- Logs must be append-only (tamper-evident)
- PII must be hashed or excluded from log entries
- Logs must be searchable by event_type, timestamp, actor, and resource
- Retention periods must comply with applicable data protection regulations

---
*Generated by BespokeAgile Comply on ${date}*
`;
    },

    _genTestingPlan(fw, repo, date, gaps) {
        const testCases = gaps.slice(0, 8).map((g, i) =>
            `### TC-${String(i+1).padStart(3, '0')}: ${g.controlId || 'Control'}

- **Control:** ${g.controlId || 'Unknown'}
- **Requirement:** ${(g.requirement || '[Requirement text]').substring(0, 120)}
- **Current Status:** ${g.status || 'gap'}
- **Test Type:** [Unit / Integration / Manual]
- **Steps:**
  1. [Step 1]
  2. [Step 2]
  3. [Verify expected outcome]
- **Expected Result:** [What constitutes a pass]
- **Owner:** [Name]
- **Status:** Not Started
`
        ).join('\n');

        return `# Compliance Test Plan

**System:** ${repo}
**Framework:** ${fw}
**Date:** ${date}
**Version:** 1.0 (DRAFT)

---

## 1. Scope

This test plan covers compliance verification for ${repo} against the ${fw} framework. It maps test cases to compliance controls identified as gaps or partially met during automated scanning.

## 2. Test Summary

| Metric | Value |
|--------|-------|
| Total Gap/Partial Controls | ${gaps.length} |
| Test Cases Defined | ${Math.min(gaps.length, 8)} |
| Test Cases Remaining | ${Math.max(gaps.length - 8, 0)} |

## 3. Test Cases

${testCases || '### TC-001: [Control ID]\n\n- **Steps:** [Define test steps]\n- **Expected Result:** [Define pass criteria]\n'}

## 4. Test Schedule

| Phase | Date | Scope |
|-------|------|-------|
| Initial Testing | [Date] | All critical gaps |
| Regression Testing | [Date] | Previously failed tests |
| Full Compliance Scan | [Date] | All controls |

## 5. Pass Criteria

- All critical control tests pass
- Compliance score reaches [target]%
- No regressions from previous scan

---
*Generated by BespokeAgile Comply on ${date}*
`;
    },

    _genRaciMatrix(fw, repo, date, gaps) {
        const allControls = [];
        (this._report.articles || []).forEach(a => {
            (a.controls || []).forEach(c => {
                allControls.push(c);
            });
        });

        const rows = allControls.map(c => {
            const status = c.status || 'gap';
            const urgency = status === 'gap' ? 'High' : status === 'partial' ? 'Medium' : 'Low';
            return `| ${c.controlId || ''} | ${(c.requirement || '').substring(0, 50)}${(c.requirement || '').length > 50 ? '...' : ''} | ${status} | ${urgency} | [R] | [A] | [C] | [I] |`;
        }).join('\n');

        return `# RACI Matrix: AI Compliance

**System:** ${repo}
**Framework:** ${fw}
**Date:** ${date}
**Version:** 1.0 (DRAFT)

---

## Legend

- **R** = Responsible (does the work)
- **A** = Accountable (approves/owns the outcome)
- **C** = Consulted (provides input)
- **I** = Informed (kept in the loop)

## Suggested Roles

| Code | Role | Typical Title |
|------|------|---------------|
| ENG | Engineering | Software Engineer, ML Engineer |
| SEC | Security | Security Engineer, AppSec |
| COMP | Compliance | Compliance Officer, GRC Analyst |
| PM | Product | Product Manager, System Owner |
| EXEC | Executive | CTO, CISO, VP Engineering |
| DPO | Data Protection | Data Protection Officer |

## Control Assignments

| Control | Requirement | Status | Priority | R | A | C | I |
|---------|-------------|--------|----------|---|---|---|---|
${rows}

## Activity Assignments

| Activity | R | A | C | I | Frequency |
|----------|---|---|---|---|-----------|
| Run compliance scan | ENG | COMP | | PM | Weekly |
| Review gap controls | COMP | EXEC | ENG, SEC | PM | Monthly |
| Implement remediations | ENG | PM | COMP, SEC | EXEC | As needed |
| Update risk assessment | COMP | EXEC | ENG, DPO | PM | Quarterly |
| Audit log review | SEC | COMP | ENG | EXEC | Monthly |
| Policy review | COMP | EXEC | ENG, DPO, PM | | Annually |
| Incident response | ENG | SEC | COMP | EXEC, PM | As needed |

---
*Generated by BespokeAgile Comply on ${date}*
`;
    },

    _genDpia(fw, repo, date, gaps) {
        const gapList = gaps.slice(0, 10).map(g =>
            `- **${g.controlId || 'Unknown'}**: ${(g.requirement || '').substring(0, 100)}`
        ).join('\n');

        return `# Data Protection Impact Assessment (DPIA)

**System:** ${repo}
**Framework:** ${fw}
**Date:** ${date}
**Version:** 1.0 (DRAFT)
**Data Controller:** [Organization Name]
**DPO:** [Name, Contact]

---

## 1. Description of Processing

### 1.1 Nature of Processing
[Describe what the AI system does with personal data]

### 1.2 Scope of Processing
- **Data subjects:** [Who the data belongs to]
- **Data categories:** [Types of personal data processed]
- **Volume:** [Scale of processing]
- **Geographic scope:** [Where data is processed/stored]

### 1.3 Context of Processing
- **Relationship to data subjects:** [Customer, employee, public]
- **Control over data:** [How much control data subjects have]
- **Expectations:** [Would data subjects expect this processing]

### 1.4 Purpose of Processing
[Why the AI system processes personal data]

## 2. Necessity and Proportionality

| Question | Assessment |
|----------|------------|
| Is processing necessary for the stated purpose? | [Yes/No + justification] |
| Could the purpose be achieved with less data? | [Yes/No + justification] |
| Is data minimization applied? | [Yes/No + details] |
| Are retention periods defined? | [Yes/No + periods] |
| Is a lawful basis identified? | [Basis: consent / contract / legitimate interest / ...] |

## 3. Risk Assessment

### 3.1 Compliance Gaps Identified

${gapList || '- No gaps identified (all controls met)'}

### 3.2 Risk to Data Subjects

| Risk | Likelihood | Severity | Overall | Mitigation |
|------|-----------|----------|---------|------------|
| Unauthorized access to personal data | [L/M/H] | [L/M/H] | [L/M/H] | [Measures] |
| Algorithmic bias affecting decisions | [L/M/H] | [L/M/H] | [L/M/H] | [Measures] |
| Lack of transparency in AI decisions | [L/M/H] | [L/M/H] | [L/M/H] | [Measures] |
| Data breach or leakage | [L/M/H] | [L/M/H] | [L/M/H] | [Measures] |
| Profiling without adequate safeguards | [L/M/H] | [L/M/H] | [L/M/H] | [Measures] |

## 4. Measures to Address Risks

| Measure | Status | Owner |
|---------|--------|-------|
| Encryption at rest and in transit | [Implemented / Planned] | [Owner] |
| Access control and authentication | [Implemented / Planned] | [Owner] |
| Audit logging for all data access | [Implemented / Planned] | [Owner] |
| Regular bias testing and monitoring | [Implemented / Planned] | [Owner] |
| Data subject rights procedures | [Implemented / Planned] | [Owner] |
| Incident response plan | [Implemented / Planned] | [Owner] |

## 5. Consultation

| Stakeholder | Consulted | Date | Key Feedback |
|-------------|-----------|------|-------------|
| Data Protection Officer | [Yes/No] | | |
| Data subjects / representatives | [Yes/No] | | |
| Supervisory authority | [Yes/No] | | |

## 6. Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Data Controller | | | |
| DPO | | | |
| System Owner | | | |

---
*Generated by BespokeAgile Comply on ${date}*
`;
    },

    async _handleRemap() {
        const fwSelect = document.getElementById('remap-framework');
        const btn = document.getElementById('remap-btn');
        const status = document.getElementById('remap-status');
        if (!fwSelect || !btn) return;

        const newFw = fwSelect.value;
        btn.disabled = true;
        btn.textContent = 'Analyzing...';
        if (status) status.innerHTML = '<span style="font-size:13px;color:var(--text-secondary)">Retrieving import data...</span>';

        try {
            const importData = await ScanAdapter.getImportRaw(this._scanId);
            if (!importData || !importData.raw) {
                if (status) status.innerHTML = '<span style="font-size:13px;color:var(--red)">Raw import data not available. Try re-importing the file from the home page.</span>';
                return;
            }

            if (status) status.innerHTML = '<span style="font-size:13px;color:var(--text-secondary)">Mapping to framework...</span>';

            const fmt = importData.format;
            let parsed = importData.raw;
            // For SARIF/SBOM the raw data is JSON (may be stored as string)
            if (fmt !== 'junit' && typeof parsed === 'string') {
                try { parsed = JSON.parse(parsed); } catch (e) {}
            }

            let data;
            if (fmt === 'sarif') {
                data = await complyApi.importSarif(parsed, newFw);
            } else if (fmt === 'sbom') {
                data = await complyApi.importSbom(parsed, newFw);
            } else if (fmt === 'junit') {
                data = await complyApi.importJunit(parsed, newFw);
            } else {
                if (status) status.innerHTML = '<span style="font-size:13px;color:var(--red)">Unknown import format.</span>';
                return;
            }

            if (data && data.report) {
                const fileName = importData.filename || fmt;
                const report = data.report;
                report.target = report.target || fileName;
                report.repoName = report.repoName || fileName;
                report.scanDepth = report.scanDepth || `${fmt}_import`;
                const savedId = await ScanAdapter.save(report, {
                    source: 'user',
                    importRaw: importData.raw,
                    importFormat: fmt,
                    importFilename: fileName,
                });
                if (typeof App !== 'undefined' && App.refreshSidebar) App.refreshSidebar();
                if (savedId) {
                    window.location.hash = `#/detail/${savedId}`;
                }
            }
        } catch (e) {
            if (status) status.innerHTML = `<span style="font-size:13px;color:var(--red)">${e.message || 'Re-analysis failed'}</span>`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Analyze';
        }
    },

    /** Run a structure scan against a different framework, inline from the detail view. */
    async _handleRescan() {
        const fwSelect = document.getElementById('remap-framework');
        const btn = document.getElementById('remap-btn');
        const status = document.getElementById('remap-status');
        if (!fwSelect || !btn) return;

        const newFw = fwSelect.value;
        const target = this._report.target || this._report.repoUrl || '';
        if (!target) {
            if (status) status.innerHTML = '<span style="font-size:13px;color:var(--red)">No repository URL available.</span>';
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Scanning...';
        if (status) status.innerHTML = '<span style="font-size:13px;color:var(--text-secondary)">Cloning and scanning... This may take 30-60 seconds.</span>';

        try {
            // Build headers (VisitorId + invite token)
            const headers = typeof VisitorId !== 'undefined' ? VisitorId.headers() : {};
            const token = localStorage.getItem('comply_invite_token');
            if (token) headers['X-Invite-Token'] = token;

            const report = await complyApi._fetch('/demo/cost-scan', {
                method: 'POST',
                headers,
                body: JSON.stringify({ url: target, framework: newFw }),
            });

            if (report) {
                const savedId = await ScanAdapter.save(report);
                if (typeof App !== 'undefined' && App.refreshSidebar) App.refreshSidebar();
                if (savedId) {
                    window.location.hash = `#/detail/${savedId}`;
                }
            }
        } catch (e) {
            if (status) {
                if (e.status === 429) {
                    const retryMin = Math.ceil((e.retryAfter || 60) / 60);
                    status.innerHTML = `<span style="font-size:13px;color:var(--red)">Rate limit reached. Try again in ~${retryMin} minute${retryMin > 1 ? 's' : ''}.</span>`;
                } else {
                    status.innerHTML = `<span style="font-size:13px;color:var(--red)">${e.message || 'Scan failed'}</span>`;
                }
            }
        } finally {
            btn.disabled = false;
            btn.textContent = 'Scan';
        }
    },

    _upgradeToSemantic(url, framework) {
        // Navigate to landing page and pre-fill URL + framework, focus API key
        Router.navigate('/landing');
        setTimeout(() => {
            const urlInput = document.getElementById('scan-url');
            const fwSelect = document.getElementById('scan-framework');
            if (urlInput) urlInput.value = url;
            if (fwSelect) fwSelect.value = framework;
            const keyInput = document.getElementById('scan-key');
            if (keyInput) {
                keyInput.focus();
                keyInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            // Trigger rescan detection
            if (urlInput) urlInput.dispatchEvent(new Event('blur'));
        }, 300);
    },

    _downloadLocal(format) {
        const report = this._report;
        if (!report) return;
        // Reuse LandingView's download if available
        if (typeof LandingView !== 'undefined' && LandingView._downloadReport) {
            LandingView._downloadReport(report, format);
            return;
        }
        // Fallback: JSON only
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `comply-${report.framework || 'scan'}-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
    },
};
