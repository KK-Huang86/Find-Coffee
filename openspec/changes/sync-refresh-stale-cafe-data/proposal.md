## Why

多筆搜尋結果的照片幾乎都顯示預設圖。追查後確認：DB 中有 267 間店沒有 S3 照片，且 `last_refreshed` 全部超過 30 天，存的 Google `photo_reference` 已失效，Google Photo API 對其回應 400 或 403（同一個 reference 先後出現過兩種狀態碼）。背景 S3 上傳也因相同原因持續失敗，這些店永遠進不了 S3。

資料更新目前有三個缺口：

1. **多筆結果完全不檢查資料是否過期**：`send_shop_result` 的多筆分支直接使用 DB 快取的 `to_dict()`，沒有任何刷新。
2. **店名搜尋另外以 `refresh_cafe_data.delay()` 背景刷新**：本次回覆仍使用舊資料；單筆結果又會在 `get_or_create_cafe_info` 中同步刷新一次，同一間店重複呼叫 Places Detail。地址、行政區、位置搜尋則完全不會觸發刷新。
3. **照片 reference 失效時沒有自我修復**：資料未滿 30 天但 reference 已失效時，只能回退預設圖，直到 30 天後才有機會更新。

使用者看到的資料過期卻只在背景更新，本次回覆仍是舊資料，體驗不佳。

## What Changes

- 過期（`last_refreshed` 為空或超過 30 天）的店家資料一律**在回覆前同步更新**，單筆與多筆結果皆同；多筆結果以 `ThreadPoolExecutor` 平行更新，整體等待時間不隨過期店家數量線性增加
- 移除店名搜尋中的 `refresh_cafe_data.delay()` 背景刷新，避免與同步刷新重複呼叫 Places Detail
- 同一間店的刷新以 Redis lock（`lock:<cafe_id>:refresh`，TTL 600 秒）限制，TTL 內最多刷新一次；同步刷新失敗或拋出例外時回退使用既有資料並記錄 log，不阻斷回覆
- Google Photo API 回應 400 或 403 時，於同一執行緒同步刷新該店資料取得新的 `photo_reference`，並以新 reference 重新解析一次（最多重試一次）
- 同步刷新不觸發首次 S3 上傳，統一由 `get_photo_url` 觸發，避免同一次請求重複送出上傳 task
- 刪除 `refresh_cafe_data` Celery task（已無非同步呼叫端），刷新邏輯移入 `cafe/services/cafe_refresh.py`；S3 照片超過 180 天時維持以背景任務重新下載，且不先清空舊照片
- `GoogleAPI.get_shop_detail` 在 Places 回應非 `OK` 時記錄 `status` 與 `error_message`；遇到 `REQUEST_DENIED` 或 `OVER_QUERY_LIMIT`（金鑰或額度問題，非 reference 過期）時暫停所有 Places Detail 呼叫 300 秒，避免每間店都白打一次

## Capabilities

### New Capabilities

- `cafe-data-refresh`：定義店家資料過期時的同步更新、重複更新防護、失敗回退與外部服務拒絕時的暫停行為

### Modified Capabilities

- `cafe-photo-loading`：新增「照片識別碼被外部來源拒絕時同步更新並重試一次」需求

## Impact

- `cafe/services/cafe_refresh.py`（新增）：過期判斷、同步刷新（含 lock 與失敗回退）
- `cafe/tasks.py`：刪除 `refresh_cafe_data`；`download_and_upload_cafe_photo` 新增 `force` 參數
- `line_bot/handlers/helpers.py`：`get_or_create_cafe_info` 改用共用的同步刷新服務
- `line_bot/builders/message_sender.py`：多筆結果先平行刷新過期店家，再平行解析照片
- `line_bot/builders/shop_flex_message.py`：`get_photo_url` 遇到 400/403 時刷新並重試
- `line_bot/event_handlers.py`：移除 `refresh_cafe_data.delay()`
- `integrations/google/api.py`：`get_shop_detail` 記錄非 `OK` status，並加入暫停機制
- 同步刷新不計入使用者的 Places Detail 月額度（與既有 `get_or_create_cafe_info` 的同步刷新行為一致）
- 回應時間：有過期店家時，回覆前多一次 Places Detail（timeout 5 秒）；照片 reference 失效時再多一次 Detail 與一次照片解析
