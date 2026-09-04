# orchestrator/runners/amenity.py
"""🦏 房務備品模組案例（amenity / BR_AIELLO）—— 重用 simulate_speaker 的情境邏輯。"""
from datetime import datetime

from ..registry import registry, register_scenario
from ..models import CaseResult, RunContext, ParamSpec
from hardware.simulate_speaker import execute_for_ctx, load_product_from_pool

from .helpers import _p, _ok, _fail, _extract_ci_serial, _expect_417


# ====================================================================
# 🦏 房務備品（amenity / BR_AIELLO）—— 重用 simulate_speaker 的情境邏輯
# ====================================================================

@register_scenario(
    "room_nos_query", module="amenity", vendor="BR_AIELLO",
    name="房號查詢住客", endpoint="/room-pay/room-nos",
    params=[ParamSpec("keyword", "房號關鍵字", "str", "11101",
                      hint="SA:在住房號關鍵字;9999 模擬查無(417/1001)")],
)
def run_room_nos_query(ctx: RunContext) -> CaseResult:
    import time as _t
    scenario = registry.get("room_nos_query")
    p = _p(ctx, "room_nos_query")
    params = {**ctx.params_amenity, "keyword": p["keyword"]}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params=params, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("room_nos_query", "", scenario, dur, response_payload={"__error__": err})
    body = res.json() if res is not None and res.status_code == 200 else None
    if res is not None and res.status_code == 200:
        return _ok("room_nos_query", "", scenario, dur, request_payload={"keyword": p["keyword"]}, response_payload=body)
    return _fail("room_nos_query", "", scenario, dur, request_payload={"keyword": p["keyword"]}, response_payload=body)


@register_scenario(
    "mifare_query", module="amenity", vendor="BR_AIELLO",
    name="卡號查詢住客(Mifare)", endpoint="/room-pay/mifare-nos",
    params=[ParamSpec("keyword", "Mifare 卡號", "str", "1A2B3C",
                      hint="沙盒預設卡號映射房號 11101;未註冊卡號 → 417/1001")],
)
def run_mifare_query(ctx: RunContext) -> CaseResult:
    import time as _t
    scenario = registry.get("mifare_query")
    p = _p(ctx, "mifare_query")
    params = {**ctx.params_amenity, "keyword": p["keyword"]}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["mifare_nos"], params=params, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("mifare_query", "", scenario, dur, response_payload={"__error__": err})
    body = res.json() if res is not None and res.status_code == 200 else None
    if res is not None and res.status_code == 200:
        return _ok("mifare_query", "", scenario, dur, request_payload={"keyword": p["keyword"]}, response_payload=body)
    return _fail("mifare_query", "", scenario, dur, request_payload={"keyword": p["keyword"]}, response_payload=body)


@register_scenario(
    "amenity_charge", module="amenity", vendor="BR_AIELLO",
    name="備品入帳(2步・查房→過帳)", endpoint="/room-billing",
    expected_key="Scenario_1_Room_Nos_To_Billing",
    params=[
        ParamSpec("room_no", "房號", "str", "11101", echo_fields=("roomNos",)),
        ParamSpec("product", "料號", "str", "M001", hint="數據池料號,經 load_product_from_pool 轉實際品項代號"),
        ParamSpec("quantity", "數量", "int", 1),
    ],
)
def run_amenity_charge(ctx: RunContext) -> CaseResult:
    """房號查驗 → 備品過帳（GET 取 ciSerial 後 POST /room-billing）。"""
    import time as _t
    scenario = registry.get("amenity_charge")
    p = _p(ctx, "amenity_charge")
    t0 = _t.perf_counter()
    # Phase 1: GET room-nos 取 ciSerial
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params={**ctx.params_amenity, "keyword": p["room_no"]}, headers=ctx.headers_amenity)
    if err or res is None or res.status_code != 200:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("amenity_charge", "", scenario, dur, response_payload={"__error__": err or f"GET room-nos {getattr(res,'status_code',None)}"})
    ci_serial = _extract_ci_serial(res)

    # Phase 2: POST room-billing
    payload = {"roomNos": p["room_no"], "items": [{"seqNos": 1, "productNos": load_product_from_pool(p["product"]), "orderQuantity": p["quantity"]}]}
    res2, err2 = execute_for_ctx(ctx, "POST", ctx.urls["room_billing"], params=ctx.params_amenity, json_body=payload, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err2 or res2 is None or res2.status_code not in (200, 204):
        return _fail("amenity_charge", "", scenario, dur, request_payload=payload, response_payload={"__error__": err2 or f"POST billing {getattr(res2,'status_code',None)}"})
    body2 = None
    try:
        body2 = res2.json()
    except Exception:
        body2 = {"status_code": res2.status_code}
    return _ok("amenity_charge", "", scenario, dur, request_payload=payload, response_payload=body2)


@register_scenario(
    "amenity_cancel", module="amenity", vendor="BR_AIELLO",
    name="掛帳沖銷(2步・掛帳→作廢)", endpoint="/room-pay-cancel",
    expected_key="Scenario_3_Room_Nos_Pay_And_Cancel",
    params=[ParamSpec("room_no", "房號", "str", "11101", echo_fields=("roomPayMain.roomNos",))],
)
def run_amenity_cancel(ctx: RunContext) -> CaseResult:
    """住掛 → 沖正作廢（先 POST /room-pay 取得單號，再 POST /room-pay-cancel）。"""
    import time as _t
    scenario = registry.get("amenity_cancel")
    p = _p(ctx, "amenity_cancel")
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params={**ctx.params_amenity, "keyword": p["room_no"]}, headers=ctx.headers_amenity)
    if err or res is None or res.status_code != 200:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("amenity_cancel", "", scenario, dur, response_payload={"__error__": err or "GET room-nos failed"})
    ci_serial = _extract_ci_serial(res)

    order_nos = f"BR-ORCH-{datetime.now().strftime('%m%d%H%M%S')}"
    pay_payload = {"roomPayMain": {
        "ciSerial": str(ci_serial), "roomNos": p["room_no"], "orderNos": order_nos,
        "needTransfer": "N", "rsptCode": "2FFO", "rsptName": "2F櫃台",
        "mTimeCode": "LCH", "mTimeName": "午餐", "deskNos": "A01",
        "payAmount": 120, "acuAmount": 0, "precreditTotal": 0, "custType": "5",
    }, "roomPayDetail": [{"sequenceNos": 1, "productName": "特製飲品", "orderQuantity": 1, "specialAmount": 120, "precreditAmount": 0}]}
    res2, err2 = execute_for_ctx(ctx, "POST", ctx.urls["room_pay"], params=ctx.params_amenity, json_body=pay_payload, headers=ctx.headers_amenity)
    if err2 or res2 is None or res2.status_code not in (200, 204):
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("amenity_cancel", "", scenario, dur, request_payload=pay_payload, response_payload={"__error__": err2 or "POST room-pay failed"})

    res3, err3 = execute_for_ctx(ctx, "POST", ctx.urls["room_pay_cancel"], params={**ctx.params_amenity, "orderNos": order_nos}, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err3 or res3 is None or res3.status_code not in (200, 204):
        return _fail("amenity_cancel", "", scenario, dur, request_payload={"cancelledOrderNos": order_nos}, response_payload={"__error__": err3 or f"cancel {getattr(res3,'status_code',None)}"})
    body3 = None
    try:
        body3 = res3.json()
    except Exception:
        body3 = {"status_code": res3.status_code}
    return _ok("amenity_cancel", "", scenario, dur, request_payload={"cancelledOrderNos": order_nos}, response_payload=body3)


@register_scenario(
    "billing_sync", module="amenity", vendor="BR_AIELLO",
    name="餐廳住掛", endpoint="/room-pay",
    expected_key="Scenario_2_Room_Nos_To_Pay",
    params=[ParamSpec("room_no", "房號", "str", "11101", echo_fields=("roomPayMain.roomNos",))],
)
def run_billing_sync(ctx: RunContext) -> CaseResult:
    """房號查驗 → 餐廳住掛（POST /room-pay）。"""
    import time as _t
    scenario = registry.get("billing_sync")
    p = _p(ctx, "billing_sync")
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params={**ctx.params_amenity, "keyword": p["room_no"]}, headers=ctx.headers_amenity)
    if err or res is None or res.status_code != 200:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("billing_sync", "", scenario, dur, response_payload={"__error__": err or "GET room-nos failed"})
    ci_serial = _extract_ci_serial(res)

    order_nos = f"BR-SYNC-{datetime.now().strftime('%m%d%H%M%S')}"
    payload = {"roomPayMain": {
        "ciSerial": str(ci_serial), "roomNos": p["room_no"], "orderNos": order_nos,
        "needTransfer": "N", "rsptCode": "2FFO", "rsptName": "2F櫃台",
        "mTimeCode": "LCH", "mTimeName": "午餐", "deskNos": "A02",
        "payAmount": 500, "acuAmount": 0, "precreditTotal": 0, "custType": "5",
    }, "roomPayDetail": [{"sequenceNos": 1, "productName": "牛排", "orderQuantity": 1, "specialAmount": 500, "precreditAmount": 0}]}
    res2, err2 = execute_for_ctx(ctx, "POST", ctx.urls["room_pay"], params=ctx.params_amenity, json_body=payload, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err2 or res2 is None or res2.status_code not in (200, 204):
        return _fail("billing_sync", "", scenario, dur, request_payload=payload, response_payload={"__error__": err2 or f"POST room-pay {getattr(res2,'status_code',None)}"})
    body2 = None
    try:
        body2 = res2.json()
    except Exception:
        body2 = {"status_code": res2.status_code}
    return _ok("billing_sync", "", scenario, dur, request_payload=payload, response_payload=body2)


# ====================================================================
# 🦏 小美犀負面路徑(對齊 SA 錯誤碼表:失敗一律 HTTP 417 + {code, message})
# PASS 條件 = 收到 417 且 code 與 SA 定義相符(反向斷言)。
# ====================================================================
@register_scenario(
    "room_nos_query_notfound", module="amenity", vendor="BR_AIELLO",
    name="查無房號(417・1001)", endpoint="/room-pay/room-nos",
)
def run_room_nos_query_notfound(ctx: RunContext) -> CaseResult:
    """SA 負面:查無此房號 → 417 code=1001(mock 以房號 9999 模擬無住客房)。"""
    import time as _t
    scenario = registry.get("room_nos_query_notfound")
    payload = {"keyword": "9999"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"],
                               params={**ctx.params_amenity, "keyword": "9999"}, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("room_nos_query_notfound", "", scenario, dur, request_payload=payload, response_payload={"__error__": err})
    return _expect_417("room_nos_query_notfound", scenario, dur, payload, res, "1001")


@register_scenario(
    "mifare_query_notfound", module="amenity", vendor="BR_AIELLO",
    name="查無卡號(417・1001)", endpoint="/room-pay/mifare-nos",
)
def run_mifare_query_notfound(ctx: RunContext) -> CaseResult:
    """SA 負面:查無此房卡卡號 → 417 code=1001(mock 以未註冊卡號模擬)。"""
    import time as _t
    scenario = registry.get("mifare_query_notfound")
    payload = {"keyword": "UNKNOWN0001"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["mifare_nos"],
                               params={**ctx.params_amenity, "keyword": "UNKNOWN0001"}, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("mifare_query_notfound", "", scenario, dur, request_payload=payload, response_payload={"__error__": err})
    return _expect_417("mifare_query_notfound", scenario, dur, payload, res, "1001")


@register_scenario(
    "amenity_billing_notfound", module="amenity", vendor="BR_AIELLO",
    name="入帳無住客(417・1001)", endpoint="/room-billing",
)
def run_amenity_billing_notfound(ctx: RunContext) -> CaseResult:
    """SA 負面:此房間無住客 → 417 code=1001(mock 以房號 9999 模擬,對齊 SA 失敗範例)。"""
    import time as _t
    scenario = registry.get("amenity_billing_notfound")
    payload = {"roomNos": "9999", "items": [{"seqNos": 1, "productNos": "M001", "orderQuantity": 1}]}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["room_billing"],
                               params=ctx.params_amenity, json_body=payload, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("amenity_billing_notfound", "", scenario, dur, request_payload=payload, response_payload={"__error__": err})
    return _expect_417("amenity_billing_notfound", scenario, dur, payload, res, "1001")


@register_scenario(
    "amenity_pay_duplicate", module="amenity", vendor="BR_AIELLO",
    name="重複掛帳(417・1010)", endpoint="/room-pay",
)
def run_amenity_pay_duplicate(ctx: RunContext) -> CaseResult:
    """SA 負面:同單號重複掛帳 → 417 code=1010(先成功掛一筆,再掛同單號)。"""
    import time as _t
    scenario = registry.get("amenity_pay_duplicate")
    t0 = _t.perf_counter()
    # Phase 1: GET room-nos 取 ciSerial
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"],
                               params={**ctx.params_amenity, "keyword": "11101"}, headers=ctx.headers_amenity)
    if err or res is None or res.status_code != 200:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("amenity_pay_duplicate", "", scenario, dur, response_payload={"__error__": err or "GET room-nos failed"})
    ci_serial = _extract_ci_serial(res)

    # Phase 2: 第一筆掛帳(應 200)
    order_nos = f"BR-DUP-{datetime.now().strftime('%m%d%H%M%S')}"
    pay_payload = {"roomPayMain": {
        "ciSerial": str(ci_serial), "roomNos": "11101", "orderNos": order_nos,
        "needTransfer": "N", "rsptCode": "2FFO", "rsptName": "2F櫃台",
        "mTimeCode": "LCH", "mTimeName": "午餐", "deskNos": "A06",
        "payAmount": 100, "acuAmount": 0, "precreditTotal": 0, "custType": "5",
    }, "roomPayDetail": [{"sequenceNos": 1, "productName": "重複掛帳測試", "orderQuantity": 1, "specialAmount": 100, "precreditAmount": 0}]}
    res2, err2 = execute_for_ctx(ctx, "POST", ctx.urls["room_pay"],
                                 params=ctx.params_amenity, json_body=pay_payload, headers=ctx.headers_amenity)
    if err2 or res2 is None or res2.status_code not in (200, 204):
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("amenity_pay_duplicate", "", scenario, dur, request_payload=pay_payload,
                     response_payload={"__error__": err2 or f"前置掛帳失敗 {getattr(res2,'status_code',None)}"})

    # Phase 3: 同單號重複掛帳 → 應 417/1010
    res3, err3 = execute_for_ctx(ctx, "POST", ctx.urls["room_pay"],
                                 params=ctx.params_amenity, json_body=pay_payload, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err3:
        return _fail("amenity_pay_duplicate", "", scenario, dur, request_payload=pay_payload, response_payload={"__error__": err3})
    return _expect_417("amenity_pay_duplicate", scenario, dur, pay_payload, res3, "1010")


@register_scenario(
    "amenity_cancel_notfound", module="amenity", vendor="BR_AIELLO",
    name="沖銷查無單(417・2001)", endpoint="/room-pay-cancel",
)
def run_amenity_cancel_notfound(ctx: RunContext) -> CaseResult:
    """SA 負面:取消不存在的掛帳單號 → 417 code=2001(掛帳資料找不到)。"""
    import time as _t
    scenario = registry.get("amenity_cancel_notfound")
    ghost_order = f"NO-SUCH-{datetime.now().strftime('%m%d%H%M%S')}"
    payload = {"orderNos": ghost_order}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["room_pay_cancel"],
                               params={**ctx.params_amenity, "orderNos": ghost_order}, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("amenity_cancel_notfound", "", scenario, dur, request_payload=payload, response_payload={"__error__": err})
    return _expect_417("amenity_cancel_notfound", scenario, dur, payload, res, "2001")
