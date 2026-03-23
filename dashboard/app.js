/* App initialization — route registration and global state */

/** Route-to-tab mapping for contextual navigation. */
const TAB_ROUTES = {
    repos: ['/landing', '/scan', '/detail', '/diff', '/overlap', '/progress', '/history', '/forecast', '/posture', '/trends', '/program'],
    ops: ['/gate', '/monitor'],
    config: ['/settings', '/mapping'],
};

const App = {
    capabilities: { demo_mode: false, managed: false },  // set by initApp()
    _currentTab: 'repos',
    _selectedRepo: null,  // { slug, repoPath, fwGroups, scanCount }
    _tabsInitialized: false,
    _scanHistory: null,  // cached /history response

    /** Switch the active sidebar tab and show corresponding panel. */
    switchTab(tabName) {
        if (!TAB_ROUTES[tabName]) return;
        this._currentTab = tabName;

        // Update tab button states + ARIA
        document.querySelectorAll('.sidebar-tab').forEach(btn => {
            const isActive = btn.dataset.tab === tabName;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        // Show the matching panel, hide others
        document.querySelectorAll('.sidebar-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === 'sidebar-' + tabName);
        });

        // Load panel content on first switch
        if (tabName === 'repos') this.loadScanSidebar();
        else if (tabName === 'ops') this.loadOpsSidebar();
        else if (tabName === 'config') this._renderConfigPanel();

        // Navigate to tab's default route if current route belongs to a different tab
        const currentRoute = '/' + (window.location.hash.split('/')[1] || '').split('?')[0];
        const tabRoutes = TAB_ROUTES[tabName];
        const isCurrentRouteInTab = tabRoutes.some(r => currentRoute.startsWith(r));
        if (!isCurrentRouteInTab) {
            const defaults = { repos: '#/landing', ops: '#/gate', config: '#/settings' };
            window.location.hash = defaults[tabName] || '#/landing';
        }
    },

    /** Determine the correct tab for a route and switch to it. */
    _autoSwitchTab(route) {
        for (const [tab, routes] of Object.entries(TAB_ROUTES)) {
            if (routes.includes(route)) {
                if (this._currentTab !== tab) {
                    this.switchTab(tab);
                }
                return;
            }
        }
    },

    /** Fetch scan history and cache it. */
    async _fetchScanHistory() {
        try {
            this._scanHistory = await complyApi.getHistory(null, null, 100);
        } catch (e) {
            this._scanHistory = [];
        }
        return this._scanHistory;
    },

    /** Group scan history entries by repo name. Returns [{name, slug, scans:[...]}] */
    _groupByRepo(history) {
        const groups = {};
        for (const scan of history) {
            const repoPath = scan.repo || scan.repo_url || 'unknown';
            // Use last path segment as display name
            const parts = repoPath.replace(/\/+$/, '').split('/');
            const slug = parts[parts.length - 1] || repoPath;
            const name = slug.charAt(0).toUpperCase() + slug.slice(1);
            if (!groups[slug]) {
                groups[slug] = { name, slug, repoPath, scans: [] };
            }
            groups[slug].scans.push(scan);
        }
        return Object.values(groups);
    },

    /** Load the Scan tab sidebar: repos grouped with framework badges (matches demo layout). */
    async loadScanSidebar() {
        const list = document.getElementById('sidebar-scan-list');
        if (!list) return;

        const history = this._scanHistory || await this._fetchScanHistory();
        if (!history || history.length === 0) {
            list.innerHTML = '<div class="sidebar-panel-empty">No scans yet. Start your first scan.</div>';
            return;
        }

        const repos = this._groupByRepo(history);
        let html = '';

        // Programs section in sidebar (self-hosted only)
        if (!(this.capabilities && this.capabilities.demo_mode)) {
            let programs = [];
            try { programs = await complyApi.listPrograms() || []; } catch (e) { /* ignore */ }
            if (programs.length > 0) {
                html += '<div class="sidebar-section-label">Programs</div>';
                for (const prog of programs) {
                    const repoCount = (prog.repos || []).length;
                    const fwCount = (prog.frameworks || []).length;
                    html += '<a href="#/program/' + prog.id + '" class="sidebar-program-item" onclick="event.stopPropagation();">' +
                        '<span class="sidebar-program-name">' + (prog.name || 'Untitled') + '</span>' +
                        '<span class="sidebar-program-meta">' + repoCount + ' repo' + (repoCount !== 1 ? 's' : '') +
                        ' \u00b7 ' + fwCount + ' fw</span></a>';
                }
                html += '<div class="sidebar-section-divider"></div>';
            }
            // Show "+ New Program" when 2+ repos or programs already exist
            if (repos.length >= 2 || programs.length > 0) {
                if (programs.length === 0) html += '<div class="sidebar-section-label">Programs</div>';
                html += '<a href="#/program" class="sidebar-program-add" onclick="event.stopPropagation();">+ New Program</a>';
                if (programs.length === 0) html += '<div class="sidebar-section-divider"></div>';
            }
            if (repos.length > 0) {
                html += '<div class="sidebar-section-label">Repositories</div>';
            }
        }

        for (const repo of repos) {
            // Group scans by framework within this repo (normalize IDs)
            const fwGroups = {};
            for (const scan of repo.scans) {
                const fw = typeof fwNorm === 'function' ? fwNorm(scan.framework || 'unknown') : (scan.framework || 'unknown');
                if (!fwGroups[fw]) fwGroups[fw] = [];
                fwGroups[fw].push(scan);
            }

            // Framework tiles (reuses demo's .repo-sidebar-fw-tile classes)
            let fwTiles = '';
            for (const [fw, scans] of Object.entries(fwGroups)) {
                const latest = scans[0];
                const score = latest.score != null ? Math.round(latest.score) : null;
                const scoreColor = score !== null
                    ? (score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)')
                    : '';
                // Trend arrow: compare two most recent scans for this framework
                let trendHtml = '';
                if (scans.length >= 2) {
                    const prevScore = scans[1].score != null ? Math.round(scans[1].score) : null;
                    if (score !== null && prevScore !== null) {
                        if (score > prevScore) trendHtml = '<span class="repo-sidebar-trend up">\u2191</span>';
                        else if (score < prevScore) trendHtml = '<span class="repo-sidebar-trend down">\u2193</span>';
                        else trendHtml = '<span class="repo-sidebar-trend flat">\u2192</span>';
                    }
                }

                const scoreHtml = score !== null
                    ? '<span class="repo-sidebar-fw-score" style="color:' + scoreColor + '">' + score + '%' + trendHtml + '</span>'
                    : '';
                const label = typeof fwLabel === 'function' ? fwLabel(fw) : fw.replace(/_/g, ' ');

                // Depth dots (blue = structure, purple = semantic, gray = missing)
                const hasStructure = scans.some(s => (s.scan_depth || s.depth || '').includes('structure'));
                const hasSemantic = scans.some(s => (s.scan_depth || s.depth || '').includes('semantic'));
                const dots = '<span class="repo-sidebar-dot ' + (hasStructure ? 'structure' : 'missing') + '" title="Structure"></span>' +
                    '<span class="repo-sidebar-dot ' + (hasSemantic ? 'semantic' : 'missing') + '" title="Semantic"></span>';

                // Build href: compare view if both depths, else detail of latest
                let href;
                if (hasStructure && hasSemantic) {
                    const structScan = scans.find(s => (s.scan_depth || s.depth || '').includes('structure'));
                    const semScan = scans.find(s => (s.scan_depth || s.depth || '').includes('semantic'));
                    href = '#/diff/' + structScan.id + '/' + semScan.id;
                } else {
                    href = '#/detail/' + latest.id;
                }

                fwTiles += '<a href="' + href + '" class="repo-sidebar-fw-tile" data-scan-id="' + latest.id + '"' +
                    ' onclick="event.stopPropagation();">' +
                    '<span class="repo-sidebar-fw-label">' + label + '</span>' +
                    '<span class="repo-sidebar-fw-right">' + scoreHtml + dots + '</span></a>';
            }

            // Default click navigates to first framework's view
            const firstScans = Object.values(fwGroups)[0];
            const defaultHref = firstScans && firstScans[0] ? '#/detail/' + firstScans[0].id : '#/scan';

            // Repo-level links (Compare, Progress)
            const fwKeys = Object.keys(fwGroups);
            const repoLinks = [];
            if (fwKeys.length >= 2) {
                const slug = encodeURIComponent(repo.slug);
                repoLinks.push('<a href="#/overlap/' + slug + '" class="repo-sidebar-overlap-link"' +
                    ' onclick="event.stopPropagation();">Compare ' + fwKeys.length + ' Frameworks</a>');
            }
            if (repo.scans.length >= 2) {
                const slug = encodeURIComponent(repo.slug);
                repoLinks.push('<a href="#/progress/' + slug + '" class="repo-sidebar-overlap-link"' +
                    ' onclick="event.stopPropagation();">Progress (' + repo.scans.length + ' scans)</a>');
            }
            const linksHtml = repoLinks.length > 0
                ? '<div class="repo-sidebar-links">' + repoLinks.join('') + '</div>'
                : '';

            html += '<div class="repo-sidebar-item" onclick="window.location.hash=\'' + defaultHref + '\';">' +
                '<div style="flex:1;min-width:0">' +
                '<div class="repo-sidebar-name">' + repo.name + '</div>' +
                (fwTiles ? '<div class="repo-sidebar-fw-stack">' + fwTiles + '</div>' : '') +
                linksHtml +
                '</div></div>';
        }

        list.innerHTML = html;
        this._highlightScanSidebar();
    },

    /** Highlight active nav items in ops/config panels based on current route. */
    _highlightNavItems() {
        const hash = window.location.hash || '';
        document.querySelectorAll('.sidebar-nav-item').forEach(item => {
            const route = item.dataset.route || '';
            item.classList.toggle('active', route && hash.includes(route));
        });
        // Highlight individual monitor in sidebar
        const monitorId = hash.startsWith('#/monitor/') ? hash.split('/')[2] : '';
        document.querySelectorAll('.sidebar-monitor-item').forEach(item => {
            item.classList.toggle('active', monitorId && item.dataset.monitorId === monitorId);
        });
    },

    /** Highlight the scan sidebar tile matching the current hash route. */
    _highlightScanSidebar() {
        const panel = document.getElementById('sidebar-scan-list');
        if (!panel) return;
        const hash = window.location.hash || '';

        panel.querySelectorAll('.repo-sidebar-item').forEach(i => i.classList.remove('active'));
        panel.querySelectorAll('.repo-sidebar-fw-tile').forEach(t => t.classList.remove('active'));
        if (!hash) return;

        // Exact href match
        let matched = false;
        panel.querySelectorAll('.repo-sidebar-fw-tile').forEach(tile => {
            if (tile.getAttribute('href') === hash) {
                tile.classList.add('active');
                const item = tile.closest('.repo-sidebar-item');
                if (item) item.classList.add('active');
                matched = true;
            }
        });

        // Fuzzy match: for /detail/ and /diff/ routes, match by scan ID
        if (!matched && (hash.startsWith('#/diff/') || hash.startsWith('#/detail/'))) {
            const scanId = hash.split('/')[2] || '';

            // First try: direct scan ID substring match in tile hrefs
            panel.querySelectorAll('.repo-sidebar-fw-tile').forEach(tile => {
                const tileHref = tile.getAttribute('href') || '';
                if (scanId && tileHref.includes(scanId)) {
                    tile.classList.add('active');
                    const item = tile.closest('.repo-sidebar-item');
                    if (item) item.classList.add('active');
                    matched = true;
                }
            });

            // Second try: look up scan in history and match by repo+framework
            if (!matched && this._scanHistory) {
                const scan = this._scanHistory.find(s => s.id === scanId);
                if (scan) {
                    const repoPath = scan.repo || scan.repo_url || '';
                    const parts = repoPath.replace(/\/+$/, '').split('/');
                    const slug = parts[parts.length - 1] || '';
                    const fw = typeof fwNorm === 'function' ? fwNorm(scan.framework || '') : (scan.framework || '');

                    panel.querySelectorAll('.repo-sidebar-item').forEach(item => {
                        const name = (item.querySelector('.repo-sidebar-name') || {}).textContent || '';
                        if (slug && name.toLowerCase() === slug.toLowerCase()) {
                            item.classList.add('active');
                            // Try to highlight the specific framework tile
                            item.querySelectorAll('.repo-sidebar-fw-tile').forEach(tile => {
                                const tileLabel = (tile.querySelector('.repo-sidebar-fw-label') || {}).textContent || '';
                                const fwDisplay = typeof fwLabel === 'function' ? fwLabel(fw) : fw;
                                if (tileLabel === fwDisplay) {
                                    tile.classList.add('active');
                                }
                            });
                            matched = true;
                        }
                    });
                }
            }
        }

        // Match overlap/progress routes by repo slug
        if (!matched && (hash.startsWith('#/overlap/') || hash.startsWith('#/progress/'))) {
            const slug = decodeURIComponent(hash.split('/')[2] || '');
            panel.querySelectorAll('.repo-sidebar-item').forEach(item => {
                const name = (item.querySelector('.repo-sidebar-name') || {}).textContent || '';
                if (slug && name.toLowerCase() === slug.toLowerCase()) {
                    item.classList.add('active');
                    matched = true;
                }
            });
        }
    },

    /** Track the selected repo context and show/hide content sub-tabs. */
    _updateRepoContext() {
        const hash = window.location.hash || '';
        const subtabs = document.getElementById('content-subtabs');
        if (!subtabs) return;

        // Find which repo is active by matching scan IDs in the hash
        if (!this._scanHistory) { subtabs.style.display = 'none'; return; }

        let matchedRepo = null;
        const scanId = hash.split('/')[2] || '';

        if (scanId && (hash.startsWith('#/detail/') || hash.startsWith('#/diff/'))) {
            // Find the scan in history
            const scan = this._scanHistory.find(s => s.id === scanId);
            if (scan) {
                const repoPath = scan.repo || scan.repo_url || '';
                const repos = this._groupByRepo(this._scanHistory);
                matchedRepo = repos.find(r => r.repoPath === repoPath);
            }
        } else if (hash.startsWith('#/history') || hash.startsWith('#/forecast')) {
            // Keep subtabs visible when navigated via subtab with repo context
            const params = new URLSearchParams(hash.split('?')[1] || '');
            const repo = params.get('repo');
            if (repo && this._selectedRepo && this._selectedRepo.repoPath === repo) {
                matchedRepo = this._selectedRepo;
            }
        }

        if (matchedRepo && matchedRepo.scans.length >= 2) {
            this._selectedRepo = matchedRepo;
            subtabs.style.display = 'flex';

            // Determine which subtab is active based on current route
            const route = hash.replace('#', '').split('/')[1] || '';
            subtabs.querySelectorAll('.content-subtab').forEach(tab => {
                const isActive =
                    (tab.dataset.subtab === 'compare' && (route === 'detail' || route === 'diff')) ||
                    (tab.dataset.subtab === 'history' && route === 'history') ||
                    (tab.dataset.subtab === 'forecast' && route === 'forecast');
                tab.classList.toggle('active', isActive);
            });
        } else {
            this._selectedRepo = null;
            subtabs.style.display = 'none';
        }
    },

    /** Handle content sub-tab clicks. */
    switchContentTab(tab) {
        const repo = this._selectedRepo;
        if (!repo) return;

        const repoPath = encodeURIComponent(repo.repoPath);
        if (tab === 'compare') {
            // Navigate to diff view if structure+semantic exist, else detail
            const fwGroups = {};
            for (const scan of repo.scans) {
                const fw = typeof fwNorm === 'function' ? fwNorm(scan.framework || 'unknown') : (scan.framework || 'unknown');
                if (!fwGroups[fw]) fwGroups[fw] = [];
                fwGroups[fw].push(scan);
            }
            const firstFw = Object.values(fwGroups)[0] || [];
            const struct = firstFw.find(s => (s.scan_depth || s.depth || '').includes('structure'));
            const sem = firstFw.find(s => (s.scan_depth || s.depth || '').includes('semantic'));
            if (struct && sem) {
                window.location.hash = '#/diff/' + struct.id + '/' + sem.id;
            } else if (firstFw[0]) {
                window.location.hash = '#/detail/' + firstFw[0].id;
            }
        } else if (tab === 'history') {
            window.location.hash = '#/history?repo=' + repoPath;
        } else if (tab === 'forecast') {
            window.location.hash = '#/forecast?repo=' + repoPath;
        }
    },

    /** Load the Ops tab sidebar: flat list with Gate section + Monitors section. */
    async loadOpsSidebar() {
        const list = document.getElementById('sidebar-ops-list');
        if (!list) return;

        let html = '';

        // Portfolio Report link
        html += '<a href="#/posture" class="sidebar-nav-item" data-route="posture">' +
            '<span class="sidebar-nav-icon">&#128202;</span>' +
            '<span class="sidebar-nav-label">Portfolio Report</span></a>';

        // Gate section — always show as a nav item with inline stats
        html += '<a href="#/gate" class="sidebar-nav-item" data-route="gate">' +
            '<span class="sidebar-nav-icon">&#9881;</span>' +
            '<span class="sidebar-nav-label">CI/CD Gate</span>';
        try {
            const summary = await complyApi.getGateSummary();
            if (summary && (summary.total || 0) > 0) {
                html += '<span class="sidebar-nav-badge">' +
                    '<span style="color:var(--green)">' + (summary.passed || 0) + '</span>/' +
                    '<span style="color:var(--red)">' + (summary.failed || 0) + '</span>' +
                    '</span>';
            }
        } catch (e) { /* ignore */ }
        html += '</a>';

        // Watches — monitored repo+framework pairs
        html += '<a href="#/monitor" class="sidebar-nav-item" data-route="monitor">' +
            '<span class="sidebar-nav-icon">&#128065;</span>' +
            '<span class="sidebar-nav-label">Watches</span>';
        let monitors = [];
        try {
            monitors = await complyApi.getMonitors() || [];
            if (monitors.length > 0) {
                const running = monitors.filter(m => m.status === 'running').length;
                html += '<span class="sidebar-nav-badge">' + running + '/' + monitors.length + ' active</span>';
            }
        } catch (e) { /* ignore */ }
        html += '</a>';

        // Show running monitors inline
        for (const mon of monitors) {
            const repoName = (mon.repo_path || '').split('/').pop() || 'unknown';
            const statusClass = mon.status === 'running' ? 'running' : (mon.status === 'error' ? 'error' : 'stopped');
            const fwShort = typeof fwLabel === 'function' ? fwLabel(mon.framework) : (mon.framework || '').replace(/_/g, ' ');
            const scoreColor = mon.last_score != null
                ? (mon.last_score >= 70 ? 'var(--green)' : mon.last_score >= 40 ? 'var(--yellow)' : 'var(--red)')
                : '';

            html += '<div class="sidebar-monitor-item" data-monitor-id="' + mon.id + '" onclick="window.location.hash=\'#/monitor/' + mon.id + '\'">' +
                '<div class="sidebar-monitor-name">' +
                '<span class="sidebar-monitor-status ' + statusClass + '"></span> ' +
                repoName + '</div>' +
                '<div class="sidebar-monitor-meta">' +
                '<span>' + fwShort + '</span>' +
                (mon.last_score != null ? '<span style="margin-left:auto;color:' + scoreColor + ';font-weight:600">' + Math.round(mon.last_score) + '%</span>' : '') +
                '</div>' +
                '</div>';
        }

        list.innerHTML = html;

        // Highlight active route
        const hash = window.location.hash || '';
        list.querySelectorAll('.sidebar-nav-item').forEach(item => {
            const route = item.dataset.route || '';
            item.classList.toggle('active', hash.includes(route));
        });
    },

    /** Render the Config panel — flat list of settings links. */
    _renderConfigPanel() {
        const list = document.getElementById('sidebar-config-list');
        if (!list) return;

        const hash = window.location.hash || '';
        const items = [
            { route: 'settings', href: '#/settings', icon: '&#9881;', label: 'Settings' },
            { route: 'mapping', href: '#/mapping', icon: '&#128506;', label: 'Control Mapping' },
        ];

        list.innerHTML = items.map(item =>
            '<a href="' + item.href + '" class="sidebar-nav-item' +
            (hash.includes(item.route) ? ' active' : '') +
            '" data-route="' + item.route + '">' +
            '<span class="sidebar-nav-icon">' + item.icon + '</span>' +
            '<span class="sidebar-nav-label">' + item.label + '</span></a>'
        ).join('');
    },

    /** Initialize the tab system for self-hosted mode. */
    initTabs() {
        if (this._tabsInitialized) return;
        this._tabsInitialized = true;

        // Register afterNavigate hook for auto-tab-switching + active state + subtabs
        Router.afterNavigate((route) => {
            this._autoSwitchTab(route);
            this._highlightScanSidebar();
            this._highlightNavItems();
            this._updateRepoContext();
        });

        // Also highlight on hashchange (covers direct navigation)
        window.addEventListener('hashchange', () => {
            this._highlightScanSidebar();
            this._highlightNavItems();
            this._updateRepoContext();
        });

        // Load initial tab content
        this._fetchScanHistory().then(() => {
            this.loadScanSidebar();
            this._updateRepoContext();
        });

        // Drag-to-resize sidebar
        this._initSidebarResize();
    },

    /** Clear all scan history (self-hosted mode). */
    async clearScanHistory() {
        if (!confirm('Delete all scan history? This cannot be undone.')) return;
        try {
            await complyApi.clearHistory();
            this._scanHistory = null;
            await this.refreshScanSidebar();
            window.location.hash = '#/landing';
        } catch (e) {
            alert('Failed to clear history: ' + e.message);
        }
    },

    /** Navigate to New Scan, pre-filling repo if one is currently selected. */
    newScanWithContext() {
        if (this._selectedRepo && this._selectedRepo.repoPath) {
            window.location.hash = '/scan?repo=' + encodeURIComponent(this._selectedRepo.repoPath);
        } else {
            window.location.hash = '/scan';
        }
    },

    /** Invalidate cached history and refresh the current scan sidebar. */
    async refreshScanSidebar() {
        this._scanHistory = null;
        // Also refresh ScanAdapter's server cache so shared views stay in sync
        if (!ScanAdapter._demoMode) await ScanAdapter._refreshServerCache();
        await this._fetchScanHistory();
        if (this._currentTab === 'repos') this.loadScanSidebar();
    },

    /** Show the "Last Result" nav link pointing to a scan detail or compare view. */
    setLastResult(scanId) {
        if (!scanId) return;
        localStorage.setItem('comply_last_scan', scanId);

        // Check if we now have a compare pair
        const pair = this._findComparePair(scanId);
        if (pair) {
            localStorage.setItem('comply_last_compare', JSON.stringify(pair));
            this._showLastResultLink(null, pair);
            return;
        }

        localStorage.removeItem('comply_last_compare');
        this._showLastResultLink(scanId);
    },

    /** Find a structure+semantic pair for the given scan ID. */
    _findComparePair(scanId) {
        return ScanAdapter.findComparePair(scanId);
    },

    _showLastResultLink(scanId, comparePair) {
        const li = document.getElementById('nav-last-result');
        if (!li) return;
        const a = li.querySelector('a');
        if (a) {
            if (comparePair) {
                a.href = `#/diff/${comparePair.structureId}/${comparePair.semanticId}`;
                a.textContent = 'Compare';
            } else {
                a.href = `#/detail/${scanId}`;
                a.textContent = 'Results';
            }
        }
        li.style.display = '';
    },

    // --- Mode initialization: called once from initApp() ---

    /** Demo mode: legacy sidebar nav, LandingView as home, hide self-hosted chrome. */
    _initDemoMode() {
        document.body.classList.add('demo-mode');
        Router.setDefaultRoute('/landing');
        Router.on('/landing', () => LandingView.render());
        Router.on('/scan', () => LandingView.render());
        Router.on('/history', () => LandingView.render());
        document.querySelectorAll('[data-demo-hide]').forEach(el => el.style.display = 'none');
        const tabsEl = document.getElementById('sidebar-tabs');
        if (tabsEl) tabsEl.style.display = 'none';
        const panelsEl = document.querySelector('.sidebar-panels');
        if (panelsEl) panelsEl.style.display = 'none';
        const subtabsEl = document.getElementById('content-subtabs');
        if (subtabsEl) subtabsEl.style.display = 'none';
        const legacyNav = document.getElementById('legacy-nav');
        if (legacyNav) legacyNav.style.display = '';
        this.initSidebar();
        this._initKeyboardNav();
    },

    /** Self-hosted mode: 3-tab sidebar, HomeView as home, hide demo chrome. */
    _initSelfHostedMode() {
        this.restoreLastResult();
        document.querySelectorAll('[data-demo-only]').forEach(el => el.style.display = 'none');
        this.initTabs();
    },

    /** Toggle Alice panel expand/collapse. */
    toggleAlice() {
        if (window._alice) window._alice.toggle();
    },

    /** Send message to Alice from input field. */
    sendToAlice() {
        if (window._alice) window._alice.sendMessage();
    },

    /** Trigger an Alice shortcut. */
    aliceShortcut(text) {
        if (window._alice) window._alice.shortcut(text);
    },

    initSidebar() {
        if (!ScanAdapter) return;
        const sidebar = document.getElementById('repo-sidebar');
        const toggle = document.getElementById('sidebar-toggle');
        if (!sidebar) return;

        sidebar.style.display = '';
        if (toggle) toggle.style.display = '';

        // Add grid class to content area
        const contentArea = sidebar.parentElement;
        if (contentArea) contentArea.classList.add('app-layout-with-sidebar');

        this.refreshSidebar();

        // Highlight active fw-tile on route changes
        window.addEventListener('hashchange', () => this.highlightCurrentRoute());
    },

    /** Refresh the sidebar repo list. */
    refreshSidebar() {
        if (!ScanAdapter) return;
        const list = document.getElementById('repo-sidebar-list');
        if (!list) return;

        const repos = ScanAdapter.listRepos();
        const userRepos = repos.filter(r => r.source === 'user');
        const demoRepos = repos.filter(r => r.source === 'demo');

        let html = '';

        if (userRepos.length > 0) {
            html += '<div class="repo-sidebar-divider">Your Scans</div>';
            for (const repo of userRepos) {
                html += this._renderSidebarItem(repo);
            }
        }

        if (demoRepos.length > 0) {
            html += '<div class="repo-sidebar-divider">Demo Repos</div>';
            for (const repo of demoRepos) {
                html += this._renderSidebarItem(repo);
            }
        }

        list.innerHTML = html || '<div style="padding:16px;color:var(--text-muted);font-size:13px">No scans yet</div>';

        // Render sidebar footer (clear button + privacy notice)
        let footer = document.getElementById('repo-sidebar-footer');
        if (!footer) {
            footer = document.createElement('div');
            footer.id = 'repo-sidebar-footer';
            footer.className = 'repo-sidebar-footer';
            const sidebar = document.getElementById('repo-sidebar');
            if (sidebar) sidebar.appendChild(footer);
        }
        const hasUserScans = userRepos.length > 0;
        footer.innerHTML = `
            ${hasUserScans ? '<button class="sidebar-clear-btn" onclick="App.clearMyScans()">Clear My Scans</button>' : ''}
            <div class="sidebar-privacy-notice">Scan results encrypted in your browser. No plaintext data on our servers.</div>
        `;

        // Highlight the tile matching current route
        this.highlightCurrentRoute();
    },

    /** Delete a single scan by id. */
    async deleteScan(id, event) {
        if (event) { event.stopPropagation(); event.preventDefault(); }
        if (!ScanAdapter) return;
        ScanAdapter.remove(id);
        const hash = window.location.hash || '';
        if (hash.includes(id)) {
            window.location.hash = '/landing';
        } else if (hash.includes('/landing') || hash === '' || hash === '#/') {
            const sr = document.getElementById('scan-results');
            const ir = document.getElementById('import-results');
            if (sr) sr.innerHTML = '';
            if (ir) ir.innerHTML = '';
        }
        this.refreshSidebar();
    },

    /** Delete all scans for a repo (by scan ID list). */
    deleteRepoScans(ids) {
        if (!ids || !ids.length) return;
        if (!ScanAdapter) return;
        for (const id of ids) ScanAdapter.remove(id);
        const hash = window.location.hash || '';
        if (ids.some(id => hash.includes(id))) {
            window.location.hash = '/landing';
        } else if (hash.includes('/landing') || hash === '' || hash === '#/') {
            // On landing page: clear displayed results since they may belong to deleted scan
            const sr = document.getElementById('scan-results');
            const ir = document.getElementById('import-results');
            if (sr) sr.innerHTML = '';
            if (ir) ir.innerHTML = '';
        }
        this.refreshSidebar();
    },

    /** Clear all visitor scans (server + local). */
    async clearMyScans() {
        if (!confirm('Delete all your scan history?')) return;
        if (typeof UserScans !== 'undefined') {
            await UserScans.clear();
        }
        localStorage.removeItem('comply_last_scan');
        localStorage.removeItem('comply_last_compare');
        const li = document.getElementById('nav-last-result');
        if (li) li.style.display = 'none';
        this.refreshSidebar();
        window.location.hash = '/landing';
    },

    /** Resolve the best view href for a specific repo + framework. */
    _fwHref(repo, fw) {
        if (!ScanAdapter) return '#/landing';
        const allScans = ScanAdapter.list();
        const repoScans = allScans.filter(s =>
            (s.repoSlug === repo.slug || (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').endsWith(repo.slug)) &&
            s.framework === fw.fw
        );
        const struct = repoScans.find(s => (s.depth || '').includes('structure'));
        const sem = repoScans.find(s => (s.depth || '').includes('semantic'));
        if (struct && sem) return `#/diff/${struct.id}/${sem.id}`;
        const latest = repoScans[0];
        if (latest) return `#/detail/${latest.id}`;
        return '#/landing';
    },

    _renderSidebarItem(repo) {
        const fwTiles = repo.frameworks.map(fw => {
            const href = this._fwHref(repo, fw);
            const label = typeof fwLabel === 'function' ? fwLabel(fw.fw) : fw.fw;
            const score = fw.latestScan ? Math.round(fw.latestScan.score || 0) : null;
            const scoreColor = score !== null
                ? (score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)')
                : '';
            const scoreHtml = score !== null
                ? `<span class="repo-sidebar-fw-score" style="color:${scoreColor}">${score}%</span>`
                : '';
            const dots = [
                `<span class="repo-sidebar-dot ${fw.hasStructure ? 'structure' : 'missing'}" title="Structure"></span>`,
                `<span class="repo-sidebar-dot ${fw.hasSemantic ? 'semantic' : 'missing'}" title="Semantic"></span>`,
            ].join('');
            return `<a href="${href}" class="repo-sidebar-fw-tile"
                       onclick="event.stopPropagation(); App.highlightSidebarItem(this.closest('.repo-sidebar-item'));">
                       <span class="repo-sidebar-fw-label">${label}</span>
                       <span class="repo-sidebar-fw-right">${scoreHtml}${dots}</span></a>`;
        }).join('');

        // Default href: navigate to first framework's detail view if available
        let defaultHref;
        if (repo.frameworks.length > 0) {
            const fwHref = this._fwHref(repo, repo.frameworks[0]);
            defaultHref = fwHref !== '#/landing' ? fwHref : (repo.source === 'demo' ? '#/landing' : `#/landing?repo=${encodeURIComponent(repo.slug)}`);
        } else {
            defaultHref = repo.source === 'demo' ? '#/landing' : `#/landing?repo=${encodeURIComponent(repo.slug)}`;
        }

        // Repo-level links
        const slug = encodeURIComponent(repo.slug);
        const repoLinks = [];
        if (repo.frameworks.length >= 2) {
            repoLinks.push(`<a href="#/overlap/${slug}" class="repo-sidebar-overlap-link"
                  onclick="event.stopPropagation(); App.highlightSidebarItem(this.closest('.repo-sidebar-item'));">
                  Compare ${repo.frameworks.length} Frameworks</a>`);
        }
        // Count total scans for this repo
        const totalScans = ScanAdapter
            ? ScanAdapter.list().filter(s => {
                const sSlug = s.repoSlug || (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').replace(/.*\//, '');
                return sSlug === repo.slug;
              }).length
            : 0;
        if (totalScans >= 2) {
            repoLinks.push(`<a href="#/progress/${slug}" class="repo-sidebar-overlap-link"
                  onclick="event.stopPropagation(); App.highlightSidebarItem(this.closest('.repo-sidebar-item'));">
                  Progress (${totalScans} scans)</a>`);
        }
        const linksHtml = repoLinks.length > 0
            ? `<div class="repo-sidebar-links">${repoLinks.join('')}</div>`
            : '';

        // Delete button for user scans: collect scan IDs for this repo
        let deleteBtn = '';
        if (repo.source === 'user') {
            const scanIds = ScanAdapter.list()
                .filter(s => {
                    const sSlug = s.repoSlug || (s.url || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '').replace(/.*\//, '');
                    return sSlug === repo.slug;
                })
                .map(s => s.id);
            if (scanIds.length > 0) {
                const idsJson = JSON.stringify(scanIds).replace(/"/g, '&quot;');
                deleteBtn = `<button class="repo-sidebar-delete" title="Delete scan${scanIds.length > 1 ? 's' : ''}"
                    onclick="event.stopPropagation(); App.deleteRepoScans(${idsJson});">&times;</button>`;
            }
        }

        return `
        <div class="repo-sidebar-item"
             onclick="window.location.hash='${defaultHref}'; App.highlightCurrentRoute();">
            <div style="flex:1;min-width:0">
                <div class="repo-sidebar-name">${repo.name}${deleteBtn}</div>
                ${fwTiles ? `<div class="repo-sidebar-fw-stack">${fwTiles}</div>` : ''}
                ${linksHtml}
            </div>
        </div>`;
    },

    highlightSidebarItem(el) {
        document.querySelectorAll('.repo-sidebar-item').forEach(item => item.classList.remove('active'));
        document.querySelectorAll('.repo-sidebar-fw-tile').forEach(t => t.classList.remove('active'));
        if (el) el.classList.add('active');
    },

    /** Highlight the sidebar fw-tile matching the current hash route. */
    highlightCurrentRoute() {
        const hash = window.location.hash || '';
        if (!hash) return;
        document.querySelectorAll('.repo-sidebar-item').forEach(i => i.classList.remove('active'));
        document.querySelectorAll('.repo-sidebar-fw-tile').forEach(t => t.classList.remove('active'));

        // Try exact match first
        let matched = false;
        document.querySelectorAll('.repo-sidebar-fw-tile').forEach(tile => {
            if (tile.getAttribute('href') === hash) {
                tile.classList.add('active');
                const item = tile.closest('.repo-sidebar-item');
                if (item) item.classList.add('active');
                matched = true;
            }
        });

        // Fuzzy match: for /diff/ and /detail/ routes, match by repo slug in the scan ID
        if (!matched && (hash.startsWith('#/diff/') || hash.startsWith('#/detail/'))) {
            const scanId = hash.split('/')[2] || '';
            // Extract repo slug from scan ID (e.g., "catalog-bespoketracker-eu_ai_act-semantic-v1" -> "bespoketracker")
            document.querySelectorAll('.repo-sidebar-fw-tile').forEach(tile => {
                const tileHref = tile.getAttribute('href') || '';
                const tileScanId = tileHref.split('/')[2] || '';
                // Match if both scan IDs share the same repo+framework prefix
                // Compare up to the depth segment (structure/semantic)
                const prefix = scanId.replace(/-(?:structure|semantic).*$/, '');
                const tilePrefix = tileScanId.replace(/-(?:structure|semantic).*$/, '');
                if (prefix && tilePrefix && prefix === tilePrefix) {
                    tile.classList.add('active');
                    const item = tile.closest('.repo-sidebar-item');
                    if (item) item.classList.add('active');
                    matched = true;
                }
            });
        }
    },

    openScanForm() {
        window.location.hash = '/landing';
    },

    toggleSidebar() {
        const sidebar = document.getElementById('repo-sidebar');
        if (sidebar) sidebar.classList.toggle('open');
    },

    /** Initialize drag-to-resize on the sidebar. */
    _initSidebarResize() {
        const handle = document.getElementById('sidebar-resize-handle');
        if (!handle) return;
        const sidebar = document.querySelector('.sidebar');
        const root = document.documentElement;

        // Restore saved width
        const saved = localStorage.getItem('comply-sidebar-width');
        if (saved) {
            const w = parseInt(saved, 10);
            if (w >= 200 && w <= 480) {
                root.style.setProperty('--sidebar-width', w + 'px');
            }
        }

        let startX, startW;
        const onMove = (e) => {
            const newW = Math.min(480, Math.max(200, startW + (e.clientX - startX)));
            root.style.setProperty('--sidebar-width', newW + 'px');
        };
        const onUp = () => {
            handle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            const w = parseInt(getComputedStyle(root).getPropertyValue('--sidebar-width'));
            if (w) localStorage.setItem('comply-sidebar-width', w);
        };
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            startX = e.clientX;
            startW = sidebar.offsetWidth;
            handle.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    },

    /** Keyboard navigation for sidebar: Up/Down to move, Enter to select. */
    _initKeyboardNav() {
        document.addEventListener('keydown', (e) => {
            // Only when sidebar is visible and no input focused
            const sidebar = document.getElementById('repo-sidebar');
            if (!sidebar || sidebar.style.display === 'none') return;
            const activeEl = document.activeElement;
            if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.tagName === 'SELECT')) return;

            const items = [...sidebar.querySelectorAll('.repo-sidebar-item')];
            if (items.length === 0) return;

            const current = sidebar.querySelector('.repo-sidebar-item.active');
            const idx = current ? items.indexOf(current) : -1;

            if (e.key === 'ArrowDown' || e.key === 'j') {
                e.preventDefault();
                const next = items[Math.min(idx + 1, items.length - 1)];
                if (next) {
                    items.forEach(i => i.classList.remove('active'));
                    next.classList.add('active');
                    next.scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'ArrowUp' || e.key === 'k') {
                e.preventDefault();
                const prev = items[Math.max(idx - 1, 0)];
                if (prev) {
                    items.forEach(i => i.classList.remove('active'));
                    prev.classList.add('active');
                    prev.scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'Enter') {
                if (current) {
                    e.preventDefault();
                    current.click();
                }
            }
        });
    },

    /** Restore "Last Result" link on page load. */
    async restoreLastResult() {
        // Use ScanAdapter (covers both catalog and user scans)
        if (ScanAdapter) {
            const savedPair = localStorage.getItem('comply_last_compare');
            if (savedPair) {
                try {
                    const pair = JSON.parse(savedPair);
                    if (ScanAdapter.get(pair.structureId) && ScanAdapter.get(pair.semanticId)) {
                        this._showLastResultLink(null, pair);
                        return;
                    }
                } catch (e) {}
            }
            const scans = ScanAdapter.list();
            if (scans.length > 0) {
                const pair = this._findComparePair(scans[0].id);
                if (pair) {
                    localStorage.setItem('comply_last_compare', JSON.stringify(pair));
                    this._showLastResultLink(null, pair);
                    return;
                }
                this._showLastResultLink(scans[0].id);
            }
            // No scans at all: show nothing
            return;
        }
        const saved = localStorage.getItem('comply_last_scan');
        if (saved) {
            this._showLastResultLink(saved);
            return;
        }
        // Non-demo: check server history for the most recent
        try {
            const history = await complyApi.getHistory(null, null, 1);
            if (history.length > 0) {
                const id = history[0].id;
                localStorage.setItem('comply_last_scan', id);
                this._showLastResultLink(id);
            }
        } catch (e) { /* ignore */ }
    },
};

(function() {
    // Register routes
    Router.on('/landing', () => HomeView.render());
    Router.on('/demo', () => DemoView.render());
    Router.on('/audit', () => AuditView.render());
    Router.on('/scan', () => ScanView.render());
    Router.on('/history', () => HistoryView.render());
    Router.on('/detail', (params) => DetailView.render(params));
    Router.on('/trends', () => TrendsView.render());
    Router.on('/mapping', () => MappingView.render());
    Router.on('/forecast', () => ForecastView.render());
    Router.on('/gate', () => GateView.render());
    Router.on('/monitor', (params) => {
        // If a monitor ID is passed, show detail; otherwise show list
        const id = params && params[0];
        if (id) {
            MonitorDetailView.render(id);
        } else {
            MonitorView.render();
        }
    });
    Router.on('/adapters', () => AdaptersView.render());
    Router.on('/diff', (params) => CompareView.render(params));
    Router.on('/settings', () => SettingsView.render());
    Router.on('/overlap', (params) => OverlapView.render(params));
    Router.on('/progress', (params) => ProgressView.render(params));
    Router.on('/posture', () => PostureView.render());
    Router.on('/program', (params) => ProgramView.render(params));

    // Load global state
    async function initApp() {
        // Fetch capabilities first — ScanAdapter needs mode to decide its data backend
        try {
            const caps = await complyApi._fetch('/capabilities');
            App.capabilities = caps;
        } catch (e) {
            App.capabilities = { demo_mode: false, managed: false };
        }

        // Initialize ScanAdapter — uses App.capabilities.demo_mode to pick data backend
        await ScanAdapter.init();

        try {
            const health = await complyApi.getHealth();
            const vBadge = document.getElementById('version-badge');
            if (vBadge && health.version) vBadge.textContent = `v${health.version}`;
        } catch (e) { /* ignore */ }

        // Check for LLM key -- show Alice panel if configured
        try {
            const config = await complyApi._fetch('/demo/config');
            if (config && config.llm_api_key_set) {
                const alicePanel = document.getElementById('alice-panel');
                if (alicePanel) {
                    alicePanel.style.display = '';
                    if (window._alice) window._alice.init();
                }
            }
        } catch (e) { /* ignore */ }

        if (App.capabilities.demo_mode) {
            App._initDemoMode();
        } else {
            App._initSelfHostedMode();
        }

        // Initialize co-pilot SSE connection (skips in demo mode)
        if (typeof Bridge !== 'undefined') Bridge.init();
    }

    // Offline detection
    function updateOnlineStatus() {
        let banner = document.getElementById('offline-banner');
        if (!navigator.onLine) {
            if (!banner) {
                banner = document.createElement('div');
                banner.id = 'offline-banner';
                banner.className = 'offline-banner';
                banner.innerHTML = 'You are offline. Some features may be unavailable.';
                document.body.prepend(banner);
            }
        } else if (banner) {
            banner.remove();
        }
    }
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);

    // Keyboard navigation for sidebar tabs (arrow keys)
    const tabList = document.getElementById('sidebar-tabs');
    if (tabList) {
        tabList.addEventListener('keydown', (e) => {
            const tabs = [...tabList.querySelectorAll('.sidebar-tab')];
            const idx = tabs.indexOf(document.activeElement);
            if (idx < 0) return;
            let next = -1;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % tabs.length;
            else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + tabs.length) % tabs.length;
            if (next >= 0) {
                e.preventDefault();
                tabs[next].focus();
                tabs[next].click();
            }
        });
    }

    // Set aria-live on main content for screen readers
    const mainApp = document.getElementById('app');
    if (mainApp) mainApp.setAttribute('aria-live', 'polite');

    // Start — await init so mode can set default route before router fires
    initApp().then(() => Router.start());
})();
