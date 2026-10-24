## 1. 測試

- [x] 1.1 新增 `core/tests/test_docker_compose.py`：驗證 web、celery 繼承 `DB_HOST=pgbouncer`、`DB_PORT=5432`，db 映射 `5433:5432`
- [x] 1.2 在未修改 compose 的狀態下執行測試，確認 `DB_PORT` 相關測試為紅燈

## 2. 實作

- [x] 2.1 `docker-compose.yml` 的 `x-app.environment` 新增 `DB_PORT=5432`
- [x] 2.2 本機 `.env` 的 `DB_PORT` 改為 `5433`（不進版控）
- [x] 2.3 `.env.example` 為 `DB_PORT` 補上本機使用 `5433` 的說明註解

## 3. 驗證

- [x] 3.1 執行新測試全綠，並執行完整 test suite
- [x] 3.2 本機執行 `uv run python manage.py check` 與 `showmigrations` 成功
- [x] 3.3 `docker compose up -d --force-recreate web celery` 後，確認容器內 `DB_PORT=5432` 且可查詢 DB
