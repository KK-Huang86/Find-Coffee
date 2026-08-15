## Why

搜尋結果組裝店家照片時，目前的邏輯把「同步向 Google 解析照片 URL」與「是否觸發背景上傳到 S3」綁在一起：只有同步解析成功，才會觸發 S3 背景快取；一旦逾時（`timeout=2` 秒），不只顯示預設圖，連背景快取都完全不會被觸發，導致同一間店下次被搜尋時又要重新賭一次同步解析。更嚴重的是，多筆結果（carousel，2-10 間店）會依序對每間未快取的店家各自進行一次同步解析，最差情況下（10 間店皆未快取）會讓整個 LINE webhook 回應被同步阻塞長達 10 × 2 秒 = 20 秒，遠超過合理的回應時間、也可能讓 LINE reply token 過期。

## What Changes

- `FlexMessageBuilder.get_photo_url` 新增 `allow_sync_resolve` 參數（預設 `True`），由 `create_shop_flex_message` 依既有的 `is_multiple` 旗標換算傳入（`allow_sync_resolve = not is_multiple`）：
  - 單筆結果（`is_multiple=False`）：維持現行行為，同步呼叫 `resolve_photo_url` 並等待最多 2 秒
  - 多筆結果（`is_multiple=True`）：跳過同步解析，`photo_s3_url` 未命中時直接回傳預設圖，不再逐間阻塞
- 移除 `_trigger_s3_upload` 觸發條件對「同步解析是否成功」的依賴：只要店家有 `photo_reference` 且 DB 中 `photo_s3_url` 仍為空，無論這次是否嘗試同步解析、解析成功與否，皆觸發背景上傳；`_trigger_s3_upload` 內部既有的 `not cafe.photo_s3_url` 二次確認機制維持不變，避免重複觸發
- 不調整 `resolve_photo_url` 的 `timeout=2` 秒數值，本次變更範圍不含逾時時間的調整（詳見 design.md）

## Capabilities

### New Capabilities
- `cafe-photo-loading`：描述搜尋結果組裝店家照片時的載入與背景快取行為，包含單筆／多筆結果的差異化處理、S3 背景快取觸發時機

### Modified Capabilities
（無現有 capability 需要修改，此為新增行為描述）

## Impact

- **受影響程式碼**：
  - `line_bot/builders/shop_flex_message.py`（`FlexMessageBuilder.get_photo_url`、`create_shop_flex_message`、`_trigger_s3_upload` 觸發邏輯）
  - `line_bot/tests/builders/test_shop_flex_message.py`（新增/調整對應測試）
- **不受影響**：`resolve_photo_url` 本身的實作與 timeout 數值、`cafe/tasks.py` 的 `download_and_upload_cafe_photo`（本來就已獨立於同步解析結果之外組裝照片 URL）、呼叫端（`message_sender.py`、`favorites_page.py`）的介面
- **使用者可感受到的變化**：多筆搜尋結果的回應時間上限大幅降低（不再隨未快取店家數量疊加等待）；同一間店在被背景快取後，之後任何搜尋（含多筆結果）都能命中 S3/CloudFront 的穩定連結，而不必仰賴「剛好曾經同步解析成功過」
