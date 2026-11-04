# tests_localFullStackClose/test_roomcontrol.py
"""🌡️ 房控模組(A7 公版 XML 介面,sa_docs/sa10)RC0+RC2 離線測試。

涵蓋:
- XML 工具組裝/解析往返(ROWSET>ROW、多列回應;RC2:CLEAN/RMTEMP/KeyBox 組裝器)
- mock PMS 路由契約(POST /third-party/import-sync-files):ROOM_STA 落庫、ROOM_INF 住客列、
  壞 XML → 417、缺識別 → 400;內部回讀端點
- RC2:單值族 action 更新對應房況位元(CLEAN→位9)、RMTEMP 室溫落庫、
  B5 KeyBox(REVE 4390,插/拔卡→位2+卡片資訊,回應無 ACTION_COD)、
  未知 ACTION_COD → procStatus=false+RETN 9999、缺 ROOM_NOS/B5 必填 → 417
- registry:roomcontrol 模組各案已實作且宣告 ParamSpec
- runner 離線組裝(連線失敗仍錄製 request_body → 斷言 XML 內容與覆寫貫穿)
- RC2.5(2026-11-03,sa11 = A7 SQL 處理文件):PBX_DT 欄位極性解碼、F 斷線三連動、
  未知房號 9999 / E 模擬房 1001、MAIN_POWER 單值族極性反轉、A10 走房間主檔、
  internal/rooms + internal/reset 自助端點
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

import orchestrator  # 觸發 runners 註冊
from orchestrator.registry import registry
from orchestrator import engine
from server.roomcontrol import roomcontrol_bp
from server.roomcontrol.routes import (mock_roomcontrol_state, mock_room_guest_db,
                                        mock_room_mn)
from server.roomcontrol.vendors.vendor_A7_XML import (
    build_room_sta_push, build_room_inf_query, build_return_query,
    build_clean_push, build_rmtemp_push, build_keybox_push,
    parse_rowset_xml, build_rowset_xml, DEFAULT_STATUS_BITS,
    REVE_ROOM_STA, REVE_ROOM_INF, REVE_KEYBOX, reve_keybox,
)


def _client():
    app = Flask(__name__)
    app.register_blueprint(roomcontrol_bp)
    return app.test_client()


def _import_body(xml_str, athena="25", hotel="01", third="TT", fname="C001.xml"):
    return {"athenaId": athena, "hotelCode": hotel, "thirdPartyCode": third,
            "requestDataList": [{"requestBody": xml_str, "fileName": fname}]}


def test_xml_roundtrip_and_contract_constants():
    xml = build_room_sta_push("2403", "010101011001")
    rows = parse_rowset_xml(xml)
    assert rows[0]["REVE-CODE"] == REVE_ROOM_STA == "0300TT4190"
    assert rows[0]["ACTION_COD"] == "#ROOM_STA#010101011001#"
    assert rows[0]["ROOM_NOS"] == "2403"
    assert rows[0]["ACTION_STA"] == "1"
    assert rows[0]["ACTION_DAT"].count("/") == 2 and len(rows[0]["ACTION_DAT"]) == 19

    q = parse_rowset_xml(build_room_inf_query("0770"))
    assert q[0]["REVE-CODE"] == REVE_ROOM_INF == "0300TT1090"
    assert q[0]["ACTION_COD"] == "ROOM_INF"

    # 多列回應(ROOM_INF 兩位住客)
    multi = build_rowset_xml([{"ROOM_SER": "1", "ROOM_STA": "O"},
                              {"ROOM_SER": "2", "ROOM_STA": "O"}])
    assert len(parse_rowset_xml(multi)) == 2
    # 預設房況字串 16 位
    assert len(DEFAULT_STATUS_BITS) == 16


def test_mock_route_room_sta_push_lands_in_state():
    c = _client()
    r = c.post("/third-party/import-sync-files", json=_import_body(build_room_sta_push("2501", "010101011001")))
    assert r.status_code == 200
    item = r.get_json()[0]
    assert item["procStatus"] is True
    rows = parse_rowset_xml(item["responseBody"])
    assert rows[0]["SEND-CODE"] == "0300TT4190"
    assert rows[0]["RETN-CODE"] == "0000"
    assert "2501 Set #ROOM_STA#010101011001#" in rows[0]["RETN-CODE-DESC"]  # RC2.5(sa11):{房號} Set
    # 落庫 + 內部回讀閉環
    assert mock_roomcontrol_state["2501"]["status_bits"] == "010101011001"
    rb = c.get("/roomcontrol/internal/state")
    assert rb.status_code == 200
    assert (rb.get_json()["room_control_state"]["2501"])["status_bits"] == "010101011001"


def test_mock_route_room_inf_guest_rows_and_vacant():
    c = _client()
    r = c.post("/third-party/import-sync-files", json=_import_body(build_room_inf_query("2403")))
    assert r.status_code == 200
    item = r.get_json()[0]
    rows = parse_rowset_xml(item["responseBody"])
    assert len(rows) == len(mock_room_guest_db["2403"])     # 一住客一 ROW
    assert all(row["ROOM_STA"] == "O" for row in rows)
    assert rows[0]["CI_SER"] and rows[0]["ALT_NAM"]
    assert all(row["RETN-CODE"] == "0000" for row in rows)

    # RC2.5(sa11):V/R/S 空房 → 單列全欄位空值(ADVBAL_AMT/CCARD_AMT 為 0)
    for room, sta in (("2404", "V"), ("2405", "R"), ("2406", "S")):
        r2 = c.post("/third-party/import-sync-files", json=_import_body(build_room_inf_query(room)))
        rows2 = parse_rowset_xml(r2.get_json()[0]["responseBody"])
        assert len(rows2) == 1 and rows2[0]["ROOM_STA"] == sta
        assert rows2[0]["RETN-CODE"] == "0000"
        assert rows2[0]["ROOM_SER"] == "" and rows2[0]["CI_SER"] == "" and rows2[0]["ALT_NAM"] == ""
        assert rows2[0]["ADVBAL_AMT"] == "0" and rows2[0]["CCARD_AMT"] == "0"


def test_mock_route_negative_paths():
    c = _client()
    # 壞 XML → 417
    r = c.post("/third-party/import-sync-files", json=_import_body("<ROWSET><ROW>不是完整XML"))
    assert r.status_code == 417
    # 缺識別三元組 → 400
    r2 = c.post("/third-party/import-sync-files", json={"requestDataList": [{"requestBody": "<a/>"}]})
    assert r2.status_code == 400
    # 空 requestDataList → 400
    r3 = c.post("/third-party/import-sync-files", json=_import_body("x"))  # 有識別但 list 缺
    r4 = c.post("/third-party/import-sync-files",
                json={"athenaId": "25", "hotelCode": "01", "thirdPartyCode": "TT"})
    assert r4.status_code == 400


def test_mock_route_return_all_rooms_with_clean_sta_closure():
    """A10 RETURN:全房一 ROW;推送位元串第 9 位(清潔)→ CLEAN_STA 推導(第二條閉環)。"""
    c = _client()
    # 推送:房 2601 位元串第 9 位=3(待巡房 → CLEAN_STA=S)
    c.post("/third-party/import-sync-files",
           json=_import_body(build_room_sta_push("2601", "1000001130100000")))
    # 推送:房 2602 第 9 位=1(請打掃 → D 髒房)
    c.post("/third-party/import-sync-files",
           json=_import_body(build_room_sta_push("2602", "1000001110100000")))

    r = c.post("/third-party/import-sync-files", json=_import_body(build_return_query()))
    assert r.status_code == 200
    item = r.get_json()[0]
    rows = parse_rowset_xml(item["responseBody"])
    by_room = {row["ROOM_NOS"]: row for row in rows}
    assert by_room["2403"]["ROOM_STA"] == "O"          # 種子住客房
    assert by_room["2601"]["ROOM_STA"] == "V" and by_room["2601"]["CLEAN_STA"] == "S"
    assert by_room["2602"]["ROOM_STA"] == "V" and by_room["2602"]["CLEAN_STA"] == "D"
    assert all(row["RETN-CODE"] == "0000" for row in rows)


def test_same_family_builders_and_b5_contract():
    """RC2 組裝器:CLEAN(SAMPLE1 樣式)/RMTEMP(SAMPLE3)/KeyBox(B5,訊息無 ACTION_COD)。"""
    clean = parse_rowset_xml(build_clean_push("2403", "3", vendor_code="81"))
    assert clean[0]["REVE-CODE"] == "0300814190"
    assert clean[0]["ACTION_COD"] == "CLEAN" and clean[0]["ACTION_STA"] == "3"
    assert "INS_CARD_INF" not in clean[0]          # SAMPLE1 樣式無插卡欄位

    temp = parse_rowset_xml(build_rmtemp_push("2403", "26C", vendor_code="86"))
    assert temp[0]["REVE-CODE"] == "0300864190"
    assert temp[0]["ACTION_COD"] == "#RMTEMP#26C#"

    kb = parse_rowset_xml(build_keybox_push("2403", "SERVICE", "1234567890", "王小美", "1",
                                            vendor_code="81"))
    assert kb[0]["REVE-CODE"] == reve_keybox("81") == "0300814390"
    assert REVE_KEYBOX == "0300TT4390"               # 常數為 TT 樣板(同 REVE_ROOM_STA 慣例)
    assert kb[0]["CARD_TYP"] == "SERVICE" and kb[0]["CARD_UID"] == "1234567890"
    assert kb[0]["ACTION_STA"] == "1" and "ACTION_COD" not in kb[0]   # B5 訊息無 ACTION_COD


def test_mock_route_clean_updates_bit9_and_return_clean_sta():
    """RC2:CLEAN 推送 → 位元 9 更新 + A10 CLEAN_STA 推導鏈(3=待巡房→S)。"""
    c = _client()
    r = c.post("/third-party/import-sync-files",
               json=_import_body(build_clean_push("2701", "3")))
    assert r.status_code == 200
    item = r.get_json()[0]
    assert item["procStatus"] is True
    rows = parse_rowset_xml(item["responseBody"])
    assert rows[0]["RETN-CODE"] == "0000"
    assert rows[0]["RETN-CODE-DESC"] == "Transaction done successfully."   # 單值 action 非 Set 類
    bits = mock_roomcontrol_state["2701"]["status_bits"]
    assert len(bits) == 16 and bits[8] == "3"
    # 位元 9 推導鏈:A10 RETURN 的 CLEAN_STA
    r2 = c.post("/third-party/import-sync-files", json=_import_body(build_return_query()))
    by_room = {row["ROOM_NOS"]: row for row in parse_rowset_xml(r2.get_json()[0]["responseBody"])}
    assert by_room["2701"]["CLEAN_STA"] == "S"


def test_mock_route_rmtemp_updates_temperature():
    """RC2:RMTEMP 推送 → 室溫落庫 + 回應 "1112 Set"(Set 類)。"""
    c = _client()
    r = c.post("/third-party/import-sync-files",
               json=_import_body(build_rmtemp_push("2702", "26C")))
    assert r.status_code == 200
    item = r.get_json()[0]
    assert item["procStatus"] is True
    rows = parse_rowset_xml(item["responseBody"])
    assert rows[0]["RETN-CODE"] == "0000"
    assert "2702 Set #RMTEMP#26C#" in rows[0]["RETN-CODE-DESC"]
    assert mock_roomcontrol_state["2702"]["temperature"] == "26C"
    assert mock_roomcontrol_state["2702"]["api"] == "RCU"         # sa11:RMTEMP 附 api 值 RCU


def test_mock_route_keybox_updates_bit2():
    """RC2:B5 KeyBox 插卡 → 位元 2 更新 + 卡片資訊落庫;回應無 ACTION_COD(sa10 B5 樣本)。"""
    c = _client()
    r = c.post("/third-party/import-sync-files",
               json=_import_body(build_keybox_push("2703", "SERVICE", "ABC123", "王小美", "1")))
    assert r.status_code == 200
    item = r.get_json()[0]
    assert item["procStatus"] is True
    rows = parse_rowset_xml(item["responseBody"])
    assert rows[0]["SEND-CODE"] == "0300TT4390"
    assert rows[0]["RETN-CODE"] == "0000"
    assert "ACTION_COD" not in rows[0]            # B5 回應契約無 ACTION_COD 欄位
    st = mock_roomcontrol_state["2703"]
    assert st["status_bits"][1] == "1"            # 位元 2 Keybox=插卡
    assert st["keybox"]["card_typ"] == "SERVICE" and st["keybox"]["card_uid"] == "ABC123"


def test_mock_route_unknown_action_retn9999():
    """RC2 負面:未知 ACTION_COD → procStatus=false + RETN-CODE 9999。"""
    c = _client()
    xml = build_rowset_xml({"REVE-CODE": REVE_ROOM_STA, "ROOM_NOS": "2403",
                            "ACTION_COD": "NOSUCH", "ACTION_STA": "1",
                            "ACTION_DAT": "2026/09/04 12:00:00"})
    r = c.post("/third-party/import-sync-files", json=_import_body(xml))
    assert r.status_code == 200
    item = r.get_json()[0]
    assert item["procStatus"] is False
    rows = parse_rowset_xml(item["responseBody"])
    assert rows[0]["RETN-CODE"] == "9999"
    assert "Unknown ACTION_COD" in rows[0]["RETN-CODE-DESC"]


def test_mock_route_missing_required_fields():
    """RC2 負面:ROOM_INF 缺 ROOM_NOS → 417;B5 缺 CARD_TYP / ACTION_STA → 417。"""
    c = _client()
    r = c.post("/third-party/import-sync-files",
               json=_import_body(build_rowset_xml({"REVE-CODE": REVE_ROOM_INF,
                                                   "ACTION_COD": "ROOM_INF",
                                                   "ACTION_DAT": "2026/09/04 12:00:00"})))
    assert r.status_code == 417 and r.get_json()["code"] == "417"
    r2 = c.post("/third-party/import-sync-files",
                json=_import_body(build_keybox_push("2704", "", "X", "Y", "1")))
    assert r2.status_code == 417
    r3 = c.post("/third-party/import-sync-files",
                json=_import_body(build_rowset_xml({"REVE-CODE": "0300TT4390",
                                                    "ROOM_NOS": "2705", "CARD_TYP": "GUEST",
                                                    "ACTION_DAT": "2026/09/04 12:00:00"})))
    assert r3.status_code == 417


def test_registry_roomcontrol_module():
    by_mod = registry.by_module()
    assert "roomcontrol" in by_mod
    cases = {s.id: s for s in by_mod["roomcontrol"]}
    # RC0 三案 + RC2 六案 + RC2.5 三案,雙廠商:MINXON(81) / CHAOFENG(86)
    expected = {f"rc_{v}_{a}" for v in ("minxon", "chaofeng")
                for a in ("room_sta_push", "room_inf", "return",
                          "clean", "rmtemp", "keybox",
                          "bad_xml", "unknown_action", "missing_room_nos",
                          "room_not_found", "internal_error", "room_sta_offline")}
    # RC4a:IPTV 雲朗(70)住客顯示名稱參數三案
    expected |= {"rc_iptv_display_name", "rc_iptv_display_name_default",
                 "rc_iptv_display_name_empty_custom"}
    assert expected == set(cases)
    assert all(s.implemented for s in by_mod["roomcontrol"])
    assert {s.vendor for s in by_mod["roomcontrol"]} == {"MINXON", "CHAOFENG", "IPTV"}
    push = cases["rc_minxon_room_sta_push"]
    assert {sp.key for sp in push.params} == {"room_no", "status_bits", "third_party_code"}
    # third_party_code 預設帶實際代碼(MINXON=81、CHAOFENG=86),仍可覆寫
    tp_default = {sp.key: sp.default for sp in push.params if sp.key == "third_party_code"}
    assert tp_default["third_party_code"] == "81"
    tp_cf = [sp for sp in cases["rc_chaofeng_room_inf"].params if sp.key == "third_party_code"][0]
    assert tp_cf.default == "86"


def test_vendor_codes_embedded_in_reve():
    """REVE-CODE 依廠商代號組出:0300+<2碼>+動作碼。"""
    from server.roomcontrol.vendors.vendor_A7_XML import (
        reve_room_sta, reve_room_inf, reve_return, build_return_query,
    )
    assert reve_room_inf("81") == "0300811090"
    assert reve_room_sta("86") == "0300864190"
    assert reve_return("81") == "0300814290"
    assert "<REVE-CODE>0300814290</REVE-CODE>" in build_return_query(vendor_code="81")


def test_runner_assembles_xml_with_overrides():
    """離線(無 server)仍可驗證:覆寫貫穿 XML 組裝(step 在連線前即錄製 request_body)。"""
    run = engine.start_run(["rc_minxon_room_inf"], "LOCAL_OFFLINE",
                           overrides={"rc_minxon_room_inf": {"room_no": "2501"}})
    cr = run.cases[0]
    assert cr.resolved_params["room_no"] == "2501"
    body = cr.steps[0]["request_body"]
    assert body["thirdPartyCode"] == "81"
    xml_str = body["requestDataList"][0]["requestBody"]
    assert "<REVE-CODE>0300811090</REVE-CODE>" in xml_str
    assert "<ACTION_COD>ROOM_INF</ACTION_COD>" in xml_str
    assert "<ROOM_NOS>2501</ROOM_NOS>" in xml_str

    # push 案:位元串覆寫進 ACTION_COD(#...# 包裹);CHAOFENG 代碼嵌 REVE
    run2 = engine.start_run(["rc_chaofeng_room_sta_push"], "LOCAL_OFFLINE",
                            overrides={"rc_chaofeng_room_sta_push": {"status_bits": "010101011001"}})
    xml2 = run2.cases[0].steps[0]["request_body"]["requestDataList"][0]["requestBody"]
    assert "<REVE-CODE>0300864190</REVE-CODE>" in xml2
    assert "<ACTION_COD>#ROOM_STA#010101011001#</ACTION_COD>" in xml2
    assert "<ROOM_NOS>2403</ROOM_NOS>" in xml2     # 未覆寫欄位用預設

    # RC2:RMTEMP 溫度覆寫貫穿(#RMTEMP#28C#)
    run3 = engine.start_run(["rc_minxon_rmtemp"], "LOCAL_OFFLINE",
                            overrides={"rc_minxon_rmtemp": {"temperature": "28C"}})
    xml3 = run3.cases[0].steps[0]["request_body"]["requestDataList"][0]["requestBody"]
    assert "<REVE-CODE>0300814190</REVE-CODE>" in xml3
    assert "<ACTION_COD>#RMTEMP#28C#</ACTION_COD>" in xml3


def test_run_context_has_roomcontrol_urls():
    for env in ("LOCAL_OFFLINE", "LOCAL", "REAL_QA"):
        ctx = engine.build_run_context(env)
        assert ctx.urls["import_sync"].endswith("/third-party/import-sync-files")
        assert ctx.urls["roomcontrol_internal"].endswith("/roomcontrol/internal/state")


# ---- RC2.5(2026-11-03,sa11):PBX_DT 解碼 / F 斷線 / 房間層錯誤 / 自助端點 ------------

def test_decode_status_bits_field_polarity():
    """16 位房況字串 → PBX_DT 欄位極性(sa11 對照表逐一驗證)。"""
    from server.roomcontrol.vendors.vendor_A7_XML import decode_status_bits
    # 樣本:位1插卡 位2插卡 位3冷氣開 位4電源開 位5鐵捲關 位6一氧化碳無動作
    #       位7防盜動作 位8緊急無動作 位9=2打掃中 位10勿擾無 位11房門關
    d = decode_status_bits("0111000120100000")
    assert d["KEY_HOUSE"] == "on" and d["KEY_BOX"] == "on"
    assert d["AC_STA"] == "on" and d["MAIN_POWER"] == "on"
    assert d["RSD"] == "off" and d["CO_ONE"] == "off"
    assert d["BG_ALARM"] == "on"                    # 0=動作 → on
    assert d["SOS"] == "off"                        # 1=無動作 → off
    assert d["RCU_ONLINE"] == "Y"
    assert d["CLEAN_ROOM"] == "2"                   # 直接帶入廠商值
    assert d["DND"] == "off" and d["DOOR_STA"] == "off"   # 1=門關 → off
    # 反向:防盜無動作(1)→off、緊急動作(0)→on
    d2 = decode_status_bits("0000001000000000")
    assert d2["BG_ALARM"] == "off" and d2["SOS"] == "on" and d2["RCU_ONLINE"] == "Y"


def test_mock_route_room_sta_offline_f_semantics():
    """F 斷線三連動(sa11 情境二):位8=F → SOS=off、RCU_ONLINE=N、CLEAN_ROOM 保舊值。"""
    c = _client()
    # 連線態:位9=2(打掃中)
    r1 = c.post("/third-party/import-sync-files",
                json=_import_body(build_room_sta_push("2701", "0111000120100000")))
    assert r1.get_json()[0]["procStatus"] is True
    st1 = mock_roomcontrol_state["2701"]
    assert st1["pbx_dt"]["RCU_ONLINE"] == "Y" and st1["pbx_dt"]["CLEAN_ROOM"] == "2"
    # 斷線態:位8=F、位9=4 —— CLEAN_ROOM 應保舊值 2(斷線略過位 9 更新)
    r2 = c.post("/third-party/import-sync-files",
                json=_import_body(build_room_sta_push("2701", "0101001F40100000")))
    assert r2.get_json()[0]["procStatus"] is True
    pbx = mock_roomcontrol_state["2701"]["pbx_dt"]
    assert pbx["RCU_ONLINE"] == "N" and pbx["SOS"] == "off"
    assert pbx["CLEAN_ROOM"] == "2"
    assert mock_roomcontrol_state["2701"]["status_bits"] == "0101001F40100000"  # 原始字串如實落庫
    assert mock_roomcontrol_state["2701"]["rmupd_dat"]              # sa11:RMUPD_DAT


def test_mock_route_room_level_errors():
    """RC2.5 負面:未知房號 → procStatus=false + RETN 9999;E 模擬房 → RETN 1001。"""
    c = _client()
    # ROOM_INF 查未登錄房號
    r = c.post("/third-party/import-sync-files", json=_import_body(build_room_inf_query("8888")))
    assert r.status_code == 200
    item = r.get_json()[0]
    assert item["procStatus"] is False
    rows = parse_rowset_xml(item["responseBody"])
    assert rows[0]["RETN-CODE"] == "9999" and rows[0]["RETN-CODE-DESC"] == "ROOM not found."
    assert "ROOM_NOS" not in rows[0] and "ACTION_DAT" not in rows[0]   # sa11 失敗樣本形狀
    # B4 推送未登錄房號 → 同 9999 信封,且不落庫
    r2 = c.post("/third-party/import-sync-files",
                json=_import_body(build_room_sta_push("8888", DEFAULT_STATUS_BITS)))
    item2 = r2.get_json()[0]
    assert item2["procStatus"] is False
    assert parse_rowset_xml(item2["responseBody"])[0]["RETN-CODE"] == "9999"
    assert "8888" not in mock_roomcontrol_state
    # E 模擬房 → RETN 1001(德安 DB 內部錯誤)
    r3 = c.post("/third-party/import-sync-files", json=_import_body(build_room_inf_query("9901")))
    item3 = r3.get_json()[0]
    assert item3["procStatus"] is False
    rows3 = parse_rowset_xml(item3["responseBody"])
    assert rows3[0]["RETN-CODE"] == "1001"
    assert rows3[0]["RETN-CODE-DESC"] == "處理第三方廠商傳送的資料時發生錯誤"


def test_mock_route_main_power_single_action_polarity():
    """sa11 極性差:第一種 MAIN_POWER ACTION_STA 0=on/1=off,與位元串位 4(1=開)相反。"""
    c = _client()
    xml = build_rowset_xml({"REVE-CODE": REVE_ROOM_STA, "ROOM_NOS": "2702",
                            "ACTION_COD": "MAIN_POWER", "ACTION_STA": "0",
                            "ACTION_DAT": "2026/11/03 12:00:00"})
    r = c.post("/third-party/import-sync-files", json=_import_body(xml))
    assert r.get_json()[0]["procStatus"] is True
    assert mock_roomcontrol_state["2702"]["pbx_dt"]["MAIN_POWER"] == "on"   # 0=on
    assert mock_roomcontrol_state["2702"]["status_bits"][3] == "1"          # 位4 反轉為 1(開)


def test_mock_route_return_reflects_room_mn_and_skips_error_room():
    """A10 RETURN 走房間主檔:R/S 如實回報;E 模擬房不入回報。"""
    c = _client()
    r = c.post("/third-party/import-sync-files", json=_import_body(build_return_query()))
    by_room = {row["ROOM_NOS"]: row for row in parse_rowset_xml(r.get_json()[0]["responseBody"])}
    assert by_room["2405"]["ROOM_STA"] == "R" and by_room["2406"]["ROOM_STA"] == "S"
    assert by_room["2403"]["ROOM_STA"] == "O"
    assert "9901" not in by_room


def test_internal_rooms_and_reset_endpoints():
    """沙盒自助:登錄房間主檔(動態房號)→ 可推送;reset 還原種子。"""
    c = _client()
    r = c.post("/roomcontrol/internal/rooms", json={"rooms": {"91234": "V"}})
    assert r.status_code == 200 and "91234" in r.get_json()["room_mn"]
    rp = c.post("/third-party/import-sync-files",
                json=_import_body(build_room_sta_push("91234", "010101011001")))
    assert rp.get_json()[0]["procStatus"] is True
    assert "91234 Set #ROOM_STA#010101011001#" in rp.get_json()[0]["responseBody"]
    # 非法 ROOM_STA → 400;缺 rooms → 400
    assert c.post("/roomcontrol/internal/rooms", json={"rooms": {"91235": "X"}}).status_code == 400
    assert c.post("/roomcontrol/internal/rooms", json={}).status_code == 400
    # reset:動態房消失、種子還原
    assert c.post("/roomcontrol/internal/reset").status_code == 200
    st = c.get("/roomcontrol/internal/state").get_json()
    assert "91234" not in st["room_mn"] and "91234" not in st["room_control_state"]
    assert st["room_mn"]["2403"] == "O" and st["room_mn"]["9901"] == "E"


# ---- RC4a(2026-11-04):IPTV 雲朗(70)sa11 住客顯示名稱參數 → CKI 出站姓名欄 ----

def test_resolve_display_name_param_table():
    """sa11 參數表逐項:六選項 + 預設值 + USER_DEFINED 空值如實傳送。"""
    from server.roomcontrol.routes import (
        resolve_display_name, DISPLAY_NAME_CHOICES, DEFAULT_DISPLAY_NAME,
    )
    guest = {"ALT_NAM": "王小明", "LAST_NAM": "王", "FIRST_NAM": "小明",
             "GROUP_NOS": "GP2026A"}
    assert DEFAULT_DISPLAY_NAME == "ALT_NAM"
    assert resolve_display_name({}, guest, "2407") == "王小明"              # 無參數 → 預設
    assert resolve_display_name({"guest_display_name": "ALT_NAM"}, guest, "2407") == "王小明"
    assert resolve_display_name({"guest_display_name": "LAST_NAM"}, guest, "2407") == "王"
    assert resolve_display_name({"guest_display_name": "FIRST_NAM"}, guest, "2407") == "小明"
    assert resolve_display_name({"guest_display_name": "ROOM_NOS"}, guest, "2407") == "2407"
    assert resolve_display_name({"guest_display_name": "GROUP_NOS"}, guest, "2407") == "GP2026A"
    assert resolve_display_name({"guest_display_name": "USER_DEFINED",
                                 "user_defined_display_name": "貴賓 王小明"}, guest, "2407") == "貴賓 王小明"
    # sa11 明文:USER_DEFINED 不論有無值皆依參數內容傳送 → 空值 = 廠商收無資料
    assert resolve_display_name({"guest_display_name": "USER_DEFINED"}, guest, "2407") == ""
    assert resolve_display_name({"guest_display_name": "USER_DEFINED",
                                 "user_defined_display_name": ""}, guest, "2407") == ""
    # 非合法選項 → 回預設(沙盒不炸,對齊「讀取無資料依預設值」)
    assert resolve_display_name({"guest_display_name": "NOSUCH"}, guest, "2407") == "王小明"
    assert set(DISPLAY_NAME_CHOICES) == {"GROUP_NOS", "ROOM_NOS", "LAST_NAM",
                                         "FIRST_NAM", "ALT_NAM", "USER_DEFINED"}


def test_internal_thirdparty_conf_endpoint():
    """THIRDPARTY_DT_CONF 端點:設定/讀取/清除/非法選項 400。"""
    c = _client()
    r = c.post("/roomcontrol/internal/thirdparty-conf",
               json={"third_party_code": "70",
                     "params": {"guest_display_name": "USER_DEFINED",
                                "user_defined_display_name": "貴賓"}})
    assert r.status_code == 200 and r.get_json()["params"]["guest_display_name"] == "USER_DEFINED"
    assert c.get("/roomcontrol/internal/thirdparty-conf").get_json()["thirdparty_dt_conf"]["70"]["user_defined_display_name"] == "貴賓"
    # 非法選項 → 400
    rb = c.post("/roomcontrol/internal/thirdparty-conf",
                json={"third_party_code": "70", "params": {"guest_display_name": "X"}})
    assert rb.status_code == 400
    # 值 None = 清除 → 回到無參數設定
    rc = c.post("/roomcontrol/internal/thirdparty-conf",
                json={"third_party_code": "70", "params": {"guest_display_name": None}})
    assert rc.status_code == 200
    assert "guest_display_name" not in rc.get_json()["params"]
    # 缺欄 → 400
    assert c.post("/roomcontrol/internal/thirdparty-conf", json={}).status_code == 400


def test_internal_cki_trigger_and_display_name():
    """CKI 出站:無參數 → 預設 ALT_NAM;各選項解析;USER_DEFINED 空值送無資料。"""
    c = _client()
    # 無參數(種子 conf 空)→ 姓名 = ALT_NAM;REVE 帶廠商代號 70
    r = c.post("/roomcontrol/internal/cki", json={"room_no": "2407", "third_party_code": "70"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["procStatus"] is True and body["display_name"] == "王小明"
    rows = parse_rowset_xml(body["responseBody"])
    assert rows[0]["REVE-CODE"] == "0300901070" and rows[0]["ACTION_COD"] == "CKI"
    assert rows[0]["ALT_NAM"] == "王小明" and rows[0]["ROOM_NOS"] == "2407"
    assert rows[0]["INFO_ISGROUP"] == "Y" and rows[0]["INFO_REMARK"] == "雲朗年度貴賓團"
    # sa10 A1 無 GROUP_NOS 標籤——訂房名稱/團號僅作姓名欄來源(參數解析,上方已測)
    assert mock_room_mn["2407"] == "O"                    # C/I → 房間主檔轉住人
    # 各選項
    for choice, expect in (("LAST_NAM", "王"), ("FIRST_NAM", "小明"),
                           ("ROOM_NOS", "2407"), ("GROUP_NOS", "GP2026A")):
        c.post("/roomcontrol/internal/thirdparty-conf",
               json={"third_party_code": "70", "params": {"guest_display_name": choice}})
        b = c.post("/roomcontrol/internal/cki",
                   json={"room_no": "2407", "third_party_code": "70"}).get_json()
        assert b["display_name"] == expect, choice
    # USER_DEFINED 有值/空值
    c.post("/roomcontrol/internal/thirdparty-conf",
           json={"third_party_code": "70", "params": {"guest_display_name": "USER_DEFINED",
                                                      "user_defined_display_name": "總統套房貴賓"}})
    b2 = c.post("/roomcontrol/internal/cki",
                json={"room_no": "2407", "third_party_code": "70"}).get_json()
    assert b2["display_name"] == "總統套房貴賓"
    c.post("/roomcontrol/internal/thirdparty-conf",
           json={"third_party_code": "70", "params": {"user_defined_display_name": None}})
    b3 = c.post("/roomcontrol/internal/cki",
                json={"room_no": "2407", "third_party_code": "70"}).get_json()
    assert b3["display_name"] == ""                        # 空值 → 廠商收無資料
    assert parse_rowset_xml(b3["responseBody"])[0]["ALT_NAM"] == ""
    # 負面:未知房號 9999 / E 房 1001 / 無住客資料
    rn = c.post("/roomcontrol/internal/cki", json={"room_no": "8888", "third_party_code": "70"})
    assert rn.status_code == 404 and rn.get_json()["code"] == "9999"
    re_ = c.post("/roomcontrol/internal/cki", json={"room_no": "9901", "third_party_code": "70"})
    assert re_.status_code == 500 and re_.get_json()["code"] == "1001"
    rg = c.post("/roomcontrol/internal/cki", json={"room_no": "2404", "third_party_code": "70"})
    assert rg.status_code == 400
    # reset 還原:conf 清空、2407 回 V
    c.post("/roomcontrol/internal/reset")
    st = c.get("/roomcontrol/internal/state").get_json()
    assert st["thirdparty_dt_conf"] == {} and st["room_mn"]["2407"] == "V"


def test_params_meta_carries_choices():
    """ParamSpec.choices → /scenarios 帶出(UI 下拉驅動;單選選項)。"""
    from orchestrator.registry import params_meta, registry as reg
    sc = reg.get("rc_iptv_display_name")
    metas = {m["key"]: m for m in params_meta(sc)}
    assert metas["guest_display_name"]["choices"] == [
        "GROUP_NOS", "ROOM_NOS", "LAST_NAM", "FIRST_NAM", "ALT_NAM", "USER_DEFINED"]
    assert metas["guest_display_name"]["default"] == "ALT_NAM"
    assert metas["room_no"]["choices"] == []               # 自由輸入參數不帶選項
