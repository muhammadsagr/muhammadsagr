import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  catalog,
  runSort,
  runPathfinding,
  benchmarkSort,
  schedulePipeline,
  CI_PIPELINE,
  simulateLoadBalancer,
  generateRequests,
  compareRebalancing,
  simulateAutoscaling,
  TokenBucket,
  SORTING,
  DEFAULT_SIZES,
} from './core/index.js';
import { Registry } from './metrics.js';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const STATIC_DIRS = { '/core/': path.join(ROOT, 'core'), '/': path.join(ROOT, '..', 'public') };
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
};
const MAX_BODY = 256 * 1024;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function createApp({
  version = process.env.APP_VERSION ?? 'dev',
  rateLimit = { capacity: Number(process.env.RATE_LIMIT_BURST ?? 30), refillPerSecond: Number(process.env.RATE_LIMIT_RPS ?? 10) },
  log = (entry) => console.log(JSON.stringify(entry)),
} = {}) {
  const startedAt = Date.now();
  const state = { ready: true };
  const metrics = new Registry();
  const httpRequests = metrics.counter('http_requests_total', 'HTTP requests by method, route and status');
  const httpDuration = metrics.histogram('http_request_duration_seconds', 'HTTP request latency');
  const algoRuns = metrics.counter('algorithm_runs_total', 'Algorithm executions by kind and id');
  const rateLimited = metrics.counter('rate_limited_requests_total', 'Requests rejected by the token bucket');
  metrics.gauge('process_uptime_seconds', 'Process uptime', () => ((Date.now() - startedAt) / 1000).toFixed(0));
  metrics.gauge('process_resident_memory_bytes', 'Resident memory', () => process.memoryUsage().rss);
  metrics.gauge('app_ready', '1 when the instance accepts traffic', () => (state.ready ? 1 : 0));

  const buckets = new Map(); // client ip -> TokenBucket
  const allow = (ip) => {
    if (!buckets.has(ip)) {
      if (buckets.size > 10000) buckets.clear(); // crude memory bound
      buckets.set(ip, new TokenBucket(rateLimit));
    }
    return buckets.get(ip).tryRemove();
  };

  const info = () => ({
    app: 'algo-visualizer',
    version,
    instance: process.env.POD_NAME ?? os.hostname(),
    region: process.env.CLOUD_REGION ?? 'local',
    node: process.version,
    uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
  });

  const api = {
    'GET /healthz': () => ({ status: 'ok' }),
    'GET /readyz': () => {
      if (!state.ready) throw new HttpError(503, 'shutting down');
      return { status: 'ready' };
    },
    'GET /api/info': info,
    'GET /api/algorithms': () => catalog(),
    'POST /api/sort': ({ body }) => {
      const { algorithm, array, includeSteps = false } = body;
      if (!Array.isArray(array) || array.length > 5000 || !array.every(Number.isFinite)) {
        throw new HttpError(400, 'array must contain at most 5000 finite numbers');
      }
      const record = includeSteps && array.length <= 100;
      const { result, stats, steps } = runSort(algorithm, array, { record });
      algoRuns.inc({ kind: 'sort', id: algorithm });
      return { algorithm, result, stats, ...(record ? { steps } : {}) };
    },
    'POST /api/pathfind': ({ body }) => {
      const out = runPathfinding(body.algorithm, body.grid ?? {});
      algoRuns.inc({ kind: 'pathfinding', id: body.algorithm });
      return out;
    },
    'GET /api/benchmark': ({ query }) => {
      const algorithm = query.get('algorithm') ?? 'quick';
      const input = query.get('input') ?? 'random';
      const sizes = query.get('sizes') ? query.get('sizes').split(',').map(Number) : DEFAULT_SIZES;
      if (!SORTING[algorithm]) throw new HttpError(400, `unknown algorithm ${algorithm}`);
      if (sizes.length > 10 || sizes.some((n) => !Number.isInteger(n) || n < 1 || n > 4000)) {
        throw new HttpError(400, 'sizes must be up to 10 integers in [1, 4000]');
      }
      algoRuns.inc({ kind: 'benchmark', id: algorithm });
      return { algorithm, input, instance: info().instance, results: benchmarkSort(algorithm, { sizes, input }) };
    },
    'POST /api/pipeline': ({ body }) => {
      algoRuns.inc({ kind: 'cloud', id: 'pipeline' });
      return schedulePipeline(body.nodes ? body : CI_PIPELINE);
    },
    'POST /api/loadbalance': ({ body }) => {
      const { servers, strategy, requestCount = 300, seed } = body;
      if (!Array.isArray(servers) || servers.length > 20) throw new HttpError(400, 'servers must be an array (max 20)');
      if (requestCount > 5000) throw new HttpError(400, 'requestCount must be <= 5000');
      algoRuns.inc({ kind: 'cloud', id: `lb-${strategy}` });
      const { stats } = simulateLoadBalancer({ servers, strategy, requests: generateRequests(requestCount, seed) });
      return { strategy, stats };
    },
    'POST /api/hashring': ({ body }) => {
      const { before = [], after = [], keys = 1000, virtualNodes = 50 } = body;
      if (after.length < 1 || after.length > 50 || keys > 20000 || virtualNodes > 500) {
        throw new HttpError(400, 'invalid ring parameters');
      }
      algoRuns.inc({ kind: 'cloud', id: 'hashring' });
      return compareRebalancing(before, after, keys, virtualNodes);
    },
    'POST /api/autoscale': ({ body }) => {
      if (!Array.isArray(body.load) || body.load.length > 500) throw new HttpError(400, 'load must be an array (max 500)');
      algoRuns.inc({ kind: 'cloud', id: 'hpa' });
      return { timeline: simulateAutoscaling(body) };
    },
    'GET /metrics': () => metrics.render(),
  };

  async function readJson(req) {
    let size = 0;
    const chunks = [];
    for await (const chunk of req) {
      size += chunk.length;
      if (size > MAX_BODY) throw new HttpError(413, 'body too large');
      chunks.push(chunk);
    }
    if (!chunks.length) return {};
    try {
      return JSON.parse(Buffer.concat(chunks).toString('utf8'));
    } catch {
      throw new HttpError(400, 'invalid JSON body');
    }
  }

  async function serveStatic(pathname, res) {
    for (const [prefix, dir] of Object.entries(STATIC_DIRS)) {
      if (!pathname.startsWith(prefix)) continue;
      const rel = pathname.slice(prefix.length) || 'index.html';
      const file = path.resolve(dir, rel);
      if (!file.startsWith(dir + path.sep)) throw new HttpError(403, 'forbidden'); // path traversal guard
      try {
        const data = await fs.readFile(file);
        res.writeHead(200, {
          'content-type': MIME[path.extname(file)] ?? 'application/octet-stream',
          'cache-control': 'no-cache',
        });
        res.end(data);
        return 'static';
      } catch (err) {
        if (err.code !== 'ENOENT' && err.code !== 'EISDIR') throw err;
      }
    }
    throw new HttpError(404, 'not found');
  }

  async function handler(req, res) {
    const t0 = process.hrtime.bigint();
    const url = new URL(req.url, 'http://localhost');
    const key = `${req.method} ${url.pathname}`;
    let route = api[key] ? url.pathname : 'static';
    let status = 200;
    res.setHeader('x-served-by', info().instance);
    res.setHeader('x-content-type-options', 'nosniff');
    res.setHeader('x-frame-options', 'DENY');
    res.setHeader('referrer-policy', 'no-referrer');
    res.setHeader('content-security-policy', "default-src 'self'; style-src 'self' 'unsafe-inline'");
    try {
      if (api[key]) {
        if (url.pathname.startsWith('/api/') && !allow(req.socket.remoteAddress ?? 'unknown')) {
          rateLimited.inc();
          res.setHeader('retry-after', '1');
          throw new HttpError(429, 'rate limit exceeded');
        }
        const body = req.method === 'POST' ? await readJson(req) : {};
        const out = api[key]({ body, query: url.searchParams });
        if (typeof out === 'string') {
          res.writeHead(200, { 'content-type': 'text/plain; version=0.0.4' });
          res.end(out);
        } else {
          res.writeHead(200, { 'content-type': 'application/json' });
          res.end(JSON.stringify(out));
        }
      } else if (req.method === 'GET' || req.method === 'HEAD') {
        await serveStatic(url.pathname, res);
      } else {
        route = 'unknown';
        throw new HttpError(405, 'method not allowed');
      }
    } catch (err) {
      status = err.status ?? (err instanceof Error && /Unknown|must|range|Duplicate|Edge/.test(err.message) ? 400 : 500);
      if (status === 404) route = 'not_found';
      if (status === 500) log({ level: 'error', msg: err.message, stack: err.stack, path: url.pathname });
      if (!res.headersSent) {
        res.writeHead(status, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: status === 500 ? 'internal error' : err.message }));
      }
    } finally {
      status = res.statusCode || status;
      const seconds = Number(process.hrtime.bigint() - t0) / 1e9;
      httpRequests.inc({ method: req.method, route, status });
      httpDuration.observe({ route }, seconds);
      if (route !== 'static' && !url.pathname.startsWith('/healthz') && !url.pathname.startsWith('/metrics')) {
        log({ level: 'info', method: req.method, path: url.pathname, status, ms: +(seconds * 1000).toFixed(2) });
      }
    }
  }

  return { handler, state, metrics };
}
