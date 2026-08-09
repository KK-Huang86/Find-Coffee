# Find Coffee - LINE Bot 咖啡店搜尋服務

## 專案概述

Find Coffee 是以 Django 建置的 LINE Bot 咖啡店搜尋服務，主要服務範圍為台灣。支援店名、地址、行政區與使用者位置搜尋，並提供收藏、投票式咖啡店屬性、搜尋歷史、好友與 AI 店家評論等功能。

## 技術棧

- **後端**: Django 6.0 + Python >= 3.13
- **Web 服務**: Gunicorn + Nginx
- **資料庫**: PostgreSQL 16，透過 PgBouncer transaction pooling 連線
- **Cache / Lock / State**: Redis
- **異步任務**: Celery（開發環境使用 Redis broker，生產環境使用 AWS SQS）
- **LINE Bot**: line-bot-sdk v3（Messaging API）
- **外部整合**: Google Places API、Groq API
- **圖片儲存**: AWS S3 + CloudFront
- **容器化**: Docker Compose
- **IaC**: Terraform
- **套件管理**: uv
- **測試與品質**: pytest、pytest-django、Factory Boy、Ruff、pre-commit
- **Spec 工作流**: OpenSpec + Spectra

## 專案結構

```
├── core/               # Django settings、Celery、health checks 與 URL routing
├── cafe/               # 咖啡店、收藏、屬性投票、CafeNomad 快取與 Celery tasks
│   ├── management/    # CafeNomad / Google 資料匯入指令
│   ├── services/      # 屬性匹配與投票業務邏輯
│   └── tests/
├── line_bot/            # LINE webhook 與對話核心邏輯
│   ├── builders/      # Flex Message / Quick Reply builders
│   ├── handlers/      # Postback action handlers
│   ├── services/      # 搜尋歷史等服務
│   ├── event_handlers.py
│   ├── state.py       # Redis-backed 對話狀態
│   └── tests/
├── users/              # LINE 使用者與好友關係
├── integrations/       # Google Places、Groq 與 API 用量管理
├── utils/              # Redis lock 等共用工具
├── nginx/              # Nginx reverse proxy 設定
├── terraform/          # S3、CloudFront 與 IAM 等 AWS 資源
├── openspec/           # 規格、change proposal、design 與 tasks
├── docker-compose.yml  # web、celery、nginx、PostgreSQL、PgBouncer、Redis
└── pyproject.toml      # Python dependencies 與工具設定
```

## 重要 Models

- `Cafe`: Google Places 咖啡店主資料、照片與評論
- `Favorite`: 使用者與咖啡店的收藏關係
- `CafeAttributeVote`: 使用者對插座、限時、寵物等屬性的投票
- `CafeNomadCache`: CafeNomad 屬性快取
- `User`: LINE 使用者及其 API 用量紀錄關聯
- `Friendship`: 使用者好友關係
- `ApiUsageRecord`: Google Places 與 AI API 月度用量計數

## Celery Tasks（`cafe/tasks.py`）

- `download_and_upload_cafe_photo`: 下載 Google 照片 → 上傳 S3
- `refresh_cafe_data`: 重新向 Google Places 取得咖啡店資料；店家資料過期 30 天、照片過期 180 天時觸發更新流程

## LINE Bot 架構

- **Webhook**: `/callback/`，由 `line_bot/views.py` 驗證 LINE signature 後 dispatch event
- **Rich Menu**: 6 格選單，設定邏輯位於 `line_bot/views.py`
- **State 管理**: `StateManager` + `UserState` 控制對話流程
- **Postback 路由**: `ACTION_HANDLERS` dispatch table
- **並發防護**: Redis lock 防止同一使用者重複處理請求

## 開發指令

```bash
# 安裝或同步依賴
uv sync --group dev

# 啟動 Django 開發伺服器
uv run python manage.py runserver

# 啟動完整容器化環境
docker compose up --build

# 測試與 coverage
uv run pytest -q
uv run pytest --cov --cov-report=term-missing

# 靜態檢查
uv run ruff check .

# Django 檢查與 migration
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run

# OpenSpec change 驗證
openspec validate <change-name> --strict

# Terraform
terraform -chdir=terraform fmt -check
terraform -chdir=terraform validate
terraform -chdir=terraform plan
```

## 注意事項

- Commit 訊息使用繁體中文。
- 圖片存放於 S3，透過 CloudFront 存取。
- 環境變數放在 `.env`；不得 commit secrets，新增變數時同步更新 `.env.example`。
- 生產環境 Celery broker 為 SQS；不要假設 Redis 在所有環境都是 broker。
- PostgreSQL 連線經 PgBouncer transaction pooling；`CONN_MAX_AGE` 需維持 `0`，`DISABLE_SERVER_SIDE_CURSORS` 需維持 `True`。
- 測試使用 `core.test_settings`，外部 API、Redis、Celery broker、S3 不應在 unit test 中真實呼叫。

# TDD 開發規範（專案固定規則）

任何實作階段（尤其 `/spectra-apply` 或直接寫程式碼）都必須遵守：

1. **先寫測試，後寫程式碼**：在生成/修改任何實作程式碼之前，必須先為該功能撰寫對應的 unit test。若某個任務沒有對應的 unit test，禁止生成該任務的實作程式碼。
2. **邊界案例優先**：撰寫 unit test 時，除了基本 happy path，必須額外涵蓋邊界情況（空值、極端值、錯誤輸入、併發/重複呼叫等），確保測試案例能反映真實使用情境與潛在風險。
3. **分階段驗證**：每個開發階段完成後都要驗證再往下走，而不是一次做完才驗證，包含（但不限於）：
   - 測試案例本身是否合理覆蓋需求與邊界情況
   - 新寫的測試在無實作前應為紅燈（fail）
   - 實作完成後測試需全部通過（green）
   - 通過後再視情況重構（refactor），且重構後測試仍需全綠
4. **測試全過才能生成/合併程式碼**：只有當對應的 unit test（含邊界案例）全部撰寫完成且驗證通過後，才可以生成或提交最終的實作程式碼。
5. **測試不可為了遷就程式碼而修改**：unit test 撰寫完成後，除非商業邏輯（需求本身）有變更，否則不可以因為程式碼實作結果、或是為了讓測試通過，而回頭修改測試內容（例如放寬斷言、刪除邊界案例、改動期望值以符合實作輸出）。測試失敗時，預設應該修的是程式碼，而不是測試；只有在確認是商業邏輯變更時，才能連動修改測試，且需同步說明變更原因。

# 資料操作穩健性規範（專案固定規則）

涉及資料寫入/狀態變更的開發，必須考慮以下事項：

1. **重視邊界情況**：實作前先想清楚輸入的邊界（空值、極端值、型別錯誤、超量資料等），並反映在程式邏輯與測試中。
2. **原子性操作**：提交相關聯的多筆資料變更時，要嘛全部成功、要嘛全部不生效，不可只完成一半。單一資料庫內優先用 transaction；跨系統/跨服務無法用單一 transaction 涵蓋時，需設計補償機制（compensating action / saga），不能假裝有原子性。
3. **失敗時要能 rollback**：任何寫入流程都要事先設計失敗後的回復路徑，不能只處理成功路徑（happy path）。
4. **冪等性（Idempotency）**：同一操作重複執行（重試、重複請求）結果需與只執行一次相同，避免重複扣款、重複寫入等副作用，這點在搭配 retry/rollback 機制時尤其重要。
5. **錯誤不可被吞掉**：例外必須明確拋出或記錄，禁止 catch 後靜默忽略；rollback 觸發原因也需可被追蹤。
6. **併發安全**：多請求同時操作同一資料時，需考慮鎖定或版本控制（如 optimistic lock），避免競爭條件造成資料不一致。
7. **逾時與重試需有上限**：避免無限重試造成連鎖失敗或重複副作用，並應與冪等性設計搭配。
8. **可觀測性**：失敗、rollback、重試都要有 log／監控可查，方便事後追查根因。

# PR 前的 Spec 一致性檢查（專案固定規則）

程式碼與 spec/proposal/design 是否一致，分兩層把關，性質不同：

1. **結構檢查（交給 CI）**：若這次變更修改了實作程式碼，卻沒有同步修改對應的 `openspec/specs/**` 或該 change 目錄下的文件，CI 應直接擋下 PR。這是可自動化、確定性的規則，不需要 AI 判斷。
2. **語意檢查（由我在流程中執行，不寫進 CI）**：驗證 task/實作是否真的符合 proposal、design 的描述，需要語意判讀，不適合當 CI 硬性 gate（成本高、可能不穩定）。因此：
   - 在 `/spectra-apply` 的任務完成、要準備開 PR 之前，必須先執行 `/spectra-verify` 確認實作與 change 的 spec/design 一致。
   - 同時執行 `/spectra-drift` 檢查該 change 與目前程式碼現狀是否已產生落差。
   - 若 verify 或 drift 回報落差，必須先處理（修正實作或回頭 `ingest` 調整 spec），確認一致後才能建議使用者開 PR。
   - 這一層是流程約定，仰賴我主動執行，不是 CI 保證；若程式碼是透過我以外的方式修改，此規則不會被觸發。

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`KK-Huang86/Find_Coffee`). See `docs/agents/issue-tracker.md`.

### Triage labels

Using default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — one `CONTEXT.md` at repo root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.
