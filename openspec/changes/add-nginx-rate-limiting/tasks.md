## 1. 修改 nginx 設定

- [ ] 1.1 在 `nginx/nginx.conf` 的 server 區塊外新增兩個 `limit_req_zone`：`admin`（5r/m）和 `general`（10r/s）
- [ ] 1.2 將 `location /` 拆分為三個獨立 location block：`/admin/`、`/callback/`、`/`
- [ ] 1.3 對 `/admin/` 套用 `limit_req zone=admin burst=3 nodelay` 和 `limit_req_status 429`
- [ ] 1.4 對 `/callback/` 不加任何 limit_req 指令
- [ ] 1.5 對 `/` 套用 `limit_req zone=general burst=20 nodelay` 和 `limit_req_status 429`

## 2. 本地驗證

- [ ] 2.1 執行 `docker compose restart nginx`，確認 nginx 正常啟動（無語法錯誤）
- [ ] 2.2 確認 LINE Bot webhook（`/callback/`）正常運作，未被限流
- [ ] 2.3 確認 `/admin/` 可正常存取

## 3. 語法確認

- [ ] 3.1 在 nginx container 內執行 `nginx -t` 確認設定語法無誤
