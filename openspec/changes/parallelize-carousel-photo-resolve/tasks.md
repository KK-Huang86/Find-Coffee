## 1. 前置準備與基準驗證

- [x] 1.1 確認目前在 `feature/parallelize-carousel-photo-resolve` 分支。
- [x] 1.2 `git add openspec/changes/parallelize-carousel-photo-resolve/` 並建立 commit，將本 change 的 proposal/specs/design/tasks 規劃文件單獨提交，使工作目錄回到乾淨狀態。
- [x] 1.3 確認 `git status` 乾淨。
- [x] 1.4 執行 `uv run pytest line_bot/tests/builders/test_shop_flex_message.py line_bot/tests/builders/test_message_sender.py -q`，記錄基準測試數與全數通過（基準綠燈）。
- [x] 1.5 執行 `uv run pytest -q` 全套測試，記錄基準總測試數與全數通過。

## 2. 依 TDD 規範撰寫測試（先於實作，預期紅燈）

- [x] 2.1 於 `line_bot/tests/builders/test_shop_flex_message.py` 的 `TestCreateShopFlexMessage` 新增測試：`create_shop_flex_message(info, is_multiple=True, photo_url_override='https://example.com/x.jpg')` 直接使用該值作為 `photo_url`，不呼叫 `get_photo_url`（`patch.object` 驗證 `assert_not_called`），且結果的 `result['hero']['url']` 等於傳入值。
- [x] 2.2 新增測試：`photo_url_override=None`（顯式傳入或不傳）時，行為與現行一致，仍呼叫 `get_photo_url(info, allow_sync_resolve=not is_multiple)`（沿用既有測試 `test_multiple_results_calls_get_photo_url_with_sync_resolve_disallowed`、`test_single_result_calls_get_photo_url_with_sync_resolve_allowed` 的驗證方式，確認新增參數不影響既有呼叫路徑）。
- [x] 2.3 於 `line_bot/tests/builders/test_message_sender.py` 新增測試類別（例如 `TestLineMessageBuilderResolvePhotoUrlsConcurrently`），針對新的平行解析私有方法：
  - 多筆 `infos`（例如 3 筆，皆帶不同 `photo_reference`）平行呼叫 `get_photo_url`，每次呼叫皆帶入 `allow_sync_resolve=True`（`patch.object` 記錄每次呼叫的參數）
  - 回傳正確的 `{place_id: photo_url}` 對照表，鍵值與呼叫結果一一對應
  - **證明真正並行（非序列迴圈偽裝）**：`patch.object(FlexMessageBuilder, 'get_photo_url', side_effect=...)` 的 side_effect 內用 `threading.Lock` 保護的共用計數器，記錄同時在執行中的呼叫數（進入時 +1、記錄目前最大值、`time.sleep(0.2)` 模擬 I/O、離開前 -1），並量測整體呼叫耗時；斷言「最大同時執行數 >= 2」且「總耗時遠小於 `infos` 筆數 × 0.2 秒（例如 < 0.2 秒 × infos 數 × 0.7）」。若實作為序列迴圈（依序呼叫），最大同時執行數會停在 1、總耗時會趨近 `infos` 筆數 × 0.2 秒，兩個斷言都會失敗，藉此擋下「測試只驗參數與回傳值、序列實作也能矇混過關」的風險（對應 CLAUDE.md 併發安全測試邊界案例規範）。
- [x] 2.4 新增測試：`infos` 中某一筆 `get_photo_url` 拋出例外時，該 `place_id` 對照表的值回退為 `FlexMessageBuilder.DEFAULT_PHOTO_URL`，且不影響其他筆的正確結果（驗證單一店家的失敗不會中斷整批收集）。
- [x] 2.5 新增測試：平行解析每次 worker 呼叫結束後皆呼叫 `close_old_connections`（`patch` 驗證呼叫次數等於 `infos` 筆數），確保 Decision 3 的 DB 連線清理邏輯確實執行。
- [x] 2.6 於 `TestLineMessageBuilderSendShopResult` 新增測試：多筆結果分支會呼叫新的平行解析方法，並將對照表中對應的 URL 正確傳入每一筆 `create_shop_flex_message` 呼叫的 `photo_url_override` 參數（用 `patch.object` 驗證呼叫參數，涵蓋 2-10 間店的情境）。
- [x] 2.7 執行 `uv run pytest line_bot/tests/builders/test_message_sender.py -q`，確認既有 4 個多筆結果測試（`test_multiple_shops_uses_db_cache_when_available`、`test_multiple_shops_quota_exceeded_stops_and_replies`、`test_multiple_shops_all_missing_uses_http_info_reply`、`test_multiple_shops_success_sends_carousel`）在**尚未實作**前仍可正常執行且通過（這些測試的 `info_d` 皆不含 `photo_reference`，平行解析呼叫 `get_photo_url` 會落在既有的「無照片來源」分支立即回傳預設圖，不涉及真實網路或 DB 呼叫，預期不受影響）——確認後續實作不會意外破壞這些既有測試。
- [x] 2.8 執行 `uv run pytest line_bot/tests/builders/test_shop_flex_message.py line_bot/tests/builders/test_message_sender.py -q`，確認 2.1、2.3-2.6 新增的測試在實作變更前為紅燈，且失敗原因確實是「尚未支援 `photo_url_override` 參數 / 尚未有平行解析方法」等預期原因，而非測試本身寫錯。

## 3. 實作

- [x] 3.1 `line_bot/builders/shop_flex_message.py`：`create_shop_flex_message` 新增 `photo_url_override=None` 參數；當不為 `None` 時直接使用該值作為 `photo_url`，略過 `get_photo_url` 呼叫。
- [x] 3.2 `line_bot/builders/message_sender.py`：新增 import `from concurrent.futures import ThreadPoolExecutor, as_completed` 與 `from django.db import close_old_connections`。
- [x] 3.3 新增 `LineMessageBuilder._resolve_single_photo_url(info)` 私有方法：呼叫 `FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=True)`，`finally` 區塊呼叫 `close_old_connections()`。
- [x] 3.4 新增 `LineMessageBuilder._resolve_photo_urls_concurrently(infos)` 私有方法：用 `ThreadPoolExecutor(max_workers=len(infos))` 對每筆 `info` 呼叫 `_resolve_single_photo_url`，以 `as_completed` 收集結果組成 `{place_id: photo_url}`；單一 `future` 拋例外時記錄錯誤並回退 `DEFAULT_PHOTO_URL`，不中斷其他結果收集；`infos` 為空時直接回傳空字典（不建立執行緒池）。
- [x] 3.5 重構 `send_shop_result` 多筆結果分支為三階段：① 沿用既有邏輯收集所有 `info_d`（含 DB 快取命中與 `_get_or_create_shop_info` 呼叫、`QUOTA_EXCEEDED` 檢查與提早回覆邏輯不變）② 呼叫 `_resolve_photo_urls_concurrently` 取得對照表 ③ 組裝 `flex_messages` 時，`create_shop_flex_message` 呼叫改為傳入 `photo_url_override=photo_url_map.get(info_d['place_id'])`。

## 4. 驗證

- [x] 4.1 執行 `uv run pytest line_bot/tests/builders/test_shop_flex_message.py -q`，確認全數轉綠。
- [x] 4.2 執行 `uv run pytest line_bot/tests/builders/test_message_sender.py -q`，確認全數轉綠（含 2.7 確認過的既有 4 個多筆結果測試仍然通過）。
- [x] 4.3 執行 `uv run pytest line_bot/tests/builders/ -q`，確認累積回歸全數通過。
- [x] 4.4 執行 `uv run pytest -q` 全套測試，確認全數通過，並比對總測試數 = 第 1.5 步基準數 + 本次新增測試數。
- [x] 4.5 執行 `uv run python manage.py check`，確認無誤。
- [x] 4.6 執行 `uv run ruff check .`，確認無新增 lint 錯誤。
- [x] 4.7 確認 `specs/cafe-photo-loading/spec.md` 兩項需求皆有測試覆蓋：「多筆搜尋結果照片載入不得逐筆同步等待」由 2.3 的 `test_calls_run_concurrently_not_sequentially` 證明平行、3.4/3.5 實作滿足；「照片背景快取觸發與同步解析結果無關」為 `fix-cafe-google-url-timeout` change 已建立且本次不變更的行為，由 `test_shop_flex_message.py` 既有測試 `test_triggers_upload_even_when_resolved_to_default`、`test_triggers_upload_even_when_sync_resolve_skipped` 覆蓋。

## 5. Spec 一致性檢查與收尾

- [ ] 5.1 執行 `openspec validate parallelize-carousel-photo-resolve --strict`，確認 proposal/specs/design/tasks 一致且通過驗證。
- [ ] 5.2 執行 `/spectra-verify`，確認實作與本 change 的 proposal/design/specs 語意一致；若回報落差，先修正實作或回頭調整 spec，確認一致後才繼續。
- [ ] 5.3 執行 `/spectra-drift`，檢查本 change 與目前程式碼現狀是否已產生落差；若回報落差，先處理後再繼續（依 CLAUDE.md「PR 前的 Spec 一致性檢查」規範，這兩步是開 PR 前的強制流程約定）。
- [ ] 5.4 檢視 `git diff`，確認變更範圍僅限 `line_bot/builders/shop_flex_message.py`、`line_bot/builders/message_sender.py`、`line_bot/tests/builders/test_shop_flex_message.py`、`line_bot/tests/builders/test_message_sender.py`、`openspec/changes/parallelize-carousel-photo-resolve/`。
- [ ] 5.5 `git add` 並建立 commit（訊息說明本次變更：多筆結果照片解析改為平行嘗試，取代原本完全跳過同步解析）。
