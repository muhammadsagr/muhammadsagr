// Grid path-finding: BFS, DFS, Dijkstra, A*.
// A grid is { rows, cols, walls: number[], weights: number[], start, end } where
// cells are addressed by index = row * cols + col. "Weight" cells cost WEIGHT_COST
// to enter (think: a congested network link), every other cell costs 1.
import { MinHeap } from './heap.js';
import { createRng } from './random.js';

export const WEIGHT_COST = 5;

function prepare(grid) {
  const { rows, cols, start, end } = grid;
  const size = rows * cols;
  if (!Number.isInteger(rows) || !Number.isInteger(cols) || rows < 2 || cols < 2 || size > 10000) {
    throw new Error('Grid must be between 2x2 and 10000 cells');
  }
  for (const i of [start, end]) {
    if (!Number.isInteger(i) || i < 0 || i >= size) throw new Error('start/end out of range');
  }
  const wall = new Uint8Array(size);
  const weight = new Uint8Array(size);
  for (const i of grid.walls ?? []) if (i >= 0 && i < size) wall[i] = 1;
  for (const i of grid.weights ?? []) if (i >= 0 && i < size) weight[i] = 1;
  wall[start] = 0;
  wall[end] = 0;
  return { rows, cols, start, end, size, wall, weight };
}

function neighbors(g, i) {
  const r = Math.floor(i / g.cols);
  const c = i % g.cols;
  const out = [];
  if (r > 0) out.push(i - g.cols);
  if (c < g.cols - 1) out.push(i + 1);
  if (r < g.rows - 1) out.push(i + g.cols);
  if (c > 0) out.push(i - 1);
  return out.filter((j) => !g.wall[j]);
}

const cost = (g, j) => (g.weight[j] ? WEIGHT_COST : 1);

function manhattan(g, i) {
  const dr = Math.abs(Math.floor(i / g.cols) - Math.floor(g.end / g.cols));
  const dc = Math.abs((i % g.cols) - (g.end % g.cols));
  return dr + dc;
}

function buildResult(g, visited, prev) {
  const path = [];
  if (g.start === g.end || prev[g.end] !== -1) {
    for (let at = g.end; at !== -1; at = prev[at]) path.push(at);
    path.reverse();
  }
  const pathCost = path.slice(1).reduce((sum, i) => sum + cost(g, i), 0);
  return {
    visited,
    path,
    found: path.length > 0,
    stats: { visited: visited.length, pathLength: path.length, pathCost },
  };
}

function bfs(g) {
  const prev = new Int32Array(g.size).fill(-1);
  const seen = new Uint8Array(g.size);
  const visited = [];
  const queue = [g.start];
  seen[g.start] = 1;
  for (let head = 0; head < queue.length; head++) {
    const u = queue[head];
    visited.push(u);
    if (u === g.end) break;
    for (const v of neighbors(g, u)) {
      if (!seen[v]) {
        seen[v] = 1;
        prev[v] = u;
        queue.push(v);
      }
    }
  }
  return buildResult(g, visited, prev);
}

function dfs(g) {
  const prev = new Int32Array(g.size).fill(-1);
  const seen = new Uint8Array(g.size);
  const visited = [];
  const stack = [g.start];
  while (stack.length) {
    const u = stack.pop();
    if (seen[u]) continue;
    seen[u] = 1;
    visited.push(u);
    if (u === g.end) break;
    for (const v of neighbors(g, u).reverse()) {
      if (!seen[v]) {
        prev[v] = u;
        stack.push(v);
      }
    }
  }
  return buildResult(g, visited, prev);
}

// Dijkstra = best-first search ordered by g(n). A* adds an admissible heuristic h(n).
function bestFirst(g, heuristic) {
  const dist = new Float64Array(g.size).fill(Infinity);
  const prev = new Int32Array(g.size).fill(-1);
  const closed = new Uint8Array(g.size);
  const visited = [];
  const heap = new MinHeap((e) => e.f);
  dist[g.start] = 0;
  heap.push({ node: g.start, f: heuristic(g, g.start) });
  while (heap.size) {
    const { node: u } = heap.pop();
    if (closed[u]) continue;
    closed[u] = 1;
    visited.push(u);
    if (u === g.end) break;
    for (const v of neighbors(g, u)) {
      const alt = dist[u] + cost(g, v);
      if (alt < dist[v]) {
        dist[v] = alt;
        prev[v] = u;
        heap.push({ node: v, f: alt + heuristic(g, v) });
      }
    }
  }
  return buildResult(g, visited, prev);
}

export const PATHFINDING = {
  bfs: {
    name: 'Breadth-First Search',
    complexity: { time: 'O(V + E)', space: 'O(V)' },
    weighted: false,
    optimal: 'Only on unweighted graphs',
    run: bfs,
  },
  dfs: {
    name: 'Depth-First Search',
    complexity: { time: 'O(V + E)', space: 'O(V)' },
    weighted: false,
    optimal: 'No',
    run: dfs,
  },
  dijkstra: {
    name: "Dijkstra's Algorithm",
    complexity: { time: 'O((V + E) log V)', space: 'O(V)' },
    weighted: true,
    optimal: 'Yes',
    run: (g) => bestFirst(g, () => 0),
  },
  astar: {
    name: 'A* Search (Manhattan)',
    complexity: { time: 'O((V + E) log V)', space: 'O(V)' },
    weighted: true,
    optimal: 'Yes (admissible heuristic)',
    run: (g) => bestFirst(g, manhattan),
  },
};

export function runPathfinding(id, grid) {
  const algo = PATHFINDING[id];
  if (!algo) throw new Error(`Unknown path-finding algorithm: ${id}`);
  return algo.run(prepare(grid));
}

export function randomGrid(rows, cols, { wallDensity = 0.25, weightDensity = 0.1, seed = 7 } = {}) {
  const rng = createRng(seed);
  const start = Math.floor(rows / 2) * cols + 2;
  const end = Math.floor(rows / 2) * cols + cols - 3;
  const walls = [];
  const weights = [];
  for (let i = 0; i < rows * cols; i++) {
    if (i === start || i === end) continue;
    const x = rng();
    if (x < wallDensity) walls.push(i);
    else if (x < wallDensity + weightDensity) weights.push(i);
  }
  return { rows, cols, start, end, walls, weights };
}
