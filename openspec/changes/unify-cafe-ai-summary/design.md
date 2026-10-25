## Context

`Cafe.ai_summary` 由背景任務在店家建立（有評論時）與刷新（評論變動或摘要為空）時產生，額度記在系統帳號。`handle_ask_ai` 原本另外呼叫 `review_cafe`，額度記在點擊的使用者，結果存 Redis。

## Goals / Non-Goals

**Goals:**
- 每間店只保留一份 AI 文字（`ai_summary`），搜尋與使用者閱讀共用
- 已有摘要時，點擊 AI 評價不呼叫 Groq

**Non-Goals:**
- 不新增欄位、不做 migration
- 不回補既有摘要
- 不改背景任務的觸發條件與覆寫行為

## Decisions

### Decision 1：點擊時摘要為空就當場產生，而非請使用者稍後再試

新店家建立後背景任務尚未完成、先前失敗或系統額度用盡時，`ai_summary` 會是空的。當場產生能讓使用者立即拿到結果，且寫入 DB 後所有人與搜尋都能共用，之後不再重複呼叫。額度記在點擊的使用者，與原本 `review_cafe` 的計費對象一致。

### Decision 2：點擊路徑只在 `ai_summary` 為空時寫入（條件式 update）

以 `filter(pk=..., ai_summary 為 NULL 或空字串).update(...)` 寫入。若背景任務在使用者等待 Groq 期間先寫入，條件不成立、update 影響 0 筆，此時重新讀取 DB 並回覆 DB 的版本，確保使用者看到的與搜尋比對的是同一份。

**替代方案**：Redis lock 包住「讀 → 呼叫 Groq → 寫」。不採用：背景任務與點擊在不同 process，要共用 lock 需同時修改任務；而 race 的代價只是極少數情況多打一次 Groq，資料仍一致。

### Decision 3：背景任務維持無條件覆寫

刷新時評論變動需要以新評論重產摘要，覆寫是正確行為。點擊路徑與背景任務同時執行時，最終值可能是任一方的成功結果，兩者都由同一個 prompt 與相同評論產生，可接受。

### Decision 4：空字串視同沒有摘要

`ai_summary` 為 `''` 時無法提供給使用者，與 `NULL` 同樣走產生流程。

## Risks / Trade-offs

- 使用者看到的內容由 150 字的合併 prompt 產生，舊店家在重產前仍是 100 字的搜尋摘要，可能沒有推薦商品。
- 搜尋以 `icontains` 比對摘要，內容增加推薦商品後，比對到的關鍵字可能變多。
- 極少數 race 會多打一次 Groq（見 Decision 2）。
