/* Minimal hash-based SPA router */
const Router = {
    routes: {},
    currentRoute: null,
    _defaultRoute: '/landing',
    _afterNavigateHooks: [],

    on(path, handler) {
        this.routes[path] = handler;
    },

    navigate(path) {
        window.location.hash = path;
    },

    setDefaultRoute(path) {
        this._defaultRoute = path;
    },

    /** Register a callback that fires after every route change. */
    afterNavigate(fn) {
        this._afterNavigateHooks.push(fn);
    },

    start() {
        const self = this;
        const handle = () => {
            const rawHash = window.location.hash.slice(1) || self._defaultRoute;
            const hash = rawHash.split('?')[0];
            const parts = hash.split('/').filter(Boolean);
            const route = '/' + parts[0];
            const params = parts.slice(1);

            // Update active nav link (legacy + subnav)
            document.querySelectorAll('.nav-link').forEach(link => {
                link.classList.toggle('active', link.dataset.route === parts[0]);
            });
            document.querySelectorAll('.sidebar-subnav-link').forEach(link => {
                link.classList.toggle('active', link.dataset.route === parts[0]);
            });

            const handler = self.routes[route];
            const safeCall = (fn, args) => {
                try {
                    const result = fn(args);
                    // Handle async view render errors
                    if (result && typeof result.catch === 'function') {
                        result.catch(err => {
                            console.error('View error:', err);
                            const app = document.getElementById('app');
                            if (app) app.innerHTML = `<div class="error-boundary">
                                <h3>Something went wrong</h3>
                                <p>${err.isNetwork ? 'Unable to reach the server. Check your connection.' : 'This view encountered an error loading data.'}</p>
                                <div class="error-boundary-actions">
                                    <button class="btn btn-primary btn-sm" onclick="window.location.reload()">Reload</button>
                                    <button class="btn btn-secondary btn-sm" onclick="window.location.hash='#/landing'">Go Home</button>
                                </div>
                                <details class="error-boundary-details"><summary>Details</summary><pre>${(err.message || err).toString().replace(/</g, '&lt;')}</pre></details>
                            </div>`;
                        });
                    }
                } catch (err) {
                    console.error('View error:', err);
                    const app = document.getElementById('app');
                    if (app) app.innerHTML = `<div class="error-boundary">
                        <h3>Something went wrong</h3>
                        <p>This view encountered an error.</p>
                        <div class="error-boundary-actions">
                            <button class="btn btn-primary btn-sm" onclick="window.location.reload()">Reload</button>
                            <button class="btn btn-secondary btn-sm" onclick="window.location.hash='#/landing'">Go Home</button>
                        </div>
                        <details class="error-boundary-details"><summary>Details</summary><pre>${(err.message || err).toString().replace(/</g, '&lt;')}</pre></details>
                    </div>`;
                }
            };

            if (handler) {
                self.currentRoute = route;
                safeCall(handler, params);
            } else if (self.routes[self._defaultRoute]) {
                self.currentRoute = self._defaultRoute;
                safeCall(self.routes[self._defaultRoute], []);
            }

            // Fire afterNavigate hooks
            for (const fn of self._afterNavigateHooks) {
                try { fn(route, params); } catch (e) { console.error('afterNavigate hook error:', e); }
            }
        };

        window.addEventListener('hashchange', handle);
        handle();
    },

    getParams() {
        const hash = window.location.hash.slice(1) || this._defaultRoute;
        return hash.split('?')[0].split('/').filter(Boolean).slice(1);
    },

    /** Parse query params from the hash (e.g. #/detail/abc?control=14.1&article=Article%2014). */
    getQueryParams() {
        const hash = window.location.hash.slice(1) || this._defaultRoute;
        const qIdx = hash.indexOf('?');
        if (qIdx === -1) return {};
        return Object.fromEntries(new URLSearchParams(hash.substring(qIdx + 1)));
    }
};
