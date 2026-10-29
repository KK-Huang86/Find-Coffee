#!/usr/bin/env bash
# 補產缺漏的咖啡店 AI 摘要，在 docker compose 的 web container 內執行 backfill_ai_summary command
#
# 使用方式：
#   scripts/backfill_ai_summary.sh --dry-run                 # 先試跑，確認會處理幾間
#   scripts/backfill_ai_summary.sh --limit 20                # 實際排入，最多 20 間（每筆間隔預設 25 秒）
#
# 環境變數：
#   BACKFILL_SERVICE  執行 command 的 compose service（預設 web）
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose exec -T "${BACKFILL_SERVICE:-web}" \
  uv run --no-sync python manage.py backfill_ai_summary "$@"
