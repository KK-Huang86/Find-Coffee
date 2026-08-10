## Why

`line_bot/builders/flex_builder.py` 目前已成長至 1018 行，內含 5 個職責明顯不同的類別（`FlexMessageBuilder`、`LineMessageBuilder`、`PostbackBuilder`、`FavoritesPageBuilder`、`QuickReplyBuilder`），單一檔案混雜「Flex Message 組裝」「訊息發送」「Postback payload 組裝」「收藏頁分頁」「Quick Reply 組裝」等不同關注點，導致：

- 修改任一功能時需要在近千行檔案中定位，容易誤改到不相關類別。
- Code review 時 diff 範圍難以聚焦，增加審查成本。
- 新增 builder 邏輯時，命名與職責邊界越來越模糊。

拆分此檔案可依既有類別邊界切成多個高內聚模組，降低單檔複雜度，不改變任何對外行為。

## What Changes

- 將 `line_bot/builders/flex_builder.py` 依現有 5 個類別的職責邊界拆分為多個檔案，放置於 `line_bot/builders/` 目錄下：
  - `shop_flex_message.py`：`FlexMessageBuilder`（店家 Flex Message 組裝、照片 URL、標籤、營業時間格式化）
  - `message_sender.py`：`LineMessageBuilder`（組裝並透過 LINE Bot API 發送店家搜尋結果）
  - `postback.py`：`PostbackBuilder`（店家操作 postback payload 組裝）
  - `favorites_page.py`：`FavoritesPageBuilder`（收藏清單分頁訊息組裝）
  - `quick_reply.py`：`QuickReplyBuilder`（各類 Quick Reply 組裝）
- 保留 `line_bot/builders/flex_builder.py` 作為相容 re-export 模組（`from .shop_flex_message import FlexMessageBuilder` 等），避免一次性改動所有呼叫端 import，降低風險；後續可視情況再清理呼叫端 import 路徑。
- 同步拆分既有測試檔 `line_bot/tests/test_flex_builder.py`，依相同類別邊界拆成對應測試檔，並全數維持通過。
- 不新增、不修改、不刪除任何對外行為、API 介面或資料結構。

## Capabilities

本變更為純重構（pure refactor）：僅搬動程式碼位置、不改變任何 spec 層級的行為，因此不宣告新增或修改 capability，並於 `.openspec.yaml` 設定 `skip_specs: true`。

### New Capabilities
（無）

### Modified Capabilities
（無）

## Impact

- **受影響程式碼**：
  - `line_bot/builders/flex_builder.py`（拆分為 re-export 模組）
  - 新增 `line_bot/builders/shop_flex_message.py`、`message_sender.py`、`postback.py`、`favorites_page.py`、`quick_reply.py`
  - `line_bot/tests/test_flex_builder.py`（拆分為對應測試檔）
- **間接受影響（僅透過 re-export 相容，不需修改）**：
  - `line_bot/event_handlers.py`
  - `line_bot/handlers/postback_actions.py`
  - `line_bot/handlers/helpers.py`
- **不受影響**：對外 LINE Bot 行為、資料庫 model、Celery tasks、API 介面。
