## ADDED Requirements

### Requirement: 店家刷新門檻分散在 25 到 30 天
店家資料的過期門檻 SHALL 依 `place_id` 決定，介於 25 天到 30 天之間；同一間店的門檻 MUST 固定，且任何店家 MUST NOT 超過 30 天未被視為過期。

#### Scenario: 門檻範圍
- **WHEN** 計算任一間店的過期門檻
- **THEN** 門檻大於等於 25 天、小於等於 30 天

#### Scenario: 同一間店門檻固定
- **WHEN** 對同一間店多次計算門檻
- **THEN** 每次結果相同

#### Scenario: 同一批店分散過期
- **WHEN** 計算 100 間不同 `place_id` 店家的門檻
- **THEN** 門檻分布在多個不同的值，不會全部相同

#### Scenario: 達到 30 天一定過期
- **WHEN** 店家距上次刷新已達 30 天
- **THEN** 視為過期

#### Scenario: 未達自己的門檻
- **WHEN** 店家距上次刷新的時間略低於自己的門檻
- **THEN** 不視為過期
