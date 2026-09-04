# orchestrator/runners/helpers.py
"""跨模組共用輔助(參數合併/時間戳/URL 段編碼/結果建構/回應扒取/417 反向判定)。"""
from datetime import datetime
from urllib.parse import quote

from ..registry import registry
from ..models import CaseResult, RunContext, CASE_PASS, CASE_FAIL


# ---- 共用輔助 ----------------------------------------------------------
def _p(ctx: RunContext, case_id: str) -> dict:
    """取得案例「合併後參數」（預設 ← overrides，engine 已於 run 開始時求值填 ctx.params）。

    直接呼叫 runner（離線測試 / REPL）時退化為當場求值預設——值與參數化前硬編相同。
    未宣告參數的案例回 {}（固定劇本）。
    """
    if case_id in ctx.params:
        return ctx.params[case_id]
    sc = registry.get(case_id)
    if sc is None or not sc.params:
        return {}
    return {sp.key: (sp.default(ctx) if callable(sp.default) else sp.default) for sp in sc.params}


def _ts() -> str:
    """動態唯一時間戳（%m%d%H%M%S，同參數化前 runner 內部格式）。"""
    return datetime.now().strftime("%m%d%H%M%S")


def _sa_now() -> str:
    """SA v1.2 時間格式：yyyy/mm/dd hh:mm（無秒）。"""
    return datetime.now().strftime("%Y/%m/%d %H:%M")


def _path_seg(value) -> str:
    """參數值進 URL 路徑段前的編碼（設計 §4：永不拼接未編碼路徑，防路徑注入）。"""
    return quote(str(value), safe="")


def _ok(case_id, run_id, scenario, duration_ms, request_payload=None, response_payload=None) -> CaseResult:
    return CaseResult(
        case_id=case_id, run_id=run_id, module=scenario.module, vendor=scenario.vendor,
        scenario_name=scenario.name, endpoint=scenario.endpoint, status=CASE_PASS,
        duration_ms=duration_ms, request_payload=request_payload, response_payload=response_payload,
    )


def _fail(case_id, run_id, scenario, duration_ms, request_payload=None, response_payload=None) -> CaseResult:
    return CaseResult(
        case_id=case_id, run_id=run_id, module=scenario.module, vendor=scenario.vendor,
        scenario_name=scenario.name, endpoint=scenario.endpoint, status=CASE_FAIL,
        duration_ms=duration_ms, request_payload=request_payload, response_payload=response_payload,
    )


def _extract_ci_serial(res):
    """從 GET /room-nos 或 /mifare-nos 回應扒出 checkInSerial（SA 規格:回應為裸陣列 body[0]）。"""
    body = res.json()
    return body[0]["checkInSerial"]


def _extract_room_nos(res):
    """從 GET /mifare-nos 回應扒出歸屬房號（B 閉環斷言用,裸陣列 body[0]）。"""
    body = res.json()
    return body[0]["roomNos"]


def _expect_417(case_id, scenario, dur, payload, res, expected_code):
    """負面路徑共用判定:HTTP 417 + SA code 相符 → PASS。"""
    if res is None:
        return _fail(case_id, "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 417 and isinstance(body, dict) and str(body.get("code")) == expected_code:
        return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=body)
