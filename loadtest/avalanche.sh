#!/usr/bin/env bash
# 快取雪崩防護驗證。
# 1) 刷新門檻分散：同一批匯入的 300 間店（30 組 × 10 間），在不同「匯入後經過天數」各跑一輪搜尋，
#    統計每輪被判定過期而同步刷新的 Places Detail 次數。固定 30 天門檻時應為 0、0、…、300。
# 2) TTL 隨機偏移：以 ITERATIONS 個不同地址寫入 Geocoding / Nearby Search 快取，讀取 Redis 剩餘 TTL 的分布。
#    沒有偏移時，所有 key 會在寫入期間內同時過期。
# 用法：loadtest/avalanche.sh   可調參數：AGES_DAYS="24 25 26 27 28 29 30" TTL_ITERATIONS=100
set -euo pipefail

cd "$(dirname "$0")/.."
AGES_DAYS="${AGES_DAYS:-24 25 26 27 28 29 29.9 30}"
TTL_ITERATIONS="${TTL_ITERATIONS:-100}"
OUT="loadtest/results/avalanche-$(date +%Y%m%d-%H%M%S)"
COMPOSE=(docker compose -f docker-compose.yml -f loadtest/docker-compose.loadtest.yml --profile loadtest)
mkdir -p "$OUT"

echo '==> 1. 刷新門檻分散（refresh_spread，300 間店同一時間匯入）'
for days in $AGES_DAYS; do
  hours="$(python3 -c "print(${days} * 24)")"
  stats="$(AGE_HOURS="$hours" VUS=5 ITERATIONS=30 loadtest/run.sh refresh_spread | grep 'mock 呼叫次數' | sed 's/^mock 呼叫次數：//')"
  detail="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('google_detail', 0))" "$stats")"
  echo "匯入後 ${days} 天：Places Detail ${detail} 次" | tee -a "$OUT/refresh_spread.txt"
done

echo "==> 2. TTL 隨機偏移（${TTL_ITERATIONS} 個不同地址）"
VUS=5 ITERATIONS="$TTL_ITERATIONS" loadtest/run.sh address_cold | grep -E 'mock 呼叫次數|search_duration' | tee "$OUT/ttl_warm.txt"
# 寫入期間 = k6 執行時間（iterations 次數 / 每秒 iterations）；沒有偏移時，所有 key 會在這段時間內全部過期
summary="$(ls -td loadtest/results/*/ | grep -v avalanche | head -1)address_cold.json"
python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))['metrics']['iterations']
print(f'寫入期間約 {m[\"count\"] / m[\"rate\"]:.1f} 秒')
" "$summary" | tee -a "$OUT/ttl_warm.txt"
"${COMPOSE[@]}" exec -T web-loadtest uv run --no-sync python loadtest/analyze_ttl.py | tee "$OUT/ttl.json"

echo "==> 結果存放於 ${OUT}"
