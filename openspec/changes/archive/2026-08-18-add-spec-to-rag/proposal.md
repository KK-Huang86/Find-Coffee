## Why

專案採用 SDD（spec-driven development）開發，`openspec/specs/` 與 `openspec/changes/archive/` 下的文件會隨開發持續累積。要求每個 AI agent 每次工作前都逐一讀取所有相關 spec 文件，效率低且容易漏讀。本機已有一個 AnythingLLM RAG 服務（`localhost:3001`），可以把這些文件匯入其中，讓 agent 改用查詢方式取得「現行規格」與「歷史決策脈絡」，取代逐檔閱讀。

## What Changes

- 新增本機 `pre-commit` 框架的 `post-commit` stage hook：commit 完成後檢查該次 commit 是否觸及 `openspec/changes/archive/**` 或 `openspec/specs/**/spec.md`，有則觸發匯入
- 匯入目標為 AnythingLLM 的兩個既有 workspace（皆已建立）：
  - `sdd-archived-decisions`：`openspec/changes/archive/**` 下的封存文件（proposal/design/tasks/delta specs），作為歷史決策脈絡
  - `sdd-current-specs`：`openspec/specs/**/spec.md` 下的正式生效規格，作為現行系統行為的唯一真相來源
- 寫入前先查詢是否已有相同 `title`（以 repo 相對路徑作為穩定識別碼）的舊文件，若有則先刪除，避免重複或過期版本殘留於 RAG 中
- 憑證（`ANYTHINGLLM_API_KEY`、`ANYTHINGLLM_BASE_URL`）已存於 `.env`／`.env.example`，本次不重複處理
- 不含查詢端（MCP／Claude Code skill 整合），本次僅涵蓋文件匯入這一端

## Capabilities

### New Capabilities
- `sdd-rag-ingestion`：定義 SDD 文件（已封存 change 與現行 spec）在符合條件的 commit 後，自動同步至本機 RAG 服務的行為，包含匯入範圍、去重規則與失敗處理

### Modified Capabilities
（無）

## Impact

- **受影響程式碼**：
  - 新增 `.pre-commit-config.yaml` 的 hook 設定（`post-commit` stage）
  - 新增匯入腳本（例如 `scripts/rag_ingest.py`），呼叫 AnythingLLM REST API（`/v1/document/raw-text`、`/v1/documents`、`/v1/system/remove-documents`）
  - 新增對應測試（腳本邏輯，例如檔案偵測、去重判斷；不含真實呼叫外部 API 的整合測試）
- **不受影響**：Find Coffee 應用程式本身的任何執行期程式碼、既有 `pre-commit` hook（trailing-whitespace 等 3 個既有 hook 維持不變）
- **外部依賴**：本機執行的 AnythingLLM Docker container（`localhost:3001`），此依賴僅存在於開發流程，不影響應用程式部署或執行期行為
- **範圍邊界**：僅處理「寫入 RAG」，不處理「AI agent 如何查詢 RAG」（例如 MCP 整合），該部分留待未來獨立的 change 處理
