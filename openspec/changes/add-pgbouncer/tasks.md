## 1. Django Settings 調整

- [x] 1.1 將 `core/settings.py` 的 `CONN_MAX_AGE` 設為 0，並從環境變數讀取 `DB_HOST`（讓 pgbouncer 可替換 postgres）
- [x] 1.2 確認 `DB_PORT` 從環境變數讀取，設定 `default='5432'`

## 2. 本地開發：Docker Compose 加入 PgBouncer

- [x] 2.1 在 `docker-compose.yml` 新增 pgbouncer service（使用 edoburu/pgbouncer:v1.25.2-p0 image）
- [x] 2.2 設定 pgbouncer 環境變數：`DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME`、`POOL_MODE=transaction`、`MAX_DB_CONNECTIONS=20`、`AUTH_TYPE=md5`
- [x] 2.3 將 web 與 celery service 的 `DB_HOST` 改為 `pgbouncer`，並加入 `depends_on: pgbouncer`
- [x] 2.4 本地啟動 Docker Compose，驗證 Django 可正常查詢 DB（透過 pgbouncer）

## 3. K8s Infra Repo：新增 PgBouncer 資源

- [x] 3.1 在 infra repo 新增 `pgbouncer/deployment.yml`（replicas: 2，使用 edoburu/pgbouncer，設定 readinessProbe）
- [x] 3.2 在 infra repo 新增 `pgbouncer/service.yml`（ClusterIP，port 5432）
- [x] 3.3 更新 K8s ConfigMap，將 `DB_HOST` 改為 pgbouncer Service 名稱（例如 `pgbouncer`）
- [x] 3.4 確認 PgBouncer 所需的 DB 認證資訊已放入 K8s Secret

## 4. 驗證

- [x] 4.1 執行完整 test suite，確認 273 個測試全過
- [ ] 4.2 部署至 K8s 後，確認 pgbouncer Pod readinessProbe 通過
- [ ] 4.3 確認 web Pod 可正常透過 pgbouncer 查詢 DB（觀察 ArgoCD sync 狀態）
