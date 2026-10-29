## Context

- 摘要產生由 `generate_cafe_ai_summary` 背景任務負責，任務內已處理用量記錄與不覆寫錯誤資料（見 `openspec/specs/cafe-ai-summary`），補產只需負責「找出目標並排程」。
- 生產環境 Celery broker 為 SQS；ETA / countdown 任務會在 worker 端持有，超過 SQS visibility timeout 會被重新投遞而重複執行。
- 原本系統帳號 AI 額度預設每月 50 次（`ApiUsageRecord.monthly_ai_limit`），用盡時任務直接跳過；本機 10 月因此累積 233 間店缺摘要。

## Goals / Non-Goals

**Goals:**
- 一次性、可重複執行的補產工具，失敗可重跑
- 不在短時間內打爆 Groq rate limit

**Non-Goals:**
- 不重產已有摘要的店家（包含舊 prompt 產生的摘要）
- 不排程自動執行（cron / Celery beat）
- 不修改 `generate_cafe_ai_summary` 任務本身

## Decisions

### 以 command 端 sleep 控制節奏，而非 Celery countdown
每排入一筆後 `time.sleep(interval)`。使用 countdown 分散時間的話，大量任務的 ETA 會超過 SQS visibility timeout，造成重複投遞與重複呼叫 Groq。command 端 sleep 讓排入速度約等於處理速度，代價只是 command 執行較久，對一次性維運工具可接受。

預設間隔 25 秒：Groq `openai/gpt-oss-20b` 的 TPM 上限為 8000，每次摘要約 2–3k tokens（含推理 token），每分鐘最多約 3 筆。本機實測以 2 秒間隔排入 50 筆，37 筆因 429 失敗（失敗不記錄用量、不覆寫摘要）。50 筆約需 21 分鐘。

### 背景摘要只記錄用量、不受額度阻擋
`generate_cafe_ai_summary` 移除 `try_increment_ai_calls` / `revert_ai_call`，改為成功寫入摘要後呼叫 `ApiUsageService.record_ai_call(system_user_id)`，以 `F('ai_calls') + 1` 原子累加，不檢查 `monthly_ai_limit` 與 `can_use_ai`。

- 為什麼不擋：摘要只在新店建立或 30 天刷新且評論有變時產生，兩者都要先消耗使用者的 Google Places 額度，本身已有頻率約束；月上限只會讓摘要靜默缺漏
- 為什麼仍記錄：保留系統帳號每月 Groq 實際用量，方便觀察成本
- 為什麼成功後才記：不再先佔額度，就不需要失敗時 revert；記錄的是「成功產生的摘要數」
- 真人使用者的 AI 評價與描述搜尋仍走 `try_increment_ai_calls`，行為不變

替代方案：保留上限但調高預設值 — 只是延後問題發生，用完時仍會靜默缺漏。

補產 command 因此不再查詢剩餘額度，`--limit` 是唯一的數量控制。

### 以 LockService 防止重複排入
每間店排入前 `LockService.acquire(cafe.id, 'ai_summary_backfill', ttl=600)`，拿不到鎖代表 10 分鐘內已排入過，跳過。排入失敗時 `release` 鎖，讓下次執行可以重試。不使用 DB 欄位標記，避免為一次性工具新增 schema。

### 排入失敗時中止並回報
broker 連線錯誤通常會連續發生，繼續嘗試沒有意義。記錄 log、釋放該店的鎖後以 `CommandError` 結束，訊息包含已成功排入的數量。已排入的任務照常執行；重跑時已產生摘要的店家會自然被排除。

### 空白判斷
目標條件為 `ai_summary IS NULL` 或只含空白字元（DB 端以 regex `^\s*$` 判斷；PostgreSQL `TRIM` 只去除空格、不含換行，因此不採用），`reviews` 排除 `NULL` 與空陣列。依 `id` 排序，讓 `--limit` 結果可預期。

## Risks / Trade-offs

- [背景摘要沒有月上限，Groq 用量可能超出預期] → 觸發頻率受 Google Places 使用者額度間接約束；系統帳號仍記錄每月用量可供監控；Groq 端也有自己的速率限制
- [鎖存在 Redis，Redis 重啟後失效] → 最差情況是重複排入，任務本身冪等（只覆寫為最後一次成功結果），多呼叫的 Groq 次數有上限
- [command 執行期間被中斷] → 已排入的任務照常執行，重跑即可接續
