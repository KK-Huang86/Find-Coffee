## Context

`cafe/tests/test_models.py`（`TestCafeModel`）與 `users/tests/test_models.py`（`TestUserModel`）已存在，本次新增測試會加進這兩個既有測試類別，不新建檔案。

`Cafe.to_dict()`（`cafe/models.py:109-132`）目前對 `lat`/`lng` 做無條件 `float()` 轉換；欄位定義為 `models.DecimalField(..., blank=True, null=True)`（line 51-52），schema 允許缺值但轉換邏輯未處理。實際觸發路徑：`users/views.py:35-36` 的 `FavoritesManager.add_favorite` 用 `Cafe.objects.get_or_create(..., defaults={'lat': info.get('lat'), 'lng': info.get('lng'), ...})`，未做防呆；`info` 若缺 `lat`/`lng`（例如上游資料來源本身未提供座標），`get_or_create` 會建立 `lat=None` 的 `Cafe` 列，之後該筆的 `to_dict()` 呼叫會拋 `TypeError`。

`User.save()`（`users/models.py:41-60`）的 retry loop 目前唯一呼叫路徑是 `line_bot/event_handlers.py:49` 的 `User.objects.get_or_create(line_user_id=user_id)`。Django `QuerySet.get_or_create()` 內部的 `_create_object_from_params` 本身用 `with transaction.atomic(using=self.db):` 包住 `self.create(**params)`（進而呼叫 `save()`）。PostgreSQL 在同一 transaction 中一旦發生 `IntegrityError`，該 transaction 會被標記為 aborted，後續任何指令（即使是全新的、本應成功的 `INSERT`）都會立即失敗，且失敗類型通常是 `TransactionManagementError`／`OperationalError`（`current transaction is aborted`），不是 `IntegrityError`。因此目前 `except IntegrityError as e: if 'member_code' not in str(e): raise` 這段捕捉邏輯，在第二次（含）以後的重試不會被觸發，retry loop 實質上只有「第一次嘗試」是有效的。

## Goals / Non-Goals

**Goals:**
- `Cafe.to_dict()` 對 `lat`/`lng` 缺值時不拋例外，回傳語意正確的 `None`
- `User.save()` 的 member_code 撞號重試機制，在任何 transaction 巢狀情境下都必須真正生效（每次嘗試都能獨立成功或失敗，不被前一次嘗試的失敗污染）

**Non-Goals:**
- 不修改 `FavoritesManager.add_favorite`（`users/views.py`）讓建立時的 lat/lng 一律有預設值——是否該在寫入端防呆是另一個獨立問題，本次選擇讓讀取端（`to_dict()`）對 nullable 欄位負責任地處理，維持「schema 說可以是 None，程式碼就该正確處理 None」的一致性，不擴大改動範圍
- 不改變 `member_code` 的產生演算法（6 碼英數字隨機組合）或重試上限（10 次）
- 不處理其他 model 的類似 nullable 欄位轉換問題（若未來發現，應另開 change 逐一檢視，不在本次一併處理，避免範圍發散）

## Decisions

**1. `to_dict()` 對缺值座標回傳 `None`，不 fallback 為 `0.0`**
- 選擇：`'lat': float(self.lat) if self.lat is not None else None`（`lng` 同理）
- 理由：`(0, 0)` 是幾內亞灣外海的真實地理座標。若缺值座標被 fallback 成 `0.0`，任何下游邏輯（例如未來若加入距離排序、地圖顯示）會把它當成「有效但湊巧在該處」的座標，產生靜默的錯誤結果，且不會有任何例外或 log 提示——這類「看起來正常但實際錯誤」的 bug 比直接拋例外更難排查，違反 CLAUDE.md 資料操作穩健性規範「錯誤不可被吞掉」的精神。保留 `None` 讓缺值狀態在資料流中誠實傳遞，下游若真的需要座標，會在存取 `None` 時就地發現問題（例如 `TypeError` 或明確的空值檢查），而不是悄悄算出錯誤結果。
- 替代方案：fallback 為 `0.0`（放棄，理由如上）；在 `to_dict()` 直接排除缺值的 `lat`/`lng` key（放棄——會讓呼叫端每次都要用 `.get('lat')` 而非 `['lat']`，且此欄位語意上一直存在，只是可能無值，用 `None` 比整個 key 消失更符合現有其他欄位的處理風格，如 `last_refreshed`、`reviews` 皆是保留 key、值為 `None`/`[]`）

**2. `User.save()` retry loop 內，每次嘗試包一層 `transaction.atomic()`**
- 選擇：
  ```python
  using = kwargs.get('using') or router.db_for_write(self.__class__, instance=self)
  last_error = None
  for attempt in range(10):
      self.member_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
      try:
          with transaction.atomic(using=using):
              super().save(*args, **kwargs)
          return
      except IntegrityError as e:
          if 'member_code' not in str(e):
              raise
          last_error = e
          logger.warning(
              f'member_code 撞號，觸發 rollback 並重試 (attempt {attempt + 1}/10)，'
              f'line_user_id={self.line_user_id}'
          )

  logger.error(
      f'member_code 重試 10 次仍撞號，建立失敗，line_user_id={self.line_user_id}'
  )
  raise IntegrityError(
      f'Failed to generate a unique member_code after {attempt + 1} attempts.'
  ) from last_error
  ```
- 理由：Django 的 `transaction.atomic()` 是可重入的——當已存在外層 atomic block（例如 `get_or_create` 內部）時，巢狀的 `atomic()` 會建立一個 SAVEPOINT；該區塊內若發生例外，只會回滾到該 SAVEPOINT，不會拖垮外層 transaction，外層 transaction 仍可繼續執行後續指令（包含下一次 retry 的 `INSERT`）。若沒有外層 transaction（例如未來有呼叫端直接 `User().save()` 而非透過 `get_or_create`），這個 `atomic()` 就是最外層 transaction，行為與現在相同、不受影響。這個修法讓 retry loop 在「有無外層 transaction」兩種情境下都正確運作，是最小改動且不需要呼叫端配合修改的方案。
- **`using` 參數的處理**（codex review 補強）：`transaction.atomic()` 不帶 `using` 時固定作用在 `default` 連線；但 `Model.save()` 本身支援 `save(using='other_db')` 或透過 `DATABASE_ROUTERS` 路由到非預設連線寫入。若 retry loop 內的 `atomic()` 沒有比照解析同一個 `using`，會發生「savepoint 開在 `default` 連線，實際寫入卻在別的連線」的錯位——衝突發生時，`atomic()` 保護的是錯的連線，實際寫入的 transaction 依然被留在 aborted 狀態，重試照樣失敗，等於沒修。修法：`using = kwargs.get('using') or router.db_for_write(self.__class__, instance=self)`——這正是 Django `Model.save()` 內部解析寫入目標連線的同一套邏輯（`kwargs.get('using')` 對應顯式指定；`router.db_for_write` 對應路由規則），確保 `atomic(using=using)` 保護的連線與 `super().save(*args, **kwargs)` 實際寫入的連線一致。本專案目前 `DATABASES` 只有 `default`、未設 `DATABASE_ROUTERS`（`core/settings.py:86-97`），`router.db_for_write` 現況會回傳 `None`，`transaction.atomic(using=None)` 等同 `transaction.atomic()`（Django 內部 `get_connection(using=None)` 會 fallback 成 `DEFAULT_DB_ALIAS`），所以現況行為不變；但邏輯正確涵蓋了未來若引入多資料庫路由的情境，不需要屆時再回頭修這裡。
- 替代方案：把 retry 邏輯搬到呼叫端（`line_bot/event_handlers.py`），呼叫端自己處理 savepoint。放棄原因：`member_code` 的產生與衝突處理是 `User` model 自身的資料完整性職責，不該外洩給呼叫端；且未來若有其他呼叫路徑（非 `get_or_create`）建立 `User`，也不需要每個呼叫端各自實作 savepoint 邏輯。
- **可觀測性**（codex review 補強）：原方案的 retry loop 對撞號、rollback、重試次數、最終耗盡皆無 log，違反 CLAUDE.md 資料操作穩健性規範第 8 點「失敗、rollback、重試都要有 log／監控可查，方便事後追查根因」。修法：每次撞號觸發 rollback 並重試時，`logger.warning` 記錄 attempt 次數與 `line_user_id`（不記錄嘗試中的 `member_code` 值本身，因為那是即將被丟棄的失敗值，除錯用途上 `line_user_id` 才是唯一可追蹤的關聯鍵）；10 次全部耗盡、最終拋出例外前，`logger.error` 記錄同一 `line_user_id`，讓「這位使用者建立帳號失敗」在 production log 裡可被搜尋、告警。不記錄成功情境（含首次即成功）——這是正常路徑，記錄反而製造雜訊，稀釋真正需要關注的撞號訊號。
- 需在 `users/models.py` 頂部新增 `import logging` 與 `logger = logging.getLogger(__name__)`（目前檔案內尚未有 logger，比照 `cafe/tasks.py`、`line_bot/builders/message_sender.py` 等既有檔案的既定寫法）。

## Risks / Trade-offs

- [風險] `to_dict()` 回傳 `lat`/`lng` 為 `None` 後，若現有或未來程式碼直接對其做數學運算（例如未檢查 `None` 就 `+`/`-`），會在使用端拋出例外 → 緩解：這是刻意的設計選擇（見 Decision 1），讓問題在真正發生的地方（誤用缺值座標做運算）顯現，而不是在資料轉換這一層就用假數據掩蓋；目前程式碼庫內沒有任何地方對 `to_dict()` 的 `lat`/`lng` 做數學運算（皆為建立 `Cafe` 或原樣傳遞），此風險目前無實際影響面。
- [風險] `transaction.atomic()` 巢狀使用會產生 SAVEPOINT，對 PostgreSQL 有些微效能開銷 → 緩解：`User.save()` 的呼叫頻率低（僅新使用者首次互動時觸發一次 `get_or_create`），且 SAVEPOINT 開銷在此規模下可忽略不計，不影響效能。
- [Trade-off] 本次修正皆為防禦性修正，目前罕見觸發（座標缺值需上游資料源本身缺值；member_code 撞號機率為 1/36^6 等級），修正後沒有可觀察的行為變化，純粹是降低未來風險——符合小範圍、低成本修正已知資料完整性缺口的目標，不是解決當前正在發生的故障。

## Migration Plan

1. 依 CLAUDE.md TDD 規範，先在 `cafe/tests/test_models.py`（`TestCafeModel`）與 `users/tests/test_models.py`（`TestUserModel`）補齊涵蓋 Requirement 情境的測試（座標皆有值／皆缺值／部分缺值；member_code 首次可用／衝突後重試成功／巢狀 transaction 下衝突後重試成功／達重試上限）
2. 確認新測試在無實作變更前為紅燈
3. 實作：`Cafe.to_dict()` 改 None-safe 轉換；`User.save()` retry loop 加 `transaction.atomic()`
4. 確認所有測試轉綠，執行 `cafe/tests/`、`users/tests/` 全部測試與全套 `uv run pytest -q` 回歸
5. `openspec validate fix-cafe-data-integrity-edge-cases --strict` 確認 spec/proposal/design/tasks 一致
6. Rollback：兩處修改皆為單一檔案內的局部邏輯調整（`cafe/models.py`、`users/models.py`），互不依賴，單一 commit 即可 `git revert` 完整還原，不影響其他功能。
