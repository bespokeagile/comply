/* Adapters view — manage audit log adapters */
const AdaptersView = {
    async render() {
        const app = document.getElementById('app');
        app.innerHTML = `
        <div class="page-header">
            <h2>Audit Log Adapters</h2>
            <p>Connect external systems for three-layer compliance evidence</p>
        </div>
        <div id="adapters-content"><div class="loading"><span class="spinner"></span> Loading adapters...</div></div>`;

        await this.loadData();
    },

    async loadData() {
        const container = document.getElementById('adapters-content');
        try {
            const [adapters, cicdSummary] = await Promise.all([
                complyApi.getAdapters(),
                complyApi.getCicdSummary().catch(() => null),
            ]);

            if (!adapters.length) {
                container.innerHTML = `
                <div class="empty-state">
                    <h3>No adapters registered</h3>
                    <p>Configure adapters in ~/.comply/config.yaml</p>
                </div>`;
                return;
            }

            // CI/CD summary panel at top
            let html = '';
            if (cicdSummary && cicdSummary.total_records > 0) {
                html += `
                <div class="card" style="margin-bottom:16px;border-left:3px solid var(--blue)">
                    <div class="card-header">CI/CD Evidence Summary</div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-top:8px">
                        <div style="text-align:center">
                            <div style="font-size:24px;font-weight:600;color:var(--text-primary)">${cicdSummary.pipelines || 0}</div>
                            <div style="font-size:11px;color:var(--text-muted)">Pipelines</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:24px;font-weight:600;color:var(--text-primary)">${cicdSummary.test_runs || 0}</div>
                            <div style="font-size:11px;color:var(--text-muted)">Test Runs</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:24px;font-weight:600;color:var(--text-primary)">${cicdSummary.deployments || 0}</div>
                            <div style="font-size:11px;color:var(--text-muted)">Deployments</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:24px;font-weight:600;color:${cicdSummary.pass_rate >= 80 ? 'var(--green)' : 'var(--yellow)'}">${cicdSummary.pass_rate || 0}%</div>
                            <div style="font-size:11px;color:var(--text-muted)">Pass Rate</div>
                        </div>
                    </div>
                </div>`;
            }

            html += adapters.map(a => this._renderAdapterCard(a)).join('');

            // Config instructions
            html += `
            <div class="card" style="margin-top:24px">
                <div class="card-header">Configuration</div>
                <div style="font-size:13px;color:var(--text-secondary)">
                    <p>Add adapter configuration to <code>~/.comply/config.yaml</code>:</p>
                    <pre style="background:var(--bg-primary);padding:12px;border-radius:4px;margin-top:8px;overflow-x:auto;font-size:12px">adapters:
  gateway:
    mode: sqlite
    db_path: ./gateway.db
  kong:
    admin_url: http://localhost:8001
  gravitee:
    management_url: http://localhost:8083/management
  file:
    paths:
      - ./audit-logs/*.jsonl
  github_actions:
    owner: myorg
    repo: myrepo
    token: ghp_...
  gitlab_ci:
    project_id: "12345"
    token: glpat-...</pre>
                </div>
            </div>`;

            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
        }
    },

    _renderAdapterCard(adapter) {
        const name = adapter.name || '?';
        const connected = adapter.connected;
        const configured = adapter.configured;
        const lastFetch = adapter.last_fetch || 'Never';
        const isCicd = adapter.type === 'cicd' || ['github_actions', 'gitlab_ci'].includes(name);

        const statusColor = connected ? 'var(--green)' : configured ? 'var(--yellow)' : 'var(--text-muted)';
        const statusText = connected ? 'Connected' : configured ? 'Configured' : 'Not configured';
        const cicdBadge = isCicd ? '<span style="display:inline-block;background:var(--blue);color:#fff;font-size:10px;padding:1px 6px;border-radius:3px;margin-left:8px;vertical-align:middle">CI/CD</span>' : '';

        return `
        <div class="card" id="adapter-${name}">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <div class="card-header" style="margin-bottom:4px">${name}${cicdBadge}</div>
                    <div style="font-size:12px;color:var(--text-muted)">
                        Status: <span style="color:${statusColor}">${statusText}</span>
                        &middot; Last fetch: ${lastFetch !== 'Never' ? lastFetch.substring(0, 19) : 'Never'}
                    </div>
                </div>
                <div class="btn-group">
                    <button class="btn btn-sm" onclick="AdaptersView.testAdapter('${name}')"
                        ${!configured ? 'disabled' : ''}>Test</button>
                    <button class="btn btn-sm btn-primary" onclick="AdaptersView.ingestAdapter('${name}')"
                        ${!configured ? 'disabled' : ''}>Ingest</button>
                </div>
            </div>
            <div id="adapter-msg-${name}" style="margin-top:8px"></div>
        </div>`;
    },

    async testAdapter(name) {
        const msg = document.getElementById(`adapter-msg-${name}`);
        if (!msg) return;
        msg.innerHTML = '<span class="spinner"></span> Testing...';
        try {
            const result = await complyApi.testAdapter(name);
            if (result.connected) {
                msg.innerHTML = '<div class="alert alert-success">Connection OK</div>';
            } else {
                msg.innerHTML = '<div class="alert alert-warn">Connection failed</div>';
            }
        } catch (e) {
            msg.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
        }
    },

    async ingestAdapter(name) {
        const msg = document.getElementById(`adapter-msg-${name}`);
        if (!msg) return;
        msg.innerHTML = '<span class="spinner"></span> Ingesting records...';
        try {
            const result = await complyApi.ingestAdapter(name);
            msg.innerHTML = `<div class="alert alert-success">Fetched ${result.fetched} records, ingested ${result.ingested}</div>`;
        } catch (e) {
            msg.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
        }
    },
};
