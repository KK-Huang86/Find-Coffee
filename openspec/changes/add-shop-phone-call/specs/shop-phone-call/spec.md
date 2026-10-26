## ADDED Requirements

### Requirement: 單筆詳細卡片提供一鍵撥號按鈕
單筆咖啡店詳細卡片（`is_multiple=False`）的 footer SHALL 在店家電話合法時顯示「打電話」按鈕，按鈕 action MUST 為 `uri` 類型，uri 為 `tel:` 加上正規化後的電話。多筆結果卡片 MUST NOT 顯示此按鈕。

#### Scenario: 店家有合法電話
- **WHEN** 店家電話為 `02 2345 6789` 並產生單筆詳細卡片
- **THEN** footer 包含 label 為「打電話」、uri 為 `tel:0223456789` 的按鈕

#### Scenario: 按鈕順序
- **WHEN** 店家有合法電話與官方網站並產生單筆詳細卡片
- **THEN** footer 按鈕依序為「看地圖」、「打電話」、「網站」

#### Scenario: 店家無電話
- **WHEN** 店家電話為空值、`None`、`無提供` 或 `未提供電話`
- **THEN** footer 不包含「打電話」按鈕

#### Scenario: 多筆結果卡片
- **WHEN** 產生多筆結果卡片（`is_multiple=True`）
- **THEN** footer 不包含「打電話」按鈕

### Requirement: 電話正規化為 tel URI
系統 SHALL 將電話字串正規化為僅含數字（可帶開頭 `+`）的 `tel:` URI；無法正規化為 3 到 15 位數字時 MUST 回傳 `None`。

#### Scenario: 移除分隔符號
- **WHEN** 電話為 `(02) 2345-6789`
- **THEN** 產生 `tel:0223456789`

#### Scenario: 保留國際碼
- **WHEN** 電話為 `+886 2 2345 6789`
- **THEN** 產生 `tel:+886223456789`

#### Scenario: 截斷分機
- **WHEN** 電話為 `02-2345-6789 #123` 或 `02-2345-6789 分機 123`
- **THEN** 產生 `tel:0223456789`

#### Scenario: 全形數字
- **WHEN** 電話為 `０２－２３４５－６７８９`
- **THEN** 產生 `tel:0223456789`

#### Scenario: 數字長度不合法
- **WHEN** 電話正規化後數字少於 3 位或多於 15 位
- **THEN** 回傳 `None`

#### Scenario: 非字串輸入
- **WHEN** 電話為 `None` 或非字串型別
- **THEN** 回傳 `None`
