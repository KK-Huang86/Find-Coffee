## 1. 前置準備與基準驗證

- [x] 1.1 確認目前在 `refactor/split-flex-builder` 分支，且 `git status` 乾淨。
- [x] 1.2 執行 `uv run pytest line_bot/tests/test_flex_builder.py -q`，記錄拆分前的測試數（記為 `N_base`）與全數通過（基準綠燈）。N_base = 73。
- [x] 1.3 執行 `uv run pytest -q` 全套測試，記錄拆分前的總測試數（記為 `N_total_base`）與全數通過（基準綠燈，作為後續每輪比對依據）。N_total_base = 280。
- [x] 1.4 建立 `line_bot/tests/builders/` 目錄與 `__init__.py`，作為拆分後測試檔的存放位置。

## 2. 拆分 PostbackBuilder（無跨類別依賴，既有行為搬移）

- [x] 2.1 建立 `line_bot/builders/postback.py`，搬移 `PostbackBuilder` 類別與其所需 import（`TemplateMessage`）。
- [x] 2.2 建立 `line_bot/tests/builders/test_postback.py`，將 `test_flex_builder.py` 中 `TestPostbackBuilderCreateCafeActionPostback` 測試方法原樣搬移，import 改為 `from line_bot.builders.postback import PostbackBuilder`，不修改任何斷言。
- [x] 2.3 從 `line_bot/tests/test_flex_builder.py` 移除已搬移的 `TestPostbackBuilderCreateCafeActionPostback`。
- [x] 2.4 於 `flex_builder.py` 中移除 `PostbackBuilder` 類別本體，改為 `from line_bot.builders.postback import PostbackBuilder`（暫時性 re-export，供尚未拆分的類別與外部呼叫端使用）。
- [x] 2.5 執行 `uv run pytest line_bot/tests/builders/test_postback.py -q`，確認新測試檔獨立通過（既有行為搬移後仍是綠燈，驗證程式碼確實已搬到新模組且可運作）。5 passed.
- [x] 2.6 執行 `uv run pytest line_bot/tests/test_flex_builder.py -q`，確認移除該測試類別後其餘測試仍全數通過。68 passed (73-5)。
- [x] 2.7 `git add` 本階段新增/修改檔案並獨立 commit（訊息說明「拆分 PostbackBuilder」），作為此階段最小回滾單位。

## 3. 拆分 QuickReplyBuilder（無跨類別依賴，既有行為搬移）

- [x] 3.1 建立 `line_bot/builders/quick_reply.py`，搬移 `QuickReplyBuilder` 類別與其所需 import（`QuickReply`、`QuickReplyItem`、`LocationAction`、`PostbackAction`、`MenuText`、`MenuAction`、`VOTE_OPTIONS`、`SearchHistoryService` 等）。
- [x] 3.2 建立 `line_bot/tests/builders/test_quick_reply.py`，搬移 `test_flex_builder.py` 中所有 `TestQuickReplyBuilder*` 測試類別，import 改為 `from line_bot.builders.quick_reply import QuickReplyBuilder`，不修改任何斷言；同步將 `patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', ...)` 改為 `patch('line_bot.builders.quick_reply.SearchHistoryService.get_search_history', ...)`（僅調整 mock 的 lookup location，不改變測試驗證的行為，見 design.md Decision 5）。
- [x] 3.3 從 `line_bot/tests/test_flex_builder.py` 移除已搬移的 `TestQuickReplyBuilder*` 測試類別。
- [x] 3.4 於 `flex_builder.py` 中移除 `QuickReplyBuilder` 類別本體，改為 `from line_bot.builders.quick_reply import QuickReplyBuilder`。
- [x] 3.5 執行 `uv run pytest line_bot/tests/builders/test_quick_reply.py -q`，確認獨立通過，並確認 patch 確實生效（例如 `TestQuickReplyBuilderCreateRecentSearchQuickReply` 案例中未真的呼叫外部 `SearchHistoryService`）。15 passed。
- [x] 3.6 執行 `uv run pytest line_bot/tests/builders/ line_bot/tests/test_flex_builder.py -q`，確認累積回歸（含已拆分的 PostbackBuilder）全數通過。73 passed (5+15+53)。
- [x] 3.7 `git add` 本階段新增/修改檔案並獨立 commit（訊息說明「拆分 QuickReplyBuilder」）。

## 4. 拆分 FlexMessageBuilder（含私有輔助方法，既有行為搬移）

- [x] 4.1 建立 `line_bot/builders/shop_flex_message.py`，搬移 `FlexMessageBuilder` 類別（含 `get_photo_url`、`_trigger_s3_upload`、`resolve_photo_url`、`_create_attribute_tags`、`_create_tag_element`、`_create_tags_box`、`format_opening_hours`、`create_shop_flex_message` 及其內部 `_generate_star_icons`）與所需 import（`requests`、`date`、`urlencode`、`Union`、`config`、`parse_opening_hours`、`download_and_upload_cafe_photo`）。
- [x] 4.2 建立 `line_bot/tests/builders/test_shop_flex_message.py`，搬移 `TestGetPhotoUrl`、`TestResolvePhotoUrl`、`TestCreateAttributeTags`、`TestCreateTagElement`、`TestCreateTagsBox`、`TestFormatOpeningHours`、`TestCreateShopFlexMessage`，import 改為 `from line_bot.builders.shop_flex_message import FlexMessageBuilder`，不修改任何斷言；同步將以下 patch target 改為新模組路徑（見 design.md Decision 5）：
  - `line_bot.builders.flex_builder.requests` → `line_bot.builders.shop_flex_message.requests`
  - `line_bot.builders.flex_builder.config` → `line_bot.builders.shop_flex_message.config`
  - `line_bot.builders.flex_builder.date` → `line_bot.builders.shop_flex_message.date`
- [x] 4.3 從 `line_bot/tests/test_flex_builder.py` 移除已搬移的測試類別。
- [x] 4.4 於 `flex_builder.py` 中移除 `FlexMessageBuilder` 類別本體，改為 `from line_bot.builders.shop_flex_message import FlexMessageBuilder`。
- [x] 4.5 執行 `uv run pytest line_bot/tests/builders/test_shop_flex_message.py -q`，確認獨立通過，並確認 `requests`/`config`/`date` 相關 patch 確實生效（例如 `TestFormatOpeningHours` 案例中 `date.today()` 回傳的是 mock 值而非真實日期）。53 passed。
- [x] 4.6 執行 `uv run pytest line_bot/tests/builders/ line_bot/tests/test_flex_builder.py -q`，確認前兩個已拆分模組加上剩餘測試全數通過（累積回歸驗證）。73 passed (5+15+53)；全套 `uv run pytest -q` 280 passed，與 N_total_base 相符。
- [x] 4.7 `git add` 本階段新增/修改檔案並獨立 commit（訊息說明「拆分 FlexMessageBuilder」）。

## 5. 補齊 FavoritesPageBuilder 缺漏測試並搬移（依賴 FlexMessageBuilder）

先寫測試、後搬程式碼（依 CLAUDE.md TDD 規範，`FavoritesPageBuilder` 目前無直接單元測試）：

- [x] 5.1 盤點 `build_page_message` 的行為與邊界情況：單頁/多頁標題、收藏筆數（0 筆、1 筆、15 筆上限）、`fav.cafe.address` 為空、`fav.cafe.rating` 為 `None` 等。
- [x] 5.2 於 `line_bot/tests/test_flex_builder.py`（**尚未搬移前的舊實作位置**，import 仍為 `from line_bot.builders.flex_builder import FavoritesPageBuilder`）新增 `TestFavoritesPageBuilderBuildPageMessage`，涵蓋 5.1 列出的情境。
- [x] 5.3 執行 `uv run pytest line_bot/tests/test_flex_builder.py -k TestFavoritesPageBuilderBuildPageMessage -q`，確認針對舊實作全數通過（綠燈，證明新測試正確描述現有契約，而非搬移後才拼湊出的期望值）。10 passed。
- [x] 5.4 建立 `line_bot/builders/favorites_page.py`，搬移 `FavoritesPageBuilder` 類別，import 改為 `from line_bot.builders.shop_flex_message import FlexMessageBuilder`（直接依賴來源模組，不透過 `flex_builder.py`），並補齊 `FlexMessage`、`FlexBubble` import。
- [x] 5.5 建立 `line_bot/tests/builders/test_favorites_page.py`，將 5.2 新增的測試搬移過去，import 改為 `from line_bot.builders.favorites_page import FavoritesPageBuilder`，不修改任何斷言；並從 `line_bot/tests/test_flex_builder.py` 移除已搬移的測試類別。
- [x] 5.6 於 `flex_builder.py` 中移除 `FavoritesPageBuilder` 類別本體，改為 `from line_bot.builders.favorites_page import FavoritesPageBuilder`。
- [x] 5.7 執行 `uv run pytest line_bot/tests/builders/test_favorites_page.py -q`，確認獨立通過。10 passed。
- [x] 5.8 執行 `uv run pytest line_bot/tests/builders/ line_bot/tests/test_flex_builder.py -q`，確認累積回歸驗證全數通過。83 passed (73+10)。
- [x] 5.9 `git add` 本階段新增/修改檔案並獨立 commit（訊息說明「補齊測試並拆分 FavoritesPageBuilder」）。

## 6. 補齊 LineMessageBuilder 缺漏測試並搬移（依賴 FlexMessageBuilder、PostbackBuilder）

先寫測試、後搬程式碼（依 CLAUDE.md TDD 規範，`LineMessageBuilder.send_shop_result` 目前無直接單元測試）：

- [x] 6.1 盤點 `send_shop_result` 的行為與邊界情況：`shops` 為空列表、單筆結果、多筆結果（2-10 筆）、`info_d is QUOTA_EXCEEDED`（單筆與多筆路徑各一次）、單筆但 `info_d` 為空、多筆結果中部分 `place_id` 已在 DB 快取命中、多筆結果全部取得失敗（`flex_messages` 為空）、`>10` 筆時現有實作不回覆任何訊息（鎖定既有行為的邊界測試）。
- [x] 6.2 於 `line_bot/tests/test_flex_builder.py`（**尚未搬移前的舊實作位置**，import 仍為 `from line_bot.builders.flex_builder import LineMessageBuilder`）新增 `TestLineMessageBuilderSendShopResult`，涵蓋 6.1 列出的情境，並視需要 `patch('line_bot.builders.flex_builder.LineMessageBuilder._get_or_create_shop_info', ...)` 隔離對 `helpers.get_or_create_cafe_info` 的依賴。
- [x] 6.3 執行 `uv run pytest line_bot/tests/test_flex_builder.py -k TestLineMessageBuilderSendShopResult -q`，確認針對舊實作全數通過（綠燈，證明新測試正確描述現有契約）。9 passed。
- [x] 6.4 建立 `line_bot/builders/message_sender.py`，搬移 `LineMessageBuilder` 類別，import 改為 `from line_bot.builders.shop_flex_message import FlexMessageBuilder`、`from line_bot.builders.postback import PostbackBuilder`（直接依賴來源模組），並保留 `_get_or_create_shop_info` 內部對 `line_bot.handlers.helpers.get_or_create_cafe_info` 的 lazy import 不變，補齊 `ReplyMessageRequest`、`TextMessage`、`FlexContainer`、`FlexMessage`、`QUOTA_EXCEEDED`、`Cafe`、`json`、`logger` 等所需 import。
- [x] 6.5 建立 `line_bot/tests/builders/test_message_sender.py`，將 6.2 新增的測試搬移過去，import 改為 `from line_bot.builders.message_sender import LineMessageBuilder`，並將 6.2 中的 patch target 同步改為 `line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info`，不修改任何斷言；並從 `line_bot/tests/test_flex_builder.py` 移除已搬移的測試類別。
- [x] 6.6 於 `flex_builder.py` 中移除 `LineMessageBuilder` 類別本體，改為 `from line_bot.builders.message_sender import LineMessageBuilder`。此時 `flex_builder.py` 已無殘留類別定義，一併完成第 8.1 節的收斂為相容層（提前完成，見第 8 節備註）。
- [x] 6.7 執行 `uv run pytest line_bot/tests/builders/test_message_sender.py -q`，確認獨立通過。9 passed。
- [x] 6.8 執行 `uv run pytest line_bot/tests/builders/ line_bot/tests/test_flex_builder.py -q`，確認累積回歸驗證全數通過。92 passed (83+9)；全套 `uv run pytest -q` 299 passed (280+19)。
- [x] 6.9 `git add` 本階段新增/修改檔案並獨立 commit（訊息說明「補齊測試並拆分 LineMessageBuilder」）。

## 7. 相容層 identity smoke test

- [x] 7.1 建立 `line_bot/tests/builders/test_flex_builder_compat.py`，對 5 個類別分別斷言 `from line_bot.builders.flex_builder import X` 與各自新模組匯入的 `X` 為同一物件（`is` 比較），直接驗證 proposal.md 承諾的「呼叫端 import 路徑不需修改」相容契約（見 design.md Decision 6）。
- [x] 7.2 執行 `uv run pytest line_bot/tests/builders/test_flex_builder_compat.py -q`，確認全數通過。5 passed。
- [x] 7.3 `git add` 並獨立 commit（訊息說明「新增相容層 identity smoke test」）。

## 8. 收尾：flex_builder.py 相容層與舊測試檔清理

- [ ] 8.1 確認 `line_bot/builders/flex_builder.py` 此時僅剩 5 行 re-export import 與 `__all__`，無殘留類別定義；於檔案頂部加上一行註解說明此檔為相容層、實作已搬至個別模組。
- [ ] 8.2 確認 `line_bot/tests/test_flex_builder.py` 此時已無殘留測試類別；若已清空，刪除該檔案；若仍有跨類別整合測試（如同時用到多個 Builder 的情境），改名保留為整合測試檔並更新 import。
- [ ] 8.3 逐一確認三個呼叫端檔案（`line_bot/event_handlers.py`、`line_bot/handlers/postback_actions.py`、`line_bot/handlers/helpers.py`）完全未被修改（`git diff` 應無變更）。
- [ ] 8.4 `git add` 並獨立 commit（訊息說明「flex_builder.py 收斂為相容層」）。

## 9. 最終多輪驗證

- [ ] 9.1 執行 `uv run python manage.py check`，確認 Django app 設定與 import 無誤。
- [ ] 9.2 執行 `uv run pytest -q` 全套測試，確認：既有測試案例數不得減少（不得低於第 1.3 步 `N_total_base`）；最終總數應等於 `N_total_base` 加上第 5、6 節為補齊邊界情況新增的測試數（`FavoritesPageBuilder`、`LineMessageBuilder`、相容層 smoke test），且全數通過。
- [ ] 9.3 執行 `uv run pytest --cov=line_bot.builders --cov-report=term-missing`，確認覆蓋率不低於拆分前。
- [ ] 9.4 執行 `uv run ruff check .`，確認無新增 lint 錯誤。
- [ ] 9.5 於本機以 `uv run python -c "from line_bot.event_handlers import *"` 等方式，或啟動 `uv run python manage.py runserver` 後觸發一次 LINE webhook 相關單元測試，做最後一次端到端 import 與行為 smoke test。
- [ ] 9.6 執行 `openspec validate split-flex-builder --strict`，確認 change 文件通過驗證。
- [ ] 9.7 檢視 `git diff develop...refactor/split-flex-builder` 全量差異，確認除 `line_bot/builders/`、`line_bot/tests/`、`openspec/changes/split-flex-builder/` 外無其他檔案變更。
