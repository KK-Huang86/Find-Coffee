## 1. 測試

- [x] 1.1 `line_bot/tests/builders/test_shop_flex_message.py` 的 `TestResolvePhotoUrl` 新增：
  - `test_uses_split_connect_and_read_timeout`：`requests.head` 以 `timeout=(2, 4)` 呼叫
  - `test_logs_warning_with_status_code_when_not_200`（parametrize 204/302/400/403/404/500）：回傳預設圖，且恰好一筆 warning，含 status code 與 `photo_reference`
  - `test_non_200_log_does_not_leak_api_key`：log 不含 API key
  - `test_does_not_log_warning_on_success`：200 時不記錄 warning
- [x] 1.2 實作前執行，確認 7 failed（timeout 仍為 `2`、非 200 未記錄 log）

## 2. 實作

- [x] 2.1 `resolve_photo_url`：timeout 改為 `(2, 4)`；非 200 時 `logger.warning` 記錄 status code 與 `photo_reference`（不含 `photo_api_url`）

## 3. 驗證

- [x] 3.1 `uv run pytest -q` 全數通過（438 passed）
- [x] 3.2 `uv run ruff check .`、`uv run python manage.py check` 通過
- [x] 3.3 `openspec validate tune-photo-resolve-timeout --strict` 通過
