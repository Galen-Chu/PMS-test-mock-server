# orchestrator/runners/pbx.py
"""☎️ 交換機(PABX)模組案例 — mock 交換機側在 server/pbx/(pbx_interface 公版記錄介面)。

方向:德安 HOST → 交換機(runner 發砲端=模擬德安 C# 交換機程式寫 HOST2PMS.DAT;
mock 被測端=模擬計費系統 PMS MODULE 讀檔/回應)。契約=pbx_interface.doc 固定長度記錄。

M0(2026-10-12)十案:
- 正向七案:checkin 開電話(CKI)、晨喚設定/取消(MCS 0/D)、勿擾/限撥(DND/TCE)、
  退房關電話(CKO,連動晨呼取消)、換房(RMC,pbx_dt+晨呼搬移);
- 負向三案(固定劇本不宣告 params):未知房號(ERR ROOM_NOT_FOUND)、
  壞記錄(417)、空房設勿擾(ERR GUEST_NOT_IN,宏興 SD 前置規則)。

REAL 環境:交換機介面為檔案交換、無雲端 URL → 案例一律 SKIP(REAL_NOT_SUPPORTED),
待 SA 提供 PMS0210120 REST API SD(func_id 1011-1027)後於 M1 開放(計畫文件 §4)。
"""
import itertools
import time as _t
from datetime import datetime, timedelta

from ..models import CaseResult, RunContext, ParamSpec, CASE_SKIP
from ..registry import registry
from hardware.simulate_speaker import execute_for_ctx
from server.pbx.vendors.vendor_PABX import (
    build_host_record, parse_response_fields,
)

from .helpers import _p, _ok, _fail

_seq = itertools.count(1)   # 模擬 pbx_mn seq_nos 流水(Wcycle 檔案輪替見計畫文件 §2)

# CKI 前置固定測資(非案例參數;正式住客資料面屬 M1 API 開通後的範圍)
_CKI_SEED = {"lang_cod": "001", "vip_sta": "N", "master_nos": "0101",
             "guest_nam": "Mr. CHU,GALEN", "account_nos": "CI20261012001"}


def _mcall_dat_default(ctx):
    return datetime.now().strftime("%Y%m%d")


def _mcall_tim_default(ctx):
    return (datetime.now() + timedelta(minutes=40)).strftime("%H%M%S")


def _real_skip(case_id, scenario) -> CaseResult:
    """REAL 環境一律跳過(M0=本地檔案介面模擬,無雲端端點)。"""
    return CaseResult(
        case_id=case_id, run_id="", module=scenario.module, vendor=scenario.vendor,
        scenario_name=scenario.name, endpoint=scenario.endpoint, status=CASE_SKIP,
        error_category="REAL_NOT_SUPPORTED",
        response_payload={"__note__": "M0 為本地 mock 檔案介面;REAL 發砲待 SA 提供 "
                                      "PMS0210120 API SD(func_id 1011-1027)後於 M1 開放"},
    )


def _post_records(ctx, records):
    """批次送指令記錄 → (response, err)。識別二元組沿用環境矩陣。"""
    athena = str(ctx.headers_amenity.get("athena") or "25")
    hotel = str(ctx.headers_amenity.get("hotel") or "01")
    payload = {"athenaId": athena, "hotelCode": hotel, "records": records}
    return execute_for_ctx(ctx, "POST", ctx.urls["pbx_commands"], json_body=payload)


def _resp_fields(res, idx=0):
    """取回應記錄陣列第 idx 筆並解欄位;失敗回 ({}, None)。"""
    try:
        recs = (res.json() or {}).get("responses") or []
    except Exception:
        recs = []
    if idx >= len(recs):
        return {}, None
    try:
        return parse_response_fields(recs[idx]), recs[idx]
    except Exception:
        return {}, None


def _readback(ctx):
    """LOCAL 閉環:內部回讀 mock 交換機狀態(REAL 環境無此端點,呼叫端自行判斷)。"""
    res, _ = execute_for_ctx(ctx, "GET", ctx.urls["pbx_internal"])
    if res is None or res.status_code != 200:
        return None
    return res.json()


def _summarize(recs_desc, res):
    """共用摘要:結構化指令描述 + 逐筆回應碼(runner 不把 192-byte 原文塞進結果,
    原文已由 steps 的 HTTP 稽核錄製)。"""
    out = {"records": recs_desc, "http_status": getattr(res, "status_code", None)}
    try:
        out["results"] = (res.json() or {}).get("results")
    except Exception:
        pass
    return out


def _simple_case(case_id, build_records, assert_readback=None):
    """共用案例骨架:REAL→SKIP;送記錄→斷言全 SUC(或自訂 resp 判斷)→LOCAL 回讀。"""

    def runner(ctx: RunContext) -> CaseResult:
        scenario = registry.get(case_id)   # 呼叫期解析(註冊後才有;同 roomcontrol 慣例)
        if ctx.use_real:
            return _real_skip(case_id, scenario)
        p = _p(ctx, case_id)
        desc, records = build_records(p)
        t0 = _t.perf_counter()
        res, err = _post_records(ctx, records)
        dur = int((_t.perf_counter() - t0) * 1000)
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=desc,
                         response_payload={"__error__": err or "no response"})
        summary = _summarize(desc, res)
        all_suc = (res.status_code == 200
                   and all(r.get("resp_cod") == "SUC" for r in (summary.get("results") or [])))
        summary["all_suc"] = all_suc
        ok = all_suc
        if ok and assert_readback and not ctx.use_real:
            state = _readback(ctx)
            if state is not None:
                rb = assert_readback(p, state)
                summary["state_readback"] = rb
                ok = rb is not False
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)

    return runner


def _next_seq():
    return next(_seq)


# ---- 記錄組裝(案例層;對齊 pbx_interface 各指令佈局) --------------------
def _rec_cki(room, **over):
    fields = dict(_CKI_SEED, phone_nos=room, master_nos=room, **over)
    return build_host_record("CKI", fields, _next_seq())


def _rec_mcs(room, mcall_dat, mcall_tim, mcall_sta="0"):
    return build_host_record("MCS", {"phone_nos": room, "mcall_dat": mcall_dat,
                                     "mcall_tim": mcall_tim, "mcall_sta": mcall_sta}, _next_seq())


def _rec_status(inst, room, status_typ):
    return build_host_record(inst, {"phone_nos": room, "status_typ": status_typ}, _next_seq())


# ====================================================================
# 正向七案
# ====================================================================
def _checkin_readback(p, s):
    dt = (s.get("pbx_dt") or {}).get(p["room_no"])
    if dt is None:
        return False
    if dt.get("tel_sta") != "1" or dt.get("room_sta") != "O" or dt.get("lang_cod") != p["lang_cod"]:
        return False
    return {"tel_sta": dt.get("tel_sta"), "room_sta": dt.get("room_sta"),
            "lang_cod": dt.get("lang_cod")}


_pbx_checkin_open_tel = _simple_case(
    "pbx_checkin_open_tel",
    lambda p: ([{"inst_cod": "CKI", "phone_nos": p["room_no"], "lang_cod": p["lang_cod"],
                 "vip_sta": p["vip_sta"], "guest_nam": p["guest_nam"],
                 "account_nos": p["account_nos"]}],
               [_rec_cki(p["room_no"], lang_cod=p["lang_cod"], vip_sta=p["vip_sta"],
                         guest_nam=p["guest_nam"], account_nos=p["account_nos"])]),
    _checkin_readback,
)

_pbx_morning_call_set = _simple_case(
    "pbx_morning_call_set",
    lambda p: ([{"inst_cod": "CKI", "phone_nos": p["room_no"]},
                {"inst_cod": "MCS", "phone_nos": p["room_no"], "mcall_dat": p["mcall_dat"],
                 "mcall_tim": p["mcall_tim"], "mcall_sta": "0"}],
               [_rec_cki(p["room_no"]),
                _rec_mcs(p["room_no"], p["mcall_dat"], p["mcall_tim"])]),
    lambda p, s: _mcall_readback(s, p["room_no"], p["mcall_dat"], p["mcall_tim"], "0"),
)

_pbx_morning_call_cancel = _simple_case(
    "pbx_morning_call_cancel",
    lambda p: ([{"inst_cod": "CKI", "phone_nos": p["room_no"]},
                {"inst_cod": "MCS", "phone_nos": p["room_no"], "mcall_dat": p["mcall_dat"],
                 "mcall_tim": p["mcall_tim"], "mcall_sta": "0"},
                {"inst_cod": "MCS", "phone_nos": p["room_no"], "mcall_dat": p["mcall_dat"],
                 "mcall_tim": p["mcall_tim"], "mcall_sta": "D"}],
               [_rec_cki(p["room_no"]),
                _rec_mcs(p["room_no"], p["mcall_dat"], p["mcall_tim"]),
                _rec_mcs(p["room_no"], p["mcall_dat"], p["mcall_tim"], mcall_sta="D")]),
    lambda p, s: _mcall_readback(s, p["room_no"], p["mcall_dat"], p["mcall_tim"], "D"),
)

_pbx_dnd_set = _simple_case(
    "pbx_dnd_set",
    lambda p: ([{"inst_cod": "CKI", "phone_nos": p["room_no"]},
                {"inst_cod": "DND", "phone_nos": p["room_no"], "status_typ": p["status_typ"]}],
               [_rec_cki(p["room_no"]), _rec_status("DND", p["room_no"], p["status_typ"])]),
    lambda p, s: _field_readback(s, p["room_no"], "dnd_cod", p["status_typ"]),
)

_pbx_tce_set = _simple_case(
    "pbx_tce_set",
    lambda p: ([{"inst_cod": "CKI", "phone_nos": p["room_no"]},
                {"inst_cod": "TCE", "phone_nos": p["room_no"], "status_typ": p["status_typ"]}],
               [_rec_cki(p["room_no"]), _rec_status("TCE", p["room_no"], p["status_typ"])]),
    lambda p, s: _field_readback(s, p["room_no"], "tce_cod", p["status_typ"]),
)

_pbx_checkout_close_tel = _simple_case(
    "pbx_checkout_close_tel",
    lambda p: ([{"inst_cod": "CKI", "phone_nos": p["room_no"]},
                {"inst_cod": "MCS", "phone_nos": p["room_no"], "mcall_dat": p["mcall_dat"],
                 "mcall_tim": p["mcall_tim"], "mcall_sta": "0"},
                {"inst_cod": "CKO", "phone_nos": p["room_no"]}],
               [_rec_cki(p["room_no"]),
                _rec_mcs(p["room_no"], p["mcall_dat"], p["mcall_tim"]),
                build_host_record("CKO", {"phone_nos": p["room_no"]}, _next_seq())]),
    lambda p, s: _checkout_readback(s, p["room_no"], p["mcall_dat"], p["mcall_tim"]),
)

_pbx_room_change = _simple_case(
    "pbx_room_change",
    lambda p: ([{"inst_cod": "CKI", "phone_nos": p["room_no"]},
                {"inst_cod": "RMC", "ophone_nos": p["room_no"], "nphone_nos": p["new_room_no"]}],
               [_rec_cki(p["room_no"]),
                build_host_record("RMC", {"ophone_nos": p["room_no"],
                                          "nphone_nos": p["new_room_no"]}, _next_seq())]),
    lambda p, s: _rmc_readback(s, p["room_no"], p["new_room_no"]),
)


def _mcall_readback(s, room, dat, tim, expect_sta):
    for mc in s.get("mcall_mn") or []:
        if (mc.get("room_nos"), mc.get("mcall_dat"), mc.get("mcall_tim")) == (room, dat, tim):
            return False if mc.get("mcall_sta") != expect_sta else {"mcall_sta": mc.get("mcall_sta")}
    return False


def _field_readback(s, room, field, expect):
    dt = (s.get("pbx_dt") or {}).get(room)
    if dt is None:
        return False
    return {field: dt.get(field)} if dt.get(field) == str(expect) else False


def _checkout_readback(s, room, dat, tim):
    dt = (s.get("pbx_dt") or {}).get(room)
    if dt is None or dt.get("tel_sta") != "0" or dt.get("room_sta") != "V":
        return False
    mcs = [mc for mc in (s.get("mcall_mn") or [])
           if (mc.get("room_nos"), mc.get("mcall_dat"), mc.get("mcall_tim")) == (room, dat, tim)]
    if not mcs or mcs[0].get("mcall_sta") != "C":
        return False
    return {"tel_sta": "0", "mcall_sta": mcs[0].get("mcall_sta")}


def _rmc_readback(s, old, new):
    dt_old = (s.get("pbx_dt") or {}).get(old)
    dt_new = (s.get("pbx_dt") or {}).get(new)
    if not dt_old or not dt_new:
        return False
    if dt_new.get("tel_sta") != "1" or dt_new.get("room_sta") != "O":
        return False
    if dt_old.get("tel_sta") != "0" or dt_old.get("room_sta") != "V":
        return False
    return {"new_tel_sta": dt_new.get("tel_sta"), "old_room_sta": dt_old.get("room_sta")}


# ====================================================================
# 負向三案(固定劇本)
# ====================================================================
def _unknown_room(ctx: RunContext) -> CaseResult:
    case_id, scenario = "pbx_unknown_room", registry.get("pbx_unknown_room")
    if ctx.use_real:
        return _real_skip(case_id, scenario)
    desc = [{"inst_cod": "CKI", "phone_nos": "9999"}]
    records = [_rec_cki("9999")]
    t0 = _t.perf_counter()
    res, err = _post_records(ctx, records)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail(case_id, "", scenario, dur, request_payload=desc,
                     response_payload={"__error__": err or "no response"})
    summary = _summarize(desc, res)
    f, _raw = _resp_fields(res)
    summary.update({"resp_cod": f.get("resp_cod"), "msg_cod": f.get("msg_cod")})
    # 反向斷言:HTTP 200 + ERR + Msg_cod=ROOM_NOT_FOUND
    ok = (res.status_code == 200 and f.get("resp_cod") == "ERR"
          and str(f.get("msg_cod", "")).startswith("ROOM_NOT_FOUND"))
    if ok:
        return _ok(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)
    return _fail(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)


def _bad_record(ctx: RunContext) -> CaseResult:
    case_id, scenario = "pbx_bad_record", registry.get("pbx_bad_record")
    if ctx.use_real:
        return _real_skip(case_id, scenario)
    desc = [{"inst_cod": "!!", "malformed": "長度不足的壞記錄"}]
    t0 = _t.perf_counter()
    res, err = _post_records(ctx, ["NOT-A-RECORD"])
    dur = int((_t.perf_counter() - t0) * 1000)
    if err:
        return _fail(case_id, "", scenario, dur, request_payload=desc,
                     response_payload={"__error__": err})
    body = None
    try:
        body = res.json()
    except Exception:
        body = {"status_code": res.status_code}
    # 反向斷言:結構壞記錄 → 417(對齊沙盒錯誤信封)
    if res.status_code == 417 and str((body or {}).get("code")) == "417":
        return _ok(case_id, "", scenario, dur, request_payload=desc, response_payload=body)
    return _fail(case_id, "", scenario, dur, request_payload=desc, response_payload=body)


def _dnd_without_guest(ctx: RunContext) -> CaseResult:
    case_id, scenario = "pbx_dnd_without_guest", registry.get("pbx_dnd_without_guest")
    if ctx.use_real:
        return _real_skip(case_id, scenario)
    desc = [{"inst_cod": "DND", "phone_nos": "0108", "status_typ": "1", "precondition": "未入住"}]
    records = [_rec_status("DND", "0108", "1")]
    t0 = _t.perf_counter()
    res, err = _post_records(ctx, records)
    dur = int((_t.perf_counter() - t0) * 1000)
    if err or res is None:
        return _fail(case_id, "", scenario, dur, request_payload=desc,
                     response_payload={"__error__": err or "no response"})
    summary = _summarize(desc, res)
    f, _raw = _resp_fields(res)
    summary.update({"resp_cod": f.get("resp_cod"), "msg_cod": f.get("msg_cod")})
    # 反向斷言:空房設勿擾 → ERR + GUEST_NOT_IN(宏興 SD「有住人才可以設」)
    ok = (res.status_code == 200 and f.get("resp_cod") == "ERR"
          and str(f.get("msg_cod", "")).startswith("GUEST_NOT_IN"))
    if ok:
        return _ok(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)
    return _fail(case_id, "", scenario, dur, request_payload=desc, response_payload=summary)


# ====================================================================
# 註冊(ParamSpec 宣告;hint 用 SA/宏興 SD 術語)
# ====================================================================
_dat_hint = "介面 9(8) YYYYMMDD;預設今天"
_tim_hint = "介面 9(6) HHMMSS;預設 now+40 分(避免落在過去被排程 SKIP)"

registry.register(
    "pbx_checkin_open_tel", module="pbx", vendor="PABX",
    name="入住開電話(CKI)", endpoint="/pbx/host-commands", runner=_pbx_checkin_open_tel,
    params=[
        ParamSpec("room_no", "房號(分機)", "str", "0101", hint="pbx_interface Phone_nos X(6)"),
        ParamSpec("lang_cod", "交換機語言", "str", "001", hint="PBX specific;pbx_dt.lang_cod"),
        ParamSpec("vip_sta", "VIP", "str", "N", hint="'Y'=VIP,其他非 VIP"),
        ParamSpec("guest_nam", "住客英文名", "str", "Mr. CHU,GALEN",
                  hint="宏興SD:Mr./Miss.+last+','+first;過濾後空白改送房號;取前30碼"),
        ParamSpec("account_nos", "Chkin_nos", "str", "CI20261012001", hint="interface Account_nos X(20)"),
    ],
)
registry.register(
    "pbx_morning_call_set", module="pbx", vendor="PABX",
    name="晨喚設定(MCS)", endpoint="/pbx/host-commands", runner=_pbx_morning_call_set,
    params=[
        ParamSpec("room_no", "房號(分機)", "str", "0101"),
        ParamSpec("mcall_dat", "晨喚日期", "str", _mcall_dat_default, hint=_dat_hint),
        ParamSpec("mcall_tim", "晨喚時間", "str", _mcall_tim_default, hint=_tim_hint),
    ],
)
registry.register(
    "pbx_morning_call_cancel", module="pbx", vendor="PABX",
    name="晨喚取消(MCS・D)", endpoint="/pbx/host-commands", runner=_pbx_morning_call_cancel,
    params=[
        ParamSpec("room_no", "房號(分機)", "str", "0101"),
        ParamSpec("mcall_dat", "晨喚日期", "str", _mcall_dat_default, hint=_dat_hint),
        ParamSpec("mcall_tim", "晨喚時間", "str", _mcall_tim_default, hint=_tim_hint),
    ],
)
registry.register(
    "pbx_dnd_set", module="pbx", vendor="PABX",
    name="勿擾設定(DND)", endpoint="/pbx/host-commands", runner=_pbx_dnd_set,
    params=[
        ParamSpec("room_no", "房號(分機)", "str", "0101"),
        ParamSpec("status_typ", "設定/取消", "str", "1", hint="1:設定 0:取消;需有住人且電話開"),
    ],
)
registry.register(
    "pbx_tce_set", module="pbx", vendor="PABX",
    name="限撥設定(TCE)", endpoint="/pbx/host-commands", runner=_pbx_tce_set,
    params=[
        ParamSpec("room_no", "房號(分機)", "str", "0101"),
        ParamSpec("status_typ", "設定/取消", "str", "1", hint="1:限制撥出ON 0:OFF;需有住人且電話開"),
    ],
)
registry.register(
    "pbx_checkout_close_tel", module="pbx", vendor="PABX",
    name="退房關電話(CKO・連動取消晨喚)", endpoint="/pbx/host-commands", runner=_pbx_checkout_close_tel,
    params=[
        ParamSpec("room_no", "房號(分機)", "str", "0101"),
        ParamSpec("mcall_dat", "晨喚日期", "str", _mcall_dat_default, hint=_dat_hint),
        ParamSpec("mcall_tim", "晨喚時間", "str", _mcall_tim_default, hint=_tim_hint),
    ],
)
registry.register(
    "pbx_room_change", module="pbx", vendor="PABX",
    name="換房(RMC・狀態搬移)", endpoint="/pbx/host-commands", runner=_pbx_room_change,
    params=[
        ParamSpec("room_no", "原房號", "str", "0101"),
        ParamSpec("new_room_no", "新房號", "str", "0102", hint="RMC:舊房關電話、新房開電話;晨呼跟著移房"),
    ],
)
registry.register("pbx_unknown_room", module="pbx", vendor="PABX",
                  name="未知房號(ERR・ROOM_NOT_FOUND)", endpoint="/pbx/host-commands",
                  runner=_unknown_room)
registry.register("pbx_bad_record", module="pbx", vendor="PABX",
                  name="壞記錄(417)", endpoint="/pbx/host-commands", runner=_bad_record)
registry.register("pbx_dnd_without_guest", module="pbx", vendor="PABX",
                  name="空房設勿擾(ERR・GUEST_NOT_IN)", endpoint="/pbx/host-commands",
                  runner=_dnd_without_guest)
