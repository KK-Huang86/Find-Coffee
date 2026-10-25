## 1. 測試（TDD 紅燈）

- [x] 1.1 新增 `cafe/tests/test_cafe_refresh.py`：`is_cafe_stale`（None、31 天、剛好 30 天、29 天 23 小時、剛刷新）；`refresh_cafe_now`（成功以 `trigger_photo_upload=False` 呼叫並重新載入、TTL 內重複呼叫只刷新一次、lock 依店家分開、lock 被持有時跳過、lock 參數為 `(cafe.id, 'refresh', ttl=600)`、回傳 failed 時 warning、拋例外時 error 且不外拋、失敗後 lock 保留）；`refresh_cafe_if_stale`（未過期不刷新、過期與 None 會刷新）
- [x] 1.2 `cafe/tests/test_tasks.py`：`trigger_photo_upload=False` 時無 S3 照片不觸發上傳、照片超過 180 天時仍清除但不觸發上傳
- [x] 1.3 `integrations/tests/test_google_api.py`：非 `OK` 記錄 status / error_message / place_id、log 不含 API key、`REQUEST_DENIED` / `OVER_QUERY_LIMIT` 暫停後續呼叫、暫停 TTL 300 秒、暫停期間記錄被跳過、`NOT_FOUND` / `INVALID_REQUEST` / `ZERO_RESULTS` 不暫停
- [x] 1.4 `line_bot/tests/builders/test_shop_flex_message.py`：`resolve_photo_url` 的 `on_rejected`（400/403 重試新 reference、新 reference 仍被拒只重試一次、回傳 None 不重試、其他非 200 與逾時不觸發、成功不觸發、未提供時維持原行為）；`get_photo_url` 傳入刷新本店的 callback、刷新後 S3 上傳仍只觸發一次、`allow_sync_resolve=False` 不刷新；`_refresh_photo_reference`（成功回傳新 reference、找不到店家、刷新跳過或失敗、reference 未改變、刷新後為空、place_id 為空、例外記錄 error）
- [x] 1.5 `line_bot/tests/builders/test_message_sender.py`：多筆結果只刷新過期店家、回覆使用刷新後資料、刷新先於照片解析、刷新失敗沿用快取、單一 worker 例外不影響其他店、無過期店家不刷新、每個 worker 關閉 DB 連線、`Barrier` 證明平行刷新
- [x] 1.6 `line_bot/tests/test_helpers.py`：委派給 `refresh_cafe_if_stale`、回傳刷新後資料、刷新失敗回傳既有資料
- [x] 1.7 `line_bot/tests/test_event_handlers.py`：店名搜尋命中過期店家不送 `refresh_cafe_data.delay`
- [x] 1.8 測試基礎設施：根目錄 `conftest.py` 每個測試前後清空 LocMemCache（lock / 暫停旗標不跨測試殘留）；`line_bot/tests/conftest.py` 預設擋下 Places Detail 真實呼叫
- [x] 1.9 實作前執行：新增測試 43 failed（`test_cafe_refresh.py` 因模組不存在無法 collect），既有測試全數通過

### 既有測試的調整（商業邏輯變更）

- `test_helpers.py` 的 `test_refreshes_stale_cafe_data`、`test_refreshes_when_last_refreshed_is_none`：原本斷言 `refresh_cafe_data(cafe.id)`，改為斷言委派給 `refresh_cafe_if_stale`；過期 / None 的邊界移到 `test_cafe_refresh.py` 覆蓋。原因：刷新加入 lock 與失敗回退，且不再由刷新觸發 S3 上傳。
- `test_shop_flex_message.py` 的 `test_resolves_google_photo_when_no_s3_url`、`test_allow_sync_resolve_true_explicit_matches_default`：`assert_called_once_with('ref123')` 改為 `assert_called_once()` + 第一個參數為 `'ref123'`。原因：`get_photo_url` 額外傳入 `on_rejected` callback。

## 2. 實作

- [x] 2.1 新增 `cafe/services/cafe_refresh.py`（`is_cafe_stale`、`refresh_cafe_now`、`refresh_cafe_if_stale`）
- [x] 2.2 `cafe/tasks.py`：`refresh_cafe_data` 新增 `trigger_photo_upload=True`
- [x] 2.3 `integrations/google/api.py`：`get_shop_detail` 記錄非 `OK` status，`REQUEST_DENIED` / `OVER_QUERY_LIMIT` 暫停 300 秒
- [x] 2.4 `line_bot/builders/shop_flex_message.py`：`resolve_photo_url` 新增 `on_rejected`、拆出 `_request_photo_url`、新增 `_refresh_photo_reference`，`get_photo_url` 傳入 callback
- [x] 2.5 `line_bot/builders/message_sender.py`：多筆結果先以 `_refresh_stale_cafes_concurrently` 平行刷新過期店家
- [x] 2.6 `line_bot/handlers/helpers.py`：改用 `refresh_cafe_if_stale`
- [x] 2.7 `line_bot/event_handlers.py`：移除 `refresh_cafe_data.delay()` 與未使用的 import

## 3. 驗證

- [x] 3.1 `uv run pytest -q` 全數通過（501 passed）；平行相關測試重複執行 5 次無 flaky
- [x] 3.2 `uv run ruff check .`、`uv run python manage.py check`、`makemigrations --check --dry-run` 通過
- [x] 3.3 本機 Docker 實測：對 3 間 `photo_reference` 已失效、超過 30 天的店家執行多筆結果，3 間皆同步刷新並顯示 `lh3.googleusercontent.com` 真實照片，每間只送出一次 S3 上傳 task，Celery 上傳全部成功
- [x] 3.4 `openspec validate sync-refresh-stale-cafe-data --strict` 通過

## 4. 重構（測試維持全綠）

- [x] 4.1 `message_sender.py`：刷新與照片解析兩組 thread pool 寫法重複，抽成 `_run_concurrently`；移除 `_refresh_single_cafe`、`_resolve_single_photo_url`。測試未修改。
- [x] 4.2 `_refresh_photo_reference` 由 `FlexMessageBuilder` 搬到 `cafe/services/cafe_refresh.py` 的 `refresh_photo_reference`，「是否重抓」的判斷全部集中在 `cafe_refresh`。對應測試隨程式碼搬到 `cafe/tests/test_cafe_refresh.py`，斷言不變，只改呼叫對象與 patch 目標；`get_photo_url` 接線測試的 patch 目標改為 `line_bot.builders.shop_flex_message.refresh_photo_reference`。
- [x] 4.3 `uv run pytest -q` 501 passed（數量與重構前相同）；`uv run ruff check .` 通過。
