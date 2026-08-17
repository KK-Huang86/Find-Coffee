## 1. 前置準備與基準驗證

- [ ] 1.1 確認目前在 `feature/fix-to-dict-bug` 分支，且分支乾淨地從最新 `develop` 分出（`git merge-base develop HEAD` 應等於 `git rev-parse develop`；比對對象是 `develop` 本身而非 `HEAD`——分支上一旦有新 commit，`HEAD` 就會領先 `develop`，用 `HEAD` 當比對基準在那之後永遠無法成立）。
- [ ] 1.2 `git add openspec/changes/fix-cafe-data-integrity-edge-cases/` 並建立 commit，將本 change 的 proposal/specs/design/tasks 規劃文件單獨提交，使工作目錄回到乾淨狀態。
- [ ] 1.3 確認 `git status` 乾淨。
- [ ] 1.4 執行 `uv run pytest cafe/tests/test_models.py users/tests/test_models.py -q`，記錄基準測試數與全數通過（基準綠燈）。
- [ ] 1.5 執行 `uv run pytest -q` 全套測試，記錄基準總測試數與全數通過。

## 2. 依 TDD 規範撰寫測試（先於實作，預期紅燈）

- [ ] 2.1 於 `cafe/tests/test_models.py` 的 `TestCafeModel` 新增測試：座標皆有值時，`to_dict()['lat']`、`to_dict()['lng']` 為對應浮點數（對應 spec `cafe-data-serialization` Scenario「座標皆已設定」）。
- [ ] 2.2 新增測試：`lat`、`lng` 皆為 `None` 時，`to_dict()` 不拋例外，回傳的 `lat`、`lng` 皆為 `None`（對應 Scenario「座標皆未設定」）。
- [ ] 2.3 新增測試：僅 `lat` 有值、`lng` 為 `None`（及相反情況）時，`to_dict()` 不拋例外，有值欄位回傳浮點數、缺值欄位回傳 `None`（對應 Scenario「座標部分設定」，建議拆成兩個測試分別涵蓋兩種缺值方向）。
- [ ] 2.4 新增測試：確認 `to_dict()` 對缺值座標**不會** fallback 為 `0.0`（明確斷言 `is None`，而非只斷言 falsy，避免未來有人誤改成 `0.0` 卻仍通過測試）。
- [ ] 2.5 執行 `uv run pytest cafe/tests/test_models.py -q -k to_dict`，確認 2.1 沿用既有測試仍通過、2.2-2.4 新增測試在實作變更前為紅燈，且失敗原因確實是 `TypeError`（`float() argument must be a string or a real number, not 'NoneType'`），而非測試本身寫錯。
- [ ] 2.6 於 `users/tests/test_models.py` 的 `TestUserModel` 新增測試：`member_code` 首次產生即不衝突時，使用者建立成功、不觸發 retry（對應 spec `user-account-creation` Scenario「首次代號即可用」；可用既有 `test_create_user_auto_generate_member_code` 的模式驗證，或明確 patch `random.choices` 只呼叫一次驗證不重試）。
- [ ] 2.7 新增測試：`member_code` 首次產生與既有使用者衝突、重試後產生未衝突代號時，使用者仍建立成功（patch `random.choices` 依序回傳「已存在的 code」「新的 code」，驗證最終 `user.member_code` 為第二個值，對應 Scenario「代號衝突後重試成功」）。
- [ ] 2.8 **關鍵：巢狀 transaction 情境的重試證明**——新增測試模擬 `User.save()` 被巢狀於外層 transaction 中呼叫（`@pytest.mark.django_db` 本身即讓每個測試跑在 outer atomic transaction 中，天然滿足此情境，不需額外 mock transaction）：pre-create 一個 `member_code='AAAAAA'` 的既有使用者，patch `random.choices` 依序回傳 `'AAAAAA'`（衝突）、`'BBBBBB'`（不衝突），呼叫 `User.objects.get_or_create(line_user_id='new_user')`（沿用實際生產呼叫路徑，而非直接呼叫 `.save()`，確保測的是真實觸發情境），斷言：不拋出 `TransactionManagementError`／`OperationalError`，且最終使用者的 `member_code == 'BBBBBB'`。此測試在**目前未修正的實作**下應會失敗（因為第二次 `super().save()` 在已 aborted 的 transaction 中會拋非 `IntegrityError` 的例外，被目前的 `except IntegrityError` 捕捉不到，直接往外傳），藉此擋下「retry loop 只在無外層 transaction 時才生效」的假保護（對應 CLAUDE.md 併發安全與原子性測試邊界案例規範）。
- [ ] 2.9 新增測試：連續 10 次產生的 `member_code` 皆與既有使用者衝突（重試上限用盡）時，最終拋出明確的 `IntegrityError`（對應 Scenario「重試次數達上限仍衝突」；沿用既有測試風格，patch `random.choices` 固定回傳同一個已存在的 code）。
- [ ] 2.10 **`using` 參數正確傳遞的證明（codex review 補強兩輪：第一輪要求驗證 `using` 有正確解析並傳入 `atomic()`；第二輪指出僅 mock `transaction.atomic` 不夠——`super().save()` 仍會真的嘗試連線到 `'some_alias'`／`'explicit_alias'` 這種本專案 `DATABASES` 裡不存在的別名，導致測試因 `ConnectionDoesNotExist` 失敗，而非驗證到預期行為，對應 Scenario「建立操作指定非預設資料庫連線時重試機制仍正確運作」）**：除了 `patch('users.models.transaction.atomic')`（回傳可用作 context manager 的 `MagicMock`）與 `patch('users.models.router.db_for_write', return_value='some_alias')`，**必須額外 `patch('django.db.models.Model.save')`**（同樣回傳 `MagicMock`），讓 `User.save()` 內 `super().save(*args, **kwargs)` 呼叫到的是 mock、完全不觸發真實資料庫連線解析。呼叫 `user.save()`（不顯式帶 `using`），斷言 `transaction.atomic` 被呼叫時 `using='some_alias'`（而非 `None` 或 `'default'`），且 `Model.save` 的 mock 確實被呼叫過一次（證明寫入流程仍在 mock 的 atomic 區塊內被觸發，不是被跳過）。另外新增一筆測試：顯式呼叫 `user.save(using='explicit_alias')`，同樣 patch 上述三者，斷言 `transaction.atomic` 被呼叫時 `using='explicit_alias'`（顯式 `using` kwarg 優先於 router 解析結果）。本專案目前只有 `default` 一個資料庫連線、未設 `DATABASE_ROUTERS`，這兩筆測試全程不需要真的接一個第二資料庫、也不會嘗試任何真實連線，純粹用 mock 驗證「解析邏輯有沒有把 `using` 正確傳給 `atomic()`」這件事本身。
- [ ] 2.11 **可觀測性的證明（codex review 補強，對應 CLAUDE.md 資料操作穩健性規範第 8 點與 Scenario「代號衝突觸發重試時可被追蹤」「重試次數達上限仍衝突」）**：用 pytest 的 `caplog` fixture，(a) 重現一次撞號後重試成功的情境（同 2.7 設定），斷言 `caplog` 中有一筆 `WARNING` 等級紀錄，內容包含該使用者的 `line_user_id`；(b) 重現 10 次全撞號耗盡的情境（同 2.9 設定），斷言除了最終拋出的例外外，`caplog` 中有一筆 `ERROR` 等級紀錄，內容包含該使用者的 `line_user_id`；(c) 重現首次即成功的情境（同 2.6），斷言 `caplog` 中**沒有** `WARNING`／`ERROR` 等級的撞號相關紀錄（正常路徑不該產生雜訊 log）。
- [ ] 2.12 執行 `uv run pytest users/tests/test_models.py -q -k member_code`，確認 2.7-2.11 新增測試中，2.8（巢狀 transaction 情境）、2.10（`using` 傳遞）、2.11（可觀測性）在實作變更前為紅燈且失敗原因與上述分析相符；2.6、2.7、2.9 若本來就已通過（現行實作在無巢狀 transaction 情境下本就正確）則保持綠燈即可，不強求紅燈——這些測試的目的是鎖定既有正確行為、防止之後改動破壞它，不是本次修正的紅燈標的。

## 3. 實作

- [ ] 3.1 `cafe/models.py`：`Cafe.to_dict()` 的 `lat`、`lng` 欄位改為 `float(self.lat) if self.lat is not None else None`、`float(self.lng) if self.lng is not None else None`。
- [ ] 3.2 `users/models.py`：新增 `import logging` 與 `logger = logging.getLogger(__name__)`（比照 `cafe/tasks.py` 既有寫法）。`User.save()` 新增 `using = kwargs.get('using') or router.db_for_write(self.__class__, instance=self)`，retry loop 內 `super().save(*args, **kwargs)` 改為在 `with transaction.atomic(using=using):` 區塊中呼叫；每次捕捉到 `member_code` 撞號的 `IntegrityError` 時 `logger.warning(...)` 記錄 attempt 次數與 `line_user_id`；10 次重試耗盡、最終 `raise IntegrityError` 前 `logger.error(...)` 記錄 `line_user_id`。`from django.db import models, IntegrityError` 補上 `router`、`transaction`（若尚未匯入）。

## 4. 驗證

- [ ] 4.1 執行 `uv run pytest cafe/tests/test_models.py -q`，確認全數轉綠。
- [ ] 4.2 執行 `uv run pytest users/tests/test_models.py -q`，確認全數轉綠（含 2.8 巢狀 transaction、2.10 `using` 傳遞、2.11 可觀測性測試皆轉綠）。
- [ ] 4.3 執行 `uv run pytest cafe/tests/ users/tests/ -q`，確認累積回歸全數通過。
- [ ] 4.4 執行 `uv run pytest -q` 全套測試，確認全數通過，並比對總測試數 = 第 1.5 步基準數 + 本次新增測試數。
- [ ] 4.5 執行 `uv run python manage.py check`，確認無誤。
- [ ] 4.6 執行 `uv run ruff check .`，確認無新增 lint 錯誤。
- [ ] 4.7 確認兩份 spec 的需求皆有測試覆蓋：「咖啡店序列化不因座標缺值而失敗」由 2.1-2.4 覆蓋；「會員代號衝突時自動重試且不受外層 transaction 影響」由 2.6-2.11 覆蓋（含巢狀 transaction 情境 2.8、資料庫連線路由情境 2.10、可觀測性 2.11）。

## 5. Spec 一致性檢查與收尾

- [ ] 5.1 執行 `openspec validate fix-cafe-data-integrity-edge-cases --strict`，確認 proposal/specs/design/tasks 一致且通過驗證。
- [ ] 5.2 執行語意一致性檢查（環境內若無 `/spectra-verify` slash command，改跑 `spectra analyze fix-cafe-data-integrity-edge-cases` 等效檢查），確認實作與本 change 的 proposal/design/specs 語意一致；若回報 Coverage/Consistency/Gaps 落差，先修正實作或回頭調整 spec，確認一致後才繼續。
- [ ] 5.3 執行 drift 檢查（環境內若無 `/spectra-drift` slash command，改跑 `spectra drift fix-cafe-data-integrity-edge-cases` 等效檢查），檢查本 change 與目前程式碼現狀是否已產生落差；若回報真實落差（非工具誤判），先處理後再繼續（依 CLAUDE.md「PR 前的 Spec 一致性檢查」規範，這兩步是開 PR 前的強制流程約定）。
- [ ] 5.4 檢視 `git diff`，確認變更範圍僅限 `cafe/models.py`、`users/models.py`、`cafe/tests/test_models.py`、`users/tests/test_models.py`、`openspec/changes/fix-cafe-data-integrity-edge-cases/`。
- [ ] 5.5 `git add` 並建立 commit（訊息說明本次變更：修正 `Cafe.to_dict()` 座標缺值例外與 `User.save()` 巢狀 transaction 下 retry 失效兩個資料完整性邊界案例）。
