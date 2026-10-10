/* رسوم SVG مكتوبة يدوياً: خطوط، وأعمدة أفقية، وخريطة حرارية، ورسم بنفورد. كلها بتلميح عند المرور. */
(function () {
  "use strict";
  const { fmt, esc } = window.M;
  const NS = "http://www.w3.org/2000/svg";

  // ---------------------------------------------------------------- التلميح
  const tip = document.createElement("div");
  tip.id = "tip"; tip.hidden = true; tip.setAttribute("role", "status");
  const attachTip = () => document.body.appendChild(tip);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", attachTip); else attachTip();
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x - r.width / 2, top = y - r.height - 14;
    left = Math.max(8, Math.min(left, window.innerWidth - r.width - 8));
    if (top < 8) top = y + 18;
    tip.style.left = left + "px"; tip.style.top = top + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  const tipRow = (color, label, value) =>
    `<div class="row"><span class="sw" style="background:${color}"></span>${esc(label)}<b>${value}</b></div>`;

  // ---------------------------------------------------------------- أدوات
  function svgEl(tag, attrs = {}, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      // متغيرات CSS تعمل بثبات داخل style أكثر من سمات SVG
      if ((k === "fill" || k === "stroke") && String(v).includes("var(")) e.style.setProperty(k, v);
      else e.setAttribute(k, v);
    }
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceTicks(lo, hi, count = 5) {
    if (!(hi > lo)) { const pad = Math.abs(lo) * 0.1 || 1; lo -= pad; hi += pad; }
    const raw = (hi - lo) / count;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
    const start = Math.floor(lo / step) * step, end = Math.ceil(hi / step) * step;
    const ticks = [];
    for (let v = start; v <= end + step / 2; v += step) ticks.push(+v.toFixed(10));
    return ticks;
  }
  function makeSvg(container, width, height) {
    container.innerHTML = "";
    const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
    container.appendChild(svg);
    return svg;
  }
  const widthOf = (container) => Math.max(300, Math.round(container.clientWidth || 640));

  // محور زمني: علامات عند بداية السنوات أو الأشهر حسب طول الفترة
  function timeTicks(dates) {
    const t0 = dates[0], t1 = dates[dates.length - 1];
    const years = (t1 - t0) / (365.25 * 864e5);
    const out = [];
    const stepMonths = years > 6 ? 12 : years > 2.5 ? 6 : years > 1 ? 3 : 1;
    let d = new Date(t0.getFullYear(), t0.getMonth() + 1, 1);
    while (d <= t1) {
      if (d.getMonth() % stepMonths === 0) out.push(new Date(d));
      d = new Date(d.getFullYear(), d.getMonth() + 1, 1);
    }
    const label = stepMonths === 12 ? (x) => String(x.getFullYear()) : fmt.month;
    return { ticks: out, label };
  }

  // ---------------------------------------------------------------- رسم خطي
  // series: [{name, color, values}] بنفس طول x. x: تواريخ أو أرقام.
  function line(container, { x, series, height = 280, yFormat = (v) => fmt.num(v), xFormat, zero = false, yTitle }) {
    const W = widthOf(container), H = height;
    const m = { t: 12, r: 16, b: 28, l: 56 };
    const svg = makeSvg(container, W, H);
    if (yTitle) svg.setAttribute("aria-label", yTitle);
    const isDate = x[0] instanceof Date;
    const xs = x.map((v) => (isDate ? v.getTime() : v));
    let lo = Infinity, hi = -Infinity;
    for (const s of series) for (const v of s.values) if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    const yt = niceTicks(lo, hi, 5);
    const y0 = yt[0], y1 = yt[yt.length - 1];
    const X = (v) => m.l + ((v - xs[0]) / (xs[xs.length - 1] - xs[0] || 1)) * (W - m.l - m.r);
    const Y = (v) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);

    for (const t of yt) {
      svgEl("line", { class: "grid-line", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, svg);
      svgEl("text", { class: "tick", x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg).textContent = yFormat(t);
    }
    if (zero && y0 < 0) svgEl("line", { class: "zero", x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0) }, svg);
    svgEl("line", { class: "base", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }, svg);
    if (isDate) {
      const { ticks, label } = timeTicks(x);
      const every = Math.ceil(ticks.length / Math.max(2, Math.floor((W - m.l - m.r) / 80)));
      ticks.filter((_, i) => i % every === 0).forEach((d) => {
        svgEl("text", { class: "tick", x: X(d.getTime()), y: H - 8, "text-anchor": "middle" }, svg).textContent = label(d);
      });
    } else {
      const xt = niceTicks(xs[0], xs[xs.length - 1], Math.min(xs.length - 1, 8)).filter((v) => v >= xs[0] && v <= xs[xs.length - 1]);
      xt.forEach((v) => { svgEl("text", { class: "tick", x: X(v), y: H - 8, "text-anchor": "middle" }, svg).textContent = xFormat ? xFormat(v) : v; });
    }
    for (const s of series) {
      let d = "", pen = false;
      s.values.forEach((v, i) => {
        if (!Number.isFinite(v)) { pen = false; return; }
        d += (pen ? "L" : "M") + X(xs[i]).toFixed(1) + "," + Y(v).toFixed(1); pen = true;
      });
      svgEl("path", { class: "series", d, stroke: s.color }, svg);
      if (s.markers) s.values.forEach((v, i) => svgEl("circle", { cx: X(xs[i]), cy: Y(v), r: 4, fill: s.color, class: "hover-dot" }, svg));
    }

    // طبقة التفاعل: خط عمودي ونقاط وتلميح عند أقرب نقطة
    const hover = svgEl("g", { visibility: "hidden" }, svg);
    const xl = svgEl("line", { class: "xhair", y1: m.t, y2: H - m.b }, hover);
    const dots = series.map((s) => svgEl("circle", { r: 4.5, fill: s.color, class: "hover-dot" }, hover));
    const overlay = svgEl("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    const pick = (ev) => {
      const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
      const p = pt.matrixTransform(svg.getScreenCTM().inverse());
      const target = xs[0] + ((p.x - m.l) / (W - m.l - m.r)) * (xs[xs.length - 1] - xs[0]);
      let lo2 = 0, hi2 = xs.length - 1;
      while (hi2 - lo2 > 1) { const mid = (lo2 + hi2) >> 1; if (xs[mid] < target) lo2 = mid; else hi2 = mid; }
      const i = Math.abs(xs[lo2] - target) < Math.abs(xs[hi2] - target) ? lo2 : hi2;
      const cx = X(xs[i]);
      xl.setAttribute("x1", cx); xl.setAttribute("x2", cx);
      series.forEach((s, k) => {
        const v = s.values[i];
        dots[k].setAttribute("visibility", Number.isFinite(v) ? "visible" : "hidden");
        if (Number.isFinite(v)) { dots[k].setAttribute("cx", cx); dots[k].setAttribute("cy", Y(v)); }
      });
      hover.setAttribute("visibility", "visible");
      const head = isDate ? fmt.date(x[i]) : (xFormat ? xFormat(x[i]) : x[i]);
      const rows = series.map((s) => [s, s.values[i]]).filter(([, v]) => Number.isFinite(v))
        .sort((a, b) => b[1] - a[1]).map(([s, v]) => tipRow(s.color, s.name, yFormat(v))).join("");
      showTip(`<div>${esc(head)}</div>${rows}`, ev.clientX, svg.getBoundingClientRect().top + Y(Math.max(...series.map((s) => s.values[i]).filter(Number.isFinite))) * (svg.getBoundingClientRect().height / H));
    };
    overlay.addEventListener("pointermove", pick);
    overlay.addEventListener("pointerdown", pick);
    overlay.addEventListener("pointerleave", () => { hover.setAttribute("visibility", "hidden"); hideTip(); });
  }

  // ---------------------------------------------------------------- أعمدة أفقية
  // items: [{label, value, color?}] — القيم موجبة أو سالبة
  function hbar(container, items, { format = (v) => fmt.num(v, 2), color = "var(--s1)", negColor, rowH = 30 } = {}) {
    const W = widthOf(container);
    const labelW = Math.min(190, W * 0.38), m = { t: 6, r: 56, b: 24, l: 8 };
    const H = m.t + m.b + items.length * rowH;
    const svg = makeSvg(container, W, H);
    const lo = Math.min(0, ...items.map((d) => d.value)), hi = Math.max(0, ...items.map((d) => d.value));
    const ticks = niceTicks(lo, hi, 4);
    const x0 = m.l, x1 = W - labelW - m.r;                      // مساحة الأعمدة على اليسار، والتسميات على اليمين (RTL)
    const X = (v) => x0 + ((v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0] || 1)) * (x1 - x0);
    for (const t of ticks) {
      svgEl("line", { class: "grid-line", x1: X(t), x2: X(t), y1: m.t, y2: H - m.b }, svg);
      svgEl("text", { class: "tick", x: X(t), y: H - 6, "text-anchor": "middle" }, svg).textContent = format(t);
    }
    items.forEach((d, i) => {
      const y = m.t + i * rowH;
      const g = svgEl("g", { class: "mark" }, svg);
      svgEl("rect", { class: "bar-hit", x: 0, y, width: W, height: rowH }, g);
      const a = X(Math.min(0, d.value)), b = X(Math.max(0, d.value));
      const c = d.color || (d.value < 0 && negColor ? negColor : color);
      svgEl("rect", { class: "fill", x: a, y: y + 6, width: Math.max(1, b - a), height: rowH - 12, rx: 3, fill: c }, g);
      svgEl("text", { class: "lbl", x: W - 4, y: y + rowH / 2 + 4, "text-anchor": "start", direction: "rtl" }, g).textContent = d.label;
      svgEl("text", { class: "val", x: d.value < 0 ? a - 6 : b + 6, y: y + rowH / 2 + 4, "text-anchor": d.value < 0 ? "end" : "start" }, g).textContent = format(d.value);
      g.addEventListener("pointermove", (ev) => showTip(`${esc(d.label)}<div class="row"><b>${format(d.value)}</b></div>`, ev.clientX, ev.clientY));
      g.addEventListener("pointerleave", hideTip);
    });
    svgEl("line", { class: "base", x1: X(0), x2: X(0), y1: m.t, y2: H - m.b }, svg);
  }

  // ---------------------------------------------------------------- خريطة حرارية
  // colorFn(v) → لون الخلية، textFn(v) → لون النص
  function heatmap(container, { rows, cols, values, colorFn, textFn, format, rowTitle, colTitle, tipFn }) {
    const W = widthOf(container);
    const m = { t: colTitle ? 40 : 24, r: 8, b: 8, l: 8 };
    const labelW = Math.min(130, W * 0.25);
    const cw = (W - m.l - m.r - labelW) / cols.length;
    const ch = Math.max(28, Math.min(46, cw * 0.6));
    const H = m.t + m.b + rows.length * ch;
    const svg = makeSvg(container, W, H);
    if (colTitle) svgEl("text", { class: "lbl", x: m.l + (W - labelW - m.l) / 2, y: 12, "text-anchor": "middle", direction: "rtl" }, svg).textContent = colTitle;
    cols.forEach((c, j) => {
      svgEl("text", { class: "tick", x: m.l + (j + 0.5) * cw, y: m.t - 8, "text-anchor": "middle" }, svg).textContent = c;
    });
    rows.forEach((r, i) => {
      svgEl("text", { class: "lbl", x: W - 4, y: m.t + (i + 0.5) * ch + 4, "text-anchor": "start", direction: "rtl" }, svg).textContent = r;
      cols.forEach((c, j) => {
        const v = values[i][j];
        const g = svgEl("g", { class: "mark" }, svg);
        svgEl("rect", { class: "fill", x: m.l + j * cw + 1, y: m.t + i * ch + 1, width: cw - 2, height: ch - 2, rx: 3, fill: colorFn(v) }, g);
        if (cw > 34) svgEl("text", { class: "cell-txt", x: m.l + (j + 0.5) * cw, y: m.t + (i + 0.5) * ch + 4, "text-anchor": "middle", fill: textFn(v) }, g).textContent = format(v);
        g.addEventListener("pointermove", (ev) => showTip(tipFn ? tipFn(r, c, v) : `${esc(r)} × ${esc(c)}<div class="row"><b>${format(v)}</b></div>`, ev.clientX, ev.clientY));
        g.addEventListener("pointerleave", hideTip);
      });
    });
    if (rowTitle) svg.setAttribute("aria-label", rowTitle);
  }

  // ---------------------------------------------------------------- أعمدة رأسية + خط مرجعي (بنفورد)
  function barsWithLine(container, { labels, bars, line: ref, barName, lineName, height = 260, format = (v) => fmt.pct(v, 1) }) {
    const W = widthOf(container), H = height, m = { t: 12, r: 12, b: 26, l: 48 };
    const svg = makeSvg(container, W, H);
    const yt = niceTicks(0, Math.max(...bars, ...ref), 5);
    const top = yt[yt.length - 1];
    const bw = (W - m.l - m.r) / labels.length;
    const X = (i) => m.l + (i + 0.5) * bw;
    const Y = (v) => H - m.b - (v / top) * (H - m.t - m.b);
    for (const t of yt) {
      svgEl("line", { class: "grid-line", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, svg);
      svgEl("text", { class: "tick", x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg).textContent = format(t);
    }
    labels.forEach((l, i) => {
      const g = svgEl("g", { class: "mark" }, svg);
      svgEl("rect", { class: "bar-hit", x: m.l + i * bw, y: m.t, width: bw, height: H - m.t - m.b }, g);
      svgEl("rect", { class: "fill", x: X(i) - bw * 0.32, y: Y(bars[i]), width: bw * 0.64, height: Math.max(0, H - m.b - Y(bars[i])), rx: 3, fill: "var(--s1)" }, g);
      svgEl("text", { class: "tick", x: X(i), y: H - 8, "text-anchor": "middle" }, svg).textContent = l;
      g.addEventListener("pointermove", (ev) => showTip(`الرقم الأول: ${l}${tipRow("var(--s1)", barName, format(bars[i]))}${tipRow("var(--s2)", lineName, format(ref[i]))}`, ev.clientX, ev.clientY));
      g.addEventListener("pointerleave", hideTip);
    });
    svgEl("line", { class: "base", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }, svg);
    svgEl("path", { class: "series", stroke: "var(--s2)", d: ref.map((v, i) => (i ? "L" : "M") + X(i) + "," + Y(v)).join(""), "pointer-events": "none" }, svg);
    ref.forEach((v, i) => svgEl("circle", { cx: X(i), cy: Y(v), r: 4, fill: "var(--s2)", class: "hover-dot", "pointer-events": "none" }, svg));
  }

  window.Charts = { line, hbar, heatmap, barsWithLine, showTip, hideTip };
})();
