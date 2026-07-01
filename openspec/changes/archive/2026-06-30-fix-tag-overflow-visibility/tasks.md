## 1. 修改核心邏輯

- [x] 1.1 修改 `_create_tags_box` 方法：將 tags 清單以每 2 個為一組切割，每組包成一個 `horizontal` box，再由外層 `vertical` box 統整
- [x] 1.2 確認 1~2 個 tag 時仍使用單一水平列（行為與現在相同）

## 2. 測試補充

- [x] 2.1 在 `test_flex_builder.py` 補充 3 個 tag 的情境：驗證輸出為 vertical box，第一列 2 個、第二列 1 個
- [x] 2.2 在 `test_flex_builder.py` 補充 4 個 tag 的情境：驗證輸出為 vertical box，兩列各 2 個
- [x] 2.3 確認現有 1、2 個 tag 的測試案例仍通過

## 3. 驗證

- [x] 3.1 執行 `uv run pytest line_bot/tests/test_flex_builder.py` 確認全部通過
- [ ] 3.2 手動使用 LINE Bot 發送含 4 種屬性的咖啡店訊息，確認 4 個 tag 完整顯示
