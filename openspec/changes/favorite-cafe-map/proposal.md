## Why

使用者在 LINE 內只能以分頁 bubble 逐頁瀏覽「收藏的咖啡店」，無法一眼看出收藏店家的地理分布，也無法依插座、限時、寵物等屬性快速挑選。提供一張個人「咖啡地圖」網頁，讓使用者在地圖上檢視全部收藏，並沿用既有屬性標籤作為篩選條件。

## What Changes

- 新增 `FavoriteMap` model：每位使用者一份，持有不可猜的存取 token、收藏 snapshot（JSON）、收藏 fingerprint、最後生成時間與每日生成次數
- 新增地圖生成服務：使用者點選「我的咖啡地圖」時，於 webhook 內同步判斷並生成 snapshot，以 reply token 回傳地圖連結
  - 收藏未變動：直接回傳既有連結，不計次
  - 收藏有變動但距上次生成未滿 30 分鐘：回傳既有連結並提示剩餘等待分鐘數
  - 收藏有變動、冷卻已過且當日（Asia/Taipei）生成未滿 5 次：生成新版
  - 當日已生成 5 次：回傳既有連結並提示當日次數已用完
  - 店家資料（`ai_summary`、照片、屬性）更新不視為收藏變動
- 新增公開端點（不需登入，憑 token 存取）：
  - `GET /map/<token>/`：地圖頁面殼（HTML，不含個人資料）
  - `GET /map/<token>/data.json`：回傳該使用者的 snapshot
- 新增前端地圖頁：MapLibre GL JS + OpenFreeMap 向量底圖，原生 clustering、桌面側邊店家清單、手機底部抽屜、店家卡片（照片、店名、評分、屬性標籤、AI 摘要、Google Maps、電話、備註）、四個屬性篩選（有插座、不限時、寵物友善、店內有貓狗）、深色模式。版型與互動參考 coffee.aaron-shih.com，配色、字體、元件外觀與文案自行設計
- 「更多資訊」quick reply 與「收藏的咖啡店」回覆加入「🗺️ 我的咖啡地圖」入口（Rich Menu 六格已滿，不新增格位）
- 導入 WhiteNoise 由 Django serve static 檔案（目前生產環境沒有 static serving）
- `/map/` 回應加上 `Referrer-Policy`、`X-Robots-Tag: noindex` 與 CSP；nginx 新增 `/map/` location 與專用 rate limit
- 新增 `PUBLIC_BASE_URL` 設定，尚無網域前預設為 `http://localhost:8000`
- 電話正規化（`tel:` URI）邏輯移至共用模組，供 LINE 卡片與地圖 snapshot 共用

## Capabilities

### New Capabilities

- `favorite-cafe-map`：個人咖啡地圖的存取 token、snapshot 生成規則（變動判斷、30 分鐘冷卻、每日 5 次上限）、LINE 入口、公開端點與 snapshot 資料格式。
- `favorite-cafe-map-page`：地圖前端頁面的呈現、篩選、響應式版型、深色模式與安全標頭。

### Modified Capabilities

（無）

## Impact

- **`cafe/models.py`、`cafe/migrations/`**：新增 `FavoriteMap` model 與 migration
- **`cafe/services/favorite_map.py`**：新增生成與限流邏輯
- **`cafe/views.py`、`cafe/urls.py`、`core/urls.py`**：新增 `/map/` 路由
- **`cafe/templates/`、`cafe/static/`**：新增地圖頁面殼、CSS、JS
- **`line_bot/handlers/postback_actions.py`、`line_bot/builders/quick_reply.py`、`line_bot/constants.py`**：新增「我的咖啡地圖」入口與回覆文案
- **`utils/phone.py`、`line_bot/builders/shop_flex_message.py`**：電話正規化移至共用模組，builder 改為呼叫共用函式（行為不變）
- **`core/settings.py`、`core/test_settings.py`、`pyproject.toml`、`Dockerfile`**：加入 WhiteNoise、`collectstatic`、`PUBLIC_BASE_URL` 設定，移除重複的 `STATIC_URL`
- **`.env.example`**：新增 `PUBLIC_BASE_URL`
- **`nginx/nginx.conf`、`nginx/tests/`**：新增 `/map/` location、rate limit 與安全標頭
- **`.github/workflows/ci.yml`**：新增 `node --test` 執行前端純邏輯測試
- 新增前端外部相依：MapLibre GL JS（CDN，固定版本）、OpenFreeMap tiles（免費、免 API key）
- 不影響既有收藏寫入流程、Google Places 用量與 Celery tasks
