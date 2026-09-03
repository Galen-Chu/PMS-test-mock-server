# orchestrator/runners.py
"""案例執行器：把「發砲邏輯」包成回傳 CaseResult 的 runner，並註冊進 registry。

設計原則：
- 不重寫 hardware/simulate_speaker 的 payload 組裝，重用其 _execute_for_ctx（環境隔離版）。
- runner 簽章固定：(RunContext) -> CaseResult。成功 2xx → PASS，否則 FAIL。
- 案例參數化（docs/design-case-parameterization.md）：案例宣告 ParamSpec，
  runner 以 ``_p(ctx, case_id)`` 取合併後參數組 payload；不帶覆寫時
  resolved 值 = 預設 = 參數化前的硬編值（行為 100% 相同，向後相容硬約束）。
"""
from datetime import datetime, timedelta
from urllib.parse import quote

from .registry import registry, register_scenario
from .models import CaseResult, RunContext, ParamSpec, CASE_PASS, CASE_FAIL

# 重用模擬器的環境隔離發射引擎 + 數據池料號載入
from hardware.simulate_speaker import execute_for_ctx, load_product_from_pool


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


# ====================================================================
# 🦏 房務備品（amenity / BR_AIELLO）—— 重用 simulate_speaker 的情境邏輯
# ====================================================================

@register_scenario(
    "room_nos_query", module="amenity", vendor="BR_AIELLO",
    name="房號查詢", endpoint="/room-pay/room-nos",
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
    name="Mifare 卡號查詢", endpoint="/room-pay/mifare-nos",
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
    name="備品入帳", endpoint="/room-billing",
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
    name="入帳沖銷", endpoint="/room-pay-cancel",
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
    name="帳務同步", endpoint="/room-pay",
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
    params=[
        ParamSpec("car_number", "車牌", "str",
                  default=lambda ctx: f"ABC-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("guest_name", "住客名", "str", "Orchestrator"),
        ParamSpec("arrival_time", "抵達時間", "datetime",
                  default=lambda ctx: _sa_now(), hint="SA v1.2 格式 yyyy/mm/dd hh:mm(無秒)"),
    ],
)
def run_car_arrival(ctx: RunContext) -> CaseResult:
    """模擬車辨回推車輛抵達。先 check-in 落庫白名單，再觸發 car-arrival（car_arrival 需 guest 在白名單）。"""
    import time as _t
    scenario = registry.get("car_arrival")
    p = _p(ctx, "car_arrival")
    guest_id = f"G-{_ts()}"  # 內部動態唯一 ID(未宣告為參數,保證每次 run 白名單隔離)
    # 先 check-in 落庫（car_arrival 路由會查 mock_vendor_db，無此 guest 會 417）
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": p["car_number"], "guest_name": p["guest_name"],
        "start_date": p["arrival_time"], "end_date": p["arrival_time"], "is_enabled": "Yes"})
    payload = {"guest_id": guest_id, "car_number": p["car_number"], "guest_name": p["guest_name"], "arrival_time": p["arrival_time"]}
    t0 = _t.perf_counter()
    # 💡 SA v1.2:出站帶 athena/hotel headers、query 僅 thirdParty
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["car_arrival"], params=ctx.params_parking, headers=ctx.headers_parking, json_body=payload)
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
    params=[
        ParamSpec("car_number", "車牌", "str",
                  default=lambda ctx: f"ABC-{datetime.now().strftime('%m%d%H%M')}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("guest_name", "住客名", "str", "Orchestrator"),
        ParamSpec("start_date", "入住時間", "datetime", default=lambda ctx: _sa_now(), hint="yyyy/mm/dd hh:mm"),
        ParamSpec("end_date", "退房時間", "datetime", default=lambda ctx: _sa_now(), hint="yyyy/mm/dd hh:mm"),
    ],
)
def run_checkin_sync(ctx: RunContext) -> CaseResult:
    """PMS→廠商方向：模擬 PMS 推播住客 check-in 落庫（建立白名單）。"""
    import time as _t
    scenario = registry.get("checkin_sync")
    p = _p(ctx, "checkin_sync")
    payload = {
        "guest_id": f"G-{datetime.now().strftime('%m%d%H%M')}", "car_number": p["car_number"],
        "guest_name": p["guest_name"], "start_date": p["start_date"], "end_date": p["end_date"],
        "is_enabled": "Yes",  # 💡 SA v1.2 欄位(值域 Yes/No)
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
    params=[
        ParamSpec("car_number", "車牌", "str",
                  default=lambda ctx: f"AUD-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("guest_name", "住客名", "str", "NightAudit"),
        ParamSpec("start_date", "入住時間", "datetime", default=lambda ctx: _sa_now()),
        ParamSpec("end_date", "退房時間", "datetime", default=lambda ctx: _sa_now()),
    ],
)
def run_night_audit(ctx: RunContext) -> CaseResult:
    """PMS→廠商夜核:POST /pms-sync-data/night-audit 推播夜核住客名單(增量 Upsert)。"""
    import time as _t
    scenario = registry.get("night_audit")
    p = _p(ctx, "night_audit")
    payload = {
        "guest_id": f"G-AUDIT-{_ts()}", "car_number": p["car_number"],
        "guest_name": p["guest_name"], "start_date": p["start_date"], "end_date": p["end_date"],
        "is_enabled": "Yes",
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
    params=[
        ParamSpec("car_number", "原車牌", "str",
                  default=lambda ctx: f"CKO-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("end_date", "新退房時間", "datetime", "2026/12/31 12:00", hint="yyyy/mm/dd hh:mm"),
    ],
)
def run_change_checkout(ctx: RunContext) -> CaseResult:
    """PMS→廠商:綜合櫃台延長/修改退房時間(CHANGE_CKO_DATE_TIME)。"""
    import time as _t
    scenario = registry.get("change_checkout")
    p = _p(ctx, "change_checkout")
    now = _sa_now()
    guest_id = f"G-CKO-{_ts()}"
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": p["car_number"], "guest_name": "Orchestrator",
        "start_date": now, "end_date": now, "is_enabled": "Yes"})
    payload = {"guest_id": guest_id, "end_date": p["end_date"], "car_number": p["car_number"], "is_enabled": "Yes"}
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
    params=[
        ParamSpec("old_car_number", "原車牌", "str",
                  default=lambda ctx: f"OLD-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("new_car_number", "新車牌", "str",
                  default=lambda ctx: f"NEW-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
    ],
)
def run_change_car_nos(ctx: RunContext) -> CaseResult:
    """PMS→廠商:綜合櫃台車牌異動(CHG_CAR_NOS,新增/清除/更新三態)。"""
    import time as _t
    scenario = registry.get("change_car_nos")
    p = _p(ctx, "change_car_nos")
    now = _sa_now()
    guest_id = f"G-CHG-{_ts()}"
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": p["old_car_number"], "guest_name": "Orchestrator",
        "start_date": now, "end_date": now, "is_enabled": "Yes"})
    payload = {"guest_id": guest_id, "car_number": p["new_car_number"], "is_enabled": "Yes"}
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
    params=[
        ParamSpec("car_number", "車牌", "str",
                  default=lambda ctx: f"CIX-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("end_date", "結束時間", "datetime", default=lambda ctx: _sa_now(), hint="yyyy/mm/dd hh:mm"),
    ],
)
def run_check_in_cancel(ctx: RunContext) -> CaseResult:
    """PMS→廠商:取消入住(CIX),廠商保留車牌供離場驗證。"""
    import time as _t
    scenario = registry.get("check_in_cancel")
    p = _p(ctx, "check_in_cancel")
    now = _sa_now()
    guest_id = f"G-CIX-{_ts()}"
    execute_for_ctx(ctx, "POST", ctx.urls["check_in"], json_body={
        "guest_id": guest_id, "car_number": p["car_number"], "guest_name": "Orchestrator",
        "start_date": now, "end_date": now, "is_enabled": "Yes"})
    payload = {"guest_id": guest_id, "car_number": p["car_number"], "end_date": p["end_date"], "is_enabled": "Yes"}
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
# 🚗 新詠 SA v1.2 公版單一端點情境(POST /parking/sync)
# 德安所有停車事件(入住/改車號/改C-O/取消入住/夜核)皆以「同一 schema」打到廠商唯一 URL,
# is_enabled("Yes"/"No")控啟停;回應 {code, message}(0000=成功,其餘失敗)。
# ====================================================================
def _sync_expect(case_id, scenario, dur, payload, res, expect_code="0000"):
    """公版單一端點共用判定:HTTP 200 且 body.code 相符 → PASS。"""
    body = None
    try:
        body = res.json()
    except Exception:
        body = {}
    if res.status_code == 200 and body.get("code") == expect_code:
        return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=body)


def _sa_sync_payload(guest_id, car, enabled="Yes", start=None, end=None, guest_name="Orchestrator"):
    """組 SA v1.2 公版 schema payload(時間 yyyy/mm/dd hh:mm 無秒)。"""
    now_sa = _sa_now()
    return {
        "guest_id": guest_id, "car_number": car, "guest_name": guest_name,
        "start_date": start or now_sa, "end_date": end or now_sa,
        "is_enabled": enabled,
    }


@register_scenario(
    "parking_sync_checkin", module="parking", vendor="SHIN_YEONG",
    name="公版入住啟用", endpoint="/parking/sync",
    params=[
        ParamSpec("car_number", "車牌", "str",
                  default=lambda ctx: f"SY-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("guest_name", "住客名", "str", "Orchestrator"),
        ParamSpec("start_date", "入住時間", "datetime", default=lambda ctx: _sa_now()),
        ParamSpec("end_date", "退房時間", "datetime", default=lambda ctx: _sa_now()),
    ],
)
def run_parking_sync_checkin(ctx: RunContext) -> CaseResult:
    """SA 公版:入住且有車號 → 傳送啟用(Yes),廠商 upsert。"""
    import time as _t
    scenario = registry.get("parking_sync_checkin")
    p = _p(ctx, "parking_sync_checkin")
    payload = _sa_sync_payload(f"G-SYNC-{_ts()}", p["car_number"], "Yes",
                               start=p["start_date"], end=p["end_date"], guest_name=p["guest_name"])
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["parking_sync"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("parking_sync_checkin", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    return _sync_expect("parking_sync_checkin", scenario, dur, payload, res)


@register_scenario(
    "parking_sync_change_car", module="parking", vendor="SHIN_YEONG",
    name="公版換車號(舊停用+新啟用兩筆)", endpoint="/parking/sync",
    params=[
        ParamSpec("guest_name", "住客名", "str", "Orchestrator"),
        ParamSpec("old_car_number", "原車牌", "str",
                  default=lambda ctx: f"OLD-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("new_car_number", "新車牌", "str",
                  default=lambda ctx: f"NEW-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
    ],
)
def run_parking_sync_change_car(ctx: RunContext) -> CaseResult:
    """SA 公版範例 3:更改車號 → 兩筆連發(原車號 No + 新車號 Yes),兩筆皆應 0000。"""
    import time as _t
    scenario = registry.get("parking_sync_change_car")
    p = _p(ctx, "parking_sync_change_car")
    guest_id = f"G-CHC-{_ts()}"
    t0 = _t.perf_counter()
    payload_old = _sa_sync_payload(guest_id, p["old_car_number"], "No", guest_name=p["guest_name"])
    res1, err1 = execute_for_ctx(ctx, "POST", ctx.urls["parking_sync"], json_body=payload_old)
    payload_new = _sa_sync_payload(guest_id, p["new_car_number"], "Yes", guest_name=p["guest_name"])
    res2, err2 = execute_for_ctx(ctx, "POST", ctx.urls["parking_sync"], json_body=payload_new)
    dur = int((_t.perf_counter() - t0) * 1000)
    summary = {"disable_old": payload_old, "enable_new": payload_new}
    if err1 or res1 is None or err2 or res2 is None:
        return _fail("parking_sync_change_car", "", scenario, dur, request_payload=summary,
                     response_payload={"__error__": err1 or err2 or "no response"})
    try:
        codes = {"disable_old_code": res1.json().get("code"), "enable_new_code": res2.json().get("code")}
    except Exception:
        codes = {"disable_old_code": None, "enable_new_code": None}
    if res1.status_code == 200 and res2.status_code == 200 \
            and codes["disable_old_code"] == "0000" and codes["enable_new_code"] == "0000":
        return _ok("parking_sync_change_car", "", scenario, dur, request_payload=summary, response_payload=codes)
    return _fail("parking_sync_change_car", "", scenario, dur, request_payload=summary, response_payload=codes)


@register_scenario(
    "parking_sync_disable", module="parking", vendor="SHIN_YEONG",
    name="公版清除車號(停用)", endpoint="/parking/sync",
    params=[
        ParamSpec("car_number", "車牌", "str",
                  default=lambda ctx: f"DIS-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("guest_name", "住客名", "str", "Orchestrator"),
    ],
)
def run_parking_sync_disable(ctx: RunContext) -> CaseResult:
    """SA 公版範例 4:清除車號 → 傳送原車號停用(No)。"""
    import time as _t
    scenario = registry.get("parking_sync_disable")
    p = _p(ctx, "parking_sync_disable")
    payload = _sa_sync_payload(f"G-DIS-{_ts()}", p["car_number"], "No", guest_name=p["guest_name"])
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["parking_sync"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("parking_sync_disable", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    return _sync_expect("parking_sync_disable", scenario, dur, payload, res)


@register_scenario(
    "parking_sync_cancel", module="parking", vendor="SHIN_YEONG",
    name="公版取消入住(當日結束)", endpoint="/parking/sync",
    params=[
        ParamSpec("car_number", "車牌", "str",
                  default=lambda ctx: f"CXL-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
        ParamSpec("guest_name", "住客名", "str", "Orchestrator"),
        ParamSpec("end_date", "結束時間", "datetime",
                  default=lambda ctx: f"{datetime.now().strftime('%Y/%m/%d')} 23:59", hint="SA 範例 5:當日最晚 23:59"),
    ],
)
def run_parking_sync_cancel(ctx: RunContext) -> CaseResult:
    """SA 公版範例 5:取消入住 → is_enabled Yes、結束日為當日最晚(23:59)。"""
    import time as _t
    scenario = registry.get("parking_sync_cancel")
    p = _p(ctx, "parking_sync_cancel")
    payload = _sa_sync_payload(f"G-CXL-{_ts()}", p["car_number"], "Yes",
                               end=p["end_date"], guest_name=p["guest_name"])
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["parking_sync"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("parking_sync_cancel", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    return _sync_expect("parking_sync_cancel", scenario, dur, payload, res)


@register_scenario(
    "parking_sync_invalid", module="parking", vendor="SHIN_YEONG",
    name="公版參數錯誤(is_enabled 非法)", endpoint="/parking/sync",
)
def run_parking_sync_invalid(ctx: RunContext) -> CaseResult:
    """SA 公版負面:is_enabled 非 Yes/No → code 1000(反向斷言)。"""
    import time as _t
    scenario = registry.get("parking_sync_invalid")
    ts = datetime.now().strftime("%m%d%H%M%S")
    payload = _sa_sync_payload(f"G-INV-{ts}", f"INV-{ts}", "X")  # 非法值
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["parking_sync"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("parking_sync_invalid", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    return _sync_expect("parking_sync_invalid", scenario, dur, payload, res, expect_code="1000")


@register_scenario(
    "car_arrival_missing_field", module="parking", vendor="SHIN_YEONG",
    name="車輛抵達缺必填(417/1000)", endpoint="/external/vendor-sync-data/car-arrival",
)
def run_car_arrival_missing_field(ctx: RunContext) -> CaseResult:
    """SA v1.2 負面:必填欄位缺值(car_number)→ 417 + code 1000 "xxx is required"。"""
    import time as _t
    scenario = registry.get("car_arrival_missing_field")
    payload = {"guest_id": "G-NEVER-EXIST", "arrival_time": datetime.now().strftime("%Y/%m/%d %H:%M")}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["car_arrival"],
                               params=ctx.params_parking, headers=ctx.headers_parking, json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail("car_arrival_missing_field", "", scenario, dur, request_payload=payload, response_payload={"__error__": err})
    return _expect_417("car_arrival_missing_field", scenario, dur, payload, res, "1000")


# ====================================================================
# 🚗 停車車辨（parking / PAYTRONEX）—— 博辰專屬路由(/parktron/hpms/services/roomer/*)
# 注意:PAYTRONEX 與 SHIN_YEONG 的 API 合約不同(endpoint + payload shape),故獨立 runner。
# ====================================================================
@register_scenario(
    "car_arrival_pt", module="parking", vendor="PAYTRONEX",
    name="新增房客預約(車輛抵達)", endpoint="/parktron/hpms/services/roomer/add",
    params=[
        ParamSpec("room_number", "房號", "str", "207"),
        ParamSpec("license_plate", "車牌", "str",
                  default=lambda ctx: f"PT-{_ts()}", hint="留自動=每次執行產生唯一車牌"),
    ],
)
def run_paytronex_add(ctx: RunContext) -> CaseResult:
    """PAYTRONEX:POST /parktron/hpms/services/roomer/add 新增房客預約(帶車牌)。"""
    import time as _t
    scenario = registry.get("car_arrival_pt")
    p = _p(ctx, "car_arrival_pt")
    today = datetime.now().strftime("%Y/%m/%d")  # 💡 SA:StartTime=C/I 日 00:00:00,請求格式 yyyy/mm/dd hh:mm:ss(斜線+秒)
    payload = {"Roomer": {
        "RoomNumber": p["room_number"], "StartTime": f"{today} 00:00:00", "EndTime": f"{today} 23:59:00",
        "LicensePlateList": [p["license_plate"]],
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
    params=[ParamSpec("license_plate", "車牌", "str",
                      default=lambda ctx: f"FIND-{_ts()}", hint="留自動=每次執行產生唯一車牌")],
)
def run_paytronex_find(ctx: RunContext) -> CaseResult:
    """PAYTRONEX:先 add_roomer 建租約,再 findByLicensePlate 逆查(模擬車辨感應 → 查租約)。

    若查無對應租約,mock 會動態就地合法(建虛擬租約),故應回 200 + roomer。
    """
    import time as _t
    scenario = registry.get("car_arrival_retry")
    p = _p(ctx, "car_arrival_retry")
    plate = p["license_plate"]
    t0 = _t.perf_counter()
    # 先 add 建立含該車牌的租約(SA 格式 yyyy/mm/dd hh:mm:ss);種子參數沿用同一車牌保證查得到
    today = datetime.now().strftime("%Y/%m/%d")
    execute_for_ctx(ctx, "POST", ctx.urls["paytronex_add"], json_body={"Roomer": {
        "RoomNumber": "209", "StartTime": f"{today} 00:00:00", "EndTime": f"{today} 23:59:00",
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


# ====================================================================
# 🚗 博辰(PAYTRONEX)SA 管線情境 — find→update 兩步閉環(wiki 博辰停車場 SA)
# SA 事件:CIX 取消入住(EndTime=當下+緩衝、車牌空)/清除車號(車牌空)/更新車號(新牌)/修改退房(新 EndTime)
# 💡 SA 未定義 add/update 回應 body 與 find 查無行為 → 沿用 mock 現況(resultCode 0000 / 動態虛擬租約),待 SA 確認
# ====================================================================
def _pt_today():
    return datetime.now().strftime("%Y/%m/%d")


def _pt_add_roomer(ctx, room, plate_list):
    """管線前置:add 建租約(SA 請求格式 yyyy/mm/dd hh:mm:ss)。"""
    return execute_for_ctx(ctx, "POST", ctx.urls["paytronex_add"], json_body={"Roomer": {
        "RoomNumber": room, "StartTime": f"{_pt_today()} 00:00:00", "EndTime": f"{_pt_today()} 23:59:00",
        "LicensePlateList": plate_list,
    }})


def _pt_find_rentid(ctx, plate):
    """管線第一步:findByLicensePlate 取 RentId。回傳 (rent_id, res, err)。"""
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_find"], json_body={"LicensePlate": plate})
    if err or res is None or res.status_code != 200:
        return None, res, err
    try:
        roomer = (res.json() or {}).get("roomer") or {}
    except Exception:
        roomer = {}
    return roomer.get("rentId"), res, err


@register_scenario(
    "paytronex_cancel_checkin", module="parking", vendor="PAYTRONEX",
    name="取消入住管線(查租約→更新銷帳)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
)
def run_paytronex_cancel_checkin(ctx: RunContext) -> CaseResult:
    """SA CIX:find 取 RentId → update(EndTime=當下+緩衝分鐘、車牌空)。
    閉環斷言:原車牌已從租約移除(舊牌再查會落到 mock 動態虛擬租約)。"""
    import time as _t
    scenario = registry.get("paytronex_cancel_checkin")
    ts = datetime.now().strftime("%m%d%H%M%S")
    plate = f"CIX-{ts}"
    t0 = _t.perf_counter()
    _pt_add_roomer(ctx, "301", [plate])
    rent_id, _, err_f = _pt_find_rentid(ctx, plate)
    # 💡 SA 兩處說法(當下時間 vs 當下+緩衝分鐘),取較具體的「當下+30分」
    cix_end = (datetime.now() + timedelta(minutes=30)).strftime("%Y/%m/%d %H:%M:%S")
    payload = {"Roomer": {"RentId": rent_id, "RoomNumber": "301",
                          "StartTime": f"{_pt_today()} 00:00:00", "EndTime": cix_end,
                          "LicensePlateList": []}}
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_update"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err_f or not rent_id or err or res is None:
        return _fail("paytronex_cancel_checkin", "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": err or err_f or "前置 find 未取得 RentId"})
    body = res.json()
    rent2, res2, _ = _pt_find_rentid(ctx, plate)
    summary = {"update_code": body.get("resultCode"), "old_plate_rentid_changed": (rent2 != rent_id) if rent2 else None}
    if res.status_code == 200 and body.get("resultCode") == "0000" and summary["old_plate_rentid_changed"]:
        return _ok("paytronex_cancel_checkin", "", scenario, dur, request_payload=payload, response_payload=summary)
    return _fail("paytronex_cancel_checkin", "", scenario, dur, request_payload=payload, response_payload=summary)


@register_scenario(
    "paytronex_clear_plate", module="parking", vendor="PAYTRONEX",
    name="清除車號管線(查租約→空車牌更新)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
)
def run_paytronex_clear_plate(ctx: RunContext) -> CaseResult:
    """SA 綜合櫃台清除車號:find(修改前車號)→ update(LicensePlateList 空)。閉環:舊牌已移出原租約。"""
    import time as _t
    scenario = registry.get("paytronex_clear_plate")
    ts = datetime.now().strftime("%m%d%H%M%S")
    plate = f"CLR-{ts}"
    t0 = _t.perf_counter()
    _pt_add_roomer(ctx, "302", [plate, f"{plate}-B"])
    rent_id, _, err_f = _pt_find_rentid(ctx, plate)
    payload = {"Roomer": {"RentId": rent_id, "RoomNumber": "302",
                          "StartTime": f"{_pt_today()} 00:00:00", "EndTime": f"{_pt_today()} 23:59:00",
                          "LicensePlateList": []}}
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_update"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err_f or not rent_id or err or res is None:
        return _fail("paytronex_clear_plate", "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": err or err_f or "前置 find 未取得 RentId"})
    body = res.json()
    rent2, _, _ = _pt_find_rentid(ctx, plate)
    summary = {"update_code": body.get("resultCode"), "old_plate_rentid_changed": (rent2 != rent_id) if rent2 else None}
    if res.status_code == 200 and body.get("resultCode") == "0000" and summary["old_plate_rentid_changed"]:
        return _ok("paytronex_clear_plate", "", scenario, dur, request_payload=payload, response_payload=summary)
    return _fail("paytronex_clear_plate", "", scenario, dur, request_payload=payload, response_payload=summary)


@register_scenario(
    "paytronex_change_plate", module="parking", vendor="PAYTRONEX",
    name="更新車號管線(查舊牌→新牌更新)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
)
def run_paytronex_change_plate(ctx: RunContext) -> CaseResult:
    """SA 綜合櫃台更新車號:find(修改前舊牌)取 RentId → update(新牌)。閉環:新牌查到同一租約。"""
    import time as _t
    scenario = registry.get("paytronex_change_plate")
    ts = datetime.now().strftime("%m%d%H%M%S")
    old_plate, new_plate = f"OLDP-{ts}", f"NEWP-{ts}"
    t0 = _t.perf_counter()
    _pt_add_roomer(ctx, "303", [old_plate])
    rent_id, _, err_f = _pt_find_rentid(ctx, old_plate)
    payload = {"Roomer": {"RentId": rent_id, "RoomNumber": "303",
                          "StartTime": f"{_pt_today()} 00:00:00", "EndTime": f"{_pt_today()} 23:59:00",
                          "LicensePlateList": [new_plate]}}
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_update"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err_f or not rent_id or err or res is None:
        return _fail("paytronex_change_plate", "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": err or err_f or "前置 find 未取得 RentId"})
    body = res.json()
    rent_new, _, _ = _pt_find_rentid(ctx, new_plate)
    summary = {"update_code": body.get("resultCode"), "new_plate_same_rent": (rent_new == rent_id) if rent_new else None}
    if res.status_code == 200 and body.get("resultCode") == "0000" and summary["new_plate_same_rent"]:
        return _ok("paytronex_change_plate", "", scenario, dur, request_payload=payload, response_payload=summary)
    return _fail("paytronex_change_plate", "", scenario, dur, request_payload=payload, response_payload=summary)


@register_scenario(
    "paytronex_change_checkout", module="parking", vendor="PAYTRONEX",
    name="修改退房管線(查租約→新EndTime更新)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
)
def run_paytronex_change_checkout(ctx: RunContext) -> CaseResult:
    """SA 修改退房日期:find 取 RentId → update(新 EndTime=退房日+最晚離場時間)。閉環:find 回新 EndTime。"""
    import time as _t
    scenario = registry.get("paytronex_change_checkout")
    ts = datetime.now().strftime("%m%d%H%M%S")
    plate = f"CKO-{ts}"
    t0 = _t.perf_counter()
    _pt_add_roomer(ctx, "304", [plate])
    rent_id, _, err_f = _pt_find_rentid(ctx, plate)
    new_end = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d 15:00:00")
    payload = {"Roomer": {"RentId": rent_id, "RoomNumber": "304",
                          "StartTime": f"{_pt_today()} 00:00:00", "EndTime": new_end,
                          "LicensePlateList": [plate]}}
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_update"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err_f or not rent_id or err or res is None:
        return _fail("paytronex_change_checkout", "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": err or err_f or "前置 find 未取得 RentId"})
    body = res.json()
    # find 回應的時間會洗成 ISO T 格式(mock 防禦,亦符合 SA 回應範例 2026-10-11T10:01:14)
    expected_end_iso = new_end.replace("/", "-").replace(" ", "T")
    rent2, res2, _ = _pt_find_rentid(ctx, plate)
    end_after = ((res2.json().get("roomer") or {}).get("endTime")) if res2 else None
    summary = {"update_code": body.get("resultCode"), "end_after": end_after, "expected": expected_end_iso}
    if res.status_code == 200 and body.get("resultCode") == "0000" and end_after == expected_end_iso:
        return _ok("paytronex_change_checkout", "", scenario, dur, request_payload=payload, response_payload=summary)
    return _fail("paytronex_change_checkout", "", scenario, dur, request_payload=payload, response_payload=summary)


@register_scenario(
    "paytronex_find_unknown", module="parking", vendor="PAYTRONEX",
    name="查無車牌(動態虛擬租約・SA未定義)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate",
)
def run_paytronex_find_unknown(ctx: RunContext) -> CaseResult:
    """SA 未定義 find 查無行為;mock 現況=動態就地合法(建虛擬租約回 200)。本情境守護現況,待 SA 確認後改斷言。"""
    import time as _t
    scenario = registry.get("paytronex_find_unknown")
    ts = datetime.now().strftime("%m%d%H%M%S")
    payload = {"LicensePlate": f"NOSUCH-{ts}"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["paytronex_find"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("paytronex_find_unknown", "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": err or "no response"})
    body = res.json()
    roomer = body.get("roomer") or {}
    ok = res.status_code == 200 and roomer.get("rentId") and roomer.get("isRenting") is True
    if ok:
        return _ok("paytronex_find_unknown", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("paytronex_find_unknown", "", scenario, dur, request_payload=payload, response_payload=body)


# ====================================================================
# 🌡️ 房控(roomcontrol / A7 公版 XML 介面)— 對齊 sa_docs/sa10 V1.2
# 方向:廠商→PMS(沙盒發砲端=模擬房控廠商;mock PMS 側在 server/roomcontrol/)。
# RC0 兩案:B4 ROOM_STA 房況推送(16 位房況字串)、A6 ROOM_INF 房況查詢(住客現況)。
# 傳輸:POST /third-party/import-sync-files(sa8/sa9 REST 版;
#      GET TxnData 閘門版見 sa10,REAL 端點與 thirdParty 實際代碼待 SA 提供)。
# ====================================================================
from server.roomcontrol.vendors.vendor_A7_XML import (
    build_room_sta_push, build_room_inf_query, parse_rowset_xml,
    DEFAULT_STATUS_BITS,
)


def _a7_identity(ctx: RunContext):
    """A7 公版識別三元組(athena/hotel 取自該環境矩陣;thirdParty 由案例參數帶入)。"""
    return (str(ctx.headers_amenity.get("athena") or "25"),
            str(ctx.headers_amenity.get("hotel") or "01"))


def _a7_import_payload(ctx: RunContext, xml_str: str, third_party: str, file_name="C001.xml") -> dict:
    """組 VendorImportSyncDataRequest(XML 字串包進 JSON,sa8/sa9 swagger 契約)。"""
    athena, hotel = _a7_identity(ctx)
    return {"athenaId": athena, "hotelCode": hotel, "thirdPartyCode": third_party,
            "requestDataList": [{"requestBody": xml_str, "fileName": file_name}]}


def _a7_first_response_item(res):
    """取回應首項與其 responseBody 解析列;失敗回 ({}, [])。

    相容兩種回應形狀:
    - sa8/sa9 swagger:200 → [VendorImportSyncDataResponse, ...](沙盒 mock)
    - REAL_QA 實測(2026-09-03):Athena 標準信封 {"code":"2000","data":[...]} 包著同結構
    """
    try:
        body = res.json()
    except Exception:
        body = None
    if isinstance(body, dict) and isinstance(body.get("data"), list) and body["data"]:
        item = body["data"][0]
    elif isinstance(body, list) and body:
        item = body[0]
    else:
        item = {}
    rows = []
    if item.get("responseBody"):
        try:
            rows = parse_rowset_xml(item["responseBody"])
        except Exception:
            rows = []
    return item, rows


@register_scenario(
    "rc_room_status_push", module="roomcontrol", vendor="A7_XML",
    name="房況推送(ROOM_STA/B4)", endpoint="/third-party/import-sync-files",
    params=[
        ParamSpec("room_no", "房號", "str", "2403"),
        ParamSpec("status_bits", "房況位元串", "str", DEFAULT_STATUS_BITS,
                  hint="16 位:1Keyhouse 2Keybox 3冷氣 4總電源 5鐵捲門 6一氧化碳 7防盜 8緊急 9清潔(1請掃/2掃中/3待巡/4巡中/0完成) 10勿擾 11房門 12-16保留"),
        ParamSpec("third_party_code", "廠商代碼", "str", "TT",
                  hint="A7 公版 thirdParty 代碼;TT=sa10 佔位,實際值由德安上線前提供"),
    ],
)
def run_rc_room_status_push(ctx: RunContext) -> CaseResult:
    """B4 送全部房況:推 16 位房況字串 → 斷言 procStatus + RETN-CODE 0000 + "1112 Set";
    LOCAL 再經內部回讀閉環驗證狀態已落庫(REAL 無內部端點,跳過回讀)。"""
    import time as _t
    scenario = registry.get("rc_room_status_push")
    p = _p(ctx, "rc_room_status_push")
    xml_str = build_room_sta_push(p["room_no"], p["status_bits"])
    payload = _a7_import_payload(ctx, xml_str, p["third_party_code"])
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    summary = {"room_no": p["room_no"], "action_cod": f"#ROOM_STA#{p['status_bits']}#"}
    if err or res is None:
        return _fail("rc_room_status_push", "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": err or "no response"})
    item, rows = _a7_first_response_item(res)
    retn = rows[0].get("RETN-CODE") if rows else None
    summary.update({"procStatus": item.get("procStatus"), "retn_code": retn,
                    "retn_desc": rows[0].get("RETN-CODE-DESC") if rows else None})
    ok = res.status_code == 200 and item.get("procStatus") is True and retn == "0000"
    # LOCAL 閉環:內部回讀斷言位元串已落庫(下命令→回讀,前例:keycard checkinTime)
    if ok and not ctx.use_real:
        res_rb, _ = execute_for_ctx(ctx, "GET", ctx.urls["roomcontrol_internal"])
        if res_rb is not None and res_rb.status_code == 200:
            state = (res_rb.json() or {}).get("room_control_state") or {}
            summary["state_readback_bits"] = (state.get(p["room_no"]) or {}).get("status_bits")
            ok = summary["state_readback_bits"] == p["status_bits"]
    if ok:
        return _ok("rc_room_status_push", "", scenario, dur, request_payload=payload, response_payload=summary)
    return _fail("rc_room_status_push", "", scenario, dur, request_payload=payload, response_payload=summary)


@register_scenario(
    "rc_room_status_query", module="roomcontrol", vendor="A7_XML",
    name="房況查詢(ROOM_INF/A6)", endpoint="/third-party/import-sync-files",
    params=[
        ParamSpec("room_no", "房號", "str", "2403", hint="查無住客的房號會回 ROOM_STA=V(空房)單列"),
        ParamSpec("third_party_code", "廠商代碼", "str", "TT",
                  hint="A7 公版 thirdParty 代碼;TT=sa10 佔位,實際值由德安上線前提供"),
    ],
)
def run_rc_room_status_query(ctx: RunContext) -> CaseResult:
    """A6 房間狀態查詢:ROOM_INF → 斷言 procStatus + 每住客一 ROW + ROOM_STA(O/S/V)+ RETN-CODE 0000。"""
    import time as _t
    scenario = registry.get("rc_room_status_query")
    p = _p(ctx, "rc_room_status_query")
    xml_str = build_room_inf_query(p["room_no"])
    payload = _a7_import_payload(ctx, xml_str, p["third_party_code"], file_name="C002.xml")
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("rc_room_status_query", "", scenario, dur, request_payload=payload,
                     response_payload={"__error__": err or "no response"})
    item, rows = _a7_first_response_item(res)
    summary = {
        "procStatus": item.get("procStatus"),
        "row_count": len(rows),
        "rows": rows,   # 結構化住客列(JSON 稽核可直接檢視;HTTP 稽核另有原始 XML)
    }
    first = rows[0] if rows else {}
    ok = (res.status_code == 200 and item.get("procStatus") is True
          and rows and first.get("ROOM_STA") in ("O", "S", "V", "R")
          and first.get("RETN-CODE") == "0000")
    if ok:
        return _ok("rc_room_status_query", "", scenario, dur, request_payload=payload, response_payload=summary)
    return _fail("rc_room_status_query", "", scenario, dur, request_payload=payload, response_payload=summary)


# （原本 checkin_sync/whitelist_update/car_arrival_retry 的 UNIMPLEMENTED 註冊已由上方實作取代）


# ====================================================================
# 🔑 門禁製卡（keycard / WAFERLOCK_LIVEAM）— 對齊華豫寧 LiveAM Swagger 真實合約
# 真實管線:login 取 token → getRoomIdByName 房號轉 roomID(int) → POST Order(必填六欄位)
#          → getCardInfo/{pmrId} 讀卡取 cardUid → OrderCard {orderID, cardUid} 綁定
# 狀態機  :PUT Order 填 checkinTime=當下 → 開門;填 checkoutTime → 卡片失效
# 錯誤合約:ResponseData {error:int(0=成功), desc, msg};401 UnauthorizedInfo
# ====================================================================
_KC_READER = "801F12A3D8CA"  # 沙盒預設讀卡機(SA 測試環境為 E8EB1BCCE94F1)


def _kc_headers(ctx):
    """keycard 路由的 auth gate:LOCAL 模式帶 LOCAL_TOKEN;REAL 應改帶 login 取得的 JWT(待真實環境驗證)。"""
    h = dict(ctx.headers)
    if not ctx.use_real:
        h["Authorization"] = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"  # config.LOCAL_TOKEN
    return h


def _kc_iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _kc_room_id(ctx, room_nos, h):
    """管線前置:GET /api/Room/getRoomIdByName/{房號} → roomID(int)。"""
    res, err = execute_for_ctx(ctx, "GET", f"{ctx.urls['keycard_roomid_base']}/{room_nos}", headers=h)
    if err or res is None or res.status_code != 200:
        return None
    return ((res.json() or {}).get("idList") or [None])[0]


def _kc_make_order(ctx, room_nos, h, guest="Orchestrator", pre_out=None):
    """管線前置:依 Swagger Order 必填欄位建訂單 → 回 (order_id, order_payload);失敗回 (None, payload)。

    pre_out 可指定 preOutTime(參數化案例傳入);未指定=當下+1天(參數化前行為)。
    """
    ts = datetime.now().strftime("%m%d%H%M%S%f")
    order_id = f"KC-{ts}"
    payload = {
        "id": order_id,
        "reserveID": int(datetime.now().timestamp()) % 1000000,  # Swagger:系統未用可任意
        "roomID": 0,  # 下方經 getRoomIdByName 轉換後覆寫
        "preInTime": _kc_iso(datetime.now()),
        "preOutTime": pre_out or _kc_iso(datetime.now() + timedelta(days=1)),
        "canAppCheckin": False,
        "status": 0,
        "guestName": guest,
    }
    payload["roomID"] = _kc_room_id(ctx, room_nos, h) or 0
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["keycard_order"], headers=h, json_body=payload)
    if err or res is None or res.status_code != 201:
        return None, payload
    return order_id, payload


def _kc_make_card(ctx, room_nos, h, guest="Orchestrator", pre_out=None):
    """完整真實管線:建訂單 → 讀卡取 cardUid → OrderCard 綁定。回傳 (order_id, cardUid, order_payload)。"""
    order_id, order_payload = _kc_make_order(ctx, room_nos, h, guest, pre_out=pre_out)
    if not order_id:
        return None, None, order_payload
    # 💡 Swagger CommonPara:{projectId, tokenValue, timeout}(mock 不嚴格驗 body,送最小集)
    res_c, err_c = execute_for_ctx(ctx, "POST", f"{ctx.urls['keycard_getcardinfo_base']}/{_KC_READER}",
                                   headers=h, json_body={"timeout": 5})
    if err_c or res_c is None or res_c.status_code != 200:
        return order_id, None, order_payload
    card_uid = (res_c.json() or {}).get("cardUid")
    res_b, err_b = execute_for_ctx(ctx, "POST", ctx.urls["keycard_ordercard"], headers=h,
                                   json_body={"orderID": order_id, "cardUid": card_uid})
    if err_b or res_b is None or res_b.status_code != 201:
        return order_id, None, order_payload
    return order_id, card_uid, order_payload


@register_scenario(
    "keycard_login", module="keycard", vendor="WAFERLOCK",
    name="登入取得Token", endpoint="/api/Auth/login",
    params=[
        ParamSpec("account", "帳號", "str", "athena_pms", hint="Swagger LoginPara.id"),
        ParamSpec("password", "密碼", "str", "liveam_password_123"),
        ParamSpec("project_id", "專案代號", "str", "PRJ-01", hint="Swagger LoginPara.projectID"),
    ],
)
def run_keycard_login(ctx: RunContext) -> CaseResult:
    """Swagger LoginPara {id, password, projectID} → TokenInfo {id, token}(SA:token 72 小時有效)。"""
    import time as _t
    scenario = registry.get("keycard_login")
    p = _p(ctx, "keycard_login")
    payload = {"id": p["account"], "password": p["password"], "projectID": p["project_id"]}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["keycard_login"], json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("keycard_login", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = res.json() if res.status_code == 200 else {}
    if res.status_code == 200 and body.get("token"):
        return _ok("keycard_login", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("keycard_login", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "keycard_room_lookup", module="keycard", vendor="WAFERLOCK",
    name="房號轉房間編號", endpoint="/api/Room/getRoomIdByName/{name}",
    params=[ParamSpec("room_name", "房號名稱", "str", "401", hint="沙盒房號 101–499 皆可查得 roomID")],
)
def run_keycard_room_lookup(ctx: RunContext) -> CaseResult:
    """Swagger:getRoomIdByName → IdInfo {error:0, idList:[int]}(Order.roomID 為整數,必要前置)。"""
    import time as _t
    scenario = registry.get("keycard_room_lookup")
    h = _kc_headers(ctx)
    p = _p(ctx, "keycard_room_lookup")
    payload = {"name": p["room_name"]}
    t0 = _t.perf_counter()
    # 💡 設計 §4:參數值進 URL 路徑前一律編碼(quote,連 / 也轉義),防路徑注入
    res, err = execute_for_ctx(ctx, "GET", f"{ctx.urls['keycard_roomid_base']}/{_path_seg(p['room_name'])}", headers=h)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("keycard_room_lookup", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = res.json() if res.status_code == 200 else {}
    if res.status_code == 200 and body.get("error") == 0 and (body.get("idList") or [None])[0]:
        return _ok("keycard_room_lookup", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("keycard_room_lookup", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "keycard_make_card", module="keycard", vendor="WAFERLOCK",
    name="正規製卡管線(訂單→讀卡→綁定)", endpoint="/api/Order + /api/Operation/getCardInfo + /api/OrderCard",
    params=[
        ParamSpec("room_no", "房號", "str", "401"),
        ParamSpec("guest_name", "住客名", "str", "MakeCard"),
        ParamSpec("pre_out_time", "預計退房", "datetime",
                  default=lambda ctx: _kc_iso(datetime.now() + timedelta(days=1)),
                  hint="ISO 格式 yyyy-mm-ddThh:mm:ss;留自動=當下+1天"),
    ],
)
def run_keycard_make_card(ctx: RunContext) -> CaseResult:
    """真實管線:getRoomIdByName → POST Order(必填六欄位)→ getCardInfo 取 cardUid → OrderCard 綁定。"""
    import time as _t
    scenario = registry.get("keycard_make_card")
    h = _kc_headers(ctx)
    p = _p(ctx, "keycard_make_card")
    t0 = _t.perf_counter()
    order_id, card_uid, _payload = _kc_make_card(ctx, p["room_no"], h, p["guest_name"], pre_out=p["pre_out_time"])
    dur = int((_t.perf_counter() - t0) * 1000)
    summary = {"orderID": order_id, "cardUid": card_uid}
    if order_id and card_uid:
        return _ok("keycard_make_card", "", scenario, dur, request_payload={"room": p["room_no"]}, response_payload=summary)
    return _fail("keycard_make_card", "", scenario, dur, request_payload={"room": p["room_no"]},
                 response_payload={"__error__": summary})


def _kc_put_order(ctx, h, order_payload, **fields):
    """PUT /api/Order(部分欄位更新,回 (res, err))。"""
    body = dict(order_payload)
    body.update(fields)
    return execute_for_ctx(ctx, "PUT", ctx.urls["keycard_order"], headers=h, json_body=body)


def _kc_get_order(ctx, h, order_id):
    return execute_for_ctx(ctx, "GET", f"{ctx.urls['keycard_order']}/{order_id}", headers=h)


@register_scenario(
    "keycard_checkin_open", module="keycard", vendor="WAFERLOCK",
    name="入住開門(CKI・填checkinTime)", endpoint="PUT /api/Order",
)
def run_keycard_checkin_open(ctx: RunContext) -> CaseResult:
    """SA CKI:PUT Order 填 checkinTime=當下 → 開啟客房權限。閉環:GET 訂單驗 checkinTime 已寫入。"""
    import time as _t
    scenario = registry.get("keycard_checkin_open")
    h = _kc_headers(ctx)
    t0 = _t.perf_counter()
    order_id, card_uid, order_payload = _kc_make_card(ctx, "402", h, "Checkin")
    if not order_id or not card_uid:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("keycard_checkin_open", "", scenario, dur, response_payload={"__error__": "前置製卡管線失敗"})
    ck_time = _kc_iso(datetime.now())
    res, err = _kc_put_order(ctx, h, order_payload, checkinTime=ck_time)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None or res.status_code != 200:
        return _fail("keycard_checkin_open", "", scenario, dur, request_payload={"checkinTime": ck_time},
                     response_payload={"__error__": err or f"PUT {getattr(res,'status_code',None)}"})
    res_g, _ = _kc_get_order(ctx, h, order_id)
    after = (res_g.json() or {}).get("checkinTime") if res_g is not None and res_g.status_code == 200 else None
    summary = {"orderID": order_id, "checkinTime_sent": ck_time, "checkinTime_after": after}
    if after == ck_time:
        return _ok("keycard_checkin_open", "", scenario, dur, request_payload={"checkinTime": ck_time}, response_payload=summary)
    return _fail("keycard_checkin_open", "", scenario, dur, request_payload={"checkinTime": ck_time}, response_payload=summary)


@register_scenario(
    "keycard_checkout_invalidate", module="keycard", vendor="WAFERLOCK",
    name="退房取消失效(填checkoutTime)", endpoint="PUT /api/Order",
)
def run_keycard_checkout_invalidate(ctx: RunContext) -> CaseResult:
    """SA CIX/CKO:PUT Order 填 checkoutTime → 卡片失效。閉環:GET 訂單驗 checkoutTime 已寫入。"""
    import time as _t
    scenario = registry.get("keycard_checkout_invalidate")
    h = _kc_headers(ctx)
    t0 = _t.perf_counter()
    order_id, card_uid, order_payload = _kc_make_card(ctx, "403", h, "Checkout")
    if not order_id or not card_uid:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("keycard_checkout_invalidate", "", scenario, dur, response_payload={"__error__": "前置製卡管線失敗"})
    _kc_put_order(ctx, h, order_payload, checkinTime=_kc_iso(datetime.now()))
    co_time = _kc_iso(datetime.now())
    res, err = _kc_put_order(ctx, h, order_payload, checkoutTime=co_time)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None or res.status_code != 200:
        return _fail("keycard_checkout_invalidate", "", scenario, dur, request_payload={"checkoutTime": co_time},
                     response_payload={"__error__": err or f"PUT {getattr(res,'status_code',None)}"})
    res_g, _ = _kc_get_order(ctx, h, order_id)
    after = (res_g.json() or {}).get("checkoutTime") if res_g is not None and res_g.status_code == 200 else None
    summary = {"orderID": order_id, "checkoutTime_sent": co_time, "checkoutTime_after": after}
    if after == co_time:
        return _ok("keycard_checkout_invalidate", "", scenario, dur, request_payload={"checkoutTime": co_time}, response_payload=summary)
    return _fail("keycard_checkout_invalidate", "", scenario, dur, request_payload={"checkoutTime": co_time}, response_payload=summary)


@register_scenario(
    "keycard_change_checkout", module="keycard", vendor="WAFERLOCK",
    name="修改退房時間(改PreOutTime)", endpoint="PUT /api/Order",
)
def run_keycard_change_checkout(ctx: RunContext) -> CaseResult:
    """SA CHANGE_CKO_DATE_TIME:PUT Order 修改 preOutTime。閉環:GET 訂單驗 preOutTime 已更新。"""
    import time as _t
    scenario = registry.get("keycard_change_checkout")
    h = _kc_headers(ctx)
    t0 = _t.perf_counter()
    order_id, card_uid, order_payload = _kc_make_card(ctx, "404", h, "ChangeCko")
    if not order_id or not card_uid:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("keycard_change_checkout", "", scenario, dur, response_payload={"__error__": "前置製卡管線失敗"})
    new_out = _kc_iso(datetime.now() + timedelta(days=2))
    res, err = _kc_put_order(ctx, h, order_payload, preOutTime=new_out)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None or res.status_code != 200:
        return _fail("keycard_change_checkout", "", scenario, dur, request_payload={"preOutTime": new_out},
                     response_payload={"__error__": err or f"PUT {getattr(res,'status_code',None)}"})
    res_g, _ = _kc_get_order(ctx, h, order_id)
    after = (res_g.json() or {}).get("preOutTime") if res_g is not None and res_g.status_code == 200 else None
    summary = {"orderID": order_id, "preOutTime_sent": new_out, "preOutTime_after": after}
    if after == new_out:
        return _ok("keycard_change_checkout", "", scenario, dur, request_payload={"preOutTime": new_out}, response_payload=summary)
    return _fail("keycard_change_checkout", "", scenario, dur, request_payload={"preOutTime": new_out}, response_payload=summary)


@register_scenario(
    "keycard_revoke_card", module="keycard", vendor="WAFERLOCK",
    name="刪卡(DELETE + 重刪404)", endpoint="DELETE /api/OrderCard/{oid}/{cuid}",
)
def run_keycard_revoke_card(ctx: RunContext) -> CaseResult:
    """真實管線製卡後刪卡:首刪 200;重刪應 404(ResponseData)——含負面斷言。"""
    import time as _t
    scenario = registry.get("keycard_revoke_card")
    h = _kc_headers(ctx)
    t0 = _t.perf_counter()
    order_id, card_uid, _payload = _kc_make_card(ctx, "405", h, "Revoke")
    if not order_id or not card_uid:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("keycard_revoke_card", "", scenario, dur, response_payload={"__error__": "前置製卡管線失敗"})
    del_url = f"{ctx.urls['keycard_ordercard']}/{order_id}/{card_uid}"
    res1, err1 = execute_for_ctx(ctx, "DELETE", del_url, headers=h)
    res2, err2 = execute_for_ctx(ctx, "DELETE", del_url, headers=h)
    dur = int((_t.perf_counter() - t0) * 1000)
    summary = {"orderID": order_id, "cardUid": card_uid,
               "first_delete": getattr(res1, "status_code", None), "second_delete": getattr(res2, "status_code", None)}
    if not err1 and res1 is not None and res1.status_code in (200, 204) \
            and not err2 and res2 is not None and res2.status_code == 404:
        return _ok("keycard_revoke_card", "", scenario, dur, request_payload={"del_url": del_url}, response_payload=summary)
    return _fail("keycard_revoke_card", "", scenario, dur, request_payload={"del_url": del_url}, response_payload=summary)


@register_scenario(
    "keycard_bad_token", module="keycard", vendor="WAFERLOCK",
    name="無效Token(401)", endpoint="/api/OrderCard",
)
def run_keycard_bad_token(ctx: RunContext) -> CaseResult:
    """負面:帶無效 Token 呼叫 → 401 + ResponseData {error:int}。"""
    import time as _t
    scenario = registry.get("keycard_bad_token")
    h = {"Authorization": "Bearer WRONG-TOKEN", "Content-Type": "application/json"}
    payload = {"orderID": "KC-GHOST", "cardUid": "DEADBEEF"}
    t0 = _t.perf_counter()
    res, err = execute_for_ctx(ctx, "POST", ctx.urls["keycard_ordercard"], headers=h, json_body=payload)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail("keycard_bad_token", "", scenario, dur, request_payload=payload, response_payload={"__error__": err or "no response"})
    body = {}
    try:
        body = res.json()
    except Exception:
        pass
    if res.status_code == 401 and body.get("error") == 401:
        return _ok("keycard_bad_token", "", scenario, dur, request_payload=payload, response_payload=body)
    return _fail("keycard_bad_token", "", scenario, dur, request_payload=payload, response_payload=body)


@register_scenario(
    "card_lifecycle", module="keycard", vendor="WAFERLOCK",
    name="跨模組卡片生命週期閉環（真實管線製卡→mifare 刷回房號）", endpoint="/api/OrderCard + /room-pay/mifare-nos",
)
def run_card_lifecycle(ctx: RunContext) -> CaseResult:
    """B 閉環(真實管線版):keycard 製卡(Order→getCardInfo→OrderCard,注入 mock_card_mapping_db)
    → 用 cardUid 走 amenity mifare 查詢刷回房號 → 斷言房號與製卡時一致。跨廠商整合閉環。"""
    import time as _t
    scenario = registry.get("card_lifecycle")
    h = _kc_headers(ctx)
    room = "309"
    t0 = _t.perf_counter()
    order_id, card_uid, _payload = _kc_make_card(ctx, room, h, "Lifecycle")
    if not order_id or not card_uid:
        dur = int((_t.perf_counter() - t0) * 1000)
        return _fail("card_lifecycle", "", scenario, dur, response_payload={"__error__": "製卡階段失敗"})

    # 用該 cardUid 走 amenity mifare 查詢（跨模組）
    res_mf, err_mf = execute_for_ctx(ctx, "GET", ctx.urls["mifare_nos"],
                                     params={**ctx.params_amenity, "keyword": card_uid},
                                     headers=ctx.headers_amenity)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err_mf or res_mf is None or res_mf.status_code != 200:
        return _fail("card_lifecycle", "", scenario, dur,
                     request_payload={"cardUid": card_uid, "expected_room": room},
                     response_payload={"__error__": err_mf or f"mifare {getattr(res_mf,'status_code',None)}"})

    # 斷言刷回房號 == 製卡房號
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
