# 多筆搜尋回應時間壓測（K6 + mock server）

量測「多筆搜尋結果（carousel，10 間店）」從 LINE webhook 進來到回覆完成的時間，並驗證 Google 搜尋共用快取（穿透、擊穿、雪崩防護）。webhook 為同步處理，`/callback` 的回應時間即為完整處理時間。

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
loadtest/run.sh                         # 六個情境全跑
loadtest/avalanche.sh                   # 快取雪崩防護驗證（刷新門檻分散 + TTL 隨機偏移）
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
| `address_cold` | 地址搜尋，每次都是不同地址 | 每次都未命中：Geocoding、Nearby Search 各 1 次（等同沒有快取） |
| `address_hot` | 地址搜尋，所有人搜同一個地址 | 整輪只有第一次打 Google：Geocoding、Nearby Search 各 1 次；同時進來的請求等鎖（擊穿防護） |
| `address_miss` | 地址搜尋，所有人搜同一個查不到的地址 | Geocoding 回 `ZERO_RESULTS` 被快取，整輪只打 1 次；不呼叫 Nearby Search（穿透防護） |

地址搜尋情境的 10 間店已預先寫入 DB 且為快取狀態，量到的差異只來自 Geocoding（mock 200ms）與 Nearby Search（mock 300ms）。

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

## Google 搜尋共用快取（2026-10-25，`feature/cache-protection`）

mock 延遲：Geocoding 200ms、Nearby Search 300ms、LINE 50ms。

**VUS=5，30 次**

| 情境 | Geocoding 呼叫 | Nearby 呼叫 | min | med | p95 | max |
|---|---|---|---|---|---|---|
| address_cold（沒有命中） | 30 | 30 | 643ms | 856ms | 1.24s | 1.30s |
| address_hot（同一個地址） | **1** | **1** | 186ms | 308ms | 737ms | 765ms |
| address_miss（查不到的地址） | **1** | 0 | 149ms | 249ms | 361ms | 367ms |

**VUS=10，50 次（address_hot，同時請求數超過 gunicorn worker 數）**

| Geocoding 呼叫 | Nearby 呼叫 | 等鎖逾時 | min | med | p95 | max |
|---|---|---|---|---|---|---|
| **1** | **1** | 0 次 | 204ms | 558ms | 1.84s | 1.89s |

- **擊穿防護有效**：5 人、10 人同時搜尋同一個沒快取過的地址，Google 都只被打 1 次，其他請求等持有者寫入快取後直接拿結果，沒有任何請求等鎖逾時
- **命中時省下約 550ms**：address_hot 的中位數 308ms 和 `cached`（全部快取的店名搜尋）差不多；address_cold 的 856ms ≈ 308ms + Geocoding 200ms + Nearby 300ms + 開銷
- **address_hot 的 p95 偏高**：第一批同時進來的請求要等持有者打完 Google（約 0.5 秒）才拿得到結果
- **VUS=10 的 p95 1.84s** 主要是 3 個 gunicorn worker 排隊，Google 呼叫次數沒有增加
- **穿透防護有效**：查不到的地址整輪只打 1 次 Geocoding

## 快取雪崩防護（2026-10-25，`loadtest/avalanche.sh`）

雪崩要等大量 key 同時過期才看得到，壓測不可能真的等 24 小時或 30 天，所以分兩部分驗證：

### 1. 店家刷新門檻分散（`refresh_spread`）

seed 300 間「同一時間匯入」的店（30 組 × 10 間，`last_refreshed` 全部相同、已有 S3 照片），把匯入時間設成 N 天前，跑一輪真實的搜尋流量（VUS=5，30 次，每次 10 間店），統計被判定過期而同步刷新的 Places Detail 次數。每個天數都重新 seed，彼此獨立。

| 匯入後經過 | 實測刷新次數（累計） | 當天新增 | 固定 30 天門檻時 |
|---|---|---|---|
| 24 天 | 0 | 0 | 0 |
| 25 天 | 1 | 1 | 0 |
| 26 天 | 39 | 38 | 0 |
| 27 天 | 105 | 66 | 0 |
| 28 天 | 168 | 63 | 0 |
| 29 天 | 228 | 60 | 0 |
| 29.9 天 | 290 | 62（29～29.9 天） | 0 |
| 30 天 | 300 | 10（29.9～30 天） | **300** |

- 實測次數與用 `refresh_threshold` 直接計算這 300 個 `place_id` 的理論值**完全一致**
- 固定門檻時，300 間店會在第 30 天同一刻一起過期；分散後，單日最多 72 次（第 29 到 30 天，228 → 300），**尖峰降到原本的 24%**
- 30 天時一定全部刷新：門檻只提前、不延後，沒有店家超過 30 天沒更新

### 2. 快取 TTL 隨機偏移（`address_cold` + `analyze_ttl.py`）

用 100 個不同地址做地址搜尋（VUS=5），在約 29.5 秒內寫入 100 個 Geocoding 和 100 個 Nearby Search 快取 key，接著讀出 Redis 裡每個 key 的剩餘 TTL。

| | Geocoding（基準 7 天） | Nearby Search（基準 24 小時） |
|---|---|---|
| TTL 範圍 | 基準的 90.0%～109.9% | 基準的 90.5%～109.6% |
| 過期時間分散在 | 約 33.4 小時 | 約 4.6 小時 |
| 任一 60 秒內最多同時過期 | **2 個** | **4 個** |
| 沒有偏移時 | 100 個 key 在約 29.5 秒內全部過期 | 同左 |

- 100 個 key 大致均勻分布在 ±10% 的範圍內，沒有集中在某個時間點
- 沒有偏移時，同一批寫入的 key 會在寫入期間（約 30 秒）內全部過期，下一波請求會一起打到 Google

## 解讀

- **平行化有效**：`stale` 的中位數 735ms ≈ 基準 173ms + Detail 300ms + Photo 150ms + 額外開銷。若 10 間店依序處理，光外部呼叫就要 10 × (300 + 150) = 4.5 秒。
- **同步刷新的成本**：有過期店家時，比全部快取多約 0.5～0.7 秒（取決於 Google 的實際延遲），換來回覆的是最新資料與真實照片。
- **`cached` 的 p95 / max 偏高**是每個 gunicorn worker 第一次處理請求時載入 jieba 斷詞字典（log 顯示約 0.6～0.9 秒），不是穩態延遲。
- **VUS=5 變慢**主要來自 gunicorn 只有 3 個 sync worker，超過的請求要排隊。每個請求最多再開 10 個執行緒各自連 DB，PgBouncer `DEFAULT_POOL_SIZE=10` 也可能讓連線排隊，尚未單獨量測。
- **沒量到的**：真實 Google 的延遲分布（尤其長尾）、LINE 平台本身、正式環境的機器規格。gunicorn `--timeout 30` 與 LINE webhook 的逾時是同步刷新最壞情況的上限，要靠 `DETAIL_LATENCY_MS` 等參數另外模擬長尾。
