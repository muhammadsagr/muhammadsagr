import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { buildStandalone } from '../scripts/build-standalone.mjs';

test('standalone html (double-click version) is up to date', () => {
  const committed = fs.readFileSync(new URL('../../algo_visualizer.html', import.meta.url), 'utf8');
  assert.equal(committed, buildStandalone(), 'run: npm run build:standalone');
});
