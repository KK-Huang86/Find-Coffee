## ADDED Requirements

### Requirement: /admin/ 路徑套用嚴格限流
系統 SHALL 對 `/admin/` 路徑套用每分鐘 5 個 request 的限制，超過限制回 429。

#### Scenario: 正常登入操作不受影響
- **WHEN** 使用者在 1 分鐘內對 `/admin/` 發送 5 個以內的 request
- **THEN** 所有 request 正常處理，不回 429

#### Scenario: 暴力破解被擋住
- **WHEN** 同一 IP 在短時間內對 `/admin/` 發送超過 5+3（rate+burst）個 request
- **THEN** 超過的 request 收到 429 Too Many Requests，不進入 Django

### Requirement: /callback/ 路徑不限流
系統 SHALL 對 `/callback/` 路徑不套用任何 rate limiting，確保 LINE 伺服器的 webhook 不被擋。

#### Scenario: LINE webhook 正常送達
- **WHEN** LINE 伺服器對 `/callback/` 發送 webhook request
- **THEN** request 正常進入 Django，不受任何 rate limit 影響

### Requirement: 其他路徑套用一般限流
系統 SHALL 對其他路徑套用每秒 10 個 request（burst 20）的限制，超過限制回 429。

#### Scenario: 正常瀏覽不受影響
- **WHEN** 使用者在正常頻率下發送 request
- **THEN** request 正常處理

#### Scenario: 異常高頻被擋住
- **WHEN** 同一 IP 在持續高頻發送超過 10r/s+burst 的 request
- **THEN** 超過的 request 收到 429

### Requirement: 超過限制回 429 而非 503
系統 SHALL 對所有被 rate limit 擋住的 request 回 429 Too Many Requests。

#### Scenario: 被擋住的 request 收到正確狀態碼
- **WHEN** request 超過 rate limit
- **THEN** 回應狀態碼為 429，不是 503
