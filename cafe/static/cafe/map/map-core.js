// 咖啡地圖純邏輯：不碰 DOM 與 MapLibre，供 map-app.js 使用並由 node --test 測試

export const BASEMAP_STYLES = {
  light: 'https://tiles.openfreemap.org/styles/positron',
  dark: 'https://tiles.openfreemap.org/styles/dark',
};

const TAIPEI_VIEW = { center: [121.5654, 25.033], zoom: 12 };
const SINGLE_CAFE_ZOOM = 15;

// 篩選條件：屬性值在 values 內才符合，缺值一律不符合
export const FILTERS = [
  { id: 'socket', label: '有插座', attribute: 'has_socket', values: ['yes', 'maybe'] },
  { id: 'no_time_limit', label: '不限時', attribute: 'limited_time', values: ['no', 'maybe'] },
  { id: 'pet_friendly', label: '寵物友善', attribute: 'pet_friendly', values: ['yes'] },
  { id: 'has_pet', label: '店內有貓狗', attribute: 'has_pet', values: ['yes'] },
];

// 地圖分色用的互斥分組，依陣列順序判斷，每間店只歸一組
export const GROUPS = [
  { id: 'work', label: '適合工作' },
  { id: 'pet', label: '毛孩友善' },
  { id: 'other', label: '其他' },
  { id: 'unknown', label: '尚無資料' },
];

const ATTRIBUTE_KEYS = ['has_socket', 'limited_time', 'pet_friendly', 'has_pet'];

// 與 LINE「工作友善咖啡」條件相同：有插座（很多或視座位）且不限時（不限時或視情況）
export function groupOf(cafe) {
  const a = cafe.attributes || {};
  if (['yes', 'maybe'].includes(a.has_socket) && ['no', 'maybe'].includes(a.limited_time)) return 'work';
  if (a.pet_friendly === 'yes' || a.has_pet === 'yes') return 'pet';
  if (ATTRIBUTE_KEYS.every((key) => a[key] === null || a[key] === undefined)) return 'unknown';
  return 'other';
}

// 與 LINE 卡片標籤文字一致
const TAG_TEXTS = [
  ['has_socket', { yes: '🔌 有插座', maybe: '🔌 有插座' }],
  ['limited_time', { no: '⏱ 不限時', maybe: '⏱ 視情況', yes: '⏱ 有限時' }],
  ['pet_friendly', { yes: '🐕 寵物友善', maybe: '🐕 寵物友善' }],
  ['has_pet', { yes: '🐈 有貓貓狗狗', maybe: '🐈 有貓貓狗狗' }],
];

function matches(cafe, filter) {
  return filter.values.includes(cafe.attributes?.[filter.attribute]);
}

export function filterCafes(cafes, activeIds, hiddenGroups = new Set()) {
  const active = FILTERS.filter((f) => activeIds.has(f.id));
  return cafes.filter((cafe) => !hiddenGroups.has(groupOf(cafe)) && active.every((f) => matches(cafe, f)));
}

export function countFilters(cafes) {
  return Object.fromEntries(FILTERS.map((f) => [f.id, cafes.filter((cafe) => matches(cafe, f)).length]));
}

export function countGroups(cafes) {
  const counts = Object.fromEntries(GROUPS.map((g) => [g.id, 0]));
  for (const cafe of cafes) counts[groupOf(cafe)] += 1;
  return counts;
}

export function attributeTags(attributes) {
  if (!attributes) return [];
  return TAG_TEXTS.map(([key, texts]) => texts[attributes[key]]).filter(Boolean);
}

function hasCoordinates(cafe) {
  return Number.isFinite(cafe.lat) && Number.isFinite(cafe.lng);
}

// feature id 與 properties.index 指向傳入陣列的索引，供選取與 feature-state 使用
export function toGeoJSON(cafes) {
  const features = [];
  cafes.forEach((cafe, index) => {
    if (!hasCoordinates(cafe)) return;
    features.push({
      type: 'Feature',
      id: index,
      geometry: { type: 'Point', coordinates: [cafe.lng, cafe.lat] },
      properties: { index, place_id: cafe.place_id, group: groupOf(cafe) },
    });
  });
  return { type: 'FeatureCollection', features };
}

export function computeView(cafes) {
  const points = cafes.filter(hasCoordinates);
  if (points.length === 0) return { ...TAIPEI_VIEW };

  const lngs = points.map((c) => c.lng);
  const lats = points.map((c) => c.lat);
  const west = Math.min(...lngs);
  const east = Math.max(...lngs);
  const south = Math.min(...lats);
  const north = Math.max(...lats);
  if (west === east && south === north) return { center: [west, south], zoom: SINGLE_CAFE_ZOOM };
  return { bounds: [[west, south], [east, north]] };
}

// 只接受絕對的 http(s) 網址，擋下 javascript:、data: 等 scheme
export function safeHttpUrl(value) {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value)) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? value : null;
  } catch {
    return null;
  }
}

export function safeTelUri(value) {
  return typeof value === 'string' && /^tel:\+?\d{3,15}$/.test(value) ? value : null;
}
