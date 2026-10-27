// 咖啡地圖頁面：DOM、MapLibre、抽屜與主題切換。所有店家文字一律以 textContent 寫入，不使用 innerHTML
import {
  BASEMAP_STYLES,
  FILTERS,
  GROUPS,
  attributeTags,
  computeView,
  countFilters,
  countGroups,
  filterCafes,
  groupOf,
  safeHttpUrl,
  safeTelUri,
  toGeoJSON,
} from './map-core.js';

const THEME_KEY = 'find-coffee-map:theme';
const SHEET_STATES = ['peek', 'half', 'full'];
const SOURCE_ID = 'cafes';
// 選取店家時至少放大到此層級；需大於 clusterMaxZoom，店家才不會被包在群集裡
const SELECT_ZOOM = 16;
const CLUSTER_MAX_ZOOM = 14;
const desktopQuery = window.matchMedia('(min-width: 768px)');

const els = {
  map: document.getElementById('map'),
  panel: document.getElementById('panel'),
  handle: document.getElementById('panel-handle'),
  summary: document.getElementById('summary'),
  filters: document.getElementById('filters'),
  status: document.getElementById('status'),
  detail: document.getElementById('detail'),
  list: document.getElementById('cafe-list'),
  themeToggle: document.getElementById('theme-toggle'),
  legend: document.getElementById('legend'),
};

const state = {
  snapshot: null,
  cafes: [],
  visible: [],
  activeFilters: new Set(),
  hiddenGroups: new Set(),
  legendOpen: desktopQuery.matches,
  selectedId: null,
  selectedMarker: null,
  map: null,
  popup: null,
};

// ---------- DOM helpers ----------

function el(tag, { className, text, attrs } = {}, children = []) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child) node.append(child);
  }
  return node;
}

function svg(pathDefs, className) {
  const ns = 'http://www.w3.org/2000/svg';
  const node = document.createElementNS(ns, 'svg');
  node.setAttribute('viewBox', '0 0 24 24');
  node.setAttribute('aria-hidden', 'true');
  if (className) node.setAttribute('class', className);
  for (const d of pathDefs) {
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', d);
    node.append(path);
  }
  return node;
}

// 篩選 chip 圖示（自繪線稿）
const FILTER_ICONS = {
  socket: ['M9 3v5', 'M15 3v5', 'M6 8h12v3a6 6 0 0 1-12 0Z', 'M12 17v4'],
  no_time_limit: ['M12 7v5l3 2', 'M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0'],
  pet_friendly: ['M7 14c0-2.5 2.2-4 5-4s5 1.5 5 4-2 4-5 4-5-1.5-5-4Z', 'M6 8.5a1.5 1.5 0 1 0 0 .1', 'M10 5.5a1.5 1.5 0 1 0 0 .1', 'M14 5.5a1.5 1.5 0 1 0 0 .1', 'M18 8.5a1.5 1.5 0 1 0 0 .1'],
  has_pet: ['M5 20v-9l-1-6 4 3h8l4-3-1 6v9Z', 'M9.5 13h.01', 'M14.5 13h.01', 'M11 16.5h2'],
};

const CUP_PATHS = ['M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5Z', 'M17 10h1.5a2.5 2.5 0 0 1 0 5H17', 'M8 3.5c0 1.5 1.5 1.5 1.5 3', 'M12 3.5c0 1.5 1.5 1.5 1.5 3'];

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function isDesktop() {
  return desktopQuery.matches;
}

// ---------- 狀態訊息 ----------

function showStatus(message, action) {
  els.status.replaceChildren(el('p', { text: message }));
  if (action) {
    const button = el('button', { className: 'button button-secondary', text: action.label, attrs: { type: 'button' } });
    button.addEventListener('click', action.onClick);
    els.status.append(button);
  }
  els.status.hidden = false;
}

function hideStatus() {
  els.status.hidden = true;
  els.status.replaceChildren();
}

// ---------- 店家卡片 ----------

function buildPhoto(cafe) {
  const placeholder = el('div', { className: 'card-photo card-photo-placeholder' }, [svg(CUP_PATHS)]);
  const src = safeHttpUrl(cafe.photo_url);
  if (!src) return placeholder;

  const img = el('img', {
    className: 'card-photo',
    attrs: { src, alt: cafe.name || '', loading: 'lazy', referrerpolicy: 'no-referrer' },
  });
  img.addEventListener('error', () => img.replaceWith(placeholder), { once: true });
  return img;
}

function buildTags(attributes) {
  const tags = attributeTags(attributes);
  if (tags.length === 0) return null;
  return el('ul', { className: 'tags' }, tags.map((text) => el('li', { className: 'tag', text })));
}

function buildSection(label, text) {
  if (!text) return null;
  return el('div', { className: 'card-section' }, [
    el('span', { className: 'card-section-label', text: label }),
    el('span', { text }),
  ]);
}

function buildCard(cafe) {
  const meta = [];
  if (cafe.rating != null) {
    meta.push(el('span', { className: 'card-rating', text: `★ ${cafe.rating}` }));
    if (cafe.user_ratings_total) meta.push(document.createTextNode(` · ${cafe.user_ratings_total} 則 Google 評論`));
  }

  const actions = [];
  const mapsUrl = safeHttpUrl(cafe.google_maps);
  if (mapsUrl) {
    actions.push(el('a', {
      className: 'button',
      text: 'Google Maps',
      attrs: { href: mapsUrl, target: '_blank', rel: 'noopener noreferrer' },
    }));
  }
  const telUri = safeTelUri(cafe.tel_uri);
  if (telUri) {
    actions.push(el('a', { className: 'button button-secondary', text: '打電話', attrs: { href: telUri } }));
  }

  return el('article', { className: 'card' }, [
    buildPhoto(cafe),
    el('div', { className: 'card-body' }, [
      el('h2', { className: 'card-title', text: cafe.name }),
      meta.length ? el('p', { className: 'card-meta' }, meta) : null,
      cafe.address ? el('p', { className: 'card-address', text: cafe.address }) : null,
      buildTags(cafe.attributes),
      buildSection('AI 評論摘要', cafe.ai_summary),
      buildSection('我的備註', cafe.note),
      actions.length ? el('div', { className: 'card-actions' }, actions) : null,
    ]),
  ]);
}

// ---------- 清單與篩選 ----------

function renderFilters() {
  els.filters.replaceChildren(...FILTERS.map((filter) => {
    const button = el('button', {
      className: 'chip',
      attrs: { type: 'button', 'aria-pressed': String(state.activeFilters.has(filter.id)) },
    }, [
      svg(FILTER_ICONS[filter.id], 'chip-icon'),
      el('span', { text: filter.label }),
      el('span', { className: 'chip-count', text: String(state.filterCounts?.[filter.id] ?? 0) }),
    ]);
    button.addEventListener('click', () => toggleFilter(filter.id));
    return button;
  }));
}

// ---------- 地圖圖例（依工作友善程度分色，可點選顯示或隱藏） ----------

function renderLegend() {
  const counts = countGroups(state.cafes);
  const shownOnMap = state.visible.length;
  const toggle = el('button', {
    className: 'legend-toggle',
    attrs: { type: 'button', 'aria-expanded': String(state.legendOpen) },
  }, [
    el('span', { className: 'legend-dots' }, GROUPS.map((g) => el('span', { className: 'group-dot', attrs: { 'data-group': g.id } }))),
    el('span', { text: `地圖上 ${shownOnMap} 間` }),
    svg(['M6 9l6 6 6-6'], 'legend-chevron'),
  ]);
  toggle.addEventListener('click', () => {
    state.legendOpen = !state.legendOpen;
    renderLegend();
  });

  const rows = GROUPS.map((group) => {
    const shown = !state.hiddenGroups.has(group.id);
    const row = el('button', {
      className: 'legend-row',
      attrs: { type: 'button', 'aria-pressed': String(shown) },
    }, [
      el('span', { className: 'group-dot', attrs: { 'data-group': group.id } }),
      el('span', { className: 'legend-label', text: group.label }),
      el('span', { className: 'legend-count', text: String(counts[group.id]) }),
    ]);
    row.addEventListener('click', () => toggleGroup(group.id));
    return row;
  });

  els.legend.replaceChildren(toggle);
  if (state.legendOpen) els.legend.append(el('div', { className: 'legend-rows', attrs: { role: 'group', 'aria-label': '分組' } }, rows));
  els.legend.hidden = state.cafes.length === 0;
}

function toggleGroup(id) {
  if (state.hiddenGroups.has(id)) state.hiddenGroups.delete(id);
  else state.hiddenGroups.add(id);
  applyFilters();
}

function toggleFilter(id) {
  if (state.activeFilters.has(id)) state.activeFilters.delete(id);
  else state.activeFilters.add(id);
  applyFilters();
}

function clearFilters() {
  state.activeFilters.clear();
  state.hiddenGroups.clear();
  applyFilters();
}

function applyFilters() {
  state.visible = filterCafes(state.cafes, state.activeFilters, state.hiddenGroups);
  if (state.selectedId && !state.visible.some((c) => c.place_id === state.selectedId)) clearSelection();
  renderFilters();
  renderLegend();
  renderList();
  updateMapData();
}

function renderSummary() {
  const total = state.cafes.length;
  const shown = state.visible.length;
  const filtered = state.activeFilters.size || state.hiddenGroups.size;
  const parts = [filtered ? `${shown} / ${total} 間` : `共 ${total} 間`];
  const generatedAt = new Date(state.snapshot.generated_at);
  if (!Number.isNaN(generatedAt.getTime())) {
    parts.push(`更新於 ${generatedAt.toLocaleString('zh-TW', { dateStyle: 'short', timeStyle: 'short' })}`);
  }
  els.summary.textContent = parts.join(' · ');
}

function renderList() {
  renderSummary();

  if (state.cafes.length === 0) {
    els.list.replaceChildren();
    showStatus('還沒有收藏的咖啡店，回 LINE 收藏幾間吧 ☕️');
    return;
  }
  if (state.visible.length === 0) {
    els.list.replaceChildren();
    showStatus('沒有符合這些條件的店家', { label: '清除篩選', onClick: clearFilters });
    return;
  }
  hideStatus();

  els.list.replaceChildren(...state.visible.map((cafe) => {
    const metaText = [cafe.rating != null ? `★ ${cafe.rating}` : null, cafe.address].filter(Boolean).join(' · ');
    const button = el('button', {
      className: 'cafe-item',
      attrs: { type: 'button', 'aria-current': String(cafe.place_id === state.selectedId) },
    }, [
      el('span', { className: 'cafe-item-name', text: cafe.name }),
      metaText ? el('span', { className: 'cafe-item-meta', text: metaText }) : null,
      buildTags(cafe.attributes),
    ]);
    button.prepend(el('span', { className: 'group-dot', attrs: { 'data-group': groupOf(cafe), 'aria-hidden': 'true' } }));
    button.addEventListener('click', () => selectCafe(cafe.place_id));
    return el('li', {}, [button]);
  }));
}

// ---------- 選取 ----------

function findCafe(placeId) {
  return state.cafes.find((c) => c.place_id === placeId) || null;
}

// 選取後店家在畫面上的位置（相對地圖中心）：桌面放在偏下方讓上方 popup 有空間，手機放在抽屜上方可見區域的中央
function selectionOffset() {
  const height = els.map.clientHeight;
  return isDesktop() ? [0, Math.round(height * 0.28)] : [0, -Math.round(height * 0.26)];
}

function selectCafe(placeId) {
  const cafe = findCafe(placeId);
  if (!cafe) return;
  state.selectedId = placeId;
  updateSelectedMarker(cafe);
  markListSelection();

  if (state.map) {
    state.map.flyTo({
      center: [cafe.lng, cafe.lat],
      zoom: Math.max(state.map.getZoom(), SELECT_ZOOM),
      offset: selectionOffset(),
      speed: 1.2,
      curve: 1.4,
      maxDuration: 1600,
      essential: true,
    });
  }

  if (isDesktop()) {
    showPopup(cafe);
  } else {
    showDetail(cafe);
  }
}

function clearSelection() {
  state.selectedId = null;
  updateSelectedMarker(null);
  markListSelection();
  if (state.popup) {
    const popup = state.popup;
    state.popup = null;
    popup.remove();
  }
  hideDetail();
}

function markListSelection() {
  for (const item of els.list.querySelectorAll('.cafe-item')) item.setAttribute('aria-current', 'false');
  const index = state.visible.findIndex((c) => c.place_id === state.selectedId);
  const item = index >= 0 ? els.list.children[index]?.querySelector('.cafe-item') : null;
  if (item) {
    item.setAttribute('aria-current', 'true');
    if (isDesktop()) item.scrollIntoView({ block: 'nearest' });
  }
}

function showPopup(cafe) {
  if (!state.map || !window.maplibregl) return;
  if (state.popup) {
    const old = state.popup;
    state.popup = null;
    old.remove();
  }
  const popup = new window.maplibregl.Popup({ className: 'cafe-popup', anchor: 'bottom', offset: 46, maxWidth: 'none', focusAfterOpen: false })
    .setLngLat([cafe.lng, cafe.lat])
    .setDOMContent(buildCard(cafe))
    .addTo(state.map);
  popup.on('close', () => {
    if (state.popup === popup) {
      state.popup = null;
      state.selectedId = null;
      updateSelectedMarker(null);
      markListSelection();
    }
  });
  state.popup = popup;
}

function showDetail(cafe) {
  const back = el('button', { className: 'detail-back', text: '‹ 回到清單', attrs: { type: 'button' } });
  back.addEventListener('click', clearSelection);
  els.detail.replaceChildren(back, buildCard(cafe));
  els.detail.hidden = false;
  els.list.hidden = true;
  els.status.hidden = true;
  setSheet('half');
  document.getElementById('panel-body').scrollTop = 0;
}

function hideDetail() {
  if (els.detail.hidden) return;
  els.detail.hidden = true;
  els.detail.replaceChildren();
  els.list.hidden = false;
  if (state.snapshot) renderList();
}

// ---------- 手機抽屜 ----------

function setSheet(value) {
  els.panel.dataset.sheet = value;
}

function stepSheet(delta) {
  const current = SHEET_STATES.indexOf(els.panel.dataset.sheet);
  const next = Math.min(SHEET_STATES.length - 1, Math.max(0, current + delta));
  setSheet(SHEET_STATES[next]);
}

// 把手與標題列都可以上下拖曳切換抽屜高度；標題列上的按鈕維持原本行為
function setupSheet() {
  const header = els.panel.querySelector('.panel-header');
  let startY = null;

  const onDown = (event) => {
    if (isDesktop() || event.target.closest('button:not(.panel-handle)')) return;
    startY = event.clientY;
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onUp = (event) => {
    if (startY === null) return;
    const dy = event.clientY - startY;
    startY = null;
    if (dy < -30) stepSheet(1);
    else if (dy > 30) stepSheet(-1);
    else if (event.currentTarget === els.handle) setSheet(els.panel.dataset.sheet === 'peek' ? 'half' : 'peek');
  };

  for (const target of [els.handle, header]) {
    target.addEventListener('pointerdown', onDown);
    target.addEventListener('pointerup', onUp);
    target.addEventListener('pointercancel', () => { startY = null; });
  }
}

// ---------- 主題 ----------

function storedTheme() {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  // diff: false 才會觸發 style.load，讓自訂圖層依新主題色重新加入
  if (state.map) state.map.setStyle(BASEMAP_STYLES[theme], { diff: false });
}

function setupTheme() {
  els.themeToggle.addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // 無法儲存時只影響本次瀏覽
    }
    applyTheme(next);
  });

  // 沒有手動選擇時跟隨系統切換
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (event) => {
    if (!storedTheme()) applyTheme(event.matches ? 'dark' : 'light');
  });
}

// ---------- 地圖 ----------

function addCafeLayers() {
  const map = state.map;
  if (map.getSource(SOURCE_ID)) return;

  map.addSource(SOURCE_ID, {
    type: 'geojson',
    data: toGeoJSON(state.visible),
    cluster: true,
    clusterRadius: 50,
    clusterMaxZoom: CLUSTER_MAX_ZOOM,
  });

  const stroke = cssVar('--marker-stroke');
  map.addLayer({
    id: 'clusters',
    type: 'circle',
    source: SOURCE_ID,
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': cssVar('--cluster'),
      'circle-radius': ['step', ['get', 'point_count'], 16, 10, 20, 30, 26],
      'circle-stroke-width': 3,
      'circle-stroke-color': stroke,
      'circle-opacity': 0.92,
    },
  });
  map.addLayer({
    id: 'cluster-count',
    type: 'symbol',
    source: SOURCE_ID,
    filter: ['has', 'point_count'],
    layout: {
      'text-field': ['get', 'point_count_abbreviated'],
      'text-font': ['Noto Sans Bold'],
      'text-size': 13,
      'text-allow-overlap': true,
    },
    paint: { 'text-color': '#FFFFFF' },
  });
  map.addLayer({
    id: 'cafe-points',
    type: 'circle',
    source: SOURCE_ID,
    filter: pointsFilter(),
    paint: {
      'circle-color': ['match', ['get', 'group'], ...GROUPS.flatMap((g) => [g.id, cssVar(`--group-${g.id}`)]), cssVar('--group-unknown')],
      'circle-radius': 7,
      'circle-stroke-width': 2,
      'circle-stroke-color': stroke,
    },
  });
}

// 選取中的店家改由圖釘呈現，從圓點圖層排除，避免圓點露在針尖底下
function pointsFilter() {
  return ['all', ['!', ['has', 'point_count']], ['!=', ['get', 'place_id'], state.selectedId || '']];
}

// 選取的店家以 HTML 標記呈現：不受群集影響、針尖對準座標，並可用 CSS 做跳動動畫
function updateSelectedMarker(cafe) {
  if (state.selectedMarker) {
    state.selectedMarker.remove();
    state.selectedMarker = null;
  }
  if (state.map?.getLayer('cafe-points')) state.map.setFilter('cafe-points', pointsFilter());
  if (!cafe || !state.map || !window.maplibregl) return;

  const pin = el('div', { className: 'selected-pin', attrs: { 'data-group': groupOf(cafe), 'aria-hidden': 'true' } }, [
    el('span', { className: 'selected-pin-head' }, [svg(CUP_PATHS, 'selected-pin-icon')]),
    el('span', { className: 'selected-pin-shadow' }),
  ]);
  state.selectedMarker = new window.maplibregl.Marker({ element: pin, anchor: 'bottom' })
    .setLngLat([cafe.lng, cafe.lat])
    .addTo(state.map);
}

function updateMapData() {
  const source = state.map?.getSource(SOURCE_ID);
  if (source) source.setData(toGeoJSON(state.visible));
}

function fitPadding() {
  return isDesktop() ? 64 : { top: 48, left: 32, right: 32, bottom: 220 };
}

function setupMap() {
  if (!window.maplibregl) {
    els.map.replaceChildren(el('div', { className: 'status', text: '地圖元件載入失敗，仍可瀏覽下方清單' }));
    return;
  }

  const view = computeView(state.cafes);
  const map = new window.maplibregl.Map({
    container: els.map,
    style: BASEMAP_STYLES[currentTheme()],
    center: view.center || [121.5654, 25.033],
    zoom: view.zoom || 12,
    attributionControl: { compact: true },
    dragRotate: false,
    pitchWithRotate: false,
  });
  state.map = map;
  map.touchZoomRotate.disableRotation();
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-right');

  if (view.bounds) map.fitBounds(view.bounds, { padding: fitPadding(), maxZoom: 15, duration: 0 });

  // setStyle（切換主題）會清掉自訂圖層，每次樣式載入完成後重新加入
  map.on('style.load', addCafeLayers);

  map.on('click', 'clusters', async (event) => {
    const feature = event.features?.[0];
    if (!feature) return;
    const zoom = await map.getSource(SOURCE_ID).getClusterExpansionZoom(feature.properties.cluster_id);
    map.easeTo({ center: feature.geometry.coordinates, zoom });
  });
  map.on('click', 'cafe-points', (event) => {
    const feature = event.features?.[0];
    if (feature) selectCafe(feature.properties.place_id);
  });
  for (const layer of ['clusters', 'cafe-points']) {
    map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
  }
}

// ---------- 載入 ----------

async function loadSnapshot() {
  els.summary.textContent = '讀取中…';
  showStatus('正在載入你的咖啡地圖…');
  try {
    const response = await fetch(new URL('data.json', window.location.href), { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const snapshot = await response.json();
    if (!snapshot || !Array.isArray(snapshot.cafes)) throw new Error('snapshot 格式錯誤');
    return snapshot;
  } catch (error) {
    console.error('咖啡地圖資料載入失敗', error);
    els.summary.textContent = '載入失敗';
    showStatus('地圖資料載入失敗，請檢查網路後再試一次', { label: '重新載入', onClick: start });
    return null;
  }
}

async function start() {
  const snapshot = await loadSnapshot();
  if (!snapshot) return;

  state.snapshot = snapshot;
  state.cafes = snapshot.cafes.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng));
  state.filterCounts = countFilters(state.cafes);
  state.visible = filterCafes(state.cafes, state.activeFilters, state.hiddenGroups);
  renderFilters();
  renderLegend();
  renderList();
  if (!state.map) setupMap();
  else updateMapData();
}

desktopQuery.addEventListener('change', () => {
  // 切換版型時改用對應的卡片呈現方式
  const selected = state.selectedId;
  clearSelection();
  if (selected) selectCafe(selected);
});

setupSheet();
setupTheme();
renderFilters();
start();
