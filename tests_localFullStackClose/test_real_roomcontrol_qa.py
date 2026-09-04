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
    build_clean_push, build_rmtemp_push, build_keybox_push,
    build_rowset_xml, action_dat_now, reve_room_sta, reve_room_inf,
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


# ====================================================================
# RC2 實測輪(2026-09-04,引擎發砲 12 案後固化;雙廠行為一致)
# QA 實況:
# - CLEAN / #RMTEMP# 推送:200+信封,procStatus=false + RETN 9999 + DESC「ADD item」→ 待 SA(Q5)
# - B5 KeyBox(REVE 4390):data[] 全 null 失敗殼(同 A10 RETURN 形狀)→ Q5
# - 壞 XML / 未知 ACTION_COD:不回 417/9999 XML,一律 200 + 全 null 殼(QA 拒收風格)
# - ROOM_INF 缺 ROOM_NOS:200 + procStatus=false + RETN 9999 + 「Room configuration not found…Room null」
# mock 維持 sa10 契約(417 / 9999 XML);下方 PASS 測試=QA 現況守護,xfail=待 SA 修復項。
# ====================================================================
QA_PUSH_ROOM = os.environ.get("A7_PUSH_ROOM_NO", "9901")   # RC2 推送用隔離房號,避免動 QA 既有房況


def _envelope_items(res, action_label):
    """解 Athena 信封 → data 項 list(共用;非 JSON/非 200 形狀即斷言失敗)。"""
    print(f"\n[{action_label}] HTTP {res.status_code}")
    print(f"[{action_label}] body: {res.text[:600]}")
    assert res.status_code not in (404, 405), "REST 端點不存在——Q5 需與 SA 確認 REAL 端點"
    payload = res.json() if res.headers.get("content-type", "").startswith("application/json") else None
    assert payload is not None, f"回應非 JSON:{res.headers.get('content-type')}"
    items = payload.get("data") if isinstance(payload, dict) else payload
    assert isinstance(items, list) and items, f"信封內無 data 陣列:{str(payload)[:200]}"
    return items


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
@pytest.mark.xfail(reason="QA 2026-09-04 實測:CLEAN 推送回 procStatus=false + RETN 9999「ADD item」(雙廠)——"
                          "支援方式待 SA 確認(Q5);修復後轉 XPASS 即可移除",
                   strict=False)
def test_qa_clean_push(vid, vlabel, code):
    """RC2 B4 CLEAN:{vlabel} 推清掃狀態(ACTION_STA=1 請打掃)至隔離房。"""
    res = _post_qa(build_clean_push(QA_PUSH_ROOM, "1", vendor_code=code), code, "C001.xml")
    rb = _assert_query_response(res, f"QA CLEAN {vlabel}({code}) 房{QA_PUSH_ROOM}")
    assert "<RETN-CODE>0000</RETN-CODE>" in rb


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
@pytest.mark.xfail(reason="QA 2026-09-04 實測:#RMTEMP# 推送回 procStatus=false + RETN 9999「ADD item」(雙廠)——"
                          "支援方式待 SA 確認(Q5);修復後轉 XPASS 即可移除",
                   strict=False)
def test_qa_rmtemp_push(vid, vlabel, code):
    """RC2 B4 RMTEMP:{vlabel} 推室溫 26C 至隔離房。"""
    res = _post_qa(build_rmtemp_push(QA_PUSH_ROOM, "26C", vendor_code=code), code, "C001.xml")
    rb = _assert_query_response(res, f"QA RMTEMP {vlabel}({code}) 房{QA_PUSH_ROOM}")
    assert "<RETN-CODE>0000</RETN-CODE>" in rb


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
@pytest.mark.xfail(reason="QA 2026-09-04 實測:B5 KeyBox(4390)回 data[] 全 null 失敗殼(同 A10 RETURN 形狀)——"
                          "支援方式待 SA 確認(Q5);修復後轉 XPASS 即可移除",
                   strict=False)
def test_qa_keybox_push(vid, vlabel, code):
    """RC2 B5 KeyBox:{vlabel} 推插卡現況(SERVICE 卡)至隔離房。"""
    res = _post_qa(build_keybox_push(QA_PUSH_ROOM, "SERVICE", "1234567890", "王小美", "1",
                                     vendor_code=code), code, "C001.xml")
    rb = _assert_query_response(res, f"QA KEYBOX {vlabel}({code}) 房{QA_PUSH_ROOM}")
    assert "<RETN-CODE>0000</RETN-CODE>" in rb


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
def test_qa_bad_xml_rejected_as_null_shell(vid, vlabel, code):
    """RC2 負面:壞 XML——QA 拒收風格=200 + 信封內 procStatus=false 全 null 殼(非 417;mock 契約差異記錄)。"""
    res = _post_qa("<ROWSET><ROW>不是完整XML", code, "C001.xml")
    items = _envelope_items(res, f"QA bad_xml {vlabel}({code})")
    assert all(isinstance(it, dict) and it.get("procStatus") is False and not it.get("responseBody")
               for it in items), "QA 現況應為全 null 失敗殼;若改回 417/XML 錯誤信封請更新本測試"


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
def test_qa_unknown_action_rejected_as_null_shell(vid, vlabel, code):
    """RC2 負面:未知 ACTION_COD——QA 現況回全 null 殼(非 RETN 9999 XML;mock 契約差異記錄)。"""
    xml = build_rowset_xml({"REVE-CODE": reve_room_sta(code), "ROOM_NOS": QA_PUSH_ROOM,
                            "ACTION_COD": "NOSUCH", "ACTION_STA": "1",
                            "ACTION_DAT": action_dat_now()})
    res = _post_qa(xml, code, "C001.xml")
    items = _envelope_items(res, f"QA unknown_action {vlabel}({code})")
    assert all(isinstance(it, dict) and it.get("procStatus") is False and not it.get("responseBody")
               for it in items), "QA 現況應為全 null 失敗殼;若改回 RETN 9999 XML 請更新本測試"


@_QA_ONLY
@pytest.mark.parametrize("vid,vlabel,code", VENDORS, ids=[v[0] for v in VENDORS])
def test_qa_missing_room_nos_retn9999(vid, vlabel, code):
    """RC2 負面:ROOM_INF 缺 ROOM_NOS——QA 現況:procStatus=false + RETN 9999 + Room null 錯誤訊息。"""
    xml = build_rowset_xml({"REVE-CODE": reve_room_inf(code), "ACTION_COD": "ROOM_INF",
                            "ACTION_DAT": action_dat_now()})
    res = _post_qa(xml, code, "C002.xml")
    items = _envelope_items(res, f"QA missing_room_nos {vlabel}({code})")
    ok_item = next((it for it in items if isinstance(it, dict) and it.get("responseBody")), None)
    assert ok_item is not None, "應回帶 responseBody 的錯誤 XML(Room null)"
    rb = ok_item["responseBody"]
    assert "<RETN-CODE>9999</RETN-CODE>" in rb
    assert "Room" in rb       # QA 錯誤訊息現況:「Room configuration not found … Room null.」
