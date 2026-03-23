/* IndexedDB-backed scan store. Replaces localStorage for scan records.
   Stores encrypted report blobs alongside metadata.
   Fallback: in-memory Map if IndexedDB unavailable. */

const ScanDB = {
    _db: null,
    _fallback: null, // Map used when IndexedDB unavailable

    /** Open IndexedDB comply_scans v1. */
    async init() {
        try {
            this._db = await this._openDB();
        } catch (e) {
            console.warn('ScanDB: IndexedDB unavailable, using in-memory fallback', e);
            this._fallback = new Map();
        }
    },

    get available() { return this._db !== null; },

    /** Store a scan record. */
    async put(record) {
        if (this._fallback) { this._fallback.set(record.id, record); return; }
        return new Promise((resolve, reject) => {
            const tx = this._db.transaction('scans', 'readwrite');
            const req = tx.objectStore('scans').put(record);
            req.onsuccess = () => resolve();
            req.onerror = () => reject(req.error);
        });
    },

    /** Get a scan record by id. */
    async get(id) {
        if (this._fallback) return this._fallback.get(id) || null;
        return new Promise((resolve, reject) => {
            const tx = this._db.transaction('scans', 'readonly');
            const req = tx.objectStore('scans').get(id);
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => reject(req.error);
        });
    },

    /** List scan records, most recent first. */
    async list(limit = 50) {
        if (this._fallback) {
            return [...this._fallback.values()]
                .sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))
                .slice(0, limit);
        }
        return new Promise((resolve, reject) => {
            const tx = this._db.transaction('scans', 'readonly');
            const store = tx.objectStore('scans');
            const idx = store.index('timestamp');
            const results = [];
            const req = idx.openCursor(null, 'prev');
            req.onsuccess = () => {
                const cursor = req.result;
                if (cursor && results.length < limit) {
                    results.push(cursor.value);
                    cursor.continue();
                } else {
                    resolve(results);
                }
            };
            req.onerror = () => reject(req.error);
        });
    },

    /** Remove a scan by id. */
    async remove(id) {
        if (this._fallback) { this._fallback.delete(id); return; }
        return new Promise((resolve, reject) => {
            const tx = this._db.transaction('scans', 'readwrite');
            const req = tx.objectStore('scans').delete(id);
            req.onsuccess = () => resolve();
            req.onerror = () => reject(req.error);
        });
    },

    /** Clear all scan records. */
    async clear() {
        if (this._fallback) { this._fallback.clear(); return; }
        return new Promise((resolve, reject) => {
            const tx = this._db.transaction('scans', 'readwrite');
            const req = tx.objectStore('scans').clear();
            req.onsuccess = () => resolve();
            req.onerror = () => reject(req.error);
        });
    },

    // -- Internals --

    _openDB() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open('comply_scans', 1);
            req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains('scans')) {
                    const store = db.createObjectStore('scans', { keyPath: 'id' });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                }
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    },
};
