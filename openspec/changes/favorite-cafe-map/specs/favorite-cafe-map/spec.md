## Purpose

依使用者的收藏產生個人咖啡地圖 snapshot，以不可猜的 token 網址公開存取，並以冷卻時間與每日次數上限控制重新生成頻率。

## ADDED Requirements

### Requirement: 地圖存取 token
系統 SHALL 為每位使用者至多建立一份個人地圖，並配發一組不可猜的存取 token。token MUST 由密碼學安全亂數產生、長度至少 32 字元、全系統唯一，且 MUST NOT 包含或可推導出 LINE user ID。同一使用者重複取得地圖時 token MUST 維持不變。

#### Scenario: 首次建立地圖
- **WHEN** 從未建立地圖的使用者點選「我的咖啡地圖」且至少有一筆收藏
- **THEN** 系統建立該使用者的地圖並配發新 token

#### Scenario: token 不含 LINE user ID
- **WHEN** 系統為 LINE user ID 為 `U1234567890abcdef` 的使用者配發 token
- **THEN** token 不包含 `U1234567890abcdef` 的任何子字串長度 8 以上的片段

#### Scenario: 再次取得地圖 token 不變
- **WHEN** 已有地圖的使用者再次點選「我的咖啡地圖」
- **THEN** 回傳的連結 token 與先前相同

### Requirement: 地圖連結格式
地圖連結 SHALL 為 `<PUBLIC_BASE_URL>/map/<token>/`。`PUBLIC_BASE_URL` 未設定時 MUST 預設為 `http://localhost:8000`，且結尾斜線 MUST 被正規化，不產生雙斜線。

#### Scenario: 使用預設網域
- **WHEN** `PUBLIC_BASE_URL` 未設定
- **THEN** 連結為 `http://localhost:8000/map/<token>/`

#### Scenario: 設定值帶結尾斜線
- **WHEN** `PUBLIC_BASE_URL` 為 `https://example.com/`
- **THEN** 連結為 `https://example.com/map/<token>/`

### Requirement: 收藏變動判斷
系統 SHALL 以使用者目前收藏的咖啡店集合計算 fingerprint，並與上次生成時的 fingerprint 比對以判斷收藏是否變動。fingerprint MUST 與收藏順序無關，且 MUST 只依收藏集合決定；咖啡店本身資料（AI 摘要、照片、屬性、評分）更新 MUST NOT 改變 fingerprint。

#### Scenario: 收藏未變動
- **WHEN** 使用者收藏集合與上次生成時相同
- **THEN** 系統判定未變動

#### Scenario: 新增或移除收藏
- **WHEN** 使用者在上次生成後新增或移除任一收藏
- **THEN** 系統判定有變動

#### Scenario: 移除後再加回同一間
- **WHEN** 使用者移除一間收藏後又加回，收藏集合與上次生成時相同
- **THEN** 系統判定未變動

#### Scenario: 店家資料更新
- **WHEN** 收藏集合不變，但其中一間咖啡店的 AI 摘要被更新
- **THEN** 系統判定未變動

### Requirement: 地圖生成規則
使用者點選「我的咖啡地圖」時，系統 SHALL 依下列順序決定結果並以單一回覆訊息回應：

1. 使用者沒有任何收藏且尚未建立地圖：回覆尚無收藏提示，不建立地圖
2. 尚未建立地圖：生成地圖，計入當日次數
3. 收藏未變動：回傳既有連結，不生成、不計次
4. 收藏有變動且當日已生成 5 次：回傳既有連結，並提示當日更新次數已用完（不論是否仍在冷卻中，避免使用者等完冷卻才得知次數用完）
5. 收藏有變動、當日未滿 5 次且距上次生成未滿 30 分鐘：回傳既有連結，並提示剩餘等待分鐘數（無條件進位）
6. 收藏有變動、當日未滿 5 次且已滿 30 分鐘：生成新版，計入當日次數

「當日」MUST 以 Asia/Taipei 時區 00:00 為界。每日次數 MUST 於跨日後重新計算。

#### Scenario: 無收藏且無地圖
- **WHEN** 沒有收藏、也沒有地圖的使用者點選「我的咖啡地圖」
- **THEN** 回覆尚無收藏的提示，且不建立地圖

#### Scenario: 已有地圖但收藏全部移除
- **WHEN** 已有地圖的使用者移除所有收藏，冷卻已過且當日未達上限
- **THEN** 系統生成不含任何店家的新版地圖並回傳連結

#### Scenario: 收藏未變動不計次
- **WHEN** 收藏未變動的使用者在同一天點選 10 次「我的咖啡地圖」
- **THEN** 每次都回傳既有連結，當日次數不增加

#### Scenario: 冷卻中
- **WHEN** 使用者於 10:00 生成地圖，10:12 新增收藏後點選「我的咖啡地圖」
- **THEN** 回傳既有連結並提示約 18 分鐘後可更新，地圖內容不變

#### Scenario: 冷卻剩餘不足一分鐘
- **WHEN** 距上次生成 29 分 30 秒且收藏有變動
- **THEN** 提示約 1 分鐘後可更新

#### Scenario: 冷卻剛好屆滿
- **WHEN** 距上次生成恰好 30 分鐘且收藏有變動、當日未達上限
- **THEN** 系統生成新版

#### Scenario: 當日達上限
- **WHEN** 使用者當日已生成 5 次，冷卻已過且收藏有變動
- **THEN** 回傳既有連結並提示當日更新次數已用完，地圖內容不變

#### Scenario: 達上限時優先於冷卻
- **WHEN** 使用者當日已生成 5 次，最後一次在 10 分鐘前，且收藏有變動
- **THEN** 提示當日更新次數已用完，不提示等待分鐘數

#### Scenario: 跨日重置
- **WHEN** 使用者於 Asia/Taipei 23:50 已生成第 5 次，隔日 00:30 收藏有變動後點選
- **THEN** 系統生成新版，當日次數為 1

#### Scenario: UTC 與台北日期不同
- **WHEN** 使用者於 Asia/Taipei 07:00（UTC 前一日 23:00）點選，且前一次生成為 Asia/Taipei 前一日
- **THEN** 當日次數依 Asia/Taipei 日期重新計算

### Requirement: 並發生成防護
同一使用者同時送出多次「我的咖啡地圖」請求時，系統 MUST 確保至多生成一次、當日次數至多增加一次，且所有請求回傳相同 token。

#### Scenario: 連點兩次
- **WHEN** 同一使用者在收藏有變動、冷卻已過的狀態下幾乎同時送出兩次請求
- **THEN** 只生成一次，當日次數只增加 1

#### Scenario: 連續被搶先寫入
- **WHEN** 生成過程中連續兩次被其他請求搶先寫入，且收藏仍與地圖內容不同
- **THEN** 回覆稍後再試，不回報為收藏未變動

#### Scenario: 首次建立的並發
- **WHEN** 從未建立地圖的使用者幾乎同時送出兩次請求
- **THEN** 只建立一份地圖、只配發一組 token

### Requirement: 生成失敗不留半成品
地圖生成過程中任一步驟失敗時，系統 MUST 保留上一版 snapshot、fingerprint、生成時間與當日次數不變，MUST 記錄錯誤 log，並回覆使用者稍後再試的訊息。

#### Scenario: 生成時發生錯誤
- **WHEN** 生成 snapshot 時發生例外
- **THEN** 地圖維持上一版內容，當日次數不增加，並回覆稍後再試

### Requirement: snapshot 內容
snapshot SHALL 包含格式版本、生成時間（ISO 8601，含時區）與店家清單。每間店家 MUST 包含：Google Place ID、店名、地址、緯度、經度、Google 評分、評論數、電話、可撥號的 `tel:` URI（電話無法正規化時為 `null`）、Google Maps 連結、網站、照片網址、AI 摘要、屬性（插座、限時、寵物友善、店內有貓狗）、個人備註與收藏時間。缺值欄位 MUST 輸出為 `null`。緯度或經度缺值的店家 MUST 被排除。店家清單 MUST 依收藏時間由新到舊排序。snapshot MUST NOT 包含 LINE user ID、使用者暱稱或其他使用者識別資料。

#### Scenario: 缺少座標的店家
- **WHEN** 收藏中有一間咖啡店緯度為空
- **THEN** snapshot 店家清單不包含該店

#### Scenario: 缺少 AI 摘要與照片
- **WHEN** 收藏的咖啡店沒有 AI 摘要且沒有照片
- **THEN** 該店的 AI 摘要與照片網址為 `null`

#### Scenario: 備註保留
- **WHEN** 收藏未填寫備註
- **THEN** 該店的備註為 `null`

#### Scenario: 不含使用者識別資料
- **WHEN** 產生任一 snapshot
- **THEN** 內容不包含 LINE user ID 與使用者暱稱

### Requirement: 地圖資料端點
系統 SHALL 提供 `GET /map/<token>/data.json` 回傳該 token 的 snapshot（`application/json`），不需登入。token 不存在或格式不符時 MUST 回傳 404，且回應內容 MUST NOT 區分「格式錯誤」與「不存在」。非 GET/HEAD 方法 MUST 回傳 405。回應 MUST 帶 `X-Robots-Tag: noindex` 與 `Referrer-Policy: strict-origin`。

#### Scenario: 有效 token
- **WHEN** 以有效 token 請求資料端點
- **THEN** 回傳 200 與 snapshot JSON

#### Scenario: 不存在的 token
- **WHEN** 以格式正確但不存在的 token 請求
- **THEN** 回傳 404

#### Scenario: 格式錯誤的 token
- **WHEN** 以含非法字元或過長的 token 請求
- **THEN** 回傳與不存在 token 相同的 404

#### Scenario: 非 GET 方法
- **WHEN** 以 POST 請求資料端點
- **THEN** 回傳 405

### Requirement: LINE 入口
「更多資訊」選單的 quick reply 與「收藏的咖啡店」回覆 SHALL 提供「🗺️ 我的咖啡地圖」選項。地圖連結回覆 MUST 使用 reply token 回覆，MUST NOT 使用 push message。

#### Scenario: 從更多資訊進入
- **WHEN** 使用者點選「更多資訊」
- **THEN** quick reply 包含「🗺️ 我的咖啡地圖」

#### Scenario: 從收藏清單進入
- **WHEN** 有收藏的使用者點選「收藏的咖啡店」
- **THEN** 回覆的 quick reply 包含「🗺️ 我的咖啡地圖」

#### Scenario: 收藏清單有下一頁
- **WHEN** 收藏清單超過一頁
- **THEN** quick reply 同時包含「➡️ 下一頁」與「🗺️ 我的咖啡地圖」
