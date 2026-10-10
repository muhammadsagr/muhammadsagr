/* الأسعار والعوائد: نفس منطق mizan/sources.py و mizan/analytics.py. */
(function () {
  "use strict";
  const { rng, mean, std, corr } = window.M;

  // أصول تجريبية بأسماء توضيحية — الأرقام مُولَّدة وليست أسعار سوق حقيقية
  const UNIVERSE = [
    { id: "ENERGY", label: "طاقة", price: 30, drift: 0.06, vol: 0.22, beta: 0.9 },
    { id: "BANK", label: "بنوك", price: 80, drift: 0.09, vol: 0.25, beta: 1.1 },
    { id: "TELECOM", label: "اتصالات", price: 40, drift: 0.05, vol: 0.18, beta: 0.7 },
    { id: "PETCHEM", label: "بتروكيماويات", price: 70, drift: 0.04, vol: 0.30, beta: 1.2 },
    { id: "INDEX", label: "مؤشر السوق", price: 11000, drift: 0.07, vol: 0.16, beta: 1.0 },
    { id: "GOLD", label: "ذهب", price: 2000, drift: 0.05, vol: 0.14, beta: -0.1 },
  ];
  const TRADING_DAYS = 252;

  function businessDays(from, to) {
    const out = [];
    for (let d = new Date(from); d <= to; d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)) {
      const w = d.getDay();
      if (w !== 0 && w !== 6) out.push(d);  // أيام العمل (الاثنين–الجمعة) كما في pandas.bdate_range
    }
    return out;
  }

  // حركة براونية هندسية + عامل سوق مشترك (ارتباط) + فترات تذبذب مرتفع + قفزات نادرة
  function generate(seed = 1) {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const dates = businessDays(new Date(2015, 0, 1), today);
    const n = dates.length, dt = 1 / TRADING_DAYS;
    const mr = rng(seed, "market"), rr = rng(seed, "regime");
    const regimeRaw = Array.from({ length: n }, () => (rr.random() < 0.005 ? 2 : 1));
    const market = regimeRaw.map((_, i) => {
      let r = 1; for (let k = Math.max(0, i - 19); k <= i; k++) r = Math.max(r, regimeRaw[k]);
      return mr.normal() * r;
    });
    const prices = {};
    for (const a of UNIVERSE) {
      const g = rng(seed, a.id), load = 0.6 * a.beta, idio = Math.sqrt(1 - load * load);
      const jumpP = 0.004, jumpMean = -0.03, dv = a.vol * Math.sqrt(dt);
      const close = new Float64Array(n);
      let lp = Math.log(a.price);
      for (let i = 0; i < n; i++) {
        if (i > 0) {
          const z = load * market[i] + idio * g.normal();
          const jump = g.random() < jumpP ? g.normal(jumpMean, 0.04) : 0;
          lp += (a.drift - 0.5 * a.vol ** 2) * dt - jumpP * jumpMean + dv * z + jump;
        }
        close[i] = Math.exp(lp);
      }
      prices[a.id] = close;
    }
    return { dates, prices };
  }

  function returns(p) { const r = new Float64Array(p.length - 1); for (let i = 1; i < p.length; i++) r[i - 1] = p[i] / p[i - 1] - 1; return r; }
  function drawdown(p) { let peak = -Infinity; return Array.from(p, (v) => { peak = Math.max(peak, v); return v / peak - 1; }); }
  function rollingVol(r, w) {
    const out = new Array(r.length + 1).fill(NaN);
    for (let i = w; i <= r.length; i++) out[i] = std(Array.from(r.subarray(i - w, i))) * Math.sqrt(TRADING_DAYS);
    return out;
  }
  function summary(p, dates) {
    const r = Array.from(returns(p));
    const years = (dates[dates.length - 1] - dates[0]) / (365.25 * 864e5);
    const total = p[p.length - 1] / p[0] - 1;
    const cagr = years > 0 ? (p[p.length - 1] / p[0]) ** (1 / years) - 1 : NaN;
    const vol = std(r) * Math.sqrt(TRADING_DAYS);
    return { last: p[p.length - 1], total, cagr, vol, sharpe: cagr / vol, mdd: Math.min(...drawdown(p)), worst: Math.min(...r), best: Math.max(...r) };
  }
  function correlation(series) {
    const rs = series.map((p) => Array.from(returns(p)));
    return rs.map((a) => rs.map((b) => corr(a, b)));
  }

  window.Prices = { UNIVERSE, generate, returns, drawdown, rollingVol, summary, correlation, mean };
})();
