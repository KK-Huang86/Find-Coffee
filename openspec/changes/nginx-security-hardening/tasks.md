## 1. 修改 nginx/nginx.conf（docker-compose）

- [x] 1.1 移除 `real_ip_header X-Forwarded-For`、`real_ip_recursive on`、`set_real_ip_from 0.0.0.0/0` 三行
- [x] 1.2 將 `location /callback` 改為 `location = /callback`（exact match）
- [x] 1.3 將三個 location block 的 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` 全部改為 `$remote_addr`

## 2. 語法確認與重啟

- [x] 2.1 在 nginx container 內執行 `nginx -t`，確認語法無誤
- [x] 2.2 執行 `docker compose restart nginx`，確認正常啟動

## 3. 驗證 docker-compose 行為

- [x] 3.1 驗證 `/admin` 超量仍回 429（rate limiting 未受影響）：
      `for i in $(seq 1 10); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost/admin; done`
- [x] 3.2 驗證 `POST /callback` 直接到達 Django（不再出現 301）：
      `curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost/callback`
      預期：400（LINE SDK signature 驗證失敗），不是 301
- [x] 3.3 驗證 `/callback/`（尾斜線）受一般限流保護：
      `for i in $(seq 1 30); do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost/callback/; done`
      超量後應出現 429

## 4. infra repo 設計參考（使用者自行執行）

- [ ] 4.1 在 infra repo 新增 `ingress-admin.yaml`：path `/admin`，套用嚴格 rate limiting annotation（`limit-rps: "1"`、`limit-burst-multiplier: "3"`）
- [ ] 4.2 在 infra repo 新增 `ingress-callback.yaml`：path `/callback`，`pathType: Exact`，無 rate limiting annotation
- [ ] 4.3 在 infra repo 新增 `ingress-general.yaml`：path `/`，套用一般 rate limiting annotation（`limit-rps: "10"`、`limit-burst-multiplier: "20"`）
- [ ] 4.4 刪除 infra repo 現有的單一 Ingress object，`kubectl apply` 套用三個新 Ingress
- [ ] 4.5 驗證生產環境各路徑限流行為符合預期
