# tests_localFullStackClose/test_local_pbx.py
"""☎️ 交換機模組本地閉環測試(需本地 Flask 沙盒在線:python main.py)。

與 test_local_roomcontrol.py 同類(打 127.0.0.1:5000);離線單元版見 test_pbx.py。

閉環鏈:德安(編排端,模擬 HOST 寫 HOST2PMS)──指令記錄──► mock 交換機(狀態機落庫)
        ──內部回讀──► 斷言 pbx_dt/mcall_mn 一致(CKI 開電話/CKO 清空+晨呼取消/RMC 搬移)。
"""
import os
import sys
import time
from datetime import datetime, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:5000"
COMMANDS_URL = f"{BASE}/pbx/host-commands"
STATE_URL = f"{BASE}/pbx/internal/state"
RESET_URL = f"{BASE}/pbx/internal/reset"
PMS_RESET_URL = f"{BASE}/pbx/pms/internal/reset"


def test_orchestrator_m1_full_chain_via_runs(server_up):
    """M1 閉環:頁面動作全鏈經 /runs 編排(入住→設定→排程→MCS 下達→雙側回讀)。"""
    requests.post(RESET_URL)
    requests.post(PMS_RESET_URL)
    dat = datetime.now().strftime("%Y%m%d")
    tim = (datetime.now() + timedelta(minutes=40)).strftime("%H%M%S")
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["pbx_ui_set_mcall_full_flow", "pbx_ui_del_mcall_after_trans",
                         "pbx_ui_checkout_cancels_pending", "pbx_ui_room_change_reschedules",
                         "pbx_ui_mcall_expire_skip", "pbx_ui_open_tel_vacant_denied",
                         "pbx_ui_del_past_mcall_denied"],
        "overrides": {
            "pbx_ui_set_mcall_full_flow": {"room_no": "0101", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_del_mcall_after_trans": {"room_no": "0102", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_checkout_cancels_pending": {"room_no": "0103", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_room_change_reschedules": {"room_no": "0104", "new_room_no": "0105",
                                               "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_mcall_expire_skip": {"room_no": "0109"},
            "pbx_ui_open_tel_vacant_denied": {"room_no": "0108"},
            "pbx_ui_del_past_mcall_denied": {"room_no": "0106"},
        },
    })
    for cid, c in results.items():
        assert c["status"] == "PASS", (cid, c.get("response_payload"))
    full = results["pbx_ui_set_mcall_full_flow"]["response_payload"]
    assert full["pms_mcall"]["trans_pbx_sta"] == "TRANS"
    assert full["sw_mcall"]["mcall_sta"] == "0"            # 交換機側已收到 MCS
    rc = results["pbx_ui_room_change_reschedules"]["response_payload"]
    assert rc["mcall_after_change"]["trans_pbx_sta"] == "NOT_TRANS"   # 換房→重送
    assert rc["mcall_after_resend"]["trans_pbx_sta"] == "TRANS"
    skip = results["pbx_ui_mcall_expire_skip"]["response_payload"]
    assert skip["pms_mcall"]["trans_pbx_sta"] == "SKIP"

from server.pbx.vendors.vendor_PABX import (  # noqa: E402
    build_host_record, parse_record, parse_response_fields,
)


def _body(records):
    return {"athenaId": "25", "hotelCode": "01", "records": records}


def _mcall_dat():
    return datetime.now().strftime("%Y%m%d")


def _mcall_tim():
    return (datetime.now() + timedelta(minutes=40)).strftime("%H%M%S")


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


def test_direct_routes_closed_loop(server_up):
    """直打 mock 交換機:CKI → MCS → 回讀落庫;CKO → 清空+晨呼 C。"""
    requests.post(RESET_URL)
    cki = build_host_record("CKI", {"phone_nos": "0106", "lang_cod": "001", "vip_sta": "N",
                                    "master_nos": "0106", "guest_nam": "Mr. LIN,TEST",
                                    "account_nos": "CI20261012002"}, 101)
    r = requests.post(COMMANDS_URL, json=_body([cki]))
    assert r.status_code == 200
    assert parse_response_fields(r.json()["responses"][0])["resp_cod"] == "SUC"

    dat, tim = _mcall_dat(), _mcall_tim()
    mcs = build_host_record("MCS", {"phone_nos": "0106", "mcall_dat": dat,
                                    "mcall_tim": tim, "mcall_sta": "0"}, 102)
    r2 = requests.post(COMMANDS_URL, json=_body([mcs]))
    assert parse_response_fields(r2.json()["responses"][0])["resp_cod"] == "SUC"

    state = requests.get(STATE_URL).json()
    assert state["pbx_dt"]["0106"]["tel_sta"] == "1" and state["pbx_dt"]["0106"]["room_sta"] == "O"
    assert any(mc["room_nos"] == "0106" and mc["mcall_dat"] == dat and mc["mcall_sta"] == "0"
               for mc in state["mcall_mn"])

    cko = build_host_record("CKO", {"phone_nos": "0106"}, 103)
    r3 = requests.post(COMMANDS_URL, json=_body([cko]))
    assert parse_response_fields(r3.json()["responses"][0])["resp_cod"] == "SUC"
    state2 = requests.get(STATE_URL).json()
    assert state2["pbx_dt"]["0106"]["tel_sta"] == "0" and state2["pbx_dt"]["0106"]["room_sta"] == "V"
    assert all(mc["mcall_sta"] == "C" for mc in state2["mcall_mn"] if mc["room_nos"] == "0106")


def test_orchestrator_closed_loop_happy_paths(server_up):
    """經 /runs 編排:正向七案全 PASS,閉環回讀值與斷言摘要一致。"""
    requests.post(RESET_URL)
    dat, tim = _mcall_dat(), _mcall_tim()
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["pbx_checkin_open_tel", "pbx_morning_call_set", "pbx_morning_call_cancel",
                         "pbx_dnd_set", "pbx_tce_set", "pbx_checkout_close_tel", "pbx_room_change"],
        "overrides": {
            "pbx_checkin_open_tel": {"room_no": "0101", "lang_cod": "002"},
            "pbx_morning_call_set": {"room_no": "0102", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_morning_call_cancel": {"room_no": "0103", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_dnd_set": {"room_no": "0104", "status_typ": "1"},
            "pbx_tce_set": {"room_no": "0104", "status_typ": "0"},
            "pbx_checkout_close_tel": {"room_no": "0105", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_room_change": {"room_no": "0101", "new_room_no": "0107"},
        },
    })
    for cid, c in results.items():
        assert c["status"] == "PASS", (cid, c.get("response_payload"))
    assert results["pbx_checkin_open_tel"]["response_payload"]["state_readback"]["lang_cod"] == "002"
    assert results["pbx_morning_call_set"]["response_payload"]["state_readback"] == {"mcall_sta": "0"}
    assert results["pbx_morning_call_cancel"]["response_payload"]["state_readback"] == {"mcall_sta": "D"}
    assert results["pbx_dnd_set"]["response_payload"]["state_readback"] == {"dnd_cod": "1"}
    assert results["pbx_tce_set"]["response_payload"]["state_readback"] == {"tce_cod": "0"}
    ck = results["pbx_checkout_close_tel"]["response_payload"]["state_readback"]
    assert ck["tel_sta"] == "0" and ck["mcall_sta"] == "C"
    rmc = results["pbx_room_change"]["response_payload"]["state_readback"]
    assert rmc["new_tel_sta"] == "1" and rmc["old_room_sta"] == "V"
    # 覆寫貫穿:0101 換房到 0107 後,0107 電話開、0101 空房
    state = requests.get(STATE_URL).json()
    assert state["pbx_dt"]["0107"]["tel_sta"] == "1" and state["pbx_dt"]["0101"]["room_sta"] == "V"


def test_orchestrator_closed_loop_negatives(server_up):
    """經 /runs 編排:負向三案全 PASS(反向斷言:ERR ROOM_NOT_FOUND / 417 / ERR GUEST_NOT_IN)。"""
    requests.post(RESET_URL)
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["pbx_unknown_room", "pbx_bad_record", "pbx_dnd_without_guest"],
    })
    unk = results["pbx_unknown_room"]
    assert unk["status"] == "PASS"
    assert unk["response_payload"]["resp_cod"] == "ERR"
    assert unk["response_payload"]["msg_cod"].startswith("ROOM_NOT_FOUND")
    bad = results["pbx_bad_record"]
    assert bad["status"] == "PASS"
    assert bad["response_payload"]["code"] == "417"
    dnd = results["pbx_dnd_without_guest"]
    assert dnd["status"] == "PASS"
    assert dnd["response_payload"]["msg_cod"].startswith("GUEST_NOT_IN")
