## Context

- Redis 同時作為 Django cache（`KEY_PREFIX='linebot'`）與鎖使用；測試環境使用 LocMemCache，unit test 不得連真的 Redis
- gunicorn 為 sync worker，等待鎖會佔住 worker，所以等待時間必須有上限
- 現有 `LockService.acquire` 只有 `cache.add`（SETNX + TTL），沒有 token 也沒有釋放，只適合做節流，不適合做互斥
- Google 回應狀態：`OK`、`ZERO_RESULTS` 是確定的結果；`REQUEST_DENIED`、`OVER_QUERY_LIMIT`、`UNKNOWN_ERROR`、逾時與連線錯誤是暫時性或設定問題

## Goals / Non-Goals

**Goals:**
- 同一個搜尋條件在 TTL 內只打一次 Google
- 熱門 key 失效時，同一時間只有一個請求打 Google
- 查不到結果的查詢不會每次都打 Google
- 快取 key 與 DB 店家資料不會在同一時間大量失效

**Non-Goals:**
- 不快取 Places Detail 的內容（DB 的 `Cafe` 已經是它的持久快取）
- 不改變既有刷新節流 `LockService.acquire(..., 'refresh', ttl=600)` 的行為
- 不做快取預熱
- 不處理 Redis 本身故障的高可用（Redis 掛掉時對話狀態也會失效，屬於整體架構議題）

## Decisions

### Decision 1：分散式鎖使用 redis-py `Lock`

redis-py `Lock` 取得時寫入隨機 token，釋放時以 Lua 腳本比對 token 才刪除，避免鎖過期後被別人取得、又被原持有者誤刪。

- 一律非阻塞取得（`blocking=False`），等待邏輯由呼叫端決定，避免在鎖裡卡住 worker
- 鎖有逾時（預設 10 秒，大於 Google 單次 timeout 5 秒與 Geocoding + Nearby 兩段呼叫），持有者當機時自動釋放
- 釋放時若鎖已過期（`LockError`），記錄 warning，不拋出
- 取得鎖時 Redis 發生錯誤，記錄 error 後視同取得、不加鎖繼續執行：寧可多打一次 Google，也不要讓所有請求都等 2 秒
- 快取後端不是 Redis（測試的 LocMem）時，改用 `cache.add` + token 比對刪除；比對與刪除不是原子操作，僅供非 Redis 環境使用

**替代方案**：直接沿用 `LockService.acquire`。不採用，因為它無法釋放，完成查詢後其他請求仍要等 TTL 到期。

### Decision 2：只快取確定的結果

暫時性錯誤若被快取成空結果，Google 恢復後使用者仍會在 TTL 內一直拿到空結果，等於把一次故障放大。因此內部查詢函式回傳 `(value, cacheable)`，只有 `OK`、`ZERO_RESULTS` 才 `cacheable=True`。結果全部在服務範圍外而被過濾成空清單時，同樣是確定的結果，可以快取。

### Decision 3：拿不到鎖時短暫等待，逾時自行查詢

每 100ms 檢查一次快取，最多 20 次（約 2 秒）。持有者正常情況下 0.3～1 秒內完成。逾時代表持有者卡住或失敗，此時自行查詢，可用性優先；極端情況下會多打一次 Google。

等待以次數而非 wall clock 控制，測試 patch `time.sleep` 後即可同步執行，不需要真的等待。

### Decision 4：快取 key 正規化

- 文字（店名、地址）：NFKC（全形轉半形）→ 去頭尾空白 → 連續空白合併 → casefold，再取 SHA-256 前 32 碼，避免 key 過長或含特殊字元
- 經緯度：四捨五入到小數第 4 位（約 11 公尺），Nearby Search 半徑為 100 公尺，誤差可接受
- key 帶版本（`google:v1:...`），之後快取格式改變時改版本號即可讓舊 key 失效

### Decision 5：TTL 與隨機偏移

| 資料 | TTL | 空結果 TTL |
|---|---|---|
| Text Search | 24 小時 | 10 分鐘 |
| Geocoding | 7 天 | 10 分鐘 |
| Nearby Search | 24 小時 | 10 分鐘 |
| 無效 `place_id` | 1 小時 | — |

所有 TTL 乘上 0.9～1.1 的隨機係數。

### Decision 6：新店建立以 `place_id` 加鎖，等待 DB 而非快取

新店建立的結果存在 DB，不在 Redis，所以拿不到鎖的請求是輪詢 DB（`Cafe.objects.filter(place_id=...).first()`）。取得鎖後先再查一次 DB，避免前一個持有者剛建立完、自己又打一次 Google。建立時以 `transaction.atomic()` 包住 `create`，撞到 unique 限制（`IntegrityError`）時改讀既有資料。

### Decision 7：無效 `place_id` 檢查放在扣額度之前

`NOT_FOUND`、`INVALID_REQUEST` 代表這個 `place_id` 不存在或格式錯誤，重試不會成功。記錄後，`get_or_create_cafe_info` 在扣使用者額度之前先檢查，命中就直接回傳找不到，不扣額度。

### Decision 8：DB 刷新門檻依 `place_id` 決定，範圍 25～30 天

門檻 = 30 天 − `crc32(place_id) % 120` 小時。

- 依 `place_id` 決定（deterministic）而非每次隨機：同一間店的門檻固定，不會這次判斷過期、下次又判斷未過期
- 只提前、不延後：保證任何店家資料都不會超過 30 天未刷新，維持原本「最多 30 天」的承諾
- 同一批匯入的店會分散在 5 天內陸續過期

**商業邏輯變更**：原本「29 天 23 小時一定不過期」的邊界測試不再成立，改為驗證「門檻介於 25～30 天」「剛好低於自己的門檻時不過期」「達到門檻時過期」。

## Risks / Trade-offs

- 搜尋結果最多晚 24 小時反映 Google 的變化（例如新開的店），可接受
- Google Maps Platform 條款對快取內容有限制；這次只存 `place_id`、店名與評分，且 TTL 不超過 7 天，經緯度依條款可保存 30 天。正式上線前仍應依最新條款確認
- 拿不到鎖時最多讓 worker 多等 2 秒
- 非 Redis 後端的鎖不是原子釋放，只用於測試與沒有 Redis 的本機環境
