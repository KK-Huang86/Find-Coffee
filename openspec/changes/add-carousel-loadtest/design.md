## Context

- Google 網址原本寫死在三處；LINE SDK 的 `Configuration` 使用預設 host。
- webhook `/callback` 同步處理事件，回應時間即為完整處理時間，適合直接用 K6 量測。
- gunicorn 為 3 個 sync worker、`--timeout 30`；PgBouncer `DEFAULT_POOL_SIZE=10`。

## Goals / Non-Goals

**Goals:**
- 量測多筆搜尋在「全部快取」、「資料過期需同步刷新」、「照片 reference 失效需重試」三種情境的回應時間
- 壓測過程不呼叫真實 Google / LINE / S3 / Groq，不影響開發環境的資料

**Non-Goals:**
- 不量測正式環境或真實 Google 的延遲分布
- 不比較修改前的舊版本（舊版沒有可設定的外部位址，無法在不打真實 Google 的前提下壓測）

## Decisions

**1. 外部位址以環境變數設定，預設為正式網址**
- `GOOGLE_MAPS_BASE_URL`、`LINE_API_HOST` 未設定時行為與修改前完全相同。

**2. 多層防護避免打到真實外部服務**
- 位址指向 mock；金鑰一律為假值（漏網請求只會被拒絕、不計費）；`run.sh` 執行前檢查環境變數與程式內實際使用的位址，不符合即中止；壓測 broker 使用沒有 worker 的 Redis db，不會執行 S3 上傳與 Groq 呼叫。

**3. 與開發環境隔離**
- 獨立資料庫 `find_coffee_loadtest`、獨立 `pgbouncer-loadtest`（edoburu 映像只代理 `DB_NAME` 指定的資料庫）、Redis db 2 / 3；壓測服務設定 `profiles: [loadtest]`。
- `seed.py` 檢查目前資料庫名稱，非 `find_coffee_loadtest` 拒絕執行。

**4. 每個 iteration 使用不同使用者與不同店家組**
- 使用者 lock 為 2 秒，同一使用者連續請求會被節流而失真。
- 過期店家刷新後即不再過期，同一組店家不能重複使用。

**5. mock server 只用標準函式庫**
- `ThreadingHTTPServer`，以環境變數模擬延遲；`/__stats` 提供呼叫次數，用來驗證沒有重複刷新、沒有呼叫未 mock 的端點。

## Risks / Trade-offs

- [限制] mock 延遲為固定值，無法反映真實長尾；可用 `DETAIL_LATENCY_MS` 等參數另外模擬。
- [限制] 本機 Docker 規格與正式環境不同，數字用於比較情境之間的差異，不代表正式環境絕對值。
