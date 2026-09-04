# tests_localFullStackClose/test_local_roomcontrol.py
"""🌡️ 房控模組 Mock Server 閉環測試(需本地 Flask 沙盒在線:python main.py)。

與 test_local_api.py 同類(打 127.0.0.1:5000);離線單元版見 test_roomcontrol.py。

閉環鏈:廠商(編排端)──ROOM_STA 推送──► Mock PMS(落庫)──內部回讀──► 驗位元串一致
                └──ROOM_INF 查詢──► Mock PMS ──住客列(ROOM_STA O/S/V)──► 斷言 sa10 A6 合約
"""
import os
import sys
import time
from datetime import datetime

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:5000"
IMPORT_URL = f"{BASE}/third-party/import-sync-files"
STATE_URL = f"{BASE}/roomcontrol/internal/state"


def _import_body(xml_str, third="TT", fname="C001.xml", athena="16", hotel="01"):
    return {"athenaId": athena, "hotelCode": hotel, "thirdPartyCode": third,
            "requestDataList": [{"requestBody": xml_str, "fileName": fname}]}


def _room_sta_xml(room, bits):
    return (
        '<?xml version="1.0"?>\n<ROWSET>\n<ROW>\n'
        f'<REVE-CODE>0300TT4190 </REVE-CODE>\n<ROOM_NOS>{room}</ROOM_NOS>\n'
        '<INS_CARD_INF></INS_CARD_INF>\n<INS_CARD_NO></INS_CARD_NO>\n'
        f'<ACTION_COD>#ROOM_STA#{bits}#</ACTION_COD>\n<ACTION_STA>1</ACTION_STA>\n'
        f'<ACTION_DAT>{datetime.now().strftime("%Y/%m/%d %H:%M:%S")}</ACTION_DAT>\n'
        '</ROW>\n</ROWSET>'
    )


def _room_inf_xml(room):
    return (
        '<?xml version="1.0"?>\n<ROWSET>\n<ROW>\n'
        f'<REVE-CODE>0300TT1090</REVE-CODE>\n<ACTION_COD>ROOM_INF</ACTION_COD>\n'
        f'<ROOM_NOS>{room}</ROOM_NOS>\n'
        f'<ACTION_DAT>{datetime.now().strftime("%Y/%m/%d %H:%M:%S")}</ACTION_DAT>\n'
        '</ROW>\n</ROWSET>'
    )


@pytest.fixture(scope="module")
def server_up():
    """前置:本地沙盒須在線,否則整檔跳過(與 test_local_api 同策略)。"""
    try:
        r = requests.get(f"{BASE}/scenarios", timeout=3)
        assert r.status_code == 200
    except Exception:
        pytest.skip("本地 Flask 沙盒未啟動(先 python main.py)")
    return True


def test_closed_loop_room_sta_push_and_readback(server_up):
    """閉環①:ROOM_STA 推送 → Mock PMS 落庫 → 內部回讀位元串一致 + "1112 Set" 回應。"""
    room = f"9{datetime.now().strftime('%H%M%S')}"          # 每輪唯一房號,避免狀態殘留干擾
    bits = "010101011001"
    res = requests.post(IMPORT_URL, json=_import_body(_room_sta_xml(room, bits)))
    assert res.status_code == 200
    item = res.json()[0]
    assert item["procStatus"] is True
    assert "<RETN-CODE>0000</RETN-CODE>" in item["responseBody"]
    assert f"1112 Set #ROOM_STA#{bits}#" in item["responseBody"]

    rb = requests.get(STATE_URL).json()["room_control_state"]
    assert rb[room]["status_bits"] == bits                  # 下命令 → 回讀一致(閉環斷言)


def test_closed_loop_room_inf_query_contract(server_up):
    """閉環②:ROOM_INF 查詢 → 一住客一 ROW / ROOM_STA=O / RETN 0000;空房 → V 單列。"""
    res = requests.post(IMPORT_URL, json=_import_body(_room_inf_xml("2403")))
    assert res.status_code == 200
    item = res.json()[0]
    assert item["procStatus"] is True
    body = item["responseBody"]
    assert body.count("<ROW>") == 2                          # 種子房 2403 兩位住客
    assert "<ROOM_STA>O</ROOM_STA>" in body
    assert "<CI_SER>200605120002001</CI_SER>" in body

    body2 = requests.post(IMPORT_URL, json=_import_body(_room_inf_xml("813"))).json()[0]["responseBody"]
    assert body2.count("<ROW>") == 1 and "<ROOM_STA>V</ROOM_STA>" in body2


def test_mock_negative_gates(server_up):
    """負面:壞 XML → 417;缺識別三元組 → 400(mock 契約守護)。"""
    r1 = requests.post(IMPORT_URL, json=_import_body("<ROWSET><ROW>broken"))
    assert r1.status_code == 417
    r2 = requests.post(IMPORT_URL, json={"requestDataList": [{"requestBody": "<a/>"}]})
    assert r2.status_code == 400


def test_orchestrator_closed_loop_via_runs_api(server_up):
    """閉環③(編排端視角):/runs 帶覆寫跑雙廠商三案——推送落庫回讀 + 查詢合約 + 全房況,全 PASS。"""
    room = f"8{datetime.now().strftime('%H%M%S')}"
    bits = "1000001100100000"
    payload = {
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["rc_minxon_room_sta_push", "rc_minxon_room_inf", "rc_chaofeng_return"],
        "overrides": {
            "rc_minxon_room_sta_push": {"room_no": room, "status_bits": bits},
            "rc_minxon_room_inf": {"room_no": "2403"},
        },
    }
    run = requests.post(f"{BASE}/runs", json=payload).json()
    assert run.get("run_id"), run
    for _ in range(60):
        snap = requests.get(f"{BASE}/runs/{run['run_id']}").json()
        if snap["status"] != "RUNNING":
            break
        time.sleep(0.3)
    results = {c["case_id"]: c for c in requests.get(f"{BASE}/runs/{run['run_id']}/results").json()}
    push = results["rc_minxon_room_sta_push"]
    query = results["rc_minxon_room_inf"]
    ret = results["rc_chaofeng_return"]
    assert push["status"] == "PASS"
    assert push["resolved_params"]["status_bits"] == bits
    assert push["response_payload"]["state_readback_bits"] == bits     # 編排端閉環回讀
    assert query["status"] == "PASS" and query["response_payload"]["row_count"] == 2
    assert ret["status"] == "PASS" and ret["response_payload"]["row_count"] >= 1
    # RETURN 應含本輪推送的房(位元串第 9 位=0 → CLEAN_STA=C)
    ret_rooms = {r["ROOM_NOS"]: r for r in ret["response_payload"]["rows"]}
    assert ret_rooms[room]["ROOM_STA"] == "V" and ret_rooms[room]["CLEAN_STA"] == "C"


def _run_and_results(payload):
    run = requests.post(f"{BASE}/runs", json=payload).json()
    assert run.get("run_id"), run
    for _ in range(60):
        snap = requests.get(f"{BASE}/runs/{run['run_id']}").json()
        if snap["status"] != "RUNNING":
            break
        time.sleep(0.3)
    results = requests.get(f"{BASE}/runs/{run['run_id']}/results").json()
    return {c["case_id"]: c for c in results}


def test_orchestrator_closed_loop_rc2_same_family(server_up):
    """閉環④(RC2):CLEAN→位元9 / RMTEMP→室溫 / KeyBox→位元2+卡片資訊,經 /runs 全 PASS。"""
    room = f"7{datetime.now().strftime('%H%M%S')}"
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["rc_minxon_clean", "rc_chaofeng_rmtemp", "rc_minxon_keybox"],
        "overrides": {
            "rc_minxon_clean": {"room_no": room, "clean_state": "3"},
            "rc_chaofeng_rmtemp": {"room_no": room, "temperature": "27C"},
            "rc_minxon_keybox": {"room_no": room, "card_uid": f"KB{room}", "action_sta": "1"},
        },
    })
    clean, temp, kb = results["rc_minxon_clean"], results["rc_chaofeng_rmtemp"], results["rc_minxon_keybox"]
    assert clean["status"] == "PASS"
    assert clean["response_payload"]["state_readback_bit9"] == "3"
    assert temp["status"] == "PASS"
    assert temp["response_payload"]["state_readback_temperature"] == "27C"
    assert kb["status"] == "PASS"
    assert kb["response_payload"]["state_readback_bit2"] == "1"
    assert kb["response_payload"]["state_readback_keybox"]["card_uid"] == f"KB{room}"


def test_orchestrator_closed_loop_rc2_negatives(server_up):
    """閉環⑤(RC2 負面):壞XML→417 / 未知動作→RETN 9999 / 缺房號→417,經 /runs 全 PASS(反向斷言)。"""
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["rc_minxon_bad_xml", "rc_chaofeng_unknown_action",
                         "rc_chaofeng_missing_room_nos"],
    })
    bad, unknown, missing = (results["rc_minxon_bad_xml"],
                             results["rc_chaofeng_unknown_action"],
                             results["rc_chaofeng_missing_room_nos"])
    assert bad["status"] == "PASS"
    assert unknown["status"] == "PASS"
    assert unknown["response_payload"]["procStatus"] is False
    assert unknown["response_payload"]["retn_code"] == "9999"
    assert missing["status"] == "PASS"
