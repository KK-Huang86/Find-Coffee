## ADDED Requirements

### Requirement: AI 摘要同時供搜尋比對與使用者閱讀
系統 SHALL 每間咖啡店只維護一份 AI 文字（`ai_summary`），產生時的 prompt MUST 涵蓋氛圍、適合族群、環境特色、是否適合工作或讀書與推薦商品，長度 150 字以內。系統 MUST NOT 為使用者查看另外呼叫 AI 服務產生第二份評價。

#### Scenario: 產生摘要的 prompt 內容
- **WHEN** 系統呼叫 AI 服務產生 `ai_summary`
- **THEN** prompt 要求涵蓋氛圍、適合族群、環境特色、是否適合工作或讀書、推薦商品，且限制 150 字以內

### Requirement: 使用者查看 AI 評價時優先使用已存摘要
使用者點擊「看看AI怎麼說」時，系統 SHALL 先讀取該店 `ai_summary`；已有摘要時 MUST 直接回覆，不呼叫 AI 服務、不消耗使用者 AI 額度。

#### Scenario: 已有摘要
- **WHEN** 使用者點擊 AI 評價，且該店 `ai_summary` 非空
- **THEN** 系統回覆該摘要，不呼叫 AI 服務、不消耗額度

#### Scenario: 重複點擊
- **WHEN** 使用者第一次點擊時摘要已當場產生並寫入，之後再次點擊
- **THEN** 第二次點擊不呼叫 AI 服務

### Requirement: 使用者查看時摘要為空需當場產生並存入
該店 `ai_summary` 為空值或空字串時，系統 SHALL 佔用點擊使用者的 AI 額度、呼叫 AI 服務產生摘要，並且 MUST 只在 `ai_summary` 仍為空時寫入 DB。

#### Scenario: 當場產生成功
- **WHEN** 使用者點擊 AI 評價，該店 `ai_summary` 為空且有評論，使用者額度足夠
- **THEN** 系統呼叫 AI 服務一次，將結果寫入 `ai_summary` 並回覆

#### Scenario: 產生期間背景任務已寫入
- **WHEN** 使用者等待 AI 服務回應期間，背景任務已先寫入 `ai_summary`
- **THEN** 系統不覆蓋 DB 內容，回覆 DB 中的摘要

#### Scenario: 店家沒有評論
- **WHEN** 使用者點擊 AI 評價，該店 `ai_summary` 為空且 `reviews` 為空
- **THEN** 系統回覆評論不足，不呼叫 AI 服務、不消耗額度

#### Scenario: 使用者額度用盡
- **WHEN** 使用者點擊 AI 評價，該店 `ai_summary` 為空，但使用者本月 AI 額度已達上限
- **THEN** 系統回覆額度已達上限，不呼叫 AI 服務

#### Scenario: AI 服務失敗
- **WHEN** 當場產生時 AI 服務回傳空結果或發生例外
- **THEN** 系統回復使用者額度，`ai_summary` 維持原值，並回覆暫時無法使用
