## ADDED Requirements

### Requirement: docker-compose nginx 不信任 client 提供的 IP header
在 docker-compose 環境中，nginx 直接對外（無 upstream proxy），系統 SHALL 使用 `$remote_addr`（TCP 連線來源）作為限流 key 與 X-Forwarded-For header 值，不得讀取或轉發 client 提供的 X-Forwarded-For header。

#### Scenario: 移除 real_ip 模組設定
- **WHEN** nginx 啟動時
- **THEN** 設定中不得包含 `real_ip_header`、`real_ip_recursive`、`set_real_ip_from` 指令

#### Scenario: X-Forwarded-For 以 $remote_addr 覆寫
- **WHEN** nginx 將請求轉發給 Django
- **THEN** `X-Forwarded-For` header 值為 `$remote_addr`，不累加 client 原始 header

#### Scenario: client 偽造 X-Forwarded-For 不影響限流
- **WHEN** client 在請求中附帶偽造的 `X-Forwarded-For: 1.2.3.4` header
- **THEN** rate limiting key 仍為真實連線 IP（`$remote_addr`），限流計數不受影響

### Requirement: /callback 路徑使用 exact match
docker-compose nginx 的 `/callback` 不限流規則 SHALL 僅適用於完全符合 `/callback` 的路徑，不得匹配 `/callback/`、`/callback-attack` 等變體。

#### Scenario: exact match 只匹配 /callback
- **WHEN** 請求路徑為 `/callback`
- **THEN** 套用不限流的 location 區塊

#### Scenario: /callback/ 受一般限流保護
- **WHEN** 請求路徑為 `/callback/`（尾斜線）
- **THEN** 落入 `location /`，受 general rate limiting 保護

#### Scenario: /callback 變體路徑受一般限流保護
- **WHEN** 請求路徑為 `/callback-attack` 或其他 /callback 前綴路徑
- **THEN** 落入 `location /`，受 general rate limiting 保護

### Requirement: K8s 生產環境以三個 Ingress object 實作 rate limiting
在 Linode LKE 生產環境，系統 SHALL 以三個獨立的 Ingress object 分別管理 `/admin`、`/callback`、`/` 的限流策略，由 nginx Ingress Controller 執行。

#### Scenario: /admin 嚴格限流
- **WHEN** 請求路徑符合 `/admin` 前綴
- **THEN** 套用嚴格 rate limiting（對應 5r/m 等級），超量回傳 429

#### Scenario: /callback 不限流
- **WHEN** 請求路徑完全符合 `/callback`
- **THEN** 不套用任何 rate limiting，LINE webhook 正常通過

#### Scenario: 一般路徑受保護
- **WHEN** 請求路徑不符合 /admin 或 /callback
- **THEN** 套用一般 rate limiting，超量回傳 429
