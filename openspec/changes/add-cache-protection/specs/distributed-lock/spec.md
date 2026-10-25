## ADDED Requirements

### Requirement: 分散式鎖可安全釋放
系統 SHALL 提供非阻塞的分散式鎖；鎖 MUST 有逾時，且釋放時 MUST 只刪除自己持有的鎖。

#### Scenario: 取得未被持有的鎖
- **WHEN** 請求取得一把未被持有的鎖
- **THEN** 取得成功，離開時釋放鎖

#### Scenario: 鎖已被他人持有
- **WHEN** 請求取得一把已被持有的鎖
- **THEN** 立即回報未取得，不等待

#### Scenario: 鎖逾時後被他人取得
- **WHEN** 原持有者的鎖已逾時，且已被另一個請求取得，原持有者此時才釋放
- **THEN** 原持有者不會刪除另一個請求的鎖，並記錄 warning

#### Scenario: 執行期間拋出例外
- **WHEN** 持有鎖期間呼叫端拋出例外
- **THEN** 鎖仍被釋放，例外照常往外拋

#### Scenario: Redis 發生錯誤
- **WHEN** 取得鎖時 Redis 回報錯誤
- **THEN** 記錄 error，視同取得並繼續執行
