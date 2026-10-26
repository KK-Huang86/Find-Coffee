## ADDED Requirements

### Requirement: 無效 place_id 不重複查詢
Places Detail 回 `NOT_FOUND` 或 `INVALID_REQUEST` 時，系統 SHALL 記錄該 `place_id` 無效 1 小時（含隨機偏移）；期間 MUST NOT 呼叫 Google，也 MUST NOT 扣使用者額度。

#### Scenario: 第一次查詢無效 place_id
- **WHEN** 使用者點選的店家，Places Detail 回 `NOT_FOUND`
- **THEN** 回傳找不到，並記錄此 `place_id` 無效

#### Scenario: 再次查詢無效 place_id
- **WHEN** 1 小時內再次查詢同一個無效 `place_id`
- **THEN** 不呼叫 Google、不扣額度，直接回傳找不到

#### Scenario: 暫時性錯誤
- **WHEN** Places Detail 逾時或回 `REQUEST_DENIED`、`OVER_QUERY_LIMIT`、`UNKNOWN_ERROR`
- **THEN** 不記錄為無效 `place_id`

### Requirement: 新店建立只呼叫一次 Google
同一個 `place_id` 的新店建立 SHALL 以分散式鎖保護；取得鎖後 MUST 再查一次 DB。

#### Scenario: 多人同時點選同一間新店
- **WHEN** 一個請求持有該 `place_id` 的鎖並正在建立店家，另一個請求也點選同一間店
- **THEN** 第二個請求不呼叫 Google、不扣額度，等待並回傳 DB 中建立好的店家

#### Scenario: 等待逾時
- **WHEN** 第二個請求等待約 2 秒後 DB 仍沒有該店
- **THEN** 第二個請求自行建立，並記錄 warning

#### Scenario: 取得鎖後 DB 已有資料
- **WHEN** 請求取得鎖時，前一個持有者剛建立完成
- **THEN** 直接回傳 DB 資料，不呼叫 Google、不扣額度

#### Scenario: 建立時撞到 unique 限制
- **WHEN** 建立 `Cafe` 時因 `place_id` 已存在而失敗
- **THEN** 改讀既有資料回傳，不回傳錯誤
