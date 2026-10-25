## Why

使用者在單筆咖啡店詳細卡片看到店家電話後，只能手動抄寫或複製再撥號。提供一鍵撥號可縮短「找到店 → 聯絡店家（訂位、確認營業）」的流程。

原本考慮加在 `PostbackBuilder.create_cafe_action_postback` 的 buttons template，但 LINE buttons template 最多 4 個 action，目前已滿（收藏、分享、評價、AI），因此改放在單筆詳細 Flex 卡片的 footer。

## What Changes

- 單筆詳細卡片（`is_multiple=False`）footer 新增「打電話」按鈕，使用 `tel:` URI action，點擊後開啟手機撥號畫面並帶入店家電話
- 新增電話字串轉 `tel:` URI 的正規化邏輯：去除空白、連字號、括號，保留開頭 `+`，移除分機，全形數字轉半形
- 電話缺失、為佔位字串（`無提供`、`未提供電話`）或格式不合法時不顯示按鈕
- 多筆結果 carousel 卡片維持不變

## Capabilities

### New Capabilities

- `shop-phone-call`：定義單筆咖啡店詳細卡片的一鍵撥號按鈕與電話正規化規則。

### Modified Capabilities

（無）

## Impact

- **`line_bot/builders/shop_flex_message.py`**：新增 `_build_tel_uri`，單筆 footer 加入「打電話」按鈕
- **`line_bot/tests/builders/test_shop_flex_message.py`**：新增 unit test
- 不影響 DB schema、Google Places 欄位與 postback 路由
