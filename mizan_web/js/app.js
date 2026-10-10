/* ربط الواجهة: التبويبات، وأدوات التحكم، ورسم كل قسم. */
(function () {
  "use strict";
  const { fmt, esc, SERIES, later } = window.M;
  const $ = (id) => document.getElementById(id);
  const color = (i) => `var(${SERIES[i % SERIES.length]})`;

  // ================================================================ التبويبات
  const tabs = ["prices", "tax", "fraud"];
  const rendered = {};
  function show(name) {
    if (!tabs.includes(name)) name = "prices";
    for (const t of tabs) {
      $("tab-" + t).setAttribute("aria-selected", String(t === name));
      $("view-" + t).hidden = t !== name;
    }
    try { localStorage.setItem("mizan-tab", name); } catch (e) { /* التخزين غير متاح */ }
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    current = name;
    if (!rendered[name]) { rendered[name] = true; RENDER[name](); } else REDRAW[name]();
  }
  let current = "prices";
  tabs.forEach((t) => $("tab-" + t).addEventListener("click", () => show(t)));
  document.querySelector(".tabs").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const i = tabs.indexOf(current), step = e.key === "ArrowLeft" ? 1 : -1;   // في RTL السهم الأيسر = التالي
    const next = tabs[(i + step + tabs.length) % tabs.length];
    show(next); $("tab-" + next).focus();
  });

  // ================================================================ الأسعار
  const P = { data: null, selected: new Set(["ENERGY", "BANK", "TELECOM", "PETCHEM"]), years: 3 };
  function pricesInit() {
    P.data = window.Prices.generate(1);
    const box = $("p-assets");
    window.Prices.UNIVERSE.forEach((a, i) => {
      const lab = document.createElement("label");
      lab.className = "chip";
      lab.innerHTML = `<input type="checkbox" id="asset-${a.id}" ${P.selected.has(a.id) ? "checked" : ""}><span class="sw" style="background:${color(i)}"></span>${esc(a.label)} <span class="muted">${a.id}</span>`;
      lab.querySelector("input").addEventListener("change", (e) => {
        if (e.target.checked) P.selected.add(a.id);
        else if (P.selected.size > 1) P.selected.delete(a.id);
        else e.target.checked = true;                        // أصل واحد على الأقل
        pricesDraw();
      });
      box.appendChild(lab);
    });
    $("p-period").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      P.years = +b.dataset.y;
      $("p-period").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      pricesDraw();
    });
    $("p-window").addEventListener("input", () => pricesDraw());
    pricesDraw();
  }
  function pricesDraw() {
    const { dates, prices } = P.data;
    let start = 0;
    if (P.years) {
      const from = new Date(dates[dates.length - 1]); from.setFullYear(from.getFullYear() - P.years);
      start = dates.findIndex((d) => d >= from);
    }
    const x = dates.slice(start);
    const assets = window.Prices.UNIVERSE.map((a, i) => ({ ...a, i })).filter((a) => P.selected.has(a.id));
    const series = assets.map((a) => ({ ...a, p: prices[a.id].slice(start) }));
    const win = +$("p-window").value;
    $("p-window-out").textContent = win + " يوماً";
    $("p-vol-title").textContent = `التذبذب السنوي المتحرك (${win} يوماً)`;

    // جدول الملخص
    const cls = (v) => (v < 0 ? "neg" : "");
    const rows = series.map((s) => {
      const m = window.Prices.summary(s.p, x);
      return `<tr><td><span class="sw" style="background:${color(s.i)}"></span> ${esc(s.label)} <span class="muted">${s.id}</span></td>
        <td class="num">${fmt.num(m.last, 2)}</td><td class="num ${cls(m.total)}">${fmt.pct(m.total)}</td>
        <td class="num ${cls(m.cagr)}">${fmt.pct(m.cagr)}</td><td class="num">${fmt.pct(m.vol)}</td>
        <td class="num ${cls(m.sharpe)}">${fmt.num(m.sharpe, 2)}</td><td class="num neg">${fmt.pct(m.mdd)}</td>
        <td class="num neg">${fmt.pct(m.worst)}</td><td class="num">${fmt.pct(m.best)}</td></tr>`;
    }).join("");
    $("p-summary").innerHTML = `<thead><tr><th>الأصل</th><th class="num">آخر سعر</th><th class="num">العائد الكلي</th><th class="num">العائد السنوي المركب</th>
      <th class="num">التذبذب السنوي</th><th class="num">نسبة شارب</th><th class="num">أقصى تراجع</th><th class="num">أسوأ يوم</th><th class="num">أفضل يوم</th></tr></thead><tbody>${rows}</tbody>`;
    $("p-legend").innerHTML = series.map((s) => `<li><span class="sw" style="background:${color(s.i)}"></span>${esc(s.label)}</li>`).join("");

    const mk = (fn) => series.map((s) => ({ name: s.label, color: color(s.i), values: fn(s.p) }));
    Charts.line($("p-growth"), { x, series: mk((p) => Array.from(p, (v) => (v / p[0]) * 100)), yFormat: (v) => fmt.num(v, 0), height: 300 });
    Charts.line($("p-dd"), { x, series: mk((p) => window.Prices.drawdown(p)), yFormat: (v) => fmt.pct(v, 0), zero: true, height: 240 });
    Charts.line($("p-vol"), { x, series: mk((p) => window.Prices.rollingVol(window.Prices.returns(p), win)), yFormat: (v) => fmt.pct(v, 0), height: 240 });

    if (series.length < 2) { $("p-corr").innerHTML = '<p class="empty">اختر أصلين على الأقل لعرض الارتباط.</p>'; return; }
    const c = window.Prices.correlation(series.map((s) => s.p));
    const names = series.map((s) => s.label);
    Charts.heatmap($("p-corr"), {
      rows: names, cols: names, values: c, format: (v) => fmt.num(v, 2),
      colorFn: (v) => `color-mix(in srgb, ${v >= 0 ? "var(--s8)" : "var(--s1)"} ${Math.round(Math.abs(v) * 85)}%, var(--surface-2))`,
      textFn: (v) => (Math.abs(v) > 0.55 ? "#ffffff" : "var(--ink)"),
      tipFn: (r, col, v) => `${esc(r)} و ${esc(col)}<div class="row">الارتباط<b>${fmt.num(v, 2)}</b></div>`,
    });
  }

  // ================================================================ التهرب الضريبي
  const T = { pop: null, popKey: "", last: null };
  const taxCtl = {
    "t-rate": (v) => fmt.pct(v, 0), "t-pen": (v) => "× " + fmt.num(v, 2), "t-audit": (v) => fmt.pct(v, 1),
    "t-target": (v) => fmt.pct(v, 0), "t-det": (v) => fmt.pct(v, 0), "t-noise": (v) => fmt.num(v, 2),
    "t-honest": (v) => fmt.pct(v, 0), "t-years": (v) => v + " سنوات",
  };
  function taxPolicy() {
    return { taxRate: +$("t-rate").value, penalty: +$("t-pen").value, auditRate: +$("t-audit").value,
      targeting: +$("t-target").value, detection: +$("t-det").value, signalNoise: +$("t-noise").value };
  }
  function taxPop() {
    const honest = +$("t-honest").value, key = String(honest);
    if (T.popKey !== key) { T.pop = window.Tax.population(5000, honest, 0); T.popKey = key; }
    return T.pop;
  }
  let taxTimer = 0;
  function taxInit() {
    for (const [id, f] of Object.entries(taxCtl)) {
      $(id).addEventListener("input", () => {
        $(id + "-out").textContent = f(+$(id).value);
        clearTimeout(taxTimer); taxTimer = setTimeout(taxRun, 120);
      });
      $(id + "-out").textContent = f(+$(id).value);
    }
    $("t-sweep").addEventListener("click", taxSweep);
    taxRun();
  }
  function kpi(label, value, note = "") {
    return `<div class="kpi"><span class="label">${label}</span><span class="value">${value}</span>${note ? `<span class="note">${note}</span>` : ""}</div>`;
  }
  function taxRun() {
    const policy = taxPolicy(), years = +$("t-years").value;
    T.last = window.Tax.simulate(taxPop(), policy, years, 0);
    // أي تغيير في الإعدادات يجعل مقارنة السيناريوهات القديمة غير صالحة
    if ($("t-heat").dataset.done) { $("t-heat").innerHTML = '<p class="empty">تغيّرت الإعدادات. اضغط «تشغيل 25 سيناريو» لتحديث المقارنة.</p>'; delete $("t-heat").dataset.done; }
    taxDraw();
  }
  function taxDraw() {
    const { yearly, bySector } = T.last, last = yearly[yearly.length - 1], first = yearly[0];
    $("t-kpis").innerHTML =
      kpi("الفجوة الضريبية", fmt.pct(last.taxGap / last.taxDue), `كانت ${fmt.pct(first.taxGap / first.taxDue)} في السنة الأولى`) +
      kpi("نسبة المتهرّبين", fmt.pct(1 - last.compliance, 0), "من يخفي أي جزء من دخله") +
      kpi("نسبة نجاح التدقيق", fmt.pct(last.hitRate, 0), `${fmt.num(last.audits)} ملف مدقق في آخر سنة`) +
      kpi("المُسترد بالغرامات", fmt.money(last.recovered), "الضريبة المتهرَّب منها + الغرامة، آخر سنة");
    Charts.hbar($("t-sector"), bySector.slice().sort((a, b) => b.hidden - a.hidden).map((s) => ({ label: s.name, value: s.hidden })),
      { format: (v) => fmt.pct(v, 0), color: "var(--s1)" });
    Charts.line($("t-gap"), {
      x: yearly.map((r) => r.year), xFormat: (v) => "السنة " + v,
      series: [{ name: "الفجوة الضريبية", color: "var(--s1)", values: yearly.map((r) => r.taxGap / r.taxDue), markers: true }],
      yFormat: (v) => fmt.pct(v, 1), height: 250,
    });
    $("t-table").innerHTML = `<thead><tr><th>السنة</th><th class="num">الفجوة الضريبية</th><th class="num">الدخل المخفي</th><th class="num">نسبة المتهرّبين</th>
      <th class="num">التدقيقات</th><th class="num">نجاح التدقيق</th><th class="num">المُسترد</th><th class="num">احتمال التدقيق المتصوَّر</th></tr></thead><tbody>` +
      yearly.map((r) => `<tr><td>${r.year}</td><td class="num">${fmt.pct(r.taxGap / r.taxDue)}</td><td class="num">${fmt.pct(r.evasionRate)}</td>
        <td class="num">${fmt.pct(1 - r.compliance, 0)}</td><td class="num">${fmt.num(r.audits)}</td><td class="num">${fmt.pct(r.hitRate, 0)}</td>
        <td class="num">${fmt.money(r.recovered)}</td><td class="num">${fmt.pct(r.perceivedAudit, 1)}</td></tr>`).join("") + "</tbody>";
  }
  async function taxSweep() {
    const btn = $("t-sweep"), box = $("t-heat");
    btn.disabled = true; btn.textContent = "جاري الحساب...";
    box.innerHTML = '<p class="empty">جاري تشغيل 25 محاكاة...</p>';
    const audits = [0.01, 0.02, 0.04, 0.07, 0.10], pens = [0.5, 1, 2, 3, 4];
    const grid = await later(() => window.Tax.sweep(taxPop(), taxPolicy(), audits, pens, 5, 0));
    T.sweep = { audits, pens, grid };
    btn.disabled = false; btn.textContent = "تشغيل 25 سيناريو";
    box.dataset.done = "1";
    drawSweep();
  }
  function drawSweep() {
    if (!T.sweep || !$("t-heat").dataset.done) return;
    const { audits, pens, grid } = T.sweep;
    const flat = grid.flat(), lo = Math.min(...flat), hi = Math.max(...flat);
    const best = flat.indexOf(lo);
    const k = (v) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
    Charts.heatmap($("t-heat"), {
      rows: pens.map((p) => "غرامة × " + p), cols: audits.map((a) => fmt.pct(a, 0)), values: grid, colTitle: "نسبة التدقيق السنوية",
      format: (v) => fmt.pct(v, 1),
      colorFn: (v) => `color-mix(in srgb, var(--s1) ${Math.round(15 + k(v) * 80)}%, var(--surface-2))`,
      textFn: (v) => (k(v) > 0.45 ? "#ffffff" : "var(--ink)"),
      tipFn: (r, c, v) => `${esc(r)}، تدقيق ${esc(c)}<div class="row">الفجوة الضريبية<b>${fmt.pct(v, 1)}</b></div>${flat.indexOf(v) === best ? "<div>أقل فجوة بين السيناريوهات</div>" : ""}`,
    });
  }

  // ================================================================ الاحتيال
  const F = { res: null, benford: "legit" };
  let fraudTimer = 0;
  function fraudInit() {
    const outs = { "f-camo": (v) => fmt.num(v, 1), "f-schemes": (v) => String(v) };
    for (const [id, f] of Object.entries(outs)) {
      $(id + "-out").textContent = f(+$(id).value);
      $(id).addEventListener("input", () => { $(id + "-out").textContent = f(+$(id).value); clearTimeout(fraudTimer); fraudTimer = setTimeout(fraudRun, 200); });
    }
    $("f-seed").addEventListener("change", fraudRun);
    $("f-form").addEventListener("submit", (e) => { e.preventDefault(); fraudRun(); });
    $("f-benford").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      F.benford = b.dataset.k;
      $("f-benford").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      drawBenford();
    });
    fraudRun();
  }
  async function fraudRun() {
    $("f-kpis").style.opacity = 0.5;
    const cfg = { ...window.Fraud.DEFAULT, camouflage: +$("f-camo").value, schemes: +$("f-schemes").value };
    const seed = Math.max(0, Math.min(999, Math.round(+$("f-seed").value || 0)));
    F.res = await later(() => window.Fraud.run(cfg, seed));
    $("f-kpis").style.opacity = 1;
    fraudDraw();
  }
  function fraudDraw() {
    const { tx, lab, cycles, results, scores, testSet, weights } = F.res;
    const fraudTx = tx.filter((t) => t.typology).length;
    const fraudAcc = [...lab.values()].filter(Boolean).length;
    $("f-kpis").innerHTML =
      kpi("المعاملات", fmt.num(tx.length)) +
      kpi("معاملات احتيالية", fmt.num(fraudTx), `${fmt.pct(fraudTx / tx.length, 2)} من كل المعاملات`) +
      kpi("حسابات متورطة", fmt.num(fraudAcc), `من ${fmt.num(lab.size)} حساباً`) +
      kpi("دوائر مغلقة مكتشفة", fmt.num(cycles.length), "أموال عادت لمصدرها");

    const T2 = window.Fraud.TYPOLOGIES;
    const meter = (v) => `<span class="meter"><i style="--w:${(v * 100).toFixed(0)}%"></i>${fmt.pct(v, 0)}</span>`;
    const bestF1 = Math.max(...results.map((r) => r.f1));
    $("f-results").innerHTML = `<thead><tr><th>الأداة</th><th class="num">حسابات مُعلَّمة</th><th>الدقة</th><th>الاستدعاء</th><th class="num">F1</th>
      ${Object.values(T2).map((t) => `<th class="num">${t}</th>`).join("")}</tr></thead><tbody>` +
      results.map((r) => `<tr class="${r.f1 === bestF1 ? "row-best" : ""}"><td>${esc(r.name)}</td><td class="num">${r.flagged}</td><td>${meter(r.precision)}</td><td>${meter(r.recall)}</td>
        <td class="num">${fmt.num(r.f1, 2)}</td>${Object.keys(T2).map((k) => `<td class="num">${Number.isFinite(r.byTyp[k]) ? fmt.pct(r.byTyp[k], 0) : "—"}</td>`).join("")}</tr>`).join("") + "</tbody>";

    const w = weights.slice().sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
    Charts.hbar($("f-weights"), w.map((d) => ({ label: d.label, value: d.value })), { format: (v) => fmt.num(v, 2), color: "var(--s2)", negColor: "var(--s1)", rowH: 26 });

    const top = [...testSet].map((a) => [a, scores.get(a)]).sort((a, b) => b[1] - a[1]).slice(0, 15);
    $("f-top").innerHTML = `<thead><tr><th>الحساب</th><th>درجة الاشتباه</th><th>الحقيقة</th><th>النتيجة</th></tr></thead><tbody>` +
      top.map(([a, s]) => {
        const truth = lab.get(a), flagged = s > 0.5;
        const verdict = truth ? (flagged ? '<span class="pill ok">كشف صحيح</span>' : '<span class="pill bad">فاته</span>') : (flagged ? '<span class="pill bad">إنذار كاذب</span>' : '<span class="pill">سليم</span>');
        return `<tr><td>${a}</td><td>${meter(s)}</td><td>${truth ? T2[truth] : "سليم"}</td><td>${verdict}</td></tr>`;
      }).join("") + "</tbody>";

    $("f-cycles-sum").textContent = `الدوائر المغلقة المكتشفة (${cycles.length})`;
    $("f-cycles").innerHTML = `<thead><tr><th>مسار الأموال</th><th class="num">المبلغ</th><th class="num">اليوم</th></tr></thead><tbody>` +
      (cycles.length ? cycles.map((c) => `<tr><td dir="ltr" style="text-align:right">${c.accounts.concat(c.accounts[0]).join(" → ")}</td><td class="num">${fmt.num(c.amount)}</td><td class="num">${c.day}</td></tr>`).join("")
        : '<tr><td colspan="3" class="muted">لم تُكتشف دوائر. ارفع التمويه للصفر لترى الحلقات الصريحة.</td></tr>') + "</tbody>";
    drawBenford();
  }
  function drawBenford() {
    const { tx } = F.res;
    const pick = { legit: (t) => !t.typology, fake_invoice: (t) => t.typology === "fake_invoice", all: () => true }[F.benford];
    const b = window.Fraud.benford(tx.filter(pick).map((t) => t.amount));
    Charts.barsWithLine($("f-benford-chart"), { labels: ["1", "2", "3", "4", "5", "6", "7", "8", "9"], bars: b.observed, line: b.expected, barName: "الملاحظ", lineName: "بنفورد", height: 240 });
    $("f-benford-verdict").innerHTML = `الانحراف المطلق المتوسط (MAD) = <b>${fmt.num(b.mad, 4)}</b> ← <span class="pill ${b.conforms ? "ok" : "bad"}">${b.verdict}</span> حسب معايير Nigrini، على ${fmt.num(b.n)} مبلغ.`;
  }

  // ================================================================ التشغيل وإعادة الرسم
  const RENDER = { prices: pricesInit, tax: taxInit, fraud: fraudInit };
  const REDRAW = { prices: pricesDraw, tax: () => { taxDraw(); drawSweep(); }, fraud: () => F.res && fraudDraw() };
  let resizeTimer = 0, lastW = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastW) return; lastW = window.innerWidth;
    clearTimeout(resizeTimer); resizeTimer = setTimeout(() => REDRAW[current](), 150);
  });
  // إعادة الرسم عند تبديل الوضع الفاتح/الداكن (ألوان النص داخل الخلايا تُحسب عند الرسم)
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => REDRAW[current]());

  window.addEventListener("hashchange", () => { const h = location.hash.slice(1); if (tabs.includes(h) && h !== current) show(h); });

  let start = location.hash.slice(1);
  if (!tabs.includes(start)) { try { start = localStorage.getItem("mizan-tab") || "prices"; } catch (e) { start = "prices"; } }
  show(start);
})();
