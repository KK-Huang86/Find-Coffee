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
- `refresh_cafe_now(cafe) -> bool`：取得 `LockService.acquire(str(cafe.id), 'refresh', ttl=600)`，成功才呼叫 Places Detail 並更新欄位（見 Decision 8），成功回傳 `True`。取不到 lock、刷新回傳非 `success`、或拋出例外，皆記錄 log 並回傳 `False`，呼叫端沿用既有資料。
- `refresh_cafe_if_stale(cafe) -> bool`：過期才呼叫 `refresh_cafe_now`。
- `refresh_photo_reference(place_id, old_reference) -> str | None`：照片 reference 被拒時呼叫 `refresh_cafe_now`，回傳新的 reference（見 Decision 5）。
- 理由：「什麼時候要重抓店家資料」的判斷（30 天過期、照片 reference 被拒）全部集中在這個模組，單筆、多筆、照片重試三處共用同一份 lock 與失敗處理；builder 層只負責呼叫，不自己做資料決策。

**2. 照片失效時做完整刷新，而非只取 photo 欄位**
- reference 失效的店家幾乎都已超過 30 天，本來就該完整刷新。只取 photo 會導致之後 30 天刷新再打一次完整 Detail，總共兩次；完整刷新會重設 `last_refreshed`，總共只打一次。
- legacy 計價下完整 Detail 約 $25/1000 次，只取 photo 約 $17/1000 次，差距小於多打一次的成本。

**3. lock 共用 `refresh` key，TTL 600 秒**
- 刷新成功後 `last_refreshed` 已更新、reference 已換新，下次請求不會再進刷新流程，lock 是否到期不影響。
- 刷新失敗時 600 秒內不再重試，防止每次查詢都打一次 Detail。
- 同一請求內「過期刷新」與「照片重試刷新」共用 lock：過期刷新後若照片仍失敗，代表不是 reference 過期，照片重試會因取不到 lock 而跳過，不會再打一次 Detail。
- 前提是移除 `event_handlers.py` 中先行取得 `refresh` lock 的 `.delay()`；否則同步刷新永遠取不到 lock。

**4. 多筆結果分兩階段平行：先刷新過期店家，再解析照片**
- 兩個階段共用 `LineMessageBuilder._run_concurrently(items, worker, key, fallback, error_label)`：負責 `ThreadPoolExecutor`、每個 worker 結束前 `connections.close_all()`（沿用 `parallelize-carousel-photo-resolve` Decision 3）、單一 item 例外時記錄並回退 fallback。
- 階段一：對 DB 命中且過期的店家平行呼叫 `refresh_cafe_now`。完成後以刷新後的 `cafe.to_dict()` 作為該店資訊。
- 階段二：沿用既有 `_resolve_photo_urls_concurrently`，不變更其介面。
- 理由：保留既有照片平行解析的介面與測試；兩階段最壞等待時間為「最慢刷新 + 最慢照片解析」，與每店 pipeline 的最壞情況相近。
- 替代方案：每店一個 worker 依序做「刷新 → 解析照片」。放棄原因：需改變既有 `_resolve_photo_urls_concurrently` 的回傳介面，效能差異不大。

**5. `get_photo_url` 遇到 400/403 時刷新並重試一次**
- `resolve_photo_url(photo_reference, on_rejected=None)`：HEAD 請求拆到 `_request_photo_url(photo_reference) -> (url, status_code)`；status 為 400 或 403 且有 `on_rejected` 時呼叫它，回傳新 reference 才以新 reference 重新解析一次，最多重試一次。未提供 `on_rejected` 時維持原行為。
- `get_photo_url` 傳入 `on_rejected=lambda: refresh_photo_reference(place_id, photo_reference)`。`refresh_photo_reference`（位於 `cafe_refresh`）查出 `Cafe`，`refresh_cafe_now` 成功且新 reference 非空、與舊的不同，才回傳新 reference；reference 未改變時記錄「被拒原因非 reference 過期」。
- 以 callback 注入而非讓 `get_photo_url` 自己判斷 status，是為了維持 `resolve_photo_url` 仍回傳 `str`，既有呼叫端不受影響。
- 400 與 403 都處理：實測同一個過期 reference 先後回應 403 與 400；403 也可能是金鑰或額度問題，由 Decision 7 的暫停機制避免浪費。
- 不論重試結果，`_trigger_s3_upload` 仍只呼叫一次（維持既有解耦）。

**6. 同步刷新不觸發「首次」S3 上傳**
- 沒有 S3 照片時，`refresh_cafe_now` 不送上傳 task；請求流程中統一由 `get_photo_url` → `_trigger_s3_upload` 觸發，避免同一次請求重複送出。
- 已有 S3 照片但超過 180 天的「重新下載」由 `refresh_cafe_now` 送出（Decision 8），此時 `get_photo_url` 看到 S3 照片存在不會觸發，兩者不重複。

**7. Places Detail 非 `OK` 時記錄並暫停**
- `get_shop_detail` 在 `status != 'OK'` 時記錄 `status`、`error_message` 與 `place_id`（不含 API key）。
- `REQUEST_DENIED` 或 `OVER_QUERY_LIMIT` 時設定 cache key `google:places_detail:paused`（TTL 300 秒）；暫停期間 `get_shop_detail` 直接回傳 `{}` 並記錄 log，不發出請求。
- 理由：金鑰或額度問題會讓所有店家的 Detail 都失敗，不暫停的話每間店都會白打一次。

**8. 刪除 `refresh_cafe_data` task，180 天照片更新維持背景執行**
- 30 天資料刷新全部改為請求流程中同步執行後，已沒有任何地方以 `.delay()` 呼叫 `refresh_cafe_data`。保留它會讓讀者在 `tasks.py` 與 `cafe_refresh.py` 之間來回跳，且 `trigger_photo_upload` 參數只是為了相容這個歷史包袱。
- 「打 Places Detail + 更新欄位 + 觸發 AI 摘要」搬進 `cafe_refresh.refresh_cafe_now`（`_apply_google_detail`），task 刪除，`trigger_photo_upload` 參數一併移除。
- 寫入失敗時 `cafe.refresh_from_db()`，丟掉已套用到記憶體但沒寫入成功的欄位，呼叫端不會拿到半套新資料。
- 180 天照片更新：同步刷新成功後，若 S3 照片的 `photo_updated_at` 已達 180 天，送出 `download_and_upload_cafe_photo.delay(cafe.id, force=True)`。**不再先清空 `photo_s3_url`**：新照片上傳完成前使用者仍看到舊照片，不會在這段期間退回即時解析或預設圖。`download_and_upload_cafe_photo` 新增 `force` 參數，已有 S3 照片時仍重新下載並覆蓋。
- 已知限制：S3 key 固定為 `cafe-photos/{place_id}.jpg`，上傳時設定 `CacheControl: max-age=31536000`，覆蓋同一個 key 後 CloudFront 與 LINE 端可能仍快取舊圖。此問題在本次修改前即存在，另開 change 處理（例如 key 加上版本）。
- 部署注意：佇列中若殘留舊的 `refresh_cafe_data` 訊息，worker 會回報 unregistered task；部署前確認佇列中沒有該 task。

## Risks / Trade-offs

- [Trade-off] 有過期店家時回覆變慢：最壞約「Detail 5 秒 + 照片解析約 6 秒 + 照片重試的 Detail 5 秒 + 解析約 6 秒」。換取使用者拿到的是最新資料與真實照片。LINE reply token 有效時間可涵蓋，但 webhook 處理時間變長。
- [風險] 同步刷新在 worker 執行緒內寫入 DB → 每個 worker 結束前 `connections.close_all()`；同一間店由 `refresh` lock 防止並發寫入。
- [風險] 多人同時查詢同一間過期店家：只有取得 lock 的請求會刷新，其他請求沿用舊資料回覆（不等待）。
- [風險] LocMem cache 在測試間共用 → 相關測試需在前後清除 cache，避免 lock 互相影響。
- [風險] `refresh_cafe_data` 寫入時若遇到 `DataError`（例如網址超過 200 字元）會拋出例外 → `refresh_cafe_now` 捕捉並記錄，沿用既有資料回覆。
