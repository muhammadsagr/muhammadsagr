// Front-end: the same algorithm modules run in the browser (for step-by-step
// animation) and on the server (API + benchmarks). Served from /core/.
import {
  SORTING,
  runSort,
  makeArray,
  PATHFINDING,
  runPathfinding,
  randomGrid,
  WEIGHT_COST,
  CI_PIPELINE,
  schedulePipeline,
  LB_STRATEGIES,
  simulateLoadBalancer,
  generateRequests,
  HashRing,
  hash32,
  compareRebalancing,
  simulateAutoscaling,
  benchmarkSort,
} from '/core/index.js';

const $ = (sel) => document.querySelector(sel);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const PALETTE = ['#4f8cff', '#36c98e', '#f5c84c', '#ff5d6c', '#9b7bff', '#2ec4d6', '#ff9f43', '#e86fd1', '#a3d65c', '#c0c7da'];
const fmt = (n) => (typeof n === 'number' ? n.toLocaleString('en-US') : n);

/* ---------------- API helper with graceful degradation ---------------- */
async function api(path, { method = 'GET', body } = {}, fallback) {
  try {
    const res = await fetch(path, {
      method,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`${res.status} ${(await res.json().catch(() => ({}))).error ?? ''}`);
    return { data: await res.json(), source: res.headers.get('x-served-by') ?? 'server' };
  } catch (err) {
    if (!fallback) throw err;
    console.warn(`API ${path} failed (${err.message}); running locally in the browser`);
    return { data: fallback(), source: 'browser (fallback)' };
  }
}

async function refreshInstance() {
  try {
    const { data } = await api('/api/info');
    $('#instance').classList.add('online');
    $('#instance-text').textContent = `${data.instance} · v${data.version} · ${data.region}`;
  } catch {
    $('#instance').classList.remove('online');
    $('#instance-text').textContent = 'offline';
  }
}
refreshInstance();
setInterval(refreshInstance, 5000);

/* ---------------- Tabs ---------------- */
const onShow = {};
document.querySelectorAll('.tab').forEach((tab) =>
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === tab));
    document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('active', p.id === `panel-${tab.dataset.tab}`));
    onShow[tab.dataset.tab]?.();
  }),
);

/* ---------------- Canvas helper ---------------- */
function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = Number(canvas.getAttribute('height'));
  if (canvas.width !== Math.round(w * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.height = `${h}px`;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

/* ---------------- Generic step player ---------------- */
class Player {
  constructor(name, render) {
    this.render = render;
    this.steps = 0;
    this.index = 0;
    this.playing = false;
    const root = document.querySelector(`[data-player="${name}"]`);
    root.innerHTML = `
      <button data-act="reset">⏮ البداية</button>
      <button data-act="prev">خطوة للخلف</button>
      <button data-act="play" class="primary">▶ تشغيل</button>
      <button data-act="next">خطوة للأمام</button>
      <button data-act="end">النهاية ⏭</button>
      <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)">السرعة
        <input data-act="speed" type="range" min="1" max="100" value="55" style="min-width:100px"></label>
      <input data-act="progress" type="range" min="0" max="0" value="0">
      <span class="status" data-act="status"></span>`;
    this.el = Object.fromEntries([...root.querySelectorAll('[data-act]')].map((e) => [e.dataset.act, e]));
    this.el.play.onclick = () => (this.playing ? this.pause() : this.play());
    this.el.prev.onclick = () => (this.pause(), this.go(this.index - 1));
    this.el.next.onclick = () => (this.pause(), this.go(this.index + 1));
    this.el.reset.onclick = () => (this.pause(), this.go(0));
    this.el.end.onclick = () => (this.pause(), this.go(this.steps - 1));
    this.el.progress.oninput = () => (this.pause(), this.go(Number(this.el.progress.value)));
  }

  load(steps, { autoplay = true } = {}) {
    this.pause();
    this.steps = steps;
    this.el.progress.max = Math.max(0, steps - 1);
    this.go(0);
    if (autoplay) this.play();
  }

  go(i) {
    this.index = Math.max(0, Math.min(this.steps - 1, i));
    this.el.progress.value = this.index;
    this.el.status.textContent = `step ${fmt(this.index + 1)} / ${fmt(this.steps)}`;
    this.render(this.index);
  }

  play() {
    if (!this.steps) return;
    if (this.index >= this.steps - 1) this.go(0);
    this.playing = true;
    this.el.play.textContent = '⏸ إيقاف';
    let last = performance.now();
    let carry = 0;
    const tick = (now) => {
      if (!this.playing) return;
      const perSecond = 2 * 1.075 ** Number(this.el.speed.value);
      carry += ((now - last) / 1000) * perSecond;
      last = now;
      const advance = Math.floor(carry);
      if (advance > 0) {
        carry -= advance;
        this.go(this.index + advance);
      }
      if (this.index >= this.steps - 1) this.pause();
      else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  pause() {
    this.playing = false;
    this.el.play.textContent = '▶ تشغيل';
  }
}

const statsHtml = (rows) => rows.map(([k, v]) => `<span>${k}</span><b>${v}</b>`).join('');

/* ====================================================================== *
 * Sorting
 * ====================================================================== */
const sortState = { steps: [] };
$('#sort-algo').innerHTML = Object.entries(SORTING)
  .map(([id, a]) => `<option value="${id}" ${id === 'quick' ? 'selected' : ''}>${a.name}</option>`)
  .join('');

function renderSortComplexity() {
  const a = SORTING[$('#sort-algo').value];
  $('#sort-complexity').innerHTML = `<div class="stats">${statsHtml([
    ['أفضل حالة', a.complexity.best],
    ['متوسط', a.complexity.average],
    ['أسوأ حالة', a.complexity.worst],
    ['الذاكرة', a.complexity.space],
    ['مستقر (Stable)', a.stable ? 'نعم' : 'لا'],
  ])}</div>`;
}

const sortPlayer = new Player('sorting', (i) => {
  const step = sortState.steps[i];
  if (!step) return;
  const { ctx, w, h } = setupCanvas($('#sort-canvas'));
  const n = step.arr.length;
  const max = Math.max(...step.arr, 1);
  const gap = n > 60 ? 1 : 2;
  const bw = w / n;
  const sorted = new Set(step.sorted);
  const compare = new Set(step.compare ?? []);
  const swap = new Set(step.swap ?? []);
  step.arr.forEach((v, idx) => {
    const bh = (v / max) * (h - 24);
    ctx.fillStyle = swap.has(idx) ? css('--swap') : compare.has(idx) ? css('--compare') : sorted.has(idx) ? css('--sorted') : css('--bar');
    // draw left-to-right regardless of page direction (index 0 on the left)
    ctx.fillRect(idx * bw + gap / 2, h - bh, bw - gap, bh);
    if (n <= 30) {
      ctx.fillStyle = css('--muted');
      ctx.font = '11px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(v, idx * bw + bw / 2, h - bh - 4);
    }
  });
  $('#sort-stats').innerHTML = statsHtml([
    ['المقارنات', fmt(step.comparisons)],
    ['الكتابات', fmt(step.writes)],
    ['n', n],
  ]);
});

function runSorting() {
  const n = Math.max(5, Math.min(100, Number($('#sort-size').value) || 40));
  const arr = makeArray(n, $('#sort-input').value, Math.floor(Math.random() * 1e6));
  sortState.steps = runSort($('#sort-algo').value, arr).steps;
  renderSortComplexity();
  sortPlayer.load(sortState.steps.length);
}
$('#sort-generate').onclick = runSorting;
$('#sort-algo').onchange = runSorting;
$('#sort-input').onchange = runSorting;

/* ====================================================================== *
 * Path-finding
 * ====================================================================== */
const ROWS = 21;
const COLS = 51;
const grid = { rows: ROWS, cols: COLS, walls: new Set(), weights: new Set(), start: 0, end: 0 };
const pathState = { result: null };

function loadGrid(g) {
  grid.walls = new Set(g.walls);
  grid.weights = new Set(g.weights);
  grid.start = g.start;
  grid.end = g.end;
  pathState.result = null;
}
loadGrid(randomGrid(ROWS, COLS, { seed: 5 }));
$('#path-algo').innerHTML = Object.entries(PATHFINDING)
  .map(([id, a]) => `<option value="${id}" ${id === 'astar' ? 'selected' : ''}>${a.name}</option>`)
  .join('');

const gridInput = () => ({ ...grid, walls: [...grid.walls], weights: [...grid.weights] });

function drawGrid(i = -1) {
  const canvas = $('#path-canvas');
  const { ctx, w, h } = setupCanvas(canvas);
  const cs = Math.min(w / COLS, h / ROWS);
  const ox = (w - cs * COLS) / 2;
  grid.cell = { cs, ox };
  const res = pathState.result;
  const visitedUpTo = res ? Math.min(i + 1, res.visited.length) : 0;
  const pathUpTo = res ? Math.max(0, i + 1 - res.visited.length) : 0;
  const order = new Map();
  if (res) for (let k = 0; k < visitedUpTo; k++) order.set(res.visited[k], k);
  const onPath = new Set(res ? res.path.slice(0, pathUpTo) : []);
  for (let idx = 0; idx < ROWS * COLS; idx++) {
    const r = Math.floor(idx / COLS);
    const c = idx % COLS;
    let color = '#111827';
    if (grid.walls.has(idx)) color = css('--wall');
    else if (onPath.has(idx)) color = css('--path');
    else if (order.has(idx)) color = order.get(idx) === visitedUpTo - 1 ? '#7fb2ff' : css('--visited');
    if (grid.weights.has(idx) && !onPath.has(idx)) color = order.has(idx) ? '#a3622a' : css('--weight');
    if (idx === grid.start) color = css('--sorted');
    if (idx === grid.end) color = css('--swap');
    ctx.fillStyle = color;
    ctx.fillRect(ox + c * cs + 0.5, r * cs + 0.5, cs - 1, cs - 1);
  }
  if (res) {
    const done = i >= res.visited.length + res.path.length - 1;
    $('#path-stats').innerHTML = statsHtml([
      ['العقد المزارة', fmt(visitedUpTo)],
      ['طول المسار', done ? (res.found ? res.path.length : 'لا يوجد مسار') : '…'],
      ['تكلفة المسار', done && res.found ? res.stats.pathCost : '…'],
      ['تكلفة الازدحام', `${WEIGHT_COST}× لكل خلية برتقالية`],
    ]);
  }
}

const pathPlayer = new Player('pathfinding', (i) => drawGrid(i));

function runPath() {
  pathState.result = runPathfinding($('#path-algo').value, gridInput());
  pathPlayer.load(pathState.result.visited.length + pathState.result.path.length);
}

function comparePaths() {
  const rows = Object.entries(PATHFINDING).map(([id, a]) => ({ id, name: a.name, ...runPathfinding(id, gridInput()) }));
  const best = Math.min(...rows.filter((r) => r.found).map((r) => r.stats.pathCost));
  $('#path-compare-table').innerHTML = `<table><tr><th>الخوارزمية</th><th class="num">المزارة</th><th class="num">التكلفة</th></tr>${rows
    .map(
      (r) =>
        `<tr class="${r.found && r.stats.pathCost === best ? 'best' : ''}"><td>${r.name}</td><td class="num">${fmt(r.stats.visited)}</td><td class="num">${r.found ? r.stats.pathCost : '—'}</td></tr>`,
    )
    .join('')}</table>`;
}

let painting = false;
function paint(ev) {
  if (!grid.cell) return;
  const rect = $('#path-canvas').getBoundingClientRect();
  const c = Math.floor((ev.clientX - rect.left - grid.cell.ox) / grid.cell.cs);
  const r = Math.floor((ev.clientY - rect.top) / grid.cell.cs);
  if (r < 0 || r >= ROWS || c < 0 || c >= COLS) return;
  const idx = r * COLS + c;
  if (idx === grid.start || idx === grid.end) return;
  const tool = $('#path-tool').value;
  grid.walls.delete(idx);
  grid.weights.delete(idx);
  if (tool === 'wall') grid.walls.add(idx);
  if (tool === 'weight') grid.weights.add(idx);
  if (tool === 'start') grid.start = idx;
  if (tool === 'end') grid.end = idx;
  pathState.result = null;
  drawGrid();
}
$('#path-canvas').addEventListener('pointerdown', (e) => ((painting = true), paint(e)));
$('#path-canvas').addEventListener('pointermove', (e) => painting && paint(e));
window.addEventListener('pointerup', () => (painting = false));
$('#path-run').onclick = runPath;
$('#path-compare').onclick = comparePaths;
$('#path-random').onclick = () => (loadGrid(randomGrid(ROWS, COLS, { seed: Math.floor(Math.random() * 1e6) })), drawGrid(), comparePaths());
$('#path-clear').onclick = () => (loadGrid({ walls: [], weights: [], start: grid.start, end: grid.end }), drawGrid());
onShow.pathfinding = () => {
  drawGrid(pathPlayer.index);
  if (!pathState.result) {
    runPath();
    comparePaths();
  }
};

/* ====================================================================== *
 * CI/CD pipeline (topological sort + critical path)
 * ====================================================================== */
const pipeState = { result: null, dag: null };
const BOX_W = 108;
const BOX_H = 44;

function pipelineLayout(dag, result) {
  const cols = [...result.levels];
  if (result.blocked.length) cols.push(result.blocked);
  const pos = new Map();
  const colGap = 128;
  const width = cols.length * colGap + 20;
  cols.forEach((col, ci) => {
    const total = col.length * 70;
    col.forEach((id, ri) => pos.set(id, { x: 20 + ci * colGap, y: 210 - total / 2 + ri * 70 + 13 }));
  });
  return { pos, width };
}

function renderPipeline(i) {
  const { result, dag } = pipeState;
  if (!result) return;
  const { pos, width } = pipelineLayout(dag, result);
  const final = i >= result.steps.length;
  const step = final ? null : result.steps[i];
  const done = new Set(final ? result.order : step.done.slice(0, -1));
  const ready = new Set(step ? step.ready : []);
  const critical = new Set(final ? result.criticalPath : []);
  const blocked = new Set(result.blocked);
  const byId = new Map(dag.nodes.map((n) => [n.id, n]));
  const edgeOnCritical = (a, b) => {
    const k = result.criticalPath.indexOf(a);
    return final && k !== -1 && result.criticalPath[k + 1] === b;
  };
  let svg = `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#5d6a8f"/></marker></defs>`;
  for (const [a, b] of dag.edges) {
    const p = pos.get(a);
    const q = pos.get(b);
    const back = q.x <= p.x;
    const x1 = p.x + BOX_W;
    const y1 = p.y + BOX_H / 2;
    const x2 = back ? q.x + BOX_W / 2 : q.x;
    const y2 = back ? q.y : q.y + BOX_H / 2;
    const color = edgeOnCritical(a, b) ? css('--swap') : back ? css('--swap') : '#5d6a8f';
    const d = back
      ? `M${x1},${y1} C${x1 + 60},${y1 - 160} ${x2},${y2 - 160} ${x2},${y2}`
      : `M${x1},${y1} C${x1 + 30},${y1} ${x2 - 30},${y2} ${x2},${y2}`;
    svg += `<path d="${d}" fill="none" stroke="${color}" stroke-width="${color === '#5d6a8f' ? 1.5 : 2.5}" ${back ? 'stroke-dasharray="6 4"' : ''} marker-end="url(#arrow)"/>`;
  }
  for (const n of dag.nodes) {
    const p = pos.get(n.id);
    let fill = '#222b42';
    if (blocked.has(n.id)) fill = css('--swap');
    else if (critical.has(n.id)) fill = css('--swap');
    else if (step && step.current === n.id) fill = css('--compare');
    else if (done.has(n.id)) fill = css('--sorted');
    else if (ready.has(n.id)) fill = css('--ready');
    const dark = fill !== '#222b42';
    const sched = result.schedule?.find((s) => s.id === n.id);
    svg += `<g><rect x="${p.x}" y="${p.y}" width="${BOX_W}" height="${BOX_H}" rx="8" fill="${fill}" stroke="#3a4566"/>
      <text x="${p.x + BOX_W / 2}" y="${p.y + 18}" text-anchor="middle" font-size="12" fill="${dark ? '#111' : '#e6e9f2'}" font-weight="600">${n.label}</text>
      <text x="${p.x + BOX_W / 2}" y="${p.y + 34}" text-anchor="middle" font-size="10" fill="${dark ? '#222' : '#8d97b5'}">${n.duration}m${final && sched ? ` · t=${sched.start}→${sched.finish}` : ''}</text></g>`;
  }
  result.levels.forEach((_, li) => {
    svg += `<text x="${20 + li * 128 + BOX_W / 2}" y="16" text-anchor="middle" font-size="11" fill="#8d97b5">Level ${li}</text>`;
  });
  const el = $('#pipe-svg');
  el.setAttribute('viewBox', `0 0 ${Math.max(width, 600)} 420`);
  el.innerHTML = svg;
}

const pipePlayer = new Player('pipeline', renderPipeline);

async function runPipeline() {
  const dag = structuredClone(CI_PIPELINE);
  if ($('#pipe-cycle').checked) dag.edges.push(['prod', 'install']);
  const { data, source } = await api('/api/pipeline', { method: 'POST', body: dag }, () => schedulePipeline(dag));
  pipeState.dag = dag;
  pipeState.result = data;
  $('#pipe-stats').innerHTML = statsHtml(
    data.hasCycle
      ? [
          ['الحالة', '❌ يوجد دورة. الخط غير قابل للتنفيذ'],
          ['مهام عالقة', data.blocked.join(', ')],
          ['المصدر', source],
        ]
      : [
          ['ترتيب التنفيذ', `${data.order.length} مهمة`],
          ['مستويات متوازية', data.levels.length],
          ['زمن تسلسلي', `${data.sequentialTime} دقيقة`],
          ['زمن مع التوازي', `${data.makespan} دقيقة`],
          ['تسريع', `${(data.sequentialTime / data.makespan).toFixed(2)}×`],
          ['المسار الحرج', data.criticalPath.join(' → ')],
          ['المصدر', source],
        ],
  );
  pipePlayer.load(data.steps.length + 1);
}
$('#pipe-run').onclick = runPipeline;
$('#pipe-cycle').onchange = runPipeline;
onShow.pipeline = () => (pipeState.result ? renderPipeline(pipePlayer.index) : runPipeline());

/* ====================================================================== *
 * Load balancing
 * ====================================================================== */
const lbState = { sim: null, servers: [] };
$('#lb-strategy').innerHTML = Object.entries(LB_STRATEGIES)
  .map(([id, name]) => `<option value="${id}" ${id === 'least-connections' ? 'selected' : ''}>${name}</option>`)
  .join('');

function parseServers() {
  const caps = $('#lb-servers').value.split(',').map((s) => Number(s.trim())).filter((x) => x > 0).slice(0, 10);
  return (caps.length ? caps : [1, 2]).map((capacity, i) => ({ id: `srv-${i + 1}`, capacity }));
}

const lbPlayer = new Player('lb', (i) => {
  const { sim, servers } = lbState;
  if (!sim) return;
  const step = sim.steps[i];
  const handled = new Array(servers.length).fill(0);
  for (let k = 0; k <= i; k++) handled[sim.steps[k].server]++;
  const { ctx, w, h } = setupCanvas($('#lb-canvas'));
  const maxActive = Math.max(...sim.stats.peak, 1);
  const rowH = Math.min(56, (h - 40) / servers.length);
  const left = 90;
  const barW = w - left - 140;
  ctx.font = '13px sans-serif';
  servers.forEach((s, k) => {
    const y = 30 + k * rowH;
    ctx.fillStyle = k === step.server ? css('--compare') : css('--text');
    ctx.textAlign = 'left';
    ctx.fillText(`${s.id} (×${s.capacity})`, 6, y + rowH / 2);
    ctx.fillStyle = '#0b0f18';
    ctx.fillRect(left, y + 6, barW, rowH - 16);
    const active = step.active[k];
    ctx.fillStyle = active > s.capacity ? css('--swap') : css('--sorted');
    ctx.fillRect(left, y + 6, (active / maxActive) * barW, rowH - 16);
    const capX = left + (s.capacity / maxActive) * barW;
    ctx.strokeStyle = css('--compare');
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(capX, y + 2);
    ctx.lineTo(capX, y + rowH - 6);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = css('--muted');
    ctx.fillText(`active ${active} · total ${handled[k]}`, left + barW + 8, y + rowH / 2);
  });
  ctx.fillStyle = css('--muted');
  ctx.fillText(
    `t=${step.time}  request #${step.request} → ${servers[step.server].id}  latency=${step.latency.toFixed(1)}   (dashed line = capacity, red = overloaded)`,
    6,
    16,
  );
});

async function runLb() {
  const servers = parseServers();
  const count = Math.max(20, Math.min(2000, Number($('#lb-count').value) || 300));
  const requests = generateRequests(count);
  lbState.servers = servers;
  lbState.sim = simulateLoadBalancer({ servers, requests, strategy: $('#lb-strategy').value });
  lbPlayer.load(lbState.sim.steps.length);

  const rows = await Promise.all(
    Object.keys(LB_STRATEGIES).map(async (strategy) => {
      const { data, source } = await api(
        '/api/loadbalance',
        { method: 'POST', body: { servers, strategy, requestCount: count } },
        () => simulateLoadBalancer({ servers, requests, strategy }),
      );
      return { strategy, stats: data.stats, source };
    }),
  );
  const best = Math.min(...rows.map((r) => r.stats.p99Latency));
  $('#lb-table').innerHTML = `<table><tr><th>الاستراتيجية</th><th class="num">avg</th><th class="num">p95</th><th class="num">p99</th><th class="num">الطلبات لكل خادم</th><th class="num">الذروة لكل خادم</th></tr>${rows
    .map(
      ({ strategy, stats }) =>
        `<tr class="${stats.p99Latency === best ? 'best' : ''}"><td>${LB_STRATEGIES[strategy]}</td><td class="num">${stats.avgLatency}</td><td class="num">${stats.p95Latency}</td><td class="num">${stats.p99Latency}</td><td class="num">${stats.handled.join(' / ')}</td><td class="num">${stats.peak.join(' / ')}</td></tr>`,
    )
    .join('')}</table><p style="color:var(--muted);font-size:12px;margin-top:6px">المصدر: ${rows[0].source}</p>`;
}
$('#lb-run').onclick = runLb;
$('#lb-strategy').onchange = runLb;
onShow.lb = () => (lbState.sim ? lbPlayer.go(lbPlayer.index) : runLb());

/* ====================================================================== *
 * Consistent hashing
 * ====================================================================== */
const hashState = { nodes: ['node-A', 'node-B', 'node-C'], next: 3, last: null };
const nodeColor = (name) => PALETTE[(name.charCodeAt(5) - 65) % PALETTE.length];
const angle = (h) => (h / 2 ** 32) * Math.PI * 2 - Math.PI / 2;

function renderHashing() {
  const vnodes = Math.max(1, Math.min(200, Number($('#hash-vnodes').value) || 20));
  const keyCount = Math.max(10, Math.min(5000, Number($('#hash-keys').value) || 400));
  const ring = new HashRing(hashState.nodes, vnodes);
  const R = 200;
  let svg = `<circle r="${R}" fill="none" stroke="#3a4566" stroke-width="2"/>`;
  const counts = Object.fromEntries(hashState.nodes.map((n) => [n, 0]));
  for (let k = 0; k < keyCount; k++) {
    const key = `key-${k}`;
    const owner = ring.getNode(key);
    counts[owner]++;
    const a = angle(hash32(key));
    svg += `<circle cx="${(R - 22) * Math.cos(a)}" cy="${(R - 22) * Math.sin(a)}" r="2.2" fill="${nodeColor(owner)}" opacity=".8"/>`;
  }
  for (const p of ring.ring) {
    const a = angle(p.hash);
    svg += `<line x1="${(R - 8) * Math.cos(a)}" y1="${(R - 8) * Math.sin(a)}" x2="${(R + 12) * Math.cos(a)}" y2="${(R + 12) * Math.sin(a)}" stroke="${nodeColor(p.node)}" stroke-width="3"/>`;
  }
  svg += `<text text-anchor="middle" y="-6" fill="#e6e9f2" font-size="16">${hashState.nodes.length} servers</text>
    <text text-anchor="middle" y="16" fill="#8d97b5" font-size="12">${vnodes} vnodes each · ${keyCount} keys</text>`;
  $('#hash-svg').innerHTML = svg;
  const ideal = keyCount / hashState.nodes.length;
  $('#hash-dist').innerHTML = hashState.nodes
    .map(
      (n) => `<div class="bar-row"><span style="color:${nodeColor(n)}">${n}</span>
      <div class="track"><div class="fill" style="width:${Math.min(100, (counts[n] / (ideal * 2)) * 100)}%;background:${nodeColor(n)}"></div></div>
      <b>${counts[n]}</b></div>`,
    )
    .join('') + `<p style="color:var(--muted);font-size:12px">المثالي ≈ ${ideal.toFixed(0)} لكل خادم. زِد عدد الـ vnodes لترى التوزيع يتحسن.</p>`;
  const l = hashState.last;
  $('#hash-stats').innerHTML = l
    ? statsHtml([
        ['التغيير', l.label],
        ['Consistent hashing', `${l.consistent.percent}% من المفاتيح انتقلت`],
        ['hash % N', `${l.modulo.percent}% من المفاتيح انتقلت`],
        ['النسبة المثالية', `${l.ideal}%`],
      ])
    : '<span>أضف أو احذف خادماً لترى كم مفتاحاً سينتقل</span><b></b>';
}

function changeCluster(after, label) {
  if (after.length < 1) return;
  const vnodes = Number($('#hash-vnodes').value) || 20;
  const keys = Number($('#hash-keys').value) || 400;
  const res = compareRebalancing(hashState.nodes, after, keys, vnodes);
  const ideal = ((1 / Math.max(after.length, hashState.nodes.length)) * 100).toFixed(1);
  hashState.last = { ...res, label, ideal };
  hashState.nodes = after;
  renderHashing();
}
$('#hash-add').onclick = () => {
  if (hashState.nodes.length >= PALETTE.length) return;
  const name = `node-${String.fromCharCode(65 + (hashState.next++ % 26))}`;
  changeCluster([...hashState.nodes, name], `إضافة ${name}`);
};
$('#hash-remove').onclick = () => {
  const victim = hashState.nodes[hashState.nodes.length - 1];
  if (hashState.nodes.length > 1) changeCluster(hashState.nodes.slice(0, -1), `حذف ${victim}`);
};
$('#hash-reset').onclick = () => {
  Object.assign(hashState, { nodes: ['node-A', 'node-B', 'node-C'], next: 3, last: null });
  renderHashing();
};
$('#hash-vnodes').onchange = renderHashing;
$('#hash-keys').onchange = renderHashing;
onShow.hashing = renderHashing;

/* ====================================================================== *
 * Line chart (used by autoscaling + benchmark)
 * ====================================================================== */
function lineChart(canvas, { series, logX = false, logY = false, xLabel = '', yLabel = '', step = false }) {
  const { ctx, w, h } = setupCanvas(canvas);
  const pad = { l: 70, r: 20, t: 20, b: 44 };
  const pts = series.flatMap((s) => s.points);
  if (!pts.length) return;
  const tx = (x) => (logX ? Math.log10(x) : x);
  const ty = (y) => (logY ? Math.log10(Math.max(y, 1e-3)) : y);
  const xs = pts.map((p) => tx(p[0]));
  const ys = pts.map((p) => ty(p[1]));
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [logY ? Math.min(...ys) : 0, Math.max(...ys)];
  const X = (x) => pad.l + ((tx(x) - x0) / (x1 - x0 || 1)) * (w - pad.l - pad.r);
  const Y = (y) => h - pad.b - ((ty(y) - y0) / (y1 - y0 || 1)) * (h - pad.t - pad.b);

  ctx.strokeStyle = '#2a3450';
  ctx.fillStyle = css('--muted');
  ctx.font = '11px sans-serif';
  ctx.lineWidth = 1;
  for (let k = 0; k <= 5; k++) {
    const v = y0 + ((y1 - y0) * k) / 5;
    const yy = h - pad.b - ((v - y0) / (y1 - y0 || 1)) * (h - pad.t - pad.b);
    ctx.beginPath();
    ctx.moveTo(pad.l, yy);
    ctx.lineTo(w - pad.r, yy);
    ctx.stroke();
    const label = logY ? 10 ** v : v;
    ctx.textAlign = 'right';
    ctx.fillText(label >= 1000 ? `${(label / 1000).toFixed(label >= 1e4 ? 0 : 1)}k` : +label.toFixed(1), pad.l - 6, yy + 4);
  }
  const xTicks = [...new Set(series[0].points.map((p) => p[0]))];
  const every = Math.ceil(xTicks.length / 12);
  ctx.textAlign = 'center';
  xTicks.forEach((x, k) => k % every === 0 && ctx.fillText(x, X(x), h - pad.b + 16));
  ctx.fillText(xLabel, (pad.l + w - pad.r) / 2, h - 6);
  ctx.save();
  ctx.translate(14, (pad.t + h - pad.b) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(yLabel, 0, 0);
  ctx.restore();

  let legendX = pad.l + 8;
  for (const s of series) {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = s.dashed ? 1.5 : 2.5;
    ctx.setLineDash(s.dashed ? [6, 5] : []);
    ctx.beginPath();
    s.points.forEach(([x, y], k) => {
      if (k === 0) ctx.moveTo(X(x), Y(y));
      else if (step || s.step) {
        ctx.lineTo(X(x), Y(s.points[k - 1][1]));
        ctx.lineTo(X(x), Y(y));
      } else ctx.lineTo(X(x), Y(y));
    });
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = s.color;
    ctx.fillRect(legendX, pad.t, 12, 4);
    ctx.textAlign = 'left';
    ctx.fillText(s.name, legendX + 16, pad.t + 6);
    legendX += ctx.measureText(s.name).width + 36;
  }
}

/* ====================================================================== *
 * Autoscaling (Kubernetes HPA)
 * ====================================================================== */
function loadPattern(kind) {
  return Array.from({ length: 60 }, (_, t) => {
    if (kind === 'spike') return t < 15 ? 80 : t < 30 ? 520 : t < 45 ? 260 : 90;
    if (kind === 'ramp') return 40 + t * 9;
    return Math.round(260 + 220 * Math.sin((t / 60) * Math.PI * 2 - Math.PI / 2) + (t % 7) * 6);
  });
}

function runAutoscale() {
  const target = Number($('#hpa-target').value) || 50;
  const min = Number($('#hpa-min').value) || 1;
  const max = Math.max(min, Number($('#hpa-max').value) || 10);
  const timeline = simulateAutoscaling({ load: loadPattern($('#hpa-pattern').value), targetPerPod: target, min, max });
  lineChart($('#hpa-canvas'), {
    xLabel: 'time (ticks)',
    yLabel: 'requests / second',
    series: [
      { name: 'incoming load (rps)', color: css('--compare'), points: timeline.map((r) => [r.t, r.rps]) },
      { name: 'capacity = replicas × target', color: css('--sorted'), step: true, points: timeline.map((r) => [r.t, r.replicas * target]) },
    ],
  });
  const overloaded = timeline.filter((r) => r.rps > r.replicas * target).length;
  const util = timeline.reduce((s, r) => s + r.rps / (r.replicas * target), 0) / timeline.length;
  $('#hpa-stats').innerHTML = statsHtml([
    ['أعلى عدد Pods', Math.max(...timeline.map((r) => r.replicas))],
    ['لحظات تجاوز السعة', `${overloaded} / ${timeline.length}`],
    ['متوسط الاستغلال', `${(util * 100).toFixed(0)}%`],
    ['Pod-ticks (التكلفة)', fmt(timeline.reduce((s, r) => s + r.replicas, 0))],
  ]);
}
['#hpa-run'].forEach((s) => ($(s).onclick = runAutoscale));
['#hpa-pattern', '#hpa-target', '#hpa-min', '#hpa-max'].forEach((s) => ($(s).onchange = runAutoscale));
onShow.autoscale = runAutoscale;

/* ====================================================================== *
 * Benchmark (server-side)
 * ====================================================================== */
const DEFAULT_BENCH = ['bubble', 'insertion', 'merge', 'quick', 'heap'];
$('#bench-algos').innerHTML = Object.entries(SORTING)
  .map(([id, a]) => `<label><input type="checkbox" value="${id}" ${DEFAULT_BENCH.includes(id) ? 'checked' : ''}/> ${a.name}</label>`)
  .join('');
const benchState = { rows: null };

function drawBench() {
  if (!benchState.rows) return;
  const metric = $('#bench-metric').value;
  const series = benchState.rows.map((r, k) => ({
    name: SORTING[r.algorithm].name,
    color: PALETTE[Object.keys(SORTING).indexOf(r.algorithm) % PALETTE.length],
    points: r.results.map((p) => [p.n, p[metric]]),
  }));
  if (metric !== 'ms') {
    const ns = benchState.rows[0].results.map((p) => p.n);
    series.push({ name: 'n²/2', color: '#8d97b5', dashed: true, points: ns.map((n) => [n, (n * n) / 2]) });
    series.push({ name: 'n·log₂n', color: '#c0c7da', dashed: true, points: ns.map((n) => [n, n * Math.log2(n)]) });
  }
  lineChart($('#bench-canvas'), {
    series,
    logX: true,
    logY: $('#bench-log').checked,
    xLabel: 'n (input size, log scale)',
    yLabel: { comparisons: 'comparisons', writes: 'writes', ms: 'milliseconds' }[metric],
  });
}

async function runBench() {
  const algos = [...document.querySelectorAll('#bench-algos input:checked')].map((i) => i.value);
  if (!algos.length) return;
  const input = $('#bench-input').value;
  $('#bench-run').disabled = true;
  try {
    const out = await Promise.all(
      algos.map((algorithm) =>
        api(`/api/benchmark?algorithm=${algorithm}&input=${input}`, {}, () => ({
          algorithm,
          instance: 'browser',
          results: benchmarkSort(algorithm, { input }),
        })),
      ),
    );
    benchState.rows = out.map((o) => o.data);
    const instances = [...new Set(out.map((o) => o.data.instance))];
    $('#bench-source').innerHTML = statsHtml([
      ['نُفّذ على', instances.join(', ')],
      ['عدد الطلبات', algos.length],
      ['المدخلات', input],
    ]);
    drawBench();
  } finally {
    $('#bench-run').disabled = false;
  }
}
$('#bench-run').onclick = runBench;
$('#bench-input').onchange = runBench;
$('#bench-metric').onchange = drawBench;
$('#bench-log').onchange = drawBench;
onShow.benchmark = () => (benchState.rows ? drawBench() : runBench());

/* ---------------- boot ---------------- */
runSorting();
window.addEventListener('resize', () => {
  sortPlayer.go(sortPlayer.index);
  const active = document.querySelector('.tab.active').dataset.tab;
  if (active !== 'sorting') onShow[active]?.();
});
