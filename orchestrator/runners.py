# orchestrator/runners.py
"""案例執行器：把「發砲邏輯」包成回傳 CaseResult 的 runner，並註冊進 registry。

設計原則：
- 不重寫 hardware/simulate_speaker 的 payload 組裝，重用其 _execute_for_ctx（環境隔離版）。
- runner 簽章固定：(RunContext) -> CaseResult。成功 2xx → PASS，否則 FAIL。
- keycard 模組目前無執行器 → register_unimplemented（UI 顯示「待開發」）。
"""
from datetime import datetime

from .registry import registry, register_scenario
from .models import CaseResult, RunContext, CASE_PASS, CASE_FAIL

# 重用模擬器的環境隔離發射引擎 + 數據池料號載入
from hardware.simulate_speaker import execute_for_ctx, load_product_from_pool


# ---- 共用輔助 ----------------------------------------------------------
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


# ====================================================================
# 🦏 房務備品（amenity / BR_AIELLO）—— 重用 simulate_speaker 的情境邏輯
# ====================================================================

@register_scenario(
    "room_nos_query", module="amenity", vendor="BR_AIELLO",
    name="房號查詢", endpoint="/room-pay/room-nos",
)
def run_room_nos_query(ctx: RunContext) -> CaseResult:
    import time as _t
    scenario = registry.get("room_nos_query")
    params = {**ctx.params_amenity, "keyword": "11101"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params=params, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("room_nos_query", "", scenario, dur, response_payload={"__error__": err})
    body = res.json() if res is not None and res.status_code == 200 else None
    if res is not None and res.status_code == 200:
        return _ok("room_nos_query", "", scenario, dur, request_payload={"keyword": "11101"}, response_payload=body)
    return _fail("room_nos_query", "", scenario, dur, request_payload={"keyword": "11101"}, response_payload=body)


@register_scenario(
    "mifare_query", module="amenity", vendor="BR_AIELLO",
    name="Mifare 卡號查詢", endpoint="/room-pay/mifare-nos",
)
def run_mifare_query(ctx: RunContext) -> CaseResult:
    import time as _t
    scenario = registry.get("mifare_query")
    params = {**ctx.params_amenity, "keyword": "1A2B3C"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["mifare_nos"], params=params, headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("mifare_query", "", scenario, dur, response_payload={"__error__": err})
    body = res.json() if res is not None and res.status_code == 200 else None
    if res is not None and res.status_code == 200:
        return _ok("mifare_query", "", scenario, dur, request_payload={"keyword": "1A2B3C"}, response_payload=body)
    return _fail("mifare_query", "", scenario, dur, request_payload={"keyword": "1A2B3C"}, response_payload=body)


@register_scenario(
    "amenity_charge", module="amenity", vendor="BR_AIELLO",
    name="備品入帳", endpoint="/room-billing",
    expected_key="Scenario_1_Room_Nos_To_Billing",
)
def run_amenity_charge(ctx: RunContext) -> CaseResult:
    """房號查驗 → 備品過帳（GET 取 ciSerial 後 POST /room-billing）。"""
    import time as _t
    scenario = registry.get("amenity_charge")
    t0 = _t.perf_counter()
    # Phase 1: GET room-nos 取 ciSerial
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params={**ctx.params_amenity, "keyword": "11101"}, headers=ctx.headers_amenity)
    if err or res is None or res.status_code != 200:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("amenity_charge", "", scenario, dur, response_payload={"__error__": err or f"GET room-nos {getattr(res,'status_code',None)}"})
    ci_serial = _extract_ci_serial(res)

    # Phase 2: POST room-billing
    payload = {"roomNos": "11101", "items": [{"seqNos": 1, "productNos": load_product_from_pool("M001"), "orderQuantity": 1}]}
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
    name="入帳沖銷", endpoint="/room-pay-cancel",
    expected_key="Scenario_3_Room_Nos_Pay_And_Cancel",
)
def run_amenity_cancel(ctx: RunContext) -> CaseResult:
    """住掛 → 沖正作廢（先 POST /room-pay 取得單號，再 POST /room-pay-cancel）。"""
    import time as _t
    scenario = registry.get("amenity_cancel")
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params={**ctx.params_amenity, "keyword": "11101"}, headers=ctx.headers_amenity)
    if err or res is None or res.status_code != 200:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("amenity_cancel", "", scenario, dur, response_payload={"__error__": err or "GET room-nos failed"})
    ci_serial = _extract_ci_serial(res)

    order_nos = f"BR-ORCH-{datetime.now().strftime('%m%d%H%M%S')}"
    pay_payload = {"roomPayMain": {
        "ciSerial": str(ci_serial), "roomNos": "11101", "orderNos": order_nos,
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
    name="帳務同步", endpoint="/room-pay",
    expected_key="Scenario_2_Room_Nos_To_Pay",
)
def run_billing_sync(ctx: RunContext) -> CaseResult:
    """房號查驗 → 餐廳住掛（POST /room-pay）。"""
    import time as _t
    scenario = registry.get("billing_sync")
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["room_nos"], params={**ctx.params_amenity, "keyword": "11101"}, headers=ctx.headers_amenity)
    if err or res is None or res.status_code != 200:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("billing_sync", "", scenario, dur, response_payload={"__error__": err or "GET room-nos failed"})
    ci_serial = _extract_ci_serial(res)

    order_nos = f"BR-SYNC-{datetime.now().strftime('%m%d%H%M%S')}"
    payload = {"roomPayMain": {
        "ciSerial": str(ci_serial), "roomNos": "11101", "orderNos": order_nos,
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


@register_scenario(
    "room_nos_query_notfound", module="amenity", vendor="BR_AIELLO",
    name="查無房號(417/1001)", endpoint="/room-pay/room-nos",
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
    name="查無房卡卡號(417/1001)", endpoint="/room-pay/mifare-nos",
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
    name="備品入帳無住客(417/1001)", endpoint="/room-billing",
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
    name="重複掛帳(417/1010)", endpoint="/room-pay",
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
    name="取消查無單號(417/2001)", endpoint="/room-pay-cancel",
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


# ====================================================================
# 🚗 停車車辨（parking / SHIN_YEONG）—— 至少接入 car_arrival
# ====================================================================
@register_scenario(
    "car_arrival", module="parking", vendor="SHIN_YEONG",
    name="車輛抵達回推", endpoint="/car-arrival",
)
def run_car_arrival(ctx: RunContext) -> CaseResult:
    """模擬車辨回推車輛抵達。先 check-in 落庫白名單，再觸發 car-arrival（car_arrival 需 guest 在白名單）。"""
    import time as _t
    scenario = registry.get("car_arrival")
    ts = datetime.now().strftime("%m%d%H%M%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    guest_id, car = f"G-{ts}", f"ABC-{ts}"
    # 先 check-in 落庫（car_arrival 路由會查 mock_vendor_db，無此 guest 會 404）
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": car, "guest_name": "Orchestrator", "start_date": now, "end_date": now})
    payload = {"guest_id": guest_id, "car_number": car, "guest_name": "Orchestrator", "arrival_time": now}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["car_arrival"], params=ctx.params_parking, json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("car_arrival", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code, "text": getattr(res, "text", "")[:200]}
    if res.status_code == 200:
        return _ok("car_arrival", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("car_arrival", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "checkin_sync", module="parking", vendor="SHIN_YEONG",
    name="住客入住同步", endpoint="/check-in",
)
def run_checkin_sync(ctx: RunContext) -> CaseResult:
    """PMS→廠商方向：模擬 PMS 推播住客 check-in 落庫（建立白名單）。"""
    import time as _t
    scenario = registry.get("checkin_sync")
    ts = datetime.now().strftime("%m%d%H%M")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "guest_id": f"G-{ts}", "car_number": f"ABC-{ts}",
        "guest_name": "Orchestrator", "start_date": now, "end_date": now,
    }
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("checkin_sync", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200:
        return _ok("checkin_sync", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("checkin_sync", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "whitelist_update", module="parking", vendor="SHIN_YEONG",
    name="PMS 白名單異動", endpoint="/internal/whitelist",
)
def run_whitelist_update(ctx: RunContext) -> CaseResult:
    """驗證白名單查詢端點回傳當前落庫的住客字典（GET /parking/internal/whitelist）。"""
    import time as _t
    scenario = registry.get("whitelist_update")
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "GET", ctx.urls["whitelist"])
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("whitelist_update", "", scenario, dur, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200:
        return _ok("whitelist_update", "", scenario, dur, request_payload=None, response_payload=body)
    return _fail("whitelist_update", "", scenario, dur, response_payload=body)


@register_scenario(
    "night_audit", module="parking", vendor="SHIN_YEONG",
    name="夜核名單同步", endpoint="/pms-sync-data/night-audit",
)
def run_night_audit(ctx: RunContext) -> CaseResult:
    """PMS→廠商夜核:POST /pms-sync-data/night-audit 推播夜核住客名單(增量 Upsert)。"""
    import time as _t
    scenario = registry.get("night_audit")
    ts = datetime.now().strftime("%m%d%H%M%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "guest_id": f"G-AUDIT-{ts}", "car_number": f"AUD-{ts}",
        "guest_name": "NightAudit", "start_date": now, "end_date": now,
    }
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["night_audit"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("night_audit", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200:
        return _ok("night_audit", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("night_audit", "", scenario, dur, request_payload=payload, response_payload=body)


# ---- 新詠(SHIN_YEONG)PMS→廠商方向剩餘 3 條串接 API(路由+解析器早已存在,補 runner) ----
# 模式同 car_arrival：先 check-in 落庫白名單，再打目��路由；這些 /pms-sync-data/* 無 auth gate。
@register_scenario(
    "change_checkout", module="parking", vendor="SHIN_YEONG",
    name="延長/修改退房", endpoint="/pms-sync-data/change-checkout-datetime",
)
def run_change_checkout(ctx: RunContext) -> CaseResult:
    """PMS→廠商:綜合櫃台延長/修改退房時間(CHANGE_CKO_DATE_TIME)。"""
    import time as _t
    scenario = registry.get("change_checkout")
    ts = datetime.now().strftime("%m%d%H%M%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    guest_id, car = f"G-CKO-{ts}", f"CKO-{ts}"
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": car, "guest_name": "Orchestrator",
        "start_date": now, "end_date": now})
    payload = {"guest_id": guest_id, "end_date": "2026-12-31 12:00:00", "car_number": car, "enabled": "Y"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["change_checkout"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("change_checkout", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200:
        return _ok("change_checkout", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("change_checkout", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "change_car_nos", module="parking", vendor="SHIN_YEONG",
    name="車牌三態異動", endpoint="/pms-sync-data/change-car-nos",
)
def run_change_car_nos(ctx: RunContext) -> CaseResult:
    """PMS→廠商:綜合櫃台車牌異動(CHG_CAR_NOS,新增/清除/更新三態)。"""
    import time as _t
    scenario = registry.get("change_car_nos")
    ts = datetime.now().strftime("%m%d%H%M%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    guest_id, car = f"G-CHG-{ts}", f"OLD-{ts}"
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": car, "guest_name": "Orchestrator",
        "start_date": now, "end_date": now})
    payload = {"guest_id": guest_id, "car_number": f"NEW-{ts}", "enabled": "Y"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["change_car_nos"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("change_car_nos", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200:
        return _ok("change_car_nos", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("change_car_nos", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "check_in_cancel", module="parking", vendor="SHIN_YEONG",
    name="取消入住", endpoint="/pms-sync-data/check-in-cancel",
)
def run_check_in_cancel(ctx: RunContext) -> CaseResult:
    """PMS→廠商:取消入住(CIX),廠商保留車牌供離場驗證。"""
    import time as _t
    scenario = registry.get("check_in_cancel")
    ts = datetime.now().strftime("%m%d%H%M%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    guest_id, car = f"G-CIX-{ts}", f"CIX-{ts}"
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": car, "guest_name": "Orchestrator",
        "start_date": now, "end_date": now})
    payload = {"guest_id": guest_id, "car_number": car, "end_date": now, "enabled": "Y"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["check_in_cancel"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("check_in_cancel", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200:
        return _ok("check_in_cancel", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("check_in_cancel", "", scenario, dur, request_payload=payload, response_payload=body)


# ====================================================================
# 🚗 停車車辨（parking / PAYTRONEX）—— 博辰專屬路由(/parktron/hpms/services/roomer/*)
# 注意:PAYTRONEX 與 SHIN_YEONG 的 API 合約不同(endpoint + payload shape),故獨立 runner。
# ====================================================================
@register_scenario(
    "car_arrival_pt", module="parking", vendor="PAYTRONEX",
    name="新增房客預約(車輛抵達)", endpoint="/parktron/hpms/services/roomer/add",
)
def run_paytronex_add(ctx: RunContext) -> CaseResult:
    """PAYTRONEX:POST /parktron/hpms/services/roomer/add 新增房客預約(帶車牌)。"""
    import time as _t
    scenario = registry.get("car_arrival_pt")
    ts = datetime.now().strftime("%m%d%H%M%S")
    payload = {"Roomer": {
        "RoomNumber": "207", "StartTime": "2026-08-12T15:00:00", "EndTime": "2026-08-13T12:00:00",
        "LicensePlateList": [f"PT-{ts}"],
    }}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_add"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("car_arrival_pt", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200 and str(body.get("resultCode", "")) == "0000":
        return _ok("car_arrival_pt", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("car_arrival_pt", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "car_arrival_retry", module="parking", vendor="PAYTRONEX",
    name="車牌逆查(逾時重試)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate",
)
def run_paytronex_find(ctx: RunContext) -> CaseResult:
    """PAYTRONEX:先 add_roomer 建租約,再 findByLicensePlate 逆查(模擬車辨感應 → 查租約)。

    若查無對應租約,mock 會動態就地合法(建虛擬租約),故應回 200 + roomer。
    """
    import time as _t
    scenario = registry.get("car_arrival_retry")
    ts = datetime.now().strftime("%m%d%H%M%S")
    plate = f"FIND-{ts}"
    t0 = _t.perf_counter()
    # 先 add 建立含該車牌的租約
    execute_for_ctx(ctx, "POST", ctx.urls["paytronex_add"], json_body={"Roomer": {
        "RoomNumber": "209", "StartTime": "2026-08-12T15:00:00", "EndTime": "2026-08-13T12:00:00",
        "LicensePlateList": [plate],
    }})
    # 再逆查
    payload = {"LicensePlate": plate}
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_find"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("car_arrival_retry", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200 and body.get("roomer"):
        return _ok("car_arrival_retry", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("car_arrival_retry", "", scenario, dur, request_payload=payload, response_payload=body)


# （原本 checkin_sync/whitelist_update/car_arrival_retry 的 UNIMPLEMENTED 註冊已由上方實作取代）


# ====================================================================
# 🔑 門禁製卡（keycard / WAFERLOCK_LIVEAM）
# 方向提醒：此處 mock 模擬的是「廠商 API 面」，執行器扮 PMS（PMS→vendor 製卡），
# 與真實情境（vendor→PMS）相反。真實方向的 vendor→PMS 閉環目前無 PMS 接收端可測
# （需另補 PMS 側 mock，屬架構擴充）。下列案例測的是「跨模組卡片生命週期閉環」：
# 製卡（寫入 mock_card_mapping_db）→ 用該卡號走 amenity mifare 刷回房號 → 斷言一致。
# ====================================================================
def _keycard_auth_headers(ctx):
    """keycard 製卡路由的 auth gate：LOCAL 模式帶 LOCAL_TOKEN；其餘沿用 ctx.headers。"""
    h = dict(ctx.headers)
    if not ctx.use_real:
        h["Authorization"] = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"  # config.LOCAL_TOKEN
    return h


@register_scenario(
    "card_issue", module="keycard", vendor="WAFERLOCK",
    name="製卡發卡", endpoint="/api/OrderCard",
)
def run_card_issue(ctx: RunContext) -> CaseResult:
    """PMS→vendor 製卡：建 order → POST /api/OrderCard 製卡，拿回 cardUid。"""
    import time as _t
    scenario = registry.get("card_issue")
    ts = datetime.now().strftime("%m%d%H%M%S")
    order_id, room = f"KC-ISSUE-{ts}", "207"
    h = _keycard_auth_headers(ctx)
    t0 = _t.perf_counter()
    # 建 order（廠商有「查無 order 自動補」防禦，但正規流程先建）
    execute_for_ctx(ctx, "POST", ctx.urls["keycard_order"], headers=h,
                    json_body={"ikey": order_id, "roomNos": room, "guestName": "KeycardIssue"})
    # 製卡
    payload = {"ikey": order_id, "pmrId": "801F12A3D8CA", "roomNos": room, "guestName": "KeycardIssue"}
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["keycard_ordercard"], headers=h, json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("card_issue", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code in (200, 201) and body.get("cardUid"):
        return _ok("card_issue", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("card_issue", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "card_revoke", module="keycard", vendor="WAFERLOCK",
    name="消卡", endpoint="/api/OrderCard/<oid>/<cuid>",
)
def run_card_revoke(ctx: RunContext) -> CaseResult:
    """PMS→vendor 銷卡：先製卡拿 cardUid，再 DELETE /api/OrderCard/<oid>/<cuid>。"""
    import time as _t
    scenario = registry.get("card_revoke")
    ts = datetime.now().strftime("%m%d%H%M%S")
    order_id, room = f"KC-REVOKE-{ts}", "208"
    h = _keycard_auth_headers(ctx)
    t0 = _t.perf_counter()
    # 先製卡
    execute_for_ctx(ctx, "POST", ctx.urls["keycard_order"], headers=h,
                    json_body={"ikey": order_id, "roomNos": room, "guestName": "KeycardRevoke"})
    make = execute_for_ctx(ctx, "POST", ctx.urls["keycard_ordercard"], headers=h,
                           json_body={"ikey": order_id, "pmrId": "801F12A3D8CA", "roomNos": room, "guestName": "KeycardRevoke"})
    res_mk, err_mk = make
    if err_mk or res_mk is None or not res_mk.json().get("cardUid"):
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("card_revoke", "", scenario, dur, response_payload={"__error__": "前置製卡失敗"})
    card_uid = res_mk.json()["cardUid"]
    # 銷卡
    del_url = f"{ctx.urls['keycard_ordercard']}/{order_id}/{card_uid}"
    res, err = execute_for_ctx(ctx, "DELETE", del_url, headers=h)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("card_revoke", "", scenario, dur, request_payload={"orderID": order_id, "cardUid": card_uid}, response_payload={"__error__": err or "no response"})
    body = {"status_code": res.status_code}
    if res.status_code in (200, 204):
        return _ok("card_revoke", "", scenario, dur, request_payload={"orderID": order_id, "cardUid": card_uid}, response_payload=body)
    return _fail("card_revoke", "", scenario, dur, request_payload={"orderID": order_id, "cardUid": card_uid}, response_payload=body)


@register_scenario(
    "order_query", module="keycard", vendor="WAFERLOCK",
    name="訂單狀態逆查", endpoint="/api/Operation/getCardInfo/<pmrId>",
)
def run_order_query(ctx: RunContext) -> CaseResult:
    """PMS→vendor 讀卡機逆查：POST /api/Operation/getCardInfo/<pmrId>，模擬讀卡機感應。"""
    import time as _t
    scenario = registry.get("order_query")
    h = _keycard_auth_headers(ctx)
    pmr_id = "801F12A3D8CA"
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", f"{ctx.urls['keycard_ordercard'].replace('/api/OrderCard','')}/api/Operation/getCardInfo/{pmr_id}", headers=h)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("order_query", "", scenario, dur, response_payload={"__error__": err or "no response"})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    if res.status_code == 200 and body.get("cardUid"):
        return _ok("order_query", "", scenario, dur, request_payload={"pmrId": pmr_id}, response_payload=body)
    return _fail("order_query", "", scenario, dur, request_payload={"pmrId": pmr_id}, response_payload=body)


@register_scenario(
    "card_lifecycle", module="keycard", vendor="WAFERLOCK",
    name="跨模組卡片生命週期閉環（製卡→mifare 刷回房號）", endpoint="/api/OrderCard + /room-pay/mifare-nos",
)
def run_card_lifecycle(ctx: RunContext) -> CaseResult:
    """B 閉環：keycard 製卡（寫入 mock_card_mapping_db）→ 用 cardUid 走 amenity mifare 查詢
    刷回房號 → 斷言房號與製卡時一致。跨廠商（門禁→房務）整合閉環。"""
    import time as _t
    scenario = registry.get("card_lifecycle")
    ts = datetime.now().strftime("%m%d%H%M%S")
    order_id, room = f"KC-LIFE-{ts}", "309"
    h = _keycard_auth_headers(ctx)
    t0 = _t.perf_counter()

    # 1) keycard 製卡
    execute_for_ctx(ctx, "POST", ctx.urls["keycard_order"], headers=h,
                    json_body={"ikey": order_id, "roomNos": room, "guestName": "Lifecycle"})
    mk = execute_for_ctx(ctx, "POST", ctx.urls["keycard_ordercard"], headers=h,
                         json_body={"ikey": order_id, "pmrId": "801F12A3D8CA", "roomNos": room, "guestName": "Lifecycle"})
    res_mk, err_mk = mk
    if err_mk or res_mk is None or not res_mk.json().get("cardUid"):
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("card_lifecycle", "", scenario, dur, response_payload={"__error__": "製卡階段失敗"})
    card_uid = res_mk.json()["cardUid"]

    # 2) 用該 cardUid 走 amenity mifare 查詢（跨模組）
    res_mf, err_mf = execute_for_ctx(ctx, "GET", ctx.urls["mifare_nos"],
                                     params={**ctx.params_amenity, "keyword": card_uid},
                                     headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err_mf or res_mf is None or res_mf.status_code != 200:
        return _fail("card_lifecycle", "", scenario, dur,
                     request_payload={"cardUid": card_uid, "expected_room": room},
                     response_payload={"__error__": err_mf or f"mifare {getattr(res_mf,'status_code',None)}"})

    # 3) 斷言刷回房號 == 製卡房號
    read_room = _extract_room_nos(res_mf)
    response_payload = {"cardUid": card_uid, "manufactured_room": room, "mifare_read_room": read_room}
    if str(read_room) == str(room):
        return _ok("card_lifecycle", "", scenario, dur,
                   request_payload={"cardUid": card_uid, "expected_room": room}, response_payload=response_payload)
    # 房號不符 → 欄位 diff
    cr = _fail("card_lifecycle", "", scenario, dur,
               request_payload={"cardUid": card_uid, "expected_room": room}, response_payload=response_payload)
    cr.diff = [{"field": "roomNos", "expected": room, "actual": read_room}]
    return cr


# ====================================================================
# 🔑 門禁製卡（keycard / LIVEAM）—— 華豫寧��製面(/key-card-management/liveam/*)
# 不同於 WAFERLOCK 的 /api/Order* 面;LIVEAM 走 /key-card-management 路由。
# 製卡例外重試:先登錄為 UNIMPLEMENTED(LIVEAM 客製路由合約待補 runner)。
# ====================================================================
registry.register_unimplemented(
    "card_issue_exception", module="keycard", vendor="LIVEAM",
    name="製卡例外重試", endpoint="/key-card-management/liveam/create-card",
)
