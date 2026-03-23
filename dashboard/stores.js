/* Unified data stores for Comply demo dashboard.
   DemoCatalog: read-only static JSON (we own).
   UserScans:   server-persisted + localStorage cache (visitor owns).
   ScanAdapter: thin merge layer consumed by all views. */

const VisitorId = {
    _KEY: 'comply_visitor_id',
    get() {
        let id = localStorage.getItem(this._KEY);
        if (!id) {
            id = crypto.randomUUID();
            localStorage.setItem(this._KEY, id);
        }
        return id;
    },
    clear() {
        localStorage.removeItem(this._KEY);
    },
    headers() {
        return { 'X-Visitor-Id': this.get() };
    },
};

const DemoCatalog = {
    _cache: new Map(),   // framework -> scans[]
    _index: null,        // catalog_index.json contents
    _allScans: [],       // flattened for fast lookups

    async init() {
        try {
            const res = await fetch('/dashboard/catalog/catalog_index.json');
            if (!res.ok) { console.warn('DemoCatalog: no catalog index found'); return; }
            this._index = await res.json();
        } catch (e) { console.warn('DemoCatalog: failed to load index', e); return; }

        const fws = this._index.frameworks || {};
        const fetches = Object.entries(fws).map(async ([fw, meta]) => {
            try {
                const r = await fetch(`/dashboard/catalog/${meta.file}`);
                if (!r.ok) return;
                const data = await r.json();
                const scans = (data.scans || []).map(s => ({ ...s, source: 'demo' }));
                this._cache.set(fw, scans);
            } catch (e) { console.warn(`DemoCatalog: failed to load ${fw}`, e); }
        });
        await Promise.all(fetches);
        this._rebuildIndex();
    },

    _rebuildIndex() {
        this._allScans = [];
        for (const scans of this._cache.values()) {
            this._allScans.push(...scans);
        }
    },

    list(framework) {
        if (framework) return this._cache.get(framework) || [];
        return this._allScans;
    },

    get(id) {
        return this._allScans.find(s => s.id === id) || null;
    },

    repos() {
        const seen = new Map();
        for (const s of this._allScans) {
            const slug = s.repoSlug || (s.url || '').replace(/.*\//, '');
            if (slug && !seen.has(slug)) {
                seen.set(slug, {
                    slug,
                    name: s.repoName || slug,
                    url: s.url || '',
                    frameworks: [],
                    has_results: true,
                });
            }
            const entry = seen.get(slug);
            if (entry && s.framework && !entry.frameworks.includes(s.framework)) {
                entry.frameworks.push(s.framework);
            }
        }
        return [...seen.values()];
    },

    /** Find a structure+semantic pair for a given repo slug and framework. */
    findPair(repoSlug, framework) {
        const scans = this._allScans.filter(s =>
            (s.repoSlug === repoSlug || (s.url || '').replace(/.*\//, '') === repoSlug) &&
            s.framework === framework
        );
        const structure = scans.find(s => (s.depth || '').includes('structure'));
        const semantic = scans.find(s => (s.depth || '').includes('semantic'));
        return { structure: structure || null, semantic: semantic || null };
    },

    async checkForUpdates() {
        try {
            const res = await fetch('/dashboard/catalog/catalog_index.json');
            if (!res.ok) return false;
            const idx = await res.json();
            if (!this._index || idx.version !== this._index.version) {
                this._index = idx;
                this._cache.clear();
                await this.init();
                return true;
            }
        } catch (e) { /* ignore */ }
        return false;
    },
};


const UserScans = {
    _KEY: 'comply_user_scans',  // legacy localStorage key (for migration)
    _localCache: [],   // metadata-only cache (synchronous access for 15+ call sites)
    _serverScans: [],  // summary list from server
    _initialized: false,

    /** Initialize: CryptoStore -> ScanDB -> migrate localStorage -> fetch server -> rebuild cache. */
    async init() {
        await CryptoStore.init();
        await ScanDB.init();

        // Migrate old localStorage data to IndexedDB (one-time)
        await this._migrateLocalStorage();

        // Fetch server summaries
        try {
            const res = await fetch('/demo/my-scans', { headers: VisitorId.headers() });
            if (res.ok) {
                this._serverScans = await res.json();
            }
        } catch (e) {
            console.warn('UserScans: server fetch failed', e);
        }

        // Rebuild local cache from IndexedDB
        await this._rebuildCache();
        this._initialized = true;
    },

    /** Encrypt report, store in IndexedDB, push encrypted blob to server. Returns scan id.
     *  Accepts both report-format (from cost-scan) and catalog-format (from DemoCatalog). */
    async save(report, opts) {
        const source = (opts && opts.source) || 'user';
        // Handle both report-format and catalog-format field names
        const id = report.scanId || report.id || crypto.randomUUID();
        const url = report.target || report.repoUrl || report.repo || report.url || '';
        const framework = report.framework || '';
        const score = (report.summary || {}).score || report.score || 0;
        const depth = report.scanDepth || report.depth || 'structure';
        const timestamp = report.generatedAt || report.timestamp || new Date().toISOString();
        const slug = report.repoSlug || (url || '').replace(/.*\//, '').replace(/\.git$/, '');
        const name = report.repoName || slug;

        // Encrypt report
        const reportJson = JSON.stringify(report);
        const encrypted = await CryptoStore.encryptToBase64(reportJson);

        const record = {
            id, url, framework, score, depth, timestamp, source,
            repoSlug: slug,
            repoName: name,
            encrypted_iv: encrypted ? encrypted.iv : null,
            encrypted_report: encrypted ? encrypted.ciphertext : null,
            // Fallback: store plaintext if encryption unavailable
            plaintext_report: encrypted ? null : reportJson,
        };

        // Persist raw import data for re-analysis against other frameworks
        if (opts && opts.importRaw != null) {
            const rawStr = typeof opts.importRaw === 'string' ? opts.importRaw : JSON.stringify(opts.importRaw);
            const encRaw = await CryptoStore.encryptToBase64(rawStr);
            if (encRaw) {
                record.encrypted_import_iv = encRaw.iv;
                record.encrypted_import_raw = encRaw.ciphertext;
            } else {
                record.plaintext_import_raw = rawStr;
            }
            record.import_format = opts.importFormat || null;
            record.import_filename = opts.importFilename || null;
        }

        await ScanDB.put(record);

        // Push encrypted blob to server (skip for demo/catalog scans)
        if (encrypted && source === 'user') {
            try {
                await fetch(`/demo/my-scans/${id}/encrypted`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', ...VisitorId.headers() },
                    body: JSON.stringify({
                        iv: encrypted.iv,
                        ciphertext: encrypted.ciphertext,
                        url, framework, score, depth, timestamp,
                    }),
                });
            } catch (e) {
                console.warn('UserScans: failed to push encrypted scan to server', e);
            }
        }

        // Update local cache (metadata only, no report blob)
        this._localCache.unshift({ id, url, framework, score, depth, timestamp, source, repoSlug: slug, repoName: name });
        if (this._localCache.length > 50) this._localCache.length = 50;

        return id;
    },

    /** Merged list: local cache + server scans (deduped). Synchronous. */
    list() {
        if (!this._initialized || this._serverScans.length === 0) return [...this._localCache];

        const seen = new Set();
        const merged = [];
        for (const s of this._localCache) { seen.add(s.id); merged.push(s); }
        for (const s of this._serverScans) {
            if (!seen.has(s.id)) { seen.add(s.id); merged.push(s); }
        }
        return merged;
    },

    /** Get scan metadata by id. Synchronous. */
    get(id) {
        const local = this._localCache.find(s => s.id === id);
        if (local) return local;
        return this._serverScans.find(s => s.id === id) || null;
    },

    /** Async get with decrypted report. IndexedDB first, server fallback. */
    async getWithReport(id) {
        // Try IndexedDB (has encrypted report)
        const record = await ScanDB.get(id);
        if (record) {
            let report = null;
            if (record.encrypted_iv && record.encrypted_report) {
                const plaintext = await CryptoStore.decryptFromBase64(record.encrypted_iv, record.encrypted_report);
                if (plaintext) {
                    try { report = JSON.parse(plaintext); } catch (e) {}
                }
            } else if (record.plaintext_report) {
                try { report = JSON.parse(record.plaintext_report); } catch (e) {}
            }
            if (report) {
                return { ...record, report };
            }
            // Have record but can't decrypt -- return metadata with unavailable flag
            return { ...record, report: null, reportUnavailable: true };
        }

        // Server fallback: fetch and try to decrypt
        try {
            const res = await fetch(`/demo/my-scans/${id}`, { headers: VisitorId.headers() });
            if (res.ok) {
                const data = await res.json();
                if (data.encrypted && data.iv && data.ciphertext) {
                    const plaintext = await CryptoStore.decryptFromBase64(data.iv, data.ciphertext);
                    if (plaintext) {
                        const report = JSON.parse(plaintext);
                        return {
                            id, url: report.target || '', framework: report.framework || '',
                            score: (report.summary || {}).score || 0,
                            depth: report.scanDepth || 'structure',
                            timestamp: report.generatedAt || '', source: 'user', report,
                        };
                    }
                    // Can't decrypt server blob
                    return { id, report: null, reportUnavailable: true, ...this.get(id) };
                }
                // Unencrypted server response (legacy)
                if (!data.encrypted && Object.keys(data).length > 2) {
                    return {
                        id, url: data.target || '', framework: data.framework || '',
                        score: (data.summary || {}).score || 0,
                        depth: data.scanDepth || 'structure',
                        timestamp: data.generatedAt || '', source: 'user', report: data,
                    };
                }
            }
        } catch (e) { /* fallback to metadata */ }
        return this.get(id);
    },

    /** Retrieve raw import data for re-analysis. Returns { raw, format, filename } or null. */
    async getImportRaw(id) {
        const record = await ScanDB.get(id);
        if (!record) return null;
        let raw = null;
        if (record.encrypted_import_iv && record.encrypted_import_raw) {
            raw = await CryptoStore.decryptFromBase64(record.encrypted_import_iv, record.encrypted_import_raw);
        } else if (record.plaintext_import_raw) {
            raw = record.plaintext_import_raw;
        }
        if (!raw) return null;
        return { raw, format: record.import_format || null, filename: record.import_filename || null };
    },

    remove(id) {
        this._localCache = this._localCache.filter(s => s.id !== id);
        this._serverScans = this._serverScans.filter(s => s.id !== id);
        ScanDB.remove(id).catch(() => {});
        // Also delete from server
        fetch(`/demo/scan/${id}`, { method: 'DELETE', headers: VisitorId.headers() }).catch(() => {});
    },

    async clear() {
        this._localCache = [];
        this._serverScans = [];
        await ScanDB.clear().catch(() => {});
        try {
            await fetch('/demo/my-scans', { method: 'DELETE', headers: VisitorId.headers() });
        } catch (e) {}
        VisitorId.clear();
    },

    /** One-time migration: localStorage -> IndexedDB (encrypt + push to server). */
    async _migrateLocalStorage() {
        try {
            const raw = localStorage.getItem(this._KEY);
            if (!raw) return;
            const oldScans = JSON.parse(raw);
            if (!Array.isArray(oldScans) || oldScans.length === 0) return;

            let migrated = 0;
            for (const scan of oldScans) {
                const report = scan.report;
                if (!report) continue;
                const id = scan.id || crypto.randomUUID();

                // Encrypt the report
                const reportJson = JSON.stringify(report);
                const encrypted = await CryptoStore.encryptToBase64(reportJson);

                const record = {
                    id,
                    url: scan.url || '',
                    framework: scan.framework || '',
                    score: scan.score || 0,
                    depth: scan.depth || 'structure',
                    timestamp: scan.timestamp || '',
                    source: 'user',
                    repoSlug: scan.repoSlug || (scan.url || '').replace(/.*\//, ''),
                    repoName: scan.repoName || (scan.url || '').replace(/.*\//, ''),
                    encrypted_iv: encrypted ? encrypted.iv : null,
                    encrypted_report: encrypted ? encrypted.ciphertext : null,
                    plaintext_report: encrypted ? null : reportJson,
                };
                await ScanDB.put(record);

                // Push encrypted blob to server
                if (encrypted) {
                    try {
                        await fetch(`/demo/my-scans/${id}/encrypted`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json', ...VisitorId.headers() },
                            body: JSON.stringify({
                                iv: encrypted.iv, ciphertext: encrypted.ciphertext,
                                url: record.url, framework: record.framework,
                                score: record.score, depth: record.depth,
                                timestamp: record.timestamp,
                            }),
                        });
                    } catch (e) { /* best effort */ }
                }
                migrated++;
            }

            // Remove old localStorage key
            localStorage.removeItem(this._KEY);
            if (migrated > 0) console.log(`UserScans: migrated ${migrated} scans from localStorage to IndexedDB`);
        } catch (e) {
            console.warn('UserScans: localStorage migration failed', e);
        }
    },

    /** Rebuild _localCache from IndexedDB (metadata only). */
    async _rebuildCache() {
        try {
            const records = await ScanDB.list(50);
            this._localCache = records.map(r => ({
                id: r.id, url: r.url, framework: r.framework, score: r.score,
                depth: r.depth, timestamp: r.timestamp, source: r.source || 'user',
                repoSlug: r.repoSlug, repoName: r.repoName,
            }));
        } catch (e) {
            console.warn('UserScans: cache rebuild failed', e);
            this._localCache = [];
        }
    },
};


const ScanAdapter = {
    _ready: false,
    _demoMode: false,
    _serverCache: [],    // self-hosted: cached server history

    async init() {
        // Detect mode from capabilities endpoint (fetched before init in most paths)
        const isDemo = (typeof App !== 'undefined' && App.capabilities && App.capabilities.demo_mode);
        this._demoMode = isDemo;

        if (isDemo) {
            // Demo mode: load static catalog + encrypted user scan store
            await DemoCatalog.init();
            await UserScans.init();
            await this._migrateOldStore();
        } else {
            // Self-hosted: fetch scan history from server API and cache it.
            // No DemoCatalog, no encrypted IndexedDB, no visitor IDs.
            await this._refreshServerCache();
        }
        this._ready = true;
    },

    /** Self-hosted: fetch scan list from server and cache locally. */
    async _refreshServerCache() {
        try {
            const history = await complyApi.getHistory(null, null, 100);
            this._serverCache = (history || []).map(s => ({
                id: s.id,
                url: s.repo_url || s.repo_path || s.repo || '',
                framework: s.framework || '',
                score: s.score || 0,
                depth: s.scan_depth || s.depth || '',
                timestamp: s.created_at || s.timestamp || '',
                source: 'server',
                repoSlug: (s.repo_url || s.repo_path || s.repo || '').replace(/.*\//, '').replace(/\.git$/, ''),
                repoName: (s.repo_url || s.repo_path || s.repo || '').replace(/.*\//, '').replace(/\.git$/, ''),
            }));
        } catch (e) {
            this._serverCache = [];
        }
    },

    /** One-time migration from old DemoStore localStorage key (demo mode only). */
    async _migrateOldStore() {
        const OLD_KEY = 'comply_demo_scans';
        try {
            const raw = localStorage.getItem(OLD_KEY);
            if (!raw) return;
            const oldScans = JSON.parse(raw);
            if (!Array.isArray(oldScans) || oldScans.length === 0) return;

            let migrated = 0;
            for (const scan of oldScans) {
                if (DemoCatalog.get(scan.id)) continue;
                if (UserScans.get(scan.id)) continue;
                if (scan.report) {
                    await UserScans.save(scan.report);
                    migrated++;
                }
            }
            localStorage.removeItem(OLD_KEY);
            if (migrated > 0) console.log(`ScanAdapter: migrated ${migrated} scans from old store`);
        } catch (e) {
            console.warn('ScanAdapter: migration failed', e);
        }
    },

    /** List scans. In demo: merges catalog + user scans. In self-hosted: uses server cache. */
    list(opts) {
        let merged;
        if (this._demoMode) {
            const demo = DemoCatalog.list(opts && opts.framework);
            const user = opts && opts.framework
                ? UserScans.list().filter(s => s.framework === opts.framework)
                : UserScans.list();
            merged = [...user, ...demo];
        } else {
            merged = [...this._serverCache];
            if (opts && opts.framework) {
                merged = merged.filter(s => s.framework === opts.framework);
            }
        }

        if (opts && opts.source) {
            merged = merged.filter(s => s.source === opts.source);
        }

        // Sort by timestamp descending (most recent first)
        merged.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
        return merged;
    },

    get(id) {
        if (this._demoMode) {
            return UserScans.get(id) || DemoCatalog.get(id) || null;
        }
        return this._serverCache.find(s => s.id === id) || null;
    },

    /** Async get with full report. Demo: decrypts from IndexedDB. Self-hosted: fetches from API. */
    async getWithReport(id) {
        if (this._demoMode) {
            const demo = DemoCatalog.get(id);
            if (demo) return demo;
            return await UserScans.getWithReport(id);
        }
        // Self-hosted: fetch report from server
        try {
            const report = await complyApi.getScanReport(id);
            if (report) return { ...this.get(id), report };
        } catch (e) {
            try {
                const stored = await complyApi.getHistoryScan(id);
                return { ...this.get(id), report: stored.report || stored };
            } catch (_) { /* fall through */ }
        }
        return this.get(id);
    },

    async save(report, opts) {
        if (this._demoMode) {
            return await UserScans.save(report, opts);
        }
        // Self-hosted: scans are saved server-side by the scan endpoint.
        // Refresh our cache to pick up the new scan.
        await this._refreshServerCache();
        return report.scanId || report.id;
    },

    /** Retrieve raw import data for re-analysis (demo only — self-hosted stores on server). */
    async getImportRaw(id) {
        if (this._demoMode) return await UserScans.getImportRaw(id);
        return null;
    },

    /** Remove a single scan by id. */
    remove(id) {
        if (this._demoMode) {
            UserScans.remove(id);
            return;
        }
        this._serverCache = this._serverCache.filter(s => s.id !== id);
    },

    /** Find a structure+semantic compare pair for a scan ID. */
    findComparePair(scanId) {
        const scan = this.get(scanId);
        if (!scan) return null;

        const isSemantic = (scan.depth || '').includes('semantic');
        const isStructure = (scan.depth || '').includes('structure');
        if (!isSemantic && !isStructure) return null;

        const matchDepth = isSemantic ? 'structure' : 'semantic';
        const allScans = this.list();
        const match = allScans.find(s =>
            s.id !== scanId &&
            s.framework === scan.framework &&
            (s.depth || '').includes(matchDepth) &&
            s.url && scan.url &&
            s.url.toLowerCase() === scan.url.toLowerCase()
        );
        if (!match) return null;

        return isSemantic
            ? { structureId: match.id, semanticId: scanId }
            : { structureId: scanId, semanticId: match.id };
    },

    isDemo(id) {
        return this._demoMode && DemoCatalog.get(id) != null;
    },

    /** List all repos with their framework/scan metadata, user repos first. */
    listRepos() {
        const allScans = this.list();
        const repoMap = new Map(); // slug -> { url, slug, name, frameworks: Map, source, latestTimestamp }

        for (const s of allScans) {
            const url = (s.repo_url || s.url || s.repo_path || '').toLowerCase().replace(/\.git$/, '').replace(/\/+$/, '');
            const slug = (s.repoSlug || url.replace(/.*\//, '') || 'unknown');
            const fw = s.framework || '';

            if (!repoMap.has(slug)) {
                repoMap.set(slug, {
                    url: s.repo_url || s.url || s.repo_path || '',
                    slug,
                    name: s.repoName || slug,
                    frameworks: new Map(),
                    source: s.source || 'user',
                    latestTimestamp: s.timestamp || s.created_at || '',
                });
            }

            const repo = repoMap.get(slug);
            // Update source: if any scan is user, mark as user
            if (s.source === 'user') repo.source = 'user';
            // Update timestamp to most recent
            const ts = s.timestamp || s.created_at || '';
            if (ts > repo.latestTimestamp) repo.latestTimestamp = ts;

            if (fw) {
                if (!repo.frameworks.has(fw)) {
                    repo.frameworks.set(fw, { fw, latestScan: null, hasStructure: false, hasSemantic: false });
                }
                const fwMeta = repo.frameworks.get(fw);
                const depth = (s.scan_depth || s.depth || '');
                if (depth.includes('structure')) fwMeta.hasStructure = true;
                if (depth.includes('semantic')) fwMeta.hasSemantic = true;
                if (!fwMeta.latestScan || ts > (fwMeta.latestScan.timestamp || fwMeta.latestScan.created_at || '')) {
                    fwMeta.latestScan = s;
                }
            }
        }

        // Convert to array, sort: user repos first (by most recent), then demo
        const repos = [...repoMap.values()].map(r => ({
            ...r,
            frameworks: [...r.frameworks.values()],
        }));
        repos.sort((a, b) => {
            if (a.source !== b.source) return a.source === 'user' ? -1 : 1;
            return (b.latestTimestamp || '').localeCompare(a.latestTimestamp || '');
        });
        return repos;
    },

    /** Normalize a repo URL for matching (client-side mirror of url_normalize.py). */
    _normalizeUrl(url) {
        if (!url) return '';
        let s = url.trim();
        // SSH -> path
        const ssh = s.match(/^git@([^:]+):(.+)$/);
        if (ssh) s = `${ssh[1]}/${ssh[2]}`;
        // Remove protocol
        s = s.replace(/^https?:\/\//, '');
        // Remove auth tokens
        s = s.replace(/^[^@]+@/, '');
        // Lowercase, strip .git, strip trailing /
        s = s.toLowerCase();
        if (s.endsWith('.git')) s = s.slice(0, -4);
        s = s.replace(/\/+$/, '');
        return s;
    },

    /** Find previous scans for a repo URL (normalized matching). */
    findByUrl(url, framework) {
        const norm = this._normalizeUrl(url);
        if (!norm) return [];
        const all = this.list();
        return all.filter(s => {
            const sNorm = this._normalizeUrl(s.url || s.repo_url || '');
            return sNorm === norm && (!framework || s.framework === framework);
        });
    },

    /** Group scans by repo+framework -> { key: [scans oldest->newest] } */
    groupByRepoFramework(scans) {
        const groups = {};
        for (const s of scans) {
            const url = (s.repo_url || s.repo_path || s.url || '').toLowerCase();
            const key = `${url}|${s.framework || ''}`;
            if (!groups[key]) groups[key] = [];
            groups[key].push(s);
        }
        for (const arr of Object.values(groups)) {
            arr.sort((a, b) => (a.created_at || a.timestamp || '').localeCompare(b.created_at || b.timestamp || ''));
        }
        return groups;
    },
};
