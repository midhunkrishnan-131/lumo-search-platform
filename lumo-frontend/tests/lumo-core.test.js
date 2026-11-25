import test from 'node:test';
import assert from 'node:assert/strict';

import {
  normalizeThemePreference,
  resolveAppliedTheme,
} from '../js/theme-logic.js';
import {
  getLocalDateKey,
  getGreetingForHour,
  getDailyContent,
} from '../js/daily-content.js';
import {
  runSampleSearch,
  getSearchSuggestions,
  highlightSnippet,
} from '../js/search-data.js';
import {
  validateAndInspectUrl,
  isRestrictedHost,
} from '../js/url-validator.js';

test('theme-logic defaults to system and resolves light/dark properly', () => {
  assert.equal(normalizeThemePreference(null), 'system');
  assert.equal(normalizeThemePreference('unknown'), 'system');
  assert.equal(normalizeThemePreference('dark'), 'dark');
  assert.equal(normalizeThemePreference('light'), 'light');

  assert.equal(resolveAppliedTheme('system', true), 'dark');
  assert.equal(resolveAppliedTheme('system', false), 'light');
  assert.equal(resolveAppliedTheme('light', true), 'light');
  assert.equal(resolveAppliedTheme('dark', false), 'dark');
});

test('daily-content is deterministic for the same local calendar date and returns verified observances', () => {
  const nov24Morning = new Date(2026, 10, 24, 8, 15, 0);
  const nov24Evening = new Date(2026, 10, 24, 22, 45, 0);
  const first = getDailyContent(nov24Morning);
  const second = getDailyContent(nov24Evening);

  assert.equal(getLocalDateKey(nov24Morning), '2026-11-24');
  assert.deepEqual(first.specialDay, second.specialDay);
  assert.deepEqual(first.quote, second.quote);
  assert.deepEqual(first.didYouKnow, second.didYouKnow);
  assert.deepEqual(first.discovery, second.discovery);
  assert.match(first.specialDay.title, /Origin of Species/i);

  const jun5 = getDailyContent(new Date(2026, 5, 5, 12, 0, 0));
  assert.equal(jun5.specialDay.title, 'World Environment Day');

  const nov10 = getDailyContent(new Date(2026, 10, 10, 12, 0, 0));
  assert.equal(nov10.specialDay.title, 'World Science Day for Peace and Development');

  assert.equal(getGreetingForHour(9), 'Good morning');
  assert.equal(getGreetingForHour(14), 'Good afternoon');
  assert.equal(getGreetingForHour(19), 'Good evening');
});

test('search-data supports Classic, Semantic, and Hybrid modes with filtering and pagination', () => {
  const hybrid = runSampleSearch('search engines', { mode: 'hybrid', perPage: 5, page: 1 });
  assert.equal(hybrid.source, 'sample');
  assert.equal(hybrid.mode, 'hybrid');
  assert.ok(hybrid.total >= 2);
  assert.match(hybrid.items[0].title, /Search Engines|Hybrid Search/i);

  // Semantic synonym expansion: "safe link" should find URL security doc
  const semantic = runSampleSearch('safe link', { mode: 'semantic' });
  assert.ok(semantic.items.some((item) => item.id === 'doc-url-security'));

  // Category filter
  const securityOnly = runSampleSearch('security', { mode: 'hybrid', category: 'Security' });
  assert.ok(securityOnly.items.length > 0);
  assert.ok(securityOnly.items.every((item) => item.category === 'Security'));

  // Pagination
  const page1 = runSampleSearch('', { perPage: 4, page: 1 });
  const page2 = runSampleSearch('', { perPage: 4, page: 2 });
  assert.equal(page1.items.length, 4);
  assert.equal(page2.items.length, 4);
  assert.notEqual(page1.items[0].id, page2.items[0].id);

  // Suggestions & safe HTML escaping in snippet highlighter
  const suggestions = getSearchSuggestions('hybrid', 5);
  assert.ok(suggestions.length >= 1);
  const safeHighlight = highlightSnippet('<script>alert(1)</script> hybrid search', 'hybrid');
  assert.ok(!safeHighlight.includes('<script>'));
  assert.ok(safeHighlight.includes('<mark>hybrid</mark>'));

  // Web address & domain search: www.google.com matches Google and excludes unrelated substring hits
  const googleSearch = runSampleSearch('www.google.com', { mode: 'classic' });
  assert.ok(googleSearch.items.length > 0);
  assert.equal(googleSearch.items[0].id, 'doc-google-portal');
  assert.ok(!googleSearch.items.some((item) => item.id === 'doc-satellite-comms'));
});

test('url-validator enforces SSRF blocks and never invents a clean verdict', () => {
  assert.equal(isRestrictedHost('localhost'), true);
  assert.equal(isRestrictedHost('127.0.0.1'), true);
  assert.equal(isRestrictedHost('10.0.0.5'), true);
  assert.equal(isRestrictedHost('192.168.1.10'), true);
  assert.equal(isRestrictedHost('169.254.169.254'), true);
  assert.equal(isRestrictedHost('::1'), true);
  assert.equal(isRestrictedHost('example.org'), false);

  const blockedLoopback = validateAndInspectUrl('http://127.0.0.1:8000/admin');
  assert.equal(blockedLoopback.ok, false);
  assert.equal(blockedLoopback.blocked, true);

  const blockedScheme = validateAndInspectUrl('javascript:alert(1)');
  assert.equal(blockedScheme.ok, false);
  assert.equal(blockedScheme.blocked, true);

  const validPublic = validateAndInspectUrl('https://example.org/releases/lumo.tar.gz');
  assert.equal(validPublic.ok, true);
  assert.equal(validPublic.hostname, 'example.org');
  assert.equal(validPublic.fileExtension, 'gz');
  assert.equal(validPublic.isDownloadCandidate, true);
  assert.equal(validPublic.riskClassification, 'Unknown');
  assert.equal(validPublic.backendRequired, true);
});
