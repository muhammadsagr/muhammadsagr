/* الاحتيال المالي: نقل مباشر لـ mizan/fraudsim/ledger.py و detection.py.
   سجل معاملات مُولَّد بأنماط FATF مُعلَّمة، ثم أدوات كشف تُقيَّم مقابل الإجابة الصحيحة. */
(function () {
  "use strict";
  const { rng } = window.M;

  const CASH = "CASH";
  const TYPOLOGIES = { structuring: "تجزئة الإيداعات", round_trip: "تدوير الأموال", fake_invoice: "فواتير وهمية", mule: "حسابات وسيطة" };
  const DEFAULT = { people: 600, businesses: 150, days: 180, threshold: 10000, schemes: 15, camouflage: 0 };
  const round2 = (x) => Math.round(x * 100) / 100;

  // ---------------------------------------------------------------- السجل
  function ledger(cfg, seed = 0) {
    const g = rng("ledger", seed);
    const people = Array.from({ length: cfg.people }, (_, i) => "P" + String(i).padStart(4, "0"));
    const biz = Array.from({ length: cfg.businesses }, (_, i) => "B" + String(i).padStart(3, "0"));
    const all = people.concat(biz);
    const tx = [];
    const add = (day, src, dst, amount, kind, typology = null, scheme = null) => {
      if (src !== dst) tx.push({ day, src, dst, amount, kind, typology, scheme });
    };

    // معاملات سليمة: رواتب شهرية، ومشتريات، ومدفوعات بين الشركات، وتحويلات بين الأفراد، وإيداعات نقدية
    const employer = people.map(() => g.choice(biz));
    const salary = people.map(() => round2(g.lognormal(Math.log(9000), 0.45)));
    for (let day = 0; day < cfg.days; day += 30) people.forEach((p, i) => add(day, employer[i], p, salary[i], "salary"));
    const n = Math.floor((cfg.days * (people.length + biz.length)) / 3);
    const kinds = ["purchase", "b2b", "p2p", "deposit"], kp = [0.6, 0.15, 0.15, 0.1];
    const size = { purchase: [5.0, 1.1], b2b: [8.5, 1.2], p2p: [6.0, 1.0], deposit: [7.0, 1.0] };
    for (let i = 0; i < n; i++) {
      const k = kinds[g.weighted(kp)], day = g.int(0, cfg.days), amt = round2(g.lognormal(...size[k]));
      if (k === "purchase") add(day, g.choice(people), g.choice(biz), amt, k);
      else if (k === "b2b") add(day, g.choice(biz), g.choice(biz), amt, k);
      else if (k === "p2p") add(day, g.choice(people), g.choice(people), amt, k);
      else add(day, CASH, g.choice(all), amt, k);
    }

    const c = cfg.camouflage;
    for (let sid = 0; sid < cfg.schemes; sid++) {           // تجزئة الإيداعات تحت حد الإبلاغ
      const acct = g.choice(all), total = g.uniform(40000, 150000);
      const span = Math.floor(20 + 100 * c), start = g.int(0, Math.max(cfg.days - span, 1));
      for (let sent = 0; sent < total;) {
        const amt = round2(cfg.threshold * g.uniform(0.85 - 0.45 * c, 0.995));
        add(start + g.int(0, span), CASH, acct, amt, "deposit", "structuring", "s" + sid); sent += amt;
      }
    }
    for (let sid = 0; sid < cfg.schemes; sid++) {           // تدوير الأموال في حلقة مغلقة
      const ring = g.sample(biz, g.int(3, 6));
      let amount = g.uniform(50000, 400000), day = g.int(0, cfg.days - 15);
      ring.forEach((src, i) => {
        amount *= g.uniform(0.97 - 0.3 * c, 0.995);
        day += g.int(0, Math.floor(3 + 12 * c));
        add(day, src, ring[(i + 1) % ring.length], round2(amount), "b2b", "round_trip", "r" + sid);
      });
    }
    for (let sid = 0; sid < cfg.schemes; sid++) {           // فواتير وهمية بمبالغ مستديرة
      const [shell, buyer] = g.sample(biz, 2), base = g.choice([5000, 10000, 20000, 25000]);
      const count = g.int(12, 30);
      for (let k = 0; k < count; k++) {
        let amt = base * g.int(1, 4);
        if (g.random() < c) amt = round2(amt * g.uniform(0.9, 1.1));
        add(g.int(0, cfg.days), buyer, shell, amt, "b2b", "fake_invoice", "f" + sid);
      }
    }
    for (let sid = 0; sid < cfg.schemes; sid++) {           // حسابات وسيطة: تجميع ثم تحويل
      const [mule, collector] = g.sample(people, 2);
      const sources = g.sample(people, g.int(10, 25)).filter((s) => s !== mule && s !== collector);
      const span = Math.floor(5 + 40 * c), day = g.int(0, Math.max(cfg.days - span - 5, 1));
      let total = 0;
      for (const s of sources) { const a = round2(g.uniform(500, 3000)); total += a; add(day + g.int(0, span), s, mule, a, "p2p", "mule", "m" + sid); }
      total *= g.uniform(0.85, 0.95);
      const parts = 1 + g.int(0, Math.floor(1 + 4 * c));
      for (let k = 0; k < parts; k++) add(day + span + 1 + k, mule, collector, round2(total / parts), "p2p", "mule", "m" + sid);
    }
    tx.sort((a, b) => a.day - b.day || (a.src < b.src ? -1 : a.src > b.src ? 1 : 0));
    tx.forEach((t, i) => { t.id = i; });
    return tx;
  }

  // المشارك في الاحتيال: من أرسل أو استقبل معاملة احتيالية (في نمط الوسيط: المستقبِل فقط، لأن المرسلين ضحايا غالباً)
  function labels(tx) {
    const lab = new Map();
    for (const t of tx) { if (t.src !== CASH && !lab.has(t.src)) lab.set(t.src, null); if (!lab.has(t.dst)) lab.set(t.dst, null); }
    for (const t of tx) {
      if (!t.typology) continue;
      if (t.typology !== "mule" && t.src !== CASH && !lab.get(t.src)) lab.set(t.src, t.typology);
      if (!lab.get(t.dst)) lab.set(t.dst, t.typology);
    }
    return lab;   // حساب → النمط أو null
  }

  // ---------------------------------------------------------------- قانون بنفورد
  const BENFORD = Array.from({ length: 9 }, (_, i) => Math.log10(1 + 1 / (i + 1)));
  function benford(amounts) {
    const counts = new Array(9).fill(0); let n = 0;
    for (const a of amounts) {
      if (a < 1) continue;
      counts[Math.floor(a / 10 ** Math.floor(Math.log10(a))) - 1]++; n++;
    }
    const observed = counts.map((k) => k / Math.max(n, 1));
    const mad = observed.reduce((s, o, i) => s + Math.abs(o - BENFORD[i]), 0) / 9;
    const verdict = mad < 0.006 ? "مطابقة قريبة" : mad < 0.012 ? "مطابقة مقبولة" : mad < 0.015 ? "مطابقة هامشية" : "عدم مطابقة";
    return { observed, expected: BENFORD, mad, verdict, n, conforms: mad < 0.015 };
  }

  // ---------------------------------------------------------------- القواعد
  function flagStructuring(tx, threshold, windowDays = 30, minCount = 3) {
    const byAcct = new Map();
    for (const t of tx) if (t.src === CASH && t.amount >= 0.85 * threshold && t.amount < threshold) {
      if (!byAcct.has(t.dst)) byAcct.set(t.dst, []);
      byAcct.get(t.dst).push(t.day);
    }
    const out = new Set();
    for (const [acct, days] of byAcct) {
      days.sort((a, b) => a - b);
      let best = 0;
      for (let i = 0, j = 0; i < days.length; i++) { while (j < days.length && days[j] < days[i] + windowDays) j++; best = Math.max(best, j - i); }
      if (best >= minCount) out.add(acct);
    }
    return out;
  }

  // بحث بالعمق عن أموال تعود لمصدرها بترتيب زمني ومبالغ متقاربة
  function findCycles(tx, { minAmount = 20000, maxLen = 5, windowDays = 15, tolerance = 0.1 } = {}) {
    const out = new Map();
    for (const t of tx) if (t.amount >= minAmount && t.src !== CASH) {
      if (!out.has(t.src)) out.set(t.src, []);
      out.get(t.src).push(t);
    }
    const found = [], seen = new Set();
    const dfs = (start, node, path, day0, lastDay, amt0, ids) => {
      for (const e of out.get(node) || []) {
        if (e.day < lastDay || e.day - day0 > windowDays || Math.abs(e.amount / amt0 - 1) > tolerance) continue;
        if (e.dst === start && path.length >= 2) {
          const key = ids.concat(e.id).sort((a, b) => a - b).join(",");
          if (!seen.has(key)) { seen.add(key); found.push({ accounts: path.slice(), amount: amt0, day: day0 }); }
        } else if (!path.includes(e.dst) && path.length < maxLen) {
          dfs(start, e.dst, path.concat(e.dst), day0, e.day, amt0, ids.concat(e.id));
        }
      }
    };
    for (const [src, edges] of out) for (const e of edges) if (e.dst !== src) dfs(src, e.dst, [src, e.dst], e.day, e.day, e.amount, [e.id]);
    return found;
  }

  // ---------------------------------------------------------------- خصائص الحسابات
  const FEATURES = ["pass_through", "round_share", "round_count", "avg_amount_log", "near_threshold",
    "fan_in_ratio", "burst_senders", "uniq_src", "uniq_dst", "n_in", "n_out"];
  const FEATURE_NAMES = {
    pass_through: "نسبة تمرير الأموال", round_share: "حصة المبالغ المستديرة", round_count: "عدد المبالغ المستديرة الكبيرة",
    avg_amount_log: "متوسط المبلغ", near_threshold: "إيداعات قرب حد الإبلاغ", fan_in_ratio: "نسبة المرسلين للمستقبلين",
    burst_senders: "مرسلون كثر في أسبوع", uniq_src: "عدد المرسلين", uniq_dst: "عدد المستقبلين", n_in: "عدد الواردات", n_out: "عدد الصادرات",
  };

  function features(tx, accounts, threshold) {
    const f = new Map(accounts.map((a) => [a, { n_out: 0, sum_out: 0, dst: new Set(), n_in: 0, sum_in: 0, src: new Set(),
      n_all: 0, sum_all: 0, round_all: 0, round_count: 0, near_threshold: 0, p2p: [] }]));
    const touch = (a, amt) => {
      const r = f.get(a); if (!r) return;
      r.n_all++; r.sum_all += amt;
      if (amt % 1000 === 0) r.round_all++;
      if (amt >= 5000 && amt % 1000 === 0) r.round_count++;
    };
    for (const t of tx) {
      const s = f.get(t.src), d = f.get(t.dst);
      if (s) { s.n_out++; s.sum_out += t.amount; s.dst.add(t.dst); }
      if (d) {
        d.n_in++; d.sum_in += t.amount; d.src.add(t.src);
        if (t.src === CASH && t.amount >= 0.85 * threshold && t.amount < threshold) d.near_threshold++;
        if (t.kind === "p2p") d.p2p.push(t);
      }
      if (t.src !== CASH) touch(t.src, t.amount);
      touch(t.dst, t.amount);
    }
    const rows = new Map();
    for (const [a, r] of f) {
      // أكبر عدد من المرسلين المختلفين خلال 7 أيام (التحويلات بين الأفراد)
      let burst = 0;
      const p = r.p2p.sort((x, y) => x.day - y.day);
      for (let i = 0, j = 0; i < p.length; i++) {
        while (j < p.length && p[j].day < p[i].day + 7) j++;
        burst = Math.max(burst, new Set(p.slice(i, j).map((t) => t.src)).size);
      }
      rows.set(a, {
        n_out: r.n_out, n_in: r.n_in, uniq_dst: r.dst.size, uniq_src: r.src.size,
        pass_through: Math.min(r.sum_out, r.sum_in) / Math.max(r.sum_in, 1),
        round_share: r.n_all ? r.round_all / r.n_all : 0, round_count: r.round_count,
        avg_amount_log: Math.log1p(r.n_all ? r.sum_all / r.n_all : 0), near_threshold: r.near_threshold,
        fan_in_ratio: r.src.size / Math.max(r.dst.size, 1), burst_senders: burst,
      });
    }
    return rows;
  }

  // ---------------------------------------------------------------- انحدار لوجستي بموازنة الأصناف
  function trainLogistic(X, y, { lr = 0.1, epochs = 2000, l2 = 1e-3 } = {}) {
    const tr = (v) => Math.sign(v) * Math.log1p(Math.abs(v));
    const d = X[0].length, n = X.length;
    const T = X.map((r) => r.map(tr));
    const mu = new Array(d).fill(0), sd = new Array(d).fill(0);
    T.forEach((r) => r.forEach((v, j) => { mu[j] += v / n; }));
    T.forEach((r) => r.forEach((v, j) => { sd[j] += (v - mu[j]) ** 2 / n; }));
    for (let j = 0; j < d; j++) sd[j] = Math.sqrt(sd[j]) + 1e-9;
    const Z = T.map((r) => r.map((v, j) => (v - mu[j]) / sd[j]));
    const pos = y.reduce((s, v) => s + v, 0);
    const wPos = n / (2 * Math.max(pos, 1)), wNeg = n / (2 * Math.max(n - pos, 1));
    const w = new Array(d).fill(0); let b = 0;
    const grad = new Array(d);
    for (let e = 0; e < epochs; e++) {
      grad.fill(0); let gb = 0;
      for (let i = 0; i < n; i++) {
        let z = b; for (let j = 0; j < d; j++) z += Z[i][j] * w[j];
        const g = (y[i] ? wPos : wNeg) * (1 / (1 + Math.exp(-z)) - y[i]);
        for (let j = 0; j < d; j++) grad[j] += Z[i][j] * g;
        gb += g;
      }
      for (let j = 0; j < d; j++) w[j] -= lr * (grad[j] / n + l2 * w[j]);
      b -= lr * gb / n;
    }
    return {
      weights: w,
      predict: (row) => { let z = b; row.forEach((v, j) => { z += ((tr(v) - mu[j]) / sd[j]) * w[j]; }); return 1 / (1 + Math.exp(-z)); },
    };
  }

  function evaluate(flagged, testSet, lab) {
    const truth = [...testSet].filter((a) => lab.get(a));
    const f = [...flagged].filter((a) => testSet.has(a));
    const tp = f.filter((a) => lab.get(a)).length;
    const precision = f.length ? tp / f.length : 0, recall = truth.length ? tp / truth.length : 0;
    const byTyp = {};
    for (const t of Object.keys(TYPOLOGIES)) {
      const members = truth.filter((a) => lab.get(a) === t);
      byTyp[t] = members.length ? members.filter((a) => flagged.has(a)).length / members.length : NaN;
    }
    return { flagged: f.length, tp, precision, recall, f1: precision + recall ? (2 * precision * recall) / (precision + recall) : 0, byTyp };
  }

  // ---------------------------------------------------------------- تشغيل كل الكواشف
  function run(cfg, seed = 0) {
    const tx = ledger(cfg, seed);
    const lab = labels(tx);
    const accounts = [...lab.keys()];
    const feats = features(tx, accounts, cfg.threshold);
    const g = rng("split", seed);
    const testSet = new Set(accounts.filter(() => g.random() < 0.5));

    const structuring = flagStructuring(tx, cfg.threshold);
    const cycles = findCycles(tx);
    const inCycles = new Set(cycles.flatMap((c) => c.accounts));
    const invoices = new Set(accounts.filter((a) => feats.get(a).round_count >= 8));
    const mules = new Set(accounts.filter((a) => feats.get(a).burst_senders >= 6));
    for (const t of tx) if (mules.has(t.src) && t.amount >= 5000 && t.kind === "p2p") mules.add(t.dst);  // تتبع الأموال خطوة: المُجمِّع
    const rules = new Set([...structuring, ...inCycles, ...invoices, ...mules]);

    const X = accounts.map((a) => FEATURES.map((k) => feats.get(a)[k]));
    const train = accounts.map((a, i) => i).filter((i) => !testSet.has(accounts[i]));
    const model = trainLogistic(train.map((i) => X[i]), train.map((i) => (lab.get(accounts[i]) ? 1 : 0)));
    const scores = new Map(accounts.map((a, i) => [a, model.predict(X[i])]));
    const ml = new Set(accounts.filter((a) => scores.get(a) > 0.5));

    const results = [
      ["تجزئة الإيداعات", structuring], ["الدوائر المغلقة", inCycles], ["الفواتير المستديرة", invoices],
      ["الحسابات الوسيطة", mules], ["كل القواعد معاً", rules], ["نموذج تعلّم آلة", ml],
      ["القواعد + النموذج", new Set([...rules, ...ml])],
    ].map(([name, set]) => ({ name, ...evaluate(set, testSet, lab) }));

    return { tx, lab, cycles, results, scores, testSet, weights: FEATURES.map((k, j) => ({ key: k, label: FEATURE_NAMES[k], value: model.weights[j] })) };
  }

  window.Fraud = { CASH, TYPOLOGIES, DEFAULT, ledger, labels, benford, flagStructuring, findCycles, features, trainLogistic, run };
})();
