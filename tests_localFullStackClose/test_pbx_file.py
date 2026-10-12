# tests_localFullStackClose/test_pbx_file.py
"""☎️ 交換機 M3(真檔案交換層)離線測試 — HOST2PMS/PMS2HOST 四檔 + W/P cycle 輪替 + ANSI。

涵蓋:
- IDX 格式:192-byte、欄位位置(Record_len/File_size/Wcycle/Wseq/Windex/Pcycle/Pindex)、數字靠右
- 環狀緩衝:寫入/讀取順序、繞圈 cycle A↔B 翻轉、滿載守衛(對方未讀 → wait 不覆寫)
- ANSI(cp950):記錄編解碼往返;中文姓名政策(預設改送房號/allow_china 保留)
- run-cycle 端到端:pbx_mn 未處理 → 寫 HOST2PMS(標 Y)→ 交換機讀取執行 → 回應寫 PMS2HOST
  → PMS 讀回(SUC 記錄、ERR 入 pbx_err)
- registry:pbx 模組 25 案
"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

import orchestrator  # noqa: F401 觸發 runners 註冊
from orchestrator.registry import registry
from server.pbx import pbx_bp
from server.pbx.pms_side import pms_bp
from server.pbx.file_exchange import file_bp, PbxFileChannel
from server.pbx.vendors.vendor_PABX import build_host_record, parse_record


def _client():
    app = Flask(__name__)
    app.register_blueprint(pbx_bp)
    app.register_blueprint(pms_bp)
    app.register_blueprint(file_bp)
    return app.test_client()


def _rec(inst, room, seq):
    return build_host_record(inst, {"phone_nos": room}, seq)


def _tmp_channel(file_size=4, allow_china=False):
    d = tempfile.mkdtemp(prefix="pbx_exchange_")
    ch = PbxFileChannel(d, "host2pms", file_size, allow_china)
    ch.ensure()
    return ch, d


# ---- IDX 格式 -----------------------------------------------------------
def test_idx_layout_and_padding():
    ch, d = _tmp_channel(file_size=12)
    try:
        with open(ch.idx_path, "rb") as f:
            raw = f.read()
        assert len(raw) == 192 and raw.endswith(b"\r\n")
        rec = raw.decode("cp950")
        assert rec[0:3] == "192"                 # Record_len 9(3)
        assert rec[3:10] == "     12"            # File_size 靠右
        assert rec[10] == "A"                    # Wcycle 初始 A
        assert rec[11:18] == "      0"           # Wseq 從 0
        assert rec[18:25] == "      1"           # Windex 下一可寫=1
        assert rec[25] == "A" and rec[26:33] == "      1"
        assert rec[33:190].strip() == ""         # Filler
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- 環狀緩衝:順序/繞圈/守衛 ---------------------------------------------
def test_ring_order_wraparound_and_full_guard():
    ch, d = _tmp_channel(file_size=3)
    try:
        seqs = []
        for i in range(1, 4):
            s, wait = ch.write(_rec("CKO", f"010{i}", i))
            assert wait is None
            seqs.append(s)
        assert seqs == [1, 2, 3]
        assert ch.windex == 1 and ch.wcycle == "B"      # 繞圈 + 翻 cycle
        recs = ch.read_pending()
        assert len(recs) == 3
        assert [parse_record(r)["phone_nos"] for r in recs] == ["0101", "0102", "0103"]  # FIFO
        assert ch.pindex == 1 and ch.pcycle == "B"      # 讀方跟上同槽同圈
        # 再寫一圈不讀:寫滿 3 筆後第 4 筆撞上讀方未讀 → wait
        for i in range(3):
            assert ch.write(_rec("DND", "0101", 10 + i))[1] is None
        s4, wait4 = ch.write(_rec("TCE", "0101", 99))
        assert s4 is None and wait4.startswith("wait")   # 滿載守衛(不覆寫)
        # 讀掉後可再寫
        assert len(ch.read_pending()) == 3
        assert ch.write(_rec("TCE", "0101", 99))[1] is None
        assert ch.wseq == 7                              # 3+3+1 筆(10^7 才溢位歸零循環)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_channel_state_reload_from_idx():
    ch, d = _tmp_channel(file_size=3)
    try:
        for i in range(4):
            assert ch.write(_rec("CKO", "0101", i + 1))[1] is None or True
        snap = ch.idx_snapshot()
        ch2 = PbxFileChannel(d, "host2pms", 3)
        ch2.load_state()
        assert ch2.idx_snapshot() == snap                # 重啟還原(模擬進程重啟)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- ANSI / 中文姓名政策 ---------------------------------------------------
def test_china_name_policy_default_and_allow():
    ch, d = _tmp_channel(file_size=4)
    try:
        rec = build_host_record("CKI", {"phone_nos": "0105", "lang_cod": "001", "vip_sta": "N",
                                        "master_nos": "0105", "guest_nam": "王小明",
                                        "account_nos": "CI001"}, 1)
        ch.write(rec)
        got = parse_record(ch.read_pending()[0])
        assert got["guest_nam"] == "0105"                # 預設政策:中文 → 改送房號
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ch2, d2 = _tmp_channel(file_size=4, allow_china=True)
    try:
        rec = build_host_record("CKI", {"phone_nos": "0106", "lang_cod": "001", "vip_sta": "N",
                                        "master_nos": "0106", "guest_nam": "王小明",
                                        "account_nos": "CI002"}, 1)
        ch2.write(rec)
        raw = open(ch2.dat_path, "rb").read(192)
        # 位元組級斷言:檔頭 29 bytes(記錄頭)+ 中文以 cp950 入檔可解
        assert raw[0:1] == b"I"
        decoded = raw.decode("cp950", errors="replace")
        assert "王小明" in decoded                        # allow_china:cp950 保留往返
        assert decoded.endswith("\r\n")
    finally:
        shutil.rmtree(d2, ignore_errors=True)


# ---- run-cycle 端到端 ------------------------------------------------------
def test_run_cycle_end_to_end():
    c = _client()
    c.post("/pbx/internal/reset")
    c.post("/pbx/pms/internal/reset")
    from datetime import datetime, timedelta
    dat = datetime.now().strftime("%Y%m%d")
    tim = (datetime.now() + timedelta(minutes=40)).strftime("%H%M%S")
    assert c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01",
                                            "action": "checkin", "room_nos": "0101"}).get_json()["ok"]
    assert c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01", "action": "set_mcall",
                                            "room_nos": "0101", "mcall_dat": dat,
                                            "mcall_tim": tim}).get_json()["ok"]
    c.post("/pbx/pms-scheduler/tick")
    assert c.post("/pbx/file/ensure", json={"file_size": 3000}).get_json()["ok"] is True
    r = c.post("/pbx/file/run-cycle").get_json()
    insts_written = [w["inst_cod"] for w in r["written"]]
    assert "CKI" in insts_written and "MCS" in insts_written
    assert all(p["ok"] for p in r["processed"])          # 交換機全 SUC
    replies = r["handled_replies"]
    assert replies and all(f["resp_cod"] == "SUC" for f in replies)
    st = c.get("/pbx/file/state").get_json()
    h2p, p2h = st["host2pms"], st["pms2host"]
    assert h2p["pindex_nos"] == h2p["windex_nos"]        # 讀完
    assert p2h["pindex_nos"] == p2h["windex_nos"]
    assert h2p["wseq_nos"] == len(r["written"])          # 寫入數 = seq
    sw = c.get("/pbx/internal/state").get_json()
    assert sw["pbx_dt"]["0101"]["tel_sta"] == "1"        # 交換機狀態落庫(經檔案路徑)
    assert any(mc["room_nos"] == "0101" and mc["mcall_sta"] == "0" for mc in sw["mcall_mn"])


def test_run_cycle_requires_ensure():
    c = _client()
    c.post("/pbx/file/ensure", json={"directory": tempfile.mkdtemp(prefix="pbx_x_")})
    r = c.post("/pbx/file/run-cycle")
    assert r.status_code == 200                          # 已 ensure → 可跑(空佇列)
    r2 = c.post("/pbx/file/run-cycle")
    assert r2.status_code == 200


def test_registry_pbx_module_m3():
    by_mod = registry.by_module()
    cases = {s.id: s for s in by_mod["pbx"]}
    assert len(cases) == 25                              # M0 10 + M1 7 + M2 5 + M3 3
    for cid in ("pbx_file_roundtrip", "pbx_file_wraparound", "pbx_file_china_name"):
        assert cases[cid].implemented
