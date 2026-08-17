## Purpose

定義 `Cafe` model 轉換為外部使用（LINE Flex Message、內部 API 回應等）的 dict 格式時，對 nullable 欄位的處理保證，避免序列化過程因欄位缺值而中斷。

## Requirements

### Requirement: 咖啡店序列化不因座標缺值而失敗
當咖啡店的緯度（`lat`）或經度（`lng`）尚未設定時，系統轉換該咖啡店為 dict 格式時 SHALL NOT 拋出例外，SHALL 以 `None` 表示缺值狀態；當座標有值時，系統 SHALL 回傳浮點數格式。系統 SHALL NOT 以 `0.0` 作為座標缺值的替代值。

#### Scenario: 座標皆已設定
- **WHEN** 咖啡店的 `lat` 與 `lng` 皆已設定實際數值
- **THEN** 轉換結果的 `lat`、`lng` 為對應的浮點數

#### Scenario: 座標皆未設定
- **WHEN** 咖啡店的 `lat` 與 `lng` 皆為缺值狀態
- **THEN** 轉換不拋出例外，結果的 `lat`、`lng` 皆為 `None`

#### Scenario: 座標部分設定
- **WHEN** 咖啡店僅 `lat` 有值、`lng` 為缺值狀態（或相反）
- **THEN** 轉換不拋出例外，有值欄位回傳浮點數，缺值欄位回傳 `None`
