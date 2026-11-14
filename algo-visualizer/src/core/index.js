export * from './random.js';
export * from './heap.js';
export * from './sorting.js';
export * from './pathfinding.js';
export * from './cloud.js';
export * from './benchmark.js';

import { SORTING } from './sorting.js';
import { PATHFINDING } from './pathfinding.js';
import { LB_STRATEGIES } from './cloud.js';

const describe = (table) =>
  Object.entries(table).map(([id, { run, ...meta }]) => ({ id, ...meta }));

export function catalog() {
  return {
    sorting: describe(SORTING),
    pathfinding: describe(PATHFINDING),
    cloud: {
      pipeline: { name: 'Topological Sort (Kahn) + Critical Path', complexity: 'O(V + E)' },
      loadBalancing: Object.entries(LB_STRATEGIES).map(([id, name]) => ({ id, name })),
      consistentHashing: { name: 'Consistent Hashing ring', lookup: 'O(log(N·V))' },
      rateLimiting: { name: 'Token Bucket', complexity: 'O(1)' },
      autoscaling: { name: 'Kubernetes HPA formula', complexity: 'O(1)' },
    },
  };
}
