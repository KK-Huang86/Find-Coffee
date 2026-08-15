## Context

`line_bot/builders/shop_flex_message.py` 的 `FlexMessageBuilder.get_photo_url` 目前邏輯：

```python
if photo_s3_url:
    return photo_s3_url
elif photo_reference:
    resolved_url = FlexMessageBuilder.resolve_photo_url(photo_reference)   # 同步，requests.head(..., timeout=2)
    if resolved_url != FlexMessageBuilder.DEFAULT_PHOTO_URL:
        FlexMessageBuilder._trigger_s3_upload(place_id)                   # 只有解析成功才觸發背景上傳
    return resolved_url
else:
    return FlexMessageBuilder.DEFAULT_PHOTO_URL
```

關鍵約束（已確認的事實）：

- LINE webhook 是**全同步**處理：`line_bot/views.py` 的 `callback()` 直接呼叫 `handler.handle(body, signature)`，一路同步執行到 `get_photo_url`，才 `return HttpResponse('OK')`。任何同步等待都直接計入 webhook 回應時間。
- 多筆結果（carousel，2-10 間店）在 `line_bot/builders/message_sender.py` 的 `send_shop_result` 中是 `for shop in shops:` **依序**呼叫 `create_shop_flex_message(info_d, is_multiple=True)`，若每間都未快取，`resolve_photo_url` 的 2 秒 timeout 會逐間疊加，最差情境（10 間）等於 20 秒同步阻塞。
- `cafe/tasks.py` 的 Celery task `download_and_upload_cafe_photo` 是用 `cafe.photo_reference` **自行重新組出**下載用的 photo URL，完全不依賴 `resolve_photo_url` 的同步解析結果——代表「觸發背景上傳」這件事本來就不需要同步解析成功才能做。
- `create_shop_flex_message(info, is_multiple=False)` 已存在 `is_multiple` 旗標，目前只用來決定 footer 按鈕（「選擇這間」vs.「看地圖/官網」），尚未影響照片載入邏輯。

## Goals / Non-Goals

**Goals:**
- 讓多筆結果的照片載入不再逐間同步等待外部解析，回應時間不隨未快取店家數量疊加
- 讓背景 S3 快取的觸發與「這次同步解析是否嘗試、是否成功」解耦，任何有 `photo_reference` 但尚未快取的店家都應該被觸發背景快取
- 沿用既有的 `is_multiple` 分流語意，不新增與其平行的判斷依據

**Non-Goals:**
- 不調整 `resolve_photo_url` 的 `timeout=2` 數值（見 proposal.md 與 Open Questions）
- 不改變 `resolve_photo_url` 本身的實作方式（仍是 `requests.head` 同步呼叫）
- 不改變 `download_and_upload_cafe_photo` Celery task 的實作
- 不改變單筆結果的同步照片顯示行為（單筆仍維持同步等待、逾時才顯示預設圖）；背景快取觸發行為則依本 change 調整（見 Decision 2，單筆逾時後現在也會觸發背景上傳，這屬於本次要改變的行為，不在此 Non-Goal 範圍內）

## Decisions

**1. 用 `allow_sync_resolve` 參數而非拆成兩個方法**
- 選擇：`get_photo_url(cafe_dict_or_obj, allow_sync_resolve=True)`，`create_shop_flex_message` 呼叫時傳入 `allow_sync_resolve=not is_multiple`。
- 理由：`get_photo_url` 不需要知道「多筆結果」這個業務概念，只需要知道「這次能不能同步等」——用語意化的參數名稱維持函式與呼叫情境的解耦，也讓 `get_photo_url` 本身仍可獨立測試。
- 替代方案：拆成 `get_photo_url` / `get_photo_url_fast` 兩個方法。放棄原因：會有兩份幾乎相同的邏輯要同步維護，不符合專案一貫「不重複邏輯」的風格。

**2. 移除 `_trigger_s3_upload` 觸發條件對同步解析結果的依賴**
- 選擇：只要進入 `elif photo_reference:` 分支（代表 `photo_s3_url` 尚為空、但有 `photo_reference`），無條件呼叫 `_trigger_s3_upload(place_id)`，不論 `allow_sync_resolve` 為何、也不論 `resolve_photo_url` 是否被呼叫或是否成功。
- 理由：`_trigger_s3_upload` 內部本來就會重新查一次 DB 確認 `cafe and not cafe.photo_s3_url` 才真的 `.delay()`，這層既有的冪等檢查已足以避免重複觸發；移除外層的成功與否判斷，能讓「多筆結果跳過同步解析」與「背景快取仍正常運作」兩件事同時成立，而不是彼此拖累。
- 替代方案：多筆結果完全不觸發背景快取，只靠使用者之後點進單筆詳情或 180 天排程刷新來補齊。放棄原因：會讓 carousel 搜尋到的店家長期無法被快取，S3 命中率變差，也違背這次修改「讓快取更可靠」的核心動機。

**3. 單筆／多筆差異化處理，不統一邏輯**
- 選擇：單筆結果（使用者明確想看這一間）維持同步等待、逾時才回退預設圖；多筆結果一律不同步等待，未命中快取直接回預設圖。
- 理由：兩種情境的使用者預期不同——單筆是「我要看這一間的細節」，多等 2 秒換真實照片可接受；多筆是「先給我結果列表，我再選」，任何一間拖慢整體列表是不成比例的代價，且會被使用者感知為「Bot 沒反應」。
- 替代方案：統一都同步等待（現行行為）或統一都不等待。兩者都放棄，因為前者就是本次要解決的問題本身，後者會讓單筆結果的照片品質無謂下降（單筆情境並無疊加風險，沒有理由跟著犧牲）。

**4. 本次不調整 `timeout=2`**
- 選擇：維持現行 2 秒不變。
- 理由：這次變更的核心動機是「觸發條件解耦」與「單筆/多筆分流」，兩者都不依賴 timeout 數值本身；把缺乏數據支撐的參數調整一起塞進來，會讓變更動機模糊、review 難以聚焦。
- 替代方案：順便調高單筆結果的 timeout（例如 3-4 秒）。放棄原因：沒有實際的逾時發生率數據支撐這個數字，屬於應該獨立評估、獨立驗證的決定（見 Open Questions）。

## Risks / Trade-offs

- [風險] 移除觸發條件的 gate 後，`_trigger_s3_upload` 被呼叫的頻率會比現行更高（包含原本因逾時而完全不會觸發的情況）→ 緩解：`_trigger_s3_upload` 內部既有的 `not cafe.photo_s3_url` 檢查、以及 Celery task 內部再次檢查 `if cafe.photo_s3_url: skip`，兩層檢查可減少「已完成快取後」的重複工作，但**這兩次 DB 檢查之間沒有 lock，無法保證嚴格冪等**，只能避免快取完成後的多餘觸發；快取完成「前」的併發重複觸發仍可能發生（見下一項風險）。
- [風險] 高併發下（多個使用者同時搜尋同一間未快取店家）仍可能有多個請求同時通過 `not cafe.photo_s3_url` 檢查、各自 `.delay()` 一次，造成同一張照片被重複下載上傳一次 → 緩解：此競態屬既有風險，非本次變更引入（現行程式碼本來就有相同的檢查方式），後果僅止於重複下載同一張圖片、無資料損毀或不一致風險，本次不額外處理（超出本次變更範圍）。
- [Trade-off] 多筆結果不再嘗試同步解析，代表使用者第一次看到某間未快取店家的 carousel 結果時，一定是預設圖，即使 Google 端其實可以在 2 秒內回應——這是用「多筆結果的最差情境不可控」換取「所有情境的回應時間可預期」，屬於刻意的取捨。

## Migration Plan

1. 依 CLAUDE.md 的 TDD 規範，先在 `line_bot/tests/builders/test_shop_flex_message.py` 補齊／調整測試：
   - `get_photo_url(info, allow_sync_resolve=False)` 在 `photo_s3_url` 為空、有 `photo_reference` 時，不呼叫 `resolve_photo_url`、直接回傳預設圖，且觸發 `_trigger_s3_upload`
   - `get_photo_url(info, allow_sync_resolve=True)`（預設值）維持現行行為不變（既有測試應仍全數通過）
   - `resolve_photo_url` 逾時／失敗時，`get_photo_url` 仍觸發 `_trigger_s3_upload`（現行測試若原本斷言「不觸發」需依此更新，屬於商業邏輯變更帶動的測試調整，非遷就實作）
   - `create_shop_flex_message(info, is_multiple=True)` 會以 `allow_sync_resolve=False` 呼叫 `get_photo_url`（可用 `patch.object` 驗證呼叫參數）
2. 確認新測試在無實作變更前為紅燈（fail）
3. 實作 `get_photo_url` 新增 `allow_sync_resolve` 參數、移除 `_trigger_s3_upload` 的外層 gate、`create_shop_flex_message` 傳入 `allow_sync_resolve=not is_multiple`
4. 確認所有測試轉綠，執行 `line_bot/tests/builders/` 全部測試與全套 `uv run pytest -q` 回歸
5. `openspec validate fix-cafe-google-url-timeout --strict` 確認 spec/proposal/design/tasks 一致
6. Rollback：本次變更範圍集中在單一檔案（`shop_flex_message.py`）的一個方法與其呼叫點，若上線後發現問題，`git revert` 該次 commit 即可完整還原，不影響其他模組。

## Open Questions

- `timeout=2` 是否需要調整，待本次變更上線後蒐集實際的同步解析逾時發生率，再評估是否值得開下一個獨立 change 處理（不影響本次的 spec、設計方向或任務拆解，可安全留待之後決定）。
