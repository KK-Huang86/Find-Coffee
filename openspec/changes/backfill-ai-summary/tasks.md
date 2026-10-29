## 1. 測試（先寫，確認紅燈）

- [x] 1.1 `LockService.release` unit test：釋放後可再次取得、釋放不存在的鎖不拋例外、不影響其他 key
- [x] 1.2 `ApiUsageService.get_remaining_ai_calls` unit test：無紀錄時為完整額度、已用部分、已用盡、`can_use_ai=False`、`ai_calls` 超過上限時不為負數
- [x] 1.3 `backfill_ai_summary` command unit test：只排入空值/純空白且有評論的店家；`--dry-run` 不排入；`--limit`；額度不足時依剩餘額度截斷；額度用盡時不排入；重複執行不重複排入；排入失敗時釋放鎖並以 `CommandError` 結束；每筆之間呼叫 sleep、預設間隔 25 秒；`--limit`、`--interval` 不接受負數（對應 spec: 可手動補產缺漏的 AI 摘要）
- [x] 1.4 執行新測試，確認為紅燈

## 2. 實作

- [x] 2.1 `LockService.release`
- [x] 2.2 `ApiUsageService.get_remaining_ai_calls`
- [x] 2.3 `cafe/management/commands/backfill_ai_summary.py`
- [x] 2.4 `scripts/backfill_ai_summary.sh`（含 wrapper 測試：工作目錄、參數原樣傳遞、service 可覆寫、失敗 exit code）

## 3. 驗證

- [x] 3.1 新測試全綠，完整 test suite 與 `ruff check` 通過
- [x] 3.2 `openspec validate backfill-ai-summary --strict` 通過
- [ ] 3.3 於本機或正式環境先以 `--dry-run` 確認目標數量，再實際執行（本機 PostgreSQL 已以 `--dry-run` 驗證查詢條件，找到 233 間）
