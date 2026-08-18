## Context

專案已採用 SDD 工作流程（OpenSpec + `/opsx:propose` → `/opsx:apply` → `/opsx:archive`），`openspec/specs/**/spec.md` 是現行系統行為的正式規格，`openspec/changes/archive/**` 累積了每次變更當時的 proposal/design/tasks 與 delta spec，記錄決策脈絡。這兩類文件都會隨開發持續成長。

專案已在使用 `pre-commit` 框架（`.pre-commit-config.yaml`，目前跑 `trailing-whitespace`、`end-of-file-fixer`、`mixed-line-ending` 三個既有 hook），且已在本機跑一個 AnythingLLM RAG 服務（Docker container，`http://localhost:3001`，經 `docker exec` 確認其 OpenAPI 規格）。憑證 `ANYTHINGLLM_API_KEY`、`ANYTHINGLLM_BASE_URL` 已存於 `.env`／`.env.example`，兩個 workspace（`sdd-archived-decisions`、`sdd-current-specs`）已透過 `POST /v1/workspace/new` 建立完成。

實際查驗過的 AnythingLLM API 行為（見下方 Decisions）：`POST /v1/document/raw-text` 可一次完成「上傳純文字內容＋掛進指定 workspace」（`addToWorkspaces` 參數），但每次呼叫都會產生帶隨機 UUID 的全新文件，同一來源檔案重複上傳不會自動覆蓋舊版本。

## Goals / Non-Goals

**Goals:**
- Commit 完成後，若觸及 `openspec/changes/archive/**` 或 `openspec/specs/**/spec.md`，自動把變更的文件同步進對應的 RAG workspace
- 同一份來源檔案在 RAG 中僅保留最新版本，不因多次修改而累積過期副本
- 匯入流程的任何失敗都不得影響開發者的 git commit 本身
- 沿用專案既有的 `pre-commit` 框架與 Python/`uv` 工具鏈，不引入新的執行環境

**Non-Goals:**
- 不處理查詢端（MCP 整合、Claude Code skill 查詢介面），留待未來獨立 change
- 不處理多人協作情境下的觸發機制遷移（GitHub Actions、self-hosted runner），該決策留待團隊規模改變時再評估
- 不改變現有三個 `pre-commit` hook（trailing-whitespace 等）的行為
- 不對 AnythingLLM 服務本身做任何設定調整（embedding 模型、相似度門檻等維持其預設值）

## Decisions

**1. 用 `pre-commit` 框架的 `post-commit` stage，而非 GitHub Actions**
- 選擇：新增一個 local hook（`language: system`），`stages: [post-commit]`，寫進既有的 `.pre-commit-config.yaml`。
- 理由：RAG 服務只跑在使用者本機 `localhost:3001`，GitHub Actions 的 hosted runner 在雲端、無法連線到本機服務；且此需求本質是「本機開發流程的一步」，不是「不論誰在哪裡 push/PR 都要觸發」的團隊協作場景。用既有的 `pre-commit` 框架也確保不論透過哪個工具（Claude Code、其他 AI agent、手動 `git commit`）完成 commit，都會觸發，不綁定特定工具。
- 替代方案：GitHub Actions（需要 self-hosted runner 或對外曝露 RAG 服務）。放棄原因：現階段只有單人開發，多繞一層解決網路可達性問題不划算；此決策明確記錄，未來多人協作時可重新評估（見 Non-Goals）。

**1a. `post-commit` hook type 需要額外顯式安裝，不會隨 `stages: [post-commit]` 自動生效**
- 選擇：在 `.pre-commit-config.yaml` 頂層新增 `default_install_hook_types: [pre-commit, post-commit]`；並在本次任務中對目前這個 repo 實際執行一次 `pre-commit install -t post-commit`，把 `.git/hooks/post-commit` 建立出來。
- 理由：`pre-commit` 框架的 `stages: [post-commit]` 只是宣告「這個 hook 屬於哪個階段」，實際會不會在對應的 git 事件觸發，取決於 `.git/hooks/<type>` 有沒有被安裝——這是 `pre-commit install` 依 `-t/--hook-type` 參數各自獨立安裝的，預設只會裝 `pre-commit` 這個 type。查驗這個 repo 目前 `.git/hooks/` 底下確實只有 `pre-commit`、沒有 `post-commit`，代表即使加了 `stages: [post-commit]` 設定，若不額外安裝，整個匯入功能永遠不會被觸發、也不會有任何錯誤訊息（靜默失效，比報錯更難察覺）。`default_install_hook_types` 能確保之後任何人（含未來的自己在新環境）重新執行標準的 `pre-commit install` 時，會一併裝好 `post-commit`，但**既有、已經裝過 `pre-commit` hook 的 clone（包含這個 repo 現在的狀態）不會自動回溯安裝**，仍需手動跑一次 `-t post-commit`。
- 替代方案：只加 `stages: [post-commit]`，不處理安裝。放棄原因：這正是 Codex review 抓到的 P1 問題——功能設計正確但實際上永遠不會執行，且沒有任何錯誤提示會讓人發現，是最糟糕的失效模式之一。

**2. 用 `POST /v1/document/raw-text` 搭配 `addToWorkspaces`，一次完成上傳與掛載**
- 選擇：以檔案內容為 `textContent`、`metadata.title` 設為檔案的 repo 相對路徑（例如 `openspec/specs/cafe-photo-loading/spec.md`）、`addToWorkspaces` 帶入對應 workspace 的 slug。
- 理由：實際查驗 AnythingLLM 執行中容器內的 `openapi.json` 確認此 API 支援 `addToWorkspaces` 欄位，可省去「先上傳、再呼叫 `update-embeddings` 掛載」兩步驟；`metadata.title` 採用 repo 相對路徑作為穩定識別碼，確保同一來源檔案每次都能被正確查找、去重。
- 替代方案：`POST /v1/document/upload`（multipart file upload）+ `POST /v1/workspace/{slug}/update-embeddings`（兩步驟）。放棄原因：raw-text 版本已內建 `addToWorkspaces`，不需要處理檔案的 multipart 編碼與暫存，程式碼更簡單。

**3. 寫入前先查重、刪除舊版本，再寫入新版本**
- 選擇：呼叫 `GET /v1/documents` 列出所有既有文件，比對 `title` 是否等於本次要寫入檔案的 repo 相對路徑；若找到，先呼叫 `DELETE /v1/system/remove-documents`（帶入既有文件的 `name`）移除，再執行 Decision 2 的寫入。
- 理由：實測確認 AnythingLLM 每次 `raw-text` 呼叫都會建立帶隨機 UUID 的全新文件，不會自動辨識「這是同一份檔案的新版本」。若不處理，`sdd-current-specs` workspace 會隨著 spec 多次修改而累積新舊版本混雜，導致 agent 查詢時可能取得過期內容，直接違背這次變更「讓 agent 查到正確現行規格」的核心目的。
- 替代方案：不做去重，讓文件持續累加。放棄原因：對「歷史決策」workspace 或許還能接受（archive 目錄理論上不會重複修改），但對「現行規格」workspace 是不可接受的正確性問題，因此統一處理不特例。

**4. 匯入失敗（RAG 離線、API 錯誤）僅記錄，不阻斷 commit**
- 選擇：匯入腳本在 `post-commit` stage 執行，任何例外皆捕捉並記錄（例如寫入本機 log 或印出警告訊息），腳本以成功結束（exit code 0）收尾，不讓 `pre-commit` 框架視為此次 commit 失敗。
- 理由：`post-commit` 執行時 commit 已經完成，即使 hook 回報失敗也不會復原該次 commit，但若腳本用非 0 exit code 結束，會讓終端機顯示錯誤，干擾開發者對「commit 到底有沒有成功」的判斷；RAG 匯入屬於錦上添花的輔助功能，不應該讓開發者因為本機 RAG 容器剛好沒開著，就一直看到惱人的錯誤輸出。
- 替代方案：讓匯入失敗時腳本回傳非 0，讓開發者明確注意到。放棄原因：`post-commit` 語境下這個「失敗訊號」沒有實際動作可做（commit 已完成、無法重試同一個 hook 讓它變成一個「必須處理」的訊號），只會製造干擾；改用記錄檔案／日誌訊息已足夠事後追查（符合 CLAUDE.md 資料操作穩健性規範中「錯誤不可被吞掉」——這裡不是吞掉錯誤，是記錄下來但不阻斷主流程）。

**5. 用 Python 腳本（`uv run`），沿用專案既有工具鏈**
- 選擇：hook 的 `entry` 設為 `uv run python scripts/rag_ingest.py`，`language: system`，腳本用 `requests`（專案已有此依賴）呼叫 AnythingLLM API。
- 理由：專案已全面用 `uv` 管理 Python 依賴與執行，沿用一致的工具鏈，不需要另外處理 bash + curl + jq 的可攜性問題（例如 jq 是否安裝、跨平台差異）。
- 替代方案：純 shell script（`curl` + `jq`）。放棄原因：專案沒有既有的 shell 工具鏈慣例，Python 更容易撰寫、測試與維護去重邏輯（列表比對、條件判斷）。

## Risks / Trade-offs

- [風險] `post-commit` hook 若執行時間過長（例如網路延遲），會讓 `git commit` 指令的終端機停留較久 → 緩解：匯入的檔案數量通常很小（單次 commit 頂多幾份 spec 文件），且 Decision 4 已確保逾時／失敗不會讓使用者困惑；若未來實測發現延遲明顯，可考慮改為背景執行（例如 `nohup ... &`），本次先以同步執行、簡單可預期為優先。
- [風險] `title` 以 repo 相對路徑作為去重識別碼，若檔案被搬移或改名，RAG 中會留下舊路徑的殘留文件（因為新路徑會被當成「首次匯入」，不會觸發對舊路徑的移除） → 緩解：目前開發流程中 spec 檔案搬移改名的頻率低，且 `openspec/changes/archive/**` 的目錄名稱本來就是一次性建立、之後不會再變動；此為已知限制，不在本次處理範圍內，若未來出現實際困擾可另開 change 加上「清理孤兒文件」的機制。
- [Trade-off] 選擇本機 hook 而非 GitHub Actions，代表這套自動化目前只在啟用者自己的機器上生效；這是刻意的取捨，對應目前單人開發的實際情境（見 Decision 1），非疏漏。

## Migration Plan

1. 依 CLAUDE.md 的 TDD 規範，先撰寫 `scripts/rag_ingest.py` 對應的測試（例如 `scripts/tests/test_rag_ingest.py`）：
   - 給定一組 commit 變更的檔案路徑，正確判斷是否需要觸發匯入（Requirement 1）
   - 正確依路徑分流至對應 workspace slug（Requirement 2）
   - 去重邏輯：模擬 `GET /v1/documents` 回傳含有相同 `title` 的既有文件時，會先呼叫移除 API 才寫入（Requirement 3）
   - 模擬 API 呼叫拋出例外時，腳本捕捉例外、記錄、且仍以成功狀態結束（Requirement 4）
   - 上述測試皆以 mock 模擬 AnythingLLM API 呼叫，不進行真實網路連線
2. 確認新測試在無實作前為紅燈
3. 實作 `scripts/rag_ingest.py` 與 `.pre-commit-config.yaml` 的 hook 設定（含 `default_install_hook_types`，見 Decision 1a）
4. 對這個 repo 實際執行 `pre-commit install -t post-commit`，確認 `.git/hooks/post-commit` 已建立（既有的 `.git/hooks/pre-commit` 不受影響）
5. 確認測試轉綠，並手動觸發一次真實 commit（觸及 `openspec/specs/**` 或 `openspec/changes/archive/**`）驗證端到端流程確實把文件寫進對應 workspace（可用 `GET /v1/documents` 或 AnythingLLM 網頁介面確認）
6. `openspec validate add-spec-to-rag --strict` 確認 spec/proposal/design/tasks 一致

## Open Questions

- `title` 識別碼在檔案搬移/改名情境下留下孤兒文件的問題（見 Risks），是否需要之後補一個定期清理機制，留待未來視實際使用狀況決定，不影響本次的 spec、設計方向或任務拆解。
