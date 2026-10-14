# tests_localFullStackClose/test_pbx_billing.py
"""☎️ 交換機 M4(帳務面)離線測試 — PTX 電話入帳(SA §7.2.1.1)+ MBT Mini bar。

涵蓋:
- 記錄佈局:PTX/MBT 192-byte 絕對位置(pbx_interface「Telephone/Mini bar (pms to host)」)
- 規則2:trans_amt 四捨五入(Decimal HALF_UP 非 Silver rounding)、talk_tim 秒數轉時分秒上限
- 規則1/3:Trans_typ=XXX skip、PHONE_RF 查無入 pbx_err、ROOM_NOS 無設定認定住客帳
- 規則4/6:act_cod=Y→guest_dt+gutel_dt、N→smdr_dt(cost=四捨五入(amt/加成率))
- 規則5:在館客選客(aci_sys_dat<=開始時間)、零元參數、K 關帳失敗、C 已結帳現金帳(v1.8)
- MBT:自定義入住客帳(不入 gutel_dt)
- 端點:參數覆寫/guest_mn 測試入口/phone_rf 覆寫/reset 隔離
- registry:pbx 模組 32 案
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

import orchestrator  # noqa: F401 觸發 runners 註冊
from orchestrator.registry import registry
from server.pbx import pbx_bp
from server.pbx.pms_side import pms_bp
from server.pbx.billing import billing_bp
from server.pbx.vendors.vendor_PABX import build_host_record, parse_record

TODAY = datetime.now().strftime("%Y%m%d")
SOON = (datetime.now() + timedelta(minutes=2)).strftime("%H%M%S")   # 晚於入住 aci(選客條件)

BILL_RESET = "/pbx/billing/internal/reset"
BILL_STATE = "/pbx/billing/internal/state"
PMS_RESET = "/pbx/pms/internal/reset"


def _client():
    app = Flask(__name__)
    app.register_blueprint(pbx_bp)
    app.register_blueprint(pms_bp)
    app.register_blueprint(billing_bp)
    return app.test_client()


def _reset(c):
    c.post(BILL_RESET)
    c.post(PMS_RESET)


def _ptx(phone="0101", tel="0988123456", typ="LDC", amt="12.25", sign="",
         start_dat=None, start_tim=None, talk="130", seq=1):
    start_dat = start_dat or TODAY
    start_tim = start_tim or SOON
    rec = build_host_record("PTX", {
        "phone_nos": phone, "tel_nos": tel, "trans_dat": start_dat,
        "trans_tim": "080500", "trans_typ": typ, "sign_typ": sign,
        "trans_amt": amt, "start_dat": start_dat, "start_tim": start_tim,
        "talk_tim": talk}, seq)
    return rec


def _mbt(phone="0101", amt="150", dat=None, tim=None, seq=1):
    # trans_dat/tim 同時是 MBT 選客依據 → 預設晚於入住 aci_sys_dat
    return build_host_record("MBT", {"phone_nos": phone, "trans_dat": dat or TODAY,
                                     "trans_tim": tim or SOON, "sign_typ": "",
                                     "trans_amt": amt}, seq)


def _send_ptx(c, *records):
    return c.post("/pbx/billing/ptx",
                  json={"athenaId": "25", "hotelCode": "01", "records": list(records)})


def _send_mbt(c, *records):
    return c.post("/pbx/billing/mbt",
                  json={"athenaId": "25", "hotelCode": "01", "records": list(records)})


def _checkin(c, room="0101"):
    assert c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01",
                                            "action": "checkin", "room_nos": room}
                  ).get_json()["ok"] is True


# ---- 記錄佈局(pbx_interface 絕對位置) --------------------------------------
def test_ptx_layout_absolute_positions():
    rec = _ptx()
    assert len(rec) == 192 and rec.endswith("\r\n")
    assert rec[29:32] == "PTX"                 # Inst_cod 30~32
    assert rec[32:38] == "0101  "[:6]          # Phone_nos X(6) 靠左
    assert rec[38:58].startswith("0988123456")  # Tel_nos X(20)
    assert rec[58:66] == TODAY                 # Trans_dat
    assert rec[66:72] == "080500"              # Trans_tim
    assert rec[72:75] == "LDC"                 # Trans_typ
    assert rec[76:83].strip() == "12.25"       # Trans_amt 9(7) 靠右(前導空白)
    assert rec[83:91] == TODAY                 # Start_dat
    assert rec[91:97] == SOON                  # Start_tim
    assert rec[97:103] == "   130"             # Talk_tim(秒數)靠右
    parsed = parse_record(rec)
    assert parsed["trans_typ"] == "LDC" and parsed["talk_tim"] == "130"
    assert parsed["sign_typ"] == "" and parsed["trans_amt"] == "12.25"


def test_mbt_layout_absolute_positions():
    rec = _mbt()
    assert len(rec) == 192 and rec.endswith("\r\n")
    assert rec[29:32] == "MBT"
    assert rec[32:38] == "0101  "[:6]
    assert rec[38:46] == TODAY                 # Trans_dat 39~46
    assert rec[46:52] == SOON                  # Trans_tim 47~52
    assert rec[52:53] == " "                   # Sign_typ 53
    assert rec[53:60].strip() == "150"         # Trans_amt 54~60(靠右)
    parsed = parse_record(rec)
    assert parsed["trans_amt"] == "150" and parsed["trans_dat"] == TODAY


def test_billing_endpoint_rejects_bad_records():
    c = _client()
    _reset(c)
    r = _send_ptx(c, "NOT_A_RECORD")
    assert r.status_code == 417
    r2 = _send_ptx(c, _mbt())                  # PTX 端點收 MBT 記錄 → 417
    assert r2.status_code == 417
    r3 = c.post("/pbx/billing/ptx", json={"athenaId": "25", "hotelCode": "01"})
    assert r3.status_code == 400


# ---- 規則2:四捨五入 + 秒數轉換 ---------------------------------------------
def test_round_half_up_and_talk_caps():
    from server.pbx.billing import _round_hfd, _talk_hhmmss, _signed_amount
    assert _round_hfd("12.25", 1) == 12.3      # HALF_UP(Python round 會給 12.2)
    assert _round_hfd("12.5", 0) == 13.0
    assert _round_hfd(None, 1) == 0.0          # null 算 0 元
    assert _signed_amount(None, "-", 1) == 0.0    # 空金額+負號 → 0
    assert _signed_amount("12.25", "-", 1) == -12.3
    assert _talk_hhmmss("130") == "000210"     # 130 秒 = 2 分 10 秒
    assert _talk_hhmmss("86399") == "235959"   # 自然上限
    assert _talk_hhmmss("86400") == "235959"   # >86399 改 235959
    assert _talk_hhmmss("89999") == "235959"
    assert _talk_hhmmss("90000") == "245959"   # >89999 改 245959
    assert _talk_hhmmss("91000") == "245959"


# ---- 規則1/3/4/5:PTX 全路徑 --------------------------------------------------
def test_ptx_guest_posting_full_chain():
    c = _client()
    _reset(c)
    _checkin(c, "0101")
    r = _send_ptx(c, _ptx(phone="0101", amt="12.25", talk="130"))
    assert r.status_code == 200
    res = r.get_json()["results"][0]
    assert res["result"] == "GUEST" and res["acct_nos"].startswith("AC")
    st = c.get(BILL_STATE).get_json()
    gd, gu = st["guest_dt"][-1], st["gutel_dt"][-1]
    assert gd["item_cod"] == "LOCAL" and gd["item_amt"] == 12.3     # round_hfd=1
    assert gd["shift_cod"] == "Z" and gd["ins_usr"] == "PBX"
    assert gd["rspt_cod"] == "HC1" and gd["bill_dat"] == TODAY
    assert gd["remark4"].endswith("000210") and gd["ikey"] == "IK0101"
    assert gu["tel_sta"] == "HAD_TRANS" and gu["talk_tim"] == "000210"
    assert gu["trans_amt"] == 12.3 and gu["ikey"] == "IK0101"
    assert gu["acct_nos"] == gd["acct_nos"] and gu["trans_typ"] == "LDC"
    assert not st["smdr_dt"] and not st["cash_guest"]


def test_ptx_skip_xxx_and_typ_item_routing():
    c = _client()
    _reset(c)
    _checkin(c, "0102")
    r = _send_ptx(c, _ptx(phone="0102", typ="XXX"),
                  _ptx(phone="0102", typ="LDC", talk="86400", amt="30", seq=2),
                  _ptx(phone="0102", typ="OSC", talk="91000", amt="40", seq=3))
    results = [x["result"] for x in r.get_json()["results"]]
    assert results == ["SKIPPED_XXX", "GUEST", "GUEST"]
    st = c.get(BILL_STATE).get_json()
    assert [g["item_cod"] for g in st["guest_dt"]] == ["LOCAL", "INTL"]
    talks = [g["talk_tim"] for g in st["gutel_dt"]]
    assert talks == ["235959", "245959"]        # >86399 / >89999 上限


def test_ptx_zero_fee_param():
    c = _client()
    _reset(c)
    _checkin(c, "0103")
    assert c.post("/pbx/billing/params",
                  json={"pbx_zero_fee_insert_guest": "N"}).get_json()["ok"]
    r = _send_ptx(c, _ptx(phone="0103", amt="0"))
    assert r.get_json()["results"][0]["result"] == "ZERO_SKIP"
    st = c.get(BILL_STATE).get_json()
    assert not st["guest_dt"]
    gu = st["gutel_dt"][-1]
    assert gu["tel_sta"] == "NOT_TRANS" and "零元" in gu["err_rmk"]
    assert gu["trans_amt"] == 0


def test_ptx_closed_k_fails_into_pbx_err():
    c = _client()
    _reset(c)
    _checkin(c, "0104")
    g = c.post("/pbx/billing/guests",
               json={"room_nos": "0104", "guest_sta": "K"}).get_json()
    assert g["ok"] and g["guests"][0]["guest_sta"] == "K"
    r = _send_ptx(c, _ptx(phone="0104"))
    assert r.get_json()["results"][0]["result"] == "FAIL_CLOSED_K"
    st, pms = c.get(BILL_STATE).get_json(), c.get("/pbx/pms/internal/state").get_json()
    assert not st["guest_dt"]
    gu = st["gutel_dt"][-1]
    assert gu["tel_sta"] == "NOT_TRANS" and "關帳" in gu["err_rmk"]
    assert gu["ikey"] == "IK0104"               # 失敗仍保留卡號(SA:入帳失敗可知要入哪張卡)
    err = pms["pbx_err_tail"][-1]
    assert err["inst_cod"] == "PTX" and err["error_cod"] == "住客為關帳"


def test_ptx_checkout_cash_account():
    c = _client()
    _reset(c)
    _checkin(c, "0105")
    assert c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01",
                                            "action": "checkout", "room_nos": "0105"}
                  ).get_json()["ok"]
    r = _send_ptx(c, _ptx(phone="0105"))
    assert r.get_json()["results"][0]["result"] == "CASH"
    st = c.get(BILL_STATE).get_json()
    gd, gu = st["guest_dt"][-1], st["gutel_dt"][-1]
    assert gd["remark3"].startswith("from 房號:0105") and "TEL_NOS:0988123456" in gd["remark3"]
    assert gu["ikey"] == "****" and gu["ikey_seq_nos"] == 0   # v1.8 現金帳
    assert "現金帳" in gu["err_rmk"] and gu["tel_sta"] == "HAD_TRANS"
    assert gu["ci_ser"] == "CASH"
    assert st["cash_guest"]["room_nos"] == "9999"             # 自動開立現金帳


def test_ptx_smdr_office_and_phone_rf_miss():
    c = _client()
    _reset(c)
    r = _send_ptx(c, _ptx(phone="9001", amt="120", typ="LDC", talk="250"))
    res = r.get_json()["results"][0]
    assert res["result"] == "SMDR" and res["cost_amt"] == 109.1   # round(120/1.1,1)
    st = c.get(BILL_STATE).get_json()
    row = st["smdr_dt"][-1]
    assert row["dept_cod"] == "FRONT" and row["cost_amt"] == 109.1
    assert row["talk_tim"] == "000410" and not st["gutel_dt"] and not st["guest_dt"]  # 250秒=4分10秒
    # PHONE_RF 模式:phone_rf 查無 → pbx_err
    c.post("/pbx/billing/params", json={"pbx_phone_nos_way": "PHONE_RF"})
    r2 = _send_ptx(c, _ptx(phone="8888", seq=2))
    assert r2.get_json()["results"][0]["result"] == "ERR_PHONE_NOT_FOUND"
    pms = c.get("/pbx/pms/internal/state").get_json()
    assert pms["pbx_err_tail"][-1]["error_cod"].startswith("分機")


def test_ptx_vacant_room_no_guest_fails():
    c = _client()
    _reset(c)                                   # 不入住直接打 0107(空房)
    r = _send_ptx(c, _ptx(phone="0107"))
    assert r.get_json()["results"][0]["result"] == "FAIL_NO_GUEST"
    st = c.get(BILL_STATE).get_json()
    assert not st["guest_dt"]
    assert st["gutel_dt"][-1]["tel_sta"] == "NOT_TRANS"
    pms = c.get("/pbx/pms/internal/state").get_json()
    assert pms["pbx_err_tail"][-1]["error_cod"] == "查無住客資料"


# ---- MBT(Mini bar;沙盒自定義) ---------------------------------------------
def test_mbt_minibar_posting():
    c = _client()
    _reset(c)
    _checkin(c, "0106")
    r = _send_mbt(c, _mbt(phone="0106", amt="150"))
    assert r.get_json()["results"][0]["result"] == "GUEST"
    st = c.get(BILL_STATE).get_json()
    gd = st["guest_dt"][-1]
    assert gd["item_cod"] == "MB" and gd["item_amt"] == 150.0
    assert gd["remark4"].startswith("MBT") and gd["bill_dat"] == TODAY
    assert gd["shift_cod"] == "Z" and gd["ins_usr"] == "PBX"
    assert not st["gutel_dt"]                   # 非電話明細不入 gutel_dt
    # 退房後 MBT → 現金帳
    c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01",
                                     "action": "checkout", "room_nos": "0106"})
    r2 = _send_mbt(c, _mbt(phone="0106", amt="80", seq=2))
    assert r2.get_json()["results"][0]["result"] == "CASH"
    gd2 = c.get(BILL_STATE).get_json()["guest_dt"][-1]
    assert gd2["remark3"].startswith("from 房號:0106") and gd2["ikey"] == "****"


# ---- 參數/phone_rf/reset 隔離 -------------------------------------------------
def test_params_phone_rf_and_reset_isolation():
    c = _client()
    _reset(c)
    r = c.post("/pbx/billing/params", json={"round_hfd": 0, "no_such_param": 1})
    assert r.status_code == 400                  # 未知參數拒絕
    assert c.post("/pbx/billing/params", json={"round_hfd": 0}).get_json()["params"]["round_hfd"] == 0
    # phone_rf 覆寫:9003 設為事務分機
    pr = c.post("/pbx/billing/phone-rf",
                json={"phone_nos": "9003", "dept_cod": "ENG", "act_cod": "N"}).get_json()
    assert pr["ok"] and pr["phone_rf"]["act_cod"] == "N"
    _send_ptx(c, _ptx(phone="9003", amt="55"))
    st = c.get(BILL_STATE).get_json()
    assert st["smdr_dt"][-1]["dept_cod"] == "ENG"
    _reset(c)                                    # 隔離:全部回預設
    st2 = c.get(BILL_STATE).get_json()
    assert not st2["smdr_dt"] and not st2["gutel_dt"] and not st2["guest_mn"]
    assert st2["params"]["round_hfd"] == 1 and "9003" not in st2["phone_rf"]
    # pms 側 reset 亦連動帳務層
    _checkin(c, "0108")
    c.post(PMS_RESET)
    assert not c.get(BILL_STATE).get_json()["guest_mn"]


def test_registry_pbx_module_m4():
    by_mod = registry.by_module()
    cases = {s.id: s for s in by_mod["pbx"]}
    assert len(cases) == 32                      # M0 10 + M1 7 + M2 5 + M3 3 + M4 7
    for cid in ("pbx_bill_ptx_guest_posting", "pbx_bill_ptx_typ_routing",
                "pbx_bill_ptx_zero_fee", "pbx_bill_ptx_closed_k",
                "pbx_bill_ptx_cash_after_checkout", "pbx_bill_ptx_smdr_office",
                "pbx_bill_mbt_minibar"):
        assert cases[cid].implemented
        assert cases[cid].vendor == "PMS_UI"
