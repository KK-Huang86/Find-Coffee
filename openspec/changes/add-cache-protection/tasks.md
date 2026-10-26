## 1. 分散式鎖

- [x] 1.1 測試 `utils/tests/test_distributed_lock.py`：取得、已被持有、例外時釋放、逾時後不誤刪、Redis 錯誤視同取得、Redis 後端使用 redis-py Lock 且 `blocking=False`
- [x] 1.2 確認紅燈
- [x] 1.3 實作 `utils/distributed_lock.py`

## 2. Cache guard

- [x] 2.1 測試 `utils/tests/test_cache_guard.py`：命中、未命中寫入、空結果短 TTL、不可快取不寫入、TTL 偏移範圍、取得鎖後 double check、等待命中、等待逾時自行查詢、fetch 例外不寫入且往外拋、key 正規化
- [x] 2.2 確認紅燈
- [x] 2.3 實作 `utils/cache_guard.py`

## 3. Google 搜尋快取

- [x] 3.1 測試：Text Search、Geocoding、Nearby Search 命中不呼叫 Google；ZERO_RESULTS 快取；暫時性錯誤不快取；經緯度四捨五入；超出服務範圍仍拋例外
- [x] 3.2 測試：Places Detail `NOT_FOUND`、`INVALID_REQUEST` 記錄無效 `place_id`；暫時性錯誤不記錄；記錄期間不呼叫 Google
- [x] 3.3 確認紅燈
- [x] 3.4 實作 `integrations/google/api.py`

## 4. 新店建立防護

- [x] 4.1 測試 `get_or_create_cafe_info`：無效 `place_id` 不扣額度、拿不到鎖時等待 DB、等待逾時自行建立、取得鎖後 DB 已有資料、`IntegrityError` 改讀既有資料
- [x] 4.2 確認紅燈
- [x] 4.3 實作 `line_bot/handlers/helpers.py`

## 5. 刷新門檻分散

- [x] 5.1 測試 `refresh_threshold` 範圍、固定、分散，以及 `is_cafe_stale` 邊界（取代原本 29 天 23 小時的測試，商業邏輯變更）
- [x] 5.2 確認紅燈
- [x] 5.3 實作 `cafe/services/cafe_refresh.py`

## 6. 驗證與文件

- [x] 6.1 完整 test suite、`ruff check` 通過
- [x] 6.2 `openspec validate add-cache-protection --strict` 通過
- [x] 6.3 更新桌面 `find-coffee-project-highlights.md`
