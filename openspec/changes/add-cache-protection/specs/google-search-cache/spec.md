## ADDED Requirements

### Requirement: Google 搜尋結果共用快取
Text Search、Geocoding、Nearby Search 的結果 SHALL 以正規化後的查詢條件為 key 快取；快取命中時 MUST NOT 呼叫 Google。

#### Scenario: 相同查詢第二次命中快取
- **WHEN** 兩位使用者先後以相同店名搜尋
- **THEN** 只有第一次呼叫 Google Text Search，第二次直接回傳快取結果

#### Scenario: 寫法不同但語意相同的查詢
- **WHEN** 查詢只差在全形半形、頭尾空白、連續空白或英文大小寫
- **THEN** 命中同一個快取 key

#### Scenario: 經緯度相近
- **WHEN** 兩次定位搜尋的經緯度四捨五入到小數第 4 位後相同
- **THEN** 命中同一個 Nearby Search 快取 key

#### Scenario: 超出服務範圍
- **WHEN** 地址解析後的座標超出服務範圍
- **THEN** 仍拋出 `OutOfServiceAreaError`，不呼叫 Nearby Search

### Requirement: 防止快取穿透
確定沒有結果的查詢 SHALL 以較短的 TTL 快取空結果；暫時性錯誤 MUST NOT 被快取。

#### Scenario: Google 回 ZERO_RESULTS
- **WHEN** 查詢的結果為 `ZERO_RESULTS`
- **THEN** 快取空結果 10 分鐘（含隨機偏移），期間相同查詢不呼叫 Google

#### Scenario: 暫時性錯誤
- **WHEN** 查詢逾時、連線失敗，或 Google 回 `REQUEST_DENIED`、`OVER_QUERY_LIMIT`、`UNKNOWN_ERROR`
- **THEN** 回傳空結果但不寫入快取，下次相同查詢會重新呼叫 Google

### Requirement: 防止快取擊穿
快取未命中時 SHALL 以分散式鎖保護，同一個 key 同時只有一個請求呼叫 Google。

#### Scenario: 多個請求同時查詢同一個未快取的 key
- **WHEN** 一個請求持有該 key 的鎖並正在查詢，另一個請求也查詢相同的 key
- **THEN** 第二個請求不呼叫 Google，等待並回傳第一個請求寫入的快取

#### Scenario: 等待逾時
- **WHEN** 第二個請求等待約 2 秒後快取仍未出現
- **THEN** 第二個請求自行查詢並回傳結果，並記錄 warning

#### Scenario: 取得鎖後快取已存在
- **WHEN** 請求取得鎖時，前一個持有者剛寫入快取
- **THEN** 直接回傳快取，不呼叫 Google

### Requirement: 防止快取雪崩
寫入快取時 TTL SHALL 乘上 0.9～1.1 的隨機係數。

#### Scenario: 同時寫入多個 key
- **WHEN** 多個搜尋結果在同一時間寫入快取
- **THEN** 各 key 的 TTL 介於基準 TTL 的 90% 到 110% 之間，不會全部在同一秒過期
