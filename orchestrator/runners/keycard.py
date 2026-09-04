# orchestrator/runners/keycard.py
"""🔑 門禁製卡模組案例（keycard / WAFERLOCK_LIVEAM）— 對齊華豫寧 LiveAM Swagger 真實合約。"""
from datetime import datetime, timedelta

from ..registry import registry, register_scenario
from ..models import CaseResult, RunContext, ParamSpec
from hardware.simulate_speaker import execute_for_ctx

from .helpers import _p, _ok, _fail, _path_seg, _extract_room_nos

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
    name="登入取得Token(Auth)", endpoint="/api/Auth/login",
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
    name="房號轉編號(getRoomIdByName)", endpoint="/api/Room/getRoomIdByName/{name}",
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
    name="製卡(3步・訂單→讀卡→綁定)", endpoint="/api/Order + /api/Operation/getCardInfo + /api/OrderCard",
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
    name="退房失效(CIX・填checkoutTime)", endpoint="PUT /api/Order",
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
    name="刪卡(重刪404)", endpoint="DELETE /api/OrderCard/{oid}/{cuid}",
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
    name="卡片生命週期(跨模組閉環)", endpoint="/api/OrderCard + /room-pay/mifare-nos",
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
    name="製卡例外重試(LIVEAM客製)", endpoint="/key-card-management/liveam/create-card",
)
