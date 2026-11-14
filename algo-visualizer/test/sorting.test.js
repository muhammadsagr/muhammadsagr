import test from 'node:test';
import assert from 'node:assert/strict';
import { SORTING, runSort, makeArray, benchmarkSort } from '../src/core/index.js';

const inputs = ['random', 'sorted', 'reversed', 'nearly-sorted', 'few-unique'];

for (const id of Object.keys(SORTING)) {
  test(`${id} sorts every input shape correctly`, () => {
    for (const kind of inputs) {
      for (const n of [0, 1, 2, 7, 50, 257]) {
        const arr = makeArray(n, kind, n + 1);
        const expected = arr.slice().sort((a, b) => a - b);
        assert.deepEqual(runSort(id, arr, { record: false }).result, expected, `${id} ${kind} n=${n}`);
      }
    }
  });

  test(`${id} records replayable steps ending in a fully sorted state`, () => {
    const arr = makeArray(20, 'random', 3);
    const { steps, stats } = runSort(id, arr);
    assert.deepEqual(steps[0].arr, arr);
    const last = steps.at(-1);
    assert.deepEqual(last.arr, arr.slice().sort((a, b) => a - b));
    assert.equal(last.sorted.length, arr.length);
    assert.equal(last.comparisons, stats.comparisons);
  });
}

test('input array is not mutated', () => {
  const arr = [3, 1, 2];
  runSort('quick', arr);
  assert.deepEqual(arr, [3, 1, 2]);
});

test('unknown algorithm throws', () => {
  assert.throws(() => runSort('bogo', [1]), /Unknown sorting algorithm/);
});

test('benchmark shows quadratic vs n log n growth', () => {
  const sizes = [100, 800];
  const ratio = (id) => {
    const [a, b] = benchmarkSort(id, { sizes });
    return b.comparisons / a.comparisons;
  };
  assert.ok(ratio('bubble') > 40, 'bubble ~ 64x when n grows 8x');
  assert.ok(ratio('merge') < 15, 'merge ~ 8x * log factor');
});

test('bubble and insertion are O(n) on sorted input', () => {
  for (const id of ['bubble', 'insertion']) {
    const [{ comparisons }] = benchmarkSort(id, { sizes: [500], input: 'sorted' });
    assert.equal(comparisons, 499);
  }
});
