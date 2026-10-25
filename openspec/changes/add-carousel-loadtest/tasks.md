## 1. 測試（TDD 紅燈）

- [x] 1.1 `integrations/tests/test_google_api.py`：`MAPS_BASE_URL` 預設為正式網址、`BASE_URL` / `PHOTO_URL` / `GEOCODE_URL` 由其組成、`_geocode_address` 呼叫 `GEOCODE_URL`
- [x] 1.2 `line_bot/tests/builders/test_shop_flex_message.py`：照片解析呼叫 `GoogleAPI.PHOTO_URL`
- [x] 1.3 `cafe/tests/test_tasks.py`：照片下載呼叫 `GoogleAPI.PHOTO_URL`
- [x] 1.4 `core/tests/test_line_configuration.py`：`event_handlers` 與 `views` 的 LINE host 預設為正式網址且一致
- [x] 1.5 實作前執行：8 failed

## 2. 實作

- [x] 2.1 `GoogleAPI` 新增 `MAPS_BASE_URL`（`GOOGLE_MAPS_BASE_URL`）、`PHOTO_URL`、`GEOCODE_URL`，三處寫死網址改用常數
- [x] 2.2 `event_handlers.py`、`views.py` 以 `LINE_API_HOST` 建立 `Configuration`
- [x] 2.3 `.env.example` 新增兩個選填變數
- [x] 2.4 新增 `loadtest/`（mock server、compose、seed、K6、run.sh、README），`loadtest/results/` 加入 `.gitignore`

## 3. 驗證

- [x] 3.1 `uv run pytest -q` 513 passed；`ruff check .`、`manage.py check` 通過
- [x] 3.2 `loadtest/run.sh` 實跑 VUS=1 / VUS=5 三種情境，checks 100%；mock 呼叫次數符合預期，無未 mock 端點的呼叫；結果記錄於 `loadtest/README.md`
- [x] 3.3 `openspec validate add-carousel-loadtest --strict` 通過
