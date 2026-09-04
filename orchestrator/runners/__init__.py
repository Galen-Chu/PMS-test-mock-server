# orchestrator/runners/__init__.py
"""案例執行器 package:把「發砲邏輯」包成回傳 CaseResult 的 runner,並註冊進 registry。

設計原則:
- 不重寫 hardware/simulate_speaker 的 payload 組裝,重用其 _execute_for_ctx(環境隔離版)。
- runner 簽章固定:(RunContext) -> CaseResult。成功 2xx → PASS,否則 FAIL。
- 案例參數化(docs/design-case-parameterization.md):案例宣告 ParamSpec,
  runner 以 ``_p(ctx, case_id)`` 取合併後參數組 payload;不帶覆寫時
  resolved 值 = 預設 = 參數化前的硬編值(行為 100% 相同,向後相容硬約束)。

結構(2026-09-04 由 runners.py 單檔拆分,純搬家零行為變更):
- helpers.py :跨模組共用輔助(_p/_ts/_sa_now/_ok/_fail/_expect_417 等)
- amenity.py / parking.py / roomcontrol.py / keycard.py:各模組案例(原區段橫幅即檔案界線)
import 本 package 即觸發全部註冊(orchestrator/__init__.py 的 ``from . import runners`` 不變);
新增模組案例 → 加一支子模組檔 + 在此 import。
"""
from . import amenity, parking, roomcontrol, keycard  # noqa: F401
