## Context

店家電話來源有兩條：Google Places `formatted_phone_number`（如 `02 2345 6789`，缺值時為 `無提供`），以及 `Cafe.phone`（建立時缺值寫入 `未提供電話`）。卡片 footer 目前在單筆時顯示「看地圖」與「網站」。

## Goals / Non-Goals

**Goals:**
- 單筆詳細卡片提供一鍵撥號
- 不合法電話不產生按鈕，避免 LINE 回傳 400 或撥出錯誤號碼

**Non-Goals:**
- 不修改 buttons template（已達 LINE 4 個 action 上限）
- 不在多筆 carousel 卡片加入按鈕（footer 空間有限）
- 不改變 body 內電話文字的顯示方式
- 不支援自動撥分機

## Decisions

### Decision 1：使用 `tel:` URI action 而非 postback

postback 需要 server 回覆訊息，無法直接開啟撥號畫面；LINE URI action 支援 `tel:` scheme，點擊即開啟撥號畫面並帶入號碼，不經過 webhook，也不佔用 API 額度。

### Decision 2：電話正規化規則

1. 非字串或空值 → 不產生
2. NFKC 正規化（全形數字轉半形）
3. 遇到分機標記（`#`、`分機`、`ext`、`轉`、`,`、`;`，不分大小寫）截斷其後內容
4. 開頭為 `+` 時保留，其餘非數字字元全部移除
5. 數字長度需介於 3 到 15（E.164 上限），否則不產生

佔位字串（`無提供`、`未提供電話`）不含數字，經規則 5 自然排除，不需維護佔位字串清單。

### Decision 3：按鈕順序

footer 依序為「看地圖」（primary）、「打電話」、「網站」。最多 3 顆；原本的「官方網站」在 3 顆按鈕並排時文字會溢出，因此改為「網站」。

## Risks / Trade-offs

- 分機被截斷：使用者需撥通後手動輸入分機，可接受。
- 長度檢查只做寬鬆驗證，無法保證號碼真實存在；號碼正確性依賴 Google 資料。
