// Algorithms that power real cloud / DevOps systems.
import { createRng, randomInt } from './random.js';
import { MinHeap } from './heap.js';

/* ------------------------------------------------------------------ *
 * 1) CI/CD pipeline scheduling: topological sort (Kahn) + critical path
 * ------------------------------------------------------------------ */

export const CI_PIPELINE = {
  nodes: [
    { id: 'checkout', label: 'Checkout', duration: 1 },
    { id: 'install', label: 'Install deps', duration: 3 },
    { id: 'lint', label: 'Lint', duration: 2 },
    { id: 'unit', label: 'Unit tests', duration: 5 },
    { id: 'sast', label: 'SAST scan', duration: 4 },
    { id: 'build', label: 'Build image', duration: 6 },
    { id: 'scan', label: 'Image scan', duration: 3 },
    { id: 'push', label: 'Push registry', duration: 2 },
    { id: 'staging', label: 'Deploy staging', duration: 3 },
    { id: 'e2e', label: 'E2E tests', duration: 7 },
    { id: 'approve', label: 'Approval', duration: 1 },
    { id: 'prod', label: 'Deploy prod', duration: 3 },
  ],
  edges: [
    ['checkout', 'install'],
    ['checkout', 'sast'],
    ['install', 'lint'],
    ['install', 'unit'],
    ['install', 'build'],
    ['build', 'scan'],
    ['lint', 'push'],
    ['unit', 'push'],
    ['scan', 'push'],
    ['sast', 'push'],
    ['push', 'staging'],
    ['staging', 'e2e'],
    ['e2e', 'approve'],
    ['approve', 'prod'],
  ],
};

export function schedulePipeline({ nodes, edges }) {
  const ids = nodes.map((n) => n.id);
  if (new Set(ids).size !== ids.length) throw new Error('Duplicate node id');
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const adj = new Map(ids.map((id) => [id, []]));
  const radj = new Map(ids.map((id) => [id, []]));
  const indeg = new Map(ids.map((id) => [id, 0]));
  for (const [from, to] of edges) {
    if (!byId.has(from) || !byId.has(to)) throw new Error(`Edge references unknown node: ${from} -> ${to}`);
    adj.get(from).push(to);
    radj.get(to).push(from);
    indeg.set(to, indeg.get(to) + 1);
  }

  // Kahn's algorithm, processed level by level: every level can run in parallel.
  const order = [];
  const levels = [];
  const steps = [];
  let frontier = ids.filter((id) => indeg.get(id) === 0);
  while (frontier.length) {
    levels.push(frontier.slice());
    const next = [];
    frontier.forEach((u, idx) => {
      order.push(u);
      for (const v of adj.get(u)) {
        indeg.set(v, indeg.get(v) - 1);
        if (indeg.get(v) === 0) next.push(v);
      }
      steps.push({
        current: u,
        level: levels.length - 1,
        done: order.slice(),
        ready: [...frontier.slice(idx + 1), ...next],
      });
    });
    frontier = next;
  }

  const hasCycle = order.length < ids.length;
  const blocked = ids.filter((id) => !order.includes(id));
  if (hasCycle) {
    return { order, levels, steps, hasCycle, blocked, schedule: null, criticalPath: [], makespan: null };
  }

  // Critical path = longest path in a DAG, DP over the topological order.
  const earliestStart = new Map();
  const finish = new Map();
  const via = new Map();
  for (const u of order) {
    let start = 0;
    let from = null;
    for (const p of radj.get(u)) {
      if (finish.get(p) > start) {
        start = finish.get(p);
        from = p;
      }
    }
    earliestStart.set(u, start);
    finish.set(u, start + (byId.get(u).duration ?? 1));
    via.set(u, from);
  }
  let last = order[0];
  for (const u of order) if (finish.get(u) > finish.get(last)) last = u;
  const criticalPath = [];
  for (let at = last; at; at = via.get(at)) criticalPath.push(at);
  criticalPath.reverse();
  const sequential = nodes.reduce((s, n) => s + (n.duration ?? 1), 0);

  return {
    order,
    levels,
    steps,
    hasCycle,
    blocked,
    schedule: order.map((id) => ({ id, start: earliestStart.get(id), finish: finish.get(id) })),
    criticalPath,
    makespan: finish.get(last),
    sequentialTime: sequential,
  };
}

/* ------------------------------------------------------------------ *
 * 2) Load balancing strategies (discrete-event simulation)
 * ------------------------------------------------------------------ */

export const LB_STRATEGIES = {
  'round-robin': 'Round Robin',
  'weighted-round-robin': 'Smooth Weighted Round Robin (nginx)',
  'least-connections': 'Least Connections',
  random: 'Random',
  'power-of-two': 'Power of Two Choices',
};

export function generateRequests(count, seed = 3) {
  const rng = createRng(seed);
  const requests = [];
  let t = 0;
  for (let i = 0; i < count; i++) {
    t += randomInt(rng, 0, 2);
    // Heavy-tailed durations: most requests are short, a few are very long.
    const duration = rng() < 0.15 ? randomInt(rng, 15, 40) : randomInt(rng, 2, 8);
    requests.push({ id: i, arrival: t, duration });
  }
  return requests;
}

/**
 * servers: [{ id, capacity }] — capacity = how many requests it serves at full speed
 * (used as weight by weighted strategies). If more requests are active than the
 * capacity, each one is slowed down proportionally (a simple contention model).
 */
export function simulateLoadBalancer({ servers, requests, strategy, seed = 11 }) {
  if (!LB_STRATEGIES[strategy]) throw new Error(`Unknown strategy: ${strategy}`);
  if (!servers.length) throw new Error('At least one server is required');
  const rng = createRng(seed);
  const n = servers.length;
  const active = new Array(n).fill(0);
  const handled = new Array(n).fill(0);
  const peak = new Array(n).fill(0);
  const currentWeight = new Array(n).fill(0);
  const totalWeight = servers.reduce((s, x) => s + x.capacity, 0);
  const completions = new MinHeap((e) => e.at);
  const latencies = [];
  const steps = [];
  let rr = 0;

  const pick = () => {
    switch (strategy) {
      case 'round-robin':
        return rr++ % n;
      case 'weighted-round-robin': {
        let best = 0;
        for (let i = 0; i < n; i++) {
          currentWeight[i] += servers[i].capacity;
          if (currentWeight[i] > currentWeight[best]) best = i;
        }
        currentWeight[best] -= totalWeight;
        return best;
      }
      case 'least-connections': {
        let best = 0;
        for (let i = 1; i < n; i++) {
          if (active[i] / servers[i].capacity < active[best] / servers[best].capacity) best = i;
        }
        return best;
      }
      case 'random':
        return Math.floor(rng() * n);
      case 'power-of-two': {
        const a = Math.floor(rng() * n);
        const b = Math.floor(rng() * n);
        return active[a] / servers[a].capacity <= active[b] / servers[b].capacity ? a : b;
      }
      default:
        throw new Error('unreachable');
    }
  };

  for (const req of requests) {
    while (completions.size && completions.items[0].at <= req.arrival) {
      active[completions.pop().server]--;
    }
    const s = pick();
    const slowdown = Math.max(1, (active[s] + 1) / servers[s].capacity);
    const latency = req.duration * slowdown;
    active[s]++;
    handled[s]++;
    peak[s] = Math.max(peak[s], active[s]);
    latencies.push(latency);
    completions.push({ at: req.arrival + latency, server: s });
    steps.push({ time: req.arrival, request: req.id, server: s, latency, active: active.slice() });
  }

  const sorted = latencies.slice().sort((a, b) => a - b);
  const pct = (p) => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))] ?? 0;
  const avg = sorted.reduce((s, x) => s + x, 0) / (sorted.length || 1);
  return {
    strategy,
    steps,
    stats: {
      handled,
      peak,
      avgLatency: +avg.toFixed(2),
      p95Latency: +pct(0.95).toFixed(2),
      p99Latency: +pct(0.99).toFixed(2),
    },
  };
}

/* ------------------------------------------------------------------ *
 * 3) Consistent hashing (used by CDNs, DynamoDB, Cassandra, memcached clients)
 * ------------------------------------------------------------------ */

// FNV-1a followed by the murmur3 finalizer for a good avalanche effect.
export function hash32(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return h >>> 0;
}

export class HashRing {
  constructor(nodes = [], virtualNodes = 50) {
    this.virtualNodes = virtualNodes;
    this.ring = []; // sorted [{ hash, node }]
    for (const n of nodes) this.addNode(n);
  }

  get nodes() {
    return [...new Set(this.ring.map((p) => p.node))];
  }

  addNode(node) {
    for (let v = 0; v < this.virtualNodes; v++) this.ring.push({ hash: hash32(`${node}#${v}`), node });
    this.ring.sort((a, b) => a.hash - b.hash);
  }

  removeNode(node) {
    this.ring = this.ring.filter((p) => p.node !== node);
  }

  // Binary search for the first point clockwise from the key's hash: O(log(N·V)).
  getNode(key) {
    if (!this.ring.length) return null;
    const h = hash32(key);
    let lo = 0;
    let hi = this.ring.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.ring[mid].hash < h) lo = mid + 1;
      else hi = mid;
    }
    return this.ring[lo === this.ring.length ? 0 : lo].node;
  }
}

const moduloNode = (nodes, key) => nodes[hash32(key) % nodes.length];

// How many keys move when the cluster changes from `before` to `after`?
export function compareRebalancing(before, after, keyCount = 1000, virtualNodes = 50) {
  const keys = Array.from({ length: keyCount }, (_, i) => `key-${i}`);
  const r1 = new HashRing(before, virtualNodes);
  const r2 = new HashRing(after, virtualNodes);
  let movedRing = 0;
  let movedModulo = 0;
  const distribution = Object.fromEntries(after.map((n) => [n, 0]));
  for (const k of keys) {
    const owner = r2.getNode(k);
    distribution[owner]++;
    if (r1.getNode(k) !== owner) movedRing++;
    if (before.length && moduloNode(before, k) !== moduloNode(after, k)) movedModulo++;
  }
  return {
    keys: keyCount,
    consistent: { moved: movedRing, percent: +((100 * movedRing) / keyCount).toFixed(1) },
    modulo: { moved: movedModulo, percent: +((100 * movedModulo) / keyCount).toFixed(1) },
    distribution,
  };
}

/* ------------------------------------------------------------------ *
 * 4) Token bucket rate limiter (API gateways, nginx limit_req, AWS API GW)
 * ------------------------------------------------------------------ */

export class TokenBucket {
  constructor({ capacity, refillPerSecond, now = () => Date.now() }) {
    this.capacity = capacity;
    this.refillPerMs = refillPerSecond / 1000;
    this.now = now;
    this.tokens = capacity;
    this.last = now();
  }

  tryRemove(count = 1) {
    const t = this.now();
    this.tokens = Math.min(this.capacity, this.tokens + (t - this.last) * this.refillPerMs);
    this.last = t;
    if (this.tokens >= count) {
      this.tokens -= count;
      return true;
    }
    return false;
  }
}

/* ------------------------------------------------------------------ *
 * 5) Kubernetes Horizontal Pod Autoscaler formula
 * desired = ceil(current * currentMetric / targetMetric), clamped to [min, max],
 * ignored while inside the tolerance band (default 10%).
 * ------------------------------------------------------------------ */

export function hpaDesiredReplicas({ current, currentMetric, targetMetric, min = 1, max = 10, tolerance = 0.1 }) {
  const ratio = currentMetric / targetMetric;
  if (Math.abs(ratio - 1) <= tolerance) return Math.min(max, Math.max(min, current));
  return Math.min(max, Math.max(min, Math.ceil(current * ratio)));
}

export function simulateAutoscaling({ load, targetPerPod = 50, min = 1, max = 10 }) {
  let replicas = min;
  return load.map((rps, t) => {
    const perPod = rps / replicas;
    const next = hpaDesiredReplicas({ current: replicas, currentMetric: perPod, targetMetric: targetPerPod, min, max });
    const row = { t, rps, replicas, perPod: +perPod.toFixed(1) };
    replicas = next;
    return row;
  });
}
