## Why

目前 Redis 中的快取都是每個使用者各自一把 key（對話狀態、搜尋歷史），沒有多人共用的資料快取。以下請求每次都直接打 Google，同一個查詢被很多人重複送出時，會重複花錢、消耗額度：

- 地址搜尋：每次都呼叫 Geocoding 與 Nearby Search
- 定位搜尋：每次都呼叫 Nearby Search
- 店名搜尋：DB 找不到時呼叫 Text Search
- 點選 DB 沒有的店：呼叫 Places Detail 並建立 `Cafe`

加上共用快取後，必須同時處理三個典型問題：

- **快取穿透**：查不到結果的查詢（不存在的店名、無效的 `place_id`）永遠不會命中快取，每次都打 Google
- **快取擊穿**：熱門 key 過期或新店第一次被點選時，多個請求同時打 Google；建立 `Cafe` 時還可能撞到 `place_id` unique 限制
- **快取雪崩**：大量 key 同時過期，請求一起打到 Google；DB 店家資料固定 30 天過期，同一批匯入的店會在同一天一起同步刷新

## What Changes

- 新增分散式鎖 `utils/distributed_lock.py`：Redis 環境使用 redis-py `Lock`（token + Lua 釋放，只刪除自己持有的鎖），非 Redis 的快取後端（測試的 LocMem）退回 `cache.add`
- 新增共用的 cache-aside 流程 `utils/cache_guard.py`：
  - 只快取確定的結果（Google 回 `OK` 或 `ZERO_RESULTS`）；逾時、連線失敗、被拒、額度用盡等暫時性錯誤不快取
  - 空結果也快取，但 TTL 較短（防穿透）
  - 快取未命中時以分散式鎖保護，同一個 key 同時只有一個請求打 Google；拿不到鎖的請求每 100ms 檢查快取，最多 2 秒，逾時後自行查詢（防擊穿，可用性優先）
  - TTL 加上 ±10% 隨機偏移（防雪崩）
- Google 搜尋結果快取：
  - Text Search：以正規化後的關鍵字為 key，TTL 24 小時
  - Geocoding：以正規化後的地址為 key，TTL 7 天
  - Nearby Search：經緯度四捨五入到小數第 4 位（約 11 公尺）為 key，TTL 24 小時
  - 空結果 TTL 10 分鐘
- Places Detail：
  - Google 回 `NOT_FOUND`、`INVALID_REQUEST` 時記錄「此 `place_id` 無效」1 小時；期間不打 Google、不扣使用者額度（防穿透）
  - `get_or_create_cafe_info` 建立新店時以 `place_id` 加分散式鎖；取得鎖後再查一次 DB（double-checked）；拿不到鎖的請求等待 DB 出現該店，最多 2 秒，逾時後自行建立；建立撞到 unique 限制時改讀既有資料（防擊穿）
- DB 店家資料刷新：過期門檻由固定 30 天改為依 `place_id` 決定的 25～30 天（防雪崩），保證資料不會超過 30 天未刷新

## Capabilities

### New Capabilities

- `distributed-lock`：可安全釋放的分散式鎖
- `google-search-cache`：Google 搜尋結果的共用快取與穿透、擊穿、雪崩防護
- `cafe-creation-protection`：新店建立流程的穿透與擊穿防護
- `cafe-refresh-jitter`：店家資料刷新門檻的分散

### Modified Capabilities

（無）

## Impact

- **新增**：`utils/distributed_lock.py`、`utils/cache_guard.py` 與對應測試
- **`integrations/google/api.py`**：搜尋與 Geocoding 改走快取；Places Detail 記錄無效 `place_id`
- **`line_bot/handlers/helpers.py`**：`get_or_create_cafe_info` 加上鎖與無效 `place_id` 檢查
- **`cafe/services/cafe_refresh.py`**：`is_cafe_stale` 改用分散的門檻
- **測試**：`cafe/tests/test_cafe_refresh.py` 中「未滿 30 天一定不過期」的邊界測試改為依門檻驗證（商業邏輯變更，見 design）
- Redis 用量增加：搜尋結果只存 `place_id`、店名與評分，單筆約數百 bytes
- 不影響 DB schema
