## 1. 測試

- [x] 1.1 `integrations/tests/test_groq_api.py`：新增 prompt 內容測試（推薦商品、工作或讀書、150 字）與 `review_cafe` 已移除測試；移除 `TestReviewCafe`（功能移除）
- [x] 1.2 `line_bot/tests/test_postback_actions.py`：新增 `TestHandleAskAi`，涵蓋缺 place_id、找不到店、Google 額度用盡、已有摘要、空字串摘要、無評論、使用者額度用盡、產生成功、Groq 失敗、背景任務搶先寫入、重複點擊、不使用 Redis 快取
- [x] 1.3 未實作前執行測試，確認新測試為紅燈

## 2. 實作

- [x] 2.1 合併 `SUMMARIZE_FOR_SEARCH_PROMPT`，移除 `CAFE_REVIEW_PROMPT` 與 `GroqAPI.review_cafe`
- [x] 2.2 `handle_ask_ai` 改讀 `ai_summary`，空值時當場產生並條件式寫入

## 3. 驗證

- [x] 3.1 新測試全綠，完整 test suite 與 `ruff check` 通過
- [x] 3.2 `openspec validate unify-cafe-ai-summary --strict` 通過
