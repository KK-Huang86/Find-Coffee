## Context

目前 `nginx/nginx.conf` 用於 docker-compose 本地環境，nginx 直接對外，無任何 upstream proxy。設定中保留了 `set_real_ip_from 0.0.0.0/0`，導致 client 可偽造 `X-Forwarded-For` 繞過 rate limiting。

生產環境架構：

```
Client → Linode NodeBalancer → nginx Ingress Controller（Helm，ingress-nginx 4.12.0）→ Django（web:8000）
```

K8s 的 nginx 是 Ingress Controller，與 repo 裡的 `nginx/nginx.conf` 無關。目前生產環境完全沒有 rate limiting。K8s manifest 放在獨立的 infra repo。

## Goals / Non-Goals

**Goals:**
- docker-compose：移除 real_ip 設定，防止 IP 偽造繞過限流
- docker-compose：`/callback` 改 exact match，縮小不限流範圍
- docker-compose：`X-Forwarded-For` 改用 `$remote_addr`，不傳遞偽造 header
- 記錄 K8s 生產環境 rate limiting 的設計，供 infra repo 實作參考

**Non-Goals:**
- 不在本 repo 實作 K8s manifest（infra repo 負責）
- 不處理 TLS termination（已由 cert-manager 處理）
- 不改動 Django 應用層的 IP 處理邏輯

## Decisions

### Decision 1：docker-compose 完全移除 real_ip 模組

**選擇**：移除 `real_ip_header`、`real_ip_recursive`、`set_real_ip_from 0.0.0.0/0`

**理由**：docker-compose 的 nginx 直接對外，`$remote_addr` 即為真實 client IP，不需要 real_ip 模組。保留 `set_real_ip_from 0.0.0.0/0` 反而信任所有來源，讓 client 可任意偽造 `X-Forwarded-For` 改變限流 key。

**替代方案**：限縮 `set_real_ip_from` 為特定範圍 → 但 docker-compose 本地沒有固定的 proxy IP，無法填有意義的範圍，移除最乾淨。

### Decision 2：/callback 改 exact match（`location = /callback`）

**選擇**：`location = /callback`

**理由**：nginx 前綴匹配（`location /callback`）會匹配 `/callback/`、`/callbackXYZ` 等所有前綴路徑，讓不限流規則的覆蓋範圍超出預期。`= ` exact match 只匹配完全相符的路徑，符合 LINE webhook 的實際呼叫方式（`POST /callback`）。

**影響**：`/callback/`（尾斜線）將落入 `location /`，受 general rate limiting 保護。

### Decision 3：X-Forwarded-For 改為 `$remote_addr`

**選擇**：`proxy_set_header X-Forwarded-For $remote_addr`

**理由**：`$proxy_add_x_forwarded_for` 會累加 client 原始的 `X-Forwarded-For` header，若 client 偽造該 header，Django 會看到偽造的 IP 列表，影響 Django 的 IP 判斷邏輯。改用 `$remote_addr` 直接覆寫，確保 Django 收到的是 nginx 看到的真實連線 IP。

### Decision 4：K8s rate limiting 用三個 Ingress object

**選擇**：拆成三個 Ingress object，分別對應 `/admin`、`/callback`、`/`

**理由**：nginx Ingress Controller 的 annotation `limit-rps` 只能設全域，無法分路徑。拆成多個 Ingress object 可讓每條路徑套用不同 annotation，維持與 docker-compose 相同的策略結構。

**替代方案**：nginx ConfigMap + server-snippet → 需要啟用 `allow-snippet-annotations`（預設關閉，有安全疑慮），不推薦。

**K8s 三個 Ingress 設計**：

```yaml
# 1. /admin — 嚴格限流
annotations:
  nginx.ingress.kubernetes.io/limit-rps: "1"        # 約 5r/m
  nginx.ingress.kubernetes.io/limit-burst-multiplier: "3"

# 2. /callback — 不限流（無 limit annotation）
# pathType: Exact，path: /callback

# 3. / — 一般限流
annotations:
  nginx.ingress.kubernetes.io/limit-rps: "10"
  nginx.ingress.kubernetes.io/limit-burst-multiplier: "20"
```

**real_ip 在 K8s**：nginx Ingress Controller 預設已處理 `X-Forwarded-For`，`$remote_addr` 在 Ingress Controller 內即為 NodeBalancer 的 IP，Controller 內部透過 `use-forwarded-headers` 還原真實 client IP，不需要另外設定 real_ip 模組。未來若要限縮信任範圍，應在 Ingress Controller 的 ConfigMap 設定 `proxy-real-ip-cidr` 為 Linode NodeBalancer 的實際 IP 範圍，而非 `0.0.0.0/0`。

## Risks / Trade-offs

- **[Risk] exact match 後 /callback/ 被限流** → 接受，LINE 官方文件指定 webhook URL 不含尾斜線，正常使用不受影響
- **[Risk] K8s infra repo 未同步** → 本 repo 完成後，需手動在 infra repo 套用對應 Ingress 變更，無自動聯動機制
- **[Risk] Linode NodeBalancer IP 範圍變動** → 未來 K8s Ingress Controller 設定 `proxy-real-ip-cidr` 時需定期確認 NodeBalancer IP，或改用 Linode 提供的固定 IP 範圍

## Migration Plan

**docker-compose（本 repo）**：
1. 修改 `nginx/nginx.conf`
2. `docker compose restart nginx`
3. 驗證：curl 測試三條路徑行為

**K8s 生產（infra repo，使用者自行執行）**：
1. 在 infra repo 新增三個 Ingress YAML
2. 刪除或替換現有單一 Ingress object
3. `kubectl apply -f k8s/ingress/`
4. 驗證：觀察各路徑是否回傳正確 status code

**Rollback**：docker-compose 還原 `nginx/nginx.conf` 並重啟；K8s 還原舊 Ingress YAML 並 apply。

## Open Questions

- Linode NodeBalancer 的實際 IP 範圍為何？（供未來設定 `proxy-real-ip-cidr` 使用）
