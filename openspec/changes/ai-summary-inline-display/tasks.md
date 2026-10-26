## 1. 測試（先寫，確認紅燈）

- [x] 1.1 新增 Groq prompt unit test：`summarize_for_search` 送出的 prompt 要求 50–60 字、保留品項原名與具體環境特徵、只輸出摘要本身；空評論不呼叫 API（對應 spec: AI 摘要內容兼顧閱讀與搜尋比對）
- [x] 1.2 新增卡片 unit test：單筆與多筆有摘要時在營業時間後出現 separator（`margin: xxl`）、「🤖 評論摘要」標題與完整摘要文字，字級 `xs`、灰色、斜體、不設 `maxLines`；舊版 100 字摘要完整顯示；超過字數上限時截斷加省略號（對應 spec: 卡片完整顯示 AI 評論摘要）
- [x] 1.3 （併入 1.2；原多筆 `maxLines: 2` 因需求改為完整呈現而移除）
- [x] 1.4 新增邊界 unit test：`ai_summary` 為 `None`、空字串、純空白/換行、缺少 key 時單筆與多筆皆不出現摘要區塊與分隔線；摘要前後空白會被 strip（對應 spec: 無摘要時不顯示摘要區塊）
- [x] 1.5 新增回歸 unit test：有摘要時 footer 按鈕內容與順序、屬性標籤位置不變（對應 spec: 摘要區塊不影響既有卡片操作）
- [x] 1.6 確認既有 `cafe/tests/test_cafe_refresh.py` 摘要觸發測試已涵蓋「評論未變且有摘要不重產」（對應 spec: 摘要更新沿用店家資料刷新時機），不需新增實作
- [x] 1.7 執行新測試，確認 1.1–1.5 為紅燈

## 2. 實作

- [x] 2.1 改寫 `SUMMARIZE_FOR_SEARCH_PROMPT` 為 50–60 字、強調具體品項與環境特徵，`summarize_for_search` docstring 註明同時用於卡片顯示
- [x] 2.2 `FlexMessageBuilder.create_shop_flex_message` 新增摘要區塊（留白 + separator + 標題 + `xs` 灰色斜體，完整呈現、120 字上限，空白摘要不插入）

## 3. 驗證

- [x] 3.1 新測試全綠，完整 test suite 與 `ruff check` 通過
- [ ] 3.2 以數間真實店家評論手動呼叫新 prompt，比對新舊摘要對常見查詢詞（美式、肉桂捲、安靜、插座、適合工作）的命中情況，確認搜尋比對不退化，結果記錄於此
- [ ] 3.3 以 LINE Flex Message Simulator 或實機確認單筆與多筆卡片版面
- [x] 3.4 `openspec validate ai-summary-inline-display --strict` 通過
