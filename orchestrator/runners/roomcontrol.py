# orchestrator/runners/roomcontrol.py
"""🌡️ 房控模組案例(roomcontrol / A7 公版 XML 介面)— 對齊 sa_docs/sa10 V1.2。"""
from ..registry import registry
from ..models import CaseResult, RunContext, ParamSpec, CASE_SKIP
from hardware.simulate_speaker import execute_for_ctx
from server.roomcontrol.vendors.vendor_A7_XML import (
    build_room_sta_push, build_room_inf_query, build_return_query,
    build_clean_push, build_rmtemp_push, build_keybox_push,
    build_rowset_xml, action_dat_now, reve_room_sta, reve_room_inf,
    parse_rowset_xml, DEFAULT_STATUS_BITS,
)
from server.roomcontrol.vendors import vendor_MINXON, vendor_CHAOFENG, vendor_IPTV

from .helpers import _p, _ok, _fail, _expect_417

# ====================================================================
# 🌡️ 房控(roomcontrol / A7 公版 XML 介面)— 對齊 sa_docs/sa10 V1.2
# 方向:廠商→PMS(沙盒發砲端=模擬房控廠商;mock PMS 側在 server/roomcontrol/)。
# 2026-09-03 起掛雙廠商:MINXON 民笙(thirdParty=81)、CHAOFENG 超烽(thirdParty=86)。
# RC2.5(2026-11-03,sa11 = A7 收到廠商 XML 的 SQL 處理文件)每家 +3 案:
# 房況斷線推送(位8=F 三連動閉環)、不存在房號(RETN 9999)、內部錯誤模擬房(RETN 1001)。
# RC4a(2026-11-04,廠商代號 70 確認=雲朗IPTV):sa11 THIRDPARTY_DT_CONF 住客顯示名稱
# 參數(guest_display_name/user_defined_display_name)→ CKI 出站姓名欄解析,+1 廠商 3 案。
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
    bad_xml/unknown_action/missing_room_nos(負面,固定劇本不宣告 params);
    RC2.5(2026-11-03)三案:room_sta_offline(F 斷線閉環)、room_not_found/internal_error(負面)。
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
                st = state.get(p["room_no"]) or {}
                summary["state_readback_bits"] = st.get("status_bits")
                # RC2.5:PBX_DT 欄位級解碼——位8 非 F → RCU_ONLINE=Y、F → N(sa11 三連動之一)
                bits = p["status_bits"]
                rcu_expected = "N" if len(bits) == 16 and bits[7] == "F" else "Y"
                summary["state_readback_rcu_online"] = (st.get("pbx_dt") or {}).get("RCU_ONLINE")
                ok = (summary["state_readback_bits"] == bits
                      and summary["state_readback_rcu_online"] == rcu_expected)
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
        # RC2.5(sa11):Set 類 DESC =「{房號} Set {ACTION_COD}」
        ok = (res.status_code == 200 and item.get("procStatus") is True and retn == "0000"
              and f"{p['room_no']} Set" in (summary["retn_desc"] or ""))
        # LOCAL 閉環:室溫已落庫 + api='RCU' 標記(sa11)
        if ok and not ctx.use_real:
            res_rb, _ = execute_for_ctx(ctx, "GET", ctx.urls["roomcontrol_internal"])
            if res_rb is not None and res_rb.status_code == 200:
                state = (res_rb.json() or {}).get("room_control_state") or {}
                st = state.get(p["room_no"]) or {}
                summary["state_readback_temperature"] = st.get("temperature")
                summary["state_readback_api"] = st.get("api")
                ok = (summary["state_readback_temperature"] == p["temperature"]
                      and summary["state_readback_api"] == "RCU")
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

    # ---- RC2.5(2026-11-03,sa11):房間層負面 + F 斷線閉環 ----

    def _room_not_found(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_room_not_found"
        scenario = registry.get(case_id)
        xml_str = build_room_inf_query("9999", vendor_code=tp_code)   # 未登錄房間主檔的房號
        payload = _a7_import_payload(ctx, xml_str, tp_code, file_name="C002.xml")
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary = {"room_no": "9999", "action_cod": "ROOM_INF"}
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        retn = rows[0].get("RETN-CODE") if rows else None
        summary.update({"procStatus": item.get("procStatus"), "retn_code": retn,
                        "retn_desc": rows[0].get("RETN-CODE-DESC") if rows else None})
        # sa11 契約:不存在房號 → procStatus=false + RETN 9999「ROOM not found.」(反向斷言)
        ok = (res.status_code == 200 and item.get("procStatus") is False
              and retn == "9999" and "ROOM not found" in (summary["retn_desc"] or ""))
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    def _internal_error(ctx: RunContext) -> CaseResult:
        import time as _t
        case_id = f"rc_{slug}_internal_error"
        scenario = registry.get(case_id)
        xml_str = build_room_inf_query("9901", vendor_code=tp_code)   # 沙盒模擬內部錯誤房(E)
        payload = _a7_import_payload(ctx, xml_str, tp_code, file_name="C002.xml")
        t0 = _t.perf_counter()
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        dur = int((_t.perf_counter() - t0) * 1000)
        summary = {"room_no": "9901", "action_cod": "ROOM_INF"}
        if err or res is None:
            return _fail(case_id, "", scenario, dur, request_payload=payload,
                         response_payload={"__error__": err or "no response"})
        item, rows = _a7_first_response_item(res)
        retn = rows[0].get("RETN-CODE") if rows else None
        summary.update({"procStatus": item.get("procStatus"), "retn_code": retn,
                        "retn_desc": rows[0].get("RETN-CODE-DESC") if rows else None})
        # sa11 契約:德安 DB 內部錯誤 → procStatus=false + RETN 1001(反向斷言)
        ok = (res.status_code == 200 and item.get("procStatus") is False and retn == "1001")
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload, response_payload=summary)

    def _room_sta_offline(ctx: RunContext) -> CaseResult:
        """F 斷線三連動閉環(sa11 情境二):連線態推送(位9=2)→ F 斷線推送(位8=F)→
        回讀 RCU_ONLINE=N、SOS=off、CLEAN_ROOM 保舊值 2(斷線略過位 9 更新)。"""
        import time as _t
        case_id = f"rc_{slug}_room_sta_offline"
        scenario = registry.get(case_id)
        p = _p(ctx, case_id)
        t0 = _t.perf_counter()
        summary = {"room_no": p["room_no"], "bits_online": "0101001120100000",
                   "bits_offline": p["status_bits"]}
        payload = _a7_import_payload(
            ctx, build_room_sta_push(p["room_no"], "0101001120100000", vendor_code=tp_code),
            p["third_party_code"])
        res, err = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload)
        if err or res is None:
            return _fail(case_id, "", scenario, int((_t.perf_counter() - t0) * 1000),
                         request_payload=payload, response_payload={"__error__": err or "no response"})
        payload2 = _a7_import_payload(
            ctx, build_room_sta_push(p["room_no"], p["status_bits"], vendor_code=tp_code),
            p["third_party_code"])
        res2, err2 = execute_for_ctx(ctx, "POST", ctx.urls["import_sync"], json_body=payload2)
        dur = int((_t.perf_counter() - t0) * 1000)
        item2, rows2 = _a7_first_response_item(res2) if res2 is not None else ({}, [])
        retn2 = rows2[0].get("RETN-CODE") if rows2 else None
        summary.update({"procStatus": item2.get("procStatus"), "retn_code": retn2,
                        "retn_desc": rows2[0].get("RETN-CODE-DESC") if rows2 else None})
        ok = (res2 is not None and res2.status_code == 200
              and item2.get("procStatus") is True and retn2 == "0000")
        # LOCAL 閉環:F 三連動回讀(RCU_ONLINE=N / SOS=off / CLEAN_ROOM 保舊值)
        if ok and not ctx.use_real:
            res_rb, _ = execute_for_ctx(ctx, "GET", ctx.urls["roomcontrol_internal"])
            if res_rb is not None and res_rb.status_code == 200:
                state = (res_rb.json() or {}).get("room_control_state") or {}
                pbx = (state.get(p["room_no"]) or {}).get("pbx_dt") or {}
                summary["state_readback_pbx_dt"] = pbx
                ok = (pbx.get("RCU_ONLINE") == "N" and pbx.get("SOS") == "off"
                      and pbx.get("CLEAN_ROOM") == "2")
        if ok:
            return _ok(case_id, "", scenario, dur, request_payload=payload2, response_payload=summary)
        return _fail(case_id, "", scenario, dur, request_payload=payload2, response_payload=summary)

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
            ParamSpec("room_no", "房號", "str", "2403",
                      hint="需已登錄房間主檔:O 回每住客一列;V/R/S 回全空欄單列;未登錄 → RETN 9999"),
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
    # ---- RC2.5(2026-11-03,sa11) ----
    registry.register(
        f"rc_{slug}_room_not_found", module="roomcontrol", vendor=vendor_id,
        name="不存在房號(RETN・9999)", endpoint="/third-party/import-sync-files",
        runner=_room_not_found,
    )
    registry.register(
        f"rc_{slug}_internal_error", module="roomcontrol", vendor=vendor_id,
        name="內部錯誤模擬房(RETN・1001)", endpoint="/third-party/import-sync-files",
        runner=_internal_error,
    )
    registry.register(
        f"rc_{slug}_room_sta_offline", module="roomcontrol", vendor=vendor_id,
        name="房況斷線推送(B4・位8=F)", endpoint="/third-party/import-sync-files",
        runner=_room_sta_offline,
        params=[
            ParamSpec("room_no", "房號", "str", "2403",
                      hint="需已登錄於沙盒房間主檔(未登錄 → RETN 9999)"),
            ParamSpec("status_bits", "斷線位元串", "str", "0101001F40100000",
                      hint="位8=F 房間OFF_LINE:落庫後 SOS=off、RCU_ONLINE=N、位9清潔保舊值不更新"),
            ParamSpec("third_party_code", "廠商代碼", "str", tp_code,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_label}={tp_code}"),
        ],
    )


for _vid, _vlabel, _tp in _RC_VENDORS:
    _register_rc_vendor_cases(_vid, _vlabel, _tp)


# ====================================================================
# 🌡️ RC4a:IPTV 雲朗(70)— sa11 THIRDPARTY_DT_CONF 住客顯示名稱參數(2026-11-04)
# 方向:PMS→廠商(CKI 出站 XML 的 ALT_NAM 姓名欄依參數解析;沙盒以 internal/cki 觸發)。
# 案例屬 LOCAL_ONLY:CKI 由 A7 端 C/I 動作觸發,REAL 雲端無法由沙盒端模擬 → SKIP。
# ====================================================================
_IPTV_TP = vendor_IPTV.THIRD_PARTY_CODE
# 種子房 2407(預訂未入住)的期望值——runner 顯式持有,即參數表語意的可讀規格
_IPTV_SEED_2407 = {"ALT_NAM": "王小明", "LAST_NAM": "王", "FIRST_NAM": "小明",
                   "GROUP_NOS": "GP2026A"}
_DISPLAY_NAME_CHOICES = ("GROUP_NOS", "ROOM_NOS", "LAST_NAM", "FIRST_NAM",
                         "ALT_NAM", "USER_DEFINED")


def _iptv_expected_display(room_no, choice, custom):
    choice = choice or "ALT_NAM"                    # None = 無參數設定 → 預設 ALT_NAM
    if choice == "USER_DEFINED":
        return str(custom or "")                    # sa11:不論有無值皆如實傳送
    if choice == "ROOM_NOS":
        return str(room_no)
    return _IPTV_SEED_2407[choice]


def _iptv_skip(case_id, scenario):
    return CaseResult(case_id=case_id, run_id="", module=scenario.module,
                      vendor=scenario.vendor, scenario_name=scenario.name,
                      endpoint=scenario.endpoint, status=CASE_SKIP,
                      response_payload={"note": "LOCAL_ONLY:CKI 由 A7 端 C/I 觸發,"
                                                "REAL 雲端無法由沙盒端模擬出站推送"})


def _iptv_set_conf(ctx, tp, params):
    """設定/清除 THIRDPARTY_DT_CONF(值 None=清除 → 無參數設定)。"""
    return execute_for_ctx(ctx, "POST", ctx.urls["roomcontrol_conf"],
                           json_body={"third_party_code": tp, "params": params})


def _iptv_trigger_cki(ctx, room_no, tp):
    return execute_for_ctx(ctx, "POST", ctx.urls["roomcontrol_cki"],
                           json_body={"room_no": room_no, "third_party_code": tp})


def _iptv_run_case(ctx, case_id, tp, room_no, choice, custom):
    """共用流程:設參數 → 觸發 CKI → 斷言出站 XML 姓名欄 = 期望解析值。"""
    import time as _t
    scenario = registry.get(case_id)
    t0 = _t.perf_counter()
    if ctx.use_real:
        return _iptv_skip(case_id, scenario)
    conf_params = {"guest_display_name": choice}
    if custom is not None:
        conf_params["user_defined_display_name"] = custom
    _iptv_set_conf(ctx, tp, conf_params)
    res, err = _iptv_trigger_cki(ctx, room_no, tp)
    dur = int((_t.perf_counter() - t0) * 1000)
    summary = {"room_no": room_no, "guest_display_name": choice,
               "user_defined_display_name": custom}
    if err or res is None:
        return _fail(case_id, "", scenario, dur,
                     response_payload={"__error__": err or "no response", **summary})
    body = res.json() if res.status_code == 200 else {}
    rows = parse_rowset_xml(body.get("responseBody", "")) if body else []
    expected = _iptv_expected_display(room_no, choice, custom)
    summary.update({"procStatus": body.get("procStatus"),
                    "reve_code": rows[0].get("REVE-CODE") if rows else None,
                    "display_name": body.get("display_name"),
                    "expected_display_name": expected,
                    "room_sta": body.get("room_sta")})
    ok = (res.status_code == 200 and body.get("procStatus") is True
          and body.get("display_name") == expected
          and rows and rows[0].get("ALT_NAM") == expected
          and rows[0].get("REVE-CODE") == f"03009010{tp}")
    if ok:
        return _ok(case_id, "", scenario, dur, response_payload=summary)
    return _fail(case_id, "", scenario, dur, response_payload=summary)


def _register_rc_iptv_cases():
    vid, tp = vendor_IPTV.VENDOR_ID, vendor_IPTV.THIRD_PARTY_CODE

    def _display_name(ctx: RunContext) -> CaseResult:
        p = _p(ctx, "rc_iptv_display_name")
        return _iptv_run_case(ctx, "rc_iptv_display_name", p["third_party_code"],
                              p["room_no"], p["guest_display_name"],
                              p.get("user_defined_display_name"))

    def _display_name_default(ctx: RunContext) -> CaseResult:
        # 無參數設定(先清除)→ 預設值 ALT_NAM(sa11 參數表)
        _ = _iptv_set_conf(ctx, tp, {"guest_display_name": None,
                                     "user_defined_display_name": None})
        return _iptv_run_case(ctx, "rc_iptv_display_name_default", tp, "2407", None, None)

    def _display_name_empty_custom(ctx: RunContext) -> CaseResult:
        # USER_DEFINED + 自訂名稱空值 → 傳送廠商內容即無資料(sa11 明文)
        return _iptv_run_case(ctx, "rc_iptv_display_name_empty_custom", tp, "2407",
                              "USER_DEFINED", "")

    registry.register(
        "rc_iptv_display_name", module="roomcontrol", vendor=vid,
        name="住客顯示名稱選項(CKI出站・sa11參數)", endpoint="/roomcontrol/internal/cki",
        runner=_display_name,
        params=[
            ParamSpec("room_no", "房號", "str", "2407",
                      hint="種子 2407=預訂未入住(含訂房/團體資料);未登錄 → 9999"),
            ParamSpec("guest_display_name", "住客顯示名稱", "str", "ALT_NAM",
                      choices=_DISPLAY_NAME_CHOICES,
                      hint="sa11:GROUP_NOS訂房名稱團號/ROOM_NOS房號/LAST_NAM姓/"
                           "FIRST_NAM名/ALT_NAM姓名/USER_DEFINED自訂;"
                           "無參數設定或非合法值 → 預設 ALT_NAM"),
            ParamSpec("user_defined_display_name", "自訂名稱", "str", "",
                      required=False,
                      hint="僅 guest_display_name=USER_DEFINED 時作用;"
                           "不論有無值皆如實傳送(空值 → 廠商收無資料)"),
            ParamSpec("third_party_code", "廠商代碼", "str", tp,
                      hint=f"A7 公版 thirdParty 代碼;{vendor_IPTV.VENDOR_LABEL}={tp}"),
        ],
    )
    registry.register(
        "rc_iptv_display_name_default", module="roomcontrol", vendor=vid,
        name="無參數→預設ALT_NAM(CKI出站)", endpoint="/roomcontrol/internal/cki",
        runner=_display_name_default,
    )
    registry.register(
        "rc_iptv_display_name_empty_custom", module="roomcontrol", vendor=vid,
        name="自訂名稱空值→送無資料(CKI出站)", endpoint="/roomcontrol/internal/cki",
        runner=_display_name_empty_custom,
    )


_register_rc_iptv_cases()
