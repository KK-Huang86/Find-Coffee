## Context

- `Cafe.ai_summary` 已由 `generate_cafe_ai_summary` 背景任務產生並存入 DB，觸發時機見 `openspec/specs/cafe-ai-summary`；`Cafe.to_dict()` 已包含 `ai_summary`，卡片 builder 拿到的 `info` dict 不需額外查詢。
- 描述搜尋的降級路徑以 `ai_summary__icontains=<keyword>` 比對（`cafe/services/search_service.py`），因此摘要裡有沒有出現使用者會打的字（「肉桂捲」「美式」「安靜」）直接決定能否命中。
- 單筆與多筆卡片共用 `FlexMessageBuilder.create_shop_flex_message`，以 `is_multiple` 區分。
- LINE carousel 每張 bubble 會被拉到與最高的一張同高，多筆卡片的文字長度會放大成整排卡片的高度。

## Goals / Non-Goals

**Goals:**
- 不增加任何 Groq 呼叫與 DB 欄位，直接重用 `ai_summary`
- 新 prompt 產出的摘要短而具體，同時改善卡片閱讀與關鍵字比對

**Non-Goals:**
- 不回填（backfill）既有店家的舊摘要
- 不改動 `handle_ask_ai`、Redis 快取與 AI 評價 prompt
- 不改動描述搜尋的比對邏輯

## Decisions

### 摘要區塊放在 body 最後，以 separator 區隔
放在營業時間之後、footer 之前。基本資訊是使用者決策的硬條件，摘要是輔助印象，放後面且用 `xs` + `#999999` 降低視覺權重，避免與地址電話搶注意力。標題用「🤖 評論摘要」明確標示為 AI 產出。

替代方案：放在店名下方 — 視覺權重過高，且會把屬性標籤往下推。

### 行數限制用 LINE text 的 `maxLines`
- 多筆：`maxLines: 2`，控制 carousel 整排高度
- 單筆：`maxLines: 4`，新 prompt 的 50–60 字在 xs 字級約 3 行，4 行足夠完整顯示；舊版 100 字摘要會被截斷，作為過渡期防護

替代方案：在 Python 端以字數截斷 — 中英混排寬度不一，字數無法準確對應行數，交給 LINE 排版較可靠。

### 另設字數上限保護 payload
`maxLines` 只影響畫面，完整字串仍會送進 Flex JSON。模型不守字數時，一則長摘要乘上 carousel 10 張卡片可能超過 LINE bubble 30KB / carousel 50KB 上限，導致整則回覆失敗。因此 builder 端另設 `AI_SUMMARY_MAX_CHARS = 120`，超過即截斷加「…」。上限高於舊版 100 字，避免誤截舊資料。

替代方案：Groq 呼叫設 `max_tokens` — gpt-oss-20b 為推理模型，`max_tokens` 會連推理 token 一起計算，可能讓輸出被截成空字串；且無法保護已存在 DB 的資料。

### 空白摘要視同無摘要
以 `(info.get('ai_summary') or '').strip()` 判斷，空值與純空白都不插入區塊，避免出現只有標題的空殼。

### Prompt 改寫重點
- 字數 100 → 50–60 字
- 明確要求「保留評論中提到的品項原名」與「具體環境特徵」，並禁止空泛形容詞（如「很棒」「氛圍不錯」）
- 保留既有「只寫摘要本身，不要前綴、標題、引號」
- 常數名 `SUMMARIZE_FOR_SEARCH_PROMPT` 與方法名 `summarize_for_search` 不改名，避免擴大 diff；在 docstring 註明同時用於顯示

## Risks / Trade-offs

- [摘要縮短可能讓部分描述搜尋關鍵字不再命中] → prompt 要求保留品項與環境關鍵字；實作後以真實店家評論手動抽樣比對新舊摘要，對常見查詢詞（美式、肉桂捲、安靜、插座、適合工作）確認命中不退化，結果記錄在 tasks
- [LLM 不一定遵守字數] → 卡片端 `maxLines` 兜底，不依賴模型守規矩
- [舊摘要與新摘要風格並存一段時間] → 可接受；舊摘要在評論變動時自然被替換，單筆卡片以 `maxLines: 4` 截斷
- [AI 摘要可能與事實不符] → 標題明示「評論摘要」，使用者可自行判斷；詳細評價仍可透過「看看AI怎麼說」或 Google Maps 查看

## Migration Plan

純程式碼變更，無 migration。部署後新產生的摘要即套用新 prompt；rollback 只需 revert commit，已用新 prompt 產生的摘要仍可被舊版程式正常使用。
