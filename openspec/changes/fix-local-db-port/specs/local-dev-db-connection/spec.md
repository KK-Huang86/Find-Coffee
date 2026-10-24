## ADDED Requirements

### Requirement: 容器內 Django 透過 PgBouncer 內部 port 連線
Docker Compose 的 web 與 celery container SHALL 以 `pgbouncer:5432` 連線 DB，且此設定 MUST 寫在 compose 的 `environment`，不得依賴 `.env` 的 `DB_HOST`/`DB_PORT`。

#### Scenario: .env 設定本機 port 時容器仍連 PgBouncer
- **WHEN** `.env` 設定 `DB_PORT=5433` 並啟動 Docker Compose
- **THEN** web 與 celery container 的環境變數為 `DB_HOST=pgbouncer`、`DB_PORT=5432`

#### Scenario: 共用模板被 web 與 celery 繼承
- **WHEN** web 與 celery service 使用 `x-app` 模板
- **THEN** 兩者皆繼承 `DB_HOST=pgbouncer` 與 `DB_PORT=5432`

### Requirement: 本機 Django 透過 Docker 映射 port 連線
本機直接執行 Django 時 SHALL 以 `localhost:5433` 連線 Docker DB，避免與 host 上佔用 `5432` 的其他 PostgreSQL 衝突。

#### Scenario: host 上有其他 PostgreSQL 佔用 5432
- **WHEN** host 上有其他 PostgreSQL 監聽 `localhost:5432`，且 `.env` 設定 `DB_PORT=5433`
- **THEN** 本機執行 `manage.py check` 與 `showmigrations` 連到 Docker DB 並成功

#### Scenario: Docker DB 對 host 映射 5433
- **WHEN** 讀取 `docker-compose.yml` 的 db service
- **THEN** port 映射為 `5433:5432`
