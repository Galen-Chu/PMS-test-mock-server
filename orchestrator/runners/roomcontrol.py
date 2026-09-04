# orchestrator/runners/roomcontrol.py
"""🌡️ 房控模組案例(roomcontrol / A7 公版 XML 介面)— 對齊 sa_docs/sa10 V1.2。"""
from ..registry import registry
from ..models import CaseResult, RunContext, ParamSpec
from hardware.simulate_speaker import execute_for_ctx
from server.roomcontrol.vendors.vendor_A7_XML import (
    build_room_sta_push, build_room_inf_query, build_return_query, parse_rowset_xml,
    DEFAULT_STATUS_BITS,
)
from server.roomcontrol.vendors import vendor_MINXON, vendor_CHAOFENG

from .helpers import _p, _ok, _fail

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
    """以閉包工廠為一家 A7 公版房控廠商註冊三案(push / room_inf / return)。

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


for _vid, _vlabel, _tp in _RC_VENDORS:
    _register_rc_vendor_cases(_vid, _vlabel, _tp)
