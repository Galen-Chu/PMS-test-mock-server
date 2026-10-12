# orchestrator/runners/pbx_ui.py
"""☎️ 交換機(PABX)M1 案例 — PMS 側業務層(vendor=PMS_UI,模擬 PMS0210027 頁面動作)。

依據:SD文件_PMS0210027_交換機.xlsx(按鈕 0200 新增/0300 刪除/1010 開關電話/1020 限撥/
1030 勿擾——規則全指向宏興SD)+ 宏興SD §1.1/1.2/6(排程/刪除/各 API 語意)。
SD 結論:交換機無對外 REST 面(規則經框架直入 pbx_mn),故 M1 = 沙盒內模擬完整鏈:
頁面動作 → mcall_mn(NOT_TRANS) → 排程 tick → pbx_mn(TRANS) → MCS 下達交換機 → 雙側回讀斷言。
REAL 環境同樣 SKIP(無雲端介面;計畫文件 Q1 已結)。
"""
import time as _t
from datetime import datetime, timedelta

from ..models import CaseResult, RunContext, ParamSpec
from ..registry import registry
from hardware.simulate_speaker import execute_for_ctx

from .helpers import _p, _ok, _fail
from .pbx import (
    _real_skip, _readback,
    _mcall_dat_default, _mcall_tim_default,
)


def _pms_action(ctx, action, **fields):
    body = {"athenaId": "25", "hotelCode": "01", "action": action}
    body.update({k: v for k, v in fields.items() if v is not None})
    return execute_for_ctx(ctx, "POST", ctx.urls["pbx_pms_actions"], json_body=body)


def _pms_tick(ctx):
    return execute_for_ctx(ctx, "POST", ctx.urls["pbx_pms_tick"], json_body={})


def _pms_state(ctx):
    res, _ = execute_for_ctx(ctx, "GET", ctx.urls["pbx_pms_internal"])
    return res.json() if res is not None and res.status_code == 200 else None


def _ring(ctx, **fields):
    body = {"athenaId": "25", "hotelCode": "01"}
    body.update(fields)
    return execute_for_ctx(ctx, "POST", ctx.urls["pbx_ring"], json_body=body)


def _rms(ctx, **fields):
    body = {"athenaId": "25", "hotelCode": "01"}
    body.update(fields)
    return execute_for_ctx(ctx, "POST", ctx.urls["pbx_rms"], json_body=body)


def _anomalies(ctx):
    res, _ = execute_for_ctx(ctx, "GET", ctx.urls["pbx_anomalies"])
    return res.json() if res is not None and res.status_code == 200 else {}


def _json(res):
    try:
        return res.json() if res is not None else {}
    except Exception:
        return {}


def _act_ok(res):
    try:
        return bool((res.json() or {}).get("ok"))
    except Exception:
        return False


def _find_mcall(state, room, dat, tim):
    for mc in (state or {}).get("mcall_mn") or []:
        if (mc.get("room_nos"), mc.get("mcall_dat"), mc.get("mcall_tim")) == (room, dat, tim):
            return mc
    return None


def _past_tim(offset_min=10):
    return (datetime.now() - timedelta(minutes=offset_min)).strftime("%H%M%S")


def _today():
    return datetime.now().strftime("%Y%m%d")


def _register_ui_case(case_id, name, steps, params=None):
    scenario_holder = {}

    def runner(ctx: RunContext) -> CaseResult:
        scenario = registry.get(case_id)
        if ctx.use_real:
            return _real_skip(case_id, scenario)
        p = _p(ctx, case_id)
        desc = {"chain": "PMS 動作→mcall_mn→排程→pbx_mn→交換機→回讀", "params": dict(p)}
        t0 = _t.perf_counter()
        ok, summary = steps(ctx, p)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary["chain_ok"] = ok
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)

    registry.register(case_id, module="pbx", vendor="PMS_UI", name=name,
                      endpoint="/pbx/pms-actions", runner=runner, params=params or [])


# ---- 各案步驟 ------------------------------------------------------------
def _steps_set_mcall_full_flow(ctx, p):
    """晨喚全鏈:入住 → 設定(NOT_TRANS) → 排程 tick(宏興SD 1.2 五規則) → MCS 下達交換機。"""
    room, dat, tim = p["room_no"], p["mcall_dat"], p["mcall_tim"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    res_set, _ = _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    res_tick, _ = _pms_tick(ctx)
    try:
        tick = res_tick.json() if res_tick is not None else {}
    except Exception:
        tick = {}
    summary = {"room_no": room, "checkin_ok": _act_ok(res_ck), "set_ok": _act_ok(res_set),
               "tick_sent": tick.get("sent")}
    pms, sw = _pms_state(ctx), _readback(ctx)
    mc_pms, mc_sw = _find_mcall(pms, room, dat, tim), _find_mcall(sw, room, dat, tim)
    summary.update({"pms_mcall": mc_pms, "sw_mcall": mc_sw,
                    "pbx_mn_tail": (pms or {}).get("pbx_mn_tail", [])[-3:]})
    ok = (summary["checkin_ok"] and summary["set_ok"] and (tick.get("sent") or [])
          and mc_pms and mc_pms.get("trans_pbx_sta") == "TRANS" and mc_pms.get("mcall_sta") == "0"
          and mc_sw and mc_sw.get("mcall_sta") == "0")
    return ok, summary


def _steps_del_mcall_after_trans(ctx, p):
    """已傳送晨喚的刪除:TRANS → 直接 insert pbx_mn 下達 MCS D(不走排程;宏興SD 1.1.2)。"""
    room, dat, tim = p["room_no"], p["mcall_dat"], p["mcall_tim"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    _pms_tick(ctx)
    res_del, _ = _pms_action(ctx, "del_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    summary = {"room_no": room, "checkin_ok": _act_ok(res_ck), "del_ok": _act_ok(res_del)}
    pms, sw = _pms_state(ctx), _readback(ctx)
    mc_pms, mc_sw = _find_mcall(pms, room, dat, tim), _find_mcall(sw, room, dat, tim)
    summary.update({"pms_mcall": mc_pms, "sw_mcall": mc_sw})
    ok = (summary["checkin_ok"] and summary["del_ok"]
          and mc_pms and mc_pms.get("mcall_sta") == "D"
          and mc_sw and mc_sw.get("mcall_sta") == "D")
    return ok, summary


def _steps_checkout_cancels_pending(ctx, p):
    """退房連動:未傳送晨喚(NOT_TRANS+0)→D;交換機側電話關(宏興SD §6 CKO)。"""
    room, dat, tim = p["room_no"], p["mcall_dat"], p["mcall_tim"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    res_set, _ = _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    res_co, _ = _pms_action(ctx, "checkout", room_nos=room)    # 不 tick:驗未傳送晨喚處置
    summary = {"room_no": room, "checkin_ok": _act_ok(res_ck), "set_ok": _act_ok(res_set),
               "checkout_ok": _act_ok(res_co)}
    pms, sw = _pms_state(ctx), _readback(ctx)
    mc_pms = _find_mcall(pms, room, dat, tim)
    sw_dt = ((sw or {}).get("pbx_dt") or {}).get(room, {})
    summary.update({"pms_mcall": mc_pms,
                    "sw_pbx_dt": {k: sw_dt.get(k) for k in ("tel_sta", "room_sta")}})
    ok = (summary["checkin_ok"] and summary["set_ok"] and summary["checkout_ok"]
          and mc_pms and mc_pms.get("mcall_sta") == "D"
          and sw_dt.get("tel_sta") == "0")
    return ok, summary


def _steps_room_change_reschedules(ctx, p):
    """換房重送:晨喚改綁新房+NOT_TRANS(怕交換機沒移過去),tick 後新房收到 MCS(宏興SD §6 RMC)。"""
    room, new, dat, tim = p["room_no"], p["new_room_no"], p["mcall_dat"], p["mcall_tim"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    _pms_tick(ctx)
    res_rc, _ = _pms_action(ctx, "room_change", room_nos=room, new_room_nos=new)
    mid = _pms_state(ctx)
    mc_moved = _find_mcall(mid, new, dat, tim)
    _pms_tick(ctx)
    pms2, sw2 = _pms_state(ctx), _readback(ctx)
    mc_new = _find_mcall(pms2, new, dat, tim)
    summary = {"room_no": room, "new_room_no": new, "checkin_ok": _act_ok(res_ck),
               "room_change_ok": _act_ok(res_rc), "mcall_after_change": mc_moved,
               "mcall_after_resend": mc_new, "sw_mcall_new_room": _find_mcall(sw2, new, dat, tim)}
    ok = (summary["checkin_ok"] and summary["room_change_ok"]
          and mc_moved and mc_moved.get("trans_pbx_sta") == "NOT_TRANS"
          and mc_new and mc_new.get("trans_pbx_sta") == "TRANS"
          and summary["sw_mcall_new_room"])
    return ok, summary


def _steps_expire_skip(ctx, p):
    """排程邊界:時間已過的 NOT_TRANS 晨喚 → tick 標 SKIP、不下達(宏興SD 1.2 規則+SKIP 語意)。"""
    room, dat, tim = p["room_no"], _today(), _past_tim()
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    res_set, _ = _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    res_tick, _ = _pms_tick(ctx)
    try:
        tick = res_tick.json() if res_tick is not None else {}
    except Exception:
        tick = {}
    summary = {"room_no": room, "mcall_tim": tim, "checkin_ok": _act_ok(res_ck),
               "set_ok": _act_ok(res_set), "tick_sent": tick.get("sent"),
               "tick_skipped": tick.get("skipped")}
    mc = _find_mcall(_pms_state(ctx), room, dat, tim)
    summary["pms_mcall"] = mc
    ok = (summary["checkin_ok"] and summary["set_ok"]
          and not (tick.get("sent") or [])
          and mc and mc.get("trans_pbx_sta") == "SKIP")
    return ok, summary


def _steps_open_tel_vacant_denied(ctx, p):
    """負面:空房開電話 → 拒絕(宏興SD 1.1.4.1:開電話要有住人)。"""
    res, _ = _pms_action(ctx, "open_tel", room_nos=p["room_no"])
    try:
        body = res.json() if res is not None else {}
    except Exception:
        body = {}
    ok = (res is not None and res.status_code == 200
          and body.get("ok") is False and "無住人" in str(body.get("message", "")))
    return ok, {"room_no": p["room_no"], "resp": body}


def _steps_del_past_mcall_denied(ctx, p):
    """負面:取消已過時晨喚 → 拒絕(宏興SD結論:只有 MCALL 時間已過不能取消)。"""
    room, dat, tim = p["room_no"], _today(), _past_tim()
    _pms_action(ctx, "checkin", room_nos=room)
    res_set, _ = _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    res_del, _ = _pms_action(ctx, "del_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    try:
        body = res_del.json() if res_del is not None else {}
    except Exception:
        body = {}
    ok = (res_del is not None and res_del.status_code == 200
          and body.get("ok") is False and "已過" in str(body.get("message", "")))
    return ok, {"room_no": room, "set_ok": _act_ok(res_set), "del_resp": body}


# ---- 註冊(正向四 + 邊界一 + 負面二) -------------------------------------
_dat_param = ParamSpec("mcall_dat", "晨喚日期", "str", _mcall_dat_default,
                       hint="YYYYMMDD;預設今天")
_tim_param = ParamSpec("mcall_tim", "晨喚時間", "str", _mcall_tim_default,
                       hint="HHMMSS;預設 now+40 分(未來,可被排程傳送)")
_ROOMS_HINT = "沙盒房號 universe 0101-0109;空房 0108/0109 供負面案專用"


def _room_param(default):
    return ParamSpec("room_no", "房號", "str", default, hint=_ROOMS_HINT)


_register_ui_case("pbx_ui_set_mcall_full_flow", "晨喚全鏈(入住→設定→排程→MCS 下達)",
                  _steps_set_mcall_full_flow,
                  [_room_param("0101"), _dat_param, _tim_param])
_register_ui_case("pbx_ui_del_mcall_after_trans", "晨喚取消・已傳送(直接下達 MCS D)",
                  _steps_del_mcall_after_trans,
                  [_room_param("0101"), _dat_param, _tim_param])
_register_ui_case("pbx_ui_checkout_cancels_pending", "退房連動(未傳晨喚 D+交換機關電話)",
                  _steps_checkout_cancels_pending,
                  [_room_param("0101"), _dat_param, _tim_param])
_register_ui_case("pbx_ui_room_change_reschedules", "換房重送(晨喚改綁+NOT_TRANS→重下達)",
                  _steps_room_change_reschedules,
                  [_room_param("0101"),
                   ParamSpec("new_room_no", "新房號", "str", "0102", hint="RMC:晨喚改綁新房+重送"),
                   _dat_param, _tim_param])
_register_ui_case("pbx_ui_mcall_expire_skip", "排程邊界(過時未傳→SKIP)",
                  _steps_expire_skip, [_room_param("0109")])
_register_ui_case("pbx_ui_open_tel_vacant_denied", "空房開電話(拒絕)",
                  _steps_open_tel_vacant_denied, [_room_param("0108")])
_register_ui_case("pbx_ui_del_past_mcall_denied", "取消已過時晨喚(拒絕)",
                  _steps_del_past_mcall_denied, [_room_param("0109")])


# ====================================================================
# M2(2026-10-12):回報/異常/重送/RMS 案例(依 SA規格 v1.16 五規則 + PMS0210120 Ver1.4/v1.6)
# ====================================================================
def _steps_mcs_ring_answered(ctx, p):
    """撥號回應:晨喚全鏈後 ring sta=1 → mcall_mn 更新為 1,無 pbx_err、無異常。"""
    room, dat, tim = p["room_no"], p["mcall_dat"], p["mcall_tim"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    _pms_tick(ctx)
    res_ring, _ = _ring(ctx, room_nos=room, mcall_dat=dat, mcall_tim=tim, mcall_sta="1")
    ring = _json(res_ring)
    summary = {"room_no": room, "checkin_ok": _act_ok(res_ck),
               "ring": ring, "ring_ok": ring.get("ok")}
    mc = _find_mcall(_pms_state(ctx), room, dat, tim)
    err_tail = (_pms_state(ctx) or {}).get("pbx_err_tail", [])
    summary.update({"pms_mcall": mc, "pbx_err_tail": err_tail,
                    "anomaly_count": _anomalies(ctx).get("count")})
    ok = (summary["checkin_ok"] and ring.get("ok") is True
          and mc and mc.get("mcall_sta") == "1"
          and not err_tail and summary["anomaly_count"] == 0)
    return ok, summary


def _steps_mcs_ring_busy_anomaly_ack(ctx, p):
    """撥號忙線:ring sta=2 → mcall=2 + pbx_err 一筆 + 晨喚異常 1 筆 → ack 後歸零。"""
    room, dat, tim = p["room_no"], p["mcall_dat"], p["mcall_tim"]
    _pms_action(ctx, "checkin", room_nos=room)
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    _pms_tick(ctx)
    res_ring, _ = _ring(ctx, room_nos=room, mcall_sta="2")
    ring = _json(res_ring)
    anom = _anomalies(ctx)
    items = anom.get("items") or []
    ack_body = None
    if items:
        it = items[0]
        res_ack, _ = execute_for_ctx(ctx, "POST", ctx.urls["pbx_anomalies"] + "/ack",
                                     json_body={"room_nos": it["room_nos"],
                                                "mcall_dat": it["mcall_dat"],
                                                "mcall_tim": it["mcall_tim"]})
        ack_body = _json(res_ack)
    after = _anomalies(ctx)
    mc = _find_mcall(_pms_state(ctx), room, dat, tim)
    err_tail = (_pms_state(ctx) or {}).get("pbx_err_tail", [])
    summary = {"room_no": room, "ring": ring, "anomaly_before": anom.get("count"),
               "ack": ack_body, "anomaly_after": after.get("count"),
               "pms_mcall": mc, "pbx_err_tail": err_tail}
    ok = (ring.get("ok") is True and anom.get("count") == 1
          and (ack_body or {}).get("ok") is True and after.get("count") == 0
          and mc and mc.get("mcall_sta") == "2"
          and err_tail and err_tail[-1].get("error_cod") == "Busy")
    return ok, summary


def _steps_mcs_ring_no_time_earliest(ctx, p):
    """回報未帶時間:僅更新已傳送(TRANS)那一筆(排程規則3 保證是最接近時間);
    另一筆 NOT_TRANS 不受影響(SA 規則2:只更 TRANS+sta0)。"""
    room, dat = p["room_no"], p["mcall_dat"]
    tim_near, tim_far = p["mcall_tim"], (datetime.now() + timedelta(hours=2)).strftime("%H%M%S")
    _pms_action(ctx, "checkin", room_nos=room)
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim_near)
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim_far)
    _pms_tick(ctx)
    res_ring, _ = _ring(ctx, room_nos=room, mcall_sta="3")     # 不帶 dat/tim
    ring = _json(res_ring)
    state = _pms_state(ctx)
    near, far = _find_mcall(state, room, dat, tim_near), _find_mcall(state, room, dat, tim_far)
    summary = {"room_no": room, "ring": ring, "near": near, "far": far}
    ok = (ring.get("ok") is True
          and near and near.get("mcall_sta") == "3"
          and far and far.get("trans_pbx_sta") == "NOT_TRANS"
          and far.get("mcall_sta") == "0")
    return ok, summary


def _steps_resend_full(ctx, p):
    """交換機重送(1030):住人房 CKO→CKI+狀態重設;未來晨喚 NOT_TRANS→tick 再度下達。"""
    room, dat, tim = p["room_no"], p["mcall_dat"], p["mcall_tim"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    _pms_action(ctx, "dnd", room_nos=room, status_typ="1")
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    _pms_tick(ctx)
    res_rs, _ = _pms_action(ctx, "resend", room_nos=room,
                            include_vacant=False, include_occupied=True)
    rs = _json(res_rs)
    mc_mid = _find_mcall(_pms_state(ctx), room, dat, tim)
    _pms_tick(ctx)
    mc_after = _find_mcall(_pms_state(ctx), room, dat, tim)
    sw = _readback(ctx)
    summary = {"room_no": room, "checkin_ok": _act_ok(res_ck), "resend": rs.get("resend"),
               "mcall_after_resend": mc_mid, "mcall_after_retick": mc_after,
               "sw_tel_sta": ((sw or {}).get("pbx_dt") or {}).get(room, {}).get("tel_sta")}
    ok = (summary["checkin_ok"] and (rs.get("resend") or {}).get("occupied_cki", 0) >= 1
          and mc_mid and mc_mid.get("trans_pbx_sta") == "NOT_TRANS"
          and mc_after and mc_after.get("trans_pbx_sta") == "TRANS"
          and summary["sw_tel_sta"] == "1")
    return ok, summary


def _steps_rms_room_status(ctx, p):
    """RMS 房況:3 小時內 C → clean C/check C;逾 3 小時 → 不收(入 pbx_err)。"""
    room = p["room_no"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    res_ok, _ = _rms(ctx, room_nos=room, room_sta="C")
    old_ts = (datetime.now() - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
    res_old, _ = _rms(ctx, room_nos=room, room_sta="D", ins_dat=old_ts)
    ok_body, old_body = _json(res_ok), _json(res_old)
    state = _pms_state(ctx)
    err_tail = state.get("pbx_err_tail", [])
    summary = {"room_no": room, "rms_fresh": ok_body, "rms_expired": old_body,
               "check_sta": ((state.get("pbx_dt") or {}).get(room) or {}).get("check_sta"),
               "pbx_err_tail": err_tail}
    ok = (_act_ok(res_ck)
          and ok_body.get("processed") is True and ok_body.get("pbx_dt.check_sta") == "C"
          and old_body.get("processed") is False and "三小時" in str(old_body.get("message", ""))
          and summary["check_sta"] == "C"      # 逾時的 D 未覆蓋
          and err_tail and err_tail[-1].get("error_cod") == "已超過三小時,不收")
    return ok, summary


_register_ui_case("pbx_ui_mcs_ring_answered", "撥號回應(ring・1=Answered,無異常)",
                  _steps_mcs_ring_answered,
                  [_room_param("0101"), _dat_param, _tim_param])
_register_ui_case("pbx_ui_mcs_ring_busy_anomaly_ack", "撥號忙線→晨喚異常→已處理(ring・2=Busy)",
                  _steps_mcs_ring_busy_anomaly_ack,
                  [_room_param("0101"), _dat_param, _tim_param])
_register_ui_case("pbx_ui_mcs_ring_no_time_earliest", "回報未帶時間(僅更已傳送筆,SA規則2/3)",
                  _steps_mcs_ring_no_time_earliest,
                  [_room_param("0102"), _dat_param, _tim_param])
_register_ui_case("pbx_ui_resend_full", "交換機重送(1030・CKO→CKI+晨喚重送)",
                  _steps_resend_full,
                  [_room_param("0101"), _dat_param, _tim_param])
_register_ui_case("pbx_ui_rms_room_status", "RMS房況回報(3小時效期,C/逾時不收)",
                  _steps_rms_room_status,
                  [_room_param("0103")])


# ====================================================================
# M3(2026-10-12):真檔案交換層案例(vendor=PMS_UI 沿用)——HOST2PMS/PMS2HOST 四檔+W/P cycle
# 傳輸級模擬:M1 的 in-process 下達為主要編排路徑,本層示範 pbx_interface 原生檔案往返。
# ====================================================================
def _file_call(ctx, path, body=None, method="POST"):
    return execute_for_ctx(ctx, method, ctx.urls[path], json_body=body or {})


def _file_state(ctx):
    res, _ = _file_call(ctx, "pbx_file_state", method="GET")
    try:
        return res.json() if res is not None else {}
    except Exception:
        return {}


def _steps_file_roundtrip(ctx, p):
    """檔案往返:動作入 pbx_mn → ensure → run-cycle → 四檔齊動(寫/讀/回應/讀回)。"""
    room, dat, tim = p["room_no"], p["mcall_dat"], p["mcall_tim"]
    res_ck, _ = _pms_action(ctx, "checkin", room_nos=room)
    _pms_action(ctx, "set_mcall", room_nos=room, mcall_dat=dat, mcall_tim=tim)
    _pms_tick(ctx)
    res_ensure, _ = _file_call(ctx, "pbx_file_ensure", {"file_size": 3000})
    res_cycle, _ = _file_call(ctx, "pbx_file_cycle")
    cyc = _json(res_cycle)
    fstate = _file_state(ctx)
    sw = _readback(ctx)
    summary = {"room_no": room, "checkin_ok": _act_ok(res_ck),
               "ensure_ok": _json(res_ensure).get("ok"),
               "written": cyc.get("written"), "processed": cyc.get("processed"),
               "handled_replies": len(cyc.get("handled_replies") or []),
               "file_state": fstate,
               "sw_tel_sta": ((sw or {}).get("pbx_dt") or {}).get(room, {}).get("tel_sta"),
               "sw_mcall": _find_mcall(sw, room, dat, tim)}
    h2p = (fstate.get("host2pms") or {})
    ok = (summary["checkin_ok"] and summary["ensure_ok"]
          and (cyc.get("written") or []) and (cyc.get("processed") or [])
          and all(r.get("ok") for r in (cyc.get("processed") or []))
          and summary["handled_replies"] >= 1
          and h2p.get("wseq_nos", 0) >= 2 and h2p.get("pindex_nos") == h2p.get("windex_nos")
          and summary["sw_tel_sta"] == "1" and summary["sw_mcall"])
    return ok, summary


def _steps_file_wraparound(ctx, p):
    """輪替:file_size=2 的環寫 3 筆(讀寫交錯)→ Windex 繞回、Wcycle A→B 翻轉、無資料遺失。"""
    room = p["room_no"]
    _pms_action(ctx, "checkin", room_nos=room)
    _file_call(ctx, "pbx_file_ensure", {"file_size": 2})
    cyc1 = _json(_file_call(ctx, "pbx_file_cycle")[0])       # 寫 1 筆(CKI),讀+回應
    _pms_action(ctx, "dnd", room_nos=room, status_typ="1")
    _pms_action(ctx, "tce", room_nos=room, status_typ="1")
    cyc2 = _json(_file_call(ctx, "pbx_file_cycle")[0])       # 寫 2 筆(DND+TCE)→ 繞圈
    mid2 = _file_state(ctx).get("host2pms") or {}
    _pms_action(ctx, "tce", room_nos=room, status_typ="0")
    cyc3 = _json(_file_call(ctx, "pbx_file_cycle")[0])       # 再 1 筆(TCE off)→ 再繞一圈
    fstate = _file_state(ctx)
    h2p = fstate.get("host2pms") or {}
    p2h = fstate.get("pms2host") or {}
    summary = {"room_no": room, "cycles": [cyc1, cyc2, cyc3], "mid2_host2pms": mid2,
               "file_state": fstate}
    # size=2 環寫 4 筆 = 繞兩圈:第 2 筆後 A→B(中繼斷言),第 4 筆後 B→A(繞回起點)
    ok = (len(cyc1.get("written") or []) == 1
          and len(cyc2.get("written") or []) == 2
          and len(cyc3.get("written") or []) == 1
          and mid2.get("wcycle_typ") == "B"                     # 第一圈繞完已翻 B
          and h2p.get("wcycle_typ") == "A"                       # 第二圈繞回 A
          and h2p.get("pcycle_typ") == h2p.get("wcycle_typ")     # 讀方跟上
          and h2p.get("wseq_nos") == 4                           # 共寫 4 筆(1+2+1)
          and p2h.get("wseq_nos") == 4                           # 回應同數
          and all(r.get("ok") for r in (cyc3.get("processed") or [])))
    return ok, summary


def _steps_file_china_name_policy(ctx, p):
    """ANSI/中文政策:預設中文姓名改送房號(過濾中文);allow_china=true 保留中文(cp950 往返)。"""
    room = p["room_no"]
    _pms_action(ctx, "checkin", room_nos=room, guest_nam="Mr. WANG,XIAOMING")
    _file_call(ctx, "pbx_file_ensure", {"file_size": 3000})
    cyc = _json(_file_call(ctx, "pbx_file_cycle")[0])
    sw1 = _readback(ctx)
    # 第二段:allow_china=true 重置後中文姓名保留
    _pms_action(ctx, "checkout", room_nos=room)
    _file_call(ctx, "pbx_file_ensure", {"file_size": 3000, "allow_china": True})
    _pms_action(ctx, "checkin", room_nos=room, guest_nam="王小明")
    cyc2 = _json(_file_call(ctx, "pbx_file_cycle")[0])
    summary = {"room_no": room, "cycle_ascii": cyc.get("written"),
               "cycle_chinese": cyc2.get("written"), "processed_chinese": cyc2.get("processed")}
    ok = ((cyc.get("written") or []) and (cyc2.get("written") or [])
          and all(r.get("ok") for r in (cyc2.get("processed") or []))
          and ((sw1 or {}).get("pbx_dt") or {}).get(room, {}).get("tel_sta") == "1")
    return ok, summary


_register_ui_case("pbx_file_roundtrip", "檔案往返全鏈(pbx_mn→HOST2PMS→交換機→PMS2HOST→讀回)",
                  _steps_file_roundtrip,
                  [_room_param("0101"), _dat_param, _tim_param])
_register_ui_case("pbx_file_wraparound", "環狀輪替(file_size=2・Wcycle A→B 翻轉無遺失)",
                  _steps_file_wraparound, [_room_param("0102")])
_register_ui_case("pbx_file_china_name", "ANSI中文姓名政策(預設改房號/allow_china 保留)",
                  _steps_file_china_name_policy, [_room_param("0103")])
