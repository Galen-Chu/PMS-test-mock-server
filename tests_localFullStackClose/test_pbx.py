# tests_localFullStackClose/test_pbx.py
"""☎️ 交換機(PABX)模組 M0 離線測試(pbx_interface.doc + 宏興SD 契約)。

涵蓋:
- 記錄編解碼:192-byte 固定長度、CR+LF、數字靠右/文字靠左排版、
  CKI/MCS/回應記錄欄位往返、壞記錄 ValueError
- mock 交換機路由狀態機:CKI 開電話落庫、CKO 清空+晨呼取消(C)、
  MCS 設定/取消(D)、DND/TCE 前置(空房→ERR GUEST_NOT_IN)、RMC 搬移、
  未知房號→ERR ROOM_NOT_FOUND、未知指令→ERR MSG_FORMAT、壞記錄→417、內部回讀/重置
- registry:pbx 模組十案已實作且宣告 ParamSpec
- runner 離線組裝(連線失敗仍錄製 request_body → 斷言 192-byte 記錄內容與覆寫貫穿)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from flask import Flask

import orchestrator  # 觸發 runners 註冊
from orchestrator.registry import registry
from orchestrator import engine
from server.pbx import pbx_bp
from server.pbx.routes import mock_pbx_dt, mock_pbx_mcall
from server.pbx.vendors.vendor_PABX import (
    build_host_record, build_response_record,
    parse_record, parse_response_fields,
    RECORD_LEN, DATA_RMK_START,
)


def _client():
    app = Flask(__name__)
    app.register_blueprint(pbx_bp)
    return app.test_client()


def _body(records, athena="25", hotel="01"):
    return {"athenaId": athena, "hotelCode": hotel, "records": records}


def _cki(room, seq=1, **over):
    fields = {"phone_nos": room, "lang_cod": "001", "vip_sta": "N",
              "master_nos": room, "guest_nam": "Mr. CHU,GALEN",
              "account_nos": "CI20261012001"}
    fields.update(over)
    return build_host_record("CKI", fields, seq)


def _mcs(room, dat, tim, sta="0", seq=2):
    return build_host_record("MCS", {"phone_nos": room, "mcall_dat": dat,
                                     "mcall_tim": tim, "mcall_sta": sta}, seq)


def _reset(c):
    c.post("/pbx/internal/reset")


# ---- 記錄編解碼 --------------------------------------------------------
def test_record_layout_padding_and_roundtrip():
    rec = _cki("0101", 7)
    assert len(rec) == RECORD_LEN == 192 and rec.endswith("\r\n")
    assert rec[0] == "I"                              # Record_typ
    assert rec[1:8] == "      1"                      # Record_nos 9(7) 靠右(預設 1)
    assert rec[8:15] == "      7"                     # Seq_nos 靠右(本筆 seq=7)
    assert rec[15:23] == datetime.now().strftime("%Y%m%d")   # Insert_dat
    assert len(rec[23:29].strip()) == 6               # Insert_tim HHMMSS
    # Data_rmk 佈局(絕對位置 30 起):inst 3 碼 + phone X(6) + lang X(3) + vip X(1)...
    assert rec[DATA_RMK_START:DATA_RMK_START + 3] == "CKI"
    assert rec[DATA_RMK_START + 3:DATA_RMK_START + 9] == "0101  "
    assert rec[DATA_RMK_START + 9:DATA_RMK_START + 12] == "001"
    assert rec[DATA_RMK_START + 12] == "N"
    p = parse_record(rec)
    assert p["record_typ"] == "I" and p["inst_cod"] == "CKI"
    assert p["phone_nos"] == "0101" and p["lang_cod"] == "001"
    assert p["guest_nam"] == "Mr. CHU,GALEN" and p["seq_nos"] == "7"


def test_record_mcs_and_response_layout():
    rec = _mcs("0105", "20261013", "063000", "0")
    p = parse_record(rec)
    assert p["inst_cod"] == "MCS" and p["phone_nos"] == "0105"
    assert p["mcall_dat"] == "20261013" and p["mcall_tim"] == "063000"
    assert p["mcall_sta"] == "0"
    # mcall_dat 9(8) 靠右:位於 Data_rmk 區段 10~17(絕對 39~46)
    assert rec[38:46] == "20261013"

    resp = build_response_record("ERR", "20261012", "102030", 42,
                                  msg_cod="ROOM_NOT_FOUND: 9999", session_cod="S00001")
    assert len(resp) == 192 and resp.endswith("\r\n") and resp[0] == "R"
    f = parse_response_fields(resp)
    assert f["resp_cod"] == "ERR" and f["orig_seq_nos"] == "42"
    assert f["msg_cod"] == "ROOM_NOT_FOUND: 9999" and f["session_cod"] == "S00001"


def test_record_bad_structure_raises():
    for bad in ("", "X" * 100, "I" * 191 + "\r\n", "TOOLONG" * 40):
        try:
            parse_record(bad)
            assert False, f"should raise: {bad[:20]!r}"
        except ValueError:
            pass


# ---- mock 路由狀態機 ----------------------------------------------------
def test_mock_cki_lands_in_pbx_dt():
    c = _client()
    _reset(c)
    r = c.post("/pbx/host-commands", json=_body([_cki("0101")]))
    assert r.status_code == 200
    body = r.get_json()
    assert body["results"][0]["resp_cod"] == "SUC"
    f = parse_response_fields(body["responses"][0])
    assert f["resp_cod"] == "SUC" and f["msg_cod"] == ""
    assert mock_pbx_dt["0101"]["tel_sta"] == "1" and mock_pbx_dt["0101"]["room_sta"] == "O"
    assert mock_pbx_dt["0101"]["lang_cod"] == "001" and mock_pbx_dt["0101"]["dnd_cod"] == "0"
    rb = c.get("/pbx/internal/state").get_json()
    assert rb["pbx_dt"]["0101"]["tel_sta"] == "1"
    assert any(e["inst_cod"] == "CKI" and e["succ_flg"] == "Y" for e in rb["pbx_log_tail"])


def test_mock_cko_clears_state_and_cancels_mcall():
    c = _client()
    _reset(c)
    c.post("/pbx/host-commands", json=_body([_cki("0102")]))
    c.post("/pbx/host-commands", json=_body([_mcs("0102", "20261013", "070000")]))
    r = c.post("/pbx/host-commands",
               json=_body([build_host_record("CKO", {"phone_nos": "0102"}, 3)]))
    assert r.status_code == 200 and r.get_json()["results"][0]["resp_cod"] == "SUC"
    dt = mock_pbx_dt["0102"]
    assert dt["tel_sta"] == "0" and dt["room_sta"] == "V" and dt["lang_cod"] == ""
    mcs = [mc for mc in mock_pbx_mcall if mc[0] == "0102"]
    assert mcs and all(mock_pbx_mcall[k]["mcall_sta"] == "C" for k in mcs)


def test_mock_mcs_set_and_cancel():
    c = _client()
    _reset(c)
    c.post("/pbx/host-commands", json=_body([_cki("0103")]))
    c.post("/pbx/host-commands", json=_body([_mcs("0103", "20261013", "073000")]))
    assert mock_pbx_mcall[("0103", "20261013", "073000")]["mcall_sta"] == "0"
    c.post("/pbx/host-commands",
           json=_body([_mcs("0103", "20261013", "073000", sta="D")]))
    assert mock_pbx_mcall[("0103", "20261013", "073000")]["mcall_sta"] == "D"
    # 取消不存在的晨喚 → ERR MCALL_NOT_FOUND
    r = c.post("/pbx/host-commands",
               json=_body([_mcs("0103", "20261014", "080000", sta="D")]))
    f = parse_response_fields(r.get_json()["responses"][0])
    assert f["resp_cod"] == "ERR" and f["msg_cod"].startswith("MCALL_NOT_FOUND")


def test_mock_dnd_tce_preconditions():
    c = _client()
    _reset(c)
    # 空房 → ERR GUEST_NOT_IN(宏興SD:有住人才可設)
    r = c.post("/pbx/host-commands",
               json=_body([build_host_record("DND", {"phone_nos": "0104", "status_typ": "1"}, 1)]))
    f = parse_response_fields(r.get_json()["responses"][0])
    assert f["resp_cod"] == "ERR" and f["msg_cod"].startswith("GUEST_NOT_IN")
    # 入住後 → SUC + pbx_dt 落庫
    c.post("/pbx/host-commands", json=_body([_cki("0104")]))
    r2 = c.post("/pbx/host-commands",
                json=_body([build_host_record("DND", {"phone_nos": "0104", "status_typ": "1"}, 2)]))
    assert r2.get_json()["results"][0]["resp_cod"] == "SUC"
    assert mock_pbx_dt["0104"]["dnd_cod"] == "1"
    # TCE 取消(0)
    c.post("/pbx/host-commands",
           json=_body([build_host_record("TCE", {"phone_nos": "0104", "status_typ": "1"}, 3)]))
    r3 = c.post("/pbx/host-commands",
                json=_body([build_host_record("TCE", {"phone_nos": "0104", "status_typ": "0"}, 4)]))
    assert r3.get_json()["results"][0]["resp_cod"] == "SUC"
    assert mock_pbx_dt["0104"]["tce_cod"] == "0"


def test_mock_rmc_moves_state_and_mcall():
    c = _client()
    _reset(c)
    c.post("/pbx/host-commands", json=_body([_cki("0105")]))
    c.post("/pbx/host-commands", json=_body([_mcs("0105", "20261013", "090000")]))
    r = c.post("/pbx/host-commands",
               json=_body([build_host_record("RMC", {"ophone_nos": "0105",
                                                     "nphone_nos": "0106"}, 3)]))
    assert r.get_json()["results"][0]["resp_cod"] == "SUC"
    assert mock_pbx_dt["0106"]["tel_sta"] == "1" and mock_pbx_dt["0106"]["room_sta"] == "O"
    assert mock_pbx_dt["0105"]["tel_sta"] == "0" and mock_pbx_dt["0105"]["room_sta"] == "V"
    assert ("0106", "20261013", "090000") in mock_pbx_mcall      # 晨呼跟著移房
    assert ("0105", "20261013", "090000") not in mock_pbx_mcall
    # 換房到非住人房 → ERR GUEST_NOT_IN
    r2 = c.post("/pbx/host-commands",
                json=_body([build_host_record("RMC", {"ophone_nos": "0101",
                                                      "nphone_nos": "0102"}, 4)]))
    f = parse_response_fields(r2.get_json()["responses"][0])
    assert f["resp_cod"] == "ERR" and f["msg_cod"].startswith("GUEST_NOT_IN")


def _custom_record(inst, room):
    """組未知指令記錄(直接以文字排版;vendor 不認得的 inst 走 mock 的 ERR MSG_FORMAT)。"""
    head = "I" + "      1" * 2 + "20261012" + "120000"
    return head + (inst + room.ljust(6)).ljust(161)[:161] + "\r\n"


def test_mock_negative_paths():
    c = _client()
    _reset(c)
    # 未知房號 → 200 + ERR ROOM_NOT_FOUND(契約 Msg_cod 列舉)
    r = c.post("/pbx/host-commands", json=_body([_cki("9999")]))
    assert r.status_code == 200
    f = parse_response_fields(r.get_json()["responses"][0])
    assert f["resp_cod"] == "ERR" and f["msg_cod"].startswith("ROOM_NOT_FOUND")
    # 未知指令 → ERR MSG_FORMAT
    r2 = c.post("/pbx/host-commands", json=_body([_custom_record("XXY", "0101")]))
    f2 = parse_response_fields(r2.get_json()["responses"][0])
    assert f2["resp_cod"] == "ERR" and f2["msg_cod"].startswith("MSG_FORMAT")
    # 壞記錄(長度不足) → 417
    r3 = c.post("/pbx/host-commands", json=_body(["SHORT"]))
    assert r3.status_code == 417 and r3.get_json()["code"] == "417"
    # 缺識別 / 空 records → 400
    assert c.post("/pbx/host-commands", json={"records": ["x"]}).status_code == 400
    assert c.post("/pbx/host-commands", json={"athenaId": "25", "hotelCode": "01"}).status_code == 400


# ---- registry 與離線組裝 ------------------------------------------------
def test_registry_pbx_module():
    by_mod = registry.by_module()
    assert "pbx" in by_mod
    cases = {s.id: s for s in by_mod["pbx"]}
    expected = {"pbx_checkin_open_tel", "pbx_morning_call_set", "pbx_morning_call_cancel",
                "pbx_dnd_set", "pbx_tce_set", "pbx_checkout_close_tel", "pbx_room_change",
                "pbx_unknown_room", "pbx_bad_record", "pbx_dnd_without_guest"}
    assert expected == {i for i, s in cases.items() if s.vendor == "PABX"}   # M0 十案
    assert all(s.implemented for s in by_mod["pbx"])
    # 正向七案宣告 ParamSpec;負面三案固定劇本(參數化「不開放」原則)
    for sid in expected - {"pbx_unknown_room", "pbx_bad_record", "pbx_dnd_without_guest"}:
        assert cases[sid].params, sid
    set_case = cases["pbx_morning_call_set"]
    assert {sp.key for sp in set_case.params} == {"room_no", "mcall_dat", "mcall_tim"}
    # 動態預設(今天 + now+40 分)
    ctx = engine.build_run_context("LOCAL_OFFLINE")
    defaults = registry.resolve_defaults("pbx_morning_call_set", ctx)
    assert defaults["mcall_dat"] == datetime.now().strftime("%Y%m%d")
    assert len(defaults["mcall_tim"]) == 6


def test_runner_assembles_records_with_overrides():
    """離線(無 server)仍可驗證:覆寫貫穿記錄組裝(step 在連線前即錄製 request_body)。"""
    run = engine.start_run(["pbx_checkin_open_tel"], "LOCAL_OFFLINE",
                           overrides={"pbx_checkin_open_tel": {"room_no": "0107",
                                                               "lang_cod": "002"}})
    cr = run.cases[0]
    assert cr.resolved_params["room_no"] == "0107" and cr.resolved_params["lang_cod"] == "002"
    rec = cr.steps[0]["request_body"]["records"][0]
    assert len(rec) == 192 and rec.endswith("\r\n")
    assert parse_record(rec)["phone_nos"] == "0107"     # 覆寫貫穿記錄
    assert parse_record(rec)["lang_cod"] == "002"
    # 晨喚案:動態預設貫穿 MCS 記錄(第 2 筆)
    run2 = engine.start_run(["pbx_morning_call_set"], "LOCAL_OFFLINE",
                            overrides={"pbx_morning_call_set": {"mcall_tim": "233000"}})
    recs = run2.cases[0].steps[0]["request_body"]["records"]
    assert len(recs) == 2                 # CKI 前置 + MCS
    mcs = parse_record(recs[1])
    assert mcs["inst_cod"] == "MCS" and mcs["mcall_tim"] == "233000"
    assert mcs["mcall_dat"] == datetime.now().strftime("%Y%m%d")


def test_run_context_has_pbx_urls():
    for env in ("LOCAL_OFFLINE", "LOCAL", "REAL_QA"):
        ctx = engine.build_run_context(env)
        assert ctx.urls["pbx_commands"].endswith("/pbx/host-commands")
        assert ctx.urls["pbx_internal"].endswith("/pbx/internal/state")


def test_pbx_cases_skip_in_real_env():
    """REAL 環境:pbx 案例一律 SKIP(M0 檔案介面無雲端端點,待 API SD)。"""
    run = engine.start_run(["pbx_checkin_open_tel"], "REAL_QA")
    cr = run.cases[0]
    assert cr.status == "SKIP" and cr.error_category == "REAL_NOT_SUPPORTED"
