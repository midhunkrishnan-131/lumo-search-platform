/**
 * Isolated Frontend Integration Test for FastAPI Health Endpoints
 * Verifies that the frontend contract with GET /api/v1/health conforms to Phase 1 requirements.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  checkBackendHealth,
  checkVersionedHealth,
  getApiBaseUrl,
  isBackendConfigured,
} from '../js/api.js';

// Setup minimal browser-like globals for isolated Node test environment
function setupTestEnvironment(apiBaseUrl = '') {
  const store = new Map();
  if (apiBaseUrl) {
    store.set('lumo_preferences_v1', JSON.stringify({ apiBaseUrl }));
  }

  globalThis.window = {
    localStorage: {
      getItem: (key) => store.get(key) || null,
      setItem: (key, val) => store.set(key, String(val)),
      removeItem: (key) => store.delete(key),
      clear: () => store.clear(),
    },
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
    fetch: null,
  };
}

test('frontend correctly recognizes unconfigured backend state', async () => {
  setupTestEnvironment('');

  assert.equal(isBackendConfigured(), false);
  assert.equal(getApiBaseUrl(), '');

  await assert.rejects(
    async () => {
      await checkBackendHealth();
    },
    (err) => {
      assert.equal(err.code, 'BACKEND_NOT_CONFIGURED');
      assert.match(err.message, /FastAPI backend URL is not configured/i);
      return true;
    }
  );

  await assert.rejects(
    async () => {
      await checkVersionedHealth();
    },
    (err) => {
      assert.equal(err.code, 'BACKEND_NOT_CONFIGURED');
      return true;
    }
  );
});

test('frontend successfully calls GET /api/v1/health and validates response payload', async () => {
  setupTestEnvironment('http://127.0.0.1:8000');

  assert.equal(isBackendConfigured(), true);
  assert.equal(getApiBaseUrl(), 'http://127.0.0.1:8000');

  let interceptedUrl = null;
  let interceptedHeaders = null;

  globalThis.window.fetch = async (url, options) => {
    interceptedUrl = url;
    interceptedHeaders = options.headers;

    return {
      ok: true,
      status: 200,
      json: async () => ({
        status: 'healthy',
        application: 'LUMO',
        version: '0.1.0',
      }),
    };
  };

  const response = await checkVersionedHealth();

  assert.equal(interceptedUrl, 'http://127.0.0.1:8000/api/v1/health');
  assert.equal(interceptedHeaders.Accept, 'application/json');
  assert.deepEqual(response, {
    status: 'healthy',
    application: 'LUMO',
    version: '0.1.0',
  });
});

test('frontend checkBackendHealth falls back to /health if /api/v1/health returns 404', async () => {
  setupTestEnvironment('http://127.0.0.1:8000');

  const calledUrls = [];

  globalThis.window.fetch = async (url) => {
    calledUrls.push(url);
    if (url.endsWith('/api/v1/health')) {
      return {
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Not Found' }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        status: 'healthy',
        application: 'LUMO',
        version: '0.1.0',
      }),
    };
  };

  const response = await checkBackendHealth();

  assert.deepEqual(calledUrls, [
    'http://127.0.0.1:8000/api/v1/health',
    'http://127.0.0.1:8000/health',
  ]);
  assert.equal(response.status, 'healthy');
  assert.equal(response.application, 'LUMO');
});

test('frontend throws structured HTTP_ERROR when backend returns 500', async () => {
  setupTestEnvironment('http://127.0.0.1:8000');

  globalThis.window.fetch = async () => ({
    ok: false,
    status: 500,
    json: async () => ({ detail: 'Internal server error' }),
  });

  await assert.rejects(
    async () => {
      await checkVersionedHealth();
    },
    (err) => {
      assert.equal(err.code, 'HTTP_ERROR');
      assert.equal(err.status, 500);
      assert.match(err.message, /HTTP 500/);
      return true;
    }
  );
});
