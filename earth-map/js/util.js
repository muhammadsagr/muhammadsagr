/* أدوات مساعدة عامة */
(function () {
  'use strict';
  const EM = (window.EM = window.EM || {});

  const R = 6371008.8; // نصف قطر الأرض بالمتر
  const rad = (d) => (d * Math.PI) / 180;

  const U = {
    $: (sel, root = document) => root.querySelector(sel),
    $$: (sel, root = document) => Array.from(root.querySelectorAll(sel)),

    esc(s) {
      return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },

    /** المسافة بين نقطتين (متر) */
    distance(a, b) {
      const dLat = rad(b.lat - a.lat);
      const dLng = rad(b.lng - a.lng);
      const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
      return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
    },

    pathLength(pts) {
      let d = 0;
      for (let i = 1; i < pts.length; i++) d += U.distance(pts[i - 1], pts[i]);
      return d;
    },

    /** مساحة مضلع على سطح الكرة (متر مربع) */
    polygonArea(pts) {
      if (pts.length < 3) return 0;
      let area = 0;
      for (let i = 0; i < pts.length; i++) {
        const p1 = pts[i];
        const p2 = pts[(i + 1) % pts.length];
        area += rad(p2.lng - p1.lng) * (2 + Math.sin(rad(p1.lat)) + Math.sin(rad(p2.lat)));
      }
      return Math.abs((area * R * R) / 2);
    },

    num(n, digits = 0) {
      return Number(n).toLocaleString('ar-EG', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
    },

    fmtDist(m) {
      if (m == null || isNaN(m)) return '—';
      if (m < 1000) return `${U.num(Math.round(m))} م`;
      return `${U.num(m / 1000, m < 10000 ? 2 : 1)} كم`;
    },

    fmtArea(m2) {
      if (m2 < 10000) return `${U.num(m2, 0)} م²`;
      if (m2 < 1e6) return `${U.num(m2 / 10000, 2)} هكتار`;
      return `${U.num(m2 / 1e6, 2)} كم²`;
    },

    fmtDuration(sec) {
      const m = Math.round(sec / 60);
      if (m < 60) return `${U.num(Math.max(1, m))} دقيقة`;
      const h = Math.floor(m / 60);
      const r = m % 60;
      if (h >= 24) {
        const d = Math.floor(h / 24);
        return `${U.num(d)} يوم ${h % 24 ? `و ${U.num(h % 24)} ساعة` : ''}`;
      }
      return `${U.num(h)} ساعة${r ? ` و ${U.num(r)} دقيقة` : ''}`;
    },

    fmtAlt(m) {
      if (m >= 10000) return `${Math.round(m / 1000).toLocaleString('en')} km`;
      return `${Math.round(m).toLocaleString('en')} m`;
    },

    fmtLatLng(lat, lng, digits = 5) {
      return `${lat.toFixed(digits)}, ${lng.toFixed(digits)}`;
    },

    toDMS(lat, lng) {
      const f = (v, pos, neg) => {
        const a = Math.abs(v);
        const d = Math.floor(a);
        const mf = (a - d) * 60;
        const m = Math.floor(mf);
        const s = ((mf - m) * 60).toFixed(1);
        return `${d}°${String(m).padStart(2, '0')}'${String(s).padStart(4, '0')}"${v >= 0 ? pos : neg}`;
      };
      return `${f(lat, 'N', 'S')} ${f(lng, 'E', 'W')}`;
    },

    /** يحاول قراءة إحداثيات من نص مثل "24.7, 46.6" */
    parseCoords(text) {
      const m = String(text).trim().replace(/،/g, ',').match(/^(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)$/);
      if (!m) return null;
      const lat = parseFloat(m[1]);
      const lng = parseFloat(m[2]);
      if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
      return { lat, lng };
    },

    debounce(fn, ms) {
      let t;
      return (...a) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...a), ms);
      };
    },

    clamp: (v, a, b) => Math.max(a, Math.min(b, v)),

    store: {
      get(key, def) {
        try {
          const v = localStorage.getItem('earthmap.' + key);
          return v == null ? def : JSON.parse(v);
        } catch (e) {
          return def;
        }
      },
      set(key, val) {
        try {
          localStorage.setItem('earthmap.' + key, JSON.stringify(val));
        } catch (e) { /* التخزين غير متاح */ }
      },
    },

    toast(msg, ms = 2600) {
      const el = document.getElementById('toast');
      el.textContent = msg;
      el.classList.add('show');
      clearTimeout(U._toastT);
      U._toastT = setTimeout(() => el.classList.remove('show'), ms);
    },

    async copy(text) {
      try {
        await navigator.clipboard.writeText(text);
        U.toast('تم النسخ ✔');
      } catch (e) {
        prompt('انسخ النص:', text);
      }
    },

    uid: () => Math.random().toString(36).slice(2, 10),
  };

  EM.U = U;
})();
