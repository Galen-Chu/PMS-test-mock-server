# orchestrator/classify.py
"""失敗歸類規則（spec §6.5 失敗歸類）。

把 CaseResult 的 diff / status / 例外型態映射到 error_category，
規則集中在這裡，未來擴充規則不動 engine。
"""
from typing import Optional
from .models import CaseResult, CASE_FAIL

FIELD_MISMATCH = "FIELD_MISMATCH"   # 欄位缺失／值不符（對應原型 demo 文案）
STATUS_CODE = "STATUS_CODE"         # 回應狀態���非預期（非 2xx）
TIMEOUT = "TIMEOUT"                 # 請求超時／連線失敗
UNIMPLEMENTED = "UNIMPLEMENTED"     # 案例尚無 runner


def classify(case: CaseResult) -> Optional[str]:
    if case.status != CASE_FAIL:
        return None
    # 有 diff → 欄位層級問題優先歸類
    if case.diff:
        return FIELD_MISMATCH
    # 無 diff 但失敗：通常是狀態碼或連線問題
    resp = case.response_payload
    if isinstance(resp, dict) and resp.get("__error__"):
        # runner 連線失敗時會放 __error__ 標記
        return TIMEOUT
    return STATUS_CODE
