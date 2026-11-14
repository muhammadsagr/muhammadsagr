// Sorting algorithms instrumented with a Tracer.
// Every comparison / write is counted; when `record` is true a snapshot of the
// array is stored so the UI can replay the algorithm step by step.

class Tracer {
  constructor(input, record) {
    this.a = input.slice();
    this.record = record;
    this.steps = [];
    this.stats = { comparisons: 0, writes: 0 };
    this.sorted = new Set();
  }

  snap(extra = {}) {
    if (!this.record) return;
    this.steps.push({
      arr: this.a.slice(),
      sorted: [...this.sorted],
      comparisons: this.stats.comparisons,
      writes: this.stats.writes,
      ...extra,
    });
  }

  // Compare a[i] with a[j]; returns negative / 0 / positive.
  cmp(i, j) {
    this.stats.comparisons++;
    this.snap({ compare: [i, j] });
    return this.a[i] - this.a[j];
  }

  // Compare two values that are not (only) in the main array, e.g. merge sort's aux buffer.
  cmpValues(x, y, highlight) {
    this.stats.comparisons++;
    this.snap({ compare: highlight });
    return x - y;
  }

  swap(i, j) {
    if (i === j) return;
    const a = this.a;
    [a[i], a[j]] = [a[j], a[i]];
    this.stats.writes += 2;
    this.snap({ swap: [i, j] });
  }

  set(i, value) {
    this.a[i] = value;
    this.stats.writes++;
    this.snap({ swap: [i] });
  }

  markSorted(...indices) {
    for (const i of indices) this.sorted.add(i);
  }

  finish() {
    this.a.forEach((_, i) => this.sorted.add(i));
    this.snap();
    return { result: this.a, steps: this.steps, stats: this.stats };
  }
}

function bubbleSort(t) {
  const n = t.a.length;
  for (let i = 0; i < n - 1; i++) {
    let swapped = false;
    for (let j = 0; j < n - 1 - i; j++) {
      if (t.cmp(j, j + 1) > 0) {
        t.swap(j, j + 1);
        swapped = true;
      }
    }
    t.markSorted(n - 1 - i);
    if (!swapped) break; // already sorted -> O(n) best case
  }
}

function selectionSort(t) {
  const n = t.a.length;
  for (let i = 0; i < n - 1; i++) {
    let min = i;
    for (let j = i + 1; j < n; j++) if (t.cmp(j, min) < 0) min = j;
    t.swap(i, min);
    t.markSorted(i);
  }
}

function insertionSort(t) {
  const n = t.a.length;
  for (let i = 1; i < n; i++) {
    let j = i;
    while (j > 0 && t.cmp(j - 1, j) > 0) {
      t.swap(j - 1, j);
      j--;
    }
  }
}

function mergeSort(t) {
  const a = t.a;
  const aux = new Array(a.length);
  const sort = (lo, hi) => {
    if (hi <= lo) return;
    const mid = (lo + hi) >> 1;
    sort(lo, mid);
    sort(mid + 1, hi);
    for (let k = lo; k <= hi; k++) aux[k] = a[k];
    let i = lo;
    let j = mid + 1;
    for (let k = lo; k <= hi; k++) {
      if (i > mid) t.set(k, aux[j++]);
      else if (j > hi) t.set(k, aux[i++]);
      else if (t.cmpValues(aux[j], aux[i], [k, j]) < 0) t.set(k, aux[j++]);
      else t.set(k, aux[i++]);
    }
  };
  sort(0, a.length - 1);
}

function quickSort(t) {
  // Lomuto partition with the middle element as pivot (avoids O(n²) on sorted input).
  const sort = (lo, hi) => {
    if (lo > hi) return;
    if (lo === hi) {
      t.markSorted(lo);
      return;
    }
    t.swap((lo + hi) >> 1, hi);
    let p = lo;
    for (let i = lo; i < hi; i++) {
      if (t.cmp(i, hi) < 0) {
        t.swap(i, p);
        p++;
      }
    }
    t.swap(p, hi);
    t.markSorted(p);
    sort(lo, p - 1);
    sort(p + 1, hi);
  };
  sort(0, t.a.length - 1);
}

function heapSort(t) {
  const n = t.a.length;
  const siftDown = (i, size) => {
    for (;;) {
      const l = 2 * i + 1;
      const r = l + 1;
      let m = i;
      if (l < size && t.cmp(l, m) > 0) m = l;
      if (r < size && t.cmp(r, m) > 0) m = r;
      if (m === i) return;
      t.swap(i, m);
      i = m;
    }
  };
  for (let i = (n >> 1) - 1; i >= 0; i--) siftDown(i, n);
  for (let end = n - 1; end > 0; end--) {
    t.swap(0, end);
    t.markSorted(end);
    siftDown(0, end);
  }
}

function shellSort(t) {
  const n = t.a.length;
  let gap = 1;
  while (gap < n / 3) gap = 3 * gap + 1; // Knuth sequence
  for (; gap >= 1; gap = Math.floor(gap / 3)) {
    for (let i = gap; i < n; i++) {
      for (let j = i; j >= gap && t.cmp(j - gap, j) > 0; j -= gap) t.swap(j - gap, j);
    }
  }
}

export const SORTING = {
  bubble: {
    name: 'Bubble Sort',
    complexity: { best: 'O(n)', average: 'O(n²)', worst: 'O(n²)', space: 'O(1)' },
    stable: true,
    run: bubbleSort,
  },
  selection: {
    name: 'Selection Sort',
    complexity: { best: 'O(n²)', average: 'O(n²)', worst: 'O(n²)', space: 'O(1)' },
    stable: false,
    run: selectionSort,
  },
  insertion: {
    name: 'Insertion Sort',
    complexity: { best: 'O(n)', average: 'O(n²)', worst: 'O(n²)', space: 'O(1)' },
    stable: true,
    run: insertionSort,
  },
  shell: {
    name: 'Shell Sort',
    complexity: { best: 'O(n log n)', average: '≈O(n^1.25)', worst: 'O(n^1.5)', space: 'O(1)' },
    stable: false,
    run: shellSort,
  },
  merge: {
    name: 'Merge Sort',
    complexity: { best: 'O(n log n)', average: 'O(n log n)', worst: 'O(n log n)', space: 'O(n)' },
    stable: true,
    run: mergeSort,
  },
  quick: {
    name: 'Quick Sort',
    complexity: { best: 'O(n log n)', average: 'O(n log n)', worst: 'O(n²)', space: 'O(log n)' },
    stable: false,
    run: quickSort,
  },
  heap: {
    name: 'Heap Sort',
    complexity: { best: 'O(n log n)', average: 'O(n log n)', worst: 'O(n log n)', space: 'O(1)' },
    stable: false,
    run: heapSort,
  },
};

export function runSort(id, input, { record = true } = {}) {
  const algo = SORTING[id];
  if (!algo) throw new Error(`Unknown sorting algorithm: ${id}`);
  const t = new Tracer(input, record);
  t.snap();
  algo.run(t);
  return t.finish();
}
