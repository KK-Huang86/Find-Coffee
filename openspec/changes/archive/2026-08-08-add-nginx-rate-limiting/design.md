## Context

nginx 是所有流量的入口，在這層做 rate limiting 是最有效率的位置——異常請求在到達 Django 之前就被擋住，不消耗 Gunicorn worker 資源。

nginx 內建 `ngx_http_limit_req_module`，不需要安裝額外套件。

**部署拓撲：**
```
Internet → AWS Load Balancer → nginx Pod → Django Pod
```

nginx 不是直接面對 client，前面有 Load Balancer。這意味著 `$remote_addr` 會是 Load Balancer 的 IP，而不是真實 client IP，必須先處理 real IP 才能正確做 rate limiting。

## Goals / Non-Goals

**Goals:**
- 保護 `/admin/` 免於暴力破解
- 保護一般路徑免於異常高頻掃描
- LINE webhook（`/callback/`）不受任何限制
- 以真實 client IP 作為限流 key，而非 Load Balancer IP

**Non-Goals:**
- 不做 IP 白名單（維護成本高，且 LINE 的出口 IP 可能變動）
- 不做 DDoS 防禦（那是 WAF/CloudFlare 的層級）
- 不限制特定 User-Agent

## Decisions

### Decision 1：用 `real_ip_module` 取得真實 client IP

由於 nginx 在 Load Balancer 後方，必須設定：

```nginx
real_ip_header X-Forwarded-For;
real_ip_recursive on;
set_real_ip_from 0.0.0.0/0;  # 信任所有 proxy（內部部署，LB 已做邊界防護）
```

設定後，nginx 的 `$remote_addr`（以及 `$binary_remote_addr`）會自動更新為真實 client IP，rate limiting 才能正確以個別使用者 IP 計算。

`set_real_ip_from 0.0.0.0/0` 適用於 LB 已在邊界做防護的內部部署情境。若未來需要更精確控制，可改為 AWS LB 的實際 IP 段。

### Decision 2：用 `$binary_remote_addr` 作為 zone key

`$binary_remote_addr` 是 IP 的二進位格式，比字串格式的 `$remote_addr` 節省約 50% 記憶體，nginx 官方建議使用這個。real_ip_module 處理後，此值即為真實 client IP。

### Decision 3：三個路徑，兩個 zone，明訂 memory size

```nginx
limit_req_zone $binary_remote_addr zone=admin:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
```

- `10m`：共享記憶體 10MB，約可追蹤 16 萬個不同 IP，足夠使用
- `zone=admin`：套用於 `/admin/`
- `zone=general`：套用於 `/`（其他所有路徑）
- `/callback/`：不套用任何 zone

### Decision 4：`burst` 和 `nodelay` 的搭配

```nginx
limit_req zone=general burst=20 nodelay;
```

- `burst=20`：允許瞬間多接 20 個 request，不立刻拒絕
- `nodelay`：burst 內的 request 不排隊等待，立刻處理（不加 nodelay 的話會人為拖慢回應）

這樣設計讓使用者在網頁上快速操作不會被誤擋，但異常的持續高頻還是會觸發 429。

### Decision 5：`limit_req_status 429`

nginx 預設超過限制回 503，但 429（Too Many Requests）才是 HTTP 語義正確的狀態碼，讓 client 知道是流量問題而非伺服器錯誤。

### Decision 6：location 拆分後每個 block 保留完整 proxy 設定

現有 `location /` 包含 `proxy_pass`、headers、timeout。拆分為三個 location 後，每個 block 都必須保留相同的 proxy 設定，否則流量無法進入 Django。透過抽出共用設定段（或每個 block 明確複製）確保一致性。

### Decision 7：驗證順序

`nginx -t` 語法檢查成功後再 restart，避免錯誤設定中斷服務。

## Risks / Trade-offs

- **`set_real_ip_from 0.0.0.0/0` 信任所有來源**：在 LB 已做邊界防護的情況下可接受；若 nginx 直接對外，需改為明確 LB IP 段。
- **無法區分同一 NAT 後的多個使用者**：同一公司/家庭的多人共用 IP，rate limit 是針對 IP 共享的。對 LINE Bot 場景影響不大。

## Migration Plan

1. 修改 `nginx/nginx.conf`
2. 在 nginx container 內執行 `nginx -t` 確認語法無誤
3. 執行 `docker compose restart nginx`
4. 用 `curl` 驗證各路徑 rate limiting 行為符合預期
5. 部署後觀察 nginx log，確認 429 只在異常情況出現
