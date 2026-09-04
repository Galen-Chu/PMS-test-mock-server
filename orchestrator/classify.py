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
    # 優先看逐步 HTTP 交易：連線錯誤 → TIMEOUT；非 2xx → STATUS_CODE
    for st in case.steps:
        if st.get("error"):
            return TIMEOUT
    for st in case.steps:
        code = st.get("status_code")
        if isinstance(code, int) and not (200 <= code < 300):
            return STATUS_CODE
    # 退化路徑（無 steps 時，沿用舊規則）：有 diff → FIELD_MISMATCH；__error__ → TIMEOUT
    if case.diff:
        return FIELD_MISMATCH
    resp = case.response_payload
    if isinstance(resp, dict) and resp.get("__error__"):
        return TIMEOUT
    return STATUS_CODE


# 各分類的中文除錯建議（UI「錯誤分析」直接渲染）
_REMEDY = {
    STATUS_CODE: "檢查狀態碼與回應內容（常見 401/403 鑑別失敗、404/417 資料不存在、400 欄位錯誤）。",
    TIMEOUT: "檢查目標環境 URL 是否可達、認證憑證是否有效、網路/VPN 是否通。",
    FIELD_MISMATCH: "對照下方 Diff 表，修正 request payload 對應欄位後重試。",
    UNIMPLEMENTED: "該案例尚無執行器（runner），請至 orchestrator/runners/ 各模組檔補上。",
    "UNKNOWN_SCENARIO": "case_id 未在 registry 註冊，檢查呼叫端傳的案例 ID。",
}


def remediation(category: Optional[str]) -> str:
    """依錯誤分類回中文除錯建議；無對應分類時給通用提示。"""
    return _REMEDY.get(category or "", "無明確分類，請檢視逐步 HTTP 交易���回應內容。")


def first_failure(case: CaseResult) -> Optional[dict]:
    """回第一個失敗的 step（連線錯誤優先，否則第一個非 2xx），供錯誤分析直指問題那一步。"""
    for st in case.steps:
        if st.get("error"):
            return st
    for st in case.steps:
        code = st.get("status_code")
        if isinstance(code, int) and not (200 <= code < 300):
            return st
    return None
