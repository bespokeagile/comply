/* Shared: fetch unique repo paths from scan history, filtering out import artifacts.
   Also wires up focus behavior so the datalist opens fully on click. */
async function _loadRepoOptions(datalistId) {
    try {
        const history = await complyApi._fetch('/history?limit=100');
        const seen = new Set();
        const dl = document.getElementById(datalistId);
        if (!dl) return;
        const skipExts = /\.(xml|sarif|json|sbom|junit)$/i;
        (history || []).forEach(s => {
            const r = s.repo || s.repo_url || '';
            if (r && !seen.has(r) && !skipExts.test(r)) {
                seen.add(r);
                dl.innerHTML += `<option value="${r}">`;
            }
        });
        // Clear on focus so full datalist appears; restore on blur if unchanged
        const input = dl.previousElementSibling || document.querySelector(`[list="${datalistId}"]`);
        if (input) {
            let stashed = '';
            input.addEventListener('focus', () => {
                stashed = input.value;
                input.value = '';
            });
            input.addEventListener('blur', () => {
                if (!input.value && stashed) input.value = stashed;
            });
        }
    } catch (e) { /* ignore */ }
}

/* API client for Comply REST endpoints */
const complyApi = {
    baseUrl: '',

    _defaultTimeout: 30000,

    async _fetch(path, opts = {}) {
        const url = this.baseUrl + path;
        const maxRetries = (opts.method && opts.method !== 'GET') ? 0 : 2;
        const delays = [1000, 2000, 4000];
        const timeout = opts.timeout || this._defaultTimeout;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeout);
            try {
                const resp = await fetch(url, {
                    ...opts,
                    signal: controller.signal,
                    headers: { 'Content-Type': 'application/json', ...opts.headers },
                });
                clearTimeout(timer);
                if (!resp.ok) {
                    const text = await resp.text();
                    let msg = `${resp.status}: ${text}`;
                    try {
                        const json = JSON.parse(text);
                        if (json.message) msg = json.message;
                        else if (json.detail) msg = json.detail;
                    } catch (_) {}
                    const err = new Error(msg);
                    err.status = resp.status;
                    if (resp.status === 429) {
                        err.retryAfter = parseInt(resp.headers.get('Retry-After') || '60', 10);
                    }
                    // Retry on 5xx server errors for GET requests
                    if (resp.status >= 500 && attempt < maxRetries) {
                        await new Promise(r => setTimeout(r, delays[attempt]));
                        continue;
                    }
                    throw err;
                }
                return resp.json();
            } catch (e) {
                clearTimeout(timer);
                // Abort = timeout
                if (e.name === 'AbortError') {
                    if (attempt < maxRetries) {
                        await new Promise(r => setTimeout(r, delays[attempt]));
                        continue;
                    }
                    const err = new Error('Request timed out. The server may be busy — try again.');
                    err.status = 0;
                    err.isTimeout = true;
                    throw err;
                }
                // Network error (offline, DNS, etc.) — retry for GET requests
                if (e.status) throw e; // HTTP error already handled above
                if (attempt < maxRetries) {
                    await new Promise(r => setTimeout(r, delays[attempt]));
                    continue;
                }
                const err = new Error('Network error: unable to reach server. Check your connection.');
                err.status = 0;
                err.isNetwork = true;
                throw err;
            }
        }
    },

    // Scan
    async startScan(url, framework, depth, llmKey, llmProvider, noCache, baselineId) {
        const body = {
            url, framework, depth,
            llm_key: llmKey || null,
            llm_provider: llmProvider || null,
            no_cache: noCache || false,
        };
        if (baselineId) body.baseline_id = baselineId;
        return this._fetch('/scan', {
            method: 'POST',
            body: JSON.stringify(body),
        });
    },

    async getScanStatus(id) { return this._fetch(`/scan/${id}`); },
    async getScanProgress(id) { return this._fetch(`/scan/${id}/progress`); },
    async getScanReport(id) { return this._fetch(`/scan/${id}/report`); },
    async getScanRegression(id) { return this._fetch(`/scan/${id}/regression`); },

    getDownloadUrl(id, fmt) { return `${this.baseUrl}/scan/${id}/download?fmt=${fmt}`; },

    // History
    async getHistory(repo, framework, limit) {
        const params = new URLSearchParams();
        if (repo) params.set('repo', repo);
        if (framework) params.set('framework', framework);
        if (limit) params.set('limit', limit);
        return this._fetch(`/history?${params}`);
    },

    async getHistoryScan(id) { return this._fetch(`/history/${id}`); },
    async getDiff(id1, id2) { return this._fetch(`/diff?scan1=${id1}&scan2=${id2}`); },
    async setBaseline(id) { return this._fetch(`/baseline/${id}`, { method: 'POST' }); },
    async deleteScan(id) { return this._fetch(`/scan/${id}`, { method: 'DELETE' }); },
    async clearHistory() { return this._fetch('/history', { method: 'DELETE' }); },

    // Config
    async getConfig() { return this._fetch('/config'); },
    async updateConfig(data) {
        return this._fetch('/config', { method: 'PUT', body: JSON.stringify(data) });
    },

    // Frameworks
    async getFrameworks() { return this._fetch('/frameworks'); },

    // Adapters
    async getAdapters() { return this._fetch('/adapters'); },
    async testAdapter(name) { return this._fetch(`/adapters/${name}/test`, { method: 'POST' }); },
    async ingestAdapter(name, since, limit) {
        return this._fetch(`/adapters/${name}/ingest`, {
            method: 'POST',
            body: JSON.stringify({ since: since || null, limit: limit || 1000 }),
        });
    },
    async getAdapterRecords(name, limit) {
        const params = new URLSearchParams();
        if (limit) params.set('limit', limit);
        return this._fetch(`/adapters/${name}/records?${params}`);
    },

    // CI/CD
    async getCicdSummary() { return this._fetch('/cicd/summary'); },
    async getCicdRecords(limit, cicdType) {
        const params = new URLSearchParams();
        if (limit) params.set('limit', limit);
        if (cicdType) params.set('cicd_type', cicdType);
        return this._fetch(`/cicd/records?${params}`);
    },
    async ingestCicd(adapter) {
        return this._fetch('/cicd/ingest', {
            method: 'POST',
            body: JSON.stringify({ adapter: adapter || null }),
        });
    },

    // Mapping & Jurisdictions
    async getMapping(frameworks) {
        const params = new URLSearchParams();
        if (frameworks) params.set('frameworks', frameworks);
        return this._fetch(`/mapping?${params}`);
    },
    async getMappingDetail(evidenceFn) { return this._fetch(`/mapping/${evidenceFn}`); },
    async getMappingPriorities() { return this._fetch('/mapping/priorities'); },
    async getJurisdictions() { return this._fetch('/jurisdictions'); },

    // Posture
    async getPosture() { return this._fetch('/posture'); },
    async getPostureFramework(fw) { return this._fetch(`/posture/${fw}`); },

    // Cache
    async getCacheStats() { return this._fetch('/cache/stats'); },
    async clearCache() { return this._fetch('/cache', { method: 'DELETE' }); },

    // Health
    async getHealth() { return this._fetch('/health'); },

    // Predicate Audit
    async runAudit(url, framework, email) {
        return this._fetch('/audit', {
            method: 'POST',
            body: JSON.stringify({ url, framework, email: email || null }),
        });
    },

    // Monitors
    async getMonitors(status) {
        const params = new URLSearchParams();
        if (status) params.set('status', status);
        return this._fetch(`/monitors?${params}`);
    },
    async getMonitor(id) { return this._fetch(`/monitors/${id}`); },
    async createMonitor(repoPath, framework, scanDepth, intervalSecs, maxFiles, webhookUrl) {
        return this._fetch('/monitors', {
            method: 'POST',
            body: JSON.stringify({
                repo_path: repoPath,
                framework: framework || 'eu_ai_act',
                scan_depth: scanDepth || 'content',
                interval_secs: intervalSecs || 300,
                max_files: maxFiles || 500,
                webhook_url: webhookUrl || '',
            }),
        });
    },
    async updateMonitor(id, data) {
        return this._fetch(`/monitors/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    },
    async startMonitor(id) { return this._fetch(`/monitors/${id}/start`, { method: 'POST' }); },
    async stopMonitor(id) { return this._fetch(`/monitors/${id}/stop`, { method: 'POST' }); },
    async deleteMonitor(id) { return this._fetch(`/monitors/${id}`, { method: 'DELETE' }); },
    async getMonitorEvents(id, limit) {
        const params = new URLSearchParams();
        if (limit) params.set('limit', limit);
        return this._fetch(`/monitors/${id}/events?${params}`);
    },
    async getMonitorAlerts(id, limit) {
        const params = new URLSearchParams();
        if (limit) params.set('limit', limit);
        return this._fetch(`/monitors/${id}/alerts?${params}`);
    },
    async getMonitorDaemonStatus() { return this._fetch('/monitors/daemon/status'); },
    async getMonitorRecentEvents(limit) {
        const params = new URLSearchParams();
        if (limit) params.set('limit', limit);
        return this._fetch(`/monitors/events/recent?${params}`);
    },
    async getMonitorRecentAlerts(limit) {
        const params = new URLSearchParams();
        if (limit) params.set('limit', limit);
        return this._fetch(`/monitors/alerts/recent?${params}`);
    },

    // Forecast
    async getForecast(repo, framework, weeks, targetScore) {
        const params = new URLSearchParams();
        if (repo) params.set('repo', repo);
        if (framework) params.set('framework', framework);
        if (weeks) params.set('weeks', weeks);
        if (targetScore != null) params.set('target_score', targetScore);
        return this._fetch(`/forecast?${params}`);
    },

    // Gate
    async runGate(repoPath, framework, thresholdScore, failOnRegression, maxCriticalGaps) {
        return this._fetch('/gate', {
            method: 'POST',
            body: JSON.stringify({
                repo_path: repoPath,
                framework: framework || 'eu_ai_act',
                threshold_score: thresholdScore || 0,
                fail_on_regression: failOnRegression || false,
                max_critical_gaps: maxCriticalGaps != null ? maxCriticalGaps : -1,
            }),
        });
    },
    async listGateDecisions(repo, framework, limit) {
        const params = new URLSearchParams();
        if (repo) params.set('repo', repo);
        if (framework) params.set('framework', framework);
        if (limit) params.set('limit', limit);
        return this._fetch(`/gate/decisions?${params}`);
    },
    async getGateDecision(id) { return this._fetch(`/gate/${id}`); },
    async getGateSummary(repo, framework) {
        const params = new URLSearchParams();
        if (repo) params.set('repo', repo);
        if (framework) params.set('framework', framework);
        return this._fetch(`/gate/summary?${params}`);
    },

    // Narration & Chat
    async getNarrationEstimate(scanId, model) {
        const params = new URLSearchParams();
        if (model) params.set('model', model);
        return this._fetch(`/scan/${scanId}/narrate/estimate?${params}`);
    },
    async getNarration(scanId, model, llmKey, llmProvider) {
        const params = new URLSearchParams();
        if (model) params.set('model', model);
        if (llmKey) params.set('llm_key', llmKey);
        if (llmProvider) params.set('llm_provider', llmProvider);
        return this._fetch(`/scan/${scanId}/narrate?${params}`);
    },
    getNarrationStreamUrl(scanId, model, llmKey, llmProvider) {
        const params = new URLSearchParams();
        if (model) params.set('model', model);
        if (llmKey) params.set('llm_key', llmKey);
        if (llmProvider) params.set('llm_provider', llmProvider);
        return `${this.baseUrl}/scan/${scanId}/narrate/stream?${params}`;
    },
    async getChatEstimate(scanId, message, model) {
        return this._fetch('/chat/estimate', {
            method: 'POST',
            body: JSON.stringify({ scan_id: scanId, message, model: model || 'claude-sonnet-4-6' }),
        });
    },
    async sendChat(scanId, message, model, llmKey, llmProvider) {
        return this._fetch('/chat', {
            method: 'POST',
            body: JSON.stringify({
                scan_id: scanId, message,
                model: model || 'claude-sonnet-4-6',
                llm_key: llmKey || null,
                llm_provider: llmProvider || null,
            }),
        });
    },

    // Imports (SARIF, SBOM, JUnit)
    async importSarif(sarifData, framework) {
        return this._fetch('/import-sarif', {
            method: 'POST',
            body: JSON.stringify({ sarif: sarifData, framework }),
        });
    },

    async importSbom(sbomData, framework) {
        return this._fetch('/import-sbom', {
            method: 'POST',
            body: JSON.stringify({ sbom: sbomData, framework }),
        });
    },

    async importJunit(junitXml, framework) {
        return this._fetch('/import-junit', {
            method: 'POST',
            body: JSON.stringify({ junit_xml: junitXml, framework }),
        });
    },

    // Billing
    async createCheckout(tier, period, email) {
        return this._fetch('/billing/checkout', {
            method: 'POST',
            body: JSON.stringify({
                tier, billing_period: period || 'monthly', email: email || null,
            }),
        });
    },

    // Programs (portfolio)
    async listPrograms() { return this._fetch('/programs'); },
    async getProgram(id) { return this._fetch(`/programs/${id}`); },
    async createProgram(data) {
        return this._fetch('/programs', { method: 'POST', body: JSON.stringify(data) });
    },
    async updateProgram(id, data) {
        return this._fetch(`/programs/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    },
    async deleteProgram(id) {
        return this._fetch(`/programs/${id}`, { method: 'DELETE' });
    },
    async getProgramPosture(id) { return this._fetch(`/programs/${id}/posture`); },
};
