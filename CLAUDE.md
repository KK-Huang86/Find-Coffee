# Find Coffee - LINE Bot 咖啡店搜尋服務

## 專案概述

LINE Bot 服務，幫助使用者搜尋附近咖啡店，支援位置搜尋、店名查詢、收藏等功能。

## 技術棧

- **後端**: Django ~6.0 + Python 3.13
- **資料庫**: PostgreSQL
- **容器化**: Docker
- **LINE Bot**: line-bot-sdk v3 (Messaging API)
- **外部 API**: Google Places API
- **雲端**: AWS (S3 + CloudFront)
- **IaC**: Terraform
- **套件管理**: uv
- **異步任務**: celery

## 專案結構

```
├── cafe/           # 咖啡店 Model (Cafe, CafeNomadCache, Vote)
├── line_bot/       # LINE Bot 核心邏輯
│   ├── handlers/   # Postback action handlers
│   ├── builders/   # Flex Message builders
│   ├── services/   # 業務邏輯 (搜尋快取等)
│   └── views.py    # Webhook + Rich Menu 設定
├── users/          # 使用者 Model
├── integrations/   # 外部 API 整合 (Google)
├── terraform/      # AWS 資源定義
└── core/           # Django settings
```

## 重要 Model

- `Cafe`: 主要咖啡店資料 (來自 Google Places)
- `CafeNomadCache`: CafeNomad API 快取 (有 socket, limited_time 屬性)
- `User`: LINE 使用者

## Celery Tasks (cafe/tasks.py)

- `download_and_upload_cafe_photo`: 下載 Google 照片 → 上傳 S3
- `refresh_cafe_data`: 更新咖啡店資料 (last_refreshed的值超過 30 天觸發，照片 photo_updated_at的值超過 180 天重抓)

## LINE Bot 架構

- **Rich Menu**: 6 格選單 (views.py)
- **State 管理**: `StateManager` + `UserState` 控制對話流程
- **Postback 路由**: `ACTION_HANDLERS` dispatch table

## 開發指令

```bash
# 啟動開發伺服器
uv run python manage.py runserver

# 執行測試
uv run pytest

# Terraform
cd terraform && terraform plan
```

## 注意事項

- Commit 訊息使用繁體中文
- 圖片存放於 S3，透過 CloudFront 存取
- 環境變數放在 .env (不要 commit)

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`KK-Huang86/Find_Coffee`). See `docs/agents/issue-tracker.md`.

### Triage labels

Using default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — one `CONTEXT.md` at repo root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.
