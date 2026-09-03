# tests_localFullStackClose/test_real_roomcontrol_qa.py
"""🌡️ 房控 A7 公版 XML 介面 — REAL_QA 廠商查詢腳本(廠商發送查詢給 PMS)。

慣例比照 test_real_scenario.py:僅在 ENV_SWITCH=REAL_QA 時執行(CI 請設 LOCAL_OFFLINE)。
2026-09-03 起預設環境即 REAL_QA(後續測試資料以 QA 環境為主)。

廠商(2026-09-03 使用者提供):
- MINXON 民笙,thirdParty=81(REVE 前綴 030081)
- CHAOFENG 超烽,thirdParty=86(REVE 前綴 030086)

每家廠商各發兩類「唯讀查詢」:
- A6 ROOM_INF:查某房現況住客資訊(回多筆住客 ROW;查無 → V 空房列)
- A10 RETURN:要求回傳全部房況(每房一 ROW:ROOM_STA O/V/R/S + CLEAN_STA D/C/S)

2026-09-03 實測背景:QA 收件成功(HTTP 200 + Athena 信封 {code:2000,data:[...]})且不驗
thirdParty 代碼;TT 佔位時 responseBody=null。本檔以正式代碼 81/86 重驗——若 responseBody
開始回實料,斷言自動升級為 RETN-CODE 0000 檢查;仍 null 則記錄現況待 SA(Q5)。
ROOM_STA 推送(會改 PMS 房控狀態)不在此自動測試——經主控台 REAL_QA 手動執行。

可調環境變數:A7_ROOM_NO(ROOM_INF 查詢房號,預設 101,QA 歷史種子房)。
"""
import os
import sys
from datetime import datetime

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from server.roomcontrol.vendors.vendor_A7_XML import (
    build_room_inf_query, build_return_query,
)
from server.roomcontrol.vendors import vendor_MINXON, vendor_CHAOFENG

_QA_ONLY = pytest.mark.skipif(
    config.ENV_SWITCH != "REAL_QA",
    reason="僅在 ENV_SWITCH=REAL_QA 時執行。",
)

QA_IMPORT_URL = f"{config.ENV_MATRIX['REAL_QA']['PMS_URL']}/third-party/import-sync-files"
A7_ROOM_NO = os.environ.get("A7_ROOM_NO", "101")

VENDORS = [
    (vendor_MINXON.VENDOR_ID, vendor_MINXON.VENDOR_LABEL, vendor_MINXON.THIRD_PARTY_CODE),
    (vendor_CHAOFENG.VENDOR_ID, vendor_CHAOFENG.VENDOR_LABEL, vendor_CHAOFENG.THIRD_PARTY_CODE),
]


def _post_qa(xml_str, third_party, file_name):
    cfg = config.ENV_MATRIX["REAL_QA"]
    body = {"athenaId": cfg["ATHENA_ID"], "hotelCode": cfg["HOTEL_COD"],
            "thirdPartyCode": third_party,
            "requestDataList": [{"requestBody": xml_str, "fileName": file_name}]}
    # 💡 8/21 實測:QA 免 Authorization,僅身分 Header;POST body 內另帶 athena/hotel/thirdParty 三元組
    return requests.post(
        QA_IMPORT_URL, json=body, timeout=15,
        headers={"bacchus-athenaid": cfg["ATHENA_ID"], "bacchus-hotelcod": cfg["HOTEL_COD"],
                 "accept": "application/json", "Content-Type": "application/json"},
    )


def _assert_query_response(res, action_label):
    """共用斷言:端點存在(非 404/405)、Athena 信封可解析、procStatus=true;有實料則驗 RETN 0000。

    2026-09-03 實測:CHAOFENG 的 data[] 可能混 [全 null 失敗殼, 成功實料] → 掃描挑成功項;
    ROOM_INF 以正式代碼(81/86)已回 XML 實料(房 101 → ROOM_STA=V、RETN-CODE 0000)。
    """
    print(f"\n[{action_label}] HTTP {res.status_code}")
    print(f"[{action_label}] body: {res.text[:600]}")
    assert res.status_code not in (404, 405), "REST 端點不存在——Q5 需與 SA 確認 REAL 端點"
    payload = res.json() if res.headers.get("content-type", "").startswith("application/json") else None
    assert payload is not None, f"回應非 JSON:{res.headers.get('content-type')}"
    items = payload.get("data") if isinstance(payload, dict) else payload
    assert isinstance(items, list) and items, f"信封內無 data 陣列:{str(payload)[:200]}"
    ok_item = next((it for it in items if isinstance(it, dict)
                    and (it.get("procStatus") is True or it.get("responseBody"))), None)
    assert ok_item is not None, "data[] 內無成功項(procStatus=false 且無 responseBody)——見上方完整回應"
    rb = ok_item.get("responseBody")
    if rb:
        assert "<RETN-CODE>0000</RETN-CODE>" in rb, f"回應 XML 非 0000:{rb[:300]}"
    return rb


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
def test_qa_room_inf_query(vid, vlabel, code):
    """A6 ROOM_INF(唯讀):{vlabel} 以正式代碼查 QA 某房現況住客。"""
    res = _post_qa(build_room_inf_query(A7_ROOM_NO, vendor_code=code), code, "C001.xml")
    rb = _assert_query_response(res, f"QA ROOM_INF {vlabel}({code}) 房{A7_ROOM_NO}")
    if rb:
        assert "<ROOM_NOS>" in rb      # 有實料:至少帶房號欄位


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
@pytest.mark.xfail(reason="QA 2026-09-03 實測:RETURN(A10)經 import-sync-files 回 procStatus=false + 全 null——"
                          "支援方式待 SA 確認(Q5);修復後本測試轉 XPASS 即可移除標記",
                   strict=False)
def test_qa_return_all_rooms(vid, vlabel, code):
    """A10 RETURN(唯讀):{vlabel} 以正式代碼要求 QA 回傳全部房況。"""
    res = _post_qa(build_return_query(vendor_code=code), code, "C002.xml")
    rb = _assert_query_response(res, f"QA RETURN {vlabel}({code})")
    if rb:
        assert "<ROOM_STA>" in rb      # 有實料:至少帶房況欄位
