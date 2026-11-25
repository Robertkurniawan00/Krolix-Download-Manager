/**
 * Krolix Download Manager - Official Node.js Automation & Client SDK
 * 
 * Provides high-speed automation and integration with Krolix Download Manager:
 * - Direct HTTP REST integration (port 9666)
 * - Automatic background process recovery / CLI dispatch
 * - Single link and batch array link forwarding
 * 
 * Usage in Node.js:
 *   const KrolixClient = require('./krolix-client');
 *   const krolix = new KrolixClient();
 *   await krolix.download('https://example.com/file.zip', { silent: true });
 * 
 * CLI Usage:
 *   node krolix-client.js "https://fsn1-speed.hetzner.com/100MB.bin" --silent
 */

const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

class KrolixClient {
    constructor(options = {}) {
        this.host = options.host || '127.0.0.1';
        this.port = options.port || 9666;
        this.timeout = options.timeout || 3000;
    }

    /**
     * Check if Krolix Download Manager is running.
     */
    async getStatus() {
        return new Promise((resolve) => {
            const req = http.request({
                hostname: this.host,
                port: this.port,
                path: '/status',
                method: 'GET',
                timeout: this.timeout
            }, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    try {
                        const parsed = JSON.parse(data);
                        resolve({ online: true, ...parsed });
                    } catch {
                        resolve({ online: false, error: 'Invalid JSON response' });
                    }
                });
            });

            req.on('error', (err) => resolve({ online: false, error: err.message }));
            req.on('timeout', () => { req.destroy(); resolve({ online: false, error: 'Timeout' }); });
            req.end();
        });
    }

    /**
     * Sends a download task to Krolix.
     * @param {string} url 
     * @param {object} options { saveDir, filename, referer, cookies, userAgent, silent, queueOnly }
     */
    async download(url, options = {}) {
        if (!url || typeof url !== 'string') {
            throw new Error('URL is required');
        }

        const payload = {
            url: url.trim(),
            save_dir: options.saveDir || options.path || '',
            filename: options.filename || '',
            referer: options.referer || '',
            cookies: options.cookies || '',
            user_agent: options.userAgent || options.ua || '',
            silent: Boolean(options.silent),
            queue_only: Boolean(options.queueOnly || options.queue)
        };

        const postBody = JSON.stringify(payload);

        return new Promise((resolve, reject) => {
            const req = http.request({
                hostname: this.host,
                port: this.port,
                path: '/download',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json; charset=utf-8',
                    'Content-Length': Buffer.byteLength(postBody),
                    'X-Krolix-Client': 'nodejs-sdk'
                },
                timeout: this.timeout
            }, (res) => {
                let body = '';
                res.on('data', chunk => body += chunk);
                res.on('end', () => {
                    if (res.statusCode >= 200 && res.statusCode < 300) {
                        try {
                            resolve({ success: true, method: 'REST', response: JSON.parse(body) });
                        } catch {
                            resolve({ success: true, method: 'REST', raw: body });
                        }
                    } else {
                        this._fallbackCli(payload).then(resolve).catch(reject);
                    }
                });
            });

            req.on('error', () => {
                this._fallbackCli(payload).then(resolve).catch(reject);
            });

            req.on('timeout', () => {
                req.destroy();
                this._fallbackCli(payload).then(resolve).catch(reject);
            });

            req.write(postBody);
            req.end();
        });
    }

    /**
     * Sends multiple URLs as a batch download.
     */
    async batchDownload(urls, options = {}) {
        if (!Array.isArray(urls) || urls.length === 0) {
            throw new Error('Urls must be a non-empty array');
        }

        const items = urls.map(u => typeof u === 'string' ? { url: u } : u);
        const payload = {
            referer: options.referer || '',
            user_agent: options.userAgent || '',
            items: items
        };

        const postBody = JSON.stringify(payload);

        return new Promise((resolve, reject) => {
            const req = http.request({
                hostname: this.host,
                port: this.port,
                path: '/batch-download',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json; charset=utf-8',
                    'Content-Length': Buffer.byteLength(postBody),
                    'X-Krolix-Client': 'nodejs-sdk'
                },
                timeout: this.timeout
            }, (res) => {
                let body = '';
                res.on('data', chunk => body += chunk);
                res.on('end', () => {
                    if (res.statusCode >= 200 && res.statusCode < 300) {
                        try {
                            resolve({ success: true, response: JSON.parse(body) });
                        } catch {
                            resolve({ success: true, raw: body });
                        }
                    } else {
                        reject(new Error(`HTTP ${res.statusCode}: ${body}`));
                    }
                });
            });

            req.on('error', err => reject(err));
            req.on('timeout', () => {
                req.destroy();
                reject(new Error('Batch download request timed out'));
            });
            req.write(postBody);
            req.end();
        });
    }

    _findKrolixExe() {
        const localAppData = process.env.LOCALAPPDATA || '';
        const candidates = [
            path.join(localAppData, 'Programs', 'Krolix Download Manager', 'Krolix.exe'),
            path.resolve(__dirname, '..', '..', 'Krolix.exe'),
            path.resolve(__dirname, '..', '..', 'dist', 'Krolix', 'Krolix.exe')
        ];

        for (const c of candidates) {
            if (fs.existsSync(c)) return c;
        }
        return null;
    }

    _fallbackCli(payload) {
        return new Promise((resolve, reject) => {
            const krolixExe = this._findKrolixExe();
            if (!krolixExe) {
                return reject(new Error('Krolix.exe not found and REST server is offline.'));
            }

            const args = ['/d', payload.url];
            if (payload.save_dir) args.push('/p', payload.save_dir);
            if (payload.filename) args.push('/f', payload.filename);
            if (payload.silent) args.push('/n');
            if (payload.queue_only) args.push('/a');

            const child = spawn(krolixExe, args, {
                detached: true,
                stdio: 'ignore'
            });
            child.unref();

            resolve({ success: true, method: 'CLI', pid: child.pid });
        });
    }
}

// Support CLI invocation
if (require.main === module) {
    const args = process.argv.slice(2);
    if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
        console.log('Krolix Download Manager - Node.js SDK & CLI');
        console.log('Usage: node krolix-client.js <URL> [--silent] [--queue] [--dir <path>] [--filename <name>] [--status]');
        process.exit(0);
    }

    const client = new KrolixClient();

    if (args.includes('--status')) {
        client.getStatus().then(status => {
            console.log('Krolix Status:', JSON.stringify(status, null, 2));
            process.exit(status && status.online ? 0 : 1);
        });
    } else {
        let url = '';
        for (let i = 0; i < args.length; i++) {
            const a = args[i];
            if (a === '--dir' || a === '-p' || a === '--filename' || a === '-f') {
                i++; // skip option value
                continue;
            }
            if (a.startsWith('-')) continue;
            url = a;
            break;
        }
        if (!url) {
            console.error('[Krolix Node.js Error] Missing download URL.');
            process.exit(1);
        }
        const options = {
            silent: args.includes('--silent') || args.includes('-n'),
            queueOnly: args.includes('--queue') || args.includes('-a')
        };

        const dirIdx = args.indexOf('--dir') !== -1 ? args.indexOf('--dir') : args.indexOf('-p');
        if (dirIdx !== -1 && dirIdx + 1 < args.length) options.saveDir = args[dirIdx + 1];

        const fnIdx = args.indexOf('--filename') !== -1 ? args.indexOf('--filename') : args.indexOf('-f');
        if (fnIdx !== -1 && fnIdx + 1 < args.length) options.filename = args[fnIdx + 1];

        client.download(url, options)
            .then(res => {
                console.log('[Krolix Node.js] Download dispatched successfully:', res);
                process.exit(0);
            })
            .catch(err => {
                console.error('[Krolix Node.js Error]', err.message);
                process.exit(1);
            });
    }
}

module.exports = KrolixClient;
