# tests_localFullStackClose/test_pbx_ui.py
"""☎️ 交換機 M1(PMS 側業務層)離線測試 — SD文件_PMS0210027 + 宏興SD 排程/刪除/各 API 規則。

涵蓋(mock PMS 動作端點 + 排程 tick + 雙側回讀):
- 晨喚全鏈:checkin→set_mcall(NOT_TRANS)→tick(五規則)→TRANS+MCS 下達交換機側
- 刪除已傳送晨喚:直接 insert pbx_mn 下達 MCS D(不走排程);未傳送→僅 update D
- 退房連動:未傳送晨喚→D、pbx_dt 清空、CKO 下達
- 換房重送:mcall 改綁新房+NOT_TRANS、tick 後新房 TRANS
- 排程邊界:過時未傳→SKIP;同房同時段 sta=0 不重複入(宏興SD 1.1.1)
- 負面:空房開電話/設晨喚拒絕(1.1.4.1)、取消已過時晨喚拒絕
- registry:pbx 模組 17 案(M0 PABX 10 + M1 PMS_UI 7)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

from flask import Flask

import orchestrator  # 觸發 runners 註冊
from orchestrator.registry import registry
from orchestrator import engine
from server.pbx import pbx_bp
from server.pbx.pms_side import pms_bp
from server.pbx.routes import mock_pbx_dt, mock_pbx_mcall
from server.pbx.pms_side import mock_pms_mcall_mn, mock_pms_pbx_mn


def _client():
    app = Flask(__name__)
    app.register_blueprint(pbx_bp)
    app.register_blueprint(pms_bp)
    return app.test_client()


def _act(c, action, **fields):
    body = {"athenaId": "25", "hotelCode": "01", "action": action}
    body.update(fields)
    return c.post("/pbx/pms-actions", json=body).get_json()


def _tick(c):
    return c.post("/pbx/pms-scheduler/tick").get_json()


def _pms_state(c):
    return c.get("/pbx/pms/internal/state").get_json()


def _sw_state(c):
    return c.get("/pbx/internal/state").get_json()


def _future(offset_min=40):
    return (datetime.now() + timedelta(minutes=offset_min)).strftime("%Y%m%d"), \
           (datetime.now() + timedelta(minutes=offset_min)).strftime("%H%M%S")


def _past(offset_min=10):
    return datetime.now().strftime("%Y%m%d"), \
           (datetime.now() - timedelta(minutes=offset_min)).strftime("%H%M%S")


def _reset(c):
    c.post("/pbx/internal/reset")
    c.post("/pbx/pms/internal/reset")


def _find(state, room, dat, tim):
    for mc in state.get("mcall_mn") or []:
        if (mc.get("room_nos"), mc.get("mcall_dat"), mc.get("mcall_tim")) == (room, dat, tim):
            return mc
    return None


def test_full_chain_set_mcall():
    c = _client()
    _reset(c)
    dat, tim = _future()
    assert _act(c, "checkin", room_nos="0101")["ok"] is True
    assert _act(c, "set_mcall", room_nos="0101", mcall_dat=dat, mcall_tim=tim)["ok"] is True
    # 設定後、排程前:mcall_mn = 0/NOT_TRANS(未入 pbx_mn)
    st = _pms_state(c)
    mc = _find(st, "0101", dat, tim)
    assert mc["mcall_sta"] == "0" and mc["trans_pbx_sta"] == "NOT_TRANS"
    tick = _tick(c)
    assert tick["sent"] and tick["sent"][0]["inst_cod"] == "MCS"
    st2 = _pms_state(c)
    mc2 = _find(st2, "0101", dat, tim)
    assert mc2["trans_pbx_sta"] == "TRANS" and mc2["mcall_sta"] == "0"
    insts = [e["inst_cod"] for e in st2["pbx_mn_tail"]]
    assert "CKI" in insts and insts[-1] == "MCS"
    # 交換機側(經 in-process 下達)已落庫:電話開 + 晨喚 set
    sw = _sw_state(c)
    assert sw["pbx_dt"]["0101"]["tel_sta"] == "1"
    assert _find(sw, "0101", dat, tim)["mcall_sta"] == "0"


def test_del_after_trans_sends_mcs_d_directly():
    c = _client()
    _reset(c)
    dat, tim = _future()
    _act(c, "checkin", room_nos="0102")
    _act(c, "set_mcall", room_nos="0102", mcall_dat=dat, mcall_tim=tim)
    _tick(c)
    r = _act(c, "del_mcall", room_nos="0102", mcall_dat=dat, mcall_tim=tim)
    assert r["ok"] is True
    # PMS 側 mcall_sta=D;pbx_mn 多一筆 MCS(直接下達,不經排程)
    mc = _find(_pms_state(c), "0102", dat, tim)
    assert mc["mcall_sta"] == "D"
    tail = _pms_state(c)["pbx_mn_tail"]
    assert tail[-1]["inst_cod"] == "MCS"
    # 交換機側同筆已收 MCS D
    assert _find(_sw_state(c), "0102", dat, tim)["mcall_sta"] == "D"


def test_checkout_cancels_pending_mcall():
    c = _client()
    _reset(c)
    dat, tim = _future()
    _act(c, "checkin", room_nos="0103")
    _act(c, "set_mcall", room_nos="0103", mcall_dat=dat, mcall_tim=tim)
    r = _act(c, "checkout", room_nos="0103")            # 不 tick:未傳送晨喚的處置
    assert r["ok"] is True
    mc = _find(_pms_state(c), "0103", dat, tim)
    assert mc["mcall_sta"] == "D" and mc["trans_pbx_sta"] == "NOT_TRANS"
    st = _pms_state(c)
    assert st["pbx_dt"]["0103"]["tel_sta"] == "0" and st["room_mn"]["0103"]["room_sta"] == "V"
    assert _sw_state(c)["pbx_dt"]["0103"]["tel_sta"] == "0"   # CKO 已下達交換機


def test_room_change_rebinds_and_resends():
    c = _client()
    _reset(c)
    dat, tim = _future()
    _act(c, "checkin", room_nos="0104")
    _act(c, "set_mcall", room_nos="0104", mcall_dat=dat, mcall_tim=tim)
    _tick(c)
    r = _act(c, "room_change", room_nos="0104", new_room_nos="0105")
    assert r["ok"] is True
    # 換房後:晨喚改綁 0105 + NOT_TRANS(重送);舊房無晨喚
    mc = _find(_pms_state(c), "0105", dat, tim)
    assert mc and mc["trans_pbx_sta"] == "NOT_TRANS"
    assert _find(_pms_state(c), "0104", dat, tim) is None
    _tick(c)
    assert _find(_pms_state(c), "0105", dat, tim)["trans_pbx_sta"] == "TRANS"
    assert _find(_sw_state(c), "0105", dat, tim)        # 交換機側新房已收到


def test_scheduler_expire_skip_and_dedupe():
    c = _client()
    _reset(c)
    dat, tim = _past()                                   # 過時晨喚
    _act(c, "checkin", room_nos="0106")
    assert _act(c, "set_mcall", room_nos="0106", mcall_dat=dat, mcall_tim=tim)["ok"] is True
    # 重複設定同房同時段 → 拒絕(宏興SD 1.1.1:不重複入)
    dup = _act(c, "set_mcall", room_nos="0106", mcall_dat=dat, mcall_tim=tim)
    assert dup["ok"] is False and "不重複" in dup["message"]
    tick = _tick(c)
    assert tick["sent"] == [] and tick["skipped"]        # 過時 → SKIP,不下達
    assert _find(_pms_state(c), "0106", dat, tim)["trans_pbx_sta"] == "SKIP"


def test_negative_actions_denied():
    c = _client()
    _reset(c)
    # 空房開電話/設晨喚 → 拒絕(宏興SD 1.1.4.1;前置先撞「無住人」)
    r1 = _act(c, "open_tel", room_nos="0107")
    assert r1["ok"] is False and "無住人" in r1["message"]
    r2 = _act(c, "set_mcall", room_nos="0107", mcall_dat="20261013", mcall_tim="070000")
    assert r2["ok"] is False and "無住人" in r2["message"]
    # 有住人但電話關 → 設晨喚被「電話未打開」攔(1.1.4.1:有開電話才可設 mcall)
    _act(c, "checkin", room_nos="0107")
    _act(c, "close_tel", room_nos="0107")
    r2b = _act(c, "set_mcall", room_nos="0107", mcall_dat="20261013", mcall_tim="070000")
    assert r2b["ok"] is False and "電話未打開" in r2b["message"]
    # 取消已過時晨喚 → 拒絕(只有時間已過不能取消)
    dat, tim = _past()
    _act(c, "checkin", room_nos="0108")
    _act(c, "set_mcall", room_nos="0108", mcall_dat=dat, mcall_tim=tim)
    r3 = _act(c, "del_mcall", room_nos="0108", mcall_dat=dat, mcall_tim=tim)
    assert r3["ok"] is False and "已過" in r3["message"]
    # 未知房號/未知動作/缺欄位 → 400
    assert c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01",
                                            "action": "checkin", "room_nos": "9999"}).status_code == 400
    assert c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01",
                                            "action": "nope", "room_nos": "0101"}).status_code == 400
    assert c.post("/pbx/pms-actions", json={"athenaId": "25", "hotelCode": "01",
                                            "action": "checkin"}).status_code == 400


def test_registry_pbx_module_m1():
    by_mod = registry.by_module()
    cases = {s.id: s for s in by_mod["pbx"]}
    assert len(cases) == 17
    assert sum(1 for s in cases.values() if s.vendor == "PABX") == 10
    assert sum(1 for s in cases.values() if s.vendor == "PMS_UI") == 7
    assert all(s.implemented for s in cases.values())
    ui = cases["pbx_ui_set_mcall_full_flow"]
    assert {sp.key for sp in ui.params} == {"room_no", "mcall_dat", "mcall_tim"}
    # 動態預設貫穿
    ctx = engine.build_run_context("LOCAL_OFFLINE")
    defaults = registry.resolve_defaults("pbx_ui_set_mcall_full_flow", ctx)
    assert defaults["mcall_dat"] == datetime.now().strftime("%Y%m%d")


def test_run_context_has_pms_side_urls():
    for env in ("LOCAL_OFFLINE", "LOCAL", "REAL_QA"):
        ctx = engine.build_run_context(env)
        assert ctx.urls["pbx_pms_actions"].endswith("/pbx/pms-actions")
        assert ctx.urls["pbx_pms_tick"].endswith("/pbx/pms-scheduler/tick")
        assert ctx.urls["pbx_pms_internal"].endswith("/pbx/pms/internal/state")


def test_runner_ui_assembles_and_real_skips():
    """離線:步驟錄製含頁面動作 body;REAL 環境一律 SKIP。"""
    run = engine.start_run(["pbx_ui_set_mcall_full_flow"], "LOCAL_OFFLINE",
                           overrides={"pbx_ui_set_mcall_full_flow": {"room_no": "0106"}})
    cr = run.cases[0]
    assert cr.resolved_params["room_no"] == "0106"
    actions = [s["request_body"]["action"] for s in cr.steps if "action" in (s.get("request_body") or {})]
    assert actions[:2] == ["checkin", "set_mcall"]      # 前兩步為入住+設定
    run2 = engine.start_run(["pbx_ui_set_mcall_full_flow"], "REAL_QA")
    assert run2.cases[0].status == "SKIP" and run2.cases[0].error_category == "REAL_NOT_SUPPORTED"
