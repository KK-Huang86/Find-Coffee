## ADDED Requirements

### Requirement: 外部 API 位址可由設定切換
系統 SHALL 允許以設定切換 Google Maps 與 LINE Messaging API 的位址；未設定時 MUST 使用正式網址。

#### Scenario: 未設定位址
- **WHEN** 未設定外部 API 位址
- **THEN** 系統呼叫 Google Maps 與 LINE Messaging API 的正式網址

#### Scenario: 設定 Google 位址
- **WHEN** 設定了 Google Maps 位址
- **THEN** 店家資料查詢、照片解析、照片下載、地址轉換皆呼叫該位址

#### Scenario: 設定 LINE 位址
- **WHEN** 設定了 LINE Messaging API 位址
- **THEN** 回覆訊息與載入動畫皆呼叫該位址

### Requirement: 壓測不得呼叫真實外部服務
壓測環境 SHALL 將所有外部服務指向 mock，且使用假的金鑰；執行壓測前 MUST 驗證設定，不符合即中止。

#### Scenario: 設定正確
- **WHEN** 壓測環境的外部 API 位址皆指向 mock 且金鑰為假值
- **THEN** 開始執行壓測

#### Scenario: 設定錯誤
- **WHEN** 任一外部 API 位址未指向 mock，或金鑰不是假值
- **THEN** 中止壓測，不送出任何請求

#### Scenario: 壓測資料只寫入壓測資料庫
- **WHEN** 執行壓測資料準備，而目前連線的資料庫不是壓測資料庫
- **THEN** 拒絕執行
