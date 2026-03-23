/* Client-side AES-256-GCM encryption for scan reports.
   CryptoKey stored in IndexedDB (non-extractable). Zero friction.
   If browser cleared, key is lost and server ciphertext becomes unrecoverable. */

const CryptoStore = {
    _db: null,
    _key: null,
    _available: false,

    /** Open IndexedDB, load or generate AES-256-GCM key. */
    async init() {
        if (!window.crypto || !window.crypto.subtle) {
            console.warn('CryptoStore: Web Crypto API unavailable, encryption disabled');
            return;
        }
        try {
            this._db = await this._openDB();
            this._key = await this._loadOrCreateKey();
            this._available = true;
        } catch (e) {
            console.warn('CryptoStore: init failed, encryption disabled', e);
        }
    },

    /** Encrypt plaintext string -> { iv, ciphertext } as base64. */
    async encryptToBase64(plaintext) {
        if (!this._available) return null;
        try {
            const iv = crypto.getRandomValues(new Uint8Array(12));
            const encoded = new TextEncoder().encode(plaintext);
            const encrypted = await crypto.subtle.encrypt(
                { name: 'AES-GCM', iv },
                this._key,
                encoded,
            );
            return {
                iv: this._toBase64(iv),
                ciphertext: this._toBase64(new Uint8Array(encrypted)),
            };
        } catch (e) {
            console.warn('CryptoStore: encrypt failed', e);
            return null;
        }
    },

    /** Decrypt base64 { iv, ciphertext } -> plaintext string, or null on failure. */
    async decryptFromBase64(ivB64, ciphertextB64) {
        if (!this._available) return null;
        try {
            const iv = this._fromBase64(ivB64);
            const ciphertext = this._fromBase64(ciphertextB64);
            const decrypted = await crypto.subtle.decrypt(
                { name: 'AES-GCM', iv },
                this._key,
                ciphertext,
            );
            return new TextDecoder().decode(decrypted);
        } catch (e) {
            console.warn('CryptoStore: decrypt failed (key may have changed)', e);
            return null;
        }
    },

    get available() { return this._available; },

    // -- Internals --

    _openDB() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open('comply_crypto', 1);
            req.onupgradeneeded = () => {
                req.result.createObjectStore('keys');
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    },

    async _loadOrCreateKey() {
        // Try loading existing key
        const existing = await this._idbGet('keys', 'primary');
        if (existing) return existing;

        // Generate new non-extractable AES-256-GCM key
        const key = await crypto.subtle.generateKey(
            { name: 'AES-GCM', length: 256 },
            false, // non-extractable
            ['encrypt', 'decrypt'],
        );
        await this._idbPut('keys', 'primary', key);
        return key;
    },

    _idbGet(storeName, key) {
        return new Promise((resolve, reject) => {
            const tx = this._db.transaction(storeName, 'readonly');
            const req = tx.objectStore(storeName).get(key);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    },

    _idbPut(storeName, key, value) {
        return new Promise((resolve, reject) => {
            const tx = this._db.transaction(storeName, 'readwrite');
            const req = tx.objectStore(storeName).put(value, key);
            req.onsuccess = () => resolve();
            req.onerror = () => reject(req.error);
        });
    },

    _toBase64(uint8) {
        let binary = '';
        for (let i = 0; i < uint8.length; i++) binary += String.fromCharCode(uint8[i]);
        return btoa(binary);
    },

    _fromBase64(b64) {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        return bytes;
    },
};
