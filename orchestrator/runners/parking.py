# orchestrator/runners/parking.py
"""🚗 停車車辨模組案例（parking / SHIN_YEONG 新詠 + PAYTRONEX 博辰）。"""
from datetime import datetime, timedelta

from ..registry import registry, register_scenario
from ..models import CaseResult, RunContext, ParamSpec
from hardware.simulate_speaker import execute_for_ctx

from .helpers import _p, _ts, _sa_now, _ok, _fail, _expect_417


# ====================================================================
# 🚗 停車車辨（parking / SHIN_YEONG）—— 至少接入 car_arrival
# ====================================================================
@register_scenario(
    "car_arrival", module="parking", vendor="SHIN_YEONG",
    name="車輛抵達(回推)", endpoint="/car-arrival",
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
    name="住客入住(推播)", endpoint="/check-in",
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
    name="白名單總覽(沙盒內部)", endpoint="/internal/whitelist",
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
    name="夜核名單(推播)", endpoint="/pms-sync-data/night-audit",
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
# 模式同 car_arrival：先 check-in 落庫白名單，再打目��路由;這些 /pms-sync-data/* 無 auth gate。
@register_scenario(
    "change_checkout", module="parking", vendor="SHIN_YEONG",
    name="修改退房時間(推播)", endpoint="/pms-sync-data/change-checkout-datetime",
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
    name="車牌異動(推播)", endpoint="/pms-sync-data/change-car-nos",
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
    name="取消入住(推播)", endpoint="/pms-sync-data/check-in-cancel",
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
    name="入住啟用(公版)", endpoint="/parking/sync",
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
    name="換車號(公版・兩筆連發)", endpoint="/parking/sync",
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
    name="清除車號(公版)", endpoint="/parking/sync",
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
    name="取消入住(公版)", endpoint="/parking/sync",
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
    name="非法參數(公版・1000)", endpoint="/parking/sync",
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
    name="缺必填欄位(回推・417・1000)", endpoint="/external/vendor-sync-data/car-arrival",
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
    name="新增房客預約(roomer/add)", endpoint="/parktron/hpms/services/roomer/add",
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
    name="車牌逆查租約(find)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate",
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
    name="取消入住(2步・查租約→銷帳)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
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
    name="清除車號(2步・查租約→清牌)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
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
    name="更新車號(2步・查舊牌→換新牌)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
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
    name="修改退房(2步・查租約→改EndTime)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate + /update",
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
    name="查無車牌(SA未定義・虛擬租約)", endpoint="/parktron/hpms/services/roomer/findByLicensePlate",
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


# （原本 checkin_sync/whitelist_update/car_arrival_retry 的 UNIMPLEMENTED 註冊已由上方實作取代）
