## Context

- 摘要產生由 `generate_cafe_ai_summary` 背景任務負責，任務內已處理額度檢查、失敗回補額度與不覆寫錯誤資料（見 `openspec/specs/cafe-ai-summary`），補產只需負責「找出目標並排程」。
- 生產環境 Celery broker 為 SQS；ETA / countdown 任務會在 worker 端持有，超過 SQS visibility timeout 會被重新投遞而重複執行。
- 系統帳號 AI 額度預設每月 50 次（`ApiUsageRecord.monthly_ai_limit`），額度用盡時任務會直接跳過。

## Goals / Non-Goals

**Goals:**
- 一次性、可重複執行的補產工具，失敗可重跑
- 不在短時間內打爆 Groq rate limit，也不排入注定因額度不足被跳過的任務

**Non-Goals:**
- 不重產已有摘要的店家（包含舊 prompt 產生的摘要）
- 不排程自動執行（cron / Celery beat）
- 不修改 `generate_cafe_ai_summary` 任務本身

## Decisions

### 以 command 端 sleep 控制節奏，而非 Celery countdown
每排入一筆後 `time.sleep(interval)`。使用 countdown 分散時間的話，大量任務的 ETA 會超過 SQS visibility timeout，造成重複投遞與重複扣額度。command 端 sleep 讓排入速度約等於處理速度，代價只是 command 執行較久，對一次性維運工具可接受。

### 先依剩餘額度限制數量
執行前查詢系統帳號當月剩餘 AI 額度，排入數量取 `min(符合條件數, --limit, 剩餘額度)`。額度為 0 時直接結束。這只是減少無效任務的預估值，真正的額度把關仍在任務內的 `try_increment_ai_calls`（原子更新），因此與其他同時產生摘要的流程併發時也不會超用。

### 以 LockService 防止重複排入
每間店排入前 `LockService.acquire(cafe.id, 'ai_summary_backfill', ttl=600)`，拿不到鎖代表 10 分鐘內已排入過，跳過。排入失敗時 `release` 鎖，讓下次執行可以重試。不使用 DB 欄位標記，避免為一次性工具新增 schema。

### 排入失敗時中止並回報
broker 連線錯誤通常會連續發生，繼續嘗試沒有意義。記錄 log、釋放該店的鎖後以 `CommandError` 結束，訊息包含已成功排入的數量。已排入的任務照常執行；重跑時已產生摘要的店家會自然被排除。

### 空白判斷
目標條件為 `ai_summary IS NULL` 或只含空白字元（DB 端以 regex `^\s*$` 判斷；PostgreSQL `TRIM` 只去除空格、不含換行，因此不採用），`reviews` 排除 `NULL` 與空陣列。依 `id` 排序，讓 `--limit` 結果可預期。

## Risks / Trade-offs

- [預估剩餘額度與實際有落差（例如同時有新店建立也在用額度）] → 任務內額度檢查才是最終把關，超出的任務只會被跳過並記 log
- [鎖存在 Redis，Redis 重啟後失效] → 最差情況是重複排入，任務本身冪等（只覆寫為最後一次成功結果），多扣的額度有上限
- [command 執行期間被中斷] → 已排入的任務照常執行，重跑即可接續
