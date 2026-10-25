## Context

- 單筆結果：`get_or_create_cafe_info`（`line_bot/handlers/helpers.py`）已在 DB 命中時同步呼叫 `refresh_cafe_data(cafe.id)`，但沒有 lock，也沒有處理例外。
- 多筆結果：`LineMessageBuilder.send_shop_result` 以 `Cafe.objects.filter(place_id__in=...)` 批次取得快取，直接 `to_dict()`，不檢查是否過期。照片已由 `_resolve_photo_urls_concurrently` 平行解析。
- 店名搜尋：`event_handlers.py` 在呼叫 `send_shop_result` 之前，對每間過期店家取得 `refresh` lock 並 `refresh_cafe_data.delay()`。
- `refresh_cafe_data` 在店家沒有 S3 照片時會 `download_and_upload_cafe_photo.delay()`；請求流程中 `get_photo_url` 也會呼叫 `_trigger_s3_upload`，兩者在同一次請求會重複送出上傳 task。
- `LockService.acquire` 為 `cache.add`（SETNX + TTL），沒有 release，只能等 TTL 到期。
- `GoogleAPI.get_shop_detail` 在 Places 回應 `status != 'OK'` 時直接回傳 `{}`，不記錄原因。

## Goals / Non-Goals

**Goals:**
- 使用者拿到的店家資料不超過 30 天；過期資料在回覆前更新
- 照片 reference 失效時能在同一次請求內自我修復
- 同一間店不會因多人同時查詢、或同一請求內多個觸發點而重複呼叫 Places Detail
- 失敗原因（reference 失效、金鑰/額度、逾時）可從 log 區分

**Non-Goals:**
- 不平行化多筆結果中「DB 沒有、需向 Google 新建」的店家（`_get_or_create_shop_info` 依序呼叫），維持既有行為
- 不修正 `Cafe.website` / `google_maps`（`URLField` 預設 `max_length=200`）過長導致寫入失敗的問題；本次僅確保該例外不會中斷回覆，另開 change 處理
- 不另外實作「只取 photo 欄位」的 Detail 呼叫（見 Decision 2）
- 不批次補救既有 267 間店；本次機制會在使用者查到時自動修復

## Decisions

**1. 同步刷新抽成 `cafe/services/cafe_refresh.py`**
- `is_cafe_stale(cafe)`：`last_refreshed` 為空或距今 ≥ 30 天。
- `refresh_cafe_now(cafe) -> bool`：取得 `LockService.acquire(str(cafe.id), 'refresh', ttl=600)`，成功才呼叫 `refresh_cafe_data(cafe.id, trigger_photo_upload=False)`；成功時 `cafe.refresh_from_db()` 並回傳 `True`。取不到 lock、刷新回傳非 `success`、或拋出例外，皆記錄 log 並回傳 `False`，呼叫端沿用既有資料。
- `refresh_cafe_if_stale(cafe) -> bool`：過期才呼叫 `refresh_cafe_now`。
- 理由：單筆、多筆、照片重試三處共用同一份 lock 與失敗處理，避免邏輯分散。

**2. 照片失效時做完整刷新，而非只取 photo 欄位**
- reference 失效的店家幾乎都已超過 30 天，本來就該完整刷新。只取 photo 會導致之後 30 天刷新再打一次完整 Detail，總共兩次；完整刷新會重設 `last_refreshed`，總共只打一次。
- legacy 計價下完整 Detail 約 $25/1000 次，只取 photo 約 $17/1000 次，差距小於多打一次的成本。

**3. lock 共用 `refresh` key，TTL 600 秒**
- 刷新成功後 `last_refreshed` 已更新、reference 已換新，下次請求不會再進刷新流程，lock 是否到期不影響。
- 刷新失敗時 600 秒內不再重試，防止每次查詢都打一次 Detail。
- 同一請求內「過期刷新」與「照片重試刷新」共用 lock：過期刷新後若照片仍失敗，代表不是 reference 過期，照片重試會因取不到 lock 而跳過，不會再打一次 Detail。
- 前提是移除 `event_handlers.py` 中先行取得 `refresh` lock 的 `.delay()`；否則同步刷新永遠取不到 lock。

**4. 多筆結果分兩階段平行：先刷新過期店家，再解析照片**
- 階段一：對 DB 命中且過期的店家，以 `ThreadPoolExecutor` 平行呼叫 `refresh_cafe_if_stale`，worker 結束前 `connections.close_all()`（沿用 `parallelize-carousel-photo-resolve` Decision 3）。完成後以刷新後的 `cafe.to_dict()` 作為該店資訊。
- 階段二：沿用既有 `_resolve_photo_urls_concurrently`，不變更其介面。
- 理由：保留既有照片平行解析的介面與測試；兩階段最壞等待時間為「最慢刷新 + 最慢照片解析」，與每店 pipeline 的最壞情況相近。
- 替代方案：每店一個 worker 依序做「刷新 → 解析照片」。放棄原因：需改變既有 `_resolve_photo_urls_concurrently` 的回傳介面，效能差異不大。

**5. `get_photo_url` 遇到 400/403 時刷新並重試一次**
- `resolve_photo_url(photo_reference, on_rejected=None)`：HEAD 請求拆到 `_request_photo_url(photo_reference) -> (url, status_code)`；status 為 400 或 403 且有 `on_rejected` 時呼叫它，回傳新 reference 才以新 reference 重新解析一次，最多重試一次。未提供 `on_rejected` 時維持原行為。
- `get_photo_url` 傳入 `on_rejected=lambda: _refresh_photo_reference(place_id, photo_reference)`。`_refresh_photo_reference` 查出 `Cafe`，`refresh_cafe_now` 成功且新 reference 非空、與舊的不同，才回傳新 reference；reference 未改變時記錄「被拒原因非 reference 過期」。
- 以 callback 注入而非讓 `get_photo_url` 自己判斷 status，是為了維持 `resolve_photo_url` 仍回傳 `str`，既有呼叫端不受影響。
- 400 與 403 都處理：實測同一個過期 reference 先後回應 403 與 400；403 也可能是金鑰或額度問題，由 Decision 7 的暫停機制避免浪費。
- 不論重試結果，`_trigger_s3_upload` 仍只呼叫一次（維持既有解耦）。

**6. 同步刷新不觸發 S3 上傳**
- `refresh_cafe_data` 新增 `trigger_photo_upload=True` 參數；同步刷新傳 `False`。請求流程中統一由 `get_photo_url` → `_trigger_s3_upload` 觸發，該函式讀取 DB 最新的 `photo_s3_url`，180 天照片過期被清空時也能正確觸發。
- Celery 直接呼叫（預設 `True`）行為不變。

**7. Places Detail 非 `OK` 時記錄並暫停**
- `get_shop_detail` 在 `status != 'OK'` 時記錄 `status`、`error_message` 與 `place_id`（不含 API key）。
- `REQUEST_DENIED` 或 `OVER_QUERY_LIMIT` 時設定 cache key `google:places_detail:paused`（TTL 300 秒）；暫停期間 `get_shop_detail` 直接回傳 `{}` 並記錄 log，不發出請求。
- 理由：金鑰或額度問題會讓所有店家的 Detail 都失敗，不暫停的話每間店都會白打一次。

## Risks / Trade-offs

- [Trade-off] 有過期店家時回覆變慢：最壞約「Detail 5 秒 + 照片解析約 6 秒 + 照片重試的 Detail 5 秒 + 解析約 6 秒」。換取使用者拿到的是最新資料與真實照片。LINE reply token 有效時間可涵蓋，但 webhook 處理時間變長。
- [風險] 同步刷新在 worker 執行緒內寫入 DB → 每個 worker 結束前 `connections.close_all()`；同一間店由 `refresh` lock 防止並發寫入。
- [風險] 多人同時查詢同一間過期店家：只有取得 lock 的請求會刷新，其他請求沿用舊資料回覆（不等待）。
- [風險] LocMem cache 在測試間共用 → 相關測試需在前後清除 cache，避免 lock 互相影響。
- [風險] `refresh_cafe_data` 寫入時若遇到 `DataError`（例如網址超過 200 字元）會拋出例外 → `refresh_cafe_now` 捕捉並記錄，沿用既有資料回覆。
