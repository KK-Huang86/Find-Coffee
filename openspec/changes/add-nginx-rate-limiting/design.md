## Context

nginx 是所有流量的入口，在這層做 rate limiting 是最有效率的位置——異常請求在到達 Django 之前就被擋住，不消耗 Gunicorn worker 資源。

nginx 內建 `ngx_http_limit_req_module`，不需要安裝額外套件。

## Goals / Non-Goals

**Goals:**
- 保護 `/admin/` 免於暴力破解
- 保護一般路徑免於異常高頻掃描
- LINE webhook（`/callback/`）不受任何限制

**Non-Goals:**
- 不做 IP 白名單（維護成本高，且 LINE 的出口 IP 可能變動）
- 不做 DDoS 防禦（那是 WAF/CloudFlare 的層級）
- 不限制特定 User-Agent

## Decisions

### Decision 1：用 `$binary_remote_addr` 而非 `$remote_addr` 作為 key

`$binary_remote_addr` 是 IP 的二進位格式，比字串格式的 `$remote_addr` 節省約 50% 記憶體，nginx 官方建議使用這個。

### Decision 2：三個路徑，兩個 zone

```
zone=admin   → rate=5r/m   → 套用於 /admin/
zone=general → rate=10r/s  → 套用於 /（其他所有路徑）
/callback/   → 不套用任何 zone
```

只需要兩個 zone（不是三個），`/callback/` 不需要獨立的 zone，直接不加 `limit_req` 指令即可。

### Decision 3：`burst` 和 `nodelay` 的搭配

```nginx
limit_req zone=general burst=20 nodelay;
```

- `burst=20`：允許瞬間多接 20 個 request，不立刻拒絕
- `nodelay`：burst 內的 request 不排隊等待，立刻處理（不加 nodelay 的話會人為拖慢回應）

這樣設計讓使用者快速操作 LINE Bot（連續傳幾則訊息）不會被誤擋，但異常的持續高頻還是會觸發 429。

### Decision 4：`limit_req_status 429`

nginx 預設超過限制回 503，但 429（Too Many Requests）才是 HTTP 語義正確的狀態碼，讓 client 知道是流量問題而非伺服器錯誤。

## Risks / Trade-offs

- **誤擋正常使用者**：`burst=20` 已給足餘裕，一般使用不會觸發。若未來有特殊需求再調整。
- **無法區分同一 NAT 後的多個使用者**：同一公司/家庭的多人共用 IP，rate limit 是針對 IP 共享的。對 LINE Bot 場景影響不大（主要流量是 LINE 伺服器 IP）。

## Migration Plan

1. 修改 `nginx/nginx.conf`
2. 本地 `docker compose restart nginx` 驗證設定正確
3. 用 `nginx -t` 確認語法無誤
4. 部署後觀察 nginx log，確認 429 只在異常情況出現
