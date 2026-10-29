## Why

咖啡店卡片已直接顯示 `ai_summary`（見 `ai-summary-inline-display`），但資料庫中仍有店家沒有摘要：例如建立時 Groq 呼叫失敗、當時系統 AI 額度已用盡，或在 AI 摘要功能上線前就已存在的店家。這些店家只有等到 30 天刷新時才會重試，期間卡片不會顯示摘要，描述搜尋也會排除它們。需要一個可手動執行的補產工具。

其中「系統 AI 額度已用盡」是主要成因：背景摘要記在系統帳號，月上限（預設 50 次）用完後新店家的摘要會被靜默跳過。背景摘要是系統行為，不應被額度擋住；只有使用者主動觸發的 AI 功能（AI 評價、描述搜尋）才扣該使用者的額度。

## What Changes

- 新增 management command `backfill_ai_summary`：找出 `ai_summary` 為空值或純空白、且有 Google 評論的店家，逐筆排入既有的 `generate_cafe_ai_summary` 背景任務
- 支援 `--dry-run`（只列出數量與店家，不排入任務）、`--limit`（本次最多處理幾間）、`--interval`（每筆排入之間的間隔秒數，預設 25 秒，避免超過 Groq 每分鐘 token 上限）
- 同一間店在短時間內重複執行不會重複排入（避免重複呼叫 Groq）
- 新增 `scripts/backfill_ai_summary.sh`，在 docker compose 的 web container 內執行上述 command
- **背景 AI 摘要不再受額度阻擋**：`generate_cafe_ai_summary` 移除系統帳號月上限檢查，成功後以新的 `ApiUsageService.record_ai_call` 在系統帳號記錄用量（只記錄、不阻擋）；失敗時不記錄。真人使用者的 AI 評價與描述搜尋扣額度行為不變
- `LockService` 新增 `release`

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cafe-ai-summary`：新增「可手動補產缺漏的 AI 摘要」與「AI 摘要產生不受額度限制但需記錄用量」；修改失敗處理 requirement（改為不記錄用量）；移除「AI 摘要產生需遵守呼叫額度」。

## Impact

- **新增** `cafe/management/commands/backfill_ai_summary.py`、`scripts/backfill_ai_summary.sh`
- **修改** `utils/utils.py`（`LockService.release`）、`integrations/services.py`（`record_ai_call`）、`cafe/tasks.py`（`generate_cafe_ai_summary` 移除額度檢查）
- 不影響 DB schema；系統帳號的 `monthly_ai_limit` / `can_use_ai` 不再影響背景摘要，用量數字仍會累加
- Groq 呼叫量的實際上限改由 Groq 本身的速率限制與摘要觸發頻率（新店建立、30 天刷新且評論有變）決定
