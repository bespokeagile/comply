/* Settings view — LLM config, adapter status, installation info, subscription */
const SettingsView = {
    async render() {
        const app = document.getElementById('app');
        app.innerHTML = '<div class="loading"><span class="spinner"></span> Loading settings...</div>';

        let config = {}, tier = {}, license = {}, adapters = [];
        try {
            const results = await Promise.allSettled([
                complyApi.getConfig(),
                complyApi.getTier(),
                complyApi.getLicense(),
                complyApi.getAdapters(),
            ]);
            config = results[0].status === 'fulfilled' ? results[0].value : {};
            tier = results[1].status === 'fulfilled' ? results[1].value : {};
            license = results[2].status === 'fulfilled' ? results[2].value : {};
            adapters = results[3].status === 'fulfilled' ? results[3].value : [];
        } catch (e) { /* defaults */ }

        const isManaged = tier.managed === true;

        app.innerHTML = `
        <div class="settings-page">
            <div class="page-header"><h2>Settings</h2></div>
            ${this._renderLLMConfig(config)}
            ${!isManaged ? this._renderAdapterStatus(adapters) : ''}
            ${this._renderInstallation(isManaged, license, tier)}
        </div>`;
    },

    /* ── LLM Configuration ── */
    _renderLLMConfig(config) {
        const provider = config.llm_provider || '';
        const model = config.llm_model || '';
        const hasKey = config.llm_api_key_set || false;
        const keyHint = config.llm_api_key_hint || '';

        const providers = [
            { value: '', label: 'Auto-detect from key' },
            { value: 'anthropic', label: 'Anthropic (Claude)' },
            { value: 'openai', label: 'OpenAI' },
            { value: 'gemini', label: 'Google Gemini' },
            { value: 'grok', label: 'xAI Grok' },
            { value: 'ollama', label: 'Ollama (local)' },
        ];

        const providerOpts = providers.map(p =>
            `<option value="${p.value}" ${p.value === provider ? 'selected' : ''}>${p.label}</option>`
        ).join('');

        return `
        <div class="card">
            <div class="card-header">LLM Configuration</div>
            <p class="settings-section-desc">
                An API key enables semantic scans -- deep AI-assisted analysis that reads your code
                and evaluates compliance with nuanced understanding. Structure scans work without a key.
            </p>
            <form id="llm-config-form" class="settings-form" onsubmit="SettingsView.saveLLMConfig(event)">
                <div class="settings-form-row">
                    <label class="settings-field">
                        <span>API Key</span>
                        <input type="password" id="cfg-api-key" class="input"
                            placeholder="${hasKey ? keyHint : 'sk-..., AIza..., xai-...'}"
                            autocomplete="off" />
                    </label>
                    <label class="settings-field settings-field-sm">
                        <span>Provider</span>
                        <select id="cfg-provider" class="input">${providerOpts}</select>
                    </label>
                    <label class="settings-field settings-field-sm">
                        <span>Model (optional)</span>
                        <input type="text" id="cfg-model" class="input"
                            value="${model}" placeholder="Default" />
                    </label>
                </div>
                <div class="settings-form-actions">
                    <button type="submit" class="btn btn-primary" id="cfg-save-btn">Save</button>
                    <span id="cfg-status" class="settings-status"></span>
                    ${hasKey ? `<span class="settings-key-badge">\u2713 Key configured</span>` : ''}
                </div>
            </form>
        </div>`;
    },

    async saveLLMConfig(e) {
        e.preventDefault();
        const btn = document.getElementById('cfg-save-btn');
        const status = document.getElementById('cfg-status');
        btn.disabled = true;
        btn.textContent = 'Saving...';
        status.textContent = '';

        const data = {};
        const key = document.getElementById('cfg-api-key').value.trim();
        const provider = document.getElementById('cfg-provider').value;
        const model = document.getElementById('cfg-model').value.trim();

        if (key) data.llm_api_key = key;
        if (provider !== undefined) data.llm_provider = provider;
        data.llm_model = model;

        if (!Object.keys(data).length) {
            status.textContent = 'Nothing to save';
            btn.disabled = false;
            btn.textContent = 'Save';
            return;
        }

        try {
            await complyApi.updateConfig(data);
            status.innerHTML = '<span style="color:var(--green)">\u2713 Saved</span>';
            // Clear the key field and refresh to show updated state
            document.getElementById('cfg-api-key').value = '';
            setTimeout(() => this.render(), 1500);
        } catch (err) {
            status.innerHTML = `<span style="color:var(--red)">${err.message}</span>`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Save';
        }
    },

    /* ── Adapter Status (folded in from standalone page) ── */
    _renderAdapterStatus(adapters) {
        if (!adapters.length) return '';

        const configured = adapters.filter(a => a.configured);
        const unconfigured = adapters.filter(a => !a.configured);

        let rows = '';
        for (const a of configured) {
            const connected = a.connected;
            const statusColor = connected ? 'var(--green)' : 'var(--yellow)';
            const statusText = connected ? 'Connected' : 'Configured';
            const isCicd = a.type === 'cicd' || ['github_actions', 'gitlab_ci'].includes(a.name);
            rows += `
            <div class="adapter-status-row">
                <span class="adapter-name">${a.name}${isCicd ? ' <span class="badge badge-accent">CI/CD</span>' : ''}</span>
                <span class="adapter-status" style="color:${statusColor}">${statusText}</span>
                <button class="btn btn-sm" onclick="SettingsView.testAdapter('${a.name}', this)">Test</button>
            </div>`;
        }

        const unconfiguredNames = unconfigured.map(a => a.name).join(', ');

        return `
        <div class="card">
            <div class="card-header">Audit Log Adapters</div>
            ${rows || '<p class="settings-section-desc">No adapters configured yet.</p>'}
            ${unconfigured.length ? `
                <p class="settings-adapter-hint">
                    Available: ${unconfiguredNames}.
                    Configure in <code>~/.comply/config.yaml</code>
                </p>` : ''}
            <div id="adapter-test-msg"></div>
        </div>`;
    },

    async testAdapter(name, btn) {
        const msg = document.getElementById('adapter-test-msg');
        if (!msg) return;
        btn.disabled = true;
        btn.textContent = 'Testing...';
        try {
            const result = await complyApi.testAdapter(name);
            msg.innerHTML = result.connected
                ? `<div class="alert alert-success">${name}: Connection OK</div>`
                : `<div class="alert alert-warn">${name}: Connection failed</div>`;
        } catch (e) {
            msg.innerHTML = `<div class="alert alert-error">${name}: ${e.message}</div>`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Test';
        }
    },

    /* ── Installation & Subscription ── */
    _renderInstallation(isManaged, license, tier) {
        if (isManaged) {
            return this._renderManagedPlan(license, tier);
        }

        return `
        <div class="card">
            <div class="card-header">Installation</div>
            <div class="settings-install-grid">
                <div class="settings-install-item">
                    <span class="settings-install-label">Mode</span>
                    <span class="settings-install-value">Self-Hosted</span>
                </div>
                <div class="settings-install-item">
                    <span class="settings-install-label">Features</span>
                    <span class="settings-install-value">All enabled (10 frameworks, 117 controls)</span>
                </div>
                <div class="settings-install-item">
                    <span class="settings-install-label">License</span>
                    <span class="settings-install-value">BSL 1.1</span>
                </div>
                <div class="settings-install-item">
                    <span class="settings-install-label">Updates</span>
                    <span class="settings-install-value" id="settings-sub-status">Not subscribed</span>
                </div>
            </div>
            <div class="settings-sub-cta">
                <p>Subscribe for early-access frameworks, evidence function improvements, and priority support.</p>
                <a href="https://bespokeagile.com/comply/pricing/" target="_blank" rel="noopener"
                   class="btn btn-secondary">View Pricing</a>
            </div>
        </div>`;
    },

    _renderManagedPlan(license, tier) {
        const currentTier = license.tier || 'free';
        const licensed = license.licensed || false;

        return `
        <div class="card">
            <div class="card-header">Plan</div>
            <div class="settings-install-grid">
                <div class="settings-install-item">
                    <span class="settings-install-label">Tier</span>
                    <span class="settings-install-value"><span class="plan-badge plan-${currentTier}">${currentTier.toUpperCase()}</span></span>
                </div>
                <div class="settings-install-item">
                    <span class="settings-install-label">Frameworks</span>
                    <span class="settings-install-value">${(tier.frameworks || []).join(', ') || 'All'}</span>
                </div>
                <div class="settings-install-item">
                    <span class="settings-install-label">Max Depth</span>
                    <span class="settings-install-value">${tier.max_depth || 'content'}</span>
                </div>
                <div class="settings-install-item">
                    <span class="settings-install-label">Exports</span>
                    <span class="settings-install-value">${(tier.exports || []).join(', ')}</span>
                </div>
            </div>
            ${licensed ? `<p style="font-size:12px;color:var(--text-muted);margin-top:8px">License: ${license.key_prefix || ''}</p>` : ''}

            <div style="margin-top:16px">
                <div class="card-header" style="font-size:14px">License Key</div>
                <div class="settings-form-row" style="margin-top:8px">
                    <input class="input" id="license-key-input"
                           placeholder="pro-xxxxxxxx-yyyyyyyy" style="font-family:monospace;flex:1" />
                    <button class="btn btn-primary" onclick="SettingsView.activate()">Activate</button>
                    ${licensed ? '<button class="btn btn-secondary" onclick="SettingsView.deactivate()">Deactivate</button>' : ''}
                </div>
                <div id="license-message" style="margin-top:8px"></div>
            </div>
        </div>`;
    },

    async activate() {
        const key = document.getElementById('license-key-input').value.trim();
        if (!key) return;
        const msgEl = document.getElementById('license-message');
        try {
            const result = await complyApi.activateLicense(key);
            msgEl.innerHTML = `<div class="alert alert-success">${result.message}</div>`;
            setTimeout(() => this.render(), 1500);
        } catch (e) {
            msgEl.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
        }
    },

    async deactivate() {
        if (!confirm('Deactivate license and revert to free tier?')) return;
        try {
            await complyApi.deactivateLicense();
            this.render();
        } catch (e) {
            document.getElementById('license-message').innerHTML =
                `<div class="alert alert-error">${e.message}</div>`;
        }
    },
};
