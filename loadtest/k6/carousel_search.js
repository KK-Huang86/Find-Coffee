// 多筆搜尋（carousel）回應時間壓測：每個 iteration 由一位新使用者
// 1) 點選單「店名搜尋」（postback，設定對話狀態）
// 2) 輸入店名前綴，命中 10 間店 → 量這一步 /callback 的回應時間（webhook 為同步處理，回應時間 = 完整處理時間）
// address_* 情境改為點「路名查詢」並輸入地址，驗證 Geocoding / Nearby Search 的共用快取
import http from 'k6/http';
import crypto from 'k6/crypto';
import exec from 'k6/execution';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const SECRET = __ENV.LINE_CHANNEL_SECRET || 'loadtest-secret';
const SCENARIO = __ENV.SCENARIO;
const ITERATIONS = parseInt(__ENV.ITERATIONS || '30', 10);
const VUS = parseInt(__ENV.VUS || '5', 10);

const searchDuration = new Trend('search_duration', true);

export const options = {
  scenarios: {
    carousel: {
      executor: 'shared-iterations',
      vus: VUS,
      iterations: ITERATIONS,
      maxDuration: '5m',
    },
  },
  thresholds: {
    checks: ['rate==1.0'],
  },
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'max'],
};

function pad(n) {
  return String(n).padStart(4, '0');
}

function sendEvent(event) {
  const body = JSON.stringify({ destination: 'Uloadtest', events: [event] });
  const signature = crypto.hmac('sha256', SECRET, body, 'base64');
  return http.post(`${BASE_URL}/callback`, body, {
    headers: { 'Content-Type': 'application/json', 'X-Line-Signature': signature },
    timeout: '60s',
  });
}

function baseEvent(userId, type) {
  return {
    type,
    mode: 'active',
    timestamp: Date.now(),
    source: { type: 'user', userId },
    webhookEventId: `lt-${exec.scenario.iterationInTest}-${type}-${Date.now()}`,
    deliveryContext: { isRedelivery: false },
    replyToken: `lt-reply-${exec.scenario.iterationInTest}-${type}`,
  };
}

function searchStep(group) {
  if (SCENARIO === 'address_cold') {
    return { menuType: 'search_address', text: `台北市信義區壓測路 ${group + 1}` };
  }
  if (SCENARIO === 'address_hot') {
    return { menuType: 'search_address', text: '台北市信義區壓測路 1' };
  }
  if (SCENARIO === 'address_miss') {
    return { menuType: 'search_address', text: 'LT-MISS 不存在的地址' };
  }
  return { menuType: 'search_shop_name', text: `LT-${SCENARIO}-${pad(group)}-` };
}

export default function () {
  const group = exec.scenario.iterationInTest;
  const userId = `U-loadtest-${pad(group)}`;
  const step = searchStep(group);

  const menu = sendEvent({
    ...baseEvent(userId, 'postback'),
    postback: { data: `action=menu&type=${step.menuType}` },
  });
  check(menu, { 'menu postback 200': (r) => r.status === 200 });

  const search = sendEvent({
    ...baseEvent(userId, 'message'),
    message: { id: `${group}`, type: 'text', quoteToken: 'q', text: step.text },
  });
  check(search, { 'search 200': (r) => r.status === 200 });
  searchDuration.add(search.timings.duration);
}
