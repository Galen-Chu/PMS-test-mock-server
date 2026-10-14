# tests_localFullStackClose/test_case_logs.py
"""📜 結果頁「Server/Client Log 分離顯示」離線測試(雙端 Log 支撐層)。

涵蓋:
- case_logs 緩衝:begin/append/take 隔離(take 後清鍵不留殘留)
- Server 側攔截:CaseServerLogHandler 依 X-Sandbox-Case-Id header 收進對應案例;
  無 header 的請求不收單;安裝冪等
- Client 側錄製:execute_for_ctx 每筆交易 → /← /✖ 三型行;LOCAL 模式帶案例
  header 出站、REAL 模式不帶
- 端到端(離線):POST /runs(LOCAL_OFFLINE)→ CaseResult.client_log 含
  案例開始/結束框線與交易行、server_log 序列化欄位存在
"""
import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, Flask, jsonify

import orchestrator  # noqa: F401 觸發 runners 註冊 + api 安裝攔截 handler
from orchestrator import case_logs
from orchestrator.api import orchestrator_bp
from orchestrator.models import CaseResult, CASE_PASS
from hardware.simulate_speaker import execute_for_ctx


# ---- 緩衝隔離 ------------------------------------------------------------
def test_case_logs_buffer_isolation():
    case_logs.begin_case("k1")
    case_logs.begin_case("k2")
    case_logs.append_server_line("k1", "line-a")
    case_logs.append_server_line("k2", "line-b")
    case_logs.append_server_line("k1", "line-c")
    assert case_logs.take_server_log("k1") == ["line-a", "line-c"]
    assert case_logs.take_server_log("k2") == ["line-b"]
    assert case_logs.take_server_log("k1") == []            # take 後清空
    assert case_logs.take_server_log("never-begun") == []   # 未知鍵不爆


# ---- Server 側攔截:header 關聯 + 無 header 不收 + 冪等安裝 ---------------
def _capture_app():
    bp = Blueprint("log_probe", __name__)

    @bp.route("/probe", methods=["POST"])
    def probe():
        case_logs_log = __import__("logging").getLogger("ParkingSandbox")
        case_logs_log.info("🎛️ 收到探測請求")
        return jsonify({"ok": True})

    app = Flask(__name__)
    app.register_blueprint(orchestrator_bp)   # before_app_request 鉤子 + handler 安裝
    app.register_blueprint(bp)
    return app.test_client()


def test_server_log_handler_captures_by_case_header():
    c = _capture_app()
    case_logs.begin_case("probe-key")
    r = c.post("/probe", headers={case_logs.CASE_HEADER: "probe-key"})
    assert r.status_code == 200
    lines = case_logs.take_server_log("probe-key")
    assert lines and any("收到探測請求" in ln and "ParkingSandbox" in ln for ln in lines)


def test_server_log_handler_ignores_requests_without_header():
    c = _capture_app()
    case_logs.begin_case("no-header-key")
    c.post("/probe")                                   # 未帶案例 header → 不收
    assert case_logs.take_server_log("no-header-key") == []


def test_install_server_log_capture_idempotent():
    import logging
    before = len(logging.getLogger().handlers)
    case_logs.install_server_log_capture()             # api.py import 已裝過 → 不重複
    case_logs.install_server_log_capture()
    assert len(logging.getLogger().handlers) == before


# ---- Client 側錄製:execute_for_ctx 行型 + header 注入規則 ------------------
def _fake_ctx(**kw):
    ctx = types.SimpleNamespace(
        headers={"Authorization": "tok"}, params=None, recorder=[], client_log=[],
        current_case="run1:case1", use_real=False)
    for k, v in kw.items():
        setattr(ctx, k, v)
    return ctx


def test_client_log_lines_on_error_path():
    ctx = _fake_ctx()
    res, err = execute_for_ctx(ctx, "POST", "http://127.0.0.1:1/nowhere",
                               json_body={"x": 1})
    assert res is None and err                      # 連不上(本機拒絕埠)
    marks = [ln.split("] ", 1)[1].split(" ", 1)[0] for ln in ctx.client_log]
    assert marks == ["→", "✖"]                      # 出發 + 失敗
    assert "POST http://127.0.0.1:1/nowhere" in ctx.client_log[0]
    assert len(ctx.recorder) == 1 and ctx.recorder[0]["error"]
    # LOCAL 模式:案例 header 有注入到實際出站 headers(step 錄下的 request_headers)
    assert ctx.recorder[0]["request_headers"].get(case_logs.CASE_HEADER) == "run1:case1"


def test_client_log_header_not_sent_in_real_mode():
    ctx = _fake_ctx(use_real=True)
    execute_for_ctx(ctx, "POST", "http://127.0.0.1:1/nowhere")
    assert case_logs.CASE_HEADER not in ctx.recorder[0]["request_headers"]


def test_client_log_off_without_slot():
    ctx = _fake_ctx(client_log=None)                 # 無錄製槽(舊 ctx 相容)→ 不爆、不錄
    execute_for_ctx(ctx, "POST", "http://127.0.0.1:1/nowhere")
    assert ctx.client_log is None and len(ctx.recorder) == 1


# ---- 端到端(離線):/runs → CaseResult 雙端 log 落進結果 API ----------------
def test_engine_dual_log_via_runs_api():
    from orchestrator.registry import registry

    def _probe_runner(ctx):
        execute_for_ctx(ctx, "POST", "http://127.0.0.1:1/nope", json_body={"probe": 1})
        return CaseResult(case_id="logs_scratch_probe", run_id="", module="_logtest",
                          vendor="TEST", scenario_name="雙端Log探測(離線)",
                          endpoint="http://127.0.0.1:1/nope", status=CASE_PASS)

    registry.register("logs_scratch_probe", module="_logtest", vendor="TEST",
                      name="雙端Log探測(離線)", endpoint="http://127.0.0.1:1/nope",
                      runner=_probe_runner)

    app = Flask(__name__)
    app.register_blueprint(orchestrator_bp)
    c = app.test_client()
    r = c.post("/runs", json={"environment": "LOCAL_OFFLINE",
                              "scenario_ids": ["logs_scratch_probe"]})
    assert r.status_code == 202
    run_id = r.get_json()["run_id"]
    for _ in range(50):
        snap = c.get(f"/runs/{run_id}").get_json()
        if snap["status"] != "RUNNING":
            break
        time.sleep(0.1)
    assert snap["status"] == "DONE"
    results = c.get(f"/runs/{run_id}/results").get_json()
    assert len(results) == 1
    case = results[0]
    cl = case["client_log"]
    assert any("案例開始 logs_scratch_probe" in ln for ln in cl)      # START 框線
    assert any(ln.split("] ", 1)[1].startswith("→ POST") for ln in cl)  # 出發行
    assert any(ln.split("] ", 1)[1].startswith("✖") for ln in cl)      # 失敗行
    assert any("案例結束 logs_scratch_probe・PASS" in ln for ln in cl)  # END 框線
    assert case["server_log"] == []                                  # 離線無伺服器互動
