## Why

咖啡店卡片已直接顯示 `ai_summary`（見 `ai-summary-inline-display`），但資料庫中仍有店家沒有摘要：例如建立時 Groq 呼叫失敗、當時系統 AI 額度已用盡，或在 AI 摘要功能上線前就已存在的店家。這些店家只有等到 30 天刷新時才會重試，期間卡片不會顯示摘要，描述搜尋也會排除它們。需要一個可手動執行的補產工具。

## What Changes

- 新增 management command `backfill_ai_summary`：找出 `ai_summary` 為空值或純空白、且有 Google 評論的店家，逐筆排入既有的 `generate_cafe_ai_summary` 背景任務
- 支援 `--dry-run`（只列出數量與店家，不排入任務）、`--limit`（本次最多處理幾間）、`--interval`（每筆排入之間的間隔秒數，避免瞬間打爆 Groq rate limit）
- 依系統帳號當月剩餘 AI 額度限制排入數量，額度已用盡時直接結束並提示，不排入注定被跳過的任務
- 同一間店在短時間內重複執行不會重複排入（避免重複消耗額度）
- 新增 `scripts/backfill_ai_summary.sh`，在 docker compose 的 web container 內執行上述 command
- `LockService` 新增 `release`，`ApiUsageService` 新增查詢剩餘 AI 額度的方法

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cafe-ai-summary`：新增「可手動補產缺漏的 AI 摘要」requirement。

## Impact

- **新增** `cafe/management/commands/backfill_ai_summary.py`、`scripts/backfill_ai_summary.sh`
- **修改** `utils/utils.py`（`LockService.release`）、`integrations/services.py`（`get_remaining_ai_calls`）
- 不影響 DB schema、既有 Celery task 與摘要產生邏輯
- 補產會消耗系統帳號的 AI 額度（`monthly_ai_limit` 預設每月 50 次），與真人使用者額度分開
