/* التهرب الضريبي: نقل مباشر لـ mizan/fraudsim/tax.py.
   كل شخص يختار نسبة التصريح d التي تعظّم:
     EU = (1-p)·u(1 - t·d) + p·u(1 - t - f·t·(1-d)) - m·(1-d)²
   (Allingham–Sandmo بصيغة Yitzhaki + كلفة أخلاقية)، و u منفعة CRRA. */
(function () {
  "use strict";
  const { rng } = window.M;

  // القطاع: حصة السكان، نسبة من يمكنهم الإخفاء، أقصى نسبة دخل قابلة للإخفاء، مضاعف الدخل
  const SECTORS = [
    { name: "موظفون برواتب", share: 0.55, canHide: 0.0, cap: 0.05, scale: 1.0 },
    { name: "مهن حرة", share: 0.15, canHide: 1.0, cap: 0.50, scale: 1.4 },
    { name: "تجزئة نقدية", share: 0.12, canHide: 1.0, cap: 0.60, scale: 0.9 },
    { name: "مقاولات", share: 0.10, canHide: 1.0, cap: 0.45, scale: 1.3 },
    { name: "شركات كبرى", share: 0.08, canHide: 1.0, cap: 0.15, scale: 6.0 },
  ];

  const DEFAULT_POLICY = { taxRate: 0.20, penalty: 1.5, auditRate: 0.03, targeting: 0.5, detection: 0.8, signalNoise: 0.35 };

  function population(n = 5000, honestShare = 0.3, seed = 0) {
    const g = rng("pop", seed);
    const weights = SECTORS.map((s) => s.share);
    const P = { n, sector: new Int8Array(n), income: new Float64Array(n), rho: new Float64Array(n),
      moral: new Float64Array(n), honest: new Uint8Array(n), maxHidden: new Float64Array(n) };
    for (let i = 0; i < n; i++) {
      const k = g.weighted(weights), s = SECTORS[k];
      P.sector[i] = k;
      P.income[i] = Math.round(s.scale * g.lognormal(Math.log(120000), 0.6) / 100) * 100;
      P.rho[i] = g.uniform(0.8, 3.5);
      P.moral[i] = g.lognormal(Math.log(0.25), 0.9);
      P.honest[i] = g.random() < honestShare ? 1 : 0;
      P.maxHidden[i] = g.random() < Math.max(s.canHide, 0.2) ? s.cap : 0;
    }
    return P;
  }

  const crra = (w, rho) => {
    w = Math.max(w, 1e-6);
    return Math.abs(rho - 1) < 1e-9 ? Math.log(w) : w ** (1 - rho) / (1 - rho);
  };

  function optimalDeclaration(p, rho, maxHidden, t, f, moral = 0, grid = 51) {
    let best = 1, bestU = -Infinity;
    for (let k = 0; k < grid; k++) {
      const d = 1 - maxHidden * (k / (grid - 1));
      const u = (1 - p) * crra(1 - t * d, rho) + p * crra(1 - t - f * t * (1 - d), rho) - moral * (1 - d) ** 2;
      if (u > bestU) { bestU = u; best = d; }
      if (maxHidden === 0) break;
    }
    return best;
  }

  function simulate(P, policy, years = 10, seed = 0, learning = 0.3) {
    const g = rng("sim", seed);
    const n = P.n, { taxRate: t, penalty: f } = policy;
    let belief = new Float64Array(n);
    for (let i = 0; i < n; i++) belief[i] = Math.min(0.9, Math.max(0.001, policy.auditRate * g.lognormal(0.3, 0.8)));
    let totalIncome = 0; for (let i = 0; i < n; i++) totalIncome += P.income[i];

    const yearly = [];
    const frac = new Float64Array(n), audited = new Uint8Array(n), caught = new Uint8Array(n);
    for (let year = 1; year <= years; year++) {
      let declaredSum = 0, hiddenSum = 0, compliant = 0;
      const hidden = new Float64Array(n), risk = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        frac[i] = P.honest[i] ? 1 : optimalDeclaration(belief[i], P.rho[i], P.maxHidden[i], t, f, P.moral[i]);
        const declared = P.income[i] * frac[i];
        hidden[i] = P.income[i] - declared;
        declaredSum += declared; hiddenSum += hidden[i];
        if (hidden[i] <= 1e-9) compliant++;
        const signal = P.income[i] * g.lognormal(0, policy.signalNoise);   // ما تراه المصلحة
        risk[i] = 1 - declared / signal;
      }
      // التدقيق: جزء موجّه بأعلى درجات المخاطر، والباقي عشوائي
      const nAudit = Math.round(policy.auditRate * n), nTarget = Math.round(policy.targeting * nAudit);
      audited.fill(0); caught.fill(0);
      const order = Array.from({ length: n }, (_, i) => i).sort((a, b) => risk[b] - risk[a]);
      for (let k = 0; k < nTarget; k++) audited[order[k]] = 1;
      const rest = order.slice(nTarget);
      for (const i of g.sample(rest, Math.min(nAudit - nTarget, rest.length))) audited[i] = 1;

      let recovered = 0, nCaught = 0, nAudited = 0, beliefSum = 0;
      const secAud = new Float64Array(SECTORS.length), secN = new Float64Array(SECTORS.length);
      for (let i = 0; i < n; i++) {
        beliefSum += belief[i];
        if (audited[i]) { nAudited++; secAud[P.sector[i]]++; }
        secN[P.sector[i]]++;
        if (audited[i] && hidden[i] > 0 && g.random() < policy.detection) {
          caught[i] = 1; nCaught++; recovered += t * hidden[i] * (1 + f);
        }
      }
      yearly.push({
        year, compliance: compliant / n, evasionRate: hiddenSum / totalIncome,
        taxDue: t * totalIncome, taxDeclared: t * declaredSum, taxGap: t * hiddenSum,
        recovered, audits: nAudited, hitRate: nCaught / Math.max(nAudited, 1), perceivedAudit: beliefSum / n,
      });
      // التعلّم: من دُقِّق عليه يرفع تقديره، والبقية تتأثر بما يرونه في قطاعهم
      for (let i = 0; i < n; i++) {
        const peer = secAud[P.sector[i]] / secN[P.sector[i]];
        const observed = audited[i] ? 1 : 0.5 * policy.auditRate + 0.5 * peer;
        belief[i] = Math.min(0.9, Math.max(0.001, (1 - learning) * belief[i] + learning * observed));
      }
    }
    // متوسط نسبة الدخل المخفي لكل قطاع في آخر سنة
    const bySector = SECTORS.map((s, k) => {
      let sumH = 0, c = 0;
      for (let i = 0; i < n; i++) if (P.sector[i] === k) { sumH += 1 - frac[i]; c++; }
      return { name: s.name, hidden: c ? sumH / c : 0, count: c };
    });
    return { yearly, bySector };
  }

  function sweep(P, policy, auditRates, penalties, years = 5, seed = 0) {
    return penalties.map((pen) => auditRates.map((a) => {
      const { yearly } = simulate(P, { ...policy, auditRate: a, penalty: pen }, years, seed);
      const last = yearly[yearly.length - 1];
      return last.taxGap / last.taxDue;
    }));
  }

  window.Tax = { SECTORS, DEFAULT_POLICY, population, optimalDeclaration, simulate, sweep };
})();
