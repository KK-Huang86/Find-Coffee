## 1. 前置準備與基準驗證

- [ ] 1.1 確認目前在 `feature/fix-cafe-google-url-timeout` 分支。
- [ ] 1.2 `git add openspec/changes/fix-cafe-google-url-timeout/` 並建立 commit，將本 change 的 proposal/specs/design/tasks 規劃文件單獨提交，使工作目錄回到乾淨狀態（後續 TDD 步驟才能用 `git status` 判斷「除實作變更外無其他差異」）。
- [ ] 1.3 確認 `git status` 乾淨。
- [ ] 1.4 執行 `uv run pytest line_bot/tests/builders/test_shop_flex_message.py -q`，記錄基準測試數與全數通過（基準綠燈）。
- [ ] 1.5 執行 `uv run pytest -q` 全套測試，記錄基準總測試數與全數通過。

## 2. 依 TDD 規範撰寫測試（先於實作，預期紅燈）

- [ ] 2.1 修改既有測試 `test_does_not_trigger_upload_when_resolved_to_default`（`line_bot/tests/builders/test_shop_flex_message.py`）：因商業邏輯變更（見 design.md Decision 2，背景快取觸發不再依賴同步解析是否成功），此測試原本斷言「解析後得到預設圖時不觸發 S3 上傳」已不符合新需求。重新命名為 `test_triggers_upload_even_when_resolved_to_default`，斷言改為 `mock_upload.assert_called_once_with('p1')`，並在 docstring 註明此為業務邏輯變更、非遷就實作而修改測試。
- [ ] 2.2 新增測試：`get_photo_url(info, allow_sync_resolve=False)`，當 `photo_s3_url` 為空、`photo_reference` 有值時，不呼叫 `resolve_photo_url`（`patch.object` 驗證 `assert_not_called`），直接回傳 `DEFAULT_PHOTO_URL`。
- [ ] 2.3 新增測試：延續 2.2 的情境，確認即使跳過同步解析，仍呼叫 `_trigger_s3_upload('p1')`。
- [ ] 2.4 新增測試：`get_photo_url(info, allow_sync_resolve=True)` 顯式傳入 `True` 時，行為與不傳（預設值）時一致，皆會呼叫 `resolve_photo_url`（確保預設值與顯式值語意相同）。
- [ ] 2.5 新增測試：`photo_s3_url` 已有值時，無論 `allow_sync_resolve` 為 `True` 或 `False`，皆直接回傳該 S3 URL，不受此參數影響。
- [ ] 2.6 擴充既有測試 `test_returns_default_when_no_photo_reference_or_s3`：新增 `patch.object(FlexMessageBuilder, '_trigger_s3_upload')`，斷言 `mock_upload.assert_not_called()`——對應 specs/cafe-photo-loading/spec.md 新增的「沒有可用照片來源時不觸發背景快取」情境，明確界定「無 `photo_reference`」不屬於本次「觸發條件與解析結果無關」規則的適用範圍。
- [ ] 2.7 於 `TestCreateShopFlexMessage` 新增測試：`create_shop_flex_message(info, is_multiple=True)` 呼叫 `get_photo_url` 時帶入 `allow_sync_resolve=False`；`is_multiple=False`（或不傳，預設值）時帶入 `allow_sync_resolve=True`（用 `patch.object(FlexMessageBuilder, 'get_photo_url')` 驗證呼叫參數）。
- [ ] 2.8 執行 `uv run pytest line_bot/tests/builders/test_shop_flex_message.py -q`，確認 2.2-2.7 新增/調整的測試在實作變更前為紅燈，且失敗原因確實是「尚未支援 `allow_sync_resolve` 參數 / 觸發條件尚未解耦」等預期原因（例如 `TypeError: unexpected keyword argument`），而非測試本身寫錯；2.1 修改後的測試此時應仍是紅燈（因實作尚未變更）。

## 3. 實作

- [ ] 3.1 `FlexMessageBuilder.get_photo_url` 新增 `allow_sync_resolve: bool = True` 參數。
- [ ] 3.2 在 `elif photo_reference:` 分支中，依 `allow_sync_resolve` 決定是否呼叫 `resolve_photo_url`：`True` 時維持原行為；`False` 時直接視為 `DEFAULT_PHOTO_URL`（不進行同步解析）。
- [ ] 3.3 移除 `_trigger_s3_upload` 觸發前的 `if resolved_url != DEFAULT_PHOTO_URL:` 判斷，改為只要進入 `elif photo_reference:` 分支即無條件呼叫 `FlexMessageBuilder._trigger_s3_upload(place_id)`。
- [ ] 3.4 `create_shop_flex_message` 呼叫 `get_photo_url` 時改為 `FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=not is_multiple)`。

## 4. 驗證

- [ ] 4.1 執行 `uv run pytest line_bot/tests/builders/test_shop_flex_message.py -q`，確認第 2 節所有測試（含修改與新增）全數轉綠。
- [ ] 4.2 執行 `uv run pytest line_bot/tests/builders/ -q`，確認累積回歸（含依賴 `shop_flex_message` 的 `favorites_page`、`message_sender` 等模組測試）全數通過。
- [ ] 4.3 執行 `uv run pytest -q` 全套測試，確認全數通過，並比對總測試數 = 第 1.5 步基準數 + 本次新增測試數（2.2-2.5、2.7，共 5 個新增測試；2.1 為既有測試修改、2.6 為既有測試擴充斷言，皆非新增測試數）。
- [ ] 4.4 執行 `uv run python manage.py check`，確認無誤。
- [ ] 4.5 執行 `uv run ruff check .`，確認無新增 lint 錯誤。

## 5. Spec 一致性檢查與收尾

- [ ] 5.1 執行 `openspec validate fix-cafe-google-url-timeout --strict`，確認 proposal/specs/design/tasks 一致且通過驗證。
- [ ] 5.2 檢視 `git diff`，確認變更範圍僅限 `line_bot/builders/shop_flex_message.py`、`line_bot/tests/builders/test_shop_flex_message.py`、`openspec/changes/fix-cafe-google-url-timeout/`。
- [ ] 5.3 `git add` 並建立 commit（訊息說明本次變更：解耦背景快取觸發條件、單筆/多筆照片載入分流）。
