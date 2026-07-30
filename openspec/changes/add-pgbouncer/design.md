## Context

目前 Django 直接連接 PostgreSQL。K8s 水平擴展時，每個 Pod 的每個 Gunicorn worker 都會開啟獨立的 DB 連線，連線數 = Pod 數 × Workers 數，高併發時容易超過 PostgreSQL 的 `max_connections` 上限（預設 100）。

PgBouncer 是輕量的 PostgreSQL 連線池代理，放在 Django 與 PostgreSQL 之間，收斂多個應用層連線為少量的真實 DB 連線。

## Goals / Non-Goals

**Goals:**
- 降低 PostgreSQL 真實連線數，支援 K8s 水平擴展
- 本地開發與 K8s 生產環境都有 PgBouncer
- 設定可透過環境變數注入，不寫死認證資訊

**Non-Goals:**
- 不處理 PostgreSQL 本身的 HA（replica、failover）
- 不處理 Redis 連線池（Redis 本身已有 connection pooling）
- 不導入 AWS RDS Proxy（費用較高，PgBouncer 自管即可）

## Decisions

### Decision 1：使用 transaction pooling mode（而非 session mode）

transaction mode：每個 transaction 結束後連線歸還池中，連線複用率最高。
session mode：一個 client 連線對應一條 DB 連線，複用率低，效果接近不用 PgBouncer。

**選擇 transaction mode**，因為這是 PgBouncer 主要的使用情境，也是壓縮連線數效果最顯著的模式。

**限制**：transaction mode 下，以下 PostgreSQL 功能無法使用：
- `SET` 語句的 session-level 設定
- Advisory locks（`pg_advisory_lock`）
- `LISTEN/NOTIFY`
- Prepared statements（需設定 `server_reset_query`）

Django ORM 不使用上述功能，影響可忽略。

### Decision 2：Django CONN_MAX_AGE 設為 0

Django 的 `CONN_MAX_AGE` 讓 Django 持有長連線（persistent connection）。在 transaction mode 下，Django 持有的長連線會佔用 PgBouncer 的連線槽，與連線池目標衝突。

**設為 0**，讓每個 request 結束後 Django 立即釋放連線，由 PgBouncer 管理真實連線的複用。

### Decision 3：K8s 部署為獨立 Deployment，而非 sidecar

**獨立 Deployment** 的優點：
- 多個 web Pod 共用同一個 PgBouncer，連線池效果最大化
- 可獨立 scale 與監控
- 設定更新不需要重啟 web Pod

**Sidecar（每個 web Pod 一個 PgBouncer）** 的缺點：
- 每個 Pod 各自維護獨立連線池，池子被分散，效果打折
- Pod 數量 × PgBouncer 連線數仍線性增長

**選擇獨立 Deployment**。

### Decision 4：使用 bitnami/pgbouncer image

bitnami/pgbouncer 支援透過環境變數設定，不需要自己撰寫 entrypoint script 生成設定檔，維護成本低。

## Risks / Trade-offs

- **Single point of failure**：PgBouncer 成為 Django 與 DB 之間的必經點。緩解：K8s Deployment 設 replicas: 2，並設定 readinessProbe。
- **Transaction mode 限制**：如未來需要 session-level 功能，需切換為 session mode 或繞過 PgBouncer。目前 Django ORM 不受影響。
- **增加一跳（hop）**：每個 DB 查詢多一層 proxy，latency 微增（< 1ms）。在連線數壓力下，整體吞吐量仍是正向的。

## Migration Plan

1. 本地開發：Docker Compose 加入 pgbouncer service，驗證連線正常
2. 調整 Django settings `CONN_MAX_AGE=0`，確認 test suite 全過
3. 更新 K8s infra repo，新增 pgbouncer Deployment 與 Service
4. 更新 K8s ConfigMap，`DB_HOST` 改指向 pgbouncer Service
5. 部署至 K8s，驗證 readinessProbe 正常

**Rollback**：將 `DB_HOST` 改回直連 PostgreSQL，刪除 PgBouncer Deployment 即可。

## Open Questions

- PgBouncer 的 `max_db_connections` 初始值設多少？建議從 20 開始，觀察 PostgreSQL 實際連線數後調整。
