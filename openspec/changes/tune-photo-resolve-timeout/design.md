## Context

`FlexMessageBuilder.resolve_photo_url` 以 `requests.head(photo_api_url, allow_redirects=True, ...)` 跟隨 Google Places Photo API 的 redirect，取得最終圖片 URL（`response.url`）。`response.status_code == 200` 代表 redirect 走完後最終那一站成功回應，`response.url` 即為實際圖片網址；其他情況回退 `DEFAULT_PHOTO_URL`。

多筆結果已由 `parallelize-carousel-photo-resolve` 改為 `ThreadPoolExecutor` 平行解析。

## Goals / Non-Goals

**Goals:**
- 讀取階段較慢時多給時間，連不上時仍快速失敗
- 非 200 失敗可在 log 中追查，且 log 不洩漏 API key

**Non-Goals:**
- 不設定整批平行解析的硬性總時間上限
- 不改變回退預設圖與背景 S3 快取的既有行為

## Decisions

**1. timeout 改為 `(connect=2, read=4)`**
- 理由：拆開後，連線失敗仍在 2 秒內失敗；讀取慢可多等到 4 秒。多筆結果已平行，拉長不會依店家數量線性疊加。
- 注意：`requests` 的 read timeout 是「兩次收到資料之間的最大間隔」，且每一段 redirect 各自計算，不是整個請求的總時間上限，實際單次耗時可能超過 6 秒。
- 替代方案：維持 `timeout=2` 只補 log。放棄原因：偶發讀不到照片的頻率偏高，先放寬讀取時間，再用 log 驗證成效。

**2. 非 200 記錄 warning，只含 status code 與 `photo_reference`**
- 理由：區分「逾時（RequestException，既有 log）」與「Google 拒絕（4xx/5xx，新增 log）」。
- `photo_api_url` 含 `GOOGLE_API_KEY`，不得寫入 log。

## Risks / Trade-offs

- [Trade-off] 單筆結果最壞等待時間變長（約 2 秒 → 約 6 秒以上），換取較高的照片顯示成功率。LINE reply token 有效時間足以涵蓋。
- [風險] Google 大量回應 403 時 log 量增加 → 單次搜尋最多 10 間店，量級可接受。
