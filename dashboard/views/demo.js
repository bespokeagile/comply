/* Demo view — conversational compliance UI */
const DemoView = {
    _scanId: null,
    _scanReport: null,
    _narrated: false,

    render() {
        const app = document.getElementById('app');
        app.innerHTML = `
            <div class="demo-container">
                <div class="demo-header">
                    <h1>Comply</h1>
                    <p>AI-powered compliance scanning</p>
                </div>
                <div class="demo-thread" id="demo-thread"></div>
                <div class="demo-input-area">
                    <input type="text" class="demo-input" id="demo-input"
                           placeholder="Paste a GitHub repo URL to start..."
                           autocomplete="off" spellcheck="false">
                    <button class="demo-send-btn" id="demo-send">Scan</button>
                </div>
            </div>`;

        this._scanId = null;
        this._scanReport = null;
        this._narrated = false;

        this._addAiMessage(
            'Paste a GitHub repository URL and I\'ll tell you where you stand on AI compliance. ' +
            'The scan is free — no LLM cost, no sign-up.'
        );

        const input = document.getElementById('demo-input');
        const btn = document.getElementById('demo-send');

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._handleSend();
            }
        });
        btn.addEventListener('click', () => this._handleSend());
    },

    _handleSend() {
        const input = document.getElementById('demo-input');
        const text = input.value.trim();
        if (!text) return;

        input.value = '';

        if (!this._scanId) {
            // First message — treat as URL
            this._startScan(text);
        } else if (this._scanReport) {
            // Follow-up question
            this._sendChat(text);
        }
    },

    async _startScan(url) {
        // Validate URL loosely
        if (!url.includes('github.com') && !url.includes('gitlab.com') && !url.startsWith('http')) {
            url = 'https://github.com/' + url;
        }

        this._addUserMessage(url);
        const progressId = this._addProgress('Starting scan...');

        const input = document.getElementById('demo-input');
        const btn = document.getElementById('demo-send');
        input.disabled = true;
        btn.disabled = true;

        try {
            const { scanId } = await complyApi.startScan(url, 'eu-ai-act', 'content');
            this._scanId = scanId;

            // Poll for completion
            await this._pollScan(scanId, progressId);
        } catch (err) {
            this._removeMessage(progressId);
            this._addAiMessage('Something went wrong starting the scan: ' + err.message);
            input.disabled = false;
            btn.disabled = false;
        }
    },

    async _pollScan(scanId, progressId) {
        const input = document.getElementById('demo-input');
        const btn = document.getElementById('demo-send');

        const statusMessages = {
            pending: 'Queued...',
            cloning: 'Cloning repository...',
            scanning: 'Scanning files...',
            building: 'Building compliance model...',
            evaluating: 'Evaluating controls...',
        };

        const poll = async () => {
            try {
                const status = await complyApi.getScanStatus(scanId);

                if (status.status === 'complete') {
                    this._removeMessage(progressId);
                    await this._showResults(scanId);
                    return;
                }

                if (status.status === 'error') {
                    this._removeMessage(progressId);
                    this._addAiMessage('Scan failed: ' + (status.error || 'Unknown error'));
                    input.disabled = false;
                    btn.disabled = false;
                    return;
                }

                // Update progress
                const msg = statusMessages[status.status] || status.progress_detail || 'Working...';
                this._updateProgress(progressId, msg);
                setTimeout(poll, 1500);
            } catch (err) {
                this._removeMessage(progressId);
                this._addAiMessage('Lost connection while scanning: ' + err.message);
                input.disabled = false;
                btn.disabled = false;
            }
        };

        poll();
    },

    async _showResults(scanId) {
        const input = document.getElementById('demo-input');
        const btn = document.getElementById('demo-send');

        try {
            const report = await complyApi.getScanReport(scanId);
            this._scanReport = report;

            App.setLastResult(scanId);

            // Build score card
            const score = report.score || 0;
            const summary = report.summary || {};
            const met = summary.met || 0;
            const partial = summary.partial || 0;
            const gap = summary.gap || 0;
            const framework = report.framework || 'EU AI Act';
            const tier = score >= 70 ? 'high' : score >= 40 ? 'mid' : 'low';

            let scoreHtml = `
                <div class="demo-score-card">
                    <div class="score-value ${tier}">${score}%</div>
                    <div class="score-label">${framework} compliance</div>
                    <div class="demo-score-bar">
                        <div class="demo-score-bar-fill ${tier}" style="width: ${score}%"></div>
                    </div>
                    <div class="demo-score-breakdown">
                        <span><span class="dot met"></span>${met} met</span>
                        <span><span class="dot partial"></span>${partial} partial</span>
                        <span><span class="dot gap"></span>${gap} gap</span>
                    </div>
                </div>`;

            // Narration CTA
            let estimateHtml = '';
            try {
                const est = await complyApi.getNarrationEstimate(scanId);
                const costStr = est.estimated_cost_usd < 0.001
                    ? '$0.00 (demo)'
                    : '$' + est.estimated_cost_usd.toFixed(4);
                estimateHtml = `
                    <div class="demo-narrate-cta" id="demo-narrate-cta">
                        <div class="cost-info">
                            AI narration available<br>
                            Estimated cost: <span class="cost-amount">${costStr}</span>
                        </div>
                        <button class="demo-narrate-btn" id="demo-narrate-btn">Narrate results</button>
                    </div>`;
            } catch (e) {
                estimateHtml = `
                    <div class="demo-narrate-cta">
                        <div class="cost-info">AI narration requires an API key</div>
                    </div>`;
            }

            const msgId = this._addAiMessage(scoreHtml + estimateHtml, true);

            // Wire up narrate button
            const narrateBtn = document.getElementById('demo-narrate-btn');
            if (narrateBtn) {
                narrateBtn.addEventListener('click', () => this._doNarrate(scanId));
            }

            // Switch to chat mode
            input.placeholder = 'Ask a follow-up question...';
            input.disabled = false;
            btn.textContent = 'Send';
            btn.disabled = false;

        } catch (err) {
            this._addAiMessage('Could not load results: ' + err.message);
            input.disabled = false;
            btn.disabled = false;
        }
    },

    async _doNarrate(scanId) {
        if (this._narrated) return;
        this._narrated = true;

        const btn = document.getElementById('demo-narrate-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Narrating...';
        }

        // Try SSE streaming
        const streamUrl = complyApi.getNarrationStreamUrl(scanId);
        const msgId = this._addAiMessage('<div class="demo-narration" id="demo-narration-stream"></div>', true);
        const container = document.getElementById('demo-narration-stream');

        try {
            const es = new EventSource(streamUrl);
            let fullText = '';

            es.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.error) {
                        container.textContent = 'Narration error: ' + data.error;
                        es.close();
                        return;
                    }
                    if (data.token) {
                        fullText += data.token;
                        container.innerHTML = this._renderMarkdown(fullText);
                        this._scrollToBottom();
                    }
                    if (data.done) {
                        es.close();
                        const costStr = data.cost_usd != null
                            ? `$${data.cost_usd.toFixed(4)}`
                            : '';
                        if (costStr) {
                            container.innerHTML += `<div class="demo-cost-badge">Cost: ${costStr}</div>`;
                        }
                        // Hide CTA
                        const cta = document.getElementById('demo-narrate-cta');
                        if (cta) cta.style.display = 'none';
                    }
                } catch (e) { /* ignore parse errors */ }
            };

            es.onerror = () => {
                es.close();
                if (!fullText) {
                    container.textContent = 'Narration stream failed. Check your API key.';
                }
            };
        } catch (err) {
            container.textContent = 'Could not start narration: ' + err.message;
        }
    },

    async _sendChat(message) {
        this._addUserMessage(message);
        const progressId = this._addProgress('Thinking...');

        const input = document.getElementById('demo-input');
        const btn = document.getElementById('demo-send');
        input.disabled = true;
        btn.disabled = true;

        try {
            // Show cost estimate inline
            let costNote = '';
            try {
                const est = await complyApi.getChatEstimate(this._scanId, message);
                if (est.estimated_cost_usd > 0.001) {
                    costNote = ` ($${est.estimated_cost_usd.toFixed(4)})`;
                }
            } catch (e) { /* ignore */ }

            const result = await complyApi.sendChat(this._scanId, message);
            this._removeMessage(progressId);

            let html = this._renderMarkdown(result.response);
            if (result.cost_usd) {
                html += `<div class="demo-cost-badge">Cost: $${result.cost_usd.toFixed(4)}</div>`;
            }
            this._addAiMessage(html, true);
        } catch (err) {
            this._removeMessage(progressId);
            this._addAiMessage('Could not answer: ' + err.message);
        }

        input.disabled = false;
        btn.disabled = false;
        input.focus();
    },

    // ── DOM helpers ──────────────────────────────────────────────────

    _msgCounter: 0,

    _addAiMessage(content, isHtml) {
        const id = 'demo-msg-' + (++this._msgCounter);
        const thread = document.getElementById('demo-thread');
        const div = document.createElement('div');
        div.className = 'demo-msg ai';
        div.id = id;
        if (isHtml) {
            div.innerHTML = content;
        } else {
            div.textContent = content;
        }
        thread.appendChild(div);
        this._scrollToBottom();
        return id;
    },

    _addUserMessage(text) {
        const id = 'demo-msg-' + (++this._msgCounter);
        const thread = document.getElementById('demo-thread');
        const div = document.createElement('div');
        div.className = 'demo-msg user';
        div.id = id;
        div.textContent = text;
        thread.appendChild(div);
        this._scrollToBottom();
        return id;
    },

    _addProgress(text) {
        const id = 'demo-msg-' + (++this._msgCounter);
        const thread = document.getElementById('demo-thread');
        const div = document.createElement('div');
        div.className = 'demo-msg ai';
        div.id = id;
        div.innerHTML = `<div class="demo-progress"><div class="demo-spinner"></div><span>${text}</span></div>`;
        thread.appendChild(div);
        this._scrollToBottom();
        return id;
    },

    _updateProgress(id, text) {
        const el = document.getElementById(id);
        if (el) {
            const span = el.querySelector('.demo-progress span');
            if (span) span.textContent = text;
        }
    },

    _removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    },

    _scrollToBottom() {
        const thread = document.getElementById('demo-thread');
        if (thread) thread.scrollTop = thread.scrollHeight;
    },

    _renderMarkdown(text) {
        // Minimal markdown → HTML
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h3>$1</h3>')
            .replace(/^# (.+)$/gm, '<h3>$1</h3>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
            .replace(/<\/ul>\s*<ul>/g, '')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/^/, '<p>')
            .replace(/$/, '</p>')
            .replace(/<p><\/p>/g, '')
            .replace(/<p>(<h3>)/g, '$1')
            .replace(/(<\/h3>)<\/p>/g, '$1')
            .replace(/<p>(<ul>)/g, '$1')
            .replace(/(<\/ul>)<\/p>/g, '$1');
    },
};
