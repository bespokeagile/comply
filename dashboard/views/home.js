/* Self-hosted home view — situational awareness + guided next steps.
   Shown when NOT in demo mode. Demo mode uses LandingView instead.
   Two states: welcome (new user) and dashboard (returning user). */
const HomeView = {
    async render() {
        const app = document.getElementById('app');

        // Quick check: do we have scan history?
        let history = [];
        try {
            history = await complyApi.getHistory(null, null, 10);
        } catch (e) { /* empty is fine */ }

        const hasScans = history.length > 0;

        if (hasScans) {
            // Returning user: delegate to PostureView (full portfolio dashboard)
            return PostureView.render();
        }

        app.innerHTML = `
        <div class="home-container">
            ${this._renderWelcome()}
        </div>`;
    },

    /** For new users: compelling first-run experience. */
    _renderWelcome() {
        const hasApiKey = App.capabilities && App.capabilities.has_api_key;

        return `
        <div class="welcome-hero">
            <h2>See where your code stands on AI compliance.</h2>
            <p class="welcome-subtitle">Scan any repository against 10 regulatory frameworks. Structure scans are free and take 30 seconds.</p>
            <div class="welcome-quick-scan">
                <a href="#/scan" class="btn btn-primary btn-lg">Scan Your Repository</a>
            </div>
        </div>

        <div class="welcome-value-grid">
            <div class="welcome-value-card">
                <div class="welcome-value-icon">&#128269;</div>
                <strong>Find Gaps</strong>
                <p>Pattern-matching identifies compliance gaps in your code, configs, and documentation. Free for all repos.</p>
            </div>
            <div class="welcome-value-card">
                <div class="welcome-value-icon">&#129302;</div>
                <strong>AI Analysis</strong>
                <p>Semantic scans use AI to understand code intent, not just patterns. Finds gaps that static analysis misses.</p>
            </div>
            <div class="welcome-value-card">
                <div class="welcome-value-icon">&#128196;</div>
                <strong>Governance Reports</strong>
                <p>Generate audit-ready compliance reports with executive summaries, evidence, and remediation plans.</p>
            </div>
        </div>

        <div class="welcome-frameworks card">
            <div class="card-header">10 Frameworks Supported</div>
            <div class="welcome-fw-list">
                <span class="welcome-fw-pill">EU AI Act</span>
                <span class="welcome-fw-pill">SOC 2 AI</span>
                <span class="welcome-fw-pill">NIST AI RMF</span>
                <span class="welcome-fw-pill">ISO 42001</span>
                <span class="welcome-fw-pill">OWASP LLM Top 10</span>
                <span class="welcome-fw-pill">OWASP Agentic Top 10</span>
                <span class="welcome-fw-pill">California AB 2013</span>
                <span class="welcome-fw-pill">California SB 942</span>
                <span class="welcome-fw-pill">Colorado SB 24-205</span>
                <span class="welcome-fw-pill">Insurance Attestation</span>
            </div>
        </div>

        ${!hasApiKey ? `
        <div class="welcome-tip card card-info">
            <strong>Get deeper analysis</strong>
            <p>Configure your LLM API key in <a href="#/settings" style="color:var(--accent)">Settings</a> to unlock semantic scanning &mdash; AI-powered analysis that understands code intent, not just patterns.</p>
        </div>` : ''}`;
    },

    /** Returning users: posture bar + attention + repo overview + actions. */
    _renderDashboard(history, gates, monitors, gateSummary) {
        // Build repo model: group scans by repo, compute per-repo stats
        const repoMap = {};
        for (const s of history) {
            const repoKey = s.repo_path || s.repo_url || '';
            const repoName = repoKey.replace(/.*\//, '') || repoKey;
            if (!repoMap[repoKey]) {
                repoMap[repoKey] = { name: repoName, url: s.repo_url || '', path: repoKey, frameworks: {}, scanCount: 0 };
            }
            const repo = repoMap[repoKey];
            repo.scanCount++;
            const fw = fwNorm(s.framework);
            if (!repo.frameworks[fw]) {
                repo.frameworks[fw] = { scores: [], latest: null, latestDate: null, depth: '' };
            }
            const fwData = repo.frameworks[fw];
            fwData.scores.push({ score: s.score, date: s.created_at, depth: s.scan_depth });
            if (!fwData.latestDate || s.created_at > fwData.latestDate) {
                fwData.latest = s.score;
                fwData.latestDate = s.created_at;
                fwData.depth = s.scan_depth || 'content';
                fwData.scanId = s.id;
            }
        }

        // Compute aggregates
        const repos = Object.values(repoMap);
        const allFws = new Set();
        let totalLatestScores = [];
        let reposAtRisk = 0;
        for (const repo of repos) {
            let worstScore = 100;
            for (const [fw, data] of Object.entries(repo.frameworks)) {
                allFws.add(fw);
                if (data.latest !== null) {
                    totalLatestScores.push(data.latest);
                    if (data.latest < worstScore) worstScore = data.latest;
                }
            }
            if (worstScore < 70) reposAtRisk++;
        }

        const avgScore = totalLatestScores.length
            ? totalLatestScores.reduce((a, b) => a + b, 0) / totalLatestScores.length
            : 0;

        const activeMonitors = monitors.filter(m => m.status === 'running').length;
        const passRate = gateSummary.passRate || 0;
        const totalGates = gateSummary.total || 0;

        // Find attention items
        const attentionItems = this._buildAttentionItems(repos, gates, monitors);

        return `
            ${this._renderPostureBar(avgScore, reposAtRisk, repos.length, activeMonitors, passRate, totalGates)}
            ${this._renderPriorityAction(repos, history)}
            ${this._renderAttention(attentionItems)}
            ${this._renderRepoOverview(repos)}
            ${this._renderActions(monitors.length === 0, totalGates === 0)}
        `;
    },

    /** Top strip: compliance posture at a glance. */
    _renderPostureBar(avgScore, atRisk, totalRepos, activeMonitors, passRate, totalGates) {
        const scoreColor = avgScore >= 70 ? 'var(--green)' : avgScore >= 40 ? 'var(--yellow)' : 'var(--red)';
        const riskColor = atRisk > 0 ? 'var(--red)' : 'var(--green)';
        const gateColor = totalGates > 0
            ? (passRate >= 80 ? 'var(--green)' : passRate >= 50 ? 'var(--yellow)' : 'var(--red)')
            : 'var(--text-muted)';

        return `
        <div class="posture-bar">
            <div class="posture-metric">
                <span class="posture-value" style="color:${scoreColor}">${Math.round(avgScore)}%</span>
                <span class="posture-label">Avg Score</span>
            </div>
            <div class="posture-divider"></div>
            <div class="posture-metric">
                <span class="posture-value" style="color:${riskColor}">${atRisk}</span>
                <span class="posture-label">${atRisk === 1 ? 'Repo' : 'Repos'} at Risk</span>
            </div>
            <div class="posture-divider"></div>
            <div class="posture-metric">
                <span class="posture-value">${activeMonitors}</span>
                <span class="posture-label">Active Monitors</span>
            </div>
            <div class="posture-divider"></div>
            <div class="posture-metric">
                <span class="posture-value" style="color:${gateColor}">${totalGates > 0 ? passRate + '%' : '--'}</span>
                <span class="posture-label">Gate Pass Rate</span>
            </div>
        </div>`;
    },

    /** Priority-ordered attention items. */
    _buildAttentionItems(repos, gates, monitors) {
        const items = [];

        // Repos below threshold
        for (const repo of repos) {
            for (const [fw, data] of Object.entries(repo.frameworks)) {
                if (data.latest !== null && data.latest < 70) {
                    items.push({
                        severity: data.latest < 40 ? 'high' : 'medium',
                        icon: data.latest < 40 ? '\u26a0' : '\u25cf',
                        text: `<strong>${repo.name}</strong> scores ${Math.round(data.latest)}% on ${fwLabel(fw)}`,
                        action: data.scanId
                            ? `<a href="#/detail/${data.scanId}" class="attention-link">View Report</a>`
                            : '',
                        sort: data.latest,
                    });
                }
            }
        }

        // Recent gate failures
        const recentGates = gates.filter(g => g.decision === 'fail').slice(0, 3);
        for (const g of recentGates) {
            const repoName = (g.repoPath || '').replace(/.*\//, '');
            items.push({
                severity: 'high',
                icon: '\u2717',
                text: `Gate failed for <strong>${repoName}</strong> (${fwLabel(g.framework)}) at ${Math.round(g.score)}%`,
                action: g.scanId
                    ? `<a href="#/detail/${g.scanId}" class="attention-link">View Scan</a>`
                    : '',
                sort: -1,
            });
        }

        // Monitor alerts (score drops)
        const runningMonitors = monitors.filter(m => m.status === 'running');
        for (const m of runningMonitors) {
            if (m.last_score > 0 && m.last_score < 70) {
                const repoName = (m.repo_path || '').replace(/.*\//, '');
                items.push({
                    severity: 'medium',
                    icon: '\u25bc',
                    text: `Monitor on <strong>${repoName}</strong> (${fwLabel(m.framework)}) at ${Math.round(m.last_score)}%`,
                    action: `<a href="#/monitor/${m.id}" class="attention-link">View Watch</a>`,
                    sort: m.last_score,
                });
            }
        }

        // Stale repos (no scan in 30+ days)
        const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString();
        for (const repo of repos) {
            let newest = '';
            for (const data of Object.values(repo.frameworks)) {
                if (data.latestDate && data.latestDate > newest) newest = data.latestDate;
            }
            if (newest && newest < thirtyDaysAgo) {
                items.push({
                    severity: 'low',
                    icon: '\u23f0',
                    text: `<strong>${repo.name}</strong> hasn't been scanned in over 30 days`,
                    action: `<a href="#/scan" class="attention-link">Rescan</a>`,
                    sort: 200,
                });
            }
        }

        // Sort: high severity first, then by score (lower = more urgent)
        const sevOrder = { high: 0, medium: 1, low: 2 };
        items.sort((a, b) => (sevOrder[a.severity] - sevOrder[b.severity]) || (a.sort - b.sort));

        return items;
    },

    _renderAttention(items) {
        if (items.length === 0) {
            return `
            <div class="attention-card attention-clear">
                <span class="attention-icon">\u2713</span>
                <div>
                    <strong>All clear</strong>
                    <p>All repositories are above the 70% compliance threshold.</p>
                </div>
            </div>`;
        }

        const rows = items.slice(0, 5).map(item => {
            const sevClass = `attention-${item.severity}`;
            return `
                <div class="attention-row ${sevClass}">
                    <span class="attention-severity-dot"></span>
                    <span class="attention-text">${item.icon} ${item.text}</span>
                    ${item.action ? `<span class="attention-action">${item.action}</span>` : ''}
                </div>`;
        }).join('');

        return `
        <div class="attention-card">
            <h3 class="attention-title">Attention Needed</h3>
            ${rows}
            ${items.length > 5 ? `<div class="attention-overflow">${items.length - 5} more items</div>` : ''}
        </div>`;
    },

    /** Repo overview: one row per repo with framework scores. */
    _renderRepoOverview(repos) {
        if (repos.length === 0) return '';

        const rows = repos.map(repo => {
            // Collect framework badges with scores
            const fwEntries = Object.entries(repo.frameworks).map(([fw, data]) => {
                const score = data.latest !== null ? Math.round(data.latest) : null;
                const color = score !== null
                    ? (score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)')
                    : 'var(--text-muted)';

                // Compute trend from scores array
                let trend = '';
                if (data.scores.length >= 2) {
                    const sorted = [...data.scores].sort((a, b) => a.date < b.date ? -1 : 1);
                    const prev = sorted[sorted.length - 2].score;
                    const curr = sorted[sorted.length - 1].score;
                    const delta = curr - prev;
                    if (delta > 2) trend = `<span class="trend-up" title="+${Math.round(delta)}%">\u2191</span>`;
                    else if (delta < -2) trend = `<span class="trend-down" title="${Math.round(delta)}%">\u2193</span>`;
                    else trend = `<span class="trend-flat" title="stable">\u2192</span>`;
                }

                return `<span class="repo-fw-badge" title="${fwLabel(fw)}">
                    <span class="repo-fw-name">${fwLabel(fw)}</span>
                    <span class="repo-fw-score" style="color:${color}">${score !== null ? score + '%' : '--'}</span>
                    ${trend}
                </span>`;
            }).join('');

            // Last scanned date
            let lastDate = '';
            for (const data of Object.values(repo.frameworks)) {
                if (data.latestDate && data.latestDate > lastDate) lastDate = data.latestDate;
            }
            const ago = lastDate ? this._timeAgo(lastDate) : '';

            // Find a scanId to link to
            let linkScanId = '';
            for (const data of Object.values(repo.frameworks)) {
                if (data.scanId) { linkScanId = data.scanId; break; }
            }

            return `
            <div class="repo-row" ${linkScanId ? `onclick="window.location.hash='#/detail/${linkScanId}'"` : ''}>
                <div class="repo-row-name">
                    <strong>${repo.name}</strong>
                    <span class="repo-row-meta">${repo.scanCount} scan${repo.scanCount !== 1 ? 's' : ''} ${ago ? '\u00b7 ' + ago : ''}</span>
                </div>
                <div class="repo-row-frameworks">${fwEntries}</div>
                ${linkScanId ? `<button class="btn btn-sm repo-row-report" onclick="event.stopPropagation(); ReportGenerator.fromScan('${linkScanId}')" title="Generate report">Report</button>` : ''}
            </div>`;
        }).join('');

        return `
        <div class="card repo-overview">
            <h3>Repositories</h3>
            ${rows}
        </div>`;
    },

    /** Contextual quick actions. */
    _renderActions(noMonitors, noGates) {
        let contextHint = '';
        if (noMonitors && noGates) {
            contextHint = 'Set up a CI/CD gate or compliance monitor to get continuous coverage.';
        } else if (noMonitors) {
            contextHint = 'Add a compliance monitor to watch for score drift between scans.';
        } else if (noGates) {
            contextHint = 'Add a CI/CD gate to block non-compliant deploys automatically.';
        }

        return `
        <div class="home-actions">
            <a href="#/scan" class="btn btn-primary">+ New Scan</a>
            ${noGates ? `<a href="#/gate" class="btn btn-secondary">Set Up Gate</a>` : ''}
            ${noMonitors ? `<a href="#/monitor" class="btn btn-secondary">Add Monitor</a>` : ''}
            ${contextHint ? `<p class="home-actions-hint">${contextHint}</p>` : ''}
        </div>`;
    },

    /** Priority action card + progress narrative. */
    _renderPriorityAction(repos, history) {
        let html = '';

        // Find the repo+framework with the lowest score — that's the highest-impact next action
        let worst = null;
        for (const repo of repos) {
            for (const [fw, data] of Object.entries(repo.frameworks)) {
                if (data.latest !== null && (!worst || data.latest < worst.score)) {
                    worst = { repoName: repo.name, framework: fw, score: data.latest, scanId: data.scanId };
                }
            }
        }

        // Compute progress: compare oldest to newest scores for each repo+fw
        let improvedCount = 0;
        let totalDelta = 0;
        let deltaCount = 0;
        for (const repo of repos) {
            for (const [fw, data] of Object.entries(repo.frameworks)) {
                if (data.scores.length >= 2) {
                    const sorted = [...data.scores].sort((a, b) => a.date < b.date ? -1 : 1);
                    const first = sorted[0].score;
                    const last = sorted[sorted.length - 1].score;
                    const delta = last - first;
                    if (delta > 0) improvedCount++;
                    totalDelta += delta;
                    deltaCount++;
                }
            }
        }
        const avgDelta = deltaCount > 0 ? totalDelta / deltaCount : 0;

        if (worst && worst.score < 70 && worst.scanId) {
            // Next milestone: how many more % to reach 70%
            const toGo = Math.ceil(70 - worst.score);
            html += `
            <div class="priority-action-card">
                <div class="priority-action-content">
                    <strong>Next priority: ${worst.repoName} on ${typeof fwLabel === 'function' ? fwLabel(worst.framework) : worst.framework}</strong>
                    <p>Score is ${Math.round(worst.score)}% &mdash; ${toGo} points to reach the 70% compliance threshold.
                    <a href="#/detail/${worst.scanId}" class="priority-action-link">View remediation roadmap &rarr;</a></p>
                </div>
            </div>`;
        }

        // Progress narrative (only if there's history to compare)
        if (deltaCount > 0 && (avgDelta > 0 || improvedCount > 0)) {
            const direction = avgDelta >= 0 ? '+' : '';
            html += `
            <div class="progress-narrative">
                ${improvedCount > 0
                    ? `<span>${improvedCount} repo${improvedCount !== 1 ? 's' : ''} improved</span>`
                    : ''}
                ${avgDelta !== 0
                    ? `<span>${direction}${avgDelta.toFixed(1)}% avg score change</span>`
                    : ''}
                <span>${history.length} total scans</span>
            </div>`;
        }

        return html;
    },

    _timeAgo(isoDate) {
        const ms = Date.now() - new Date(isoDate).getTime();
        const mins = Math.floor(ms / 60000);
        if (mins < 60) return mins <= 1 ? 'just now' : `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        const days = Math.floor(hrs / 24);
        if (days < 30) return `${days}d ago`;
        return `${Math.floor(days / 30)}mo ago`;
    },
};
