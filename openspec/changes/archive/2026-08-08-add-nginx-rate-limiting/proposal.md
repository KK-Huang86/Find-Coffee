## Why

目前 nginx 對所有路徑一視同仁，沒有任何流量限制，異常高頻請求（暴力破解 `/admin/`、惡意掃描）會直接打穿到 Django/Gunicorn，消耗 worker 資源。加入 rate limiting 可在最外層擋住異常流量，保護後端服務。

## What Changes

- `nginx/nginx.conf`：新增 `limit_req_zone` 定義限流區，並針對不同路徑套用不同規則
- `/admin/`：嚴格限流（5 requests/分鐘），防止暴力破解登入
- `/callback/`：不限流，LINE 伺服器的 webhook 流量不應被擋
- `/`（其他）：一般保護（10 requests/秒，burst 20），擋異常高頻但不影響正常使用

## Capabilities

### New Capabilities

- `nginx-rate-limiting`：nginx 依路徑分層限流，超過限制回 429 Too Many Requests

### Modified Capabilities

（無）

## Impact

- **`nginx/nginx.conf`**：唯一修改的檔案
- LINE Bot webhook（`/callback/`）不受影響
- 正常使用者不受影響（burst 設計允許短暫高頻）
- 超過限制的 request 收到 429，不進入 Django
