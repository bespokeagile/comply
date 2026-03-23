/* Program view — portfolio grouping of repos × frameworks.
   Shows aggregate posture matrix and actions (batch scan, portfolio report). */
const ProgramView = {
    _program: null,
    _posture: null,
    _editing: false,

    async render(params) {
        const app = document.getElementById('app');
        const programId = params && params[0];

        if (!programId) {
            return this._renderList(app);
        }

        app.innerHTML = '<div class="loading"><span class="spinner"></span> Loading program...</div>';
        try {
            const [program, posture] = await Promise.all([
                complyApi.getProgram(programId),
                complyApi.getProgramPosture(programId),
            ]);
            this._program = program;
            this._posture = posture;
            this._renderDetail(app);
        } catch (e) {
            app.innerHTML = `<div class="alert alert-error">Failed to load program: ${e.message}</div>`;
        }
    },

    /** List all programs with create button. */
    async _renderList(app) {
        app.innerHTML = '<div class="loading"><span class="spinner"></span> Loading programs...</div>';
        let programs = [];
        try {
            programs = await complyApi.listPrograms();
        } catch (e) { /* empty */ }

        // Check for pre-fill params (from post-scan "Add to Program")
        const hashParts = (window.location.hash || '').split('?');
        const urlParams = hashParts.length > 1 ? new URLSearchParams(hashParts[1]) : null;
        const prefillRepo = urlParams ? urlParams.get('newRepo') : null;
        const prefillFw = urlParams ? urlParams.get('newFw') : null;

        let html = `
        <div class="page-header page-header-flex">
            <div>
                <h2>Programs</h2>
                <p class="text-desc">Group repositories and frameworks into compliance programs for portfolio-level visibility.</p>
            </div>
            <button class="btn btn-primary" onclick="ProgramView._showCreate()">+ New Program</button>
        </div>

        <div id="program-create-form" style="display:${prefillRepo ? '' : 'none'}"></div>`;

        if (programs.length === 0) {
            html += `
            <div class="empty-state card" style="text-align:center;padding:40px">
                <h3>No programs yet</h3>
                <p class="text-desc">Create a program to group repositories and frameworks together.</p>
                <button class="btn btn-primary" onclick="ProgramView._showCreate()" style="margin-top:16px">Create Your First Program</button>
            </div>`;
        } else {
            html += '<div class="program-grid">';
            for (const prog of programs) {
                const repoCount = (prog.repos || []).length;
                const fwCount = (prog.frameworks || []).length;
                html += `
                <div class="card program-card" onclick="window.location.hash='#/program/${prog.id}'">
                    <div class="card-header">${prog.name}</div>
                    ${prog.description ? `<p class="text-desc">${prog.description}</p>` : ''}
                    <div class="program-card-meta">
                        <span>${repoCount} repo${repoCount !== 1 ? 's' : ''}</span>
                        <span>${fwCount} framework${fwCount !== 1 ? 's' : ''}</span>
                    </div>
                </div>`;
            }
            html += '</div>';
        }

        app.innerHTML = html;

        // Auto-show create form with pre-filled data from URL params
        if (prefillRepo) {
            this._showCreate(prefillRepo, prefillFw);
        }
    },

    /** Render program detail with posture matrix. */
    _renderDetail(app) {
        const prog = this._program;
        const posture = this._posture;

        let html = `
        <div class="page-header page-header-flex">
            <div>
                <div class="detail-breadcrumb">
                    <a href="#/program">Programs</a>
                    <span class="breadcrumb-sep">&rsaquo;</span>
                    <span>${prog.name}</span>
                </div>
                <h2>${prog.name}</h2>
                ${prog.description ? `<p class="text-desc">${prog.description}</p>` : ''}
            </div>
            <div class="detail-header-actions">
                <button class="btn btn-primary btn-sm" onclick="ProgramView._generatePortfolioReport()">Portfolio Report</button>
                <button class="btn btn-secondary btn-sm" onclick="ProgramView._showEdit()">Edit</button>
                <button class="btn btn-sm" style="color:var(--red)" onclick="ProgramView._confirmDelete('${prog.id}')">Delete</button>
            </div>
        </div>

        <div id="program-edit-form" style="display:none"></div>`;

        // Posture summary bar
        if (posture) {
            const scoreColor = posture.avg_score >= 70 ? 'var(--green)' : posture.avg_score >= 40 ? 'var(--yellow)' : 'var(--red)';
            html += `
            <div class="posture-bar" style="margin-bottom:20px">
                <div class="posture-metric">
                    <span class="posture-value" style="color:${scoreColor}">${Math.round(posture.avg_score)}%</span>
                    <span class="posture-label">Avg Score</span>
                </div>
                <div class="posture-divider"></div>
                <div class="posture-metric">
                    <span class="posture-value">${posture.scanned}</span>
                    <span class="posture-label">Scans Complete</span>
                </div>
                <div class="posture-divider"></div>
                <div class="posture-metric">
                    <span class="posture-value">${posture.coverage}%</span>
                    <span class="posture-label">Coverage</span>
                </div>
            </div>`;
        }

        // Posture matrix: repos × frameworks
        if (posture && posture.repos && posture.repos.length > 0) {
            const frameworks = prog.frameworks || [];
            html += `
            <div class="card">
                <div class="card-header">Compliance Matrix</div>
                <div style="overflow-x:auto">
                <table class="data-table program-matrix">
                    <thead>
                        <tr>
                            <th>Repository</th>
                            ${frameworks.map(fw => `<th>${typeof fwLabel === 'function' ? fwLabel(fw) : fw}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>`;

            for (const repo of posture.repos) {
                html += `<tr><td><strong>${repo.label}</strong></td>`;
                for (const fwResult of repo.frameworks) {
                    if (fwResult.score !== null) {
                        const color = fwResult.score >= 70 ? 'var(--green)' : fwResult.score >= 40 ? 'var(--yellow)' : 'var(--red)';
                        const link = fwResult.scan_id ? `onclick="window.location.hash='#/detail/${fwResult.scan_id}'"` : '';
                        html += `<td class="matrix-cell" ${link} style="cursor:${fwResult.scan_id ? 'pointer' : 'default'}">
                            <span style="color:${color};font-weight:600">${Math.round(fwResult.score)}%</span>
                            <span class="matrix-depth">${(fwResult.scan_depth || '').includes('semantic') ? 'deep' : 'quick'}</span>
                        </td>`;
                    } else {
                        html += `<td class="matrix-cell matrix-cell-empty">--</td>`;
                    }
                }
                html += '</tr>';
            }

            html += `</tbody></table></div></div>`;

            // Gap analysis: find lowest-scoring cells
            const gaps = [];
            for (const repo of posture.repos) {
                for (const fw of repo.frameworks) {
                    if (fw.score !== null && fw.score < 70) {
                        gaps.push({ repo: repo.label, framework: fw.framework, score: fw.score, scan_id: fw.scan_id });
                    }
                }
            }
            if (gaps.length > 0) {
                gaps.sort((a, b) => a.score - b.score);
                html += `
                <div class="card">
                    <div class="card-header" style="color:var(--yellow)">Attention Required (${gaps.length})</div>`;
                for (const g of gaps.slice(0, 8)) {
                    const color = g.score < 40 ? 'var(--red)' : 'var(--yellow)';
                    html += `
                    <div class="program-gap-item" ${g.scan_id ? `onclick="window.location.hash='#/detail/${g.scan_id}'"` : ''}>
                        <strong>${g.repo}</strong>
                        <span>${typeof fwLabel === 'function' ? fwLabel(g.framework) : g.framework}</span>
                        <span style="color:${color};font-weight:600">${Math.round(g.score)}%</span>
                    </div>`;
                }
                html += '</div>';
            }

            // Missing scans
            const missing = [];
            for (const repo of posture.repos) {
                for (const fw of repo.frameworks) {
                    if (fw.score === null) {
                        missing.push({ repo: repo.label, url: repo.url, framework: fw.framework });
                    }
                }
            }
            if (missing.length > 0) {
                html += `
                <div class="card card-muted">
                    <div class="card-header">Missing Scans (${missing.length})</div>
                    <p class="text-desc">These repo × framework combinations haven't been scanned yet.</p>`;
                for (const m of missing) {
                    const repoEnc = encodeURIComponent(m.url);
                    const fwEnc = encodeURIComponent(m.framework);
                    html += `
                    <div class="program-gap-item">
                        <strong>${m.repo}</strong>
                        <span>${typeof fwLabel === 'function' ? fwLabel(m.framework) : m.framework}</span>
                        <a href="#/scan?repo=${repoEnc}&framework=${fwEnc}" class="btn btn-sm btn-secondary" onclick="event.stopPropagation()">Scan</a>
                    </div>`;
                }
                html += '</div>';
            }
        } else {
            html += `
            <div class="empty-state card" style="text-align:center;padding:32px">
                <p class="text-desc">No scans found for this program's repos and frameworks.</p>
                <p class="text-desc">Add repos and frameworks, then scan them to see the compliance matrix.</p>
            </div>`;
        }

        app.innerHTML = html;
    },

    /** Show create form inline, optionally pre-filling repo+fw. */
    _showCreate(prefillRepo, prefillFw) {
        const container = document.getElementById('program-create-form');
        if (!container) return;
        container.style.display = '';
        const prefill = prefillRepo ? { repos: [prefillRepo], frameworks: prefillFw ? [typeof fwNorm === 'function' ? fwNorm(prefillFw) : prefillFw] : [] } : null;
        container.innerHTML = this._renderForm(prefill, 'ProgramView._submitCreate()');
    },

    /** Show edit form inline. */
    _showEdit() {
        const container = document.getElementById('program-edit-form');
        if (!container) return;
        container.style.display = '';
        container.innerHTML = this._renderForm(this._program, `ProgramView._submitEdit('${this._program.id}')`);
    },

    /** Render the create/edit form. */
    _renderForm(program, submitFn) {
        const p = program || {};
        const repos = (p.repos || []).map(r => typeof r === 'string' ? r : r.url || '').join('\n');
        const fws = (p.frameworks || []);

        const allFw = [
            { id: 'eu_ai_act', label: 'EU AI Act' },
            { id: 'soc2_ai', label: 'SOC 2 AI' },
            { id: 'nist_ai_rmf', label: 'NIST AI RMF' },
            { id: 'iso_42001', label: 'ISO 42001' },
            { id: 'owasp_llm_top10', label: 'OWASP LLM Top 10' },
            { id: 'owasp_agentic_top10', label: 'OWASP Agentic Top 10' },
            { id: 'california_ab_2013', label: 'California AB 2013' },
            { id: 'california_sb_942', label: 'California SB 942' },
            { id: 'colorado_sb_24_205', label: 'Colorado SB 24-205' },
            { id: 'insurance_attestation', label: 'Insurance Attestation' },
        ];

        const fwChecks = allFw.map(fw =>
            `<label class="program-fw-check"><input type="checkbox" name="fw" value="${fw.id}" ${fws.includes(fw.id) ? 'checked' : ''}> ${fw.label}</label>`
        ).join('');

        return `
        <div class="card" style="margin-bottom:20px">
            <div class="card-header">${program ? 'Edit Program' : 'New Program'}</div>
            <div class="form-group">
                <label>Name</label>
                <input type="text" id="prog-name" class="form-input" value="${p.name || ''}" placeholder="e.g., AI Platform Compliance">
            </div>
            <div class="form-group">
                <label>Description</label>
                <input type="text" id="prog-desc" class="form-input" value="${p.description || ''}" placeholder="Optional description">
            </div>
            <div class="form-group">
                <label>Repository URLs (one per line)</label>
                <textarea id="prog-repos" class="form-input" rows="4" placeholder="https://github.com/org/repo1&#10;https://github.com/org/repo2">${repos}</textarea>
            </div>
            <div class="form-group">
                <label>Frameworks</label>
                <div class="program-fw-grid">${fwChecks}</div>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px">
                <button class="btn btn-primary" onclick="${submitFn}">Save</button>
                <button class="btn btn-secondary" onclick="this.closest('.card').parentElement.style.display='none'">Cancel</button>
            </div>
        </div>`;
    },

    /** Gather form data. */
    _getFormData() {
        const name = (document.getElementById('prog-name') || {}).value || '';
        const description = (document.getElementById('prog-desc') || {}).value || '';
        const reposText = (document.getElementById('prog-repos') || {}).value || '';
        const repos = reposText.split('\n').map(s => s.trim()).filter(Boolean);
        const fwChecks = document.querySelectorAll('input[name="fw"]:checked');
        const frameworks = Array.from(fwChecks).map(cb => cb.value);
        return { name, description, repos, frameworks };
    },

    async _submitCreate() {
        const data = this._getFormData();
        if (!data.name) return;
        try {
            await complyApi.createProgram(data);
            window.location.hash = '#/program';
            this.render([]);
        } catch (e) {
            alert('Failed to create program: ' + e.message);
        }
    },

    async _submitEdit(id) {
        const data = this._getFormData();
        if (!data.name) return;
        try {
            await complyApi.updateProgram(id, data);
            window.location.hash = '#/program/' + id;
            this.render([id]);
        } catch (e) {
            alert('Failed to update program: ' + e.message);
        }
    },

    async _confirmDelete(id) {
        if (!confirm('Delete this program? Scans are not affected.')) return;
        try {
            await complyApi.deleteProgram(id);
            window.location.hash = '#/program';
            this.render([]);
        } catch (e) {
            alert('Failed to delete program: ' + e.message);
        }
    },

    /** Generate portfolio report for the program. */
    _generatePortfolioReport() {
        if (!this._posture || !this._posture.repos) return;
        // Find all scan IDs from the posture data
        const scanIds = [];
        for (const repo of this._posture.repos) {
            for (const fw of repo.frameworks) {
                if (fw.scan_id) scanIds.push(fw.scan_id);
            }
        }
        if (scanIds.length === 0) {
            alert('No scans found for this program. Scan repos first.');
            return;
        }
        // Generate cross-framework report using the first scan (opens report page)
        // Future: aggregate portfolio report
        if (typeof ReportGenerator !== 'undefined' && ReportGenerator.crossFramework) {
            ReportGenerator.crossFramework(scanIds);
        } else if (scanIds.length > 0) {
            ReportGenerator.fromScan(scanIds[0]);
        }
    },
};
