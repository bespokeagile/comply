/* Diff view — side-by-side comparison of two scans.
   In demo mode, computes diff client-side from ScanAdapter.
   Special "depth compare" mode highlights structure vs semantic differences. */
const DiffView = {
    async render(params) {
        const app = document.getElementById('app');
        const id1 = params[0];
        const id2 = params[1];

        if (!id1 || !id2) {
            app.innerHTML = '<div class="alert alert-error">Two scan IDs required for comparison. Navigate from History view.</div>';
            return;
        }

        app.innerHTML = '<div class="loading"><span class="spinner"></span> Computing diff...</div>';

        // Try client-side diff from ScanAdapter (covers both catalog and user scans)
        const s1 = ScanAdapter.get(id1);
        const s2 = ScanAdapter.get(id2);
        if (s1 && s2) {
            const r1 = s1.report;
            const r2 = s2.report;
            const isDepthCompare = (r1.scanDepth || '') !== (r2.scanDepth || '');
            if (isDepthCompare) {
                this._renderDepthCompare(r1, r2, id1, id2);
            } else {
                this._renderLocalDiff(r1, r2, id1, id2);
            }
            return;
        }

        // Fall back to server-side diff
        try {
            const diff = await complyApi.getDiff(id1, id2);
            this._renderServerDiff(diff, id1, id2);
        } catch (e) {
            app.innerHTML = `<div class="alert alert-error">Failed to compute diff: ${e.message}</div>`;
        }
    },

    /** Build a control map from a report: { controlId -> ctrl } */
    _controlMap(report) {
        const map = {};
        for (const art of (report.articles || [])) {
            for (const c of (art.controls || [])) {
                map[c.controlId] = { ...c, articleId: art.articleId, articleLabel: art.label };
            }
        }
        return map;
    },

    /** Compute local diff between two reports. */
    _computeLocalDiff(r1, r2) {
        const map1 = this._controlMap(r1);
        const map2 = this._controlMap(r2);
        const allIds = [...new Set([...Object.keys(map1), ...Object.keys(map2)])].sort();

        const improved = [];
        const regressed = [];
        const unchanged = [];
        const statusRank = { met: 3, partial: 2, gap: 1 };

        for (const id of allIds) {
            const c1 = map1[id];
            const c2 = map2[id];
            const s1 = c1 ? (statusRank[c1.status] || 0) : 0;
            const s2 = c2 ? (statusRank[c2.status] || 0) : 0;

            const entry = {
                controlId: id,
                requirement: (c2 || c1 || {}).requirement || '',
                articleId: (c2 || c1 || {}).articleId || '',
                articleLabel: (c2 || c1 || {}).articleLabel || '',
                oldStatus: c1 ? c1.status : 'n/a',
                newStatus: c2 ? c2.status : 'n/a',
                oldEvidence: c1 ? (c1.evidence || []) : [],
                newEvidence: c2 ? (c2.evidence || []) : [],
                semanticAnalysis: (c2 || {}).semanticAnalysis || '',
            };

            if (s2 > s1) improved.push(entry);
            else if (s2 < s1) regressed.push(entry);
            else unchanged.push(entry);
        }

        const score1 = (r1.summary || {}).score || 0;
        const score2 = (r2.summary || {}).score || 0;

        return { improved, regressed, unchanged, score1, score2, delta: score2 - score1 };
    },

    /** Render depth compare (structure vs semantic) — the primary demo value proposition. */
    _renderDepthCompare(r1, r2, rawId1, rawId2) {
        const app = document.getElementById('app');

        // Ensure r1 is structure, r2 is semantic
        const isR1Structure = (r1.scanDepth || '').includes('structure');
        const structReport = isR1Structure ? r1 : r2;
        const semanticReport = isR1Structure ? r2 : r1;
        const structId = isR1Structure ? rawId1 : rawId2;
        const semId = isR1Structure ? rawId2 : rawId1;

        const diff = this._computeLocalDiff(structReport, semanticReport);
        const fw = semanticReport.framework || structReport.framework || '';
        const repo = (semanticReport.target || structReport.target || '').replace(/.*\//, '');

        // Check if both scans used the same commit
        const structCommit = (structReport.commitSha || '').substring(0, 8);
        const semCommit = (semanticReport.commitSha || '').substring(0, 8);
        const commitMismatch = structCommit && semCommit && structCommit !== semCommit;

        const repoTarget = semanticReport.target || structReport.target || '';

        let html = `
        <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
            <div>
                <h2>Compare Scan Depths: ${fwLabel(fw)}</h2>
                <p>${repo} — See what the deeper scan uncovered beyond pattern matching</p>
            </div>
            ${repoTarget ? `<a href="#/scan?repo=${encodeURIComponent(repoTarget)}&framework=${encodeURIComponent(fw)}&depth=semantic" class="btn btn-secondary btn-sm" style="flex-shrink:0">Rescan</a>` : ''}
        </div>

        ${commitMismatch ? `
        <div class="alert alert-warn" style="margin-bottom:16px;font-size:13px">
            These scans were run against different commits
            (<code>${structCommit}</code> vs <code>${semCommit}</code>).
            Score differences may partly reflect code changes, not just scan depth.
        </div>` : ''}

        ${Components.renderCompareScoreHeader({
            score1: diff.score1, score2: diff.score2,
            id1: structId, id2: semId,
            label1: 'Quick Scan', label2: 'Deep Scan',
            class1: 'structure', class2: 'semantic',
            delta: diff.delta,
        })}`;

        // Zero-delta special case: show a clear, non-broken message
        if (diff.improved.length === 0 && diff.regressed.length === 0) {
            html += `
            <div class="card" style="margin-bottom:16px">
                <div class="card-header">Semantic Analysis Confirmed</div>
                <p style="font-size:14px;color:var(--text-secondary);line-height:1.7;margin-bottom:12px">
                    The AI semantic scan confirmed all ${diff.unchanged.length} control findings from the structure scan.
                    No additional compliance evidence was found for this codebase.
                </p>
                <p style="font-size:13px;color:var(--text-muted);line-height:1.6">
                    This typically means the codebase's compliance posture is clearly expressed in its file structure
                    and naming conventions. The semantic scan adds confidence that pattern matching didn't miss anything.
                    Click the score tiles above to view the detailed findings from each scan.
                </p>
            </div>`;

            if (diff.unchanged.length > 0) {
                html += `
                <div class="accordion-item" id="compare-unchanged">
                    <div class="accordion-header" onclick="Components.toggleAccordion('compare-unchanged')">
                        <span>All Controls (${diff.unchanged.length})</span>
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
        } else {
            // Normal case with differences
            html += `
            <div class="card" style="margin-bottom:16px">
                <div style="display:flex;gap:24px;justify-content:center;padding:8px 0;font-size:14px">
                    <span style="color:var(--green)"><strong>${diff.improved.length}</strong> controls improved</span>
                    <span style="color:var(--text-muted)"><strong>${diff.unchanged.length}</strong> unchanged</span>
                    ${diff.regressed.length > 0
                        ? `<span style="color:var(--red)"><strong>${diff.regressed.length}</strong> regressed</span>`
                        : ''}
                </div>
            </div>`;

            if (diff.improved.length > 0) {
                html += `<div class="card" style="margin-bottom:16px">
                    <div class="card-header" style="color:var(--green)">
                        Controls Improved by AI Analysis (${diff.improved.length})
                    </div>
                    <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px">
                        These controls were scored higher when AI analyzed code behavior and intent,
                        not just file names and keywords.
                    </p>`;

                const depthLabels = { old: 'Quick scan found', new: 'Deep scan found' };
                for (const c of diff.improved) {
                    html += this._renderControlComparison(c, depthLabels);
                }
                html += '</div>';
            }

            if (diff.unchanged.length > 0) {
                html += `
                <div class="accordion-item" id="compare-unchanged">
                    <div class="accordion-header" onclick="Components.toggleAccordion('compare-unchanged')">
                        <span>Unchanged Controls (${diff.unchanged.length})</span>
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

            if (diff.regressed.length > 0) {
                const depthLabels = { old: 'Quick scan found', new: 'Deep scan found' };
                html += `<div class="card" style="margin-bottom:16px">
                    <div class="card-header" style="color:var(--red)">
                        Controls Changed (${diff.regressed.length})
                    </div>`;
                for (const c of diff.regressed) {
                    html += this._renderControlComparison(c, depthLabels);
                }
                html += '</div>';
            }

            html += `
            <div class="card compare-preview" style="margin-top:16px">
                <div class="card-header">Key Takeaway</div>
                <p style="font-size:14px;color:var(--text-secondary);line-height:1.7">
                    ${diff.improved.length > 0
                        ? `AI semantic analysis found evidence for <strong>${diff.improved.length} additional controls</strong>
                           that pure pattern matching missed. The score improved from
                           <strong>${diff.score1.toFixed(1)}%</strong> to <strong>${diff.score2.toFixed(1)}%</strong>
                           because the AI could understand code intent — not just match keywords.`
                        : `The semantic scan found changes in ${diff.regressed.length} controls.
                           Review the details above to understand what shifted.`}
                </p>
            </div>`;
        }

        app.innerHTML = html;
    },

    /** Render a single control comparison card.
     *  labels: { old, new } — column headers (default: Structure/Semantic). */
    _renderControlComparison(c, labels) {
        const oldLabel = (labels && labels.old) || 'Previous';
        const newLabel = (labels && labels.new) || 'Current';
        return `
        <div class="compare-control-diff">
            <div class="compare-status-change">
                ${Components.renderStatusBadge(c.oldStatus)}
                <span class="compare-status-arrow">&#8594;</span>
                ${Components.renderStatusBadge(c.newStatus)}
                <strong style="margin-left:8px">${c.controlId}</strong>
            </div>
            <div class="compare-control-req">${(c.requirement || '').substring(0, 200)}</div>
            <div class="compare-columns">
                <div class="compare-col compare-col-structure">
                    <div class="compare-col-label">${oldLabel}</div>
                    ${c.oldEvidence.length > 0
                        ? c.oldEvidence.slice(0, 3).map(e => `<div class="compare-evidence">${e}</div>`).join('')
                        : '<div class="compare-evidence compare-evidence-none">No evidence</div>'}
                </div>
                <div class="compare-col compare-col-semantic">
                    <div class="compare-col-label">${newLabel}</div>
                    ${c.newEvidence.length > 0
                        ? c.newEvidence.slice(0, 3).map(e => `<div class="compare-evidence">${e}</div>`).join('')
                        : '<div class="compare-evidence compare-evidence-none">No evidence</div>'}
                </div>
            </div>
            ${c.semanticAnalysis ? `
                <div class="compare-semantic-insight">${c.semanticAnalysis}</div>
            ` : ''}
        </div>`;
    },

    /** Render local diff (same depth, different scans — e.g. rescan after fixes). */
    _renderLocalDiff(r1, r2, id1, id2) {
        const app = document.getElementById('app');
        const diff = this._computeLocalDiff(r1, r2);
        const fw = r2.framework || r1.framework || '';
        const target = r2.target || r1.target || '';
        const repo = target.replace(/.*\//, '');
        const commit1 = (r1.commitSha || '').substring(0, 7);
        const commit2 = (r2.commitSha || '').substring(0, 7);
        const date1 = (r1.generatedAt || '').substring(5, 16).replace('T', ' ');
        const date2 = (r2.generatedAt || '').substring(5, 16).replace('T', ' ');
        const depth = r2.scanDepth || r1.scanDepth || 'content';

        const subtitle = diff.delta > 0
            ? `${repo} improved by ${diff.delta.toFixed(1)} points`
            : diff.delta < 0
                ? `${repo} regressed by ${Math.abs(diff.delta).toFixed(1)} points`
                : `${repo} score unchanged`;

        let html = `
        <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
            <div>
                <h2>${fwLabel(fw)}: Before & After</h2>
                <p>${subtitle}${commit1 && commit2 && commit1 !== commit2 ? ` (${commit1} &#8594; ${commit2})` : ''}</p>
            </div>
            ${target ? `<a href="#/scan?repo=${encodeURIComponent(target)}&framework=${encodeURIComponent(fw)}&depth=${encodeURIComponent(depth)}" class="btn btn-secondary btn-sm" style="flex-shrink:0">Rescan</a>` : ''}
        </div>

        ${diff.delta < 0 ? `<div class="regression-banner">
            <strong>Score dropped from ${diff.score1.toFixed(1)}% to ${diff.score2.toFixed(1)}%</strong>
            <span>${diff.regressed.length} control${diff.regressed.length !== 1 ? 's' : ''} regressed. Review below and fix to restore your score.</span>
        </div>` : diff.delta > 0 ? `<div class="improvement-banner">
            <strong>Score improved from ${diff.score1.toFixed(1)}% to ${diff.score2.toFixed(1)}%</strong>
            <span>${diff.improved.length} control${diff.improved.length !== 1 ? 's' : ''} fixed.</span>
        </div>` : ''}

        ${Components.renderCompareScoreHeader({
            score1: diff.score1, score2: diff.score2,
            id1: id1 || '', id2: id2 || '',
            label1: 'Previous' + (date1 ? ` (${date1})` : ''),
            label2: 'Latest' + (date2 ? ` (${date2})` : ''),
            delta: diff.delta,
        })}`;

        const labels = { old: 'Previous scan', new: 'Latest scan' };

        if (diff.improved.length > 0) {
            html += `<div class="card"><div class="card-header" style="color:var(--green)">Fixed (${diff.improved.length})</div>
                <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px">
                    These controls improved since the previous scan.
                </p>`;
            for (const c of diff.improved) html += this._renderControlComparison(c, labels);
            html += '</div>';
        }
        if (diff.regressed.length > 0) {
            html += `<div class="card"><div class="card-header" style="color:var(--red)">Regressed (${diff.regressed.length})</div>
                <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px">
                    These controls scored lower than before.
                </p>`;
            for (const c of diff.regressed) html += this._renderControlComparison(c, labels);
            html += '</div>';
        }
        if (diff.unchanged.length > 0) {
            html += `<div class="accordion-item" id="diff-unchanged">
                <div class="accordion-header" onclick="Components.toggleAccordion('diff-unchanged')">
                    <span>Unchanged (${diff.unchanged.length})</span>
                    <span class="accordion-chevron">&#9656;</span>
                </div>
                <div class="accordion-body">${Components.renderTable(
                    ['Control', 'Status'], diff.unchanged.map(c => [c.controlId, Components.renderStatusBadge(c.newStatus)])
                )}</div>
            </div>`;
        }

        // Export actions
        if (typeof ReportGenerator !== 'undefined') {
            html += `
            <div class="card" style="margin-top:16px">
                <div class="card-header">Export</div>
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                    <button class="btn btn-secondary btn-sm" onclick="ReportGenerator.fromCompare('${id1}','${id2}')">Generate Report</button>
                    <a href="${complyApi.getDownloadUrl(id2, 'json')}" class="btn btn-secondary btn-sm" style="text-decoration:none">Download JSON</a>
                    <a href="${complyApi.getDownloadUrl(id2, 'csv')}" class="btn btn-secondary btn-sm" style="text-decoration:none">Download CSV</a>
                </div>
            </div>`;
        }

        app.innerHTML = html;
    },

    /** Render server-side diff (original behavior). */
    _renderServerDiff(diff, id1, id2) {
        const app = document.getElementById('app');
        const baseline = diff.baseline || {};
        const current = diff.current || {};
        const delta = diff.scoreDelta || 0;
        const newGaps = diff.newGaps || [];
        const resolved = diff.resolvedGaps || [];
        const changed = diff.changed || [];
        const regression = diff.regressionDetected;
        const fw = current.framework || baseline.framework || '';
        const target = current.repoPath || baseline.repoPath || '';

        let html = `
        <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
            <div>
                <h2>Scan Comparison: ${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</h2>
                <p>Before & After${delta !== 0 ? ` — ${delta > 0 ? '+' : ''}${delta.toFixed(1)} points` : ''}</p>
            </div>
            ${target ? `<a href="#/scan?repo=${encodeURIComponent(target)}&framework=${encodeURIComponent(fw)}" class="btn btn-secondary btn-sm" style="flex-shrink:0">Rescan</a>` : ''}
        </div>`;

        if (regression) {
            html += `<div class="regression-banner">
                <strong>Score dropped from ${(baseline.score || 0).toFixed(1)}% to ${(current.score || 0).toFixed(1)}%</strong>
                <span>${newGaps.length} new gap${newGaps.length !== 1 ? 's' : ''} detected. Review below and use the Remediation Roadmap to address them.</span>
            </div>`;
        } else if (delta > 0) {
            html += `<div class="improvement-banner">
                <strong>Score improved from ${(baseline.score || 0).toFixed(1)}% to ${(current.score || 0).toFixed(1)}%</strong>
                <span>${resolved.length} gap${resolved.length !== 1 ? 's' : ''} resolved.</span>
            </div>`;
        }

        html += `
        <div class="grid-2">
            <div class="card">
                <div class="card-header">Baseline</div>
                <div style="font-size:13px">
                    <div>ID: <a href="#/detail/${baseline.scanId}" style="color:var(--accent)">${(baseline.scanId || '').substring(0, 12)}</a></div>
                    <div>Framework: ${baseline.framework || ''}</div>
                    <div>Score: <strong>${(baseline.score || 0).toFixed(1)}%</strong></div>
                    <div>Date: ${(baseline.generatedAt || '').substring(0, 19)}</div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">Current</div>
                <div style="font-size:13px">
                    <div>ID: <a href="#/detail/${current.scanId}" style="color:var(--accent)">${(current.scanId || '').substring(0, 12)}</a></div>
                    <div>Framework: ${current.framework || ''}</div>
                    <div>Score: <strong>${(current.score || 0).toFixed(1)}%</strong></div>
                    <div>Date: ${(current.generatedAt || '').substring(0, 19)}</div>
                </div>
            </div>
        </div>`;

        const deltaColor = delta > 0 ? 'var(--green)' : delta < 0 ? 'var(--red)' : 'var(--text-muted)';
        html += `<div class="card">
            <div class="card-header">Score Delta</div>
            <div style="font-size:24px;font-weight:700;color:${deltaColor}">${delta > 0 ? '+' : ''}${delta.toFixed(1)}%</div>
        </div>`;

        if (newGaps.length) {
            html += `<div class="card">
                <div class="card-header" style="color:var(--red)">New Gaps (${newGaps.length})</div>
                ${newGaps.map(g => `
                    <div style="font-size:13px;margin-bottom:8px;padding:8px;background:var(--bg-primary);border-radius:4px">
                        ${Components.renderStatusBadge('gap')}
                        <strong>${g.controlId || ''}</strong>
                        <div style="color:var(--text-secondary);margin-top:4px">${(g.requirement || '').substring(0, 200)}</div>
                    </div>
                `).join('')}
            </div>`;
        }

        if (resolved.length) {
            html += `<div class="card">
                <div class="card-header" style="color:var(--green)">Resolved (${resolved.length})</div>
                ${resolved.map(g => `
                    <div style="font-size:13px;margin-bottom:8px;padding:8px;background:var(--bg-primary);border-radius:4px">
                        ${Components.renderStatusBadge('met')}
                        <strong>${g.controlId || ''}</strong>
                        <div style="color:var(--text-secondary);margin-top:4px">${(g.requirement || '').substring(0, 200)}</div>
                    </div>
                `).join('')}
            </div>`;
        }

        const otherChanged = changed.filter(c =>
            !newGaps.some(g => g.controlId === c.controlId) &&
            !resolved.some(g => g.controlId === c.controlId)
        );
        if (otherChanged.length) {
            html += `<div class="card">
                <div class="card-header">Changed Controls (${otherChanged.length})</div>
                ${Components.renderTable(
                    ['Control', 'Before', 'After'],
                    otherChanged.map(c => [
                        c.controlId || '',
                        Components.renderStatusBadge(c.old || ''),
                        Components.renderStatusBadge(c.new || ''),
                    ])
                )}
            </div>`;
        }

        // Export actions
        html += `
        <div class="card" style="margin-top:16px">
            <div class="card-header">Export</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <a href="${complyApi.getDownloadUrl(id2, 'json')}" class="btn btn-secondary btn-sm" style="text-decoration:none">Download JSON</a>
                <a href="${complyApi.getDownloadUrl(id2, 'csv')}" class="btn btn-secondary btn-sm" style="text-decoration:none">Download CSV</a>
            </div>
        </div>`;

        app.innerHTML = html;
    },
};
