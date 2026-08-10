## Context

`line_bot/builders/flex_builder.py`（1018 行）目前包含 5 個類別，彼此有明確依賴關係：

- `FlexMessageBuilder`（32-520 行）：純函式風格，組裝店家 Flex Message，內部私有輔助方法（`get_photo_url`、`_trigger_s3_upload`、`resolve_photo_url`、`_create_attribute_tags`、`_create_tag_element`、`_create_tags_box`、`format_opening_hours`）僅供自身 `create_shop_flex_message` 使用，經全 repo 搜尋確認無其他模組直接呼叫這些輔助方法。
- `LineMessageBuilder`（521-662 行）：依賴 `FlexMessageBuilder.create_shop_flex_message`、`PostbackBuilder.create_cafe_action_postback`，並透過函式內 lazy import 呼叫 `line_bot.handlers.helpers.get_or_create_cafe_info`（避免與 helpers.py 循環 import，此模式須保留）。
- `PostbackBuilder`（663-712 行）：獨立，無跨類別依賴。
- `FavoritesPageBuilder`（714-802 行）：依賴 `FlexMessageBuilder.format_opening_hours`。
- `QuickReplyBuilder`（804-1018 行）：依賴 `SearchHistoryService`、`VOTE_OPTIONS` 等常數，無跨類別依賴。

外部呼叫端（`event_handlers.py`、`handlers/postback_actions.py`、`handlers/helpers.py`）皆以 `from line_bot.builders.flex_builder import <ClassName>` 具名匯入，未使用 `import *`。見 proposal.md 說明拆分動機。

## Goals / Non-Goals

**Goals:**
- 依現有 5 個類別的職責邊界，將檔案拆為 5 個責任單一、內聚的獨立模組，顯著降低單檔複雜度與行數（不強制每個檔案 < 350 行 —— `FlexMessageBuilder` 本身即約 489 行，原樣搬移後 `shop_flex_message.py` 仍會超過此門檻；拆分的判準是「一個類別只做一件事、檔案邊界與職責邊界一致」，而非硬性行數上限）。
- 保留 `flex_builder.py` 作為相容 re-export 層，所有現有呼叫端 import 語句不需修改。
- 對應測試檔同步依相同邊界拆分，且拆分後所有測試（拆分前後）全部通過，不改動任何既有斷言；測試中對內部依賴（`requests`、`config`、`date`、`SearchHistoryService` 等）的 `mock.patch` target 需隨實作搬移到的新模組路徑同步更新（詳見 Decision 5）。
- 保留類別間既有依賴（`LineMessageBuilder` → `FlexMessageBuilder`/`PostbackBuilder`；`FavoritesPageBuilder` → `FlexMessageBuilder`）與 lazy import 循環依賴迴避模式。

**Non-Goals:**
- 不重新設計類別介面、不改變任何 method 簽名或回傳格式。
- 不在此變更中把呼叫端的 import 路徑改指向新模組（避免擴大 diff 範圍與風險）；是否清理 `flex_builder.py` re-export 留待未來變更。
- 不處理 `flex_builder.py` 以外檔案的行數問題。

## Decisions

**1. 拆分邊界採「一類別一檔案」，而非依函式重新分組**
- 選擇：`shop_flex_message.py`（`FlexMessageBuilder`）、`message_sender.py`（`LineMessageBuilder`）、`postback.py`（`PostbackBuilder`）、`favorites_page.py`（`FavoritesPageBuilder`）、`quick_reply.py`（`QuickReplyBuilder`）。
- 理由：類別本身已是內聚單位，且測試檔已依類別分組（`TestCreateShopFlexMessage`、`TestPostbackBuilderCreateCafeActionPostback` 等），沿用邊界可讓程式與測試一一對應，降低拆分時誤搬程式碼的風險。
- 替代方案：依「資料流」重組（例如把所有 Quick Reply 相關邏輯與 Postback 邏輯合併成一個 interaction 模組）。放棄原因：會同時改變邊界與程式位置兩件事，增加此次純重構的風險，且不符合「不改變對外行為」的最小變更原則。

**2. 保留 `flex_builder.py` 作為 re-export 相容層，不同步修改呼叫端 import**
- 選擇：`flex_builder.py` 內容改為：
  ```python
  from line_bot.builders.shop_flex_message import FlexMessageBuilder
  from line_bot.builders.message_sender import LineMessageBuilder
  from line_bot.builders.postback import PostbackBuilder
  from line_bot.builders.favorites_page import FavoritesPageBuilder
  from line_bot.builders.quick_reply import QuickReplyBuilder

  __all__ = [
      'FlexMessageBuilder',
      'LineMessageBuilder',
      'PostbackBuilder',
      'FavoritesPageBuilder',
      'QuickReplyBuilder',
  ]
  ```
- 理由：`event_handlers.py`、`handlers/postback_actions.py`、`handlers/helpers.py` 目前共 3 個檔案、約 10 處 import 此模組。若同時改動所有呼叫端 import 路徑，會讓一個「純搬移」的變更牽涉到功能模組的 diff，增加 review 與回歸測試範圍。re-export 層讓此次變更的影響完全侷限在 `builders/` 目錄與其測試，符合資料操作穩健性規範中「降低變更風險」的精神。
- 替代方案：直接刪除 `flex_builder.py`，同步更新所有呼叫端 import。放棄原因：擴大 blast radius，且非此次重構目的；未來若確定要清理，可作為獨立的後續變更。
- 權衡：`flex_builder.py` 會長期存在一層間接 import，屬可接受的技術債，已在 proposal 的 Impact 中註明。

**3. `LineMessageBuilder` 對 `FlexMessageBuilder`/`PostbackBuilder` 的依賴改為模組層 import，而非再透過 `flex_builder.py`**
- 選擇：`message_sender.py` 直接 `from line_bot.builders.shop_flex_message import FlexMessageBuilder`、`from line_bot.builders.postback import PostbackBuilder`。
- 理由：避免 `message_sender.py` 反過來 import `flex_builder.py`（re-export 層）造成不必要的間接層與潛在循環 import 風險；直接依賴來源模組是更清楚的依賴方向。
- 替代方案：讓所有新模組都透過 `flex_builder.py` 互相依賴。放棄原因：本末倒置，`flex_builder.py` 應該是「對外相容殼」，不應被內部模組依賴。

**4. 既有 lazy import（`LineMessageBuilder._get_or_create_shop_info` 內部 `from line_bot.handlers.helpers import get_or_create_cafe_info`）原樣搬移，不做調整**
- 理由：此 lazy import 是為了避免 `flex_builder.py` 與 `handlers/helpers.py` 之間的循環 import（`helpers.py` 也會 import `FlexMessageBuilder`/`PostbackBuilder`）。拆分後 `message_sender.py` 與 `helpers.py` 之間仍有相同的相依方向，維持 lazy import 可保證行為與匯入順序完全不變。

**5. 測試邏輯與斷言不變，但 `mock.patch` target 必須隨實作搬移位置同步更新**
- 背景：`unittest.mock.patch` 是依「使用該名稱的模組路徑」而非「定義該名稱的模組路徑」查找 patch 對象。目前 `test_flex_builder.py` 中以下 patch 皆指向舊路徑：
  - `line_bot.builders.flex_builder.requests`（`TestGetPhotoUrl` 系列）
  - `line_bot.builders.flex_builder.config`（`TestGetPhotoUrl` 系列）
  - `line_bot.builders.flex_builder.date`（`TestFormatOpeningHours` 系列）
  - `line_bot.builders.flex_builder.SearchHistoryService`（`TestQuickReplyBuilderCreateRecentSearchQuickReply`）
- 選擇：搬移對應類別時，同步將這些 patch target 改為實作實際所在的新模組路徑：
  - `line_bot.builders.shop_flex_message.requests`
  - `line_bot.builders.shop_flex_message.config`
  - `line_bot.builders.shop_flex_message.date`
  - `line_bot.builders.quick_reply.SearchHistoryService`
- 理由：即使 `flex_builder.py` 保留 re-export，`patch('line_bot.builders.flex_builder.requests', ...)` 修改的是 `flex_builder` 模組命名空間裡的 `requests` 名稱，而 `FlexMessageBuilder.get_photo_url` 實際執行時查找的是 `shop_flex_message` 模組命名空間裡的 `requests`，兩者搬移後不再是同一個名稱綁定，若不同步更新，patch 會靜默失效（測試呼叫到真實的 `requests.head` / `date.today()` / `SearchHistoryService`），造成測試變成假綠燈或直接因外部呼叫而失敗。
- 澄清：這只是調整 mock 的 lookup location，不改變測試在驗證什麼行為，也不改變任何斷言內容，因此不違反「測試不可為了遷就程式碼而修改」的規範。

**6. 新增相容層 identity smoke test，直接驗證 re-export 契約**
- 選擇：新增 `line_bot/tests/builders/test_flex_builder_compat.py`，對 5 個類別分別驗證 `from line_bot.builders.flex_builder import X` 與 `from line_bot.builders.<new_module> import X` 取得的是同一個物件（`is` 比較），例如：
  ```python
  from line_bot.builders.flex_builder import FlexMessageBuilder
  from line_bot.builders.shop_flex_message import FlexMessageBuilder as NewFlexMessageBuilder

  assert FlexMessageBuilder is NewFlexMessageBuilder
  ```
- 理由：proposal.md 的核心承諾是「呼叫端 import 路徑不需修改、行為不變」，但目前驗證方式主要依賴呼叫端相關測試間接覆蓋，並未直接斷言 re-export 有效。獨立的 identity smoke test 是對這個相容契約最直接、最便宜的保護，且屬於「新增測試」而非修改既有測試，不與 TDD 規範衝突。

## Risks / Trade-offs

- [風險] 拆分過程中複製貼上程式碼可能遺漏私有輔助方法或造成 import 遺漏，導致 `ImportError` 或行為不一致 → 緩解：拆分後先跑 `uv run python manage.py check` 確認無 import 錯誤，再跑完整測試套件；tasks.md 中每個拆分步驟後都安排獨立驗證。
- [風險] 測試檔拆分時若不慎修改斷言，會違反專案 TDD 規範「測試不可為了遷就程式碼而修改」→ 緩解：測試拆分僅搬移既有測試方法到新檔案，不變更任何斷言內容；以 `git diff` 逐檔核對測試邏輯字元級一致。
- [風險] `flex_builder.py` re-export 層可能被誤認為是「真正的實作位置」，造成未來有人繼續往裡面加程式碼 → 緩解：在 `flex_builder.py` 檔案頂部加上簡短註解說明其為相容層，實作已搬至個別模組。
- [Trade-off] 保留 re-export 層代表本次變更未完全消除「呼叫端不知道實際實作位置」的間接性，但相對於一次性大範圍 import 改動，風險與 diff 範圍更可控，符合漸進式重構原則。

## Migration Plan

本次變更對「紅燈/綠燈」採三種不同定義，避免混用造成誤解：

- **既有行為搬移**（`PostbackBuilder`、`QuickReplyBuilder`、`FlexMessageBuilder`）：這些類別已有對應單元測試，屬於「基準綠燈 → 搬移程式碼與測試 → 仍是綠燈」，不刻意製造紅燈。先把測試 import 指向尚未建立的新模組只會得到 collection/import error，這是環境錯誤而非有效的行為紅燈，不採用。
- **補齊缺漏測試**（`FavoritesPageBuilder`、`LineMessageBuilder`）：目前無直接單元測試，依 CLAUDE.md 的 TDD 規範必須先寫測試。做法是先針對**舊實作位置**（`flex_builder.py` 中尚未搬移的類別）撰寫測試並執行至通過，確保測試描述的是既有真實契約，而不是搬移後才拼湊出來的期望值；測試通過後才將實作搬移到新模組，並把測試 import 一併改過去再跑一次確認仍通過。
- **相容層驗證**：透過獨立的 identity smoke test（Decision 6）直接斷言，不依賴其他測試間接證明。

步驟：

1. 依序為 `FavoritesPageBuilder`、`LineMessageBuilder` 補齊缺漏的單元測試（針對舊實作位置），確認通過後再進行搬移（見 tasks.md 第 5、6 節）。
2. 在 `line_bot/builders/` 下新增 5 個檔案，逐一搬移對應類別（含其私有輔助方法與必要 import）。
3. 將 `flex_builder.py` 改為 re-export 層。
4. 同步拆分 `line_bot/tests/test_flex_builder.py` 為 `line_bot/tests/builders/test_shop_flex_message.py` 等對應測試檔，並依 Decision 5 同步更新 `mock.patch` target（依 tasks.md 步驟）。
5. 新增相容層 identity smoke test（Decision 6）。
6. 每完成一個模組拆分，立即執行該模組對應測試 + 累積回歸測試 + `uv run python manage.py check`，確認通過後才進行下一個模組，並將該階段變更獨立 commit 作為最小回滾單位（見 tasks.md）。
7. 全部模組拆分完成後，執行完整測試套件與 `uv run ruff check .`，並手動確認三個呼叫端檔案（`event_handlers.py`、`postback_actions.py`、`helpers.py`）在未修改的情況下仍可正確 import。
8. Rollback：每個 Builder 拆分階段皆對應一個獨立 commit（見 tasks.md 各節結尾的 commit checkpoint），若某階段測試失敗且短時間內無法排除，可 `git revert` 該階段對應的單一 commit，不影響已完成且已驗證的其他階段；若需整批撤銷，則 revert 整個 `refactor/split-flex-builder` 分支範圍。因為 `flex_builder.py` 對外介面全程未變，任何一級回滾後呼叫端都不需調整。

## Open Questions

（無 — 拆分邊界、相容策略與驗證步驟已於上方 Decisions 確認，無需留待實作中另行決策。）
