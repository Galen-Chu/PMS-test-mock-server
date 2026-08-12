# orchestrator/api.py
"""測試編排 API（對齊設計規格 §8）。

端點：
- GET  /environments         → 6 環境 + {id, desc, color, ready, pms_url}
- GET  /scenarios            → 案例清單（含 implemented 標記）
- POST /runs                 → 建立並執行一次測試（環境 ready=false → 409）
- GET  /runs/<run_id>        → Run 摘要
- GET  /runs/<run_id>/results→ 該 run 的 CaseResult[]

本藍圖為「編排層」，與被測系統的 3 個 blueprint（parking/amenity/keycard）正交。
"""
from flask import Blueprint, request, jsonify

import config
from .registry import registry
from . import engine

orchestrator_bp = Blueprint('orchestrator', __name__)


@orchestrator_bp.route('/environments', methods=['GET'])
def list_environments():
    out = []
    for env_id in config.ENV_UI_ROWS[0] + config.ENV_UI_ROWS[1]:
        cfg = config.ENV_MATRIX.get(env_id, {})
        meta = config.ENV_UI_META.get(env_id, {})
        out.append({
            "id": env_id,
            "desc": meta.get("desc", ""),
            "color": meta.get("color", "#9aa0ac"),
            "ready": bool(cfg.get("READY", False)),
            "pms_url": cfg.get("PMS_URL", ""),
        })
    return jsonify(out), 200


@orchestrator_bp.route('/scenarios', methods=['GET'])
def list_scenarios():
    out = []
    for module, scs in registry.by_module().items():
        out.append({
            "module": module,
            "scenarios": [
                {
                    "id": s.id, "vendor": s.vendor, "name": s.name,
                    "endpoint": s.endpoint, "implemented": s.implemented,
                }
                for s in scs
            ],
        })
    return jsonify(out), 200


@orchestrator_bp.route('/runs', methods=['POST'])
def create_run():
    body = request.get_json(silent=True) or {}
    environment = body.get("environment")
    scenario_ids = body.get("scenario_ids") or []

    if environment not in config.ENV_MATRIX:
        return jsonify({"error": "UNKNOWN_ENVIRONMENT", "env": environment}), 400
    if not config.ENV_MATRIX[environment].get("READY", False):
        # 對齊原型「尚未設定」提示：不只 UI 擋，API 也拒絕，避免漏擋誤打未設定環境
        return jsonify({"error": "ENV_NOT_READY", "env": environment}), 409
    if not scenario_ids:
        return jsonify({"error": "NO_SCENARIOS"}), 400

    run = engine.start_run_async(scenario_ids, environment)  # 背景執行；立即回 RUNNING
    return jsonify(_run_summary(run)), 202   # 202 Accepted：已受理、執行中


@orchestrator_bp.route('/runs/<run_id>', methods=['GET'])
def get_run(run_id):
    run = engine.snapshot_run(run_id)   # 序列化安全快照(背景執行緒持續 append 不會撞)
    if run is None:
        return jsonify({"error": "RUN_NOT_FOUND", "run_id": run_id}), 404
    return jsonify(_run_summary(run)), 200


@orchestrator_bp.route('/runs/<run_id>/results', methods=['GET'])
def get_run_results(run_id):
    run = engine.snapshot_run(run_id)
    if run is None:
        return jsonify({"error": "RUN_NOT_FOUND", "run_id": run_id}), 404
    return jsonify([_case_dict(c) for c in run.cases]), 200


# ---- 序列化輔助 --------------------------------------------------------
def _run_summary(run):
    return {
        "run_id": run.run_id,
        "triggered_at": run.triggered_at,
        "environment": run.environment,
        "status": run.status,
        "total_cases": run.total_cases,
        "passed": run.passed,
        "failed": run.failed,
        "duration_ms": run.duration_ms,
    }


def _case_dict(c):
    return {
        "case_id": c.case_id,
        "module": c.module,
        "vendor": c.vendor,
        "scenario_name": c.scenario_name,
        "endpoint": c.endpoint,
        "status": c.status,
        "duration_ms": c.duration_ms,
        "request_payload": c.request_payload,
        "response_payload": c.response_payload,
        "expected_payload": c.expected_payload,
        "diff": c.diff,
        "error_category": c.error_category,
    }
