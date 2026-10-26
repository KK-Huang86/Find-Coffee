## Why

目前 AI 對咖啡店的評價只能透過操作選單的「🤖 看看AI怎麼說」按鈕取得，入口藏得深，多數使用者不會點到。使用者在挑店時最需要的是「這間店大概是什麼樣子」的一句話印象（類似 Google 評論摘要），而系統其實已經為每間店產生並儲存了 `ai_summary`，只是只拿來做描述搜尋比對，沒有顯示給使用者。

## What Changes

- 咖啡店 Flex 卡片在地址、電話、營業時間下方新增「🤖 評論摘要」區塊，以小字灰色顯示 `ai_summary`
  - 單筆詳細卡片：顯示完整摘要（設行數上限作為防護）
  - 多筆 carousel 卡片：最多顯示 2 行，超出以省略號截斷
  - 店家尚無摘要（尚未產生、無評論、產生失敗）時整個區塊不顯示，不放 placeholder
- 改寫 AI 摘要的 prompt：由 100 字改為 50–60 字，兼顧人閱讀與描述搜尋比對，要求寫出具體特色與推薦品項（例如美式、肉桂捲），避免空泛形容詞
- 摘要更新時機不變：沿用既有 30 天店家資料刷新，評論有變化或摘要為空時才重新產生；不新增欄位、不新增獨立的摘要過期規則
- 「🤖 看看AI怎麼說」按鈕保留，作為想看更詳細評價的入口

## Capabilities

### New Capabilities

- `cafe-ai-summary-display`：定義咖啡店 Flex 卡片（單筆與多筆）顯示 AI 摘要的位置、樣式、行數限制與無摘要時的行為。

### Modified Capabilities

- `cafe-ai-summary`：新增摘要內容規格（字數、須包含具體特色與品項關鍵字、純文字無前綴），使摘要同時適合顯示給使用者與描述搜尋比對。

## Impact

- **`integrations/groq/api.py`**：改寫 `SUMMARIZE_FOR_SEARCH_PROMPT`
- **`line_bot/builders/shop_flex_message.py`**：`create_shop_flex_message` 新增摘要區塊
- **測試**：`integrations` Groq prompt 測試、`line_bot/tests/builders/test_shop_flex_message.py`
- 不影響 DB schema、Celery task 流程、額度控管與 postback 路由
- 既有的 100 字舊摘要會保留到該店下次評論變動才被新 prompt 取代，期間由行數上限保護版面
