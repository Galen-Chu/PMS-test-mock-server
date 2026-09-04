# orchestrator/runners/roomcontrol.py
"""🌡️ 房控模組案例(roomcontrol / A7 公版 XML 介面)— 對齊 sa_docs/sa10 V1.2。"""
from ..registry import registry
from ..models import CaseResult, RunContext, ParamSpec
from hardware.simulate_speaker import execute_for_ctx
from server.roomcontrol.vendors.vendor_A7_XML import (
    build_room_sta_push, build_room_inf_query, build_return_query,
    build_clean_push, build_rmtemp_push, build_keybox_push,
    build_rowset_xml, action_dat_now, reve_room_sta, reve_room_inf,
    parse_rowset_xml, DEFAULT_STATUS_BITS,
)
from server.roomcontrol.vendors import vendor_MINXON, vendor_CHAOFENG

from .helpers import _p, _ok, _fail, _expect_417

# ====================================================================
# 🌡️ 房控(roomcontrol / A7 公版 XML 介面)— 對齊 sa_docs/sa10 V1.2
# 方向:廠商→PMS(沙盒發砲端=模擬房控廠商;mock PMS 側在 server/roomcontrol/)。
# 2026-09-03 起掛雙廠商:MINXON 民笙(thirdParty=81)、CHAOFENG 超烽(thirdParty=86),
# 每家三案:B4 ROOM_STA 房況推送、A6 ROOM_INF 房況查詢、A10 RETURN 全部房況。
# 傳輸:POST /third-party/import-sync-files(sa8/sa9 REST 版;GET TxnData 閘門版見 sa10)。
# ====================================================================
_RC_VENDORS = [
    (vendor_MINXON.VENDOR_ID, vendor_MINXON.VENDOR_LABEL, vendor_MINXON.THIRD_PARTY_CODE),
    (vendor_CHAOFENG.VENDOR_ID, vendor_CHAOFENG.VENDOR_LABEL, vendor_CHAOFENG.THIRD_PARTY_CODE),
]


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
    """取回應項與其 responseBody 解析列;失敗回 ({}, [])。

    相容三種實況(2026-09-03 REAL_QA 實測):
    - sa8/sa9 swagger:200 → [VendorImportSyncDataResponse, ...](沙盒 mock)
    - REAL_QA:Athena 標準信封 {"code":"2000","data":[...]} 包著同結構
    - CHAOFENG(86) 實測:data 內可能混有 [全 null 的失敗殼, 成功實料] → 掃描挑首個
      procStatus=true 或帶 responseBody 的項目,而非固定取 [0]
    """
    try:
        body = res.json()
    except Exception:
        body = None
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        items = body["data"]
    elif isinstance(body, list):
        items = body
    else:
        items = []
    item = next((it for it in items
                 if isinstance(it, dict) and (it.get("procStatus") is True or it.get("responseBody"))),
                (items[0] if items else {}))
    rows = []
    if item.get("responseBody"):
        try:
            rows = parse_rowset_xml(item["responseBody"])
        except Exception:
            rows = []
    return item, rows


def _register_rc_vendor_cases(vendor_id, vendor_label, tp_code):
    """以閉包工廠為一家 A7 公版房控廠商註冊九案。

    RC0 三案:push(B4 ROOM_STA)/ room_inf(A6)/ return(A10);
    RC2(2026-09-04)六案:clean/rmtemp(B4 同族)、keybox(B5)、
    bad_xml/unknown_action/missing_room_nos(負面,固定劇本不宣告 params)。
    REVE-CODE 依廠商代號組出(0300+代號+動作碼);third_party_code 預設帶實際代碼仍可覆寫
    (SIT/MAS 等環境代碼若不同,UI 直接改)。
    """
    slug = vendor_id.lower()

    def _room_sta_push(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_room_sta_push"
        scenario = registry.get(case_id)
        p = _p(ctx, case_id)
        xml_str = build_room_sta_push(p["room_no"], p["status_bits"], vendor_code=tp_code)
        payload = _a7_import_payload(ctx, xml_str, p["third_party_code"])
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary = {"room_no": p["room_no"], "action_cod": f"#ROOM_STA#{p['status_bits']}#"}
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
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
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    def _room_inf_query(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_room_inf"
        scenario = registry.get(case_id)
        p = _p(ctx, case_id)
        xml_str = build_room_inf_query(p["room_no"], vendor_code=tp_code)
        payload = _a7_import_payload(ctx, xml_str, p["third_party_code"], file_name="C002.xml")
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        summary = {"procStatus": item.get("procStatus"), "row_count": len(rows),
                   "rows": rows,   # 結構化住客列(JSON 稽核可直接檢視;HTTP 稽核另有原始 XML)
                   "response_body_raw": item.get("responseBody")}
        first = rows[0] if rows else {}
        ok = (res.status_code == 200 and item.get("procStatus") is True
              and rows and first.get("ROOM_STA") in ("O", "S", "V", "R")
              and first.get("RETN-CODE") == "0000")
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    def _return_all(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_return"
        scenario = registry.get(case_id)
        p = _p(ctx, case_id)
        xml_str = build_return_query(vendor_code=tp_code)
        payload = _a7_import_payload(ctx, xml_str, p["third_party_code"], file_name="C003.xml")
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        summary = {"procStatus": item.get("procStatus"), "row_count": len(rows),
                   "rows": rows, "response_body_raw": item.get("responseBody")}
        first = rows[0] if rows else {}
        ok = (res.status_code == 200 and item.get("procStatus") is True
              and rows and first.get("ROOM_STA") in ("O", "V", "R", "S")
              and first.get("RETN-CODE") == "0000")
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    # ---- RC2(2026-09-04):B4 同族單值/室溫 + B5 KeyBox(正向,LOCAL 位元級回讀閉環) ----

    def _clean_push(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_clean"
        scenario = registry.get(case_id)
        p = _p(ctx, case_id)
        xml_str = build_clean_push(p["room_no"], p["clean_state"], vendor_code=tp_code)
        payload = _a7_import_payload(ctx, xml_str, p["third_party_code"])
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary = {"room_no": p["room_no"], "action_cod": "CLEAN", "action_sta": p["clean_state"]}
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        retn = rows[0].get("RETN-CODE") if rows else None
        summary.update({"procStatus": item.get("procStatus"), "retn_code": retn})
        ok = res.status_code == 200 and item.get("procStatus") is True and retn == "0000"
        # LOCAL 閉環:位元 9(房間清潔)已更新為 ACTION_STA 值
        if ok and not ctx.use_real:
            res_rb, _ = execute_for_ctx(ctx, "GET", ctx.urls["roomcontrol_internal"])
            if res_rb is not None and res_rb.status_code == 200:
                state = (res_rb.json() or {}).get("room_control_state") or {}
                bits = (state.get(p["room_no"]) or {}).get("status_bits") or ""
                summary["state_readback_bit9"] = bits[8] if len(bits) == 16 else None
                ok = summary["state_readback_bit9"] == str(p["clean_state"])
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    def _rmtemp_push(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_rmtemp"
        scenario = registry.get(case_id)
        p = _p(ctx, case_id)
        xml_str = build_rmtemp_push(p["room_no"], p["temperature"], vendor_code=tp_code)
        payload = _a7_import_payload(ctx, xml_str, p["third_party_code"])
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary = {"room_no": p["room_no"], "action_cod": f"#RMTEMP#{p['temperature']}#"}
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        retn = rows[0].get("RETN-CODE") if rows else None
        summary.update({"procStatus": item.get("procStatus"), "retn_code": retn,
                        "retn_desc": rows[0].get("RETN-CODE-DESC") if rows else None})
        ok = (res.status_code == 200 and item.get("procStatus") is True and retn == "0000"
              and "1112 Set" in (summary["retn_desc"] or ""))
        # LOCAL 閉環:室溫已落庫
        if ok and not ctx.use_real:
            res_rb, _ = execute_for_ctx(ctx, "GET", ctx.urls["roomcontrol_internal"])
            if res_rb is not None and res_rb.status_code == 200:
                state = (res_rb.json() or {}).get("room_control_state") or {}
                summary["state_readback_temperature"] = (state.get(p["room_no"]) or {}).get("temperature")
                ok = summary["state_readback_temperature"] == p["temperature"]
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    def _keybox_push(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_keybox"
        scenario = registry.get(case_id)
        p = _p(ctx, case_id)
        xml_str = build_keybox_push(p["room_no"], p["card_typ"], p["card_uid"], p["indoor_name"],
                                    p["action_sta"], vendor_code=tp_code)
        payload = _a7_import_payload(ctx, xml_str, p["third_party_code"])
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary = {"room_no": p["room_no"], "reve": f"0300{tp_code}4390",
                   "card_typ": p["card_typ"], "card_uid": p["card_uid"], "action_sta": p["action_sta"]}
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        retn = rows[0].get("RETN-CODE") if rows else None
        summary.update({"procStatus": item.get("procStatus"), "retn_code": retn,
                        "resp_has_action_cod": "ACTION_COD" in (rows[0] if rows else {})})
        # B5 回應契約:無 ACTION_COD 欄位(sa10 B5 回應樣本)
        ok = (res.status_code == 200 and item.get("procStatus") is True and retn == "0000"
              and summary["resp_has_action_cod"] is False)
        # LOCAL 閉環:位元 2(Keybox 1=插卡 0=拔卡)+ 卡片資訊已落庫
        if ok and not ctx.use_real:
            res_rb, _ = execute_for_ctx(ctx, "GET", ctx.urls["roomcontrol_internal"])
            if res_rb is not None and res_rb.status_code == 200:
                state = (res_rb.json() or {}).get("room_control_state") or {}
                st = state.get(p["room_no"]) or {}
                bits = st.get("status_bits") or ""
                summary["state_readback_bit2"] = bits[1] if len(bits) == 16 else None
                summary["state_readback_keybox"] = st.get("keybox")
                ok = (summary["state_readback_bit2"] == str(p["action_sta"])
                      and (st.get("keybox") or {}).get("card_uid") == p["card_uid"])
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    # ---- RC2 負面路徑(固定劇本,不宣告 params;參數化設計「不開放」原則) ----

    def _bad_xml(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_bad_xml"
        scenario = registry.get(case_id)
        payload = _a7_import_payload(ctx, "<ROWSET><ROW>不是完整XML", tp_code)
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        if err:
            return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload={"__error__": err})
        return _expect_417(case_id, scenario, dur, payload, res, "417")

    def _unknown_action(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_unknown_action"
        scenario = registry.get(case_id)
        xml_str = build_rowset_xml({
            "REVE-CODE": reve_room_sta(tp_code), "ROOM_NOS": "2403",
            "ACTION_COD": "NOSUCH", "ACTION_STA": "1", "ACTION_DAT": action_dat_now(),
        })
        payload = _a7_import_payload(ctx, xml_str, tp_code)
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary = {"action_cod": "NOSUCH"}
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        retn = rows[0].get("RETN-CODE") if rows else None
        summary.update({"procStatus": item.get("procStatus"), "retn_code": retn,
                        "retn_desc": rows[0].get("RETN-CODE-DESC") if rows else None})
        # mock 契約:未知 ACTION_COD → procStatus=false + RETN-CODE 9999(反向斷言)
        ok = res.status_code == 200 and item.get("procStatus") is False and retn == "9999"
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    def _missing_room_nos(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_missing_room_nos"
        scenario = registry.get(case_id)
        xml_str = build_rowset_xml({
            "REVE-CODE": reve_room_inf(tp_code), "ACTION_COD": "ROOM_INF",
            "ACTION_DAT": action_dat_now(),
        })
        payload = _a7_import_payload(ctx, xml_str, tp_code, file_name="C002.xml")
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        if err:
            return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload={"__error__": err})
        return _expect_417(case_id, scenario, dur, payload, res, "417")

    bits_hint = ("16 位:1Keyhouse 2Keybox 3冷氣 4總電源 5鐵捲門 6一氧化碳 7防盜 "
                 "8緊急 9清潔(1請掃/2掃中/3待巡/4巡中/0完成) 10勿擾 11房門 12-16保留")
    registry.register(
        f"rc_{slug}_room_sta_push", module="roomcontrol", vendor=vendor_id,
        name="房況推送(B4・ROOM_STA)", endpoint="/third-party/import-sync-files",
        runner=_room_sta_push,
        params=[
            ParamSpec("room_no", "房號", "str", "2403"),
            ParamSpec("status_bits", "房況位元串", "str", DEFAULT_STATUS_BITS, hint=bits_hint),
            ParamSpec("third_party_code", "廠商代碼", "str", tp_code,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_label}={tp_code}(他環境不同時可覆寫)"),
        ],
    )
    registry.register(
        f"rc_{slug}_room_inf", module="roomcontrol", vendor=vendor_id,
        name="房況查詢(A6・ROOM_INF)", endpoint="/third-party/import-sync-files",
        runner=_room_inf_query,
        params=[
            ParamSpec("room_no", "房號", "str", "2403", hint="查無住客的房號會回 ROOM_STA=V(空房)單列"),
            ParamSpec("third_party_code", "廠商代碼", "str", tp_code,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_label}={tp_code}"),
        ],
    )
    registry.register(
        f"rc_{slug}_return", module="roomcontrol", vendor=vendor_id,
        name="全房況查詢(A10・RETURN)", endpoint="/third-party/import-sync-files",
        runner=_return_all,
        params=[
            ParamSpec("third_party_code", "廠商代碼", "str", tp_code,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_label}={tp_code}"),
        ],
    )
    # ---- RC2(2026-09-04):B4 同族 + B5 KeyBox + 負面路徑 ----
    registry.register(
        f"rc_{slug}_clean", module="roomcontrol", vendor=vendor_id,
        name="清潔狀態推送(B4・CLEAN)", endpoint="/third-party/import-sync-files",
        runner=_clean_push,
        params=[
            ParamSpec("room_no", "房號", "str", "2403"),
            ParamSpec("clean_state", "清潔狀態", "str", "1",
                      hint="sa10 位元9:1請打掃/2打掃中/3待巡房/4巡房中/0清潔完成(德安收0設乾淨房,餘皆髒房)"),
            ParamSpec("third_party_code", "廠商代碼", "str", tp_code,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_label}={tp_code}"),
        ],
    )
    registry.register(
        f"rc_{slug}_rmtemp", module="roomcontrol", vendor=vendor_id,
        name="室溫推送(B4・RMTEMP)", endpoint="/third-party/import-sync-files",
        runner=_rmtemp_push,
        params=[
            ParamSpec("room_no", "房號", "str", "2403"),
            ParamSpec("temperature", "室溫值", "str", "26C",
                      hint="sa10:#RMTEMP#<值>#;最多十個字由廠商決定內容(A7 前台顯示)"),
            ParamSpec("third_party_code", "廠商代碼", "str", tp_code,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_label}={tp_code}"),
        ],
    )
    registry.register(
        f"rc_{slug}_keybox", module="roomcontrol", vendor=vendor_id,
        name="插拔卡現況推送(B5・KeyBox)", endpoint="/third-party/import-sync-files",
        runner=_keybox_push,
        params=[
            ParamSpec("room_no", "房號", "str", "2403"),
            ParamSpec("card_typ", "卡片類別", "str", "SERVICE", hint="sa10 B5:GUEST房客 / SERVICE房務人員"),
            ParamSpec("card_uid", "卡片UID", "str", "1234567890"),
            ParamSpec("indoor_name", "持卡人姓名", "str", "王小美"),
            ParamSpec("action_sta", "插/拔卡", "str", "1", hint="sa10 B5:1插卡 / 0拔卡(更新位元2 Keybox)"),
            ParamSpec("third_party_code", "廠商代碼", "str", tp_code,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_label}={tp_code}"),
        ],
    )
    registry.register(
        f"rc_{slug}_bad_xml", module="roomcontrol", vendor=vendor_id,
        name="無效XML(417)", endpoint="/third-party/import-sync-files",
        runner=_bad_xml,
    )
    registry.register(
        f"rc_{slug}_unknown_action", module="roomcontrol", vendor=vendor_id,
        name="無效動作代碼(RETN・9999)", endpoint="/third-party/import-sync-files",
        runner=_unknown_action,
    )
    registry.register(
        f"rc_{slug}_missing_room_nos", module="roomcontrol", vendor=vendor_id,
        name="缺房號欄位(417)", endpoint="/third-party/import-sync-files",
        runner=_missing_room_nos,
    )


for _vid, _vlabel, _tp in _RC_VENDORS:
    _register_rc_vendor_cases(_vid, _vlabel, _tp)
