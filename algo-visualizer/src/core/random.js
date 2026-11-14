// Seeded pseudo-random generator (mulberry32) so runs and benchmarks are reproducible.
export function createRng(seed = 1) {
  let a = seed >>> 0;
  return function rng() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randomInt(rng, min, max) {
  return min + Math.floor(rng() * (max - min + 1));
}

/**
 * Build an input array for sorting.
 * kind: random | sorted | reversed | nearly-sorted | few-unique
 */
export function makeArray(n, kind = 'random', seed = 42, max = 100) {
  const rng = createRng(seed);
  let arr = Array.from({ length: n }, () => randomInt(rng, 1, max));
  switch (kind) {
    case 'sorted':
      arr.sort((x, y) => x - y);
      break;
    case 'reversed':
      arr.sort((x, y) => y - x);
      break;
    case 'nearly-sorted':
      arr.sort((x, y) => x - y);
      for (let k = 0; k < Math.max(1, Math.floor(n / 10)); k++) {
        const i = randomInt(rng, 0, n - 1);
        const j = randomInt(rng, 0, n - 1);
        [arr[i], arr[j]] = [arr[j], arr[i]];
      }
      break;
    case 'few-unique':
      arr = arr.map((v) => Math.ceil(v / (max / 4)) * Math.floor(max / 4));
      break;
    case 'random':
      break;
    default:
      throw new Error(`Unknown input kind: ${kind}`);
  }
  return arr;
}
