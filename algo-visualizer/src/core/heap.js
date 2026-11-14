// Binary min-heap (priority queue). push/pop are O(log n).
export class MinHeap {
  constructor(priority = (x) => x) {
    this.items = [];
    this.priority = priority;
  }

  get size() {
    return this.items.length;
  }

  push(item) {
    const a = this.items;
    a.push(item);
    let i = a.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this.priority(a[parent]) <= this.priority(a[i])) break;
      [a[parent], a[i]] = [a[i], a[parent]];
      i = parent;
    }
  }

  pop() {
    const a = this.items;
    if (a.length === 0) return undefined;
    const top = a[0];
    const last = a.pop();
    if (a.length > 0) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < a.length && this.priority(a[l]) < this.priority(a[m])) m = l;
        if (r < a.length && this.priority(a[r]) < this.priority(a[m])) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]];
        i = m;
      }
    }
    return top;
  }
}
