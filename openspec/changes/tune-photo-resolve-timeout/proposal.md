## Why

`parallelize-carousel-photo-resolve` 上線後，仍觀察到部分店家偶爾顯示預設圖。目前 `resolve_photo_url` 有兩個問題：

1. `requests.head(..., timeout=2)` 的 2 秒同時套用在「建立連線」與「讀取回應」。Google Places Photo API 會經過 redirect（`maps.googleapis.com` → `lh3.googleusercontent.com`），讀取階段稍慢就會失敗。
2. Google 回應非 200（例如 403 額度/金鑰問題、400 reference 失效）時完全沒有 log，只會靜默回退預設圖，無法分辨失敗原因是逾時還是被 Google 拒絕。

## What Changes

- `resolve_photo_url` 的 timeout 由 `timeout=2` 改為 `timeout=(2, 4)`（connect 2 秒、read 4 秒）
- Google 回應非 200 時以 `logger.warning` 記錄 status code 與 `photo_reference`；不記錄含 API key 的完整 URL

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cafe-photo-loading`：新增「即時解析失敗需留下可追查紀錄」需求

## Impact

- `line_bot/builders/shop_flex_message.py`（`resolve_photo_url`）
- `line_bot/tests/builders/test_shop_flex_message.py`（`TestResolvePhotoUrl` 新增測試）
- 多筆結果已平行解析，單次 read timeout 拉長不會隨店家數量疊加；單筆結果最壞等待時間由約 2 秒變為約 6 秒以上（見 design.md）
- 不影響 `_trigger_s3_upload`、`download_and_upload_cafe_photo` Celery task
