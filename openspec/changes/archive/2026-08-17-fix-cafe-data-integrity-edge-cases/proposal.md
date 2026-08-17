## Why

Senior code review 涵蓋整個專案架構後，發現兩個資料穩健性邊界案例，皆屬「schema 允許的情況，程式碼卻假設不會發生」的落差，且都已確認有真實可觸發的呼叫路徑，非純理論風險：`Cafe.to_dict()` 對 nullable 的 lat/lng 做無條件型別轉換會炸例外；`User.save()` 的 member_code 撞號 retry 機制，在唯一呼叫路徑（`get_or_create` 內建 atomic block）下實際上失效。兩者皆是小範圍、低成本即可修正的資料完整性缺口，及早修正可避免未來累積更多依賴這些錯誤假設的程式碼。

## What Changes

- `Cafe.to_dict()`（`cafe/models.py`）對 `lat`／`lng` 欄位改為 None-safe 轉換：有值時轉 `float`，為 `None` 時保持 `None`，不再無條件呼叫 `float(None)` 而拋出 `TypeError`；同時不 fallback 為 `0.0`（避免與幾內亞灣外海真實座標混淆，造成下游誤判為有效位置的靜默錯誤）
- `User.save()`（`users/models.py`）的 member_code 撞號 retry loop，改為每次嘗試都包一層 `transaction.atomic()`，確保在巢狀於外層 atomic block（如 `get_or_create` 內部）時使用 savepoint 正確回復，retry 機制在所有呼叫情境下皆能正常運作，而非僅在無外層 transaction 時才生效

## Capabilities

### New Capabilities
- `cafe-data-serialization`：`Cafe` model 轉換為外部使用（Flex Message、API 回應等）的 dict 格式時，對 nullable 欄位的處理保證
- `user-account-creation`：`User` model 建立時 member_code 唯一性衝突的 retry 保證，涵蓋巢狀 transaction 情境

### Modified Capabilities
（無）

## Impact

- **受影響程式碼**：
  - `cafe/models.py`（`Cafe.to_dict()`）
  - `users/models.py`（`User.save()`）
  - `cafe/tests/test_models.py`、`users/tests/test_models.py`（新增/調整對應測試，若既有測試檔案不存在則新建）
- **不受影響**：`Cafe` 與 `User` 的其他欄位、方法；`FavoritesManager.add_favorite`（`users/views.py`）等呼叫端邏輯不變，僅其建立出的 `Cafe` 物件在後續 `to_dict()` 呼叫時不再因 `lat`/`lng` 為 `None` 而拋出例外
- **不在本次範圍**：不修改 `FavoritesManager.add_favorite` 本身讓 lat/lng 一律有預設值（那是另一個問題——是否該在建立時就防呆，還是允許 None 並在讀取端妥善處理——本次選擇後者，讓 `to_dict()` 對 nullable 欄位負責任地處理，不擴大改動範圍）
- **使用者可感受到的變化**：無直接可見的行為變化（這是防禦性修正，修正的是「本來會炸但目前罕見觸發」的邊界情況），但降低未來資料存在座標缺失或 member_code 撞號時系統出錯的風險
