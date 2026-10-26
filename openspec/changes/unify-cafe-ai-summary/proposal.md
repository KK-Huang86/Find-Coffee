## Why

同一間咖啡店目前會用同一批 Google 評論呼叫 Groq 兩次：

1. 建立／刷新店家時，背景任務 `generate_cafe_ai_summary` 產生 `ai_summary` 存入 DB，供描述搜尋比對
2. 使用者點「🤖 看看AI怎麼說」時，`handle_ask_ai` 再呼叫 `GroqAPI.review_cafe` 產生另一份評價，只存在 Redis 7 天

兩份內容來源相同，卻重複消耗 Groq 額度；Redis 快取過期或被清除後還會再打一次。

## What Changes

- 合併兩個 prompt：`SUMMARIZE_FOR_SEARCH_PROMPT` 改為涵蓋氛圍、適合族群、環境特色、是否適合工作或讀書、推薦商品，150 字以內，同時供搜尋比對與使用者閱讀
- **BREAKING**：移除 `GroqAPI.review_cafe` 與 `CAFE_REVIEW_PROMPT`
- `handle_ask_ai` 改為讀取 `Cafe.ai_summary`：
  - 已有摘要：直接回覆，不呼叫 Groq、不扣使用者額度
  - 尚無摘要：扣使用者額度，呼叫 `summarize_for_search` 當場產生，僅在 `ai_summary` 仍為空時寫入 DB
  - 店家沒有評論：回覆評論不足，不呼叫 Groq、不扣額度
- 移除 `ai_review:{place_id}` Redis 快取（既有 key 自然過期）

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cafe-ai-summary`：新增「使用者查看 AI 評價」的讀取與補產生行為，並定義摘要內容需同時供搜尋與使用者閱讀

## Impact

- **`integrations/groq/api.py`**：合併 prompt，移除 `review_cafe`
- **`line_bot/handlers/postback_actions.py`**：`handle_ask_ai` 改讀 DB
- **測試**：`integrations/tests/test_groq_api.py` 移除 `TestReviewCafe`（功能移除），新增 prompt 內容測試；`line_bot/tests/test_postback_actions.py` 新增 `TestHandleAskAi`
- 不影響 DB schema；背景任務 `generate_cafe_ai_summary` 行為不變
- 既有 `ai_summary` 不回補，下次評論變動刷新時才會以新 prompt 重產
