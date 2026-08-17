## Context

延續 `fix-cafe-google-url-timeout`（已 archive）建立的基礎：`FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=True)` 已經把「是否同步等待 Google 解析」跟「是否觸發背景 S3 快取」解耦——後者只要有 `photo_reference` 且尚未快取即觸發，不論前者是否嘗試、是否成功。目前 `line_bot/builders/message_sender.py` 的 `send_shop_result` 在多筆結果（2-10 間店）時，對每間未快取店家呼叫 `create_shop_flex_message(info_d, is_multiple=True)`，內部固定傳入 `allow_sync_resolve=False`，也就是完全跳過同步解析。

本次要把「完全跳過」改成「平行嘗試」：對所有未快取店家同時發出 `resolve_photo_url` 請求（各自沿用既有 `requests.head(..., timeout=2)` 的 2 秒上限），而不是逐間依序呼叫。因為是並行而非序列，整批請求的實際等待時間會趨近於「最慢那一個請求的時間」（約 2 秒），而不是「間數 × 2 秒」。

專案的 LINE webhook 處理是全同步的（`line_bot/views.py` 的 `callback()` 直接呼叫 `handler.handle()`），所以這裡不能用 Celery 之類的真異步任務（那樣無法在同一次回覆前拿到結果），必須用執行緒（thread）在同一個請求內平行發出多個 HTTP 請求。

## Goals / Non-Goals

**Goals:**
- 多筆結果中，所有未快取店家平行嘗試向 Google 解析照片，而非完全跳過或依序等待
- 整體等待時間不因未快取店家數量增加而線性增加，維持在接近單一店家解析時間（約 2 秒）的範圍內
- 任一店家解析逾時或失敗，只影響該店家（回退預設圖），不影響其他店家、不拖慢整體回覆
- 背景 S3 快取觸發時機維持既有的解耦邏輯不變
- 單筆結果路徑完全不受影響

**Non-Goals:**
- 不處理 `_get_or_create_shop_info`（多筆結果中對未在 DB 快取的店家呼叫 Google Places Detail API 取得完整店家資料）的序列化問題——這是另一個獨立的同步瓶頸，不在本次「照片解析」的範圍內，需要的話應另開 change 處理
- 不調整 `resolve_photo_url` 的 `timeout=2`（沿用既有值，平行化本身已足以解決疊加問題，不需要調整單次逾時時間）
- 不改變 `resolve_photo_url`、`_trigger_s3_upload`、`download_and_upload_cafe_photo` 的內部實作，只改變它們被呼叫的方式（從主執行緒依序呼叫，變成多個 worker 執行緒平行呼叫）
- 不引入新的第三方套件，`concurrent.futures.ThreadPoolExecutor` 為標準函式庫

## Decisions

**1. 用 `ThreadPoolExecutor` 平行發出解析請求，而非改用真正的異步框架**
- 選擇：在 `LineMessageBuilder` 新增一個私有方法，對多筆未快取店家用 `ThreadPoolExecutor(max_workers=len(infos))` 平行呼叫 `FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=True)`，用 `as_completed` 收集結果，組成 `{place_id: photo_url}` 對照表。
- 理由：專案的 webhook 處理是同步的 Django view（見 Context），要在同一次回覆前拿到解析結果，只能用執行緒做 I/O 平行化；`requests.head` 是 I/O bound 操作，Python 的 GIL 在等待網路 I/O 時會釋放，執行緒平行確實能縮短總等待時間。多筆結果最多 10 間店（既有邏輯已限制），thread pool 開 10 個 worker 不會有資源疑慮，也不需要佇列等待。
- 替代方案：改成 `asyncio` + `aiohttp` 異步 I/O。放棄原因：專案目前的 Django view、`requests` 函式庫、Celery task 皆為同步/阻塞式寫法，全面改成 async 需要更動的範圍遠超本次需求（例如 Django view 本身需改成 async view、`requests` 需換成異步 HTTP client），不符合「不做過度設計」原則；`ThreadPoolExecutor` 是標準函式庫、改動最小、足以達成目標。

**2. `create_shop_flex_message` 新增 `photo_url_override` 參數，取代原本內部呼叫 `get_photo_url`**
- 選擇：`create_shop_flex_message(info, is_multiple=False, photo_url_override=None)`。當 `photo_url_override` 不為 `None` 時，直接使用該值作為 `photo_url`，不再呼叫 `get_photo_url`；為 `None` 時維持原行為（呼叫 `get_photo_url(info, allow_sync_resolve=not is_multiple)`）。
- 理由：平行解析必須在組裝所有 Flex Message **之前**、以批次方式完成，不能讓 `create_shop_flex_message` 在組裝每一則訊息時各自呼叫 `get_photo_url`（那樣就退回序列呼叫了）。新增可選參數，讓 `message_sender.py` 能把平行解析好的結果「餵」進來，同時保留預設值（`None`）以維持所有其他呼叫端（單筆結果、`helpers.reply_cafe_detail`）完全不受影響、不需修改。
- 替代方案：把 `get_photo_url` 呼叫完全從 `create_shop_flex_message` 移出，改成呼叫端一律先算好 `photo_url` 再傳入（必填參數，不留預設呼叫路徑）。放棄原因：這會強制修改所有現有呼叫端（包含單筆結果路徑與 `helpers.py`），擴大變更範圍與回歸風險，不符合「多筆結果」這個具體目標；用可選參數可以把改動完全侷限在多筆結果的呼叫路徑。

**3. 每個 worker 執行緒結束前，明確關閉 Django DB 連線**
- 選擇：平行呼叫 `get_photo_url` 的 worker 函式，在 `finally` 區塊呼叫 `django.db.connections.close_all()`。
- 理由：`get_photo_url` 內部的 `_trigger_s3_upload` 會查詢 `Cafe` model（`Cafe.objects.filter(...)`），這個查詢若在非主執行緒（worker thread）執行，Django 會在該執行緒的 thread-local 開一個新的資料庫連線；但 Django 預設只在 `request_started`／`request_finished` signal（綁定主執行緒的請求生命週期）時清理連線，worker 執行緒開的連線不會被自動清理。`ThreadPoolExecutor` 的 worker 執行緒在 `with` 區塊結束（`shutdown()`）時會終止，若沒有明確關閉連線，該連線可能以未關閉狀態遺留，在專案的 PgBouncer transaction pooling 架構下會佔用連線池資源。
- 為何用 `connections.close_all()` 而非 `close_old_connections()`：後者只關閉「已標記為過期／不可用」的連線，是否關閉取決於 `CONN_MAX_AGE` 設定——本專案 `CONN_MAX_AGE=0`（`core/settings.py:94`，CLAUDE.md 規定必須維持 0），效果上每次呼叫確實會關閉連線，但這是「間接依賴一個可能被改動的全域設定」而成立，不是函式本身保證的行為。`connections.close_all()` 不論 `CONN_MAX_AGE` 為何皆保證關閉所有連線，語意直接、不隨設定變動而改變行為，更符合「明確關閉」的設計意圖（此點為 codex review 建議修正，原先誤用 `close_old_connections()` 雖在本專案現行設定下功能無誤，但不夠明確可靠）。
- 替代方案：不特別處理，依賴作業系統在執行緒結束、行程結束時最終回收 socket。放棄原因：這是已知的資源洩漏風險，在 PgBouncer transaction pooling（連線數有限）的架構下影響更明顯，屬於低成本就能避免的技術債，沒有理由不處理。

**4. 平行解析的批次呼叫不篩選「哪些店家需要解析」，一律呼叫 `get_photo_url`，交由其內部既有優先序處理**
- 選擇：對所有 `infos`（不論是否已有 `photo_s3_url`）都送進 thread pool，讓 `get_photo_url` 自己判斷（已有 S3 URL 的分支幾乎瞬間回傳、不涉及網路 I/O）。
- 理由：`get_photo_url` 本身已經有「S3 優先 → 解析 → 預設圖」的完整優先序邏輯，外部再實作一次「哪些需要解析」的篩選邏輯是重複勞動；執行緒建立的額外開銷（對已有 S3 URL 的店家而言）可忽略不計。
- 替代方案：呼叫端先篩選出 `photo_s3_url` 為空的店家才送進 thread pool，其餘直接用既有值。放棄原因：多一層篩選邏輯、多一份跟 `get_photo_url` 重複的判斷條件，增加維護成本，換來的效能差異可忽略。

## Risks / Trade-offs

- [風險] Worker 執行緒中若 `get_photo_url` 拋出未預期例外（理論上不會，`resolve_photo_url` 與 `_trigger_s3_upload` 內部皆已包 `try/except` 吞掉例外並回退安全值），透過 `future.result()` 收集結果時仍可能重新拋出 → 緩解：收集結果時對每個 `future.result()` 個別包 `try/except`，任一店家發生未預期例外時記錄錯誤並回退為 `DEFAULT_PHOTO_URL`，不讓單一店家的例外中斷整批收集。
- [風險] PgBouncer transaction pooling 下，多個 worker 執行緒短時間內平行開啟資料庫連線查詢 `Cafe` model，若同時大量多筆搜尋發生，可能瞬間增加連線池壓力 → 緩解：單次多筆結果最多 10 間店（既有上限），且每個查詢都是輕量的單筆 `SELECT`、搭配 Decision 3 的明確連線清理，風險可控；若未來實測發現連線池壓力異常，可再評估是否需要限制平行度或加入節流。
- [Trade-off] 相較於完全跳過解析（`fix-cafe-google-url-timeout` 的做法），平行解析讓多筆結果的回應時間上限從「接近 0」提高到「接近單一店家解析時間（約 2 秒）」——這是用「回應時間上限」換取「更多店家能顯示真實照片」，符合本次修改的明確目標（使用者希望在請求中取得最多的咖啡店資料）。

## Migration Plan

1. 依 CLAUDE.md 的 TDD 規範，先在 `line_bot/tests/builders/test_shop_flex_message.py` 與 `line_bot/tests/builders/test_message_sender.py` 補齊測試：
   - `create_shop_flex_message(info, is_multiple=True, photo_url_override='...')` 直接使用該值，不呼叫 `get_photo_url`
   - `create_shop_flex_message(info, is_multiple=True)`（不傳 `photo_url_override`）維持現行行為（呼叫 `get_photo_url(info, allow_sync_resolve=False)`），確保既有測試不受影響
   - 新增的平行解析方法：多筆 `infos` 平行呼叫 `get_photo_url`（每個呼叫皆帶 `allow_sync_resolve=True`），回傳正確的 `{place_id: photo_url}` 對照表
   - 平行解析時，個別 `get_photo_url` 拋出例外，不影響其他店家的結果，該店家回退 `DEFAULT_PHOTO_URL`
   - 每次 worker 呼叫後皆呼叫 `connections.close_all()`（可用 `patch` 驗證呼叫次數與 `infos` 數量一致）
   - `send_shop_result` 多筆結果分支：確認會呼叫新的平行解析方法，並將結果正確傳入每個 `create_shop_flex_message` 呼叫的 `photo_url_override`
2. 確認新測試在無實作變更前為紅燈
3. 實作：`create_shop_flex_message` 新增 `photo_url_override` 參數、`LineMessageBuilder` 新增平行解析私有方法、`send_shop_result` 多筆結果分支改為「先收集 `infos` → 平行解析 → 組裝 Flex Message」三階段
4. 確認所有測試轉綠，執行 `line_bot/tests/builders/` 全部測試與全套 `uv run pytest -q` 回歸
5. `openspec validate parallelize-carousel-photo-resolve --strict` 確認 spec/proposal/design/tasks 一致
6. Rollback：本次變更集中在 `shop_flex_message.py`（新增可選參數，向後相容）與 `message_sender.py`（多筆結果分支重構），單一 commit 即可 `git revert` 完整還原，不影響單筆結果路徑。

## Open Questions

- 平行解析在極端高併發（多位使用者同時搜尋、每次搜尋皆開 10 個執行緒）下對 PgBouncer 連線池與伺服器整體執行緒數的實際影響，需要上線後觀察實際數據，若造成壓力可再評估是否需要限制全域同時執行的 thread pool 數量（例如用一個全域的、有上限的共用執行緒池取代每次請求各自建立的執行緒池）。此問題不影響本次的 spec、設計方向或任務拆解，可安全留待之後決定。
