## ADDED Requirements

### Requirement: Django 透過 PgBouncer 連接 PostgreSQL
Django 應用程式 SHALL 透過 PgBouncer 代理連接 PostgreSQL，不得直接連接 PostgreSQL。

#### Scenario: 本地開發正常連線
- **WHEN** 開發者啟動 Docker Compose
- **THEN** web 與 celery container 連線至 pgbouncer:5432，PgBouncer 代理至 db:5432

#### Scenario: K8s 生產環境正常連線
- **WHEN** web Pod 發送 DB 查詢
- **THEN** 查詢透過 PgBouncer Service 轉發至 PostgreSQL，不直接連接 PostgreSQL

### Requirement: PgBouncer 使用 transaction pooling mode
PgBouncer SHALL 使用 transaction pooling mode，每個 transaction 結束後連線即歸還池中。

#### Scenario: 高併發下連線數受控
- **WHEN** 多個 Django Pod 同時發送 DB 查詢
- **THEN** PgBouncer 對 PostgreSQL 維持不超過 `max_db_connections` 條真實連線

#### Scenario: Django CONN_MAX_AGE 設為 0
- **WHEN** Django settings 中 CONN_MAX_AGE 設為 0
- **THEN** Django 不持有長連線，連線池由 PgBouncer 完全管理

### Requirement: PgBouncer 設定可透過環境變數注入
PgBouncer 的 DB 認證資訊 SHALL 從環境變數讀取，不得寫死在設定檔中。

#### Scenario: 環境變數正確設定時啟動成功
- **WHEN** DB_USER、DB_PASSWORD、DB_NAME、DB_HOST 環境變數已設定
- **THEN** PgBouncer 正常啟動並可接受連線

#### Scenario: 缺少環境變數時啟動失敗
- **WHEN** 必要環境變數未設定
- **THEN** PgBouncer 啟動失敗並記錄明確錯誤訊息
