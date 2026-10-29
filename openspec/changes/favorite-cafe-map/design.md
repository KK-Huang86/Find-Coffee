## Context

- 收藏存在 `Favorite(user, cafe, note, is_public, created_at)`，`unique_together = (user, cafe)`。`is_public` 目前沒有機制，本 change 不使用；`note` 尚未開放填寫，但保留在 snapshot。
- `Cafe` 已有 `lat`、`lng`、`ai_summary`、`photo_s3_url`（CloudFront）、四個屬性欄位（`has_socket`、`limited_time`、`pet_friendly`、`has_pet`），值為 `yes` / `maybe` / `no` / `null`。
- Rich Menu 六格已滿；「更多資訊」以 quick reply 承載次要功能。
- 生產環境沒有 static serving：nginx 沒有 `/static/` location，也沒有 WhiteNoise，`Dockerfile` 沒有執行 `collectstatic`。`core/settings.py` 有兩處 `STATIC_URL` 定義。
- 資料庫經 PgBouncer transaction pooling，`select_for_update` 必須包在 `transaction.atomic` 內，transaction pooling 下可正常運作。
- 目前沒有網域，連結先使用 `http://localhost:8000`。
- 參考站 coffee.aaron-shih.com 使用 React + MapLibre GL + OpenFreeMap，GeoJSON 原生 clustering，桌面側欄、手機抽屜。本 change 借鏡版型與互動模式，不沿用其視覺識別。

## Goals / Non-Goals

**Goals:**
- 生成邏輯集中在單一 service，可在不經過 LINE 的情況下完整測試
- 頁面殼與資料分離，未來把 snapshot 搬到 S3 時前端不需改動
- 前端不引入 build pipeline

**Non-Goals:**
- 不上傳 S3 / CloudFront（第二版）
- 不做重設連結、好友地圖、可見性設定（第二版）
- 不做店名搜尋、排序切換、定位「離我最近」、隨機抽店
- 不顯示營業時間與 Google 評論
- 店家資料更新不觸發重新生成

## Decisions

### Decision 1：`FavoriteMap` 放在 `cafe` app，獨立資料表

```
FavoriteMap
  user              OneToOne(User, on_delete=CASCADE, related_name='favorite_map')
  token             CharField(max_length=64, unique=True, db_index=True)
  snapshot          JSONField(default=dict)
  fingerprint       CharField(max_length=64)          # sha256 hex
  generated_at      DateTimeField
  daily_count       PositiveSmallIntegerField(default=0)
  daily_count_date  DateField                          # Asia/Taipei 日期
  created_at / updated_at
```

- 與 `Favorite` 同屬 `cafe` app，避免跨 app 的循環相依。
- 不把欄位加在 `User` 上：地圖是可獨立演進的資源，之後的 `visibility`、重設連結都會掛在這張表；`User` 被刪除時以 CASCADE 一併移除。
- 替代方案：用 Redis 存 snapshot。拒絕原因：snapshot 是使用者可分享的持久資料，Redis 被清空會讓已發出的連結失效。

### Decision 2：token 用 `secrets.token_urlsafe(32)`

產生 43 字元 base64url 字串（256 bits）。URL 路由以 `[A-Za-z0-9_-]{43}` 比對，不符格式直接 404，不查 DB。寫入時撞到 unique constraint 就換新 token 重試，最多 3 次，超過即拋出例外（不事先 SELECT 檢查：多一次查詢且檢查與寫入之間仍有競爭）。

### Decision 3：fingerprint = 排序後 cafe id 的 sha256

`sha256(",".join(sorted(str(cafe_id))))`。只依收藏集合決定，與順序無關，店家資料更新不影響（符合 spec）。空集合也有固定的 fingerprint，所以「收藏全部移除」會被判定為變動。

### Decision 4：同步生成於 webhook 內

生成只需一次 `select_related('cafe')` 查詢加上組 dict，收藏數百筆仍在百毫秒等級，不會超過 LINE reply token 的時效。
- 替代方案 A：Celery 生成後 push 連結。拒絕原因：push 會消耗 LINE 每月免費訊息額度。
- 替代方案 B：Celery 生成、前端 polling。拒絕原因：增加狀態機與前端複雜度，換不到實質效益。收藏量成長到需要時再改。

### Decision 5：生成流程與並發控制

service 介面：

```python
@dataclass(frozen=True)
class FavoriteMapResult:
    status: Literal['no_favorites', 'created', 'generated', 'unchanged',
                    'cooldown', 'daily_limit', 'error']
    url: str | None
    wait_minutes: int | None = None

def request_favorite_map(user, *, now: datetime | None = None) -> FavoriteMapResult
```

流程：

1. 沒有 `FavoriteMap` 且沒有收藏：回傳 `no_favorites`，不建立資料
2. 尚無 `FavoriteMap`：組 snapshot 後 `create`。若撞到 OneToOne unique constraint（並發建立），代表另一個請求已建立，重新讀取後依步驟 3 判斷
3. 已有 `FavoriteMap`：依 Decision 3 計算目前 fingerprint，依 spec 規則判斷狀態（每日上限先於冷卻判斷）
4. 需要生成時：組 snapshot，以**條件式 UPDATE**（樂觀鎖）寫回：
   `FavoriteMap.objects.filter(pk=..., fingerprint=<讀取時>, generated_at=<讀取時>).update(...)`
   - 影響 1 列：生成成功
   - 影響 0 列：另一個請求已先寫入。重新讀取，以最新狀態再判斷一次（通常是 `unchanged` 或 `cooldown`），不重複計次；連續 2 次都被搶先時放棄並回傳 `error`，不回報錯誤的 `unchanged`
   - token 的唯一性只靠 unique constraint：`create` 撞到 IntegrityError 時，若該使用者已有地圖代表並發建立，否則視為 token 撞號，換新 token 重試，最多 3 次
5. 任一步驟拋出例外：不寫入任何欄位，記錄 `logger.exception`（含 user pk，不含 LINE user ID），回傳 `error`

選擇樂觀鎖而非 `select_for_update`：測試環境是 SQLite in-memory，`select_for_update` 在 SQLite 上不生效，無法以測試驗證並發行為；條件式 UPDATE 在 SQLite 與 PostgreSQL 都是單一原子操作，並發測試可在生成過程中插入另一個請求的寫入來重現競爭，不依賴 threading。代價是兩個並發請求都會組一次 snapshot（只是一次查詢，可接受），但只有一個能寫入。

`now` 參數可注入時間，方便測試冷卻與跨日。webhook 既有的 Redis 使用者鎖是第一層防護，條件式 UPDATE 是最終保證。

冷卻剩餘分鐘：`ceil((generated_at + 30min - now) / 60s)`，最小值為 1。

### Decision 6：「當日」以 Asia/Taipei 計算

專案 `TIME_ZONE = 'UTC'`，不改全域設定。service 內以 `now.astimezone(ZoneInfo('Asia/Taipei')).date()` 取得當日；`daily_count_date` 不同於當日時，視為 `daily_count = 0`。

### Decision 7：snapshot 格式

```json
{
  "version": 1,
  "generated_at": "2026-10-27T10:00:00+08:00",
  "cafes": [
    {
      "place_id": "ChIJ...",
      "name": "店名",
      "address": "台北市...",
      "lat": 25.04,
      "lng": 121.53,
      "rating": 4.6,
      "user_ratings_total": 321,
      "phone": "02 2345 6789",
      "tel_uri": "tel:0223456789",
      "google_maps": "https://maps.google.com/?cid=...",
      "website": "https://...",
      "photo_url": "https://xxx.cloudfront.net/...",
      "ai_summary": "...",
      "attributes": {"has_socket": "yes", "limited_time": "no",
                     "pet_friendly": null, "has_pet": "maybe"},
      "note": null,
      "favorited_at": "2026-10-20T08:00:00+08:00"
    }
  ]
}
```

- `tel_uri` 沿用 `add-shop-phone-call` 已實作的 `_build_tel_uri` 正規化規則，前端不需重寫一份。實作時將它從 builder 移到共用位置（例如 `utils/phone.py`），兩邊共用。
- `rating` 由 `Decimal` 轉為 `float`；空字串 `photo_s3_url` 轉為 `null`。
- 不放 `reviews`、`opening_hours`，控制大小。每間店約 1KB，數百間收藏仍在數百 KB 以內。

### Decision 8：Django serve 頁面殼與資料，WhiteNoise serve static

- `GET /map/<token>/`：render template；只確認 token 存在，不讀 snapshot
- `GET /map/<token>/data.json`：`JsonResponse(snapshot)`，帶 `Cache-Control: private, max-age=60`
- 安全標頭統一由 view 設定（`X-Robots-Tag`、`Referrer-Policy`、`Content-Security-Policy`），dev 與 prod 行為一致，且能用 pytest 驗證；nginx 只負責 rate limit
- 導入 WhiteNoise（`CompressedManifestStaticFilesStorage`），`Dockerfile` 加入 `collectstatic --noinput`，並移除重複的 `STATIC_URL`。順帶修正 Django admin 在生產環境沒有 CSS 的問題
- 替代方案：nginx 掛 volume serve `staticfiles/`。拒絕原因：需要 web 與 nginx 共享 volume，部署耦合較高
- `test_settings` 使用一般的 `StaticFilesStorage`，避免測試前必須先跑 `collectstatic`

CSP（只套用在 `/map/` 兩個端點，不影響 admin 與 webhook）：

```
default-src 'self';
script-src 'self' https://unpkg.com;
style-src 'self' https://unpkg.com;
img-src 'self' data: blob: https:;
connect-src 'self' https://tiles.openfreemap.org;
font-src 'self' https://tiles.openfreemap.org;
worker-src blob:; child-src blob:;
base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

- `img-src` 允許任意 https：店家照片網址一律是 https（CloudFront），不把 CloudFront 網域綁進設定；圖片不能執行程式，風險可接受
- CSP 禁止 inline script，因此「渲染前套用主題」獨立成同步載入的 `map-theme.js`

### Decision 9：nginx rate limit

新增 `limit_req_zone $binary_remote_addr zone=map:10m rate=30r/m;`，`location /map/` 使用 `burst=20 nodelay`、`limit_req_status 429`。一次開頁約 2 個請求（殼、資料），正常瀏覽不受影響；暴力猜 token 每個 IP 每分鐘最多 30 次，256-bit token 空間下不可行。

### Decision 10：前端技術

- MapLibre GL JS `4.7.1`，由 unpkg 載入，固定版本並加上 SRI `integrity`
- 底圖：OpenFreeMap `positron`（淺色）與 `dark`（深色），免費、免 API key，頁面顯示 OpenStreetMap / OpenFreeMap attribution
- 不使用框架與 build pipeline，ES modules：
  - `cafe/static/cafe/map/map-core.js`：純函式，不碰 DOM 與 MapLibre（`filterCafes`、`toGeoJSON`、`safeHttpUrl`、`safeTelUri`、`computeView`、`attributeTags`、篩選條件定義）。標籤文字與 LINE 卡片一致
  - `cafe/static/cafe/map/map-theme.js`：在 `<head>` 同步執行，渲染前套用主題
  - `cafe/static/cafe/map/map-app.js`：DOM、MapLibre、抽屜、主題切換
  - `cafe/static/cafe/map/map.css`
- 文字一律以 `textContent` / `createElement` 組 DOM，不使用 `innerHTML` 插入資料
- 群集：GeoJSON source `cluster: true`、`clusterRadius: 50`、`clusterMaxZoom: 15`；點選群集呼叫 `getClusterExpansionZoom` 後 `easeTo`
- 主題切換用 `setStyle(url, { diff: false })`：diff 模式不會觸發 `style.load`，自訂圖層會遺失
- 選取店家時以 `flyTo` 的 `offset` 調整位置：桌面讓上方 popup 有空間（popup 固定 `anchor: 'bottom'`），手機避開底部抽屜

### Decision 11：視覺識別（自行設計，避開參考站）

主題「烘焙」：以咖啡豆的焦糖、深焙棕搭配抹茶綠作為標籤色，有別於參考站的酒紅色系。

| token | 淺色 | 深色 |
|---|---|---|
| `--bg` | `#FAF7F2` | `#121417` |
| `--surface` | `#FFFFFF` | `#1C1F24` |
| `--text` | `#2B211A` | `#EDE6DC` |
| `--muted` | `#7C6F63` | `#A49A8E` |
| `--border` | `#E6DED3` | `#2E3238` |
| `--primary`（深焙棕，按鈕與選取） | `#5A3825` | `#E0A96D` |
| `--marker`（焦糖，店家圓點） | `#C07A2C` | `#E0A96D` |
| `--cluster` | `#5A3825` | `#C07A2C` |
| `--ring`（選取外圈） | `#5A3825` | `#EDE6DC` |
| `--tag`（抹茶，屬性標籤） | `#4E7655` | `#8FBF97` |

- 字體：系統字體堆疊 `"PingFang TC", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif`，不載入 web font（中文字型檔過大）
- 店家圓點：半徑 7px 焦糖圓點加 2px 白邊；選取時半徑 10px，外圈為 `--ring` 色環（深色模式 `--primary` 與店家點同色，需另一個 token）
- 群集：深焙棕圓，依數量分三級半徑（<10、<30、≥30），中央白色數字
- 卡片：上方 16:9 照片（無照片時為 `--bg` 底加咖啡杯線稿 SVG），下方店名、評分列、屬性標籤 chips、AI 摘要（左側 `--tag` 色細線引言樣式）、備註、底部兩個等寬按鈕
- 版型：桌面左側欄 360px；手機底部抽屜有三段高度（收合只露標題列與篩選、半開 50vh、全開 90vh），以拖曳把手切換
- 文案自行撰寫，例如標題「我的咖啡地圖」、空狀態「還沒有收藏的咖啡店，回 LINE 收藏幾間吧 ☕️」

### Decision 13：分組分色、圖例與選取圖釘（依使用者回饋調整）

- 參考站的圖例是互斥的「來源圖層」；我們的四個屬性會重疊，改用「工作友善程度」組出互斥分組（規則見 spec「分組圖例」），由 `map-core.js` 的 `groupOf` 判斷，GeoJSON properties 帶 `group`，圓點以 `match` 表達式依 `--group-*` 色彩 token 上色
- 分組色：適合工作 `#3F7D5A` / `#7FBF95`、毛孩友善 `#C0612C` / `#E89565`、其他 `#8A6A4F` / `#C4A485`、尚無資料 `#9AA0A6` / `#8B9096`（淺色 / 深色）
- 選取店家改用 `maplibregl.Marker` 的 HTML 圖釘：不受群集影響、`anchor: 'bottom'` 讓針尖對準座標，並以 CSS keyframes 做落下彈跳與停留時的輕跳；`prefers-reduced-motion` 時關閉。選取中的店家從圓點圖層排除，避免圓點露在針尖下
- 選取時至少放大到 16 級，`clusterMaxZoom` 降為 14，店家不會被包在群集裡（原本 15 級時仍在群集內，造成位置看起來不準）
- 選取偏移改以地圖容器高度計算：桌面 `+28%`（上方留給 popup），手機 `-26%`（抽屜上方可見區中央）
- 桌面版 `.app` 加上 `grid-template-rows: minmax(0, 1fr)`，側欄高度固定為視窗高度，清單才會在 `panel-body` 內捲動
- 手機版標題列也可拖曳切換抽屜高度

### Decision 12：測試策略

- pytest：fingerprint、生成規則（每個 spec scenario 都有對應測試，以 `now` 注入時間）、並發（`transaction=True` 測試 + threading，驗證只生成一次）、snapshot 序列化、views（狀態碼、標頭、不洩漏資料）、LINE handler 與 quick reply
- `node --test`（Node 內建，無相依）：`map-core.js` 的篩選、GeoJSON 轉換、URL 白名單、視野計算、標籤文字。測試檔放在 `cafe/tests/js/`（不放 static，避免被 `collectstatic` 公開）。CI 以 `actions/setup-node` 固定 Node 22 執行
- 手動驗證清單：桌面 / 手機寬度、深色模式、群集展開、XSS 字串、網路錯誤重試

## Risks / Trade-offs

- [OpenFreeMap 無 SLA，可能停擺] → 底圖 style URL 集中在 `map-core.js` 常數，必要時可換 MapTiler 或 CARTO
- [unpkg CDN 中斷或被竄改] → 固定版本加上 SRI；中斷時頁面顯示錯誤狀態。之後可改為把 MapLibre 放進 static
- [token 連結外流，任何人都能看] → 使用者已接受此取捨；snapshot 不含使用者識別資料；重設連結列入第二版
- [`localhost` 連結在手機上打不開] → 開發階段以本機瀏覽器驗證，手機實測時把 `PUBLIC_BASE_URL` 設為 ngrok 等 tunnel 網址
- [snapshot 中的店家資料會過時（例如照片網址、AI 摘要）] → 依需求不因店家更新而重新生成；使用者下次收藏有變動時就會更新
- [冷卻與次數提示讓使用者困惑] → 回覆文案明確寫出剩餘分鐘數或「明天再試」，並附上既有連結
- [同步生成拖慢 webhook] → 生成只有一次 DB 查詢；日誌記錄生成耗時，超過 1 秒時發 warning，作為改成異步的依據

## Migration Plan

1. 部署 migration（新增資料表，純新增、不影響既有資料）
2. 部署 WhiteNoise 與 `collectstatic`；確認 `/static/admin/` 可以正常存取
3. 更新 nginx 設定並 reload
4. 部署 LINE 入口（quick reply）

Rollback：移除 quick reply 入口即可讓功能下線；`/map/` 路由與資料表保留不影響其他功能。需要完全移除時，再 revert migration。
