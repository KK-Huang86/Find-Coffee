## Why

開發者本機若已安裝並啟動其他 PostgreSQL（例如 EDB installer 的 PostgreSQL 18），該服務會佔用 `localhost:5432`。`.env` 原本設定 `DB_HOST=localhost`、`DB_PORT=5432`，導致在本機直接執行 `manage.py`（runserver、migrate、pytest 以外的指令）時連到錯誤的 PostgreSQL，出現 `FATAL: password authentication failed for user "kk"`。專案的 Docker DB 實際對 host 開放的是 `5433`（`"5433:5432"`）。

## What Changes

- 本機 `.env` 的 `DB_PORT` 改為 `5433`，指向 Docker DB 對 host 映射的 port
- `docker-compose.yml` 的共用模板 `x-app` 的 `environment` 明確設定 `DB_PORT=5432`，覆蓋 `env_file` 帶入的 `.env` 值，讓 web 與 celery 仍連 `pgbouncer:5432`
- `.env.example` 補上 `DB_PORT` 的說明註解，提示本機開發應使用 `5433`

## Capabilities

### New Capabilities

- `local-dev-db-connection`：定義本機直接執行 Django 與 Docker Compose 容器內執行 Django 時，各自連線 DB 的 host/port，兩者互不干擾。

### Modified Capabilities

（無）

## Impact

- **`docker-compose.yml`**：`x-app.environment` 新增 `DB_PORT=5432`
- **`.env`**（不進版控）：`DB_PORT=5433`
- **`.env.example`**：`DB_PORT` 新增說明註解
- **`core/tests/test_docker_compose.py`**：新增 compose 設定的 unit test
- 生產環境不受影響（生產環境的 DB 連線設定不使用本機 `.env`）
