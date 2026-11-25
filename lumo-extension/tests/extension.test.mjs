import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  isValidHttpUrl,
  escapeHtml,
  checkExtensionBackendHealth,
  savePageToLumo,
  searchWorkspaceFromExtension,
} from '../lib/api.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const manifestPath = path.resolve(__dirname, '../manifest.json');

test('manifest.json uses Manifest V3 with minimal safe permissions', () => {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ['activeTab', 'contextMenus', 'storage', 'scripting']);

  // Must not request broad <all_urls>, cookies, or browser history permissions
  assert.ok(!manifest.permissions.includes('cookies'));
  assert.ok(!manifest.permissions.includes('history'));
  assert.ok(!manifest.permissions.includes('<all_urls>'));
  assert.deepEqual(manifest.host_permissions, ['http://127.0.0.1/*', 'http://localhost/*']);
});

test('isValidHttpUrl allows http/https and rejects javascript/file/chrome schemes', () => {
  assert.equal(isValidHttpUrl('https://example.com/page'), true);
  assert.equal(isValidHttpUrl('http://127.0.0.1:8000'), true);
  assert.equal(isValidHttpUrl('javascript:alert(1)'), false);
  assert.equal(isValidHttpUrl('file:///etc/passwd'), false);
  assert.equal(isValidHttpUrl('chrome://extensions'), false);
});

test('escapeHtml neutralizes XSS payloads in extension UI', () => {
  const escaped = escapeHtml('<img src=x onerror="alert(1)">');
  assert.equal(escaped.includes('<'), false);
  assert.equal(escaped, '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
});

test('extension API client handles health, savePage, search, and offline errors', async () => {
  const origFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, init) => {
      if (url.endsWith('/api/v1/extension/health')) {
        return new Response(JSON.stringify({ status: 'healthy', application: 'LUMO' }), { status: 200 });
      }
      if (url.endsWith('/api/v1/extension/save-page') && init.method === 'POST') {
        return new Response(JSON.stringify({ item: { id: 'item-1' }, is_duplicate: false }), { status: 201 });
      }
      if (url.includes('/api/v1/extension/search')) {
        return new Response(JSON.stringify({ total: 1, hits: [{ id: 'item-1', title: 'Test' }] }), { status: 200 });
      }
      return new Response('Not Found', { status: 404 });
    };

    const health = await checkExtensionBackendHealth();
    assert.equal(health.status, 'healthy');

    const saved = await savePageToLumo({ url: 'https://example.com', title: 'Example' });
    assert.equal(saved.item.id, 'item-1');

    const search = await searchWorkspaceFromExtension('Test');
    assert.equal(search.total, 1);

    // Offline error handling
    globalThis.fetch = async () => {
      throw new Error('ECONNREFUSED');
    };
    await assert.rejects(() => checkExtensionBackendHealth(), /ECONNREFUSED/);
  } finally {
    globalThis.fetch = origFetch;
  }
});
