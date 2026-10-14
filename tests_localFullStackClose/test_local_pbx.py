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
BILL_RESET_URL = f"{BASE}/pbx/billing/internal/reset"


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
            "pbx_ui_room_change_reschedules": {"room_no": "0104", "new_room_no": "0106",
                                               "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_mcall_expire_skip": {"room_no": "0109"},
            "pbx_ui_open_tel_vacant_denied": {"room_no": "0108"},
            "pbx_ui_del_past_mcall_denied": {"room_no": "0107"},
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


def test_orchestrator_m2_ring_anomaly_resend_rms(server_up):
    """M2 閉環:撥號回報/晨喚異常/重送/RMS 經 /runs 編排全 PASS。"""
    requests.post(RESET_URL)
    requests.post(PMS_RESET_URL)
    dat = datetime.now().strftime("%Y%m%d")
    tim = (datetime.now() + timedelta(minutes=40)).strftime("%H%M%S")
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["pbx_ui_mcs_ring_answered", "pbx_ui_mcs_ring_busy_anomaly_ack",
                         "pbx_ui_mcs_ring_no_time_earliest", "pbx_ui_resend_full",
                         "pbx_ui_rms_room_status"],
        "overrides": {
            "pbx_ui_mcs_ring_answered": {"room_no": "0101", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_mcs_ring_busy_anomaly_ack": {"room_no": "0102", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_mcs_ring_no_time_earliest": {"room_no": "0103", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_resend_full": {"room_no": "0104", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_ui_rms_room_status": {"room_no": "0105"},
        },
    })
    for cid, c in results.items():
        assert c["status"] == "PASS", (cid, c.get("response_payload"))
    ring_ok = results["pbx_ui_mcs_ring_answered"]["response_payload"]
    assert ring_ok["pms_mcall"]["mcall_sta"] == "1" and ring_ok["anomaly_count"] == 0
    busy = results["pbx_ui_mcs_ring_busy_anomaly_ack"]["response_payload"]
    assert busy["anomaly_before"] == 1 and busy["anomaly_after"] == 0
    assert busy["pbx_err_tail"][-1]["error_cod"] == "Busy"
    rs = results["pbx_ui_resend_full"]["response_payload"]
    assert rs["mcall_after_resend"]["trans_pbx_sta"] == "NOT_TRANS"   # 重送後先重設未傳送
    assert rs["mcall_after_retick"]["trans_pbx_sta"] == "TRANS"       # 再 tick 後重新下達
    rms = results["pbx_ui_rms_room_status"]["response_payload"]
    assert rms["rms_fresh"]["pbx_dt.check_sta"] == "C"

from server.pbx.vendors.vendor_PABX import (  # noqa: E402
    build_host_record, parse_record, parse_response_fields,
)


def _body(records):
    return {"athenaId": "25", "hotelCode": "01", "records": records}


def _mcall_dat():
    return datetime.now().strftime("%Y%m%d")


def _mcall_tim():
    return (datetime.now() + timedelta(minutes=40)).strftime("%H%M%S")


def test_orchestrator_m3_file_exchange_via_runs(server_up):
    """M3 閉環:真檔案交換三案經 /runs 編排(往返全鏈/環狀輪替/中文姓名政策)。"""
    requests.post(RESET_URL)
    requests.post(PMS_RESET_URL)
    dat = datetime.now().strftime("%Y%m%d")
    tim = (datetime.now() + timedelta(minutes=40)).strftime("%H%M%S")
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["pbx_file_roundtrip", "pbx_file_wraparound", "pbx_file_china_name"],
        "overrides": {
            "pbx_file_roundtrip": {"room_no": "0101", "mcall_dat": dat, "mcall_tim": tim},
            "pbx_file_wraparound": {"room_no": "0102"},
            "pbx_file_china_name": {"room_no": "0103"},
        },
    })
    for cid, c in results.items():
        assert c["status"] == "PASS", (cid, c.get("response_payload"))
    rt = results["pbx_file_roundtrip"]["response_payload"]
    assert rt["sw_tel_sta"] == "1" and rt["sw_mcall"]                  # 經檔案路徑落庫
    wa = results["pbx_file_wraparound"]["response_payload"]
    h2p = wa["file_state"]["host2pms"]
    assert wa["mid2_host2pms"]["wcycle_typ"] == "B"                   # 第一圈繞完翻 B
    assert h2p["wcycle_typ"] == "A" and h2p["pcycle_typ"] == "A"      # 第二圈繞回 A、讀方跟上
    assert h2p["wseq_nos"] == 4 and wa["file_state"]["pms2host"]["wseq_nos"] == 4
    cn = results["pbx_file_china_name"]["response_payload"]
    assert cn["processed_chinese"]                                     # 中文政策兩段皆通


def test_orchestrator_m4_billing_via_runs(server_up):
    """M4 閉環:帳務面六案經 /runs 編排(住客帳/類別路由/關帳失敗/現金帳/事務分機/MBT)。"""
    requests.post(BILL_RESET_URL)
    requests.post(RESET_URL)
    requests.post(PMS_RESET_URL)
    results = _run_and_results({
        "environment": "LOCAL_OFFLINE",
        "scenario_ids": ["pbx_bill_ptx_guest_posting", "pbx_bill_ptx_typ_routing",
                         "pbx_bill_ptx_closed_k", "pbx_bill_ptx_cash_after_checkout",
                         "pbx_bill_ptx_smdr_office", "pbx_bill_mbt_minibar"],
        "overrides": {
            "pbx_bill_ptx_guest_posting": {"room_no": "0101", "amt": "12.25", "talk_sec": "130"},
            "pbx_bill_ptx_typ_routing": {"room_no": "0102"},
            "pbx_bill_ptx_closed_k": {"room_no": "0104"},
            "pbx_bill_ptx_cash_after_checkout": {"room_no": "0105"},
            "pbx_bill_mbt_minibar": {"room_no": "0106"},
        },
    })
    for cid, c in results.items():
        assert c["status"] == "PASS", (cid, c.get("response_payload"))
    gp = results["pbx_bill_ptx_guest_posting"]["response_payload"]
    assert gp["ptx"][0]["result"] == "GUEST" and gp["guest_dt"][0]["item_cod"] == "LOCAL"
    assert gp["guest_dt"][0]["item_amt"] == 12.3 and gp["gutel"]["tel_sta"] == "HAD_TRANS"
    tr = results["pbx_bill_ptx_typ_routing"]["response_payload"]
    assert tr["results"] == ["SKIPPED_XXX", "GUEST", "GUEST"]
    assert tr["guest_items"] == ["LOCAL", "INTL"]                    # LDC→市話/OSC→國際
    ck = results["pbx_bill_ptx_closed_k"]["response_payload"]
    assert ck["ptx"][0]["result"] == "FAIL_CLOSED_K"
    assert ck["pbx_err_for_room"][-1]["error_cod"] == "住客為關帳"
    assert ck["gutel"]["tel_sta"] == "NOT_TRANS" and ck["gutel"]["ikey"] == "IK0104"
    ca = results["pbx_bill_ptx_cash_after_checkout"]["response_payload"]
    assert ca["ptx"][0]["result"] == "CASH"
    assert ca["gutel"]["ikey"] == "****" and ca["gutel"]["ikey_seq_nos"] == 0  # v1.8 現金帳
    assert ca["guest_dt"]["remark3"].startswith("from 房號:0105")
    assert ca["cash_guest"]["room_nos"] == "9999"                    # 自動開立現金帳
    so = results["pbx_bill_ptx_smdr_office"]["response_payload"]
    assert so["ptx_smdr"][0]["result"] == "SMDR" and so["ptx_smdr"][0]["cost_amt"] == 109.1
    assert so["smdr"]["dept_cod"] == "FRONT"                          # round(120/1.1,1)
    assert so["ptx_miss"][0]["result"] == "ERR_PHONE_NOT_FOUND"      # PHONE_RF 查無
    assert so["pbx_err_8888"] and "分機" in so["pbx_err_8888"][-1]["error_cod"]
    mb = results["pbx_bill_mbt_minibar"]["response_payload"]
    assert mb["mbt"][0]["result"] == "GUEST" and mb["guest_dt"]["item_cod"] == "MB"
    assert mb["gutel_before"] == mb["gutel_after"]                    # 非電話明細不入 gutel_dt


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
