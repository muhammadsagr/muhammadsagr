import test from 'node:test';
import assert from 'node:assert/strict';
import { runPathfinding, randomGrid, PATHFINDING } from '../src/core/index.js';

const open = { rows: 5, cols: 5, walls: [], weights: [], start: 0, end: 24 };

test('all algorithms find a path on an open grid', () => {
  for (const id of Object.keys(PATHFINDING)) {
    const r = runPathfinding(id, open);
    assert.ok(r.found, id);
    assert.equal(r.path[0], 0);
    assert.equal(r.path.at(-1), 24);
  }
});

test('BFS, Dijkstra and A* give shortest path on unweighted grid', () => {
  for (const id of ['bfs', 'dijkstra', 'astar']) assert.equal(runPathfinding(id, open).stats.pathCost, 8, id);
});

test('Dijkstra and A* agree on optimal cost on many weighted random grids; BFS never beats them', () => {
  for (let seed = 1; seed <= 40; seed++) {
    const g = randomGrid(15, 25, { seed, wallDensity: 0.22, weightDensity: 0.2 });
    const d = runPathfinding('dijkstra', g);
    const a = runPathfinding('astar', g);
    const b = runPathfinding('bfs', g);
    assert.equal(d.found, a.found);
    if (d.found) {
      assert.equal(a.stats.pathCost, d.stats.pathCost, `seed ${seed}`);
      assert.ok(b.stats.pathCost >= d.stats.pathCost);
      assert.ok(a.stats.visited <= d.stats.visited, 'A* explores no more than Dijkstra');
    }
  }
});

test('path is contiguous and avoids walls', () => {
  const g = randomGrid(15, 25, { seed: 9 });
  const { path } = runPathfinding('astar', g);
  const walls = new Set(g.walls);
  for (let i = 1; i < path.length; i++) {
    const d = Math.abs(path[i] - path[i - 1]);
    assert.ok(d === 1 || d === g.cols);
    assert.ok(!walls.has(path[i]));
  }
});

test('unreachable target reports found=false', () => {
  const g = { rows: 3, cols: 3, walls: [1, 4, 7], weights: [], start: 0, end: 2 };
  for (const id of Object.keys(PATHFINDING)) assert.equal(runPathfinding(id, g).found, false);
});

test('invalid grid is rejected', () => {
  assert.throws(() => runPathfinding('bfs', { rows: 1, cols: 1, start: 0, end: 0 }));
  assert.throws(() => runPathfinding('bfs', { ...open, end: 99 }));
});
