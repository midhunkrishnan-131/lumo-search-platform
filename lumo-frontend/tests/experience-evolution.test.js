import test from 'node:test';
import assert from 'node:assert/strict';

import { buildCommandItems } from '../js/command-palette.js';
import { formatSafeError } from '../js/api.js';

test('command palette builds grouped navigation and quick search items', () => {
  const modules = [
    { id: 'command-center', group: 'Platform', label: 'Intelligence Command Center', href: './command-center.html' },
    { id: 'research', group: 'Research', label: 'Autonomous Research Agent', href: './research.html' },
  ];

  const all = buildCommandItems(modules, '');
  assert.equal(all.length, 2);
  assert.equal(all[0].category, 'Platform');

  const filtered = buildCommandItems(modules, 'Research');
  assert.ok(filtered.some((i) => i.id === 'nav:research'));
  assert.ok(filtered.some((i) => i.id === 'search:hybrid'));
  assert.ok(filtered.some((i) => i.id === 'search:ai'));
  assert.ok(filtered.some((i) => i.id === 'search:workspace'));
});

test('formatSafeError maps network, rate-limit, and auth errors safely', () => {
  assert.match(formatSafeError(new Error('Failed to fetch')), /Unable to reach the LUMO backend/);
  assert.match(formatSafeError(new Error('HTTP 429 Too Many Requests')), /Rate limit exceeded/);
  assert.match(formatSafeError(new Error('HTTP 403 Forbidden')), /Authorization required/);
  assert.equal(formatSafeError(new Error('x'.repeat(400))).length, 240);
});
