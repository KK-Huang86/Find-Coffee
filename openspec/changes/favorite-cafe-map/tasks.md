## 1. 基礎設定

- [x] 1.1 加入 `whitenoise` 相依、設定 middleware 與 `CompressedManifestStaticFilesStorage`，`test_settings` 改用 `StaticFilesStorage`，移除重複的 `STATIC_URL`；驗證 `uv run python manage.py check` 通過且 `collectstatic --noinput` 成功
- [x] 1.2 `Dockerfile` 加入 `collectstatic --noinput`；驗證 `docker compose up --build` 後 `/static/admin/css/base.css` 回傳 200
- [x] 1.3 新增 `PUBLIC_BASE_URL` 設定（預設 `http://localhost:8000`）並更新 `.env.example`；驗證 `manage.py check` 通過

## 2. 電話正規化共用化（重構，行為不變）

- [x] 2.1 將 `_build_tel_uri` 的既有測試複製一份指向 `utils/phone.py` 的 `build_tel_uri`，確認為紅燈
- [x] 2.2 實作 `utils/phone.py`，`FlexMessageBuilder._build_tel_uri` 改為呼叫共用函式；驗證新舊測試全綠

## 3. Model 與 fingerprint（先寫測試）

- [x] 3.1 撰寫 `FavoriteMap` 與 token 測試：token 長度與字元集、唯一性、不含 LINE user ID、衝突重試上限、User 刪除時 CASCADE；確認紅燈
- [x] 3.2 撰寫 fingerprint 測試：順序無關、新增／移除會變、移除再加回不變、店家資料更新不變、空集合有固定值；確認紅燈
- [x] 3.3 實作 `FavoriteMap` model、migration、token 產生、fingerprint；驗證 3.1、3.2 全綠且 `makemigrations --check --dry-run` 無遺漏

## 4. Snapshot 序列化（先寫測試）

- [x] 4.1 撰寫 snapshot 測試：欄位完整、`version` 與含時區的 `generated_at`、缺座標排除、缺值輸出 `null`（AI 摘要、照片空字串、電話、備註、屬性）、`rating` 為 float、`tel_uri` 正規化、依收藏時間由新到舊、不含 LINE user ID 與暱稱、空收藏回傳空清單；確認紅燈
- [x] 4.2 實作 snapshot builder；驗證 4.1 全綠

## 5. 生成規則 service（先寫測試）

- [x] 5.1 撰寫生成規則測試，以注入 `now` 覆蓋 spec 所有 scenario：無收藏無地圖、首次建立、收藏全移除、未變動不計次（連點 10 次）、冷卻中與剩餘分鐘（含 29 分 30 秒進位為 1）、冷卻恰好屆滿、當日達上限、Asia/Taipei 跨日重置、UTC 與台北日期不同、token 不變、連結格式（預設網域、結尾斜線）；確認紅燈
- [x] 5.2 撰寫失敗測試：snapshot 生成拋出例外時，snapshot、fingerprint、`generated_at`、次數皆不變、回傳 `error` 且有 `logger.exception` 紀錄；確認紅燈
- [x] 5.3 撰寫並發測試（`transaction=True` + threading）：收藏有變動時兩個請求只生成一次、次數只加 1；首次建立兩個請求只產生一份地圖、一組 token；確認紅燈
- [x] 5.4 實作 `request_favorite_map`（`transaction.atomic` + `select_for_update` + `get_or_create`），並記錄生成耗時，超過 1 秒時發 warning；驗證 5.1–5.3 全綠

## 6. 公開端點（先寫測試）

- [x] 6.1 撰寫 view 測試：頁面殼 200 且 HTML 不含店名、含 noindex meta；資料端點 200 回傳 snapshot JSON 與 `Cache-Control`；不存在與格式錯誤的 token 回傳相同 404 且格式錯誤時不查 DB；POST 回傳 405；兩個端點皆帶 `X-Robots-Tag`、`Referrer-Policy`、CSP；確認紅燈
- [x] 6.2 實作 `cafe/urls.py`、views、template，掛到 `core/urls.py`；驗證 6.1 全綠
- [x] 6.3 撰寫 nginx 設定測試：`map` rate limit zone 存在、`location /map/` 使用該 zone 並回傳 429；確認紅燈
- [x] 6.4 更新 `nginx/nginx.conf`；驗證 6.3 全綠

## 7. LINE 入口（先寫測試）

- [x] 7.1 撰寫 handler 測試：每種 service 結果對應的回覆文案與連結（created / generated / unchanged / cooldown 含分鐘數 / daily_limit / no_favorites / error），一律使用 reply token、不呼叫 push；確認紅燈
- [x] 7.2 撰寫 quick reply 測試：「更多資訊」包含「🗺️ 我的咖啡地圖」；收藏清單回覆包含此選項；有下一頁時同時包含「➡️ 下一頁」；確認紅燈
- [x] 7.3 新增 `MenuAction.FAVORITE_MAP`、handler 與 quick reply；驗證 7.1、7.2 全綠

## 8. 前端純邏輯（先寫測試）

- [x] 8.1 撰寫 `node --test` 測試（`cafe/tests/js/`）：四個篩選條件的值對應、AND 組合、屬性 `null` 視為不符、無條件時回傳全部；`toGeoJSON` 輸出；`safeHttpUrl` 擋 `javascript:`、`data:` 與非字串；`computeView` 處理 0 間、1 間、多間與同座標；`safeTelUri`；`attributeTags`；確認紅燈
- [x] 8.2 實作 `map-core.js`；驗證 `node --test` 全綠
- [x] 8.3 CI 新增 `node --test` 步驟；驗證 workflow 執行成功

## 9. 前端頁面

- [x] 9.1 實作 `map.css`（design Decision 11 的色彩 token、淺色／深色、桌面側欄、手機三段式抽屜）；驗證樣式中沒有參考站色碼（`#A8263A`、`#F4F1EC`、`#E25A6E`、`#161311`），可用 grep 檢查
- [x] 9.2 實作 `map-app.js`：載入狀態、錯誤與重試、空狀態、MapLibre 初始化與底圖主題切換、clustering 與點選展開、選取樣式、清單與卡片（全部以 `textContent` 組 DOM）、篩選同步、主題偏好儲存（try/catch）；驗證用 grep 確認沒有使用 `innerHTML` 插入資料
- [x] 9.3 MapLibre CDN 加上固定版本與 SRI，頁面顯示 OpenStreetMap / OpenFreeMap attribution；驗證瀏覽器 console 沒有 CSP 錯誤

## 10. 整合驗證

- [x] 10.1 本機以 `http://localhost:8000` 手動驗證：1280px 與 375px 版型無水平捲動、深色模式、群集展開、選取店家、四個篩選與無結果狀態、店名為 `<img src=x onerror=alert(1)>` 時以文字顯示、資料端點失敗時顯示重試
- [x] 10.2 `uv run pytest -q`、`uv run ruff check .`、`manage.py check`、`makemigrations --check --dry-run`、`node --test` 全部通過
- [x] 10.3 `openspec validate favorite-cafe-map --strict` 通過

## 11. Code review 修正

- [x] 11.1 static 收集到 `/opt/staticfiles`（`STATIC_ROOT` 可由環境變數設定），docker compose 掛載 `.:/app` 時不會蓋掉 manifest；以 `DEBUG=False` + gunicorn 實測頁面與 static 正常
- [x] 11.2 移除 `STATICFILES_DIRS`：根目錄 `static/` 是文件與 Rich Menu 素材，不對外公開；實測 `/static/rich_menu.png` 回傳 404
- [x] 11.3 自訂 `core.storage.StaticStorage` 開啟 `support_js_module_import_aggregation`；驗證 hash 後的 `map-app` import hash 後的 `map-core`，且回應為 immutable 快取
- [x] 11.4 新增 system check `cafe.W001`：正式環境 `PUBLIC_BASE_URL` 為 localhost 或未設定時發出警告；`cafe/tests/test_checks.py` 涵蓋
- [x] 11.5 每日上限改為先於冷卻判斷（需求變更，見下方說明）；新增 `test_daily_limit_takes_precedence_over_cooldown`
- [x] 11.6 連續兩次被並發請求搶先寫入時回傳 `error`，不回報錯誤的 `unchanged`；新增 `test_losing_race_twice_does_not_report_unchanged`
- [x] 11.7 移除 token 寫入前的 SELECT 檢查，撞號改由 unique constraint 偵測並換新 token；新增 `test_token_collision_at_insert_retries`
- [x] 11.8 清單與卡片的評分顯示改用同一個判斷（評分 0 也顯示）；移除 `token` 多餘的 `db_index`
- [x] 11.9 `test_settings` 移除 WhiteNoise middleware，避免測試時因沒有 `STATIC_ROOT` 產生警告

### 需求變更說明

- **每日上限優先於冷卻**：原 spec 先判斷冷卻再判斷上限，已用完 5 次的使用者會先被告知「約 N 分鐘後可更新」，等完才得知今日次數已用完。改為先判斷上限，spec「地圖生成規則」同步更新並新增 scenario「達上限時優先於冷卻」。
- **收藏清單回覆一律附地圖入口**：既有測試 `test_favorites_no_next_page_button_when_exact_fit` 原斷言剛好一頁時 `quick_reply is None`，因 spec「LINE 入口」要求收藏清單回覆包含「🗺️ 我的咖啡地圖」，改為斷言沒有「下一頁」按鈕。

## 需求對應

- [x] 地圖存取 token：3.1、3.3、5.1、11.7
- [x] 地圖連結格式：1.3、5.1、11.4
- [x] 收藏變動判斷：3.2、3.3
- [x] 地圖生成規則：5.1、5.4、11.5
- [x] 並發生成防護：5.3、5.4、11.6
- [x] 生成失敗不留半成品：5.2、5.4、7.1
- [x] snapshot 內容：2.1、2.2、4.1、4.2
- [x] 地圖資料端點：6.1、6.2、6.3、6.4
- [x] LINE 入口：7.1、7.2、7.3
- [x] 地圖頁面殼：1.1、1.2、6.1、6.2、11.1、11.3
- [x] 地圖標示：8.1、8.2、9.2、10.1
- [x] 店家清單：9.2、10.1
- [x] 店家卡片：8.1、9.2、10.1
- [x] 屬性篩選：8.1、8.2、9.2、10.1
- [x] 響應式版型：9.1、10.1
- [x] 深色模式：9.1、9.2、10.1
- [x] 載入與錯誤狀態：9.2、10.1
- [x] 輸出安全：6.1、8.1、9.2、9.3、10.1
- [x] 視覺識別：9.1
