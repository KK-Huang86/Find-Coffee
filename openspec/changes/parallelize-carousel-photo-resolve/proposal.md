## Why

`fix-cafe-google-url-timeout` change 上線後，多筆搜尋結果（carousel）完全跳過同步解析，未快取的店家一律直接顯示預設圖，即使 Google 端其實可以在極短時間內回應。這解決了原本 N 間店 × 2 秒疊加逾時的問題，但代價是使用者體驗上「多筆結果幾乎都是死圖」，犧牲過大。實際上疊加風險的根源是「依序、逐間」呼叫 Google，而非「呼叫 Google」本身——把多筆店家的解析改成同時（並行）發出，就能讓大部分店家仍有機會拿到真實照片，同時把整批請求的最差等待時間限制在接近單一店家的等待時間（約 2 秒），而不是隨店家數量疊加。

## What Changes

- 多筆搜尋結果（carousel，2-10 間店）改為對所有尚未快取照片的店家**平行**發出 Google Photo 解析請求（`ThreadPoolExecutor`），取代目前「完全跳過同步解析」的行為
- 平行解析的整體等待時間不因店家數量增加而線性增加，維持在接近單一店家解析所需的時間（沿用既有 `resolve_photo_url` 的 `timeout=2` 不變）
- 任一店家解析逾時或失敗時，該店家單獨回退為預設圖，不影響其他店家的解析結果，也不阻塞整體回覆（不要求「全部解析完成」才能回覆，儘量取得最多筆真實照片後即可組裝結果）
- 背景 S3 快取觸發時機維持既有的解耦邏輯（`fix-cafe-google-url-timeout` 已建立）：不論平行解析成功、失敗、或逾時，只要有 `photo_reference` 且尚未快取即觸發
- 單筆結果的行為不變（仍是同步等待、逾時才顯示預設圖）
- 修改 `cafe-photo-loading` capability 中「多筆搜尋結果照片載入不得逐筆同步等待」相關需求，反映改為並行嘗試而非完全跳過

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `cafe-photo-loading`：多筆搜尋結果照片載入行為由「完全不嘗試解析」改為「平行嘗試解析所有未快取店家，整體等待時間不隨店家數量疊加」

## Impact

- **受影響程式碼**：
  - `line_bot/builders/message_sender.py`（`send_shop_result` 多筆結果分支，需先平行解析所有未快取店家的照片，再組裝 Flex Message）
  - `line_bot/builders/shop_flex_message.py`（`create_shop_flex_message` 需能接受外部已解析好的照片 URL，避免內部再次呼叫 `get_photo_url` 而重新走一次序列邏輯）
  - `line_bot/tests/builders/test_message_sender.py`、`line_bot/tests/builders/test_shop_flex_message.py`（新增/調整對應測試）
- **不受影響**：單筆結果路徑（`allow_sync_resolve` 相關邏輯維持不變）、`resolve_photo_url` 的 `timeout=2`、`_trigger_s3_upload` 的觸發條件、`download_and_upload_cafe_photo` Celery task
- **新技術考量**：Django ORM 在非主執行緒中查詢資料庫（`_trigger_s3_upload` 內部的 `Cafe.objects.filter`）需注意連線管理，避免執行緒池用完後遺留未關閉的資料庫連線（詳見 design.md）
- **使用者可感受到的變化**：多筆搜尋結果中，大部分未快取店家仍有機會顯示真實照片（而非清一色預設圖），且整體回應時間不會因店家數量增加而拉長
