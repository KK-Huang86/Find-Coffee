#!/usr/bin/env bash
# 多筆搜尋回應時間壓測。外部 API 全部走 mock server，DB / Redis 與開發環境隔離。
# 用法：loadtest/run.sh [情境...]   （預設 cached stale expired_photo address_cold address_hot address_miss）
# 可調參數（環境變數）：VUS=5 ITERATIONS=30 DETAIL_LATENCY_MS=300 PHOTO_LATENCY_MS=150 LINE_LATENCY_MS=50
#                       GEOCODE_LATENCY_MS=200 NEARBY_LATENCY_MS=300 AGE_HOURS=0（refresh_spread 使用）
set -euo pipefail

cd "$(dirname "$0")/.."
SCENARIOS=("${@:-cached stale expired_photo address_cold address_hot address_miss}")
read -r -a SCENARIOS <<< "${SCENARIOS[*]}"
VUS="${VUS:-5}"
ITERATIONS="${ITERATIONS:-30}"
RESULTS_DIR="loadtest/results/$(date +%Y%m%d-%H%M%S)"
COMPOSE=(docker compose -f docker-compose.yml -f loadtest/docker-compose.loadtest.yml --profile loadtest)
DB_USER="$(grep -E '^DB_USER=' .env | cut -d= -f2-)"

mkdir -p "$RESULTS_DIR"

echo '==> 啟動壓測服務'
"${COMPOSE[@]}" up -d --build mock-external pgbouncer-loadtest web-loadtest

echo '==> 安全檢查：web-loadtest 的外部 API 必須指向 mock、金鑰必須為假值'
check_env() {
  local name="$1" expected="$2" actual
  actual="$("${COMPOSE[@]}" exec -T web-loadtest printenv "$name" || true)"
  if [[ "$actual" != "$expected" ]]; then
    echo "中止：${name}=${actual}（預期 ${expected}）" >&2
    exit 1
  fi
}
check_env GOOGLE_MAPS_BASE_URL http://mock-external:8080
check_env GOOGLE_API_KEY loadtest-fake-key
check_env LINE_API_HOST http://mock-external:8080
check_env LINE_CHANNEL_ACCESS_TOKEN loadtest-fake-token
check_env DB_NAME find_coffee_loadtest
"${COMPOSE[@]}" exec -T web-loadtest uv run --no-sync python manage.py shell -c "
from integrations.google.api import GoogleAPI
from line_bot.event_handlers import configuration
assert GoogleAPI.MAPS_BASE_URL == 'http://mock-external:8080', GoogleAPI.MAPS_BASE_URL
assert configuration.host == 'http://mock-external:8080', configuration.host
" >/dev/null 2>&1 || { echo '中止：程式內的 Google / LINE 位址不是 mock' >&2; exit 1; }

echo '==> 準備壓測資料庫'
if ! "${COMPOSE[@]}" exec -T db psql -U "$DB_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='find_coffee_loadtest'" | grep -q 1; then
  "${COMPOSE[@]}" exec -T db createdb -U "$DB_USER" find_coffee_loadtest
fi
"${COMPOSE[@]}" exec -T web-loadtest uv run --no-sync python manage.py migrate -v 0
"${COMPOSE[@]}" restart web-loadtest >/dev/null
until curl -s -o /dev/null -X POST http://localhost:8001/callback; do sleep 1; done

for scenario in "${SCENARIOS[@]}"; do
  echo "==> 情境 ${scenario}（VUS=${VUS}, ITERATIONS=${ITERATIONS}）"
  "${COMPOSE[@]}" exec -T -e SCENARIO="$scenario" -e GROUPS="$ITERATIONS" -e AGE_HOURS="${AGE_HOURS:-0}" web-loadtest \
    uv run --no-sync python loadtest/seed.py
  # 只清壓測用的 Redis db（2: cache/lock/state、3: celery broker），不碰開發環境的 db 0/1
  "${COMPOSE[@]}" exec -T redis redis-cli -n 2 FLUSHDB >/dev/null
  "${COMPOSE[@]}" exec -T redis redis-cli -n 3 FLUSHDB >/dev/null
  curl -s -X POST http://localhost:8081/__reset >/dev/null

  k6 run --quiet \
    -e SCENARIO="$scenario" -e VUS="$VUS" -e ITERATIONS="$ITERATIONS" \
    --summary-export "$RESULTS_DIR/$scenario.json" \
    loadtest/k6/carousel_search.js

  curl -s http://localhost:8081/__stats > "$RESULTS_DIR/$scenario.mock_stats.json"
  echo "mock 呼叫次數：$(cat "$RESULTS_DIR/$scenario.mock_stats.json")"
done

"${COMPOSE[@]}" exec -T redis redis-cli -n 3 FLUSHDB >/dev/null
echo "==> 結果存放於 ${RESULTS_DIR}"
