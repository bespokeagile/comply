/* report.js -- Governance-ready compliance report generator.
 *
 * Generates self-contained HTML documents that open in a new tab.
 * User can print to PDF for audit-ready compliance documentation.
 *
 * Report types:
 *   fromScan(id)              - single scan report
 *   fromCompare(id1, id2)     - compare/delta report
 *   fromOverlap(slug)         - multi-framework cross-compliance report
 *   boardSummary(id)          - one-page executive summary
 *   evidenceBinder(id)        - structured evidence export (Markdown)
 */
const ReportGenerator = {

    /** Generate and open a single-scan compliance report. */
    async fromScan(scanId) {
        const scan = await ScanAdapter.getWithReport(scanId);
        if (!scan || !scan.report) return alert('Report data not available.');
        this._open(this._buildReport(scan));
    },

    /** Generate and open a compare report (structure vs semantic). */
    async fromCompare(structId, semId) {
        const [s1, s2] = await Promise.all([
            ScanAdapter.getWithReport(structId),
            ScanAdapter.getWithReport(semId),
        ]);
        if (!s1 || !s2 || !s1.report || !s2.report) return alert('Report data not available.');
        const primary = new Date(s1.timestamp) > new Date(s2.timestamp) ? s1 : s2;
        const baseline = primary === s1 ? s2 : s1;
        this._open(this._buildReport(primary, baseline));
    },

    /** Generate and open a multi-framework cross-compliance report. */
    async fromOverlap(slug) {
        if (!ScanAdapter || !Components) {
            return alert('Report data not available.');
        }
        const allScans = ScanAdapter.list();
        const repoScans = allScans.filter(s => {
            const scanSlug = s.repoSlug || (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').replace(/.*\//, '');
            return scanSlug === slug;
        });
        if (repoScans.length === 0) return alert('No scans found for this repository.');

        // Best scan per framework (prefer semantic, then latest)
        const bestByFw = {};
        for (const s of repoScans) {
            const fw = s.framework || '';
            if (!fw) continue;
            const isSemantic = (s.scan_depth || s.depth || '').includes('semantic');
            const existing = bestByFw[fw];
            if (!existing) { bestByFw[fw] = s; continue; }
            const existIsSemantic = (existing.scan_depth || existing.depth || '').includes('semantic');
            if (isSemantic && !existIsSemantic) { bestByFw[fw] = s; }
            else if (isSemantic === existIsSemantic) {
                if ((s.timestamp || '') > (existing.timestamp || '')) bestByFw[fw] = s;
            }
        }

        const scanEntries = Object.values(bestByFw);
        if (scanEntries.length < 2) return alert('Need scans in at least 2 frameworks for overlap report.');

        const reports = [];
        for (const s of scanEntries) {
            const full = await ScanAdapter.getWithReport(s.id);
            if (full && full.report) reports.push(full.report);
        }
        if (reports.length < 2) return alert('Could not load reports for overlap analysis.');

        const matrix = Components.buildOverlapMatrix(reports);
        const repoName = repoScans[0].repoName || slug;
        this._open(this._buildOverlapReport(repoName, slug, reports, matrix));
    },

    /** Generate a one-page board-ready executive summary. */
    async boardSummary(scanId) {
        const scan = await ScanAdapter.getWithReport(scanId);
        if (!scan || !scan.report) return alert('Report data not available.');
        this._open(this._buildBoardSummary(scan));
    },

    /** Generate and download a structured evidence binder (Markdown). */
    async evidenceBinder(scanId) {
        const scan = await ScanAdapter.getWithReport(scanId);
        if (!scan || !scan.report) return alert('Report data not available.');
        const md = this._buildEvidenceBinder(scan);
        const blob = new Blob([md], { type: 'text/markdown' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        const fw = (scan.report.framework || 'scan').replace(/[^a-zA-Z0-9]/g, '_');
        a.download = `evidence-binder-${fw}-${new Date().toISOString().slice(0, 10)}.md`;
        a.click();
        URL.revokeObjectURL(a.href);
    },

    _open(html) {
        const w = window.open('', '_blank');
        if (!w) return alert('Pop-up blocked. Please allow pop-ups for this site.');
        w.document.write(html);
        w.document.close();
    },

    // ── Single-Framework Report ───────────────────────────────────────────

    _buildReport(scan, baseline) {
        const r = scan.report;
        const fw = typeof fwLabel === 'function' ? fwLabel(r.framework) : r.framework;
        const repo = scan.repoName || scan.url || r.target || 'Unknown Repository';
        const date = new Date(r.generatedAt || scan.timestamp).toLocaleDateString('en-US', {
            year: 'numeric', month: 'long', day: 'numeric',
        });
        const depth = (r.scanDepth || scan.depth || '').replace('_', ' ');
        const s = r.summary || {};

        let secNum = 1;
        let sections = '';
        sections += this._coverPage(repo, fw, date, depth, s);
        sections += this._executiveSummary(r, s, baseline);
        secNum++;
        sections += this._keyFindings(r, secNum);
        secNum++;
        sections += this._complianceScorecard(r, secNum);
        secNum++;
        if (baseline) {
            sections += this._deltaAnalysis(r, baseline.report, secNum);
            secNum++;
        }
        sections += this._controlDetails(r, secNum);
        secNum++;
        if (r.remediations && r.remediations.length) {
            sections += this._remediationPlan(r, s, secNum);
            secNum++;
        }
        sections += this._appendix(r, scan, baseline, secNum);

        return this._wrapHtml(`Compliance Report - ${this._esc(repo)} - ${fw}`, sections);
    },

    _wrapHtml(title, body) {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>${title}</title>
${this._styles()}
</head>
<body>
${body}
</body>
</html>`;
    },

    // ── Cover ─────────────────────────────────────────────────────────────

    _coverPage(repo, fw, date, depth, s) {
        return `
        <div class="cover-page">
            <div class="cover-brand">BespokeAgile <strong>Comply</strong></div>
            <h1 class="cover-title">Compliance Assessment Report</h1>
            <div class="cover-framework">${fw}</div>
            <div class="cover-meta">
                <div class="cover-repo">${this._esc(repo)}</div>
                <div class="cover-date">${date}</div>
                <div class="cover-depth">Scan Depth: ${depth}</div>
            </div>
            <div class="cover-score-ring">
                <div class="cover-score">${Math.round(s.score || 0)}%</div>
                <div class="cover-score-label">Overall Compliance Score</div>
            </div>
            <div class="cover-footer">
                <div>This report is a self-assessment tool. It does not constitute legal certification or regulatory approval.</div>
            </div>
        </div>`;
    },

    // ── Executive Summary ─────────────────────────────────────────────────

    _executiveSummary(r, s, baseline) {
        const total = s.total || 0;
        const met = s.met || 0;
        const partial = s.partial || 0;
        const gap = s.gap || 0;
        const score = Math.round(s.score || 0);

        let deltaHtml = '';
        if (baseline && baseline.report && baseline.report.summary) {
            const bs = baseline.report.summary;
            const delta = score - Math.round(bs.score || 0);
            const sign = delta >= 0 ? '+' : '';
            deltaHtml = `<p>Compared to the ${(baseline.report.scanDepth || baseline.depth || '').replace('_', ' ')} scan,
                the compliance score has changed by <strong>${sign}${delta}%</strong>.</p>`;
        }

        const riskLevel = score >= 80 ? 'Low' : score >= 50 ? 'Moderate' : 'High';
        const riskColor = score >= 80 ? '#16a34a' : score >= 50 ? '#d97706' : '#dc2626';
        const fw = typeof fwLabel === 'function' ? fwLabel(r.framework) : r.framework;

        return `
        <div class="section page-break-before">
            <h2>1. Executive Summary</h2>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="summary-value">${score}%</div>
                    <div class="summary-label">Compliance Score</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value">${total}</div>
                    <div class="summary-label">Total Controls</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value" style="color:#16a34a">${met}</div>
                    <div class="summary-label">Controls Met</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value" style="color:#d97706">${partial}</div>
                    <div class="summary-label">Partially Met</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value" style="color:#dc2626">${gap}</div>
                    <div class="summary-label">Gaps Identified</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value" style="color:${riskColor}">${riskLevel}</div>
                    <div class="summary-label">Risk Level</div>
                </div>
            </div>
            ${deltaHtml}
            <p>This assessment evaluated <strong>${total} compliance controls</strong> within the
               <strong>${fw}</strong> framework. The analysis identified
               ${met} controls fully satisfied, ${partial} partially addressed, and ${gap}
               requiring remediation.</p>
            ${r.model ? `<p>The scan analyzed <strong>${r.model.filesScanned || 0} files</strong>
               and discovered <strong>${r.model.featuresDiscovered || 0} compliance-relevant features</strong>.</p>` : ''}
        </div>`;
    },

    // ── Key Findings (new) ────────────────────────────────────────────────

    _keyFindings(r, secNum) {
        const articles = r.articles || [];
        const gaps = [];
        const partials = [];
        for (const art of articles) {
            for (const ctrl of (art.controls || [])) {
                if (ctrl.status === 'gap') gaps.push(ctrl);
                else if (ctrl.status === 'partial') partials.push(ctrl);
            }
        }

        if (gaps.length === 0 && partials.length === 0) return '';

        let html = `
        <div class="section">
            <h2>${secNum}. Key Findings</h2>`;

        // Top gaps
        if (gaps.length > 0) {
            html += `<h3>Critical Gaps (${gaps.length})</h3>
            <table class="report-table"><thead><tr><th>Control</th><th>Requirement</th></tr></thead><tbody>`;
            gaps.slice(0, 5).forEach(c => {
                html += `<tr>
                    <td><span class="status-badge gap">GAP</span> <strong>${this._esc(c.controlId)}</strong></td>
                    <td>${this._esc((c.requirement || '').substring(0, 200))}${(c.requirement || '').length > 200 ? '...' : ''}</td>
                </tr>`;
            });
            if (gaps.length > 5) html += `<tr><td colspan="2" class="muted">...and ${gaps.length - 5} more gap controls</td></tr>`;
            html += '</tbody></table>';
        }

        // Quick wins from remediation
        const rems = r.remediations || [];
        const quickWins = rems.filter(rem => rem.effort === 'low').slice(0, 3);
        if (quickWins.length > 0) {
            html += `<h3>Top Quick Wins</h3>
            <table class="report-table"><thead><tr><th>Action</th><th class="center">Impact</th></tr></thead><tbody>`;
            quickWins.forEach(rem => {
                html += `<tr>
                    <td><strong>${this._esc(rem.controlId || '')}</strong>: ${this._esc(rem.action || rem.summary || '')}</td>
                    <td class="center met">+${(rem.score_delta || 0).toFixed(1)}%</td>
                </tr>`;
            });
            html += '</tbody></table>';
        }

        html += '</div>';
        return html;
    },

    // ── Scorecard ─────────────────────────────────────────────────────────

    _complianceScorecard(r, secNum) {
        if (!r.articles || !r.articles.length) return '';
        const rows = r.articles.map(a => {
            const total = (a.met || 0) + (a.partial || 0) + (a.gap || 0);
            const artScore = total > 0 ? Math.round(((a.met || 0) + 0.5 * (a.partial || 0)) / total * 100) : 0;
            return `<tr>
                <td>${this._esc(a.label || a.articleId)}</td>
                <td class="center">${total}</td>
                <td class="center met">${a.met || 0}</td>
                <td class="center partial">${a.partial || 0}</td>
                <td class="center gap">${a.gap || 0}</td>
                <td class="center"><strong>${artScore}%</strong></td>
            </tr>`;
        }).join('');

        return `
        <div class="section">
            <h2>${secNum}. Compliance Scorecard</h2>
            <p>Article-level breakdown of compliance posture:</p>
            <table class="report-table">
                <thead>
                    <tr>
                        <th>Article / Section</th>
                        <th class="center">Controls</th>
                        <th class="center">Met</th>
                        <th class="center">Partial</th>
                        <th class="center">Gap</th>
                        <th class="center">Score</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    },

    // ── Delta Analysis ────────────────────────────────────────────────────

    _deltaAnalysis(primary, baseline, secNum) {
        if (!primary.articles || !baseline.articles) return '';
        const baseMap = {};
        (baseline.articles || []).forEach(a => {
            (a.controls || []).forEach(c => { baseMap[c.controlId] = c.status; });
        });

        const improved = [], regressed = [], unchanged = [];
        (primary.articles || []).forEach(a => {
            (a.controls || []).forEach(c => {
                const prev = baseMap[c.controlId];
                if (!prev) return;
                const rank = { met: 3, partial: 2, gap: 1 };
                const diff = (rank[c.status] || 0) - (rank[prev] || 0);
                if (diff > 0) improved.push({ ...c, prevStatus: prev });
                else if (diff < 0) regressed.push({ ...c, prevStatus: prev });
                else unchanged.push(c);
            });
        });

        let html = `
        <div class="section page-break-before">
            <h2>${secNum}. Delta Analysis</h2>
            <p>Changes compared to the baseline ${(baseline.scanDepth || '').replace('_', ' ')} scan:</p>
            <div class="summary-grid" style="grid-template-columns:repeat(3,1fr)">
                <div class="summary-card"><div class="summary-value" style="color:#16a34a">${improved.length}</div><div class="summary-label">Improved</div></div>
                <div class="summary-card"><div class="summary-value" style="color:#dc2626">${regressed.length}</div><div class="summary-label">Regressed</div></div>
                <div class="summary-card"><div class="summary-value">${unchanged.length}</div><div class="summary-label">Unchanged</div></div>
            </div>`;

        if (improved.length) {
            html += `<h3>Improved Controls</h3><table class="report-table"><thead><tr><th>Control</th><th class="center">Previous</th><th class="center">Current</th></tr></thead><tbody>`;
            improved.forEach(c => {
                html += `<tr><td>${this._esc(c.controlId)}</td><td class="center ${c.prevStatus}">${c.prevStatus}</td><td class="center ${c.status}">${c.status}</td></tr>`;
            });
            html += '</tbody></table>';
        }
        if (regressed.length) {
            html += `<h3>Regressed Controls</h3><table class="report-table"><thead><tr><th>Control</th><th class="center">Previous</th><th class="center">Current</th></tr></thead><tbody>`;
            regressed.forEach(c => {
                html += `<tr><td>${this._esc(c.controlId)}</td><td class="center ${c.prevStatus}">${c.prevStatus}</td><td class="center ${c.status}">${c.status}</td></tr>`;
            });
            html += '</tbody></table>';
        }
        html += '</div>';
        return html;
    },

    // ── Control Details (enriched with semantic + evidence quality) ──────

    _controlDetails(r, secNum) {
        if (!r.articles || !r.articles.length) return '';
        let html = `<div class="section page-break-before"><h2>${secNum}. Control Details</h2>`;

        r.articles.forEach(article => {
            html += `<h3>${this._esc(article.label || article.articleId)}</h3>`;
            (article.controls || []).forEach(ctrl => {
                const statusClass = ctrl.status || 'gap';
                html += `
                <div class="control-block">
                    <div class="control-header">
                        <span class="status-badge ${statusClass}">${statusClass.toUpperCase()}</span>
                        <strong>${this._esc(ctrl.controlId)}</strong>
                    </div>
                    <div class="control-requirement">${this._esc(ctrl.requirement || '')}</div>`;

                // Semantic analysis (codebase-specific insight from LLM)
                if (ctrl.semanticAnalysis) {
                    html += `<div class="control-analysis">
                        <strong>Codebase Analysis:</strong>
                        <div>${this._esc(ctrl.semanticAnalysis)}</div>
                    </div>`;
                }

                // Evidence with quality indicator
                if (ctrl.evidence && ctrl.evidence.length > 0) {
                    const evCount = ctrl.evidence.length;
                    const quality = evCount >= 3 ? 'Strong' : evCount >= 2 ? 'Moderate' : 'Weak';
                    const qColor = evCount >= 3 ? '#16a34a' : evCount >= 2 ? '#d97706' : '#dc2626';
                    html += `<div class="control-evidence">
                        <strong>Evidence Found (${evCount})</strong>
                        <span class="evidence-quality-badge" style="background:${qColor}15;color:${qColor}">${quality}</span>
                        <ul>`;
                    ctrl.evidence.forEach(e => {
                        const text = typeof e === 'string' ? e : (e.description || e.file || JSON.stringify(e));
                        html += `<li>${this._esc(text)}</li>`;
                    });
                    html += '</ul></div>';
                }

                // Gaps identified
                if (ctrl.gaps && ctrl.gaps.length > 0) {
                    html += `<div class="control-gaps"><strong>Gaps Identified:</strong><ul>`;
                    ctrl.gaps.forEach(g => {
                        const text = typeof g === 'string' ? g : (g.description || JSON.stringify(g));
                        html += `<li>${this._esc(text)}</li>`;
                    });
                    html += '</ul></div>';
                }

                if (ctrl.recommendation) {
                    html += `<div class="control-recommendation"><strong>Recommendation:</strong> ${this._esc(ctrl.recommendation)}</div>`;
                }
                html += '</div>';
            });
        });

        html += '</div>';
        return html;
    },

    // ── Remediation Plan (with phases) ────────────────────────────────────

    _remediationPlan(r, s, secNum) {
        const rems = r.remediations || [];
        if (!rems.length) return '';
        const quick = rems.filter(r => r.effort === 'low');
        const medium = rems.filter(r => r.effort === 'medium');
        const major = rems.filter(r => r.effort === 'high');
        const projected = rems.length > 0 ? Math.round(rems[rems.length - 1].projected_score_after || s.score || 0) : 0;
        const currentScore = Math.round(s.score || 0);

        let html = `
        <div class="section page-break-before">
            <h2>${secNum}. Remediation Plan</h2>
            <p>Prioritized actions ranked by compliance impact per unit of effort.</p>
            <div class="summary-grid" style="grid-template-columns:repeat(4,1fr)">
                <div class="summary-card"><div class="summary-value">${quick.length}</div><div class="summary-label">Quick Wins</div></div>
                <div class="summary-card"><div class="summary-value">${medium.length}</div><div class="summary-label">Medium Effort</div></div>
                <div class="summary-card"><div class="summary-value">${major.length}</div><div class="summary-label">Major Work</div></div>
                <div class="summary-card"><div class="summary-value" style="color:#16a34a">${projected}%</div><div class="summary-label">Projected Score</div></div>
            </div>`;

        // Score progression
        html += `<h3>Score Progression</h3>
        <div class="score-progression">`;
        let runScore = currentScore;
        const phases = [
            { label: 'Phase 1: Quick Wins', items: quick, time: '1-2 weeks' },
            { label: 'Phase 2: Medium Effort', items: medium, time: '2-4 weeks' },
            { label: 'Phase 3: Major Work', items: major, time: '1-3 months' },
        ];
        phases.forEach(phase => {
            if (phase.items.length === 0) return;
            const phaseEnd = phase.items.length > 0
                ? Math.round(phase.items[phase.items.length - 1].projected_score_after || runScore)
                : runScore;
            const phaseDelta = phaseEnd - runScore;
            html += `<div class="phase-bar">
                <div class="phase-bar-label">${phase.label} <span class="muted">(${phase.time})</span></div>
                <div class="phase-bar-track">
                    <div class="phase-bar-fill" style="width:${phaseEnd}%"></div>
                    <span class="phase-bar-text">${runScore}% → ${phaseEnd}% (+${phaseDelta}%)</span>
                </div>
            </div>`;
            runScore = phaseEnd;
        });
        html += '</div>';

        // Detailed tables
        const renderGroup = (title, items) => {
            if (!items.length) return '';
            let g = `<h3>${title}</h3><table class="report-table"><thead><tr>
                <th>#</th><th>Control</th><th>Action</th><th class="center">Score Impact</th><th class="center">Projected</th>
            </tr></thead><tbody>`;
            items.forEach((rem, i) => {
                g += `<tr>
                    <td class="center">${rem.rank || i + 1}</td>
                    <td><strong>${this._esc(rem.controlId || '')}</strong><br><span class="muted">${this._esc(rem.summary || '')}</span></td>
                    <td>${this._esc(rem.action || '')}</td>
                    <td class="center met">+${(rem.score_delta || 0).toFixed(1)}%</td>
                    <td class="center">${Math.round(rem.projected_score_after || 0)}%</td>
                </tr>`;
            });
            g += '</tbody></table>';
            return g;
        };

        html += renderGroup('Quick Wins (Low Effort)', quick);
        html += renderGroup('Medium Effort', medium);
        html += renderGroup('Major Work (High Effort)', major);
        html += '</div>';
        return html;
    },

    // ── Appendix ──────────────────────────────────────────────────────────

    _appendix(r, scan, baseline, secNum) {
        let html = `
        <div class="section page-break-before">
            <h2>${secNum}. Appendix</h2>
            <h3>A. Scan Metadata</h3>
            <table class="report-table">
                <tbody>
                    <tr><td><strong>Repository</strong></td><td>${this._esc(scan.url || r.target || '')}</td></tr>
                    <tr><td><strong>Framework</strong></td><td>${typeof fwLabel === 'function' ? fwLabel(r.framework) : r.framework}</td></tr>
                    <tr><td><strong>Scan Depth</strong></td><td>${(r.scanDepth || scan.depth || '').replace('_', ' ')}</td></tr>
                    <tr><td><strong>Generated</strong></td><td>${r.generatedAt || scan.timestamp || ''}</td></tr>
                    ${r.commitSha ? `<tr><td><strong>Commit SHA</strong></td><td><code>${r.commitSha}</code></td></tr>` : ''}
                    ${r.model ? `<tr><td><strong>Files Scanned</strong></td><td>${r.model.filesScanned || 0}</td></tr>
                    <tr><td><strong>Features Discovered</strong></td><td>${r.model.featuresDiscovered || 0}</td></tr>` : ''}
                </tbody>
            </table>`;

        if (baseline) {
            html += `
            <h3>B. Baseline Scan</h3>
            <table class="report-table">
                <tbody>
                    <tr><td><strong>Scan Depth</strong></td><td>${(baseline.report.scanDepth || baseline.depth || '').replace('_', ' ')}</td></tr>
                    <tr><td><strong>Generated</strong></td><td>${baseline.report.generatedAt || baseline.timestamp || ''}</td></tr>
                    <tr><td><strong>Score</strong></td><td>${Math.round((baseline.report.summary || {}).score || 0)}%</td></tr>
                </tbody>
            </table>`;
        }

        html += `
            <h3>${baseline ? 'C' : 'B'}. Methodology</h3>
            <p>This compliance assessment was performed by BespokeAgile Comply using automated analysis of the target codebase.
               The assessment evaluates compliance controls against evidence found in code, configuration, documentation, and project structure.</p>
            <ul>
                <li><strong>Structure scan:</strong> Pattern-matching analysis of file names, imports, function signatures, and configuration files. Fast, deterministic, and free.</li>
                <li><strong>Semantic scan:</strong> LLM-powered analysis that reads code intent and evaluates whether implementations satisfy compliance requirements in context.</li>
            </ul>
            <p>Scoring formula: <code>(met + 0.5 * partial) / total * 100</code></p>

            <h3>${baseline ? 'D' : 'C'}. Disclaimer</h3>
            <p>This report is a self-assessment tool generated by automated analysis. It does not constitute legal advice,
               regulatory certification, or audit attestation. Organizations should consult qualified legal and compliance
               professionals for formal compliance determinations. The accuracy of this assessment depends on the completeness
               and representativeness of the scanned codebase.</p>
        </div>`;

        return html;
    },

    // ── Multi-Framework Overlap Report ────────────────────────────────────

    _buildOverlapReport(repoName, slug, reports, matrix) {
        const { capabilities, frameworks, fwScores, efficiency, scanOrder } = matrix;
        const fwCount = frameworks.length;
        const sharedCount = capabilities.filter(c => c.frameworkCount > 1).length;
        const totalCaps = capabilities.length;
        const date = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

        let secNum = 1;
        let sections = '';

        // Cover
        sections += `
        <div class="cover-page">
            <div class="cover-brand">BespokeAgile <strong>Comply</strong></div>
            <h1 class="cover-title">Cross-Framework Compliance Report</h1>
            <div class="cover-framework">${fwCount} Frameworks</div>
            <div class="cover-meta">
                <div class="cover-repo">${this._esc(repoName)}</div>
                <div class="cover-date">${date}</div>
                <div class="cover-depth">${totalCaps} capabilities, ${sharedCount} shared</div>
            </div>
            <div class="cover-score-ring">
                <div class="cover-score">${Math.round(efficiency.efficiencyPct || 0)}%</div>
                <div class="cover-score-label">Effort Reduction</div>
            </div>
            <div class="cover-footer">
                <div>This report is a self-assessment tool. It does not constitute legal certification or regulatory approval.</div>
            </div>
        </div>`;

        // 1. Executive summary
        sections += `
        <div class="section page-break-before">
            <h2>1. Executive Summary</h2>
            <p>This report analyzes compliance posture across <strong>${fwCount} regulatory frameworks</strong>
               for the <strong>${this._esc(repoName)}</strong> repository.</p>
            <div class="summary-grid" style="grid-template-columns:repeat(${Math.min(fwCount + 2, 6)},1fr)">`;
        frameworks.forEach(fw => {
            const s = fwScores[fw] || {};
            const score = Math.round(s.score || 0);
            const color = score >= 70 ? '#16a34a' : score >= 40 ? '#d97706' : '#dc2626';
            sections += `<div class="summary-card">
                <div class="summary-value" style="color:${color}">${score}%</div>
                <div class="summary-label">${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</div>
            </div>`;
        });
        sections += `
                <div class="summary-card">
                    <div class="summary-value">${sharedCount}</div>
                    <div class="summary-label">Shared Capabilities</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value" style="color:#16a34a">${Math.round(efficiency.efficiencyPct || 0)}%</div>
                    <div class="summary-label">Effort Reduction</div>
                </div>
            </div>
            <p>Of ${totalCaps} total compliance capabilities, <strong>${sharedCount} are shared</strong> across
               2 or more frameworks. Addressing shared capabilities provides
               <strong>${Math.round(efficiency.efficiencyPct || 0)}% effort reduction</strong> compared to treating
               each framework independently.</p>
        </div>`;
        secNum++;

        // 2. Framework scorecards
        sections += `
        <div class="section">
            <h2>${secNum}. Framework Scorecards</h2>`;
        frameworks.forEach(fw => {
            const s = fwScores[fw] || {};
            const score = Math.round(s.score || 0);
            const depthLabel = (s.depth || '').includes('semantic') ? 'Semantic' : 'Structure';
            sections += `
            <div class="fw-scorecard">
                <div class="fw-scorecard-header">
                    <strong>${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</strong>
                    <span class="muted">${depthLabel} scan</span>
                </div>
                <table class="report-table">
                    <tbody>
                        <tr><td>Score</td><td class="center"><strong>${score}%</strong></td></tr>
                        <tr><td>Controls Met</td><td class="center met">${s.met || 0}</td></tr>
                        <tr><td>Partially Met</td><td class="center partial">${s.partial || 0}</td></tr>
                        <tr><td>Gaps</td><td class="center gap">${s.gap || 0}</td></tr>
                    </tbody>
                </table>
            </div>`;
        });
        sections += '</div>';
        secNum++;

        // 3. Recommended scan order
        if (scanOrder && scanOrder.length > 0) {
            sections += `
            <div class="section">
                <h2>${secNum}. Recommended Implementation Order</h2>
                <p>Maximize coverage efficiency by addressing frameworks in the order that covers the most new capabilities.</p>
                <table class="report-table">
                    <thead><tr><th>Step</th><th>Framework</th><th class="center">New Capabilities</th><th class="center">Cumulative Coverage</th></tr></thead>
                    <tbody>`;
            scanOrder.forEach((step, i) => {
                const pct = totalCaps > 0 ? Math.round(step.cumulativeCovered / totalCaps * 100) : 0;
                sections += `<tr>
                    <td class="center">${i + 1}</td>
                    <td><strong>${typeof fwLabel === 'function' ? fwLabel(step.framework) : step.framework}</strong></td>
                    <td class="center">${step.newCovered}</td>
                    <td class="center">${step.cumulativeCovered}/${totalCaps} (${pct}%)</td>
                </tr>`;
            });
            sections += '</tbody></table></div>';
            secNum++;
        }

        // 4. Capability overlap matrix
        sections += `
        <div class="section page-break-before">
            <h2>${secNum}. Capability Overlap Matrix</h2>
            <p>Each row is a compliance capability. Shared capabilities (2+ frameworks) are highlighted.</p>
            <table class="report-table">
                <thead><tr><th>Capability</th>`;
        frameworks.forEach(fw => {
            sections += `<th class="center">${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</th>`;
        });
        sections += `<th class="center">Shared</th></tr></thead><tbody>`;

        capabilities.forEach(cap => {
            const isShared = cap.frameworkCount > 1;
            const rowStyle = isShared ? ' style="background:#f0f7ff"' : '';
            sections += `<tr${rowStyle}><td>${this._esc(cap.label || cap.evidence_fn)}</td>`;
            frameworks.forEach(fw => {
                const entry = cap.frameworks[fw];
                if (!entry) {
                    sections += '<td class="center">-</td>';
                } else {
                    const st = entry.status || 'gap';
                    sections += `<td class="center ${st}">${this._esc(entry.controlId || st)}</td>`;
                }
            });
            sections += `<td class="center">${isShared ? cap.frameworkCount + ' fw' : '-'}</td></tr>`;
        });
        sections += '</tbody></table></div>';
        secNum++;

        // 5. Unified remediation
        const allRems = [];
        reports.forEach(report => {
            const fw = report.framework || '';
            (report.remediations || []).forEach(rem => {
                allRems.push({ ...rem, framework: fw });
            });
        });

        if (allRems.length > 0) {
            sections += `
            <div class="section page-break-before">
                <h2>${secNum}. Unified Remediation Plan</h2>
                <p>All remediation actions across frameworks in one view. Items addressing shared capabilities provide the most value.</p>
                <table class="report-table">
                    <thead><tr><th>Framework</th><th>Control</th><th>Action</th><th class="center">Effort</th><th class="center">Impact</th></tr></thead>
                    <tbody>`;
            allRems.sort((a, b) => (b.score_delta || 0) - (a.score_delta || 0));
            allRems.forEach(rem => {
                const effortLabel = rem.effort === 'low' ? 'Quick' : rem.effort === 'medium' ? 'Medium' : 'Major';
                sections += `<tr>
                    <td>${typeof fwLabel === 'function' ? fwLabel(rem.framework) : rem.framework}</td>
                    <td><strong>${this._esc(rem.controlId || '')}</strong></td>
                    <td>${this._esc(rem.action || rem.summary || '')}</td>
                    <td class="center">${effortLabel}</td>
                    <td class="center met">+${(rem.score_delta || 0).toFixed(1)}%</td>
                </tr>`;
            });
            sections += '</tbody></table></div>';
            secNum++;
        }

        // 6. Gap analysis
        const gapCaps = capabilities.filter(c => {
            return Object.values(c.frameworks).some(f => f.status === 'gap' || f.status === 'partial');
        }).sort((a, b) => b.frameworkCount - a.frameworkCount);

        if (gapCaps.length > 0) {
            sections += `
            <div class="section page-break-before">
                <h2>${secNum}. Cross-Framework Gap Analysis</h2>
                <p>Capabilities with gaps or partial compliance, sorted by cross-framework impact.</p>
                <table class="report-table">
                    <thead><tr><th>Capability</th><th class="center">Frameworks</th><th>Status by Framework</th></tr></thead>
                    <tbody>`;
            gapCaps.forEach(cap => {
                const statuses = Object.entries(cap.frameworks).map(([fw, entry]) => {
                    const fwName = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
                    return `<span class="${entry.status || 'gap'}">${fwName}: ${entry.status || 'gap'}</span>`;
                }).join(', ');
                sections += `<tr>
                    <td><strong>${this._esc(cap.label || cap.evidence_fn)}</strong></td>
                    <td class="center">${cap.frameworkCount}</td>
                    <td>${statuses}</td>
                </tr>`;
            });
            sections += '</tbody></table></div>';
            secNum++;
        }

        // Appendix
        sections += `
        <div class="section page-break-before">
            <h2>${secNum}. Appendix</h2>
            <h3>A. Methodology</h3>
            <p>This cross-framework report aggregates individual compliance assessments performed by BespokeAgile Comply.
               Overlap analysis identifies shared compliance capabilities across frameworks using evidence function mapping.</p>
            <ul>
                <li><strong>Capability mapping:</strong> Controls across frameworks are linked by their underlying evidence function (the code pattern that satisfies the requirement).</li>
                <li><strong>Effort reduction:</strong> Calculated as <code>(1 - unique_capabilities / total_controls_naive) * 100</code></li>
                <li><strong>Scan order:</strong> Greedy set-cover algorithm that picks the framework covering the most uncovered capabilities at each step.</li>
            </ul>
            <h3>B. Disclaimer</h3>
            <p>This report is a self-assessment tool generated by automated analysis. It does not constitute legal advice,
               regulatory certification, or audit attestation. Organizations should consult qualified legal and compliance
               professionals for formal compliance determinations.</p>
        </div>`;

        return this._wrapHtml(`Cross-Framework Report - ${this._esc(repoName)}`, sections);
    },

    // ── Board Summary (one-page) ──────────────────────────────────────────

    _buildBoardSummary(scan) {
        const r = scan.report;
        const fw = typeof fwLabel === 'function' ? fwLabel(r.framework) : r.framework;
        const repo = scan.repoName || scan.url || r.target || 'Unknown Repository';
        const date = new Date(r.generatedAt || scan.timestamp).toLocaleDateString('en-US', {
            year: 'numeric', month: 'long', day: 'numeric',
        });
        const s = r.summary || {};
        const score = Math.round(s.score || 0);
        const riskLevel = score >= 80 ? 'Low' : score >= 50 ? 'Moderate' : 'High';
        const riskColor = score >= 80 ? '#16a34a' : score >= 50 ? '#d97706' : '#dc2626';

        // Top 3 gaps
        const gaps = [];
        (r.articles || []).forEach(a => {
            (a.controls || []).forEach(c => {
                if (c.status === 'gap') gaps.push(c);
            });
        });

        // Top 3 quick wins
        const quickWins = (r.remediations || []).filter(rem => rem.effort === 'low').slice(0, 3);
        const projected = (r.remediations || []).length > 0
            ? Math.round(r.remediations[r.remediations.length - 1].projected_score_after || score)
            : score;

        let sections = `
        <div class="board-summary">
            <div class="board-header">
                <div class="cover-brand">BespokeAgile <strong>Comply</strong></div>
                <h1 class="board-title">Compliance Posture Summary</h1>
                <div class="board-meta">${this._esc(repo)} | ${fw} | ${date}</div>
            </div>

            <div class="board-grid">
                <div class="board-score-section">
                    <div class="cover-score-ring" style="margin:0 auto 12px">
                        <div class="cover-score">${score}%</div>
                        <div class="cover-score-label">Compliance</div>
                    </div>
                    <div class="board-risk" style="color:${riskColor}">Risk: ${riskLevel}</div>
                    <div class="board-counts">
                        <span class="met">${s.met || 0} met</span> |
                        <span class="partial">${s.partial || 0} partial</span> |
                        <span class="gap">${s.gap || 0} gap</span>
                    </div>
                    ${projected !== score ? `<div class="board-projected">Projected after remediation: <strong>${projected}%</strong></div>` : ''}
                </div>

                <div class="board-findings">
                    <h3>Critical Gaps</h3>
                    <ul>
                        ${gaps.slice(0, 3).map(g => `<li><strong>${this._esc(g.controlId)}</strong>: ${this._esc((g.requirement || '').substring(0, 100))}${(g.requirement || '').length > 100 ? '...' : ''}</li>`).join('')}
                        ${gaps.length > 3 ? `<li class="muted">+${gaps.length - 3} more</li>` : ''}
                        ${gaps.length === 0 ? '<li class="met">No critical gaps identified</li>' : ''}
                    </ul>

                    <h3>Recommended Actions</h3>
                    <ul>
                        ${quickWins.map(w => `<li><strong>${this._esc(w.controlId || '')}</strong>: ${this._esc(w.action || w.summary || '')} <span class="met">(+${(w.score_delta || 0).toFixed(1)}%)</span></li>`).join('')}
                        ${quickWins.length === 0 ? '<li class="muted">No quick wins available</li>' : ''}
                    </ul>
                </div>
            </div>

            <div class="board-footer">
                <p>This is a self-assessment summary generated by automated analysis. It does not constitute regulatory certification.</p>
            </div>
        </div>`;

        return this._wrapHtml(`Board Summary - ${this._esc(repo)} - ${fw}`, sections);
    },

    // ── Evidence Binder (Markdown) ────────────────────────────────────────

    _buildEvidenceBinder(scan) {
        const r = scan.report;
        const fw = typeof fwLabel === 'function' ? fwLabel(r.framework) : r.framework;
        const repo = scan.repoName || scan.url || r.target || 'Unknown Repository';
        const s = r.summary || {};
        const date = r.generatedAt || scan.timestamp || new Date().toISOString();

        let md = `# Evidence Binder: ${fw}\n\n`;
        md += `**Repository:** ${repo}\n`;
        md += `**Date:** ${date}\n`;
        md += `**Score:** ${Math.round(s.score || 0)}%\n`;
        md += `**Controls:** ${s.total || 0} total (${s.met || 0} met, ${s.partial || 0} partial, ${s.gap || 0} gap)\n\n`;
        md += `---\n\n`;

        (r.articles || []).forEach(article => {
            md += `## ${article.label || article.articleId}\n\n`;

            (article.controls || []).forEach(ctrl => {
                const status = (ctrl.status || 'gap').toUpperCase();
                md += `### ${ctrl.controlId} [${status}]\n\n`;

                if (ctrl.requirement) {
                    md += `**Requirement:** ${ctrl.requirement}\n\n`;
                }

                if (ctrl.semanticAnalysis) {
                    md += `**Codebase Analysis:**\n${ctrl.semanticAnalysis}\n\n`;
                }

                if (ctrl.evidence && ctrl.evidence.length > 0) {
                    md += `**Evidence (${ctrl.evidence.length}):**\n`;
                    ctrl.evidence.forEach(e => {
                        const text = typeof e === 'string' ? e : (e.description || e.file || JSON.stringify(e));
                        md += `- ${text}\n`;
                    });
                    md += '\n';
                }

                if (ctrl.gaps && ctrl.gaps.length > 0) {
                    md += `**Gaps:**\n`;
                    ctrl.gaps.forEach(g => {
                        const text = typeof g === 'string' ? g : (g.description || JSON.stringify(g));
                        md += `- ${text}\n`;
                    });
                    md += '\n';
                }

                if (ctrl.recommendation) {
                    md += `**Recommendation:** ${ctrl.recommendation}\n\n`;
                }

                md += `---\n\n`;
            });
        });

        md += `## Methodology\n\n`;
        md += `This evidence binder was generated by BespokeAgile Comply.\n`;
        md += `- **Structure scan:** Pattern-matching analysis of file names, imports, and function signatures.\n`;
        md += `- **Semantic scan:** LLM-powered analysis that reads code intent and evaluates compliance.\n`;
        md += `- **Scoring:** (met + 0.5 * partial) / total * 100\n\n`;
        md += `*This is a self-assessment tool. It does not constitute legal certification.*\n`;

        return md;
    },

    // ── Styles ────────────────────────────────────────────────────────────

    _styles() {
        return `<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: #1a1a2e; line-height: 1.6; background: #fff; }
code { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.9em; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }
.muted { color: #64748b; font-size: 0.85em; }

/* Cover page */
.cover-page { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 60px 40px; }
.cover-brand { font-size: 14px; letter-spacing: 2px; text-transform: uppercase; color: #64748b; margin-bottom: 24px; }
.cover-title { font-size: 36px; font-weight: 300; margin-bottom: 12px; color: #1a1a2e; }
.cover-framework { font-size: 24px; color: #6366f1; font-weight: 600; margin-bottom: 48px; }
.cover-meta { font-size: 15px; color: #475569; line-height: 2; margin-bottom: 48px; }
.cover-repo { font-size: 18px; font-weight: 500; color: #1a1a2e; }
.cover-score-ring { width: 160px; height: 160px; border-radius: 50%; border: 6px solid #6366f1; display: flex; flex-direction: column; align-items: center; justify-content: center; margin: 0 auto 48px; }
.cover-score { font-size: 42px; font-weight: 700; color: #6366f1; }
.cover-score-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
.cover-footer { font-size: 11px; color: #94a3b8; max-width: 500px; margin-top: auto; }

/* Sections */
.section { padding: 40px 60px; max-width: 900px; margin: 0 auto; }
.section h2 { font-size: 22px; font-weight: 600; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; color: #1a1a2e; }
.section h3 { font-size: 16px; font-weight: 600; margin: 24px 0 12px; color: #334155; }
.section p { margin-bottom: 12px; font-size: 14px; color: #475569; }
.section ul { margin: 8px 0 16px 24px; font-size: 14px; color: #475569; }
.section li { margin-bottom: 6px; }

/* Summary grid */
.summary-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 24px; }
.summary-card { text-align: center; padding: 16px 8px; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; }
.summary-value { font-size: 28px; font-weight: 700; color: #1a1a2e; }
.summary-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }

/* Tables */
.report-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13px; }
.report-table th { background: #f1f5f9; padding: 10px 12px; text-align: left; font-weight: 600; color: #334155; border-bottom: 2px solid #e2e8f0; }
.report-table td { padding: 8px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
.report-table tr:hover { background: #fafbfd; }
.center { text-align: center; }
.met { color: #16a34a; }
.partial { color: #d97706; }
.gap { color: #dc2626; }

/* Control blocks */
.control-block { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.control-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.control-requirement { font-size: 13px; color: #475569; margin-bottom: 10px; }
.control-evidence, .control-recommendation, .control-gaps { font-size: 13px; color: #475569; margin-top: 8px; }
.control-evidence ul, .control-gaps ul { margin: 4px 0 0 20px; }
.control-evidence li, .control-gaps li { font-size: 12px; }
.control-analysis { font-size: 13px; color: #475569; margin: 8px 0; padding: 8px 12px; border-left: 3px solid #6366f1; background: #f8f9ff; }
.control-analysis div { margin-top: 4px; }
.status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; letter-spacing: 0.5px; }
.status-badge.met { background: #dcfce7; color: #166534; }
.status-badge.partial { background: #fef3c7; color: #92400e; }
.status-badge.gap { background: #fee2e2; color: #991b1b; }

/* Evidence quality badge */
.evidence-quality-badge { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 600; margin-left: 6px; vertical-align: middle; }

/* Score progression bars */
.score-progression { margin-bottom: 24px; }
.phase-bar { margin-bottom: 12px; }
.phase-bar-label { font-size: 14px; font-weight: 600; color: #334155; margin-bottom: 4px; }
.phase-bar-track { position: relative; height: 28px; background: #f1f5f9; border-radius: 6px; overflow: hidden; }
.phase-bar-fill { position: absolute; top: 0; left: 0; height: 100%; background: linear-gradient(90deg, #6366f1, #818cf8); border-radius: 6px; }
.phase-bar-text { position: absolute; top: 0; left: 0; right: 0; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: #1a1a2e; }

/* Framework scorecard */
.fw-scorecard { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.fw-scorecard-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 16px; }

/* Board summary */
.board-summary { padding: 40px 60px; max-width: 900px; margin: 0 auto; }
.board-header { text-align: center; margin-bottom: 32px; }
.board-title { font-size: 28px; font-weight: 300; margin: 8px 0; }
.board-meta { font-size: 14px; color: #64748b; }
.board-grid { display: grid; grid-template-columns: 1fr 2fr; gap: 32px; margin-bottom: 32px; }
.board-score-section { text-align: center; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; }
.board-risk { font-size: 18px; font-weight: 700; margin: 8px 0; }
.board-counts { font-size: 14px; margin: 8px 0; }
.board-projected { font-size: 13px; color: #64748b; margin-top: 12px; }
.board-findings h3 { font-size: 16px; font-weight: 600; margin: 0 0 8px; color: #334155; }
.board-findings ul { margin: 0 0 16px 20px; font-size: 13px; }
.board-findings li { margin-bottom: 6px; color: #475569; }
.board-footer { text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 16px; }

/* Print */
@media print {
    body { font-size: 11px; }
    .cover-page { min-height: auto; page-break-after: always; padding: 80px 40px; }
    .page-break-before { page-break-before: always; }
    .section { padding: 20px 40px; }
    .summary-card { border: 1px solid #ccc; }
    .control-block { break-inside: avoid; }
    .report-table tr { break-inside: avoid; }
    .board-summary { padding: 20px 40px; }
    .board-grid { gap: 16px; }
}
</style>`;
    },

    _esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    },
};
