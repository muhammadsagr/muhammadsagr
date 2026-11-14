import { runSort } from './sorting.js';
import { makeArray } from './random.js';

export const DEFAULT_SIZES = [50, 100, 200, 400, 800, 1600];

// Measure operation counts (deterministic) and wall time (machine dependent).
export function benchmarkSort(id, { sizes = DEFAULT_SIZES, input = 'random', seed = 42 } = {}) {
  return sizes.map((n) => {
    const arr = makeArray(n, input, seed + n, 1000);
    const t0 = performance.now();
    const { stats } = runSort(id, arr, { record: false });
    const ms = performance.now() - t0;
    return { n, comparisons: stats.comparisons, writes: stats.writes, ms: +ms.toFixed(3) };
  });
}
