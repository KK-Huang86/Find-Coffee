## 1. 測試

- [x] 1.1 新增 `_build_tel_uri` unit test：分隔符號、國際碼、分機、全形、佔位字串、空值、非字串、長度邊界
- [x] 1.2 新增 footer unit test：單筆有電話顯示按鈕、按鈕順序、無電話不顯示、多筆不顯示
- [x] 1.3 未實作前執行測試，確認新測試為紅燈

## 2. 實作

- [x] 2.1 `FlexMessageBuilder._build_tel_uri` 實作正規化規則
- [x] 2.2 單筆 footer 於「看地圖」之後加入「打電話」按鈕

## 3. 驗證

- [x] 3.1 新測試全綠，完整 test suite 與 `ruff check` 通過
- [x] 3.2 `openspec validate add-shop-phone-call --strict` 通過
