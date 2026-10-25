## Context

同一個 DB 有兩種連線視角：

| 執行位置 | DB_HOST | DB_PORT | 實際連到 |
|---|---|---|---|
| 本機（runserver、manage.py） | `localhost` | `5433` | Docker 映射的 port，連到 `find-coffee-db` |
| 容器內（web、celery） | `pgbouncer` | `5432` | Docker 內部網路的 PgBouncer，再轉給 `db:5432` |

容器有獨立的網路命名空間，容器內的 `5432` 與 host 的 `5432` 不衝突。問題只發生在 host 端：`localhost:5432` 可能被開發者本機的其他 PostgreSQL 佔用。

## Goals / Non-Goals

**Goals:**
- 本機直接執行 Django 時穩定連到 Docker DB，不受 host 上其他 PostgreSQL 影響
- 容器內連線行為維持不變（仍經 PgBouncer transaction pooling）

**Non-Goals:**
- 不改變 Docker DB 對 host 映射的 port（維持 `5433`）
- 不調整 PgBouncer 設定或生產環境連線設定
- 不處理本機直連時繞過 PgBouncer 的差異（本機開發可接受直連 DB）

## Decisions

### Decision 1：容器的 DB_PORT 在 compose 寫死，而非依賴 `.env`

`x-app` 同時使用 `env_file: .env` 與 `environment`。Docker Compose 中 `environment` 優先於 `env_file`，因此在 `environment` 寫死 `DB_PORT=5432`，`.env` 便可專供本機使用而不影響容器。`DB_HOST=pgbouncer` 已採用相同模式，此決策與既有做法一致。

**替代方案**：把 Docker DB 映射改成 `5432:5432`。不採用，因為會與 host 上已存在的 PostgreSQL 衝突，正是此次問題的根源。

### Decision 2：以 unit test 鎖定 compose 設定

新增 test 讀取 `docker-compose.yml`，驗證 `x-app` 的 `DB_HOST`/`DB_PORT` 與 db service 的 port 映射。避免日後有人移除 `DB_PORT=5432` 後，容器因讀到 `.env` 的 `5433` 而連不上 PgBouncer。

## Risks / Trade-offs

- 其他開發者沿用舊 `.env`（`DB_PORT=5432`）時，若本機沒有其他 PostgreSQL，連線會失敗（`localhost:5432` 無人監聽）。以 `.env.example` 註解提醒。
- Test 依賴 PyYAML（目前為間接依賴）；若日後被移除需改列為 dev 依賴。
