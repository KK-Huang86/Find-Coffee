# 多筆搜尋回應時間壓測（K6 + mock server）

量測「多筆搜尋結果（carousel，10 間店）」從 LINE webhook 進來到回覆完成的時間。webhook 為同步處理，`/callback` 的回應時間即為完整處理時間。

## 不會打到真的 Google / LINE

| 保護 | 做法 |
|---|---|
| 位址導向 mock | `GOOGLE_MAPS_BASE_URL`、`LINE_API_HOST` 指向 `mock-external`（`loadtest/mock_server.py`） |
| 金鑰為假值 | `GOOGLE_API_KEY=loadtest-fake-key` 等；即使請求漏到真的 Google，也只會回 `REQUEST_DENIED`，不計費、不推播 |
| 執行前檢查 | `run.sh` 先確認 container 環境變數與程式內實際使用的位址都是 mock，否則中止 |
| 不跑 celery | 壓測用的 broker 是 Redis db 3，沒有 worker 消費，不會上傳 S3、不會呼叫 Groq；結束後清空 |
| 資料隔離 | 獨立資料庫 `find_coffee_loadtest`（經 `pgbouncer-loadtest`）、Redis db 2；`seed.py` 只在該資料庫執行 |

mock server 的 `GET /__stats` 會回傳各端點被呼叫次數，用來確認呼叫次數符合預期（例如每次搜尋剛好 10 次 Places Detail）。

## 執行

```bash
loadtest/run.sh                         # 三個情境全跑
loadtest/run.sh stale                   # 只跑指定情境
VUS=5 ITERATIONS=30 loadtest/run.sh     # 調整並發數與次數
DETAIL_LATENCY_MS=1000 loadtest/run.sh  # 模擬 Google 變慢
```

結果存在 `loadtest/results/<時間>/`（不進版控）。

## 情境

| 情境 | 店家狀態（10 間） | 預期外部呼叫 |
|---|---|---|
| `cached` | 資料未過期、已有 S3 照片 | 只有 LINE（loading + reply） |
| `stale` | 從未刷新、沒有 S3 照片、reference 已失效 | 平行刷新 10 次 Detail → 用新 reference 解析 10 張照片 |
| `expired_photo` | 資料未過期、reference 已失效、沒有 S3 照片 | 照片 403 → 刷新 → 用新 reference 重試，各 10 次 |

## 結果（2026-10-25，本機 Docker，gunicorn 3 sync workers）

mock 延遲：Places Detail 300ms、Photo 150ms、LINE 50ms。

**VUS=1，15 次（單一請求延遲，不含排隊）**

| 情境 | min | med | p95 | max |
|---|---|---|---|---|
| cached | 164ms | 173ms | 612ms | 1.56s |
| stale | 666ms | 735ms | 841ms | 942ms |
| expired_photo | 828ms | 896ms | 956ms | 997ms |

**VUS=5，30 次（5 人同時查詢，worker 只有 3 個）**

| 情境 | min | med | p95 | max |
|---|---|---|---|---|
| cached | 176ms | 327ms | 508ms | 548ms |
| stale | 875ms | 1.08s | 1.73s | 2.38s |
| expired_photo | 889ms | 1.17s | 2.04s | 2.07s |

mock 呼叫次數完全符合預期：`stale` 每次搜尋剛好 10 次 Detail、10 次照片解析；`expired_photo` 每次剛好 10 次 403、10 次 Detail、10 次重試。沒有重複刷新，也沒有呼叫到未 mock 的端點。

## 解讀

- **平行化有效**：`stale` 的中位數 735ms ≈ 基準 173ms + Detail 300ms + Photo 150ms + 額外開銷。若 10 間店依序處理，光外部呼叫就要 10 × (300 + 150) = 4.5 秒。
- **同步刷新的成本**：有過期店家時，比全部快取多約 0.5～0.7 秒（取決於 Google 的實際延遲），換來回覆的是最新資料與真實照片。
- **`cached` 的 p95 / max 偏高**是每個 gunicorn worker 第一次處理請求時載入 jieba 斷詞字典（log 顯示約 0.6～0.9 秒），不是穩態延遲。
- **VUS=5 變慢**主要來自 gunicorn 只有 3 個 sync worker，超過的請求要排隊。每個請求最多再開 10 個執行緒各自連 DB，PgBouncer `DEFAULT_POOL_SIZE=10` 也可能讓連線排隊，尚未單獨量測。
- **沒量到的**：真實 Google 的延遲分布（尤其長尾）、LINE 平台本身、正式環境的機器規格。gunicorn `--timeout 30` 與 LINE webhook 的逾時是同步刷新最壞情況的上限，要靠 `DETAIL_LATENCY_MS` 等參數另外模擬長尾。
