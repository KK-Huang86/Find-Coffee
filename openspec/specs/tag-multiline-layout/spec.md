# tag-multiline-layout Specification

## Purpose
TBD - created by archiving change fix-tag-overflow-visibility. Update Purpose after archive.
## Requirements
### Requirement: 標籤容器支援多列換行顯示
標籤容器 SHALL 根據標籤數量自動分列，確保每個標籤完整可見，不被截斷。當標籤數量超過 2 個時，系統 SHALL 將標籤分成多列顯示，每列最多 2 個標籤。

#### Scenario: 1 個標籤時維持單列
- **WHEN** 咖啡店只有 1 種屬性標籤
- **THEN** 標籤容器使用單一水平列顯示，與現有行為相同

#### Scenario: 2 個標籤時維持單列
- **WHEN** 咖啡店有 2 種屬性標籤
- **THEN** 標籤容器使用單一水平列顯示，2 個標籤並排

#### Scenario: 3 個標籤時分為兩列
- **WHEN** 咖啡店有 3 種屬性標籤
- **THEN** 標籤容器使用兩列顯示：第一列 2 個標籤，第二列 1 個標籤，所有標籤完整可見

#### Scenario: 4 個標籤時分為兩列
- **WHEN** 咖啡店有 4 種屬性標籤（插座、有貓貓狗狗、寵物友善、限時）
- **THEN** 標籤容器使用兩列顯示：第一列 2 個標籤，第二列 2 個標籤，所有標籤完整可見

#### Scenario: 標籤樣式保持不變
- **WHEN** 任意數量的標籤被顯示
- **THEN** 每個標籤的顏色、背景色、圓角、padding 與 TAG_STYLES 定義完全一致
