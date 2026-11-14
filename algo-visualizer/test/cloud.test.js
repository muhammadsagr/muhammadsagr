import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CI_PIPELINE,
  schedulePipeline,
  simulateLoadBalancer,
  generateRequests,
  LB_STRATEGIES,
  HashRing,
  compareRebalancing,
  TokenBucket,
  hpaDesiredReplicas,
  simulateAutoscaling,
} from '../src/core/index.js';

test('topological order respects every dependency', () => {
  const r = schedulePipeline(CI_PIPELINE);
  assert.equal(r.hasCycle, false);
  const pos = new Map(r.order.map((id, i) => [id, i]));
  for (const [a, b] of CI_PIPELINE.edges) assert.ok(pos.get(a) < pos.get(b), `${a} before ${b}`);
  assert.equal(r.steps.length, CI_PIPELINE.nodes.length);
});

test('critical path and makespan', () => {
  const r = schedulePipeline(CI_PIPELINE);
  assert.deepEqual(r.criticalPath, ['checkout', 'install', 'build', 'scan', 'push', 'staging', 'e2e', 'approve', 'prod']);
  assert.equal(r.makespan, 1 + 3 + 6 + 3 + 2 + 3 + 7 + 1 + 3);
  assert.ok(r.makespan < r.sequentialTime);
});

test('cycle is detected and reported', () => {
  const dag = { nodes: CI_PIPELINE.nodes, edges: [...CI_PIPELINE.edges, ['prod', 'install']] };
  const r = schedulePipeline(dag);
  assert.equal(r.hasCycle, true);
  assert.ok(r.blocked.includes('install') && r.blocked.includes('prod'));
  assert.ok(!r.blocked.includes('checkout'));
});

test('unknown edge endpoints are rejected', () => {
  assert.throws(() => schedulePipeline({ nodes: [{ id: 'a' }], edges: [['a', 'b']] }), /unknown node/);
});

const servers = [
  { id: 'a', capacity: 1 },
  { id: 'b', capacity: 2 },
  { id: 'c', capacity: 4 },
];

test('every strategy assigns every request exactly once', () => {
  const requests = generateRequests(200);
  for (const strategy of Object.keys(LB_STRATEGIES)) {
    const r = simulateLoadBalancer({ servers, requests, strategy });
    assert.equal(r.stats.handled.reduce((s, x) => s + x, 0), 200, strategy);
    assert.equal(r.steps.length, 200);
  }
});

test('round robin splits evenly; weighted round robin follows capacity', () => {
  const requests = generateRequests(70);
  assert.deepEqual(simulateLoadBalancer({ servers, requests, strategy: 'round-robin' }).stats.handled, [24, 23, 23]);
  assert.deepEqual(simulateLoadBalancer({ servers, requests, strategy: 'weighted-round-robin' }).stats.handled, [10, 20, 40]);
});

test('load-aware strategies beat round robin on tail latency with heterogeneous servers', () => {
  const requests = generateRequests(500);
  const p99 = (strategy) => simulateLoadBalancer({ servers, requests, strategy }).stats.p99Latency;
  assert.ok(p99('least-connections') < p99('round-robin'));
  assert.ok(p99('power-of-two') < p99('random'));
});

test('hash ring lookup is stable and spreads keys', () => {
  const ring = new HashRing(['a', 'b', 'c', 'd'], 100);
  assert.equal(ring.getNode('user:42'), ring.getNode('user:42'));
  const counts = {};
  for (let i = 0; i < 4000; i++) counts[ring.getNode(`k${i}`)] = (counts[ring.getNode(`k${i}`)] ?? 0) + 1;
  for (const n of ['a', 'b', 'c', 'd']) assert.ok(counts[n] > 700 && counts[n] < 1300, `${n}: ${counts[n]}`);
});

test('adding a node moves ~1/N keys with consistent hashing but most keys with modulo', () => {
  const r = compareRebalancing(['a', 'b', 'c', 'd'], ['a', 'b', 'c', 'd', 'e'], 5000, 100);
  assert.ok(r.consistent.percent < 30, `consistent moved ${r.consistent.percent}%`);
  assert.ok(r.modulo.percent > 60, `modulo moved ${r.modulo.percent}%`);
});

test('removing a node only moves the keys it owned', () => {
  const before = new HashRing(['a', 'b', 'c'], 50);
  const after = new HashRing(['a', 'b'], 50);
  for (let i = 0; i < 2000; i++) {
    const k = `k${i}`;
    if (before.getNode(k) !== 'c') assert.equal(after.getNode(k), before.getNode(k));
  }
});

test('token bucket allows bursts then refills over time', () => {
  let now = 0;
  const b = new TokenBucket({ capacity: 3, refillPerSecond: 2, now: () => now });
  assert.deepEqual([b.tryRemove(), b.tryRemove(), b.tryRemove(), b.tryRemove()], [true, true, true, false]);
  now = 500; // +1 token
  assert.equal(b.tryRemove(), true);
  assert.equal(b.tryRemove(), false);
});

test('HPA formula', () => {
  assert.equal(hpaDesiredReplicas({ current: 2, currentMetric: 100, targetMetric: 50 }), 4);
  assert.equal(hpaDesiredReplicas({ current: 4, currentMetric: 52, targetMetric: 50 }), 4, 'within tolerance');
  assert.equal(hpaDesiredReplicas({ current: 4, currentMetric: 10, targetMetric: 50, min: 2 }), 2);
  assert.equal(hpaDesiredReplicas({ current: 4, currentMetric: 1000, targetMetric: 50, max: 10 }), 10);
  const tl = simulateAutoscaling({ load: [50, 500, 500, 500, 50, 50], targetPerPod: 50, min: 1, max: 20 });
  assert.equal(tl[0].replicas, 1);
  assert.equal(tl[2].replicas, 10);
});
