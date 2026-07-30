## Why

Django 每個 request 都會向 PostgreSQL 開一條新連線，K8s 水平擴展後多個 Pod 同時運行，DB 連線數會線性增長（Pod 數 × Gunicorn workers），在高併發情況下容易超過 PostgreSQL 的連線上限，導致新請求被拒絕。加入 PgBouncer 作為連線池代理，可將應用層對 DB 的大量連線收斂為少量的長連線，解決此問題。

## What Changes

- 在 Docker Compose 新增 PgBouncer service（本地開發）
- Django `DATABASES` 設定改為連接 PgBouncer，而非直連 PostgreSQL
- 新增 PgBouncer 設定檔（`pgbouncer.ini`、`userlist.txt`）
- K8s infra repo 新增 PgBouncer Deployment 與 Service（獨立 Pod 部署）
- 移除或調整 `CONN_MAX_AGE` 設定（與 PgBouncer transaction mode 衝突）

## Capabilities

### New Capabilities

- `pgbouncer-connection-pool`：PgBouncer 作為 Django 與 PostgreSQL 之間的連線池代理，支援 transaction pooling mode，限制真實 DB 連線數，允許應用層連線數遠大於 DB 連線數。

### Modified Capabilities

（無既有 spec 的行為變更）

## Impact

- **`docker-compose.yml`**：新增 pgbouncer service，web 與 celery 改連 pgbouncer
- **`core/settings.py`**：`DB_HOST` 改指向 pgbouncer，port 改為 5432（pgbouncer 預設）
- **`pgbouncer/pgbouncer.ini`**：新增設定檔
- **`pgbouncer/userlist.txt`**：新增認證用帳密檔
- **infra repo**：新增 `pgbouncer/deployment.yml`、`pgbouncer/service.yml`
- **注意**：PgBouncer transaction mode 下，Django 的 `CONN_MAX_AGE` 需設為 0，否則與 pooling 衝突
