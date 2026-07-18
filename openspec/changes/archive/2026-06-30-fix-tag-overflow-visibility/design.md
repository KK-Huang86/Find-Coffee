## Context

LINE Flex Message 的 `box` 元件在 `layout: 'horizontal'` 模式下不支援自動換行。目前 `_create_tags_box` 將所有 tag 放入同一個水平 box，當 tag 數量達到 4 個時（插座 + 有貓貓狗狗 + 寵物友善 + 限時），各 tag 的寬度加總超過容器寬度，導致末端 tag 被截斷不可見。

現有結構：
```
box (horizontal)
├── tag1
├── tag2
├── tag3
└── tag4  ← 被截斷
```

## Goals / Non-Goals

**Goals:**
- 1~4 個 tag 皆完整顯示，不被截斷
- 視覺排列整齊，維持現有 tag 樣式（顏色、圓角、padding）
- 邏輯集中在 `_create_tags_box`，不影響呼叫端

**Non-Goals:**
- 不修改 TAG_STYLES 樣式定義
- 不改變 tag 的產生邏輯（`_create_attribute_tags`）
- 不支援超過 4 個 tag 的情境（目前最多 4 種屬性）

## Decisions

### 決策：分列顯示（每列最多 2 個 tag）

將 tag 清單以 2 個為一組切割，每組包成一個 `horizontal` box，再由外層 `vertical` box 統整。

```
box (vertical, spacing: sm)
├── box (horizontal, spacing: sm)
│   ├── tag1
│   └── tag2
└── box (horizontal, spacing: sm)
    ├── tag3
    └── tag4
```

**選此方案原因：**
- LINE Flex Message 原生支援 vertical + horizontal 巢狀 box，相容性最高
- 不依賴任何 wrap 屬性（部分舊版 LINE 客戶端可能不支援）
- tag 數量 ≤ 2 時維持單列，不改變現有外觀

**排除方案：**
- `wrap: true` on text element：只對文字換行，不適用於 box 內的多個 element 排列
- 縮小 tag 字體/padding：犧牲可讀性，非根本解法

### 決策：切割閾值為 2

每列放 2 個 tag，確保中文 tag 文字（最長約 6 字）在各種螢幕寬度下都有足夠空間。

## Risks / Trade-offs

- [外觀差異] 原本 1~2 個 tag 的咖啡店顯示不變，3~4 個的會從單列變為兩列，整體卡片高度略增 → 屬預期中的改善，可接受
- [測試覆蓋] 現有 `test_flex_builder.py` 需補充 3、4 個 tag 的情境測試 → 在 tasks 中安排

## Migration Plan

純前端 Flex Message 結構調整，無資料庫 migration，無 API 版本變更。部署後即生效，LINE 客戶端重新渲染訊息時自動套用新結構。
