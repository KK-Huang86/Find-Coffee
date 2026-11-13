## Purpose

定義個人咖啡地圖前端頁面的呈現方式，包含地圖標示、店家清單與卡片、屬性篩選、響應式版型、深色模式與安全標頭。

## ADDED Requirements

### Requirement: 地圖頁面殼
系統 SHALL 提供 `GET /map/<token>/` 回傳地圖頁面 HTML。頁面殼 MUST NOT 內嵌任何使用者或店家資料，店家資料 MUST 由頁面向資料端點取得。token 不存在或格式不符時 MUST 回傳 404。回應 MUST 帶 `X-Robots-Tag: noindex`、`Referrer-Policy: strict-origin`，HTML MUST 包含 `<meta name="robots" content="noindex">`。

#### Scenario: 有效 token
- **WHEN** 以有效 token 開啟地圖頁
- **THEN** 回傳 200 HTML，且 HTML 不含任何店名

#### Scenario: 無效 token
- **WHEN** 以不存在的 token 開啟地圖頁
- **THEN** 回傳 404

### Requirement: 地圖標示
頁面 SHALL 將每間店家以圓點標示於地圖，圓點顏色 MUST 對應該店的分組（見「分組圖例」）。相近店家 MUST 合併為顯示數量的群集；點選群集 MUST 放大至群集展開的縮放層級。初次載入 MUST 將視野縮放至涵蓋全部店家；只有一間店時 MUST 以該店為中心。沒有店家時 MUST 以台北市為預設視野。

#### Scenario: 多間店家
- **WHEN** snapshot 有 3 間分散的店家
- **THEN** 地圖視野涵蓋全部 3 間

#### Scenario: 點選群集
- **WHEN** 使用者點選顯示數字的群集
- **THEN** 地圖放大並展開該群集

#### Scenario: 選取店家
- **WHEN** 使用者點選地圖上的店家圓點或清單項目
- **THEN** 地圖移動並放大至該店不會被群集包住的層級，以圖釘標示該店，圖釘針尖對準店家座標，並顯示店家卡片

#### Scenario: 選取動畫
- **WHEN** 店家被選取
- **THEN** 圖釘以落下彈跳的動畫出現，之後持續輕微跳動；系統設定「減少動態效果」時不播放動畫

#### Scenario: 選取位置不被遮住
- **WHEN** 在手機版選取店家，底部抽屜展開
- **THEN** 圖釘位於抽屜上方的可見地圖區域內

### Requirement: 店家清單
頁面 SHALL 顯示目前篩選條件下的店家清單與數量，清單順序與 snapshot 相同，每個項目 MUST 以該店分組的顏色標示，並 MUST 顯示店家照片縮圖；照片網址缺值、不是 http(s) 或載入失敗時 MUST 顯示預設圖樣。清單超出可視高度時 MUST 可在清單區域內捲動到最後一間。

#### Scenario: 顯示數量
- **WHEN** 篩選後剩 4 間店家
- **THEN** 清單顯示 4 間與數量「4」

#### Scenario: 清單縮圖
- **WHEN** 店家照片網址為 `https://` 開頭
- **THEN** 清單項目顯示該照片縮圖

#### Scenario: 清單縮圖缺值
- **WHEN** 店家照片網址為 `null` 或 `javascript:` 開頭
- **THEN** 清單項目顯示預設圖樣

#### Scenario: 長清單捲動
- **WHEN** 店家數量超出側欄或抽屜的可視高度
- **THEN** 使用者可以在清單區域內捲動至最後一間

### Requirement: 店家卡片
店家卡片 SHALL 顯示照片、店名、Google 評分與評論數、地址、屬性標籤、AI 摘要、個人備註，以及「Google Maps」與「打電話」動作。缺值欄位 MUST 優雅降級：無照片顯示預設圖樣；無評分、AI 摘要或備註時隱藏該區塊；無電話時隱藏「打電話」；屬性為未知時不顯示該標籤。

#### Scenario: 完整資料
- **WHEN** 店家具備所有欄位
- **THEN** 卡片顯示全部區塊與兩個動作

#### Scenario: 缺少照片與摘要
- **WHEN** 店家照片網址與 AI 摘要為 `null`
- **THEN** 卡片顯示預設圖樣且不顯示 AI 摘要區塊

#### Scenario: 無電話
- **WHEN** 店家電話為 `null` 或不含可撥號數字
- **THEN** 卡片不顯示「打電話」

### Requirement: 分組圖例
頁面 SHALL 在地圖上提供分組圖例，依下列順序將每間店歸入唯一一組，並以不同顏色區分：

1. 適合工作：插座為很多或視座位，且限時為一律不限時或視情況
2. 毛孩友善：寵物友善為歡迎，或店內有貓狗為有
3. 尚無資料：四個屬性皆缺值
4. 其他：其餘店家

圖例 MUST 顯示各組顏色與數量，以及目前地圖上的店家數。點選某組 MUST 切換該組在地圖與清單中的顯示；隱藏的分組 MUST 與屬性篩選同時套用。桌面版圖例預設展開，手機版預設收合。

#### Scenario: 歸組優先順序
- **WHEN** 店家同時符合適合工作與毛孩友善
- **THEN** 該店歸為適合工作

#### Scenario: 隱藏分組
- **WHEN** 使用者點選圖例中的「其他」
- **THEN** 地圖與清單不再顯示「其他」組的店家，圖例中該組呈現未選取樣式，「地圖上 N 間」同步更新

#### Scenario: 清除篩選
- **WHEN** 隱藏分組或屬性篩選導致沒有符合的店家，使用者點選清除篩選
- **THEN** 屬性篩選與隱藏分組都被清除

### Requirement: 屬性篩選
頁面 SHALL 提供四個可切換的篩選條件，每個條件 MUST 顯示圖示與全部店家中符合的數量：「有插座」（插座為很多或視座位）、「不限時」（限時為一律不限時或視情況）、「寵物友善」（寵物友善為歡迎）、「店內有貓狗」（店內有貓狗為有）。多個條件 MUST 以 AND 組合；屬性缺值的店家 MUST 視為不符合該條件。地圖標示與清單 MUST 同步反映篩選結果。沒有店家符合時 MUST 顯示無符合結果的提示與清除篩選動作。

#### Scenario: 單一條件
- **WHEN** 使用者開啟「有插座」
- **THEN** 只顯示插座為很多或視座位的店家

#### Scenario: 多個條件
- **WHEN** 使用者同時開啟「有插座」與「不限時」
- **THEN** 只顯示同時符合兩個條件的店家

#### Scenario: 屬性缺值
- **WHEN** 店家插座屬性為 `null` 且使用者開啟「有插座」
- **THEN** 該店家不顯示

#### Scenario: 無符合結果
- **WHEN** 篩選後沒有任何店家
- **THEN** 顯示無符合結果提示與清除篩選動作

### Requirement: 響應式版型
視窗寬度 768px 以上時，頁面 SHALL 以左側欄顯示篩選與店家清單、右側顯示地圖，店家卡片以地圖 popup 呈現。寬度小於 768px 時，地圖 MUST 佔滿畫面，篩選與店家清單 MUST 置於可上拉的底部抽屜，店家卡片 MUST 於抽屜中呈現。頁面 MUST NOT 產生水平捲動。

#### Scenario: 桌面版
- **WHEN** 視窗寬度為 1280px
- **THEN** 顯示左側欄與地圖

#### Scenario: 手機版
- **WHEN** 視窗寬度為 375px
- **THEN** 地圖佔滿畫面，清單位於底部抽屜，且無水平捲動

### Requirement: 深色模式
頁面 SHALL 依系統偏好預設深色或淺色主題，並提供手動切換；手動選擇 MUST 在同一瀏覽器下次開啟時保留。瀏覽器儲存不可用時 MUST 仍能正常顯示並使用系統偏好。底圖 MUST 隨主題切換為對應的深色或淺色樣式。

#### Scenario: 系統為深色
- **WHEN** 系統偏好為深色且未手動選擇
- **THEN** 頁面與底圖為深色

#### Scenario: 儲存不可用
- **WHEN** 瀏覽器封鎖本機儲存
- **THEN** 頁面正常顯示並套用系統偏好

### Requirement: 載入與錯誤狀態
頁面 SHALL 於資料載入中顯示載入狀態；資料端點回傳錯誤或網路失敗時 MUST 顯示可重試的錯誤訊息；snapshot 店家清單為空時 MUST 顯示尚無收藏的空狀態。

#### Scenario: 資料端點失敗
- **WHEN** 資料端點回傳 500 或網路中斷
- **THEN** 顯示錯誤訊息與重試動作

#### Scenario: 空收藏
- **WHEN** snapshot 店家清單為空
- **THEN** 顯示尚無收藏的空狀態

### Requirement: 輸出安全
頁面 MUST 將所有店家文字欄位（店名、地址、AI 摘要、備註等）以純文字呈現，MUST NOT 將其解析為 HTML。外部連結 MUST 僅允許 `http`、`https`（Google Maps、網站、照片）與 `tel`（電話）scheme，其他 scheme MUST 不產生連結。外部連結 MUST 帶 `rel="noopener noreferrer"`。

#### Scenario: 店名含 HTML
- **WHEN** 店名為 `<img src=x onerror=alert(1)>`
- **THEN** 頁面以文字顯示該字串，不執行任何腳本

#### Scenario: 不安全的連結 scheme
- **WHEN** 店家網站為 `javascript:alert(1)`
- **THEN** 卡片不產生網站連結

### Requirement: 視覺識別
頁面的配色、字體、圖示、元件外觀與文案 SHALL 為本專案自行設計，MUST NOT 沿用 coffee.aaron-shih.com 的色碼、logo、圖示或文案。

#### Scenario: 色碼檢查
- **WHEN** 檢視頁面樣式的色彩 token
- **THEN** 不包含 `#A8263A`、`#F4F1EC`、`#E25A6E`、`#161311`
