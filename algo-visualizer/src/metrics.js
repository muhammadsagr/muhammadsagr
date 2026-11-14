// Minimal Prometheus exposition-format metrics (no external dependencies).
const BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5];

const labelKey = (labels) =>
  Object.entries(labels)
    .map(([k, v]) => `${k}="${String(v).replace(/["\\\n]/g, '_')}"`)
    .join(',');

export class Registry {
  constructor() {
    this.counters = new Map(); // name -> { help, values: Map(labelKey -> n) }
    this.histograms = new Map(); // name -> { help, series: Map(labelKey -> {buckets, sum, count}) }
    this.gauges = new Map(); // name -> { help, fn }
  }

  counter(name, help) {
    if (!this.counters.has(name)) this.counters.set(name, { help, values: new Map() });
    const c = this.counters.get(name);
    return {
      inc: (labels = {}, by = 1) => {
        const k = labelKey(labels);
        c.values.set(k, (c.values.get(k) ?? 0) + by);
      },
    };
  }

  histogram(name, help) {
    if (!this.histograms.has(name)) this.histograms.set(name, { help, series: new Map() });
    const h = this.histograms.get(name);
    return {
      observe: (labels, value) => {
        const k = labelKey(labels);
        if (!h.series.has(k)) h.series.set(k, { buckets: new Array(BUCKETS.length).fill(0), sum: 0, count: 0 });
        const s = h.series.get(k);
        BUCKETS.forEach((b, i) => {
          if (value <= b) s.buckets[i]++;
        });
        s.sum += value;
        s.count++;
      },
    };
  }

  gauge(name, help, fn) {
    this.gauges.set(name, { help, fn });
  }

  render() {
    const out = [];
    for (const [name, { help, values }] of this.counters) {
      out.push(`# HELP ${name} ${help}`, `# TYPE ${name} counter`);
      for (const [k, v] of values) out.push(`${name}${k ? `{${k}}` : ''} ${v}`);
    }
    for (const [name, { help, series }] of this.histograms) {
      out.push(`# HELP ${name} ${help}`, `# TYPE ${name} histogram`);
      for (const [k, s] of series) {
        const sep = k ? ',' : '';
        BUCKETS.forEach((b, i) => out.push(`${name}_bucket{${k}${sep}le="${b}"} ${s.buckets[i]}`));
        out.push(`${name}_bucket{${k}${sep}le="+Inf"} ${s.count}`);
        out.push(`${name}_sum${k ? `{${k}}` : ''} ${s.sum}`);
        out.push(`${name}_count${k ? `{${k}}` : ''} ${s.count}`);
      }
    }
    for (const [name, { help, fn }] of this.gauges) {
      out.push(`# HELP ${name} ${help}`, `# TYPE ${name} gauge`, `${name} ${fn()}`);
    }
    return out.join('\n') + '\n';
  }
}
