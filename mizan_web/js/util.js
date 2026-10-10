/* أدوات مشتركة: مولّد أرقام عشوائية قابل للتكرار، وإحصاءات، وتنسيق أرقام عربي. */
(function () {
  "use strict";

  // mulberry32: مولّد سريع؛ نفس البذرة = نفس الأرقام دائماً
  function hashSeed(parts) {
    let h = 2166136261 >>> 0;
    for (const p of parts) {
      const s = String(p);
      for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
      h ^= 0x9e3779b9; h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function rng(...seedParts) {
    let a = hashSeed(seedParts);
    let spare = null;
    const random = () => {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const normal = (mu = 0, sd = 1) => {
      if (spare !== null) { const z = spare; spare = null; return mu + sd * z; }
      let u = 0, v = 0;
      while (u === 0) u = random();
      v = random();
      const r = Math.sqrt(-2 * Math.log(u));
      spare = r * Math.sin(2 * Math.PI * v);
      return mu + sd * r * Math.cos(2 * Math.PI * v);
    };
    return {
      random,
      normal,
      uniform: (lo, hi) => lo + (hi - lo) * random(),
      int: (lo, hi) => lo + Math.floor(random() * (hi - lo)),            // [lo, hi)
      lognormal: (mu, sd) => Math.exp(normal(mu, sd)),
      choice: (arr) => arr[Math.floor(random() * arr.length)],
      weighted: (weights) => {
        let r = random() * weights.reduce((s, w) => s + w, 0);
        for (let i = 0; i < weights.length; i++) { r -= weights[i]; if (r < 0) return i; }
        return weights.length - 1;
      },
      sample: (arr, k) => {                                               // بدون تكرار
        const a = arr.slice();
        for (let i = 0; i < k; i++) { const j = i + Math.floor(random() * (a.length - i)); [a[i], a[j]] = [a[j], a[i]]; }
        return a.slice(0, k);
      },
    };
  }

  const sum = (a) => { let s = 0; for (const x of a) s += x; return s; };
  const mean = (a) => (a.length ? sum(a) / a.length : NaN);
  function std(a) {
    if (a.length < 2) return NaN;
    const m = mean(a); let s = 0;
    for (const x of a) s += (x - m) ** 2;
    return Math.sqrt(s / (a.length - 1));
  }
  function corr(a, b) {
    const ma = mean(a), mb = mean(b); let sab = 0, sa = 0, sb = 0;
    for (let i = 0; i < a.length; i++) { const da = a[i] - ma, db = b[i] - mb; sab += da * db; sa += da * da; sb += db * db; }
    return sa && sb ? sab / Math.sqrt(sa * sb) : 0;
  }

  // تنسيق بالأرقام العربية-الغربية (0-9) لأنها الشائعة في التقارير المالية
  const nf = (d) => new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const fmt = {
    pct: (x, d = 1) => (Number.isFinite(x) ? nf(d).format(x * 100) + "%" : "—"),
    num: (x, d = 0) => (Number.isFinite(x) ? nf(d).format(x) : "—"),
    money: (x) => {
      if (!Number.isFinite(x)) return "—";
      const a = Math.abs(x);
      if (a >= 1e9) return nf(2).format(x / 1e9) + " مليار";
      if (a >= 1e6) return nf(1).format(x / 1e6) + " مليون";
      if (a >= 1e3) return nf(1).format(x / 1e3) + " ألف";
      return nf(0).format(x);
    },
    date: (d) => d.toLocaleDateString("ar-EG-u-nu-latn", { year: "numeric", month: "short", day: "numeric" }),
    month: (d) => d.toLocaleDateString("ar-EG-u-nu-latn", { year: "numeric", month: "short" }),
  };

  const el = (tag, attrs = {}, html = "") => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (html) e.innerHTML = html;
    return e;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // ألوان السلاسل بترتيب ثابت؛ تُقرأ من متغيرات CSS كي تتبع الوضع الفاتح/الداكن
  const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  // تنفيذ عمل ثقيل بعد أن يرسم المتصفح حالة "جاري الحساب"
  const later = (fn) => new Promise((res) => requestAnimationFrame(() => setTimeout(() => res(fn()), 0)));

  window.M = { rng, sum, mean, std, corr, fmt, el, esc, SERIES, cssVar, later };
})();
