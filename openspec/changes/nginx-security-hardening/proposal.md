## Why

目前 docker-compose 的 `nginx/nginx.conf` 啟用了 `set_real_ip_from 0.0.0.0/0`，在 nginx 直接對外（無 proxy 在前）的情況下，任何 client 都能偽造 `X-Forwarded-For` header 變更自己在限流計數器中的 key，完全繞過 rate limiting。生產環境（Linode LKE）的 nginx Ingress Controller 目前也完全沒有 rate limiting。

## What Changes

- **docker-compose**：移除 `real_ip_header`、`real_ip_recursive`、`set_real_ip_from 0.0.0.0/0`，改用 `$remote_addr` 作為限流 key 與轉發 header
- **docker-compose**：將 `location /callback` 改為 `location = /callback`（exact match），避免 `/callback-attack` 等路徑意外繞過不限流規則
- **docker-compose**：所有 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` 改為 `$remote_addr`，防止 client 偽造的 header 傳入 Django
- **infra repo（記錄設計，實作由使用者執行）**：在 nginx Ingress Controller 上拆成三個 Ingress object，分別針對 `/admin`、`/callback`、`/` 設定不同限流策略

## Capabilities

### New Capabilities

- `nginx-security-hardening`: docker-compose nginx 的安全性強化與 K8s Ingress rate limiting 設計

### Modified Capabilities

（無）

## Impact

- `nginx/nginx.conf`：移除 real_ip 區塊，修改 location 匹配方式與 X-Forwarded-For header
- infra repo：新增三個 Ingress object YAML（設計記錄於本 repo，實作在 infra repo）
- 生產環境部署流程：需在 infra repo 套用 Ingress 變更後重新部署
