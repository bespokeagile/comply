/* Trends view — score-over-time charts and multi-framework comparison */
const TrendsView = {
    async render() {
        const app = document.getElementById('app');
        app.innerHTML = `
        <div class="page-header">
            <h2>Compliance Trends</h2>
            <p>Score progression and cross-framework comparison</p>
        </div>
        <div id="trends-content"><div class="loading"><span class="spinner"></span> Loading trends...</div></div>`;

        await this.loadData();
    },

    async loadData() {
        const container = document.getElementById('trends-content');
        try {
            const scans = await complyApi.getHistory(null, null, 100);
            if (!scans.length) {
                container.innerHTML = '<div class="empty-state"><h3>No scan history</h3><p>Run scans to see trends over time</p></div>';
                return;
            }

            // Group by framework
            const byFw = {};
            for (const s of scans) {
                const fw = s.framework || 'unknown';
                if (!byFw[fw]) byFw[fw] = [];
                byFw[fw].push(s);
            }

            let html = '';

            // Overall score trend chart (all frameworks combined)
            const chartData = scans
                .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''))
                .map(s => ({
                    date: s.created_at || '',
                    score: s.score || 0,
                    label: `${s.framework} (${(s.created_at || '').substring(0, 10)})`,
                }));

            html += `
            <div class="card">
                <div class="card-header">Score Over Time</div>
                <div class="chart-container">
                    ${Components.renderLineChart(chartData, 700, 220)}
                </div>
            </div>`;

            // Per-framework comparison table
            const fwSummary = Object.entries(byFw).map(([fw, scans]) => {
                const latest = scans[0];
                const scores = scans.map(s => s.score || 0);
                const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
                const trend = scores.length >= 2 ? scores[0] - scores[scores.length - 1] : 0;
                return {
                    framework: fw,
                    latest: latest.score || 0,
                    avg: avg,
                    trend: trend,
                    scans: scans.length,
                    lastDate: (latest.created_at || '').substring(0, 10),
                };
            });

            html += `
            <div class="card">
                <div class="card-header">Framework Comparison</div>
                ${Components.renderTable(
                    ['Framework', 'Latest Score', 'Avg Score', 'Trend', 'Scans', 'Last Scan'],
                    fwSummary.map(f => [
                        `<strong>${f.framework}</strong>`,
                        `<span style="color:${f.latest >= 70 ? 'var(--green)' : f.latest >= 40 ? 'var(--yellow)' : 'var(--red)'}; font-weight:600">${f.latest.toFixed(1)}%</span>`,
                        `${f.avg.toFixed(1)}%`,
                        `<span style="color:${f.trend >= 0 ? 'var(--green)' : 'var(--red)'}">${f.trend >= 0 ? '+' : ''}${f.trend.toFixed(1)}%</span>`,
                        f.scans,
                        f.lastDate,
                    ])
                )}
            </div>`;

            // Per-framework trend charts
            for (const [fw, fwScans] of Object.entries(byFw)) {
                if (fwScans.length < 2) continue;
                const fwData = fwScans
                    .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''))
                    .map(s => ({
                        date: s.created_at || '',
                        score: s.score || 0,
                        label: (s.created_at || '').substring(0, 10),
                    }));
                html += `
                <div class="card">
                    <div class="card-header">${fw} — Score Trend</div>
                    <div class="chart-container">
                        ${Components.renderLineChart(fwData, 600, 160)}
                    </div>
                </div>`;
            }

            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
        }
    },
};
