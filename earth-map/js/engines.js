/* محركا العرض:
   - Map2D  : خريطة ثنائية الأبعاد (Leaflet) — تجربة شبيهة بخرائط الطرق
   - Globe3D: كرة أرضية ثلاثية الأبعاد (CesiumJS) — تجربة شبيهة ببرامج الكرة الأرضية
   - Overlays: طبقة بيانات موحّدة تُرسم في المحركين معاً
   - Engines: واجهة موحّدة يستخدمها التطبيق دون أن يهتم بالمحرك النشط */
(function () {
  'use strict';
  const EM = window.EM;
  const U = EM.U;

  /* ===================== الخرائط الأساسية ===================== */
  const BASE_LAYERS = {
    streets: {
      name: 'خريطة الطرق',
      url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
      subdomains: 'abcd', maxNative: 20,
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    },
    satellite: {
      name: 'قمر صناعي',
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      maxNative: 19, labels: true,
      attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    },
    terrain: {
      name: 'التضاريس',
      url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
      subdomains: 'abc', maxNative: 17,
      attribution: '&copy; OpenStreetMap, SRTM | &copy; OpenTopoMap (CC-BY-SA)',
    },
    osm: {
      name: 'OpenStreetMap',
      url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      maxNative: 19,
      attribution: '&copy; OpenStreetMap contributors',
    },
    dark: {
      name: 'ليلي',
      url: 'https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png',
      subdomains: 'abcd', maxNative: 20,
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    },
    light: {
      name: 'فاتح',
      url: 'https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}.png',
      subdomains: 'abcd', maxNative: 20,
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    },
  };
  const LABELS = {
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/dark_only_labels/{z}/{x}/{y}.png',
    subdomains: 'abcd', maxNative: 20,
  };

  function thumbUrl(layer) {
    // بلاطة صغيرة تمثل الطبقة (منطقة الشرق الأوسط)
    return layer.url.replace('{s}', 'a').replace('{z}', '5').replace('{x}', '20').replace('{y}', '13');
  }

  /* ===================== تحويل التكبير ↔ الارتفاع ===================== */
  const TAN30 = Math.tan(Math.PI / 6);
  function zoomToHeight(zoom, lat) {
    const w = window.innerWidth || 1200;
    const mpp = (156543.034 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, zoom);
    return Math.max(30, (mpp * w) / 2 / TAN30);
  }
  function heightToZoom(h, lat) {
    const w = window.innerWidth || 1200;
    const mpp = (h * TAN30 * 2) / w;
    const z = Math.log2((156543.034 * Math.max(0.05, Math.cos((lat * Math.PI) / 180))) / mpp);
    return U.clamp(z, 2, 20);
  }

  /* ===================== رسم الدبوس (للكرة الأرضية) ===================== */
  const pinCache = new Map();
  function pinCanvas(color, glyph) {
    const key = color + glyph;
    if (pinCache.has(key)) return pinCache.get(key);
    const s = 2; // دقة عالية
    const W = 40 * s, H = 52 * s;
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    const g = c.getContext('2d');
    const cx = W / 2, cy = 19 * s, r = 17 * s;
    g.shadowColor = 'rgba(0,0,0,.45)'; g.shadowBlur = 5 * s; g.shadowOffsetY = 2 * s;
    g.beginPath();
    g.moveTo(cx, H - 2 * s);
    g.bezierCurveTo(cx - 4 * s, cy + r * 0.9, cx - r, cy + r * 0.55, cx - r, cy);
    g.arc(cx, cy, r, Math.PI, 0);
    g.bezierCurveTo(cx + r, cy + r * 0.55, cx + 4 * s, cy + r * 0.9, cx, H - 2 * s);
    g.closePath();
    g.fillStyle = color; g.fill();
    g.shadowColor = 'transparent';
    g.lineWidth = 2.5 * s; g.strokeStyle = '#fff'; g.stroke();
    g.font = `${16 * s}px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif`;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(glyph || '', cx, cy + 1 * s);
    pinCache.set(key, c);
    return c;
  }
  function dotCanvas(fill, stroke, size) {
    const key = 'dot' + fill + stroke + size;
    if (pinCache.has(key)) return pinCache.get(key);
    const c = document.createElement('canvas');
    c.width = c.height = size * 2 + 8;
    const g = c.getContext('2d');
    g.beginPath(); g.arc(c.width / 2, c.height / 2, size, 0, Math.PI * 2);
    g.fillStyle = fill; g.fill(); g.lineWidth = 5; g.strokeStyle = stroke; g.stroke();
    pinCache.set(key, c);
    return c;
  }

  /* ===================== المحرك ثنائي الأبعاد ===================== */
  class Map2D {
    constructor(el, cb) {
      this.cb = cb;
      this.map = L.map(el, {
        zoomControl: false, worldCopyJump: true, minZoom: 2, maxZoom: 20,
        zoomSnap: 0.25, wheelPxPerZoomLevel: 90, center: [25, 45], zoom: 4,
      });
      this.map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank">Leaflet</a>');
      L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(this.map);
      this.groups = {};
      this.map.on('click', (e) => cb.onClick(e.latlng.lat, wrapLng(e.latlng.lng)));
      this.map.on('mousemove', (e) => cb.onMouseMove(e.latlng.lat, wrapLng(e.latlng.lng)));
      this.map.on('moveend', () => cb.onViewChange());
    }

    setBase(key, labels) {
      const b = BASE_LAYERS[key];
      if (this.base) this.map.removeLayer(this.base);
      if (this.labels) this.map.removeLayer(this.labels);
      this.base = L.tileLayer(b.url, {
        subdomains: b.subdomains || 'abc', maxNativeZoom: b.maxNative, maxZoom: 20,
        attribution: b.attribution, crossOrigin: true,
      }).addTo(this.map);
      this.labels = null;
      if (b.labels && labels) {
        if (!this.map.getPane('labels')) {
          this.map.createPane('labels');
          this.map.getPane('labels').style.zIndex = 450;
          this.map.getPane('labels').style.pointerEvents = 'none';
        }
        this.labels = L.tileLayer(LABELS.url, { subdomains: LABELS.subdomains, maxNativeZoom: LABELS.maxNative, maxZoom: 20, pane: 'labels' }).addTo(this.map);
      }
      this.base.bringToBack();
    }

    getView() {
      const c = this.map.getCenter();
      return { lat: c.lat, lng: wrapLng(c.lng), zoom: this.map.getZoom(), heading: 0 };
    }
    setView(v, animate) {
      this.map.setView([v.lat, v.lng], U.clamp(v.zoom, 2, 20), { animate: !!animate });
    }
    flyTo(lat, lng, zoom) {
      this.map.flyTo([lat, lng], zoom, { duration: 1.4 });
    }
    fitBounds(s, n, w, e) {
      this.map.flyToBounds([[s, w], [n, e]], { padding: [40, 40], maxZoom: 17, duration: 1.4 });
    }
    zoomBy(d) { this.map.setZoom(this.map.getZoom() + d); }
    resize() { this.map.invalidateSize(false); }
    viewRadius() {
      const b = this.map.getBounds();
      return U.distance({ lat: b.getNorth(), lng: b.getCenter().lng }, { lat: b.getCenter().lat, lng: b.getCenter().lng });
    }

    setGroup(name, features) {
      if (this.groups[name]) this.map.removeLayer(this.groups[name]);
      const grp = L.layerGroup();
      features.forEach((f) => {
        let layer;
        if (f.kind === 'point') {
          let html, size, anchor;
          if (f.style === 'me') { html = '<div class="me-dot"></div>'; size = [24, 24]; anchor = [12, 12]; }
          else if (f.style === 'vertex') { html = '<div class="vertex"></div>'; size = [18, 18]; anchor = [9, 9]; }
          else {
            html = `<div class="pin" style="background:${f.color || '#ea4335'}"><span>${U.esc(f.icon || '')}</span></div>` +
              (f.label ? `<div class="pin-label">${U.esc(f.label)}</div>` : '');
            size = [34, 34]; anchor = [17, 41];
          }
          layer = L.marker([f.lat, f.lng], {
            icon: L.divIcon({ className: 'pin-wrap', html, iconSize: size, iconAnchor: anchor }),
            interactive: !!f.clickable, keyboard: false, zIndexOffset: f.z || 0, title: f.label || '',
          });
          if (f.clickable) layer.on('click', () => this.cb.onFeatureClick(f));
        } else if (f.kind === 'line') {
          const ll = f.points.map((p) => [p.lat, p.lng]);
          if (f.casing) L.polyline(ll, { color: '#fff', weight: (f.width || 5) + 4, opacity: 0.9, interactive: false }).addTo(grp);
          layer = L.polyline(ll, { color: f.color, weight: f.width || 4, dashArray: f.dashed ? '8 8' : null, interactive: false });
        } else if (f.kind === 'polygon') {
          layer = L.polygon(f.points.map((p) => [p.lat, p.lng]), { color: f.color, weight: 2, fillOpacity: 0.2, interactive: false });
        } else if (f.kind === 'circle') {
          layer = L.circle([f.lat, f.lng], { radius: f.radius, color: f.color, weight: 1, fillOpacity: 0.12, interactive: false });
        }
        if (layer) layer.addTo(grp);
      });
      grp.addTo(this.map);
      this.groups[name] = grp;
    }
  }

  function wrapLng(lng) {
    return ((((lng + 180) % 360) + 360) % 360) - 180;
  }

  /* ===================== المحرك ثلاثي الأبعاد ===================== */
  class Globe3D {
    constructor(el, cb) {
      const C = window.Cesium;
      this.C = C;
      this.cb = cb;
      C.Ion.defaultAccessToken = U.store.get('ionToken', '') || '';
      const v = (this.viewer = new C.Viewer(el, {
        baseLayer: false, animation: false, timeline: false, baseLayerPicker: false, geocoder: false,
        homeButton: false, sceneModePicker: false, navigationHelpButton: false, fullscreenButton: false,
        infoBox: false, selectionIndicator: false, requestRenderMode: true, maximumRenderTimeChange: Infinity,
        shouldAnimate: true, msaaSamples: 4, contextOptions: { webgl: { preserveDrawingBuffer: true } },
      }));
      const scene = (this.scene = v.scene);
      scene.globe.depthTestAgainstTerrain = false;
      scene.globe.maximumScreenSpaceError = 1.6; // صور أوضح
      scene.screenSpaceCameraController.minimumZoomDistance = 25;
      scene.fog.enabled = true;
      scene.highDynamicRange = false;
      v.cesiumWidget.screenSpaceEventHandler.removeInputAction(C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

      this.sources = {};
      this.tileset = null;
      this.buildingsMode = 'none';
      this.terrainOn = false;

      const h = new C.ScreenSpaceEventHandler(scene.canvas);
      h.setInputAction((e) => {
        const picked = scene.pick(e.position);
        if (picked && picked.id && picked.id._emFeature) {
          const f = picked.id._emFeature;
          if (f.clickable) return cb.onFeatureClick(f);
        }
        const ll = this.pickLatLng(e.position);
        if (ll) cb.onClick(ll.lat, ll.lng);
      }, C.ScreenSpaceEventType.LEFT_CLICK);
      let last = 0;
      h.setInputAction((e) => {
        const now = performance.now();
        if (now - last < 60) return;
        last = now;
        const ll = this.pickLatLng(e.endPosition, true);
        if (ll) cb.onMouseMove(ll.lat, ll.lng);
      }, C.ScreenSpaceEventType.MOUSE_MOVE);

      // إيقاف الدوران التلقائي عند تفاعل المستخدم
      ['pointerdown', 'wheel', 'touchstart'].forEach((ev) =>
        scene.canvas.addEventListener(ev, () => this.spinning && this.setSpin(false), { passive: true }));

      v.camera.moveEnd.addEventListener(() => cb.onViewChange());
      v.camera.percentageChanged = 0.01;
      v.camera.changed.addEventListener(() => cb.onCameraChange && cb.onCameraChange());

      // البداية: الكرة كاملة من الفضاء
      v.camera.setView({ destination: C.Cartesian3.fromDegrees(45, 22, 19000000) });
    }

    req() { this.scene.requestRender(); }

    setBase(key, labels) {
      const C = this.C;
      const b = BASE_LAYERS[key];
      const layers = this.viewer.imageryLayers;
      layers.removeAll();
      const mk = (o) => new C.UrlTemplateImageryProvider({
        url: o.url, subdomains: o.subdomains || 'abc', maximumLevel: o.maxNative,
        credit: new C.Credit((o.attribution || '').replace(/&copy;/g, '©'), false),
      });
      layers.addImageryProvider(mk(b));
      if (b.labels && labels) layers.addImageryProvider(mk(LABELS));
      this.req();
    }

    pickLatLng(pos, fast) {
      const C = this.C;
      const scene = this.scene;
      let cart;
      if (this.tileset && !fast && scene.pickPositionSupported) {
        try { cart = scene.pickPosition(pos); } catch (e) { cart = undefined; }
      }
      if (!cart && scene.globe.show) {
        const ray = scene.camera.getPickRay(pos);
        if (ray) cart = scene.globe.pick(ray, scene);
      }
      if (!cart) cart = scene.camera.pickEllipsoid(pos, scene.globe.ellipsoid);
      if (!cart) return null;
      const c = C.Cartographic.fromCartesian(cart);
      if (!c) return null;
      return { lat: C.Math.toDegrees(c.latitude), lng: C.Math.toDegrees(c.longitude), height: c.height };
    }

    centerCartesian() {
      const canvas = this.scene.canvas;
      const pos = new this.C.Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2);
      const ll = this.pickLatLng(pos);
      return ll ? this.C.Cartesian3.fromDegrees(ll.lng, ll.lat, ll.height || 0) : null;
    }

    getView() {
      const C = this.C;
      const cam = this.viewer.camera;
      const camC = cam.positionCartographic;
      const center = this.centerCartesian();
      let lat, lng, dist;
      if (center) {
        const c = C.Cartographic.fromCartesian(center);
        lat = C.Math.toDegrees(c.latitude);
        lng = C.Math.toDegrees(c.longitude);
        dist = C.Cartesian3.distance(cam.positionWC, center);
      } else {
        lat = C.Math.toDegrees(camC.latitude);
        lng = C.Math.toDegrees(camC.longitude);
        dist = camC.height;
      }
      return {
        lat, lng, zoom: heightToZoom(dist, lat), height: camC.height,
        heading: C.Math.toDegrees(cam.heading), pitch: C.Math.toDegrees(cam.pitch),
      };
    }

    setView(v) {
      const C = this.C;
      this.viewer.camera.setView({
        destination: C.Cartesian3.fromDegrees(v.lng, v.lat, zoomToHeight(v.zoom, v.lat)),
        orientation: { heading: 0, pitch: -C.Math.PI_OVER_TWO, roll: 0 },
      });
      this.req();
    }

    async groundHeight(lat, lng) {
      const C = this.C;
      if (!this.terrainOn) return 0;
      try {
        const res = await Promise.race([
          C.sampleTerrainMostDetailed(this.viewer.terrainProvider, [C.Cartographic.fromDegrees(lng, lat)]),
          new Promise((r) => setTimeout(() => r(null), 1500)),
        ]);
        return (res && res[0].height) || 0;
      } catch (e) {
        return 0;
      }
    }

    /** طيران سينمائي إلى نقطة مع زاوية ميل */
    async flyTo(lat, lng, zoom, o = {}) {
      const C = this.C;
      const range = o.range || zoomToHeight(zoom, lat);
      const alt = o.alt != null ? o.alt : await this.groundHeight(lat, lng);
      const pitch = o.pitch != null ? o.pitch : zoom >= 13 ? -45 : zoom >= 9 ? -65 : -90;
      const center = C.Cartesian3.fromDegrees(lng, lat, alt);
      this.viewer.camera.flyToBoundingSphere(new C.BoundingSphere(center, 0), {
        offset: new C.HeadingPitchRange(C.Math.toRadians(o.heading || 0), C.Math.toRadians(pitch), range),
        duration: o.duration,
        complete: o.complete,
        cancel: o.cancel,
      });
    }

    fitBounds(s, n, w, e) {
      const C = this.C;
      this.viewer.camera.flyTo({ destination: C.Rectangle.fromDegrees(w, s, e, n), duration: 2 });
    }

    zoomBy(d) {
      const cam = this.viewer.camera;
      const h = cam.positionCartographic.height;
      if (d > 0) cam.zoomIn(h * 0.5);
      else cam.zoomOut(h * 1.0);
      this.req();
    }

    orbit(headingDeg, pitchDeg) {
      const C = this.C;
      const center = this.centerCartesian();
      if (!center) return false;
      const cam = this.viewer.camera;
      const range = C.Cartesian3.distance(cam.positionWC, center);
      cam.flyToBoundingSphere(new C.BoundingSphere(center, 0), {
        offset: new C.HeadingPitchRange(
          headingDeg == null ? cam.heading : C.Math.toRadians(headingDeg),
          pitchDeg == null ? cam.pitch : C.Math.toRadians(pitchDeg),
          range),
        duration: 1.2,
      });
      return true;
    }

    resetNorth() { this.orbit(0, null); }

    /** دوران سينمائي حول نقطة (للجولات) — يعيد Promise */
    orbitPoint(lat, lng, alt, range, pitchDeg, ms, startHeadingDeg = 0) {
      const C = this.C;
      const cam = this.viewer.camera;
      const center = C.Cartesian3.fromDegrees(lng, lat, alt);
      const t0 = performance.now();
      this.orbitStop = false;
      return new Promise((resolve) => {
        const step = (t) => {
          const k = (t - t0) / ms;
          if (this.orbitStop || k >= 1) {
            cam.lookAtTransform(C.Matrix4.IDENTITY);
            this.req();
            return resolve(!this.orbitStop);
          }
          const hd = C.Math.toRadians(startHeadingDeg + k * 50);
          cam.lookAt(center, new C.HeadingPitchRange(hd, C.Math.toRadians(pitchDeg), range));
          this.req();
          requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    }

    toggleTilt() {
      const pitch = this.C.Math.toDegrees(this.viewer.camera.pitch);
      return this.orbit(null, pitch < -75 ? -35 : -90);
    }

    streetLevel() {
      const C = this.C;
      const center = this.centerCartesian();
      if (!center) return false;
      const cam = this.viewer.camera;
      cam.flyToBoundingSphere(new C.BoundingSphere(center, 0), {
        offset: new C.HeadingPitchRange(cam.heading, C.Math.toRadians(-8), 450),
        duration: 2.5,
      });
      return true;
    }

    setSpin(on) {
      this.spinning = on;
      const C = this.C;
      const tick = () => {
        if (!this.spinning) return;
        if (!this.hidden) {
          this.viewer.camera.rotate(C.Cartesian3.UNIT_Z, -0.0012);
          this.req();
        }
        requestAnimationFrame(tick);
      };
      if (on) requestAnimationFrame(tick);
      this.cb.onSpinChange && this.cb.onSpinChange(on);
    }

    setLighting(on) {
      const g = this.scene.globe;
      g.enableLighting = on;
      g.dynamicAtmosphereLighting = on;
      g.dynamicAtmosphereLightingFromSun = on;
      this.viewer.clock.currentTime = this.C.JulianDate.now();
      this.req();
    }

    setAtmosphere(on) {
      this.scene.skyAtmosphere.show = on;
      this.scene.globe.showGroundAtmosphere = on;
      this.scene.fog.enabled = on;
      this.req();
    }

    setToken(token) {
      this.C.Ion.defaultAccessToken = token || '';
    }

    async setTerrain(on) {
      const C = this.C;
      if (on) {
        const tp = await C.CesiumTerrainProvider.fromIonAssetId(1, { requestVertexNormals: true, requestWaterMask: true });
        this.viewer.terrainProvider = tp;
        this.scene.globe.depthTestAgainstTerrain = true;
      } else {
        this.viewer.terrainProvider = new C.EllipsoidTerrainProvider();
        this.scene.globe.depthTestAgainstTerrain = false;
      }
      this.terrainOn = on;
      this.req();
    }

    async setBuildings(mode) {
      const C = this.C;
      if (this.tileset) {
        this.scene.primitives.remove(this.tileset);
        this.tileset = null;
      }
      this.scene.globe.show = true;
      this.buildingsMode = 'none';
      if (mode === 'osm') {
        this.tileset = await C.createOsmBuildingsAsync();
      } else if (mode === 'google') {
        this.tileset = await C.createGooglePhotorealistic3DTileset();
      }
      if (this.tileset) {
        this.scene.primitives.add(this.tileset);
        if (mode === 'google') this.scene.globe.show = false;
        this.buildingsMode = mode;
      }
      this.req();
    }

    snapshot() {
      this.viewer.render();
      return this.scene.canvas.toDataURL('image/png');
    }

    resize() { this.viewer.resize(); this.req(); }

    setGroup(name, features) {
      const C = this.C;
      let ds = this.sources[name];
      if (!ds) {
        ds = this.sources[name] = new C.CustomDataSource(name);
        this.viewer.dataSources.add(ds);
      }
      ds.entities.suspendEvents();
      ds.entities.removeAll();
      features.forEach((f) => {
        let ent;
        if (f.kind === 'point') {
          const position = C.Cartesian3.fromDegrees(f.lng, f.lat, f.alt || 0);
          let image, vo = C.VerticalOrigin.BOTTOM, scale = 0.5;
          if (f.style === 'me') { image = dotCanvas('#1a73e8', '#ffffff', 11); vo = C.VerticalOrigin.CENTER; }
          else if (f.style === 'vertex') { image = dotCanvas('#ffffff', '#ff6d00', 7); vo = C.VerticalOrigin.CENTER; }
          else image = pinCanvas(f.color || '#ea4335', f.icon || '');
          ent = {
            position,
            billboard: {
              image, verticalOrigin: vo, scale: f.style ? 1 : scale,
              heightReference: C.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
          };
          if (f.label) {
            ent.label = {
              text: f.label, font: '600 14px "IBM Plex Sans Arabic", sans-serif',
              fillColor: C.Color.WHITE, outlineColor: C.Color.BLACK, outlineWidth: 3,
              style: C.LabelStyle.FILL_AND_OUTLINE, verticalOrigin: C.VerticalOrigin.BOTTOM,
              pixelOffset: new C.Cartesian2(0, -30), heightReference: C.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              distanceDisplayCondition: new C.DistanceDisplayCondition(0, f.labelFar || 2.5e6),
            };
          }
        } else if (f.kind === 'line') {
          const color = C.Color.fromCssColorString(f.color);
          ent = {
            polyline: {
              positions: f.points.map((p) => C.Cartesian3.fromDegrees(p.lng, p.lat)),
              width: (f.width || 4) + (f.casing ? 3 : 0),
              clampToGround: true,
              material: f.dashed
                ? new C.PolylineDashMaterialProperty({ color, dashLength: 16 })
                : f.casing
                  ? new C.PolylineOutlineMaterialProperty({ color, outlineColor: C.Color.WHITE, outlineWidth: 2 })
                  : color,
            },
          };
        } else if (f.kind === 'polygon') {
          ent = {
            polygon: {
              hierarchy: f.points.map((p) => C.Cartesian3.fromDegrees(p.lng, p.lat)),
              material: C.Color.fromCssColorString(f.color).withAlpha(0.25),
            },
          };
        } else if (f.kind === 'circle') {
          ent = {
            position: C.Cartesian3.fromDegrees(f.lng, f.lat),
            ellipse: {
              semiMajorAxis: f.radius, semiMinorAxis: f.radius,
              material: C.Color.fromCssColorString(f.color).withAlpha(0.15),
            },
          };
        }
        if (ent) {
          const e = ds.entities.add(ent);
          e._emFeature = f;
        }
      });
      ds.entities.resumeEvents();
      this.req();
    }
  }

  /* ===================== الواجهة الموحّدة ===================== */
  const Engines = {
    BASE_LAYERS,
    thumbUrl,
    mode: '2d',
    m2: null,
    g3: null,
    groups: {},

    init(cb) {
      this.cb = cb;
      this.m2 = new Map2D(document.getElementById('map2d'), {
        ...cb,
        onViewChange: () => this.mode === '2d' && cb.onViewChange(),
      });
      try {
        if (!window.Cesium) throw new Error('Cesium not loaded');
        this.g3 = new Globe3D(document.getElementById('map3d'), {
          ...cb,
          onViewChange: () => this.mode === '3d' && cb.onViewChange(),
        });
      } catch (e) {
        console.error(e);
        this.g3 = null;
      }
    },

    get active() { return this.mode === '3d' && this.g3 ? this.g3 : this.m2; },
    has3D() { return !!this.g3; },

    setMode(mode, keepView = true) {
      if (mode === '3d' && !this.g3) return false;
      const prev = this.mode;
      if (keepView && prev !== mode) {
        const v = this.active.getView();
        this.mode = mode;
        this.active.setView(v);
      }
      this.mode = mode;
      document.getElementById('map2d').classList.toggle('off', mode !== '2d');
      document.getElementById('map3d').classList.toggle('off', mode !== '3d');
      if (this.g3) this.g3.hidden = mode !== '3d';
      setTimeout(() => this.active.resize(), 30);
      return true;
    },

    setBase(key, labels) {
      this.m2.setBase(key, labels);
      if (this.g3) this.g3.setBase(key, labels);
    },

    /** يرسم مجموعة عناصر في المحركين */
    set(group, features) {
      this.groups[group] = features;
      this.m2.setGroup(group, features);
      if (this.g3) this.g3.setGroup(group, features);
    },
    clear(group) { this.set(group, []); },

    getView() { return this.active.getView(); },
    flyTo(lat, lng, zoom = 16, o) { return this.active.flyTo(lat, lng, zoom, o); },
    fitBounds(s, n, w, e) { this.active.fitBounds(s, n, w, e); },
    fitPoints(pts) {
      if (!pts.length) return;
      let s = 90, n = -90, w = 180, e = -180;
      pts.forEach((p) => { s = Math.min(s, p.lat); n = Math.max(n, p.lat); w = Math.min(w, p.lng); e = Math.max(e, p.lng); });
      const pad = Math.max(0.002, (n - s) * 0.15, (e - w) * 0.15);
      this.fitBounds(s - pad, n + pad, w - pad, e + pad);
    },
    zoomBy(d) { this.active.zoomBy(d); },
    viewRadius() {
      if (this.mode === '2d') return this.m2.viewRadius();
      const v = this.g3.getView();
      return Math.max(300, zoomToHeight(v.zoom, v.lat) * TAN30);
    },
  };

  EM.Engines = Engines;
})();
