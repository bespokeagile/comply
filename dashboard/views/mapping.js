/* Mapping view — cross-framework control mapping with scan-aware filtering */
const MappingView = {
    _jurisdictions: [],
    _activeJurisdiction: null,
    _myFrameworks: [],
    _showAllFrameworks: false,

    async render() {
        const app = document.getElementById('app');
        app.innerHTML = `
        <div class="page-header">
            <h2>Cross-Framework Control Mapping</h2>
            <p>See how one capability satisfies controls across multiple frameworks</p>
        </div>
        <div id="mapping-filters"></div>
        <div id="mapping-content"><div class="loading"><span class="spinner"></span> Loading mapping...</div></div>
        <div id="priorities-content"></div>`;

        // Detect which frameworks the user has actually scanned
        await this._detectMyFrameworks();
        await this.loadJurisdictions();
        await this.loadMapping();
        await this.loadPriorities();
    },

    async _detectMyFrameworks() {
        try {
            const history = await complyApi.getHistory(null, null, 100);
            const fws = new Set();
            for (const s of history) {
                if (s.framework) fws.add(fwNorm(s.framework));
            }
            this._myFrameworks = [...fws];
        } catch (e) {
            this._myFrameworks = [];
        }
        // Default to "my frameworks" if any exist
        this._showAllFrameworks = this._myFrameworks.length === 0;
    },

    async loadJurisdictions() {
        const bar = document.getElementById('mapping-filters');
        if (!bar) return;
        try {
            this._jurisdictions = await complyApi.getJurisdictions();
        } catch (e) {
            this._jurisdictions = [];
        }
        this._renderFilters(bar);
    },

    _renderFilters(bar) {
        let html = '<div class="mapping-filter-bar">';

        // Scope toggle: My Frameworks vs All
        if (this._myFrameworks.length > 0) {
            html += `<div class="mapping-scope-toggle">
                <button class="btn btn-sm${!this._showAllFrameworks ? ' btn-primary' : ''}"
                    onclick="MappingView.toggleScope(false)">My Frameworks (${this._myFrameworks.length})</button>
                <button class="btn btn-sm${this._showAllFrameworks ? ' btn-primary' : ''}"
                    onclick="MappingView.toggleScope(true)">All Frameworks</button>
            </div>`;
        }

        // Jurisdiction filter
        if (this._jurisdictions.length) {
            html += `<div class="mapping-jurisdiction-filter">`;
            html += `<button class="btn btn-sm${!this._activeJurisdiction ? ' btn-primary' : ''}"
                onclick="MappingView.selectJurisdiction(null)">All</button>`;
            for (const j of this._jurisdictions) {
                const active = this._activeJurisdiction === j.id;
                html += `<button class="btn btn-sm${active ? ' btn-primary' : ''}"
                    onclick="MappingView.selectJurisdiction('${j.id}')"
                    title="${j.description}">${j.label}</button>`;
            }
            html += '</div>';
        }

        html += '</div>';
        bar.innerHTML = html;
    },

    toggleScope(showAll) {
        this._showAllFrameworks = showAll;
        this._activeJurisdiction = null;
        this._renderFilters(document.getElementById('mapping-filters'));
        this.loadMapping();
    },

    async selectJurisdiction(id) {
        this._activeJurisdiction = id;
        this._showAllFrameworks = true; // jurisdiction = cross-framework view
        this._renderFilters(document.getElementById('mapping-filters'));
        await this.loadMapping();
    },

    async loadMapping() {
        const container = document.getElementById('mapping-content');
        if (!container) return;
        container.innerHTML = '<div class="loading"><span class="spinner"></span> Loading...</div>';

        try {
            let frameworks = null;
            if (this._activeJurisdiction) {
                const j = this._jurisdictions.find(p => p.id === this._activeJurisdiction);
                if (j) frameworks = j.frameworks.join(',');
            } else if (!this._showAllFrameworks && this._myFrameworks.length) {
                frameworks = this._myFrameworks.join(',');
            }
            const mapping = await complyApi.getMapping(frameworks);
            container.innerHTML = this._renderEfficiencyInsight(mapping) + this._renderMappingTable(mapping);
        } catch (e) {
            container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
        }
    },

    /** Coverage efficiency callout — one-line insight above the matrix. */
    _renderEfficiencyInsight(mapping) {
        const caps = mapping.capabilities || [];
        if (!caps.length) return '';

        // Find the capability that covers the most frameworks
        let best = null;
        for (const cap of caps) {
            if (!best || cap.framework_count > best.framework_count) best = cap;
        }
        if (!best || best.framework_count < 2) return '';

        const totalFws = (mapping.frameworks || []).length;
        return `
        <div class="mapping-efficiency-card">
            <span class="mapping-efficiency-icon">\u2728</span>
            <div>
                <strong>${best.name}</strong> covers ${best.framework_count} of ${totalFws} frameworks.
                Fixing one capability improves compliance across ${best.framework_count} regulatory requirements.
            </div>
        </div>`;
    },

    _renderMappingTable(mapping) {
        const caps = mapping.capabilities || [];
        const fws = mapping.frameworks || [];

        if (!caps.length) {
            return '<div class="empty-state"><h3>No capabilities found</h3></div>';
        }

        let html = `
        <div class="card">
            <div class="card-header">Control Mapping
                <span style="font-weight:normal;font-size:12px;color:var(--text-muted)">
                    ${mapping.totalCapabilities} capabilities &middot; ${fws.length} frameworks &middot; ${mapping.totalControls} controls
                </span>
            </div>
            <div style="overflow-x:auto">
            <table class="mapping-table">
                <thead>
                    <tr>
                        <th class="mapping-th-cap">Capability</th>
                        <th class="mapping-th-count">#</th>`;

        for (const fw of fws) {
            html += `<th class="mapping-th-fw">${fwLabel(fw)}</th>`;
        }
        html += '</tr></thead><tbody>';

        for (const cap of caps) {
            html += `<tr>
                <td class="mapping-td-cap">${cap.name}</td>
                <td class="mapping-td-count">${cap.framework_count}</td>`;

            for (const fw of fws) {
                const ctrls = (cap.controls || []).filter(c => c.framework === fw);
                if (ctrls.length) {
                    const ids = ctrls.map(c => c.controlId).join(', ');
                    const tips = ctrls.map(c => c.requirement || '').join('\n');
                    html += `<td class="mapping-td-ctrl" title="${tips.replace(/"/g, '&quot;')}">${ids}</td>`;
                } else {
                    html += '<td class="mapping-td-empty">&mdash;</td>';
                }
            }
            html += '</tr>';
        }

        html += '</tbody></table></div></div>';
        return html;
    },

    async loadPriorities() {
        const container = document.getElementById('priorities-content');
        if (!container) return;

        try {
            const priorities = await complyApi.getMappingPriorities();
            if (!priorities || !priorities.length) {
                container.innerHTML = '';
                return;
            }

            let html = `
            <div class="card" style="margin-top:16px">
                <div class="card-header">Remediation Priorities
                    <span style="font-weight:normal;font-size:12px;color:var(--text-muted)">
                        Fix one capability to improve multiple frameworks
                    </span>
                </div>
                <div class="mapping-priorities">`;

            for (const p of priorities) {
                const color = p.impact_count >= 3 ? 'var(--red)' : p.impact_count >= 2 ? 'var(--yellow)' : 'var(--text-muted)';
                const ctrls = (p.controls || []).slice(0, 4);
                const ctrlList = ctrls.map(c => {
                    const sColor = c.status === 'gap' ? 'var(--red)' : 'var(--yellow)';
                    return `<span style="font-size:11px;color:${sColor}">${fwLabel(c.framework)}:${c.controlId}</span>`;
                }).join(' \u00b7 ');
                const more = (p.controls || []).length > 4
                    ? `<span style="font-size:11px;color:var(--text-muted)"> +${p.controls.length - 4} more</span>` : '';

                html += `
                <div class="mapping-priority-item" style="border-left-color:${color}">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <strong>${p.name}</strong>
                        <span style="color:${color};font-size:12px;font-weight:600">${p.impact_count} framework${p.impact_count !== 1 ? 's' : ''}</span>
                    </div>
                    <div style="margin-top:4px">${ctrlList}${more}</div>
                </div>`;
            }

            html += '</div></div>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = '';
        }
    },
};
