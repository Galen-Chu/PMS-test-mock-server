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
