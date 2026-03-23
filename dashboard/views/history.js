/* History view — browse past scans */
const HistoryView = {
    _scans: [],
    _selected: [],

    async render() {
        const app = document.getElementById('app');
        const isDemo = App.capabilities && App.capabilities.demo_mode;
        app.innerHTML = `
        <div class="page-header">
            <h2>Scan History</h2>
            <p>Browse and compare past compliance scans</p>
        </div>
        <div class="card">
            <div class="form-row" style="margin-bottom:12px">
                <div class="form-group" style="flex:2">
                    <label for="hist-filter-repo" class="sr-only">Filter by repository</label>
                    <select class="form-select" id="hist-filter-repo" aria-label="Filter by repository" onchange="HistoryView.filterAndRender()">
                        <option value="">All repositories</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="hist-filter-fw" class="sr-only">Filter by framework</label>
                    <select class="form-select" id="hist-filter-fw" aria-label="Filter by framework" onchange="HistoryView.filterAndRender()">
                        <option value="">All frameworks</option>
                    </select>
                </div>
                ${isDemo ? `<div class="form-group">
                    <select class="form-select" id="hist-filter-source" onchange="HistoryView.filterAndRender()">
                        <option value="">All scans</option>
                        <option value="user">My Scans</option>
                        <option value="demo">Demo</option>
                    </select>
                </div>` : `<div class="form-group" style="flex:0">
                    <button class="btn btn-sm" id="hist-compare-btn" disabled onclick="HistoryView.compare()">Compare</button>
                </div>`}
            </div>
            <div id="hist-table"><div class="loading">Loading...</div></div>
        </div>`;

        // Pre-select filters from URL params (e.g. from Browse "View in History" link)
        this._applyUrlParams();
        await this.loadData();
    },

    /** Parse URL hash params and pre-select filter dropdowns. */
    _applyUrlParams() {
        const hashParts = window.location.hash.split('?');
        if (hashParts.length < 2) return;
        const params = new URLSearchParams(hashParts[1]);

        const source = params.get('source');
        const repo = params.get('repo');
        const fw = params.get('fw');

        if (source) {
            const sel = document.getElementById('hist-filter-source');
            if (sel) sel.value = source;
        }
        if (repo) {
            // Will be applied after populateRepoFilter adds options
            this._pendingRepoFilter = repo;
        }
        if (fw) {
            this._pendingFwFilter = fw;
        }
    },

    async loadData() {
        try {
            // ScanAdapter handles both demo (catalog + IndexedDB) and self-hosted (server API)
            const scans = ScanAdapter.list();
            this._scans = scans.map(s => {
                const url = s.url || s.repo_url || (s.report && s.report.target) || '';
                return {
                    id: s.id,
                    score: s.score,
                    framework: s.framework,
                    scan_depth: s.depth || s.scan_depth,
                    repo_url: url,
                    repo_path: url,
                    created_at: s.timestamp || s.created_at,
                    commit_sha: (s.report && s.report.commitSha) || '',
                    is_baseline: false,
                    source: s.source || 'user',
                    _local: true,
                };
            });
            this._populateRepoFilter();
            this._populateFrameworkFilter();
            this.filterAndRender();
        } catch (e) {
            document.getElementById('hist-table').innerHTML =
                `<div class="alert alert-error">${e.message}</div>`;
        }
    },

    _populateRepoFilter() {
        const repos = [...new Set(this._scans.map(s =>
            (s.repo_url || s.repo_path || '').replace(/.*\//, '')
        ).filter(Boolean))].sort();
        const sel = document.getElementById('hist-filter-repo');
        if (!sel) return;
        repos.forEach(r => {
            const opt = document.createElement('option');
            opt.value = r;
            opt.textContent = r;
            sel.appendChild(opt);
        });
        // Apply pending URL param
        if (this._pendingRepoFilter) {
            sel.value = this._pendingRepoFilter;
            this._pendingRepoFilter = null;
        }
    },

    _populateFrameworkFilter() {
        const fws = [...new Set(this._scans.map(s => s.framework))].sort();
        const sel = document.getElementById('hist-filter-fw');
        if (!sel) return;
        fws.forEach(fw => {
            const opt = document.createElement('option');
            opt.value = fw;
            opt.textContent = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
            sel.appendChild(opt);
        });
        // Apply pending URL param
        if (this._pendingFwFilter) {
            sel.value = this._pendingFwFilter;
            this._pendingFwFilter = null;
        }
    },

    filterAndRender() {
        const repo = document.getElementById('hist-filter-repo')?.value || '';
        const fw = document.getElementById('hist-filter-fw')?.value || '';
        const source = document.getElementById('hist-filter-source')?.value || '';

        let filtered = this._scans;
        if (repo) {
            filtered = filtered.filter(s =>
                (s.repo_url || s.repo_path || '').replace(/.*\//, '') === repo);
        }
        if (fw) {
            filtered = filtered.filter(s => s.framework === fw);
        }
        if (source) {
            filtered = filtered.filter(s => s.source === source);
        }

        this._renderTable(filtered);
    },

    _groupScans(scans) {
        if (ScanAdapter.groupByRepoFramework) {
            return ScanAdapter.groupByRepoFramework(scans);
        }
        // Fallback
        const groups = {};
        for (const s of scans) {
            const key = `${(s.repo_url || s.repo_path || '').toLowerCase()}|${s.framework || ''}`;
            if (!groups[key]) groups[key] = [];
            groups[key].push(s);
        }
        for (const arr of Object.values(groups)) {
            arr.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
        }
        return groups;
    },

    _renderTable(scans) {
        if (!scans.length) {
            document.getElementById('hist-table').innerHTML =
                '<div class="empty-state"><h3>No scans found</h3><p>Run a scan to get started</p></div>';
            return;
        }

        const isDemo = App.capabilities && App.capabilities.demo_mode;

        if (isDemo) {
            const groups = this._groupScans(scans);

            // Sort groups: user scans first, demo scans last
            const entries = Object.entries(groups);
            const userGroups = [];
            const demoGroups = [];
            for (const [key, timeline] of entries) {
                const hasUser = timeline.some(s => s.source !== 'demo');
                if (hasUser) {
                    userGroups.push([key, timeline]);
                } else {
                    demoGroups.push([key, timeline]);
                }
            }
            // Sort each section by most recent scan
            const byRecent = (a, b) => {
                const aLatest = a[1][a[1].length - 1];
                const bLatest = b[1][b[1].length - 1];
                return (bLatest.created_at || bLatest.timestamp || '').localeCompare(aLatest.created_at || aLatest.timestamp || '');
            };
            userGroups.sort(byRecent);
            demoGroups.sort(byRecent);

            let html = '';
            for (const [, timeline] of userGroups) {
                html += this._renderGroup(timeline);
            }
            if (userGroups.length > 0 && demoGroups.length > 0) {
                html += '<div class="hist-section-divider">Demo Scans</div>';
            }
            for (const [, timeline] of demoGroups) {
                html += this._renderGroup(timeline);
            }
            document.getElementById('hist-table').innerHTML = html;
        } else {
            this._renderStandardTable(scans);
        }
    },

    /** Render any group (1 or more scans) as a consistent expandable row. */
    _renderGroup(timeline) {
        return Components.renderTimelineGroup(timeline);
    },

    /** Standard table for non-demo mode. */
    _renderStandardTable(scans) {
        const rows = scans.map(s => {
            const id = s.id || '';
            const score = s.score || 0;
            const scoreColor = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)';
            const baseline = s.is_baseline ? ' *' : '';
            const repo = (s.repo_url || s.repo_path || '').replace(/.*\//, '').substring(0, 40);
            const date = (s.created_at || '').substring(0, 19).replace('T', ' ');
            const depth = s.scan_depth || '';

            return `<tr>
                <td><input type="checkbox" data-id="${id}" onchange="HistoryView.onSelect()"></td>
                <td><a href="#/detail/${id}" style="color:var(--accent);text-decoration:none">${id.substring(0, 12)}</a></td>
                <td style="color:${scoreColor};font-weight:600">${score.toFixed(1)}%${baseline}</td>
                <td>${typeof fwLabel === 'function' ? fwLabel(s.framework || '') : (s.framework || '')}</td>
                <td>${depth}</td>
                <td style="color:var(--text-muted)">${date}</td>
                <td title="${s.repo_path || ''}">${repo}</td>
                <td><button class="btn btn-sm" onclick="HistoryView.setBaseline('${id}')">Baseline</button></td>
            </tr>`;
        }).join('');

        document.getElementById('hist-table').innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th></th><th>ID</th><th>Score</th><th>Framework</th><th>Depth</th><th>Date</th><th>Repo</th><th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    },

    onSelect() {
        const boxes = document.querySelectorAll('#hist-table input[type=checkbox]:checked');
        this._selected = [...boxes].map(b => b.dataset.id);
        const btn = document.getElementById('hist-compare-btn');
        if (btn) btn.disabled = this._selected.length !== 2;
    },

    compare() {
        if (this._selected.length === 2) {
            Router.navigate(`/diff/${this._selected[0]}/${this._selected[1]}`);
        }
    },

    async setBaseline(id) {
        try {
            await complyApi.setBaseline(id);
            await this.loadData();
        } catch (e) {
            alert('Failed to set baseline: ' + e.message);
        }
    },
};
