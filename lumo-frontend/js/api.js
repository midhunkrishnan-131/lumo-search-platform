/**
 * LUMO Centralized FastAPI Integration Layer
 * All browser API requests route strictly through the FastAPI gateway.
 * Never connects directly to PostgreSQL, OpenSearch, Qdrant, Redis, or Ollama.
 * Clearly separates live FastAPI responses from sample demonstration data.
 */

import { getPreferences } from './preferences.js';
import { runSampleSearch } from './search-data.js';

const DEFAULT_TIMEOUT_MS = 10000;

export function getApiBaseUrl() {
  const prefs = getPreferences();
  return prefs.apiBaseUrl || '';
}

export function isBackendConfigured() {
  return Boolean(getApiBaseUrl());
}

/**
 * Low-level JSON fetch wrapper with timeout and structured error reporting.
 */
async function requestFastApi(path, options = {}) {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    const err = new Error('FastAPI backend URL is not configured.');
    err.code = 'BACKEND_NOT_CONFIGURED';
    throw err;
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || DEFAULT_TIMEOUT_MS);

  try {
    const response = await window.fetch(`${baseUrl}${path}`, {
      method: options.method || 'GET',
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });

    if (!response.ok) {
      const err = new Error(`FastAPI request failed with HTTP ${response.status}`);
      err.code = 'HTTP_ERROR';
      err.status = response.status;
      throw err;
    }

    if (response.status === 204) {
      return null;
    }

    const data = await response.json();
    return data;
  } catch (err) {
    if (err.name === 'AbortError') {
      const timeoutErr = new Error('FastAPI request timed out.');
      timeoutErr.code = 'TIMEOUT';
      throw timeoutErr;
    }
    throw err;
  } finally {
    window.clearTimeout(timeout);
  }
}

/**
 * Classic Search: GET /api/v1/search?q=...
 */
export async function searchClassic(query, options = {}) {
  if (!isBackendConfigured()) {
    return runSampleSearch(query, { ...options, mode: 'classic' });
  }
  const params = new URLSearchParams({
    q: query,
    page: String(options.page || 1),
    per_page: String(options.perPage || 8),
    sort: options.sort || 'relevance',
  });
  if (options.category && options.category !== 'All') {
    params.set('category', options.category);
  }
  const data = await requestFastApi(`/api/v1/search?${params.toString()}`);
  return normalizeSearchResponse(data, query, 'classic', options);
}

/**
 * Semantic Search: GET /api/v1/search?q=...&mode=semantic
 */
export async function searchSemantic(query, options = {}) {
  if (!isBackendConfigured()) {
    return runSampleSearch(query, { ...options, mode: 'semantic' });
  }
  const params = new URLSearchParams({
    q: query,
    mode: 'semantic',
    page: String(options.page || 1),
    per_page: String(options.perPage || 8),
    sort: options.sort || 'relevance',
  });
  if (options.category && options.category !== 'All') {
    params.set('category', options.category);
  }
  const data = await requestFastApi(`/api/v1/search?${params.toString()}`);
  return normalizeSearchResponse(data, query, 'semantic', options);
}

/**
 * Hybrid Search: GET /api/v1/search/hybrid?q=...
 */
export async function searchHybrid(query, options = {}) {
  if (!isBackendConfigured()) {
    return runSampleSearch(query, { ...options, mode: 'hybrid' });
  }
  const params = new URLSearchParams({
    q: query,
    page: String(options.page || 1),
    per_page: String(options.perPage || 8),
    sort: options.sort || 'relevance',
  });
  if (options.category && options.category !== 'All') {
    params.set('category', options.category);
  }
  const data = await requestFastApi(`/api/v1/search/hybrid?${params.toString()}`);
  return normalizeSearchResponse(data, query, 'hybrid', options);
}

/**
 * Unified Search Dispatcher
 */
export async function executeSearch(query, options = {}) {
  const mode = options.mode || 'hybrid';
  if (mode === 'classic') return searchClassic(query, options);
  if (mode === 'semantic') return searchSemantic(query, options);
  if (mode === 'ai') return searchAi(query, options);
  return searchHybrid(query, options);
}

/**
 * AI Search: POST /api/v1/search/ai
 */
export async function searchAi(query, options = {}) {
  if (!isBackendConfigured()) {
    const sample = runSampleSearch(query, { ...options, mode: 'hybrid' });
    return {
      ...sample,
      mode: 'ai',
      aiAnswer: 'FastAPI backend is not configured. Connect your API in Settings to generate live grounded answers using Google Gemini or Grok.',
      citations: [],
    };
  }
  const payload = {
    query,
    page_size: Number(options.perPage) || 8,
    provider: options.provider || 'auto',
  };
  const data = await requestFastApi('/api/v1/search/ai', {
    method: 'POST',
    body: payload,
  });
  const items = Array.isArray(data.sources) ? data.sources : [];
  return {
    source: 'api',
    query,
    mode: 'ai',
    category: options.category || 'All',
    sort: options.sort || 'relevance',
    total: items.length,
    page: 1,
    perPage: options.perPage || 8,
    totalPages: 1,
    aiAnswer: data.answer || '',
    citations: Array.isArray(data.citations) ? data.citations : [],
    provider: data.provider,
    model: data.model,
    fallbackUsed: data.fallback_used,
    status: data.status,
    items: items.map((item, idx) => ({
      id: item.document_id || `src-${idx}`,
      title: item.title || 'Untitled Source',
      url: item.url || '',
      domain: item.domain || safeExtractDomain(item.url),
      category: 'Verified Source',
      publishedAt: '',
      description: item.snippet || '',
      snippet: item.snippet || '',
      sourceBadge: item.source_id,
    })),
  };
}

/**
 * AI / Research Search: POST /api/v1/search/ai
 */
export async function submitAiResearch(payload) {
  return requestFastApi('/api/v1/search/ai', {
    method: 'POST',
    body: payload,
  });
}

/**
 * Phase 9 Autonomous Research Agent: POST /api/v1/research
 */
export async function createResearchSession(payload) {
  return requestFastApi('/api/v1/research', {
    method: 'POST',
    body: payload,
  });
}

export async function getResearchSession(sessionId) {
  return requestFastApi(`/api/v1/research/${encodeURIComponent(sessionId)}`);
}

export async function getResearchReport(sessionId) {
  return requestFastApi(`/api/v1/research/${encodeURIComponent(sessionId)}/report`);
}

export async function cancelResearchSession(sessionId) {
  return requestFastApi(`/api/v1/research/${encodeURIComponent(sessionId)}/cancel`, {
    method: 'POST',
  });
}

export async function listResearchSessions(limit = 20, offset = 0) {
  return requestFastApi(`/api/v1/research?limit=${limit}&offset=${offset}`);
}


/**
 * Download Guardian / URL Security Analysis: POST /api/v1/guardian/url
 */
export async function submitUrlSecurityScan(url, options = {}) {
  return requestFastApi('/api/v1/guardian/url', {
    method: 'POST',
    body: {
      url,
      check_network: options.checkNetwork !== false,
      check_reputation: Boolean(options.checkReputation),
      explain_ai: Boolean(options.explainAi),
    },
  });
}

/**
 * File Hash Threat Intelligence Lookup: POST /api/v1/guardian/file
 */
export async function submitFileHashScan(payload) {
  return requestFastApi('/api/v1/guardian/file', {
    method: 'POST',
    body: payload,
  });
}

/**
 * File Upload Static & Security Analysis: POST /api/v1/guardian/file (multipart)
 */
export async function submitFileUploadScan(file, options = {}) {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    const err = new Error('FastAPI backend URL is not configured.');
    err.code = 'BACKEND_NOT_CONFIGURED';
    throw err;
  }

  const formData = new FormData();
  formData.append('file', file);
  if (options.checkReputation) formData.append('check_reputation', 'true');
  if (options.explainAi) formData.append('explain_ai', 'true');

  const response = await window.fetch(`${baseUrl}/api/v1/guardian/file`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const err = new Error(`File analysis request failed with HTTP ${response.status}`);
    err.code = 'HTTP_ERROR';
    err.status = response.status;
    throw err;
  }

  return response.json();
}

export async function getGuardianAnalysis(analysisId) {
  return requestFastApi(`/api/v1/guardian/analysis/${encodeURIComponent(analysisId)}`);
}

export async function listGuardianHistory(limit = 20, offset = 0) {
  return requestFastApi(`/api/v1/guardian/history?limit=${limit}&offset=${offset}`);
}

export async function deleteGuardianAnalysis(analysisId) {
  return requestFastApi(`/api/v1/guardian/analysis/${encodeURIComponent(analysisId)}`, {
    method: 'DELETE',
  });
}

export async function clearGuardianHistory() {
  return requestFastApi('/api/v1/guardian/history', {
    method: 'DELETE',
  });
}

/**
 * Knowledge Graph Query: GET /api/v1/graph
 * Accepts either string query or options object.
 */
export async function fetchKnowledgeGraph(queryOrOptions = '') {
  let params = {};
  if (typeof queryOrOptions === 'string') {
    params = { query: queryOrOptions };
  } else if (queryOrOptions && typeof queryOrOptions === 'object') {
    params = queryOrOptions;
  }
  const queryParts = [];
  if (params.limitNodes) queryParts.push(`limit_nodes=${encodeURIComponent(params.limitNodes)}`);
  if (params.limitEdges) queryParts.push(`limit_edges=${encodeURIComponent(params.limitEdges)}`);
  if (params.type && params.type !== 'All') queryParts.push(`type=${encodeURIComponent(params.type)}`);
  if (params.relType && params.relType !== 'All') queryParts.push(`rel_type=${encodeURIComponent(params.relType)}`);
  if (params.query) queryParts.push(`q=${encodeURIComponent(params.query)}`);
  const qs = queryParts.length ? `?${queryParts.join('&')}` : '';
  return requestFastApi(`/api/v1/graph${qs}`);
}

/**
 * FastAPI Health Check: GET /api/v1/health (falls back to /health if needed)
 */
export async function checkBackendHealth() {
  try {
    return await requestFastApi('/api/v1/health', { timeoutMs: 4000 });
  } catch (err) {
    if (err.status === 404) {
      return await requestFastApi('/health', { timeoutMs: 4000 });
    }
    throw err;
  }
}

/**
 * Direct versioned health check: GET /api/v1/health
 */
export async function checkVersionedHealth() {
  return requestFastApi('/api/v1/health', { timeoutMs: 4000 });
}

function normalizeSearchResponse(data, query, mode, options) {
  const items = Array.isArray(data.results || data.items) ? data.results || data.items : [];
  const total = typeof data.total === 'number' ? data.total : items.length;
  const perPage = Number(options.perPage) || 8;
  const page = Number(options.page) || 1;
  return {
    source: 'api',
    query,
    mode,
    category: options.category || 'All',
    sort: options.sort || 'relevance',
    total,
    page,
    perPage,
    totalPages: Math.max(1, Math.ceil(total / perPage)),
    items: items.map((item, idx) => ({
      id: item.id || `api-${idx}`,
      title: item.title || item.url || 'Untitled Result',
      url: item.url || '',
      domain: item.domain || safeExtractDomain(item.url),
      category: item.category || 'Indexed',
      publishedAt: item.published_at || item.publishedAt || '',
      description: item.description || '',
      snippet: item.snippet || item.description || '',
    })),
  };
}

/**
 * Record a browsing event / click on a result: POST /api/v1/history/browse
 */
export async function logBrowsingEvent(payload) {
  if (!isBackendConfigured()) return null;
  try {
    return await requestFastApi('/api/v1/history/browse', {
      method: 'POST',
      body: payload,
    });
  } catch (err) {
    // Non-blocking telemetry
    console.debug('Browse event logging failed:', err);
    return null;
  }
}

function safeExtractDomain(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return '';
  }
}

/**
 * Phase 11: Knowledge Graph API Methods
 */
export async function fetchGraphStats() {
  return await requestFastApi('/api/v1/graph/stats');
}

export async function fetchEntityDetails(entityId) {
  return await requestFastApi(`/api/v1/graph/entities/${encodeURIComponent(entityId)}`);
}

export async function fetchEntityConnections(entityId, depth = 1, limit = 50) {
  return await requestFastApi(
    `/api/v1/graph/entities/${encodeURIComponent(entityId)}/connections?depth=${depth}&limit=${limit}`
  );
}

export async function searchGraphEntities(query, type = null, limit = 20) {
  const queryParts = [`q=${encodeURIComponent(query)}`];
  if (type && type !== 'All') queryParts.push(`type=${encodeURIComponent(type)}`);
  queryParts.push(`limit=${limit}`);
  return await requestFastApi(`/api/v1/graph/search?${queryParts.join('&')}`);
}

export async function reprocessKnowledgeGraph(options = {}) {
  return await requestFastApi('/api/v1/graph/reprocess', {
    method: 'POST',
    body: {
      batch_size: options.batchSize || 50,
      use_ai: Boolean(options.useAi),
    },
  });
}

/**
 * Phase 12: Platform Diagnostics: GET /api/v1/health/diagnostics
 */
export async function fetchPlatformDiagnostics() {
  return await requestFastApi('/api/v1/health/diagnostics', { timeoutMs: 5000 });
}

/**
 * Phase 14: Personal Knowledge Workspace API Methods
 */
export async function fetchWorkspaceDashboard() {
  return await requestFastApi('/api/v1/workspace');
}

export async function listWorkspaceItems(params = {}) {
  const qs = new URLSearchParams();
  if (params.collectionId) qs.set('collection_id', params.collectionId);
  if (params.sourceType) qs.set('source_type', params.sourceType);
  if (params.tag) qs.set('tag', params.tag);
  if (params.limit) qs.set('limit', String(params.limit));
  const q = qs.toString() ? `?${qs.toString()}` : '';
  return await requestFastApi(`/api/v1/workspace/items${q}`);
}

export async function saveToWorkspace(payload) {
  return await requestFastApi('/api/v1/workspace/items', {
    method: 'POST',
    body: payload,
  });
}

export async function fetchWorkspaceItem(itemId) {
  return await requestFastApi(`/api/v1/workspace/items/${encodeURIComponent(itemId)}`);
}

export async function deleteWorkspaceItem(itemId) {
  return await requestFastApi(`/api/v1/workspace/items/${encodeURIComponent(itemId)}`, {
    method: 'DELETE',
  });
}

export async function fetchWorkspaceItemConnections(itemId) {
  return await requestFastApi(`/api/v1/workspace/items/${encodeURIComponent(itemId)}/connections`);
}

export async function importWorkspaceFile(file, collectionId = '', tags = '') {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    const err = new Error('FastAPI backend URL is not configured.');
    err.code = 'BACKEND_NOT_CONFIGURED';
    throw err;
  }
  const form = new FormData();
  form.append('file', file);
  if (collectionId) form.append('collection_id', collectionId);
  if (tags) form.append('tags', tags);

  const resp = await window.fetch(`${baseUrl}/api/v1/workspace/import`, {
    method: 'POST',
    body: form,
  });
  if (!resp.ok) {
    let msg = `Import failed with HTTP ${resp.status}`;
    try {
      const errData = await resp.json();
      if (errData.detail) msg = errData.detail;
    } catch {}
    throw new Error(msg);
  }
  return await resp.json();
}

export async function importWorkspaceUrl(url, collectionId = null, tags = []) {
  return await requestFastApi('/api/v1/workspace/import-url', {
    method: 'POST',
    body: { url, collection_id: collectionId, tags },
    timeoutMs: 15000,
  });
}

export async function listWorkspaceCollections() {
  return await requestFastApi('/api/v1/workspace/collections');
}

export async function createWorkspaceCollection(name, description = '') {
  return await requestFastApi('/api/v1/workspace/collections', {
    method: 'POST',
    body: { name, description },
  });
}

export async function deleteWorkspaceCollection(collectionId) {
  return await requestFastApi(`/api/v1/workspace/collections/${encodeURIComponent(collectionId)}`, {
    method: 'DELETE',
  });
}

export async function listWorkspaceNotes(collectionId = null) {
  const qs = collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : '';
  return await requestFastApi(`/api/v1/workspace/notes${qs}`);
}

export async function createWorkspaceNote(payload) {
  return await requestFastApi('/api/v1/workspace/notes', {
    method: 'POST',
    body: payload,
  });
}

export async function updateWorkspaceNote(noteId, payload) {
  return await requestFastApi(`/api/v1/workspace/notes/${encodeURIComponent(noteId)}`, {
    method: 'PATCH',
    body: payload,
  });
}

export async function deleteWorkspaceNote(noteId) {
  return await requestFastApi(`/api/v1/workspace/notes/${encodeURIComponent(noteId)}`, {
    method: 'DELETE',
  });
}

export async function listWorkspaceAnnotations(itemId) {
  return await requestFastApi(`/api/v1/workspace/items/${encodeURIComponent(itemId)}/annotations`);
}

export async function createWorkspaceAnnotation(itemId, payload) {
  return await requestFastApi(`/api/v1/workspace/items/${encodeURIComponent(itemId)}/annotations`, {
    method: 'POST',
    body: payload,
  });
}

export async function deleteWorkspaceAnnotation(annotationId) {
  return await requestFastApi(`/api/v1/workspace/annotations/${encodeURIComponent(annotationId)}`, {
    method: 'DELETE',
  });
}

export async function searchWorkspace(payload) {
  return await requestFastApi('/api/v1/workspace/search', {
    method: 'POST',
    body: payload,
  });
}

export async function askWorkspaceAI(payload) {
  return await requestFastApi('/api/v1/workspace/ask', {
    method: 'POST',
    body: payload,
    timeoutMs: 30000,
  });
}

/**
 * Phase 15: Offline AI Intelligence Engine (Local Ollama)
 */
export async function fetchLocalAIStatus() {
  return await requestFastApi('/api/v1/local-ai/status', { timeoutMs: 5000 });
}

export async function updateLocalAIConfig(payload) {
  return await requestFastApi('/api/v1/local-ai/config', {
    method: 'POST',
    body: payload,
  });
}

export async function fetchLocalAIModels() {
  return await requestFastApi('/api/v1/local-ai/models', { timeoutMs: 5000 });
}

export async function testLocalAIModel(model = null) {
  return await requestFastApi('/api/v1/local-ai/test', {
    method: 'POST',
    body: { model },
    timeoutMs: 20000,
  });
}

export async function runLocalAITask(payload) {
  return await requestFastApi('/api/v1/local-ai/tasks', {
    method: 'POST',
    body: payload,
    timeoutMs: 60000,
  });
}

export async function streamLocalAIChat(payload, { signal, onCitations, onToken, onError }) {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    throw new Error('FastAPI backend URL is not configured.');
  }

  const resp = await window.fetch(`${baseUrl}/api/v1/local-ai/chat/stream`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!resp.ok || !resp.body) {
    throw new Error(`Local AI stream failed with HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    for (const rawEvent of events) {
      const line = rawEvent.trim();
      if (!line.startsWith('data:')) continue;
      try {
        const msg = JSON.parse(line.slice(5).trim());
        if (msg.type === 'citations' && onCitations) onCitations(msg.citations || []);
        else if (msg.type === 'token' && onToken) onToken(msg);
        else if (msg.type === 'error' && onError) onError(msg.detail || 'Stream error');
      } catch {}
    }
  }
}



/**
 * Phase 16: Intelligence Automation Engine API Methods
 */
export async function fetchAutomationTemplates() {
  return await requestFastApi('/api/v1/automations/templates');
}

export async function listAutomations() {
  return await requestFastApi('/api/v1/automations');
}

export async function createAutomation(payload) {
  return await requestFastApi('/api/v1/automations', { method: 'POST', body: payload });
}

export async function deleteAutomation(automationId) {
  return await requestFastApi(`/api/v1/automations/${encodeURIComponent(automationId)}`, { method: 'DELETE' });
}

export async function runAutomationNow(automationId, sync = false) {
  return await requestFastApi(`/api/v1/automations/${encodeURIComponent(automationId)}/run?sync=${sync}`, { method: 'POST', timeoutMs: 30000 });
}

export async function pauseAutomation(automationId) {
  return await requestFastApi(`/api/v1/automations/${encodeURIComponent(automationId)}/pause`, { method: 'POST' });
}

export async function resumeAutomation(automationId) {
  return await requestFastApi(`/api/v1/automations/${encodeURIComponent(automationId)}/resume`, { method: 'POST' });
}

export async function duplicateAutomation(automationId) {
  return await requestFastApi(`/api/v1/automations/${encodeURIComponent(automationId)}/duplicate`, { method: 'POST' });
}

export async function listAutomationExecutions(limit = 20) {
  return await requestFastApi(`/api/v1/automation-executions?limit=${limit}`);
}

export async function cancelAutomationExecution(executionId) {
  return await requestFastApi(`/api/v1/automation-executions/${encodeURIComponent(executionId)}/cancel`, { method: 'POST' });
}

export async function listNotifications(limit = 20) {
  return await requestFastApi(`/api/v1/notifications?limit=${limit}`);
}

export async function markNotificationRead(notificationId) {
  return await requestFastApi(`/api/v1/notifications/${encodeURIComponent(notificationId)}/read`, { method: 'POST' });
}

export async function deleteNotification(notificationId) {
  return await requestFastApi(`/api/v1/notifications/${encodeURIComponent(notificationId)}`, { method: 'DELETE' });
}


/**
 * Phase 17: Adaptive Intelligence & Personalization API Methods
 */
export async function fetchPersonalizationProfile() {
  return await requestFastApi('/api/v1/personalization/profile');
}

export async function updatePersonalizationSettings(payload) {
  return await requestFastApi('/api/v1/personalization/settings', { method: 'PUT', body: payload });
}

export async function addPersonalizationInterest(payload) {
  return await requestFastApi('/api/v1/personalization/interests', { method: 'POST', body: payload });
}

export async function deletePersonalizationInterest(interestId) {
  return await requestFastApi(`/api/v1/personalization/interests/${encodeURIComponent(interestId)}`, { method: 'DELETE' });
}

export async function addSourcePreference(payload) {
  return await requestFastApi('/api/v1/personalization/sources', { method: 'POST', body: payload });
}

export async function deleteSourcePreference(sourceId) {
  return await requestFastApi(`/api/v1/personalization/sources/${encodeURIComponent(sourceId)}`, { method: 'DELETE' });
}

export async function fetchRecommendations(limit = 12) {
  return await requestFastApi(`/api/v1/personalization/recommendations?limit=${limit}`);
}

export async function submitPersonalizationFeedback(payload) {
  return await requestFastApi('/api/v1/personalization/feedback', { method: 'POST', body: payload });
}

export async function deletePersonalizationFeedback(feedbackId) {
  return await requestFastApi(`/api/v1/personalization/feedback/${encodeURIComponent(feedbackId)}`, { method: 'DELETE' });
}

export async function resetPersonalizationData() {
  return await requestFastApi('/api/v1/personalization/reset', { method: 'POST' });
}

/* ---- Phase 18: Universal Data Intelligence Engine ---- */
export async function fetchIntelligenceProvidersStatus() {
  return await requestFastApi('/api/v1/intelligence/providers/status');
}

export async function uploadIntelligenceFile(file, { classifyWithAi = false, provider = 'auto' } = {}) {
  const form = new FormData();
  form.append('file', file);
  form.append('classify_with_ai', String(Boolean(classifyWithAi)));
  form.append('provider', provider);
  const url = `${getBackendUrl().replace(/\/+$/, '')}/api/v1/intelligence/import`;
  const resp = await fetch(url, { method: 'POST', body: form });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `Import failed (${resp.status})`);
  return data;
}

export async function importIntelligenceUrl(payload) {
  return await requestFastApi('/api/v1/intelligence/import/url', { method: 'POST', body: payload });
}

export async function fetchIntelligenceImports(limit = 50) {
  return await requestFastApi(`/api/v1/intelligence/imports?limit=${limit}`);
}

export async function retryIntelligenceImport(importId) {
  return await requestFastApi(`/api/v1/intelligence/imports/${encodeURIComponent(importId)}/retry`, { method: 'POST' });
}

export async function deleteIntelligenceImport(importId) {
  return await requestFastApi(`/api/v1/intelligence/imports/${encodeURIComponent(importId)}`, { method: 'DELETE' });
}

export async function fetchIntelligenceDocuments(limit = 50) {
  return await requestFastApi(`/api/v1/intelligence/documents?limit=${limit}`);
}

export async function analyzeIntelligenceDocument(docId, payload) {
  return await requestFastApi(`/api/v1/intelligence/documents/${encodeURIComponent(docId)}/analyze`, {
    method: 'POST',
    body: payload,
  });
}

export async function fetchIntelligenceDatasets(limit = 50) {
  return await requestFastApi(`/api/v1/intelligence/datasets?limit=${limit}`);
}

export async function fetchIntelligenceDatasetProfile(datasetId, sheet = '') {
  const qs = sheet ? `?sheet=${encodeURIComponent(sheet)}` : '';
  return await requestFastApi(`/api/v1/intelligence/datasets/${encodeURIComponent(datasetId)}/profile${qs}`);
}

export async function analyzeIntelligenceDataset(datasetId, payload) {
  return await requestFastApi(`/api/v1/intelligence/datasets/${encodeURIComponent(datasetId)}/analyze`, {
    method: 'POST',
    body: payload,
  });
}

export async function visualizeIntelligenceDataset(datasetId, payload) {
  return await requestFastApi(`/api/v1/intelligence/datasets/${encodeURIComponent(datasetId)}/visualize`, {
    method: 'POST',
    body: payload,
  });
}

export async function runCrossDocumentAnalysis(payload) {
  return await requestFastApi('/api/v1/intelligence/cross-analysis', { method: 'POST', body: payload });
}

export async function fetchIntelligenceReports(limit = 30) {
  return await requestFastApi(`/api/v1/intelligence/reports?limit=${limit}`);
}

/* ---- Phase 19: Intelligence Command Center ---- */
export async function fetchDashboardOverview() {
  return await requestFastApi('/api/v1/dashboard/overview');
}

export async function fetchDashboardActivity({ limit = 20, offset = 0, category = 'all' } = {}) {
  return await requestFastApi(
    `/api/v1/dashboard/activity?limit=${limit}&offset=${offset}&category=${encodeURIComponent(category)}`
  );
}

export async function fetchDashboardResearch(limit = 6) {
  return await requestFastApi(`/api/v1/dashboard/research?limit=${limit}`);
}

export async function fetchDashboardAutomations(limit = 6) {
  return await requestFastApi(`/api/v1/dashboard/automations?limit=${limit}`);
}

export async function fetchDashboardAiStatus() {
  return await requestFastApi('/api/v1/dashboard/ai-status');
}

export async function fetchDashboardKnowledge(limit = 6) {
  return await requestFastApi(`/api/v1/dashboard/knowledge?limit=${limit}`);
}

export async function fetchDashboardGuardian(limit = 6) {
  return await requestFastApi(`/api/v1/dashboard/guardian?limit=${limit}`);
}

export async function fetchDashboardSystemHealth(force = false) {
  return await requestFastApi(`/api/v1/dashboard/system-health?force=${Boolean(force)}`);
}

export async function fetchDashboardNotifications(limit = 15, unreadOnly = false) {
  return await requestFastApi(`/api/v1/dashboard/notifications?limit=${limit}&unread_only=${Boolean(unreadOnly)}`);
}

export async function markDashboardNotificationRead(notificationId) {
  return await requestFastApi(`/api/v1/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: 'POST',
  });
}

/* ---- Phase 21: Operations, Diagnostics & Backups ---- */
export async function fetchOpsDiagnostics() {
  return await requestFastApi('/api/v1/ops/diagnostics');
}

export async function fetchOpsRelease() {
  return await requestFastApi('/api/v1/ops/release');
}

export async function fetchOpsBackups() {
  return await requestFastApi('/api/v1/ops/backups');
}

export async function createOpsBackup(label = 'dashboard') {
  return await requestFastApi(`/api/v1/ops/backups?label=${encodeURIComponent(label)}`, { method: 'POST' });
}

/* ---- Phase 22: External Integration Layer ---- */
export async function fetchIntegrations() {
  return await requestFastApi('/api/v1/integrations');
}

export async function fetchAvailableIntegrations() {
  return await requestFastApi('/api/v1/integrations/available');
}

export async function enableIntegration(id) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/enable`, { method: 'POST' });
}

export async function disableIntegration(id) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/disable`, { method: 'POST' });
}

export async function configureIntegration(id, payload) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/configure`, { method: 'POST', body: payload });
}

export async function testIntegration(id) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/test`, { method: 'POST' });
}

export async function syncIntegration(id, payload = {}) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/sync`, { method: 'POST', body: payload });
}

export async function fetchIntegrationHistory(id, limit = 20) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/history?limit=${limit}`);
}

export async function fetchIntegrationRecords(id, limit = 30) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/records?limit=${limit}`);
}

export async function fetchIntegrationSources(id) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/sources`);
}

export async function addIntegrationSource(id, payload) {
  return await requestFastApi(`/api/v1/integrations/${encodeURIComponent(id)}/sources`, { method: 'POST', body: payload });
}

export async function pauseIntegrationSource(sourceId) {
  return await requestFastApi(`/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/pause`, { method: 'POST' });
}

export async function resumeIntegrationSource(sourceId) {
  return await requestFastApi(`/api/v1/integrations/sources/${encodeURIComponent(sourceId)}/resume`, { method: 'POST' });
}

export async function deleteIntegrationSource(sourceId) {
  return await requestFastApi(`/api/v1/integrations/sources/${encodeURIComponent(sourceId)}`, { method: 'DELETE' });
}

/* ---- Phase 23: Developer Platform & API Keys ---- */
export async function fetchDeveloperInfo() {
  return await requestFastApi('/api/v1/developer/info');
}

export async function fetchApiKeys() {
  return await requestFastApi('/api/v1/developer/keys');
}

export async function createApiKey(payload) {
  return await requestFastApi('/api/v1/developer/keys', { method: 'POST', body: payload });
}

export async function rotateApiKey(keyId) {
  return await requestFastApi(`/api/v1/developer/keys/${encodeURIComponent(keyId)}/rotate`, { method: 'POST' });
}

export async function revokeApiKey(keyId) {
  return await requestFastApi(`/api/v1/developer/keys/${encodeURIComponent(keyId)}/revoke`, { method: 'POST' });
}

export async function deleteApiKey(keyId) {
  return await requestFastApi(`/api/v1/developer/keys/${encodeURIComponent(keyId)}`, { method: 'DELETE' });
}

export async function fetchApiUsage(limit = 30) {
  return await requestFastApi(`/api/v1/developer/usage?limit=${limit}`);
}

/* ---- Phase 24: Consistent Safe Error Formatter ---- */
export function formatSafeError(err) {
  const raw = String(err?.message || err || 'An unexpected error occurred.');
  if (/Failed to fetch|NetworkError/i.test(raw)) {
    return 'Unable to reach the LUMO backend. Check that FastAPI is running on the configured URL.';
  }
  if (/429/.test(raw)) {
    return 'Rate limit exceeded. Please wait a moment before retrying.';
  }
  if (/401|403/.test(raw)) {
    return 'Authorization required or insufficient permissions for this action.';
  }
  return raw.slice(0, 240);
}

/* ---- Phase 25: Evaluation & Benchmarking Engine ---- */
export async function fetchEvaluationDatasets() {
  return await requestFastApi('/api/v1/evaluation-datasets');
}

export async function createEvaluationDataset(payload) {
  return await requestFastApi('/api/v1/evaluation-datasets', { method: 'POST', body: payload });
}

export async function deleteEvaluationDataset(id) {
  return await requestFastApi(`/api/v1/evaluation-datasets/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function fetchEvaluations() {
  return await requestFastApi('/api/v1/evaluations');
}

export async function createEvaluation(payload) {
  return await requestFastApi('/api/v1/evaluations', { method: 'POST', body: payload });
}

export async function cloneEvaluation(id) {
  return await requestFastApi(`/api/v1/evaluations/${encodeURIComponent(id)}/clone`, { method: 'POST' });
}

export async function deleteEvaluation(id) {
  return await requestFastApi(`/api/v1/evaluations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function runEvaluation(id, payload = {}) {
  return await requestFastApi(`/api/v1/evaluations/${encodeURIComponent(id)}/run`, { method: 'POST', body: payload });
}

export async function fetchEvaluationRuns(limit = 30) {
  return await requestFastApi(`/api/v1/evaluations/runs?limit=${limit}`);
}

export async function compareEvaluationRuns(baselineId, currentId) {
  return await requestFastApi(
    `/api/v1/evaluations/compare?baseline_run_id=${encodeURIComponent(baselineId)}&current_run_id=${encodeURIComponent(currentId)}`
  );
}

export async function addEvaluationReview(runId, payload) {
  return await requestFastApi(`/api/v1/evaluations/runs/${encodeURIComponent(runId)}/reviews`, {
    method: 'POST',
    body: payload,
  });
}
