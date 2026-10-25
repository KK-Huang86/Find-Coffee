## Why

`sync-refresh-stale-cafe-data` 讓過期店家在回覆前同步刷新，回應時間會變長，但只有估算，沒有實際數字。直接對開發環境壓測會打到真的 Google Places（費用、額度）與 LINE API（推播），因此需要一個完全隔離、外部 API 皆為 mock 的壓測環境。

## What Changes

- Google Maps 與 LINE Messaging API 的位址改為可由環境變數設定（`GOOGLE_MAPS_BASE_URL`、`LINE_API_HOST`），預設值維持正式網址，不影響既有環境
- Google 端點集中在 `GoogleAPI.MAPS_BASE_URL` / `BASE_URL` / `PHOTO_URL` / `GEOCODE_URL`，取代散落在 `integrations/google/api.py`、`cafe/tasks.py`、`line_bot/builders/shop_flex_message.py` 的寫死網址
- 新增 `loadtest/`：mock server、隔離的 docker compose 服務、資料準備腳本、K6 腳本與一鍵執行腳本，量測多筆搜尋三種情境（全部快取、資料過期、照片 reference 失效）的回應時間

## Capabilities

### New Capabilities

- `external-api-endpoints`：外部 API 位址可由設定切換，且壓測環境不得呼叫真實外部服務

### Modified Capabilities

（無）

## Impact

- `integrations/google/api.py`、`cafe/tasks.py`、`line_bot/builders/shop_flex_message.py`：改用 `GoogleAPI` 的端點常數
- `line_bot/event_handlers.py`、`line_bot/views.py`：`Configuration(host=LINE_API_HOST, ...)`
- `.env.example`：新增兩個選填變數
- 新增 `loadtest/`（`mock_server.py`、`docker-compose.loadtest.yml`、`seed.py`、`k6/carousel_search.js`、`run.sh`、`README.md`）；`loadtest/results/` 加入 `.gitignore`
- 壓測服務皆設定 compose `profiles: [loadtest]`，一般 `docker compose up` 不會啟動
