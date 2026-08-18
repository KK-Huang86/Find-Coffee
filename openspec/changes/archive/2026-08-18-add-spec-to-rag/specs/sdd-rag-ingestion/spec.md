## Purpose

定義 SDD（spec-driven development）文件在符合條件的本機 commit 後，自動同步至本機 RAG 服務的行為，讓 AI agent 能透過查詢取得現行規格與歷史決策脈絡，取代逐檔閱讀所有 spec 文件。

## ADDED Requirements

### Requirement: 依 commit 內容判斷是否觸發匯入
系統 SHALL 在每次 commit 完成後檢查該次 commit 變更的檔案路徑，僅當變更觸及 `openspec/changes/archive/**` 或 `openspec/specs/**/spec.md` 時才觸發匯入流程；未觸及這些路徑的 commit SHALL NOT 觸發任何匯入行為。

#### Scenario: commit 觸及已封存 change 文件
- **WHEN** 一次 commit 的變更檔案包含 `openspec/changes/archive/**` 底下的檔案
- **THEN** 系統觸發匯入流程

#### Scenario: commit 觸及現行 spec 文件
- **WHEN** 一次 commit 的變更檔案包含 `openspec/specs/**/spec.md`
- **THEN** 系統觸發匯入流程

#### Scenario: commit 未觸及任何相關路徑
- **WHEN** 一次 commit 的變更檔案不包含上述任一路徑（例如僅修改應用程式原始碼）
- **THEN** 系統不觸發匯入流程，也不對外發出任何 RAG 相關的網路請求

### Requirement: 匯入內容依來源路徑分流至對應 RAG workspace
系統 SHALL 將 `openspec/changes/archive/**` 底下的文件匯入至歷史決策用途的 workspace，並將 `openspec/specs/**/spec.md` 底下的文件匯入至現行規格用途的 workspace，兩者 SHALL NOT 混合存放。

#### Scenario: 封存文件匯入歷史決策 workspace
- **WHEN** 一份變更的文件位於 `openspec/changes/archive/**`
- **THEN** 該文件被匯入至歷史決策用途的 workspace

#### Scenario: 現行規格文件匯入現行規格 workspace
- **WHEN** 一份變更的文件位於 `openspec/specs/**/spec.md`
- **THEN** 該文件被匯入至現行規格用途的 workspace

### Requirement: 匯入前需避免重複或過期版本殘留
系統 SHALL 以檔案的 repo 相對路徑作為穩定識別碼，於匯入新版本前檢查 RAG 服務中是否已存在相同識別碼的文件；若存在，SHALL 先移除舊版本再寫入新版本，確保同一份來源檔案在 RAG 中僅有一份最新版本。

#### Scenario: 檔案首次匯入
- **WHEN** 一份文件的識別碼在 RAG 服務中尚無對應的既有文件
- **THEN** 系統直接寫入新文件，不需要先執行移除動作

#### Scenario: 檔案已有舊版本
- **WHEN** 一份文件的識別碼在 RAG 服務中已存在對應的既有文件
- **THEN** 系統先移除該既有文件，再寫入新版本，使該識別碼在 RAG 中僅保留最新內容

### Requirement: RAG 服務無法連線或匯入失敗不得阻斷 commit
系統 SHALL 將匯入流程設計為不影響 commit 本身是否成功；當 RAG 服務無法連線或匯入過程發生錯誤時，系統 SHALL 記錄失敗原因，SHALL NOT 造成 commit 失敗或需要開發者重試 commit。

#### Scenario: RAG 服務離線
- **WHEN** 觸發匯入時，本機 RAG 服務無法連線
- **THEN** 系統記錄此次失敗，commit 本身仍視為成功完成

#### Scenario: 匯入過程中 API 回傳錯誤
- **WHEN** 觸發匯入時，RAG 服務的 API 呼叫回傳非預期的錯誤狀態
- **THEN** 系統記錄此次失敗與錯誤內容，commit 本身仍視為成功完成
