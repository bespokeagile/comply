/* AI bridge SSE client -- receives events from the AI and drives the dashboard */
const Bridge = {
    _es: null,
    _connected: false,
    _retryDelay: 1000,
    _maxRetryDelay: 30000,

    /** Called from initApp(). Skipped in demo mode. */
    init() {
        if (App.capabilities.demo_mode) return;
        this._connect();
    },

    _connect() {
        if (this._es) {
            this._es.close();
            this._es = null;
        }

        try {
            this._es = new EventSource('/bridge/events');
        } catch (e) {
            console.warn('Bridge: EventSource creation failed', e);
            this._scheduleReconnect();
            return;
        }

        this._es.onopen = () => {
            this._connected = true;
            this._retryDelay = 1000;
            this._showIndicator(true);
        };

        this._es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case 'scan-complete':
                        this._onScanComplete(data);
                        break;
                    case 'navigate':
                        this._onNavigate(data);
                        break;
                    case 'highlight':
                        this._onHighlight(data);
                        break;
                    case 'heartbeat':
                        break;
                    default:
                        console.debug('Bridge: unknown event type', data.type);
                }
            } catch (e) {
                console.warn('Bridge: parse error', e);
            }
        };

        this._es.onerror = () => {
            this._connected = false;
            this._showIndicator(false);
            this._es.close();
            this._es = null;
            this._scheduleReconnect();
        };
    },

    _scheduleReconnect() {
        setTimeout(() => this._connect(), this._retryDelay);
        this._retryDelay = Math.min(this._retryDelay * 2, this._maxRetryDelay);
    },

    // --- Event handlers ---

    _onScanComplete(data) {
        if (data.scanId) {
            Router.navigate('#/detail/' + data.scanId);
        }
    },

    _onNavigate(data) {
        if (data.route) {
            Router.navigate(data.route);
        }
    },

    _onHighlight(data) {
        const scanId = data.scanId;
        const articleId = data.articleId;
        const controlId = data.controlId;

        if (scanId && Router.currentRoute !== '/detail') {
            Router.navigate('#/detail/' + scanId);
            setTimeout(() => this._applyHighlight(articleId, controlId), 300);
        } else {
            this._applyHighlight(articleId, controlId);
        }
    },

    _applyHighlight(articleId, controlId) {
        if (typeof DetailView !== 'undefined' && DetailView._report) {
            DetailView.switchTab('controls');
        }

        setTimeout(() => {
            if (articleId) {
                const accordion = document.querySelector(`[data-article-id="${articleId}"]`);
                if (accordion && !accordion.classList.contains('open')) {
                    accordion.classList.add('open');
                }
            }

            if (controlId) {
                const row = document.querySelector(`[data-control-id="${controlId}"]`);
                if (row) {
                    row.classList.add('ai-highlight');
                    row.scrollIntoView({ behavior: 'smooth', block: 'center' });

                    const uid = 'ctrl-' + controlId.replace(/[^a-zA-Z0-9]/g, '-');
                    const detail = document.getElementById(uid + '-detail');
                    if (detail) detail.style.display = 'table-row';

                    setTimeout(() => row.classList.remove('ai-highlight'), 5000);
                }
            }
        }, 100);
    },

    // --- UI indicator ---

    _showIndicator(connected) {
        let indicator = document.getElementById('ai-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'ai-indicator';
            indicator.className = 'ai-indicator';
            const footer = document.querySelector('.sidebar-footer');
            if (footer) {
                footer.insertBefore(indicator, footer.firstChild);
            }
        }
        if (connected) {
            indicator.innerHTML = '<span class="ai-dot"></span> AI Connected';
            indicator.classList.add('connected');
            indicator.classList.remove('disconnected');
        } else {
            indicator.innerHTML = '<span class="ai-dot"></span> AI Disconnected';
            indicator.classList.remove('connected');
            indicator.classList.add('disconnected');
        }
    },
};
