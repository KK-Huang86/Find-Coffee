## Why

當咖啡店同時擁有「插座」、「有貓貓狗狗」、「寵物友善」、「限時」四種屬性時，TAG 全部排在同一水平列（`layout: 'horizontal'`），超出 LINE Flex Message 容器寬度後被截斷，使用者無法看到完整資訊。

## What Changes

- 將 `_create_tags_box` 的單列水平排列改為多列自動換行排列
- 當 tag 數量超過 2 個時，自動分成多列（每列最多 2 個 tag），以垂直 box 包裹多個水平 box
- 不影響 TAG_STYLES 的顏色與樣式定義

## Capabilities

### New Capabilities

- `tag-multiline-layout`: 標籤容器支援多列換行顯示，確保 1~4 個 tag 皆完整可見

### Modified Capabilities

（無需求層級變更）

## Impact

- `line_bot/builders/flex_builder.py`：`_create_tags_box` 方法邏輯調整
- 不影響 LINE Flex Message API 相容性（仍使用 box + horizontal/vertical layout）
- 不影響其他 builder 方法或資料庫 model
