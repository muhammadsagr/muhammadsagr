import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { createApp } from '../src/app.js';

async function withServer(opts, fn) {
  const app = createApp({ log: () => {}, ...opts });
  const server = http.createServer(app.handler);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await fn(base, app);
  } finally {
    await new Promise((r) => server.close(r));
  }
}

const post = (url, body) =>
  fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });

test('health, readiness and info endpoints', () =>
  withServer({}, async (base, app) => {
    assert.equal((await fetch(`${base}/healthz`)).status, 200);
    assert.equal((await fetch(`${base}/readyz`)).status, 200);
    const info = await (await fetch(`${base}/api/info`)).json();
    assert.equal(info.app, 'algo-visualizer');
    app.state.ready = false;
    assert.equal((await fetch(`${base}/readyz`)).status, 503, 'readiness fails while draining');
  }));

test('sort, pathfind, pipeline, loadbalance, hashring, autoscale, benchmark', () =>
  withServer({}, async (base) => {
    const sort = await (await post(`${base}/api/sort`, { algorithm: 'merge', array: [3, 1, 2], includeSteps: true })).json();
    assert.deepEqual(sort.result, [1, 2, 3]);
    assert.ok(sort.steps.length > 0);

    const grid = { rows: 3, cols: 3, walls: [], weights: [], start: 0, end: 8 };
    const pf = await (await post(`${base}/api/pathfind`, { algorithm: 'astar', grid })).json();
    assert.equal(pf.stats.pathCost, 4);

    const pipe = await (await post(`${base}/api/pipeline`, {})).json();
    assert.equal(pipe.hasCycle, false);

    const lb = await (await post(`${base}/api/loadbalance`, { servers: [{ id: 'a', capacity: 1 }], strategy: 'random' })).json();
    assert.equal(lb.stats.handled[0], 300);

    const ring = await (await post(`${base}/api/hashring`, { before: ['a', 'b'], after: ['a', 'b', 'c'] })).json();
    assert.ok(ring.consistent.percent < ring.modulo.percent);

    const hpa = await (await post(`${base}/api/autoscale`, { load: [10, 200], targetPerPod: 50 })).json();
    assert.equal(hpa.timeline.length, 2);

    const bench = await (await fetch(`${base}/api/benchmark?algorithm=heap&sizes=10,20`)).json();
    assert.deepEqual(bench.results.map((r) => r.n), [10, 20]);
  }));

test('validation errors return 400', () =>
  withServer({}, async (base) => {
    assert.equal((await post(`${base}/api/sort`, { algorithm: 'nope', array: [1] })).status, 400);
    assert.equal((await post(`${base}/api/sort`, { algorithm: 'quick', array: 'x' })).status, 400);
    assert.equal((await fetch(`${base}/api/benchmark?algorithm=quick&sizes=999999`)).status, 400);
    const bad = await fetch(`${base}/api/sort`, { method: 'POST', body: '{nope' });
    assert.equal(bad.status, 400);
  }));

test('static files are served and path traversal is blocked', () =>
  withServer({}, async (base) => {
    const index = await fetch(`${base}/`);
    assert.equal(index.status, 200);
    assert.match(index.headers.get('content-type'), /text\/html/);
    assert.equal((await fetch(`${base}/core/sorting.js`)).status, 200);
    assert.equal((await fetch(`${base}/missing.js`)).status, 404);
    const traversal = await new Promise((resolve) => {
      const u = new URL(base);
      http.get({ host: u.hostname, port: u.port, path: '/core/../../package.json' }, (res) => resolve(res.statusCode));
    });
    assert.ok([403, 404].includes(traversal));
  }));

test('token-bucket rate limiting returns 429', () =>
  withServer({ rateLimit: { capacity: 2, refillPerSecond: 0.001 } }, async (base) => {
    const codes = [];
    for (let i = 0; i < 4; i++) codes.push((await fetch(`${base}/api/info`)).status);
    assert.deepEqual(codes, [200, 200, 429, 429]);
    assert.equal((await fetch(`${base}/healthz`)).status, 200, 'probes are never rate limited');
  }));

test('prometheus metrics are exposed', () =>
  withServer({}, async (base) => {
    await post(`${base}/api/sort`, { algorithm: 'quick', array: [2, 1] });
    const text = await (await fetch(`${base}/metrics`)).text();
    assert.match(text, /http_requests_total\{method="POST",route="\/api\/sort",status="200"\} 1/);
    assert.match(text, /algorithm_runs_total\{kind="sort",id="quick"\} 1/);
    assert.match(text, /http_request_duration_seconds_bucket/);
  }));
