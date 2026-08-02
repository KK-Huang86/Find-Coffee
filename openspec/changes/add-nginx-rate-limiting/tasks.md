## 1. 修改 nginx 設定

- [ ] 1.1 在 `nginx/nginx.conf` 的 server 區塊外新增 real_ip 設定：`real_ip_header X-Forwarded-For`、`real_ip_recursive on`、`set_real_ip_from 0.0.0.0/0`
- [ ] 1.2 在 server 區塊外新增兩個 `limit_req_zone`（含 memory size）：
      `limit_req_zone $binary_remote_addr zone=admin:10m rate=5r/m;`
      `limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;`
- [ ] 1.3 將現有 `location /` 拆分為三個獨立 location block：`/admin/`、`/callback/`、`/`，每個 block 均保留完整 proxy 設定（proxy_pass、headers、timeout）
- [ ] 1.4 對 `/admin/` 加入 `limit_req zone=admin burst=3 nodelay;` 和 `limit_req_status 429;`
- [ ] 1.5 對 `/callback/` 不加任何 limit_req 指令
- [ ] 1.6 對 `/` 加入 `limit_req zone=general burst=20 nodelay;` 和 `limit_req_status 429;`

## 2. 語法確認與重啟

- [ ] 2.1 在 nginx container 內執行 `nginx -t`，確認語法無誤後再重啟
- [ ] 2.2 執行 `docker compose restart nginx`，確認正常啟動

## 3. 驗證各路徑行為

- [ ] 3.1 驗證 `/admin/` 超量回 429：
      `for i in $(seq 1 10); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost/admin/; done`
      前幾個應為 302/200，超過後應出現 429
- [ ] 3.2 驗證 `/` 一般流量超量回 429：
      `for i in $(seq 1 30); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost/; done`
      持續高頻後應出現 429
- [ ] 3.3 驗證 `/callback/` 高頻不回 429：
      `for i in $(seq 1 30); do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost/callback/; done`
      應全部為非 429（405 或其他，但不是 429）
