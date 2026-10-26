import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  FILTERS,
  filterCafes,
  toGeoJSON,
  safeHttpUrl,
  safeTelUri,
  computeView,
  attributeTags,
} from '../../static/cafe/map/map-core.js';

const cafe = (placeId, attributes = {}, extra = {}) => ({
  place_id: placeId,
  name: placeId,
  lat: 25.03,
  lng: 121.56,
  attributes: { has_socket: null, limited_time: null, pet_friendly: null, has_pet: null, ...attributes },
  ...extra,
});

describe('FILTERS', () => {
  test('提供四個篩選條件', () => {
    assert.deepEqual(FILTERS.map((f) => f.id), ['socket', 'no_time_limit', 'pet_friendly', 'has_pet']);
    assert.deepEqual(FILTERS.map((f) => f.label), ['有插座', '不限時', '寵物友善', '店內有貓狗']);
  });
});

describe('filterCafes', () => {
  const cafes = [
    cafe('socket_yes', { has_socket: 'yes' }),
    cafe('socket_maybe', { has_socket: 'maybe' }),
    cafe('socket_no', { has_socket: 'no' }),
    cafe('time_no', { limited_time: 'no' }),
    cafe('time_maybe', { limited_time: 'maybe' }),
    cafe('time_yes', { limited_time: 'yes' }),
    cafe('pet_yes', { pet_friendly: 'yes' }),
    cafe('pet_maybe', { pet_friendly: 'maybe' }),
    cafe('cat_yes', { has_pet: 'yes' }),
    cafe('cat_maybe', { has_pet: 'maybe' }),
    cafe('all_null'),
  ];
  const ids = (list) => list.map((c) => c.place_id);

  test('沒有條件時回傳全部，且不改變順序', () => {
    assert.deepEqual(ids(filterCafes(cafes, new Set())), ids(cafes));
  });

  test('有插座：很多或視座位', () => {
    assert.deepEqual(ids(filterCafes(cafes, new Set(['socket']))), ['socket_yes', 'socket_maybe']);
  });

  test('不限時：一律不限時或視情況', () => {
    assert.deepEqual(ids(filterCafes(cafes, new Set(['no_time_limit']))), ['time_no', 'time_maybe']);
  });

  test('寵物友善：只有歡迎', () => {
    assert.deepEqual(ids(filterCafes(cafes, new Set(['pet_friendly']))), ['pet_yes']);
  });

  test('店內有貓狗：只有有', () => {
    assert.deepEqual(ids(filterCafes(cafes, new Set(['has_pet']))), ['cat_yes']);
  });

  test('多個條件以 AND 組合', () => {
    const list = [
      cafe('both', { has_socket: 'yes', limited_time: 'no' }),
      cafe('socket_only', { has_socket: 'yes', limited_time: 'yes' }),
      cafe('time_only', { has_socket: 'no', limited_time: 'no' }),
    ];
    assert.deepEqual(ids(filterCafes(list, new Set(['socket', 'no_time_limit']))), ['both']);
  });

  test('屬性缺值或缺 attributes 視為不符合', () => {
    const list = [cafe('null_attr'), { place_id: 'no_attributes', lat: 25, lng: 121 }];
    assert.deepEqual(filterCafes(list, new Set(['socket'])), []);
  });

  test('未知的條件 id 忽略', () => {
    assert.deepEqual(ids(filterCafes(cafes, new Set(['unknown']))), ids(cafes));
  });

  test('空清單', () => {
    assert.deepEqual(filterCafes([], new Set(['socket'])), []);
  });
});

describe('toGeoJSON', () => {
  test('轉為 FeatureCollection，座標為 [lng, lat]，properties 帶索引與 place_id', () => {
    const geojson = toGeoJSON([cafe('a', {}, { lat: 25.1, lng: 121.5 }), cafe('b', {}, { lat: 24.9, lng: 121.2 })]);
    assert.equal(geojson.type, 'FeatureCollection');
    assert.deepEqual(geojson.features, [
      { type: 'Feature', id: 0, geometry: { type: 'Point', coordinates: [121.5, 25.1] }, properties: { index: 0, place_id: 'a' } },
      { type: 'Feature', id: 1, geometry: { type: 'Point', coordinates: [121.2, 24.9] }, properties: { index: 1, place_id: 'b' } },
    ]);
  });

  test('跳過座標不是有限數字的店家', () => {
    const geojson = toGeoJSON([cafe('ok'), cafe('bad', {}, { lat: null }), cafe('nan', {}, { lng: Number.NaN })]);
    assert.deepEqual(geojson.features.map((f) => f.properties.place_id), ['ok']);
  });

  test('空清單', () => {
    assert.deepEqual(toGeoJSON([]), { type: 'FeatureCollection', features: [] });
  });
});

describe('safeHttpUrl', () => {
  test('允許 http 與 https', () => {
    assert.equal(safeHttpUrl('https://maps.google.com/?cid=1'), 'https://maps.google.com/?cid=1');
    assert.equal(safeHttpUrl('http://example.com/a'), 'http://example.com/a');
  });

  for (const bad of ['javascript:alert(1)', 'JAVASCRIPT:alert(1)', ' javascript:alert(1)', 'data:text/html,x',
    'vbscript:x', 'tel:0223456789', '//evil.com', 'not a url', '', null, undefined, 42, {}]) {
    test(`拒絕 ${JSON.stringify(bad)}`, () => {
      assert.equal(safeHttpUrl(bad), null);
    });
  }
});

describe('safeTelUri', () => {
  test('允許 tel: 加數字與開頭 +', () => {
    assert.equal(safeTelUri('tel:0223456789'), 'tel:0223456789');
    assert.equal(safeTelUri('tel:+886223456789'), 'tel:+886223456789');
  });

  for (const bad of ['0223456789', 'tel:02-2345', 'tel:', 'javascript:alert(1)', 'tel:02;x', null, 5]) {
    test(`拒絕 ${JSON.stringify(bad)}`, () => {
      assert.equal(safeTelUri(bad), null);
    });
  }
});

describe('computeView', () => {
  test('沒有店家時以台北市為中心', () => {
    assert.deepEqual(computeView([]), { center: [121.5654, 25.033], zoom: 12 });
  });

  test('一間店時以該店為中心', () => {
    assert.deepEqual(computeView([cafe('a', {}, { lat: 24.15, lng: 120.67 })]), { center: [120.67, 24.15], zoom: 15 });
  });

  test('多間店時回傳涵蓋全部的邊界', () => {
    const view = computeView([
      cafe('a', {}, { lat: 25.1, lng: 121.6 }),
      cafe('b', {}, { lat: 24.9, lng: 121.4 }),
      cafe('c', {}, { lat: 25.0, lng: 121.7 }),
    ]);
    assert.deepEqual(view, { bounds: [[121.4, 24.9], [121.7, 25.1]] });
  });

  test('多間店座標相同時視為一間', () => {
    const same = { lat: 25.0, lng: 121.5 };
    assert.deepEqual(computeView([cafe('a', {}, same), cafe('b', {}, same)]), { center: [121.5, 25.0], zoom: 15 });
  });
});

describe('attributeTags', () => {
  test('文字與 LINE 卡片標籤一致，依插座、限時、寵物友善、店貓店狗排序', () => {
    assert.deepEqual(
      attributeTags({ has_socket: 'yes', limited_time: 'no', pet_friendly: 'yes', has_pet: 'yes' }),
      ['🔌 有插座', '⏱ 不限時', '🐕 寵物友善', '🐈 有貓貓狗狗'],
    );
  });

  test('maybe 也顯示；限時依值顯示不同文字', () => {
    assert.deepEqual(
      attributeTags({ has_socket: 'maybe', limited_time: 'maybe', pet_friendly: 'maybe', has_pet: 'maybe' }),
      ['🔌 有插座', '⏱ 視情況', '🐕 寵物友善', '🐈 有貓貓狗狗'],
    );
    assert.deepEqual(attributeTags({ limited_time: 'yes' }), ['⏱ 有限時']);
  });

  test('no、缺值與未知值不顯示', () => {
    assert.deepEqual(attributeTags({ has_socket: 'no', pet_friendly: 'no', has_pet: 'no' }), []);
    assert.deepEqual(attributeTags({ has_socket: null, limited_time: 'weird' }), []);
    assert.deepEqual(attributeTags(undefined), []);
  });
});
