/* خدمات مجانية مفتوحة المصدر (بدون مفاتيح API):
   - Nominatim (OpenStreetMap): البحث والعناوين
   - OSRM (routing.openstreetmap.de): الاتجاهات
   - Overpass API: الأماكن القريبة
   - Open-Meteo: الطقس والارتفاع
   - Wikipedia: المعالم القريبة */
(function () {
  'use strict';
  const EM = window.EM;

  async function getJSON(url, opts = {}) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  const NOMINATIM = 'https://nominatim.openstreetmap.org';

  const CATEGORIES = {
    restaurant: { label: 'مطاعم', icon: '🍽️', color: '#f97316', q: 'nwr["amenity"~"^(restaurant|fast_food)$"]' },
    cafe: { label: 'مقاهي', icon: '☕', color: '#a16207', q: 'nwr["amenity"="cafe"]' },
    hotel: { label: 'فنادق', icon: '🏨', color: '#db2777', q: 'nwr["tourism"~"^(hotel|motel|guest_house|hostel)$"]' },
    fuel: { label: 'محطات وقود', icon: '⛽', color: '#0891b2', q: 'nwr["amenity"="fuel"]' },
    hospital: { label: 'مستشفيات', icon: '🏥', color: '#dc2626', q: 'nwr["amenity"~"^(hospital|clinic)$"]' },
    pharmacy: { label: 'صيدليات', icon: '💊', color: '#16a34a', q: 'nwr["amenity"="pharmacy"]' },
    mosque: { label: 'مساجد', icon: '🕌', color: '#059669', q: 'nwr["amenity"="place_of_worship"]["religion"="muslim"]' },
    atm: { label: 'صرّاف وبنوك', icon: '🏧', color: '#4f46e5', q: 'nwr["amenity"~"^(atm|bank)$"]' },
    park: { label: 'حدائق', icon: '🌳', color: '#15803d', q: 'nwr["leisure"="park"]' },
    museum: { label: 'متاحف', icon: '🏛️', color: '#7c3aed', q: 'nwr["tourism"="museum"]' },
  };

  const WEATHER = {
    0: ['☀️', 'صحو'], 1: ['🌤️', 'غائم جزئياً'], 2: ['⛅', 'غائم جزئياً'], 3: ['☁️', 'غائم'],
    45: ['🌫️', 'ضباب'], 48: ['🌫️', 'ضباب متجمد'],
    51: ['🌦️', 'رذاذ خفيف'], 53: ['🌦️', 'رذاذ'], 55: ['🌧️', 'رذاذ كثيف'],
    61: ['🌧️', 'مطر خفيف'], 63: ['🌧️', 'مطر'], 65: ['🌧️', 'مطر غزير'],
    66: ['🌧️', 'مطر متجمد'], 67: ['🌧️', 'مطر متجمد غزير'],
    71: ['🌨️', 'ثلج خفيف'], 73: ['🌨️', 'ثلج'], 75: ['❄️', 'ثلج كثيف'], 77: ['🌨️', 'حبيبات ثلج'],
    80: ['🌦️', 'زخات مطر'], 81: ['🌧️', 'زخات مطر'], 82: ['⛈️', 'زخات غزيرة'],
    85: ['🌨️', 'زخات ثلج'], 86: ['🌨️', 'زخات ثلج كثيفة'],
    95: ['⛈️', 'عاصفة رعدية'], 96: ['⛈️', 'عاصفة رعدية مع برد'], 99: ['⛈️', 'عاصفة رعدية مع برد'],
  };

  // أيقونة حسب نوع المكان القادم من Nominatim
  function placeIcon(r) {
    const t = `${r.category || r.class || ''}:${r.type || ''}`;
    if (/country|state|administrative/.test(t)) return '🗺️';
    if (/city|town|village|suburb|hamlet/.test(t)) return '🏙️';
    if (/airport|aerodrome/.test(t)) return '✈️';
    if (/natural|peak|volcano|mountain/.test(t)) return '⛰️';
    if (/water|river|lake|sea|bay/.test(t)) return '🌊';
    if (/tourism|attraction|museum|monument|historic/.test(t)) return '🏛️';
    if (/place_of_worship/.test(t)) return '🕌';
    if (/restaurant|cafe|fast_food/.test(t)) return '🍽️';
    if (/hotel/.test(t)) return '🏨';
    if (/school|university|college/.test(t)) return '🎓';
    if (/hospital|clinic/.test(t)) return '🏥';
    if (/highway|road/.test(t)) return '🛣️';
    if (/building|house/.test(t)) return '🏠';
    return '📍';
  }

  let searchCtl;

  const S = {
    CATEGORIES,

    async search(q, near) {
      if (searchCtl) searchCtl.abort();
      searchCtl = new AbortController();
      const p = new URLSearchParams({ format: 'jsonv2', q, limit: '8', 'accept-language': 'ar,en', addressdetails: '1', extratags: '1' });
      if (near) {
        // تفضيل النتائج القريبة من العرض الحالي (دون حصرها)
        const d = 2;
        p.set('viewbox', `${near.lng - d},${near.lat + d},${near.lng + d},${near.lat - d}`);
      }
      const data = await getJSON(`${NOMINATIM}/search?${p}`, { signal: searchCtl.signal });
      return data.map((r) => ({
        id: 'osm-' + r.osm_type + r.osm_id,
        name: r.name || r.display_name.split(',')[0],
        address: r.display_name,
        lat: +r.lat,
        lng: +r.lon,
        bbox: r.boundingbox ? r.boundingbox.map(Number) : null, // [s, n, w, e]
        icon: placeIcon(r),
        type: r.type,
        wikipedia: r.extratags && r.extratags.wikipedia,
      }));
    },

    async reverse(lat, lng, zoom = 18) {
      const p = new URLSearchParams({ format: 'jsonv2', lat, lon: lng, zoom, 'accept-language': 'ar,en' });
      const r = await getJSON(`${NOMINATIM}/reverse?${p}`);
      if (r.error) return null;
      return { name: r.name || (r.display_name || '').split(',')[0], address: r.display_name, icon: placeIcon(r) };
    },

    async weather(lat, lng) {
      const p = new URLSearchParams({
        latitude: lat.toFixed(4), longitude: lng.toFixed(4),
        current: 'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,is_day',
        timezone: 'auto',
      });
      const r = await getJSON(`https://api.open-meteo.com/v1/forecast?${p}`);
      const c = r.current;
      const [icon, text] = WEATHER[c.weather_code] || ['🌡️', ''];
      return {
        icon: c.is_day === 0 && c.weather_code <= 1 ? '🌙' : icon,
        text, temp: c.temperature_2m, humidity: c.relative_humidity_2m, wind: c.wind_speed_10m,
        timezone: r.timezone, time: c.time,
      };
    },

    async elevation(lat, lng) {
      const r = await getJSON(`https://api.open-meteo.com/v1/elevation?latitude=${lat.toFixed(5)}&longitude=${lng.toFixed(5)}`);
      return r.elevation && r.elevation[0];
    },

    async wikiNearby(lat, lng, radius = 10000) {
      const p = new URLSearchParams({
        action: 'query', format: 'json', origin: '*', generator: 'geosearch',
        ggscoord: `${lat}|${lng}`, ggsradius: String(Math.min(10000, radius)), ggslimit: '8',
        prop: 'coordinates|pageimages|description', piprop: 'thumbnail', pithumbsize: '400',
      });
      const r = await getJSON(`https://ar.wikipedia.org/w/api.php?${p}`);
      const pages = Object.values((r.query && r.query.pages) || {});
      return pages
        .filter((pg) => pg.coordinates)
        .map((pg) => ({
          title: pg.title,
          desc: pg.description || '',
          lat: pg.coordinates[0].lat,
          lng: pg.coordinates[0].lon,
          thumb: pg.thumbnail && pg.thumbnail.source,
          url: `https://ar.wikipedia.org/wiki/${encodeURIComponent(pg.title.replace(/ /g, '_'))}`,
          dist: EM.U.distance({ lat, lng }, { lat: pg.coordinates[0].lat, lng: pg.coordinates[0].lon }),
        }))
        .sort((a, b) => a.dist - b.dist);
    },

    async wikiSummary(tag) {
      // tag مثل "ar:الأهرامات" أو "en:Eiffel Tower"
      const m = String(tag || '').match(/^([a-z-]+):(.+)$/);
      if (!m) return null;
      const r = await getJSON(`https://${m[1]}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(m[2].replace(/ /g, '_'))}`);
      return { extract: r.extract, thumb: r.thumbnail && r.thumbnail.source, url: r.content_urls && r.content_urls.desktop.page };
    },

    async nearby(cat, lat, lng, radius) {
      const c = CATEGORIES[cat];
      const query = `[out:json][timeout:25];${c.q}(around:${Math.round(radius)},${lat},${lng});out center 60;`;
      const endpoints = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'];
      let lastErr;
      for (const ep of endpoints) {
        try {
          const r = await getJSON(ep, { method: 'POST', body: 'data=' + encodeURIComponent(query), headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
          return r.elements
            .map((e) => {
              const t = e.tags || {};
              const plat = e.lat ?? (e.center && e.center.lat);
              const plng = e.lon ?? (e.center && e.center.lon);
              const addr = [t['addr:street'], t['addr:housenumber'], t['addr:city']].filter(Boolean).join('، ');
              return {
                id: 'poi-' + e.type + e.id,
                name: t['name:ar'] || t.name || t['name:en'] || c.label.replace(/ات$|ف$/, ''),
                address: addr,
                lat: plat, lng: plng, icon: c.icon, color: c.color,
                phone: t.phone || t['contact:phone'], website: t.website || t['contact:website'],
                hours: t.opening_hours, cuisine: t.cuisine,
                dist: EM.U.distance({ lat, lng }, { lat: plat, lng: plng }),
              };
            })
            .filter((p) => p.lat != null)
            .sort((a, b) => a.dist - b.dist);
        } catch (e) {
          lastErr = e;
        }
      }
      throw lastErr;
    },

    /** profile: car | foot | bike */
    async route(points, profile = 'car') {
      const coords = points.map((p) => `${p.lng.toFixed(6)},${p.lat.toFixed(6)}`).join(';');
      const url = `https://routing.openstreetmap.de/routed-${profile}/route/v1/driving/${coords}?overview=full&geometries=geojson&steps=true&alternatives=false`;
      const r = await getJSON(url);
      if (r.code !== 'Ok' || !r.routes.length) throw new Error(r.message || 'NoRoute');
      const route = r.routes[0];
      const steps = [];
      route.legs.forEach((leg) => leg.steps.forEach((s) => steps.push(s)));
      return {
        distance: route.distance,
        duration: route.duration,
        line: route.geometry.coordinates.map(([lng, lat]) => ({ lat, lng })),
        steps: steps.map((s) => ({
          text: instruction(s),
          icon: maneuverIcon(s.maneuver),
          distance: s.distance,
          lat: s.maneuver.location[1],
          lng: s.maneuver.location[0],
        })),
      };
    },
  };

  /* ---------- تعليمات الاتجاهات بالعربية ---------- */
  const MOD = {
    left: 'يساراً', right: 'يميناً', 'slight left': 'قليلاً إلى اليسار', 'slight right': 'قليلاً إلى اليمين',
    'sharp left': 'بحدة إلى اليسار', 'sharp right': 'بحدة إلى اليمين', straight: 'للأمام', uturn: 'للخلف',
  };
  const ORD = ['', 'الأول', 'الثاني', 'الثالث', 'الرابع', 'الخامس', 'السادس', 'السابع', 'الثامن'];

  function instruction(s) {
    const m = s.maneuver;
    const mod = MOD[m.modifier] || '';
    const on = s.name ? ` إلى ${s.name}` : '';
    const at = s.name ? ` على ${s.name}` : '';
    switch (m.type) {
      case 'depart': return `انطلق${at}`;
      case 'arrive': return 'وصلت إلى وجهتك 🏁';
      case 'turn': return m.modifier === 'uturn' ? `استدر للخلف${at}` : m.modifier === 'straight' ? `استمر للأمام${at}` : `انعطف ${mod}${on}`;
      case 'new name': case 'continue': return m.modifier && m.modifier !== 'straight' ? `استمر ${mod}${at}` : `استمر${at}`;
      case 'merge': return `اندمج ${mod}${on}`.replace('  ', ' ');
      case 'on ramp': return `اسلك المدخل ${mod}${on}`;
      case 'off ramp': return `اسلك المخرج ${mod}${on}`;
      case 'fork': return `الزم ${/left/.test(m.modifier) ? 'اليسار' : 'اليمين'} عند التفرع${on}`;
      case 'end of road': return `في نهاية الطريق انعطف ${mod}${on}`;
      case 'roundabout': case 'rotary': case 'exit roundabout': case 'exit rotary':
        return m.exit ? `في الدوار اسلك المخرج ${ORD[m.exit] || m.exit}${on}` : `ادخل الدوار${on}`;
      case 'roundabout turn': return `في الدوار انعطف ${mod}${on}`;
      default: return `${mod ? 'اتجه ' + mod : 'استمر'}${on}`;
    }
  }

  function maneuverIcon(m) {
    if (m.type === 'depart') return '🟢';
    if (m.type === 'arrive') return '🏁';
    if (/roundabout|rotary/.test(m.type)) return '🔄';
    const mod = m.modifier || '';
    if (mod === 'uturn') return '↩️';
    if (/left/.test(mod)) return '⬅️';
    if (/right/.test(mod)) return '➡️';
    return '⬆️';
  }

  EM.S = S;
})();
