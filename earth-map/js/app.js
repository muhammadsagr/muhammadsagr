/* أرض ماب — منطق الواجهة والتفاعل */
(function () {
  'use strict';
  const { U, S, Engines: E } = window.EM;
  const { $, $$, esc } = U;

  /* ===================== الحالة ===================== */
  const state = {
    base: U.store.get('base', 'satellite'),
    labels: U.store.get('labels', true),
    lighting: U.store.get('lighting', false),
    atmosphere: U.store.get('atmosphere', true),
    theme: U.store.get('theme', 'dark'),
    saved: U.store.get('saved', []),
    tool: null, // measure | pickFrom | pickTo
    measure: { pts: [], closed: false },
    route: { from: null, to: null, profile: 'car', result: null },
    myLoc: null,
    activeCat: null,
    placeSeq: 0,
    touring: false,
  };

  /* ===================== المعالم (للجولات) ===================== */
  const LANDMARKS = [
    { name: 'المسجد الحرام', place: 'مكة المكرمة، السعودية', emoji: '🕋', lat: 21.4225, lng: 39.8262, alt: 280, range: 1400, pitch: -35, heading: 20 },
    { name: 'المسجد النبوي', place: 'المدينة المنورة، السعودية', emoji: '🕌', lat: 24.4672, lng: 39.6112, alt: 610, range: 1300, pitch: -35, heading: 0 },
    { name: 'أهرامات الجيزة', place: 'الجيزة، مصر', emoji: '🔺', lat: 29.9773, lng: 31.1325, alt: 60, range: 2200, pitch: -25, heading: 230 },
    { name: 'برج خليفة', place: 'دبي، الإمارات', emoji: '🏙️', lat: 25.1972, lng: 55.2744, alt: 5, range: 2600, pitch: -22, heading: 300 },
    { name: 'البتراء', place: 'معان، الأردن', emoji: '🏜️', lat: 30.3222, lng: 35.4517, alt: 900, range: 2600, pitch: -35, heading: 60 },
    { name: 'قصر الحمراء', place: 'غرناطة، إسبانيا', emoji: '🏰', lat: 37.1761, lng: -3.5881, alt: 760, range: 1600, pitch: -32, heading: 150 },
    { name: 'برج إيفل', place: 'باريس، فرنسا', emoji: '🗼', lat: 48.8584, lng: 2.2945, alt: 35, range: 1500, pitch: -28, heading: 130 },
    { name: 'سور الصين العظيم', place: 'بكين، الصين', emoji: '🧱', lat: 40.4319, lng: 116.5704, alt: 750, range: 2600, pitch: -30, heading: 0 },
    { name: 'جبل إيفرست', place: 'نيبال / التبت', emoji: '🏔️', lat: 27.9881, lng: 86.925, alt: 8848, range: 22000, pitch: -20, heading: 200 },
    { name: 'غراند كانيون', place: 'أريزونا، الولايات المتحدة', emoji: '🏞️', lat: 36.0997, lng: -112.1124, alt: 1400, range: 16000, pitch: -30, heading: 0 },
    { name: 'تمثال المسيح الفادي', place: 'ريو دي جانيرو، البرازيل', emoji: '⛰️', lat: -22.9519, lng: -43.2105, alt: 700, range: 2200, pitch: -25, heading: 180 },
    { name: 'دار أوبرا سيدني', place: 'سيدني، أستراليا', emoji: '🎭', lat: -33.8568, lng: 151.2153, alt: 5, range: 1500, pitch: -28, heading: 40 },
  ];

  /* ===================== اللوحة الجانبية ===================== */
  const panelEl = $('#panel');
  const Panel = {
    stack: [],
    cur: null,
    go(name, arg, push = true) {
      if (this.cur && push) this.stack.push(this.cur);
      if (!push) { /* استبدال */ }
      this.leave(this.cur, name);
      this.cur = { name, arg };
      panelEl.hidden = false;
      document.body.classList.add('panel-open');
      $('#panelBack').hidden = this.stack.length === 0;
      $('#panelBody').scrollTop = 0;
      views[name](arg);
    },
    replace(name, arg) { this.go(name, arg, false); },
    reset() { this.leave(this.cur, null); this.cur = null; this.stack = []; },
    back() {
      const prev = this.stack.pop();
      if (!prev) return this.close();
      this.leave(this.cur, prev.name);
      this.cur = null;
      this.go(prev.name, prev.arg, false);
    },
    refresh() { if (this.cur) views[this.cur.name](this.cur.arg); },
    close() {
      this.leave(this.cur, null);
      this.cur = null;
      this.stack = [];
      panelEl.hidden = true;
      document.body.classList.remove('panel-open');
      ['pin', 'search', 'poi', 'route', 'measure', 'wiki'].forEach((g) => E.clear(g));
      state.route = { from: null, to: null, profile: state.route.profile, result: null };
      state.measure = { pts: [], closed: false };
      setActiveChip(null);
    },
    leave(cur, next) {
      if (!cur) return;
      if (cur.name === 'measure' && next !== 'measure') endTool();
      if (cur.name === 'directions' && next !== 'directions' && /pick/.test(state.tool || '')) endTool();
    },
    title(t) { $('#panelTitle').textContent = t; },
    body(html) { const b = $('#panelBody'); b.innerHTML = html; return b; },
  };
  $('#panelBack').onclick = () => Panel.back();
  $('#panelClose').onclick = () => Panel.close();

  /* ===================== الأدوات (قياس/اختيار نقطة) ===================== */
  function startTool(tool, text) {
    state.tool = tool;
    document.body.classList.add('tool-active');
    $('#toolText').textContent = text;
    $('#toolBanner').hidden = false;
    $('#measureBtn').classList.toggle('on', tool === 'measure');
  }
  function endTool() {
    state.tool = null;
    document.body.classList.remove('tool-active');
    $('#toolBanner').hidden = true;
    $('#measureBtn').classList.remove('on');
  }
  $('#toolDone').onclick = () => {
    const t = state.tool;
    endTool();
    if (t === 'measure') Panel.refresh();
  };

  /* ===================== أحداث الخريطة ===================== */
  const callbacks = {
    onClick(lat, lng) {
      $('#layersPop').hidden = true;
      if (state.tool === 'measure') {
        state.measure.pts.push({ lat, lng });
        drawMeasure();
        if (Panel.cur && Panel.cur.name === 'measure') Panel.refresh();
        return;
      }
      if (state.tool === 'pickFrom' || state.tool === 'pickTo') {
        const key = state.tool === 'pickFrom' ? 'from' : 'to';
        endTool();
        setRoutePoint(key, { lat, lng, label: U.fmtLatLng(lat, lng, 5) }, true);
        return;
      }
      openPlace({ lat, lng, dropped: true });
    },
    onFeatureClick(f) {
      if (f.place) openPlace(f.place, { fly: false });
    },
    onMouseMove(lat, lng) {
      $('#stCoords').textContent = U.fmtLatLng(lat, lng, 5);
    },
    onViewChange: U.debounce(() => { updateStatus(); updateHash(); }, 250),
    onCameraChange: () => updateStatus(),
    onSpinChange(on) { $('#spinBtn').classList.toggle('on', on); },
  };

  function updateStatus() {
    const v = E.getView();
    if (E.mode === '3d') {
      $('#stAlt').textContent = `Alt ${U.fmtAlt(v.height)}`;
      $('#compassIcon').style.transform = `rotate(${-v.heading}deg)`;
      $('#tiltBtn').classList.toggle('on', v.pitch > -75);
    } else {
      $('#stAlt').textContent = `Zoom ${v.zoom.toFixed(1)}`;
      $('#compassIcon').style.transform = '';
    }
  }

  /* ===================== رابط المشاركة (#) ===================== */
  function buildHash(extra = {}) {
    const v = E.getView();
    const p = new URLSearchParams();
    p.set('m', E.mode);
    p.set('c', `${v.lat.toFixed(5)},${v.lng.toFixed(5)},${v.zoom.toFixed(2)}`);
    p.set('l', state.base);
    Object.entries(extra).forEach(([k, val]) => p.set(k, val));
    return '#' + p.toString();
  }
  function updateHash() {
    const cur = new URLSearchParams(location.hash.slice(1));
    const extra = {};
    if (cur.get('p') && Panel.cur && Panel.cur.name === 'place') extra.p = cur.get('p');
    history.replaceState(null, '', buildHash(extra));
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    const out = {};
    if (p.get('m')) out.mode = p.get('m');
    if (p.get('l') && E.BASE_LAYERS[p.get('l')]) out.base = p.get('l');
    const c = (p.get('c') || '').split(',').map(Number);
    if (c.length === 3 && c.every((x) => !isNaN(x))) out.view = { lat: c[0], lng: c[1], zoom: c[2] };
    const pin = (p.get('p') || '').split(',').map(Number);
    if (pin.length === 2 && pin.every((x) => !isNaN(x))) out.pin = { lat: pin[0], lng: pin[1] };
    return out;
  }

  /* ===================== البحث ===================== */
  $('#searchBox').addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = $('#searchInput').value.trim();
    if (!q) return;
    $('#searchInput').blur();
    const coords = U.parseCoords(q);
    if (coords) return openPlace({ ...coords, dropped: true }, { zoom: 15 });
    Panel.reset();
    Panel.go('loading', 'جاري البحث…');
    try {
      const v = E.getView();
      const results = await S.search(q, v.zoom > 8 ? v : null);
      showResults(q, results);
    } catch (err) {
      if (err.name === 'AbortError') return;
      Panel.replace('message', { title: 'تعذّر البحث', text: 'تحقق من الاتصال بالإنترنت ثم حاول مرة أخرى.' });
    }
  });

  function showResults(q, results) {
    E.set('search', results.map((r, i) => ({
      kind: 'point', lat: r.lat, lng: r.lng, icon: r.icon, color: '#ea4335', label: r.name,
      clickable: true, place: r, z: 100 - i,
    })));
    if (results.length === 1) {
      Panel.cur = null;
      return openPlace(results[0]);
    }
    Panel.replace('results', { q, results });
    if (results.length) E.fitPoints(results);
  }

  function flyToPlace(p, zoom) {
    if (p.bbox && !p.dropped) {
      const [s, n, w, e] = p.bbox;
      const big = (n - s) > 0.02 || (e - w) > 0.02;
      if (big) return E.fitBounds(s, n, w, e);
    }
    E.flyTo(p.lat, p.lng, zoom || 16.5);
  }

  /* ===================== بطاقة المكان ===================== */
  function openPlace(p, o = {}) {
    p = { ...p };
    if (o.fly !== false && !p.dropped) flyToPlace(p, o.zoom);
    if (o.fly !== false && p.dropped && o.zoom) E.flyTo(p.lat, p.lng, o.zoom);
    const isListed = p.id && ((E.groups.search || []).some((f) => f.place && f.place.id === p.id) ||
      (E.groups.poi || []).some((f) => f.place && f.place.id === p.id) || isSaved(p));
    if (!isListed) {
      E.set('pin', [{ kind: 'point', lat: p.lat, lng: p.lng, icon: p.icon || '📍', color: '#ea4335', clickable: true, place: p, z: 500 }]);
    } else E.clear('pin');
    history.replaceState(null, '', buildHash({ p: `${p.lat.toFixed(6)},${p.lng.toFixed(6)}` }));
    Panel.go('place', p);
  }

  function isSaved(p) {
    return state.saved.find((s) => Math.abs(s.lat - p.lat) < 1e-6 && Math.abs(s.lng - p.lng) < 1e-6);
  }

  /* ===================== الأماكن المحفوظة ===================== */
  function saveSaved() {
    U.store.set('saved', state.saved);
    E.set('saved', state.saved.map((s) => ({
      kind: 'point', lat: s.lat, lng: s.lng, icon: '⭐', color: '#f9a825', label: s.name, clickable: true, place: s, z: 50, labelFar: 8e5,
    })));
  }

  /* ===================== أماكن قريبة ===================== */
  function setActiveChip(cat) {
    state.activeCat = cat;
    $$('.chip').forEach((c) => c.classList.toggle('active', c.dataset.cat === cat));
  }
  $('#chips').addEventListener('click', async (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    const cat = chip.dataset.cat;
    if (state.activeCat === cat) { setActiveChip(null); E.clear('poi'); Panel.close(); return; }
    const v = E.getView();
    const r = E.viewRadius();
    if (r > 40000) return U.toast('قرّب الخريطة إلى مدينة أو حي للبحث عن الأماكن القريبة 🔍', 3200);
    setActiveChip(cat);
    const radius = U.clamp(r, 400, 8000);
    const c = S.CATEGORIES[cat];
    Panel.reset();
    Panel.go('loading', `${c.icon} البحث عن ${c.label}…`);
    try {
      const list = await S.nearby(cat, v.lat, v.lng, radius);
      if (state.activeCat !== cat) return;
      E.set('poi', list.map((p) => ({ kind: 'point', lat: p.lat, lng: p.lng, icon: p.icon, color: p.color, clickable: true, place: p, label: list.length <= 25 ? p.name : '' })));
      Panel.replace('nearby', { cat, list, radius });
    } catch (err) {
      Panel.replace('message', { title: c.label, text: 'خدمة الأماكن القريبة مشغولة حالياً، حاول بعد قليل.' });
    }
  });

  /* ===================== القياس ===================== */
  function drawMeasure() {
    const { pts, closed } = state.measure;
    const f = pts.map((p) => ({ kind: 'point', style: 'vertex', lat: p.lat, lng: p.lng }));
    if (pts.length >= 2) {
      if (closed && pts.length >= 3) f.unshift({ kind: 'polygon', points: pts, color: '#ff6d00' });
      f.unshift({ kind: 'line', points: closed && pts.length >= 3 ? [...pts, pts[0]] : pts, color: '#ff6d00', width: 3, dashed: true });
    }
    E.set('measure', f);
  }
  function openMeasure() {
    if (Panel.cur && Panel.cur.name === 'measure') return;
    Panel.go('measure');
  }
  $('#measureBtn').onclick = () => {
    if (state.tool === 'measure') { endTool(); Panel.refresh(); }
    else openMeasure();
  };

  /* ===================== الاتجاهات ===================== */
  function setRoutePoint(key, pt, compute) {
    state.route[key] = pt;
    drawRouteEnds();
    if (!Panel.cur || Panel.cur.name !== 'directions') Panel.go('directions');
    else Panel.refresh();
    if (compute) computeRoute();
  }
  function drawRouteEnds(extra = []) {
    const f = [...extra];
    const { from, to } = state.route;
    if (from) f.push({ kind: 'point', lat: from.lat, lng: from.lng, icon: '🟢', color: '#34a853', z: 900 });
    if (to) f.push({ kind: 'point', lat: to.lat, lng: to.lng, icon: '🏁', color: '#ea4335', z: 900 });
    E.set('route', f);
  }
  async function resolveRouteInput(key, text) {
    text = text.trim();
    if (!text) { state.route[key] = null; drawRouteEnds(); return; }
    const c = U.parseCoords(text);
    if (c) return setRoutePoint(key, { ...c, label: text }, true);
    try {
      const v = E.getView();
      const r = await S.search(text, v.zoom > 8 ? v : null);
      if (!r.length) return U.toast('لم يتم العثور على: ' + text);
      setRoutePoint(key, { lat: r[0].lat, lng: r[0].lng, label: r[0].name }, true);
    } catch (e) {
      if (e.name !== 'AbortError') U.toast('تعذّر البحث عن العنوان');
    }
  }
  let routeSeq = 0;
  async function computeRoute() {
    const { from, to, profile } = state.route;
    if (!from || !to) return;
    const seq = ++routeSeq;
    state.route.result = 'loading';
    Panel.cur && Panel.cur.name === 'directions' && Panel.refresh();
    try {
      const r = await S.route([from, to], profile);
      if (seq !== routeSeq) return;
      state.route.result = r;
      const colors = { car: '#1a73e8', foot: '#7c3aed', bike: '#0f9d58' };
      drawRouteEnds([{ kind: 'line', points: r.line, color: colors[profile], width: 6, casing: true }]);
      E.fitPoints(r.line);
    } catch (e) {
      if (seq !== routeSeq) return;
      state.route.result = { error: true };
    }
    if (Panel.cur && Panel.cur.name === 'directions') Panel.refresh();
  }
  $('#directionsBtn').onclick = () => Panel.go('directions');

  /* ===================== موقعي ===================== */
  function locate(cb) {
    if (!navigator.geolocation) return U.toast('المتصفح لا يدعم تحديد الموقع');
    U.toast('جاري تحديد موقعك…');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: lat, longitude: lng, accuracy } = pos.coords;
        state.myLoc = { lat, lng };
        E.set('me', [
          { kind: 'circle', lat, lng, radius: Math.min(accuracy, 5000), color: '#1a73e8' },
          { kind: 'point', style: 'me', lat, lng, z: 1000 },
        ]);
        if (cb) cb(state.myLoc);
        else E.flyTo(lat, lng, 16);
      },
      (err) => U.toast(err.code === 1 ? 'تم رفض إذن الوصول إلى الموقع' : 'تعذّر تحديد موقعك'),
      { enableHighAccuracy: true, timeout: 12000 },
    );
  }
  $('#locateBtn').onclick = () => locate();

  /* ===================== الجولات ===================== */
  async function runTour(startIdx = 0, single = false) {
    if (!E.has3D()) return U.toast('العرض ثلاثي الأبعاد غير مدعوم في هذا المتصفح');
    setMode('3d');
    state.touring = true;
    if (E.g3.spinning) E.g3.setSpin(false);
    if (Panel.cur && Panel.cur.name === 'tour') Panel.refresh();
    for (let i = startIdx; i < LANDMARKS.length && state.touring; i++) {
      const lm = LANDMARKS[i];
      state.tourIdx = i;
      if (Panel.cur && Panel.cur.name === 'tour') Panel.refresh();
      const alt = E.g3.terrainOn || E.g3.buildingsMode === 'google' ? lm.alt : 0;
      E.set('pin', [{ kind: 'point', lat: lm.lat, lng: lm.lng, alt, icon: lm.emoji, color: '#1a73e8', label: lm.name, labelFar: 1e7 }]);
      const ok = await new Promise((resolve) => {
        E.g3.flyTo(lm.lat, lm.lng, 0, {
          alt, range: lm.range, pitch: lm.pitch, heading: lm.heading, duration: 5,
          complete: () => resolve(true), cancel: () => resolve(false),
        });
      });
      if (!ok || !state.touring) break;
      await E.g3.orbitPoint(lm.lat, lm.lng, alt, lm.range, lm.pitch, single ? 9000 : 6500, lm.heading);
      if (single) break;
    }
    state.touring = false;
    state.tourIdx = null;
    if (Panel.cur && Panel.cur.name === 'tour') Panel.refresh();
  }
  function stopTour() {
    state.touring = false;
    if (E.g3) {
      E.g3.orbitStop = true;
      E.g3.viewer.camera.cancelFlight();
    }
  }

  /* ===================== الوضع والطبقات ===================== */
  function setMode(mode) {
    if (mode === E.mode) return;
    if (mode === '3d' && !E.has3D()) return U.toast('العرض ثلاثي الأبعاد (WebGL) غير مدعوم في هذا المتصفح');
    if (mode === '2d') stopTour();
    E.setMode(mode);
    document.body.classList.toggle('mode-2d', mode === '2d');
    document.body.classList.toggle('mode-3d', mode === '3d');
    $$('#modeSwitch button').forEach((b) => b.classList.toggle('on', b.dataset.mode === mode));
    U.store.set('mode', mode);
    updateStatus();
    updateHash();
  }
  $('#modeSwitch').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b) setMode(b.dataset.mode);
  });

  function buildLayersUI() {
    const grid = $('#layersGrid');
    grid.innerHTML = Object.entries(E.BASE_LAYERS).map(([k, l]) => `
      <button class="layer-opt ${k === state.base ? 'on' : ''}" data-layer="${k}">
        <span class="lo-img" style="background-image:url('${E.thumbUrl(l)}')"></span>${esc(l.name)}
      </button>`).join('');
    const alt = state.base === 'satellite' ? 'streets' : 'satellite';
    $('#layersThumb').style.backgroundImage = `url('${E.thumbUrl(E.BASE_LAYERS[state.base] || E.BASE_LAYERS[alt])}')`;
    $('#optLabels').checked = state.labels;
    $('#optLabels').disabled = !E.BASE_LAYERS[state.base].labels;
    $('#optLighting').checked = state.lighting;
    $('#optAtmos').checked = state.atmosphere;
  }
  function setBase(key) {
    state.base = key;
    U.store.set('base', key);
    E.setBase(key, state.labels);
    buildLayersUI();
    updateHash();
  }
  $('#layersBtn').onclick = () => { $('#layersPop').hidden = !$('#layersPop').hidden; };
  $('#layersGrid').addEventListener('click', (e) => {
    const b = e.target.closest('[data-layer]');
    if (b) setBase(b.dataset.layer);
  });
  $('#optLabels').onchange = (e) => { state.labels = e.target.checked; U.store.set('labels', state.labels); E.setBase(state.base, state.labels); };
  $('#optLighting').onchange = (e) => { state.lighting = e.target.checked; U.store.set('lighting', state.lighting); E.g3 && E.g3.setLighting(state.lighting); };
  $('#optAtmos').onchange = (e) => { state.atmosphere = e.target.checked; U.store.set('atmosphere', state.atmosphere); E.g3 && E.g3.setAtmosphere(state.atmosphere); };
  document.addEventListener('pointerdown', (e) => {
    if (!$('#layersPop').hidden && !e.target.closest('#layersWrap')) $('#layersPop').hidden = true;
  });

  /* ===================== أدوات التحكم ===================== */
  $('#zoomIn').onclick = () => E.zoomBy(1);
  $('#zoomOut').onclick = () => E.zoomBy(-1);
  $('#compassBtn').onclick = () => { if (E.mode === '3d') E.g3.resetNorth(); };
  $('#tiltBtn').onclick = () => E.mode === '3d' && E.g3.toggleTilt();
  $('#streetBtn').onclick = () => {
    if (E.mode !== '3d') return;
    if (E.getView().zoom < 10) return U.toast('قرّب الكرة الأرضية من مدينة أولاً ثم جرّب منظر الشارع');
    E.g3.streetLevel();
  };
  $('#spinBtn').onclick = () => E.g3 && E.g3.setSpin(!E.g3.spinning);
  $('#fullscreenBtn').onclick = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
  };

  /* ===================== القائمة ===================== */
  function openDrawer(open) {
    $('#drawer').hidden = !open;
    $('#drawerBackdrop').hidden = !open;
  }
  $('#menuBtn').onclick = () => openDrawer(true);
  $('#drawerBackdrop').onclick = () => openDrawer(false);
  $('#drawer').addEventListener('click', (e) => {
    const b = e.target.closest('[data-open]');
    if (!b) return;
    openDrawer(false);
    const what = b.dataset.open;
    if (what === 'share') return share();
    if (what === 'snapshot') return snapshot();
    if (what === 'measure') return openMeasure();
    Panel.go(what);
  });

  function share(extra) {
    const url = location.href.split('#')[0] + buildHash(extra);
    if (navigator.share && /Mobi/.test(navigator.userAgent)) navigator.share({ title: 'أرض ماب', url }).catch(() => {});
    else U.copy(url);
  }
  function snapshot() {
    if (E.mode !== '3d') {
      setMode('3d');
      return U.toast('تم التبديل إلى وضع الأرض — اضغط "حفظ صورة" مرة أخرى بعد ضبط المنظر', 3500);
    }
    try {
      const a = document.createElement('a');
      a.href = E.g3.snapshot();
      a.download = `earth-${Date.now()}.png`;
      a.click();
    } catch (e) {
      U.toast('تعذّر حفظ الصورة');
    }
  }

  /* ===================== الاختصارات ===================== */
  document.addEventListener('keydown', (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (e.key === 'Escape') {
      if (typing) return document.activeElement.blur();
      if (!$('#drawer').hidden) return openDrawer(false);
      if (!$('#layersPop').hidden) return ($('#layersPop').hidden = true);
      if (state.touring) return stopTour();
      if (state.tool) { const t = state.tool; endTool(); if (t === 'measure') Panel.refresh(); return; }
      if (!panelEl.hidden) return Panel.close();
      return;
    }
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === '/') { e.preventDefault(); $('#searchInput').focus(); }
    else if (k === 'm') setMode(E.mode === '2d' ? '3d' : '2d');
    else if (k === 'l') $('#layersPop').hidden = !$('#layersPop').hidden;
    else if (k === 'n' && E.mode === '3d') E.g3.resetNorth();
    else if (k === 't' && E.mode === '3d') E.g3.toggleTilt();
    else if (k === '+' || k === '=') E.zoomBy(1);
    else if (k === '-') E.zoomBy(-1);
  });

  /* ===================== العروض (محتوى اللوحة) ===================== */
  const views = {
    loading(text) {
      Panel.title(text || 'جاري التحميل…');
      Panel.body('<div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:60%"></div><div class="skeleton" style="width:70%"></div>');
    },

    message({ title, text }) {
      Panel.title(title);
      Panel.body(`<div class="empty">${esc(text)}</div>`);
    },

    results({ q, results }) {
      Panel.title(`نتائج: ${q}`);
      if (!results.length) return Panel.body('<div class="empty">لا توجد نتائج. جرّب كتابة الاسم بطريقة أخرى أو بالإنجليزية.</div>');
      const b = Panel.body(`<div class="list">${results.map((r, i) => `
        <button class="list-item" data-i="${i}">
          <span class="li-icon">${r.icon}</span>
          <span class="li-main"><div class="li-title">${esc(r.name)}</div><div class="li-sub">${esc(r.address)}</div></span>
        </button>`).join('')}</div>`);
      b.querySelectorAll('[data-i]').forEach((el) => (el.onclick = () => openPlace(results[+el.dataset.i])));
    },

    nearby({ cat, list, radius }) {
      const c = S.CATEGORIES[cat];
      Panel.title(`${c.icon} ${c.label} (${U.num(list.length)})`);
      if (!list.length) return Panel.body(`<div class="empty">لا توجد نتائج ضمن ${U.fmtDist(radius)} من مركز الخريطة.<br>جرّب تحريك الخريطة أو تصغيرها قليلاً.</div>`);
      const b = Panel.body(`<div class="list">${list.map((p, i) => `
        <button class="list-item" data-i="${i}">
          <span class="li-icon">${p.icon}</span>
          <span class="li-main"><div class="li-title">${esc(p.name)}</div>
            <div class="li-sub">${esc([p.cuisine, p.address, p.hours].filter(Boolean).join(' · ') || c.label)}</div></span>
          <span class="li-meta">${U.fmtDist(p.dist)}</span>
        </button>`).join('')}</div>`);
      b.querySelectorAll('[data-i]').forEach((el) => (el.onclick = () => openPlace(list[+el.dataset.i], { zoom: 18 })));
    },

    place(p) {
      const seq = ++state.placeSeq;
      const saved = isSaved(p);
      Panel.title(p.name || 'موقع محدد');
      const b = Panel.body(`
        <div class="place-hero" id="plHero">${p.icon || '📍'}</div>
        <div>
          <h3 class="place-title" id="plName">${esc(p.name || 'موقع محدد')}</h3>
          <div class="place-sub" id="plAddr">${p.address ? esc(p.address) : '<div class="skeleton" style="width:85%;margin-top:6px"></div>'}</div>
        </div>
        <div class="btn-row">
          <button class="btn primary" id="plDir">🧭 الاتجاهات</button>
          <button class="btn" id="plSave">${saved ? '★ محفوظ' : '☆ حفظ'}</button>
          <button class="btn" id="pl3d">🌍 عرض 3D</button>
          <button class="btn" id="plShare">🔗 مشاركة</button>
        </div>
        ${saved ? `<div class="field"><label>ملاحظتي</label><textarea class="input" id="plNote" rows="2" placeholder="أضف ملاحظة لهذا المكان…">${esc(saved.note || '')}</textarea></div>` : ''}
        <div id="plWeather" class="weather"><div class="skeleton" style="width:100%"></div></div>
        <dl class="kv">
          <dt>الإحداثيات</dt><dd><a href="#" id="plCopy">${U.fmtLatLng(p.lat, p.lng, 6)}</a></dd>
          <dt>DMS</dt><dd>${U.toDMS(p.lat, p.lng)}</dd>
          <dt>الارتفاع</dt><dd id="plElev">…</dd>
          ${state.myLoc ? `<dt>المسافة منك</dt><dd>${U.fmtDist(U.distance(state.myLoc, p))}</dd>` : ''}
          ${p.phone ? `<dt>الهاتف</dt><dd><a href="tel:${esc(p.phone)}">${esc(p.phone)}</a></dd>` : ''}
          ${p.hours ? `<dt>ساعات العمل</dt><dd>${esc(p.hours)}</dd>` : ''}
          ${p.website ? `<dt>الموقع</dt><dd><a href="${esc(/^https?:/.test(p.website) ? p.website : 'https://' + p.website)}" target="_blank" rel="noopener">${esc(p.website.replace(/^https?:\/\//, ''))}</a></dd>` : ''}
        </dl>
        <div id="plWikiSummary"></div>
        <div><div class="section-title">📚 معالم قريبة (ويكيبيديا)</div><div id="plWiki"><div class="skeleton"></div></div></div>
      `);

      b.querySelector('#plDir').onclick = () => {
        state.route.to = { lat: p.lat, lng: p.lng, label: p.name || U.fmtLatLng(p.lat, p.lng) };
        if (!state.route.from && state.myLoc) state.route.from = { ...state.myLoc, label: 'موقعي' };
        drawRouteEnds();
        Panel.go('directions');
        computeRoute();
      };
      b.querySelector('#plSave').onclick = () => {
        const s = isSaved(p);
        if (s) state.saved = state.saved.filter((x) => x !== s);
        else state.saved.unshift({ id: U.uid(), name: p.name || U.fmtLatLng(p.lat, p.lng, 4), address: p.address || '', lat: p.lat, lng: p.lng, icon: p.icon, note: '', ts: Date.now() });
        saveSaved();
        U.toast(s ? 'تمت الإزالة من المحفوظات' : 'تم الحفظ في أماكني ⭐');
        Panel.refresh();
      };
      b.querySelector('#pl3d').onclick = () => {
        setMode('3d');
        setTimeout(() => E.flyTo(p.lat, p.lng, 16.5, { pitch: -35 }), 80);
      };
      b.querySelector('#plShare').onclick = () => share({ p: `${p.lat.toFixed(6)},${p.lng.toFixed(6)}` });
      b.querySelector('#plCopy').onclick = (e) => { e.preventDefault(); U.copy(U.fmtLatLng(p.lat, p.lng, 6)); };
      const note = b.querySelector('#plNote');
      if (note) note.onchange = () => { saved.note = note.value; saveSaved(); U.toast('تم حفظ الملاحظة'); };

      const alive = () => seq === state.placeSeq && Panel.cur && Panel.cur.name === 'place';

      if (!p.address || !p.name) {
        S.reverse(p.lat, p.lng).then((r) => {
          if (!alive()) return;
          if (!r) { $('#plAddr').textContent = 'منطقة غير معنونة (بحر أو صحراء أو منطقة نائية)'; return; }
          if (!p.name) { p.name = r.name; Panel.title(r.name); $('#plName').textContent = r.name; $('#plHero').textContent = r.icon; }
          p.address = r.address;
          $('#plAddr').textContent = r.address;
        }).catch(() => alive() && ($('#plAddr').textContent = ''));
      }

      S.weather(p.lat, p.lng).then((w) => {
        if (!alive()) return;
        let localTime = '';
        try { localTime = new Date().toLocaleTimeString('ar-EG', { timeZone: w.timezone, hour: '2-digit', minute: '2-digit' }); } catch (e) { /* */ }
        $('#plWeather').innerHTML = `
          <span class="w-icon">${w.icon}</span>
          <div style="flex:1"><div class="w-temp">${U.num(w.temp, 1)}°</div><div class="muted small">${esc(w.text)}</div></div>
          <div class="small muted" style="text-align:left">💧 ${U.num(w.humidity)}٪<br>💨 ${U.num(w.wind, 1)} كم/س${localTime ? `<br>🕒 ${localTime}` : ''}</div>`;
      }).catch(() => alive() && ($('#plWeather').hidden = true));

      S.elevation(p.lat, p.lng).then((h) => alive() && ($('#plElev').textContent = h == null ? '—' : `${Math.round(h).toLocaleString('en')} m`))
        .catch(() => alive() && ($('#plElev').textContent = '—'));

      if (p.wikipedia) {
        S.wikiSummary(p.wikipedia).then((w) => {
          if (!alive() || !w) return;
          if (w.thumb) $('#plHero').innerHTML = `<img src="${esc(w.thumb)}" alt="">`;
          if (w.extract) $('#plWikiSummary').innerHTML = `<div class="section-title">نبذة</div><div class="small" style="line-height:1.8">${esc(w.extract)} ${w.url ? `<a href="${esc(w.url)}" target="_blank" rel="noopener">اقرأ المزيد</a>` : ''}</div>`;
        }).catch(() => {});
      }

      S.wikiNearby(p.lat, p.lng).then((list) => {
        if (!alive()) return;
        const el = $('#plWiki');
        if (!list.length) { el.innerHTML = '<div class="muted small">لا توجد مقالات قريبة.</div>'; return; }
        if (!p.wikipedia && list[0].thumb && list[0].dist < 300) $('#plHero').innerHTML = `<img src="${esc(list[0].thumb)}" alt="">`;
        el.innerHTML = list.slice(0, 6).map((w, i) => `
          <a class="wiki-item" href="${esc(w.url)}" target="_blank" rel="noopener" data-i="${i}">
            ${esc(w.title)} <span>· ${U.fmtDist(w.dist)}${w.desc ? ' · ' + esc(w.desc) : ''}</span></a>`).join('');
        E.set('wiki', list.slice(0, 6).map((w) => ({
          kind: 'point', lat: w.lat, lng: w.lng, icon: '📖', color: '#5f6368', label: w.title, labelFar: 60000, clickable: true,
          place: { lat: w.lat, lng: w.lng, name: w.title, icon: '📖', wikipedia: 'ar:' + w.title },
        })));
      }).catch(() => alive() && ($('#plWiki').innerHTML = '<div class="muted small">تعذّر التحميل.</div>'));
    },

    directions() {
      const r = state.route;
      Panel.title('🧭 الاتجاهات');
      const res = r.result;
      let out = '';
      if (res === 'loading') out = '<div class="skeleton"></div><div class="skeleton" style="width:60%"></div>';
      else if (res && res.error) out = '<div class="empty">تعذّر إيجاد مسار بين النقطتين. تأكد أن النقطتين على اليابسة وقريبتين من طريق.</div>';
      else if (res) {
        out = `
          <div class="route-summary"><span class="big">${U.fmtDuration(res.duration)}</span><span class="muted">(${U.fmtDist(res.distance)})</span></div>
          <div class="steps">${res.steps.map((s, i) => `
            <div class="step" data-i="${i}"><span class="st-ico">${s.icon}</span><span>${esc(s.text)}</span>
            <span class="st-dist">${s.distance ? U.fmtDist(s.distance) : ''}</span></div>`).join('')}</div>`;
      } else out = '<div class="muted small">اختر نقطة البداية والوجهة بالكتابة، أو اضغط 🎯 ثم انقر على الخريطة.</div>';

      const b = Panel.body(`
        <div class="seg" id="rtProfile">
          <button data-p="car" class="${r.profile === 'car' ? 'on' : ''}">🚗 سيارة</button>
          <button data-p="foot" class="${r.profile === 'foot' ? 'on' : ''}">🚶 مشي</button>
          <button data-p="bike" class="${r.profile === 'bike' ? 'on' : ''}">🚲 دراجة</button>
        </div>
        <div class="route-inputs">
          <span class="route-dot a"></span>
          <input class="input" id="rtFrom" placeholder="نقطة البداية" value="${esc(r.from ? r.from.label : '')}">
          <span class="btn-row" style="flex-wrap:nowrap;gap:4px">
            <button class="icon-btn" id="rtMe" title="موقعي">📍</button>
            <button class="icon-btn ${state.tool === 'pickFrom' ? 'accent' : ''}" id="rtPickFrom" title="اختر من الخريطة">🎯</button>
          </span>
          <span class="route-dot b"></span>
          <input class="input" id="rtTo" placeholder="الوجهة" value="${esc(r.to ? r.to.label : '')}">
          <span class="btn-row" style="flex-wrap:nowrap;gap:4px">
            <button class="icon-btn" id="rtSwap" title="تبديل">⇅</button>
            <button class="icon-btn ${state.tool === 'pickTo' ? 'accent' : ''}" id="rtPickTo" title="اختر من الخريطة">🎯</button>
          </span>
        </div>
        ${out}`);

      b.querySelector('#rtProfile').onclick = (e) => {
        const btn = e.target.closest('[data-p]');
        if (!btn) return;
        r.profile = btn.dataset.p;
        Panel.refresh();
        computeRoute();
      };
      const bindInput = (id, key) => {
        const el = b.querySelector(id);
        el.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); resolveRouteInput(key, el.value); } });
        el.addEventListener('change', () => { if (el.value !== (r[key] ? r[key].label : '')) resolveRouteInput(key, el.value); });
      };
      bindInput('#rtFrom', 'from');
      bindInput('#rtTo', 'to');
      b.querySelector('#rtMe').onclick = () => locate((loc) => setRoutePoint('from', { ...loc, label: 'موقعي' }, true));
      b.querySelector('#rtPickFrom').onclick = () => { startTool('pickFrom', '🎯 انقر على الخريطة لتحديد نقطة البداية'); Panel.refresh(); };
      b.querySelector('#rtPickTo').onclick = () => { startTool('pickTo', '🎯 انقر على الخريطة لتحديد الوجهة'); Panel.refresh(); };
      b.querySelector('#rtSwap').onclick = () => {
        [r.from, r.to] = [r.to, r.from];
        drawRouteEnds();
        Panel.refresh();
        computeRoute();
      };
      b.querySelectorAll('.step').forEach((el) => (el.onclick = () => {
        const s = res.steps[+el.dataset.i];
        E.flyTo(s.lat, s.lng, 18, { pitch: -50 });
      }));
    },

    measure() {
      if (state.tool !== 'measure' && !state.measure.pts.length) startTool('measure', '📏 انقر على الخريطة لإضافة نقاط القياس');
      const { pts, closed } = state.measure;
      Panel.title('📏 قياس المسافة والمساحة');
      const dist = U.pathLength(closed && pts.length >= 3 ? [...pts, pts[0]] : pts);
      const area = closed ? U.polygonArea(pts) : 0;
      const b = Panel.body(`
        <div class="measure-out">
          <div class="stat"><div class="s-label">${closed ? 'المحيط' : 'المسافة الإجمالية'}</div><div class="s-val">${U.fmtDist(dist)}</div></div>
          <div class="stat"><div class="s-label">المساحة</div><div class="s-val">${closed && pts.length >= 3 ? U.fmtArea(area) : '—'}</div></div>
        </div>
        <div class="muted small">عدد النقاط: ${U.num(pts.length)} ${state.tool === 'measure' ? '— انقر على الخريطة لإضافة المزيد' : ''}</div>
        <label class="switch"><input type="checkbox" id="msClosed" ${closed ? 'checked' : ''}><span></span> إغلاق الشكل لحساب المساحة</label>
        <div class="btn-row">
          <button class="btn" id="msToggle">${state.tool === 'measure' ? '⏸ إيقاف الإضافة' : '✏️ متابعة الرسم'}</button>
          <button class="btn" id="msUndo" ${pts.length ? '' : 'disabled'}>↶ تراجع</button>
          <button class="btn danger" id="msClear" ${pts.length ? '' : 'disabled'}>🗑 مسح</button>
        </div>`);
      b.querySelector('#msClosed').onchange = (e) => { state.measure.closed = e.target.checked; drawMeasure(); Panel.refresh(); };
      b.querySelector('#msUndo').onclick = () => { pts.pop(); drawMeasure(); Panel.refresh(); };
      b.querySelector('#msClear').onclick = () => { state.measure.pts = []; drawMeasure(); startTool('measure', '📏 انقر على الخريطة لإضافة نقاط القياس'); Panel.refresh(); };
      b.querySelector('#msToggle').onclick = () => {
        if (state.tool === 'measure') endTool();
        else startTool('measure', '📏 انقر على الخريطة لإضافة نقاط القياس');
        Panel.refresh();
      };
    },

    saved() {
      Panel.title(`⭐ أماكني المحفوظة (${U.num(state.saved.length)})`);
      if (!state.saved.length) return Panel.body('<div class="empty">لا توجد أماكن محفوظة بعد.<br>انقر على أي مكان في الخريطة ثم اضغط "☆ حفظ".</div>');
      const b = Panel.body(`
        <div class="btn-row"><button class="btn small" id="svShowAll">🗺️ عرض الكل</button><button class="btn small" id="svExport">⬇️ تصدير GeoJSON</button></div>
        <div class="list" style="margin-top:0">${state.saved.map((s, i) => `
        <button class="list-item" data-i="${i}">
          <span class="li-icon">⭐</span>
          <span class="li-main"><div class="li-title">${esc(s.name)}</div><div class="li-sub">${esc(s.note || s.address || U.fmtLatLng(s.lat, s.lng, 4))}</div></span>
          <span class="li-meta">${state.myLoc ? U.fmtDist(U.distance(state.myLoc, s)) : ''}</span>
        </button>`).join('')}</div>`);
      b.querySelectorAll('[data-i]').forEach((el) => (el.onclick = () => openPlace(state.saved[+el.dataset.i], { zoom: 17 })));
      b.querySelector('#svShowAll').onclick = () => E.fitPoints(state.saved);
      b.querySelector('#svExport').onclick = () => {
        const gj = {
          type: 'FeatureCollection',
          features: state.saved.map((s) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [s.lng, s.lat] }, properties: { name: s.name, address: s.address, note: s.note } })),
        };
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([JSON.stringify(gj, null, 2)], { type: 'application/geo+json' }));
        a.download = 'my-places.geojson';
        a.click();
      };
    },

    tour() {
      Panel.title('✈️ جولات حول العالم');
      const b = Panel.body(`
        <div class="btn-row">
          ${state.touring
            ? '<button class="btn danger" id="trStop">⏹ إيقاف الجولة</button>'
            : '<button class="btn primary" id="trAll">▶ ابدأ الجولة الكاملة</button>'}
        </div>
        <div class="muted small">تنقلك الجولة بين أشهر معالم العالم على الكرة الأرضية ثلاثية الأبعاد مع دوران سينمائي حول كل معلم. ${E.g3 && E.g3.buildingsMode === 'google' ? '' : 'لتجربة أكثر واقعية فعّل المباني ثلاثية الأبعاد من الإعدادات.'}</div>
        <div class="list" style="margin-top:0">${LANDMARKS.map((l, i) => `
          <button class="list-item" data-i="${i}" ${state.tourIdx === i ? 'style="background:var(--card-2)"' : ''}>
            <span class="tour-card"><span class="t-emoji">${l.emoji}</span></span>
            <span class="li-main"><div class="li-title">${esc(l.name)} ${state.tourIdx === i ? '◀' : ''}</div><div class="li-sub">${esc(l.place)}</div></span>
          </button>`).join('')}</div>`);
      const all = b.querySelector('#trAll');
      if (all) all.onclick = () => runTour(0);
      const stop = b.querySelector('#trStop');
      if (stop) stop.onclick = () => { stopTour(); setTimeout(() => Panel.refresh(), 50); };
      b.querySelectorAll('[data-i]').forEach((el) => (el.onclick = () => {
        stopTour();
        setTimeout(() => runTour(+el.dataset.i, true), 60);
      }));
    },

    settings() {
      Panel.title('⚙️ الإعدادات');
      const token = U.store.get('ionToken', '');
      const g = E.g3;
      const b = Panel.body(`
        <div class="field">
          <label>المظهر</label>
          <div class="seg" id="stTheme">
            <button data-t="dark" class="${state.theme === 'dark' ? 'on' : ''}">🌙 داكن</button>
            <button data-t="light" class="${state.theme === 'light' ? 'on' : ''}">☀️ فاتح</button>
          </div>
        </div>
        <hr style="border:0;border-top:1px solid var(--line);width:100%;margin:0">
        <div>
          <div class="section-title">🏔️ تضاريس ومبانٍ ثلاثية الأبعاد</div>
          <div class="muted small" style="line-height:1.8">
            تعمل الكرة الأرضية بدون أي مفتاح. لتفعيل <b>التضاريس الحقيقية (الجبال والوديان)</b> و<b>المباني ثلاثية الأبعاد الواقعية</b>
            أنشئ مفتاحاً مجانياً من <a href="https://ion.cesium.com/signup" target="_blank" rel="noopener">Cesium ion</a> والصقه هنا.
          </div>
        </div>
        <div class="field">
          <label for="stToken">مفتاح Cesium ion</label>
          <input class="input" id="stToken" dir="ltr" placeholder="eyJhbGciOi..." value="${esc(token)}">
          <div class="btn-row"><button class="btn small primary" id="stSaveToken">حفظ المفتاح</button>${token ? '<button class="btn small danger" id="stDelToken">حذف</button>' : ''}</div>
        </div>
        <label class="switch"><input type="checkbox" id="stTerrain" ${g && g.terrainOn ? 'checked' : ''} ${token && g ? '' : 'disabled'}><span></span> التضاريس ثلاثية الأبعاد</label>
        <div class="field">
          <label>المباني ثلاثية الأبعاد</label>
          <select class="input" id="stBuildings" ${token && g ? '' : 'disabled'}>
            <option value="none" ${!g || g.buildingsMode === 'none' ? 'selected' : ''}>بدون</option>
            <option value="osm" ${g && g.buildingsMode === 'osm' ? 'selected' : ''}>مباني OpenStreetMap (مجسمات)</option>
            <option value="google" ${g && g.buildingsMode === 'google' ? 'selected' : ''}>مدن واقعية ثلاثية الأبعاد (Google Photorealistic)</option>
          </select>
        </div>
        <hr style="border:0;border-top:1px solid var(--line);width:100%;margin:0">
        <button class="btn danger" id="stReset">🗑 حذف جميع البيانات المحفوظة</button>
      `);
      b.querySelector('#stTheme').onclick = (e) => {
        const t = e.target.closest('[data-t]');
        if (!t) return;
        state.theme = t.dataset.t;
        U.store.set('theme', state.theme);
        document.documentElement.dataset.theme = state.theme;
        Panel.refresh();
      };
      b.querySelector('#stSaveToken').onclick = () => {
        const v = b.querySelector('#stToken').value.trim();
        U.store.set('ionToken', v);
        if (g) g.setToken(v);
        U.toast(v ? 'تم حفظ المفتاح ✔ يمكنك الآن تفعيل التضاريس والمباني' : 'تم الحفظ');
        Panel.refresh();
      };
      const del = b.querySelector('#stDelToken');
      if (del) del.onclick = async () => {
        U.store.set('ionToken', '');
        U.store.set('terrain', false);
        U.store.set('buildings', 'none');
        if (g) { g.setToken(''); await g.setTerrain(false); await g.setBuildings('none'); }
        Panel.refresh();
      };
      b.querySelector('#stTerrain').onchange = async (e) => {
        const on = e.target.checked;
        try {
          await g.setTerrain(on);
          U.store.set('terrain', on);
          if (on) { setMode('3d'); U.toast('تم تفعيل التضاريس — جرّب الإمالة (3D) فوق منطقة جبلية ⛰️', 3500); }
        } catch (err) {
          e.target.checked = false;
          U.toast('تعذّر تحميل التضاريس — تحقق من صحة المفتاح');
        }
      };
      b.querySelector('#stBuildings').onchange = async (e) => {
        const mode = e.target.value;
        U.toast('جاري التحميل…');
        try {
          await g.setBuildings(mode);
          U.store.set('buildings', mode);
          if (mode !== 'none') { setMode('3d'); U.toast('تم التفعيل — قرّب إلى مدينة كبيرة وأمِل المنظر 🏙️', 3500); }
        } catch (err) {
          e.target.value = 'none';
          await g.setBuildings('none');
          U.toast('تعذّر تحميل المباني — تحقق من المفتاح وصلاحيات الأصول في حسابك', 4000);
        }
      };
      b.querySelector('#stReset').onclick = () => {
        if (!confirm('سيتم حذف الأماكن المحفوظة والإعدادات. متابعة؟')) return;
        Object.keys(localStorage).filter((k) => k.startsWith('earthmap.')).forEach((k) => localStorage.removeItem(k));
        location.hash = '';
        location.reload();
      };
    },

    help() {
      Panel.title('⌨️ التحكم والاختصارات');
      Panel.body(`
        <div><div class="section-title">🌍 الكرة الأرضية (3D)</div>
        <dl class="kv" style="direction:rtl">
          <dt>سحب بالزر الأيسر</dt><dd style="direction:rtl;text-align:start">تحريك الكرة</dd>
          <dt>عجلة الفأرة</dt><dd style="direction:rtl;text-align:start">تكبير / تصغير</dd>
          <dt>سحب بالزر الأيمن</dt><dd style="direction:rtl;text-align:start">تكبير سلس</dd>
          <dt>Ctrl + سحب / الزر الأوسط</dt><dd style="direction:rtl;text-align:start">إمالة وتدوير المنظر</dd>
          <dt>إصبعان (هاتف)</dt><dd style="direction:rtl;text-align:start">تكبير وإمالة وتدوير</dd>
        </dl></div>
        <div><div class="section-title">⌨️ لوحة المفاتيح</div>
        <dl class="kv" style="direction:rtl">
          <dt><kbd>/</kbd></dt><dd style="direction:rtl;text-align:start">البحث</dd>
          <dt><kbd>M</kbd></dt><dd style="direction:rtl;text-align:start">التبديل بين الخريطة والأرض</dd>
          <dt><kbd>L</kbd></dt><dd style="direction:rtl;text-align:start">الطبقات</dd>
          <dt><kbd>N</kbd></dt><dd style="direction:rtl;text-align:start">توجيه الشمال للأعلى</dd>
          <dt><kbd>T</kbd></dt><dd style="direction:rtl;text-align:start">إمالة المنظر</dd>
          <dt><kbd>+</kbd> / <kbd>-</kbd></dt><dd style="direction:rtl;text-align:start">تكبير / تصغير</dd>
          <dt><kbd>Esc</kbd></dt><dd style="direction:rtl;text-align:start">إغلاق / إلغاء</dd>
        </dl></div>
        <div class="muted small" style="line-height:1.8">💡 يمكنك كتابة إحداثيات في البحث مثل <b dir="ltr">24.7136, 46.6753</b>.<br>
        البيانات من OpenStreetMap و Esri و Open-Meteo و ويكيبيديا.</div>`);
    },
  };

  /* ===================== التشغيل ===================== */
  function boot() {
    document.documentElement.dataset.theme = state.theme;
    if (!window.L) {
      $('#splash .splash-sub').textContent = 'تعذّر تحميل مكتبات الخرائط — تحقق من اتصالك بالإنترنت ثم أعد تحميل الصفحة.';
      return;
    }
    E.init(callbacks);
    const h = readHash();
    if (h.base) state.base = h.base;
    E.setBase(state.base, state.labels);
    buildLayersUI();

    if (E.g3) {
      E.g3.setLighting(state.lighting);
      E.g3.setAtmosphere(state.atmosphere);
      const token = U.store.get('ionToken', '');
      if (token) {
        if (U.store.get('terrain', false)) E.g3.setTerrain(true).catch(() => U.store.set('terrain', false));
        const bm = U.store.get('buildings', 'none');
        if (bm !== 'none') E.g3.setBuildings(bm).catch(() => U.store.set('buildings', 'none'));
      }
    } else {
      $('#modeSwitch [data-mode="3d"]').disabled = true;
      $('#modeSwitch [data-mode="3d"]').title = 'المتصفح لا يدعم WebGL';
    }

    const mode = h.mode || U.store.get('mode', E.g3 ? '3d' : '2d');
    const startMode = mode === '3d' && E.g3 ? '3d' : '2d';
    E.mode = startMode;
    E.setMode(startMode, false);
    document.body.classList.toggle('mode-2d', startMode === '2d');
    document.body.classList.toggle('mode-3d', startMode === '3d');
    $$('#modeSwitch button').forEach((b) => b.classList.toggle('on', b.dataset.mode === startMode));

    if (h.view) E.active.setView(h.view);
    else if (startMode === '3d') E.g3.setSpin(true);

    saveSaved();
    if (h.pin) openPlace({ ...h.pin, dropped: true }, { fly: !h.view, zoom: 16 });
    updateStatus();

    setTimeout(() => $('#splash').classList.add('gone'), 700);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
