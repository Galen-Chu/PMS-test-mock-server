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
from .registry import registry, params_meta
from . import engine
from .classify import remediation, first_failure
from .models import ParamSpec

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
    """三層結構:模組 → 廠商 → 案例(對齊原型,供前端畫廠商 chip)。

    參數化(設計 §3/§8):案例帶 ``params`` 詮釋資料驅動 UI 表單——動態預設求值展示
    + ``dynamic: true``;表單完全由本 API 驅動,未來廠商視角 UI 結構零改動。
    """
    _MODULE_LABEL = {"parking": "🚗 停車車辨", "amenity": "🦏 房務備品",
                     "keycard": "🔑 門禁製卡", "roomcontrol": "🌡️ 房控"}
    disp_ctx = engine.build_run_context("LOCAL_OFFLINE")  # 動態預設求值展示用（時間戳類不依環境）
    out = []
    for module, scs in registry.by_module().items():
        # 同模組的案例依 vendor 分組
        vendors_map = {}
        for s in scs:
            item = {
                "id": s.id, "name": s.name, "endpoint": s.endpoint, "implemented": s.implemented,
            }
            if s.params:
                item["params"] = params_meta(s, disp_ctx)
            vendors_map.setdefault(s.vendor, []).append(item)
        vendors = [{"id": v, "label": v, "scenarios": items} for v, items in vendors_map.items()]
        out.append({
            "module": module,
            "label": _MODULE_LABEL.get(module, module),
            "vendors": vendors,
        })
    return jsonify(out), 200


@orchestrator_bp.route('/runs', methods=['POST'])
def create_run():
    body = request.get_json(silent=True) or {}
    environment = body.get("environment")
    scenario_ids = body.get("scenario_ids") or []
    overrides = body.get("overrides") or {}

    if environment not in config.ENV_MATRIX:
        return jsonify({"error": "UNKNOWN_ENVIRONMENT", "env": environment}), 400
    if not config.ENV_MATRIX[environment].get("READY", False):
        # 對齊原型「尚未設定」提示：不只 UI 擋，API 也拒絕，避免漏擋誤打未設定環境
        return jsonify({"error": "ENV_NOT_READY", "env": environment}), 409
    if not scenario_ids:
        return jsonify({"error": "NO_SCENARIOS"}), 400

    clean, err = validate_overrides(overrides, scenario_ids)
    if err:
        return jsonify(err), 400

    run = engine.start_run_async(scenario_ids, environment, overrides=clean)  # 背景執行；立即回 RUNNING
    return jsonify(_run_summary(run)), 202   # 202 Accepted：已受理、執行中


# ---- overrides 驗證（設計 §4；純函式，離線單元測試直接測）----------------
_MAX_PARAM_LEN = 64


def validate_overrides(overrides, scenario_ids):
    """校驗 POST /runs 的 overrides：未知案例、未知參數鍵、型別轉換失敗、長度上限 64。

    回傳 (clean_overrides, None) 或 (None, error_dict 附可用清單)。
    刻意寬鬆：不擋「不合法值」——測試者故意填壞值就是在測負面路徑(417/1000)，
    分類器本來就會接住（Postman 驗證是為了打對；我們是為了可控地打錯）。
    """
    clean = {}
    if overrides in (None, {}):
        return clean, None
    if not isinstance(overrides, dict):
        return None, {"error": "OVERRIDES_NOT_OBJECT"}
    for case_id, kv in overrides.items():
        if case_id not in scenario_ids:
            return None, {"error": "UNKNOWN_CASE_IN_OVERRIDES", "case": case_id, "valid": scenario_ids}
        sc = registry.get(case_id)
        if sc is None:
            return None, {"error": "UNKNOWN_CASE_IN_OVERRIDES", "case": case_id, "valid": scenario_ids}
        if not isinstance(kv, dict):
            return None, {"error": "OVERRIDE_PARAMS_NOT_OBJECT", "case": case_id}
        specs = {sp.key: sp for sp in sc.params}
        if not specs:
            return None, {"error": "CASE_NOT_PARAMETERIZED", "case": case_id}
        out = {}
        for key, value in kv.items():
            sp = specs.get(key)
            if sp is None:
                return None, {"error": "UNKNOWN_PARAM", "case": case_id, "param": key,
                              "valid": sorted(specs)}
            coerced, bad = _coerce_param(sp, value)
            if bad:
                return None, {"error": "BAD_PARAM_TYPE", "case": case_id, "param": key, "type": sp.type}
            out[key] = coerced
        if out:
            clean[case_id] = out
    return clean, None


def _coerce_param(spec: ParamSpec, value):
    """依 ParamSpec.type 轉換覆寫值；str 類上限 64 字元（設計 §4）。失敗回 (None, True)。"""
    if spec.type == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None, True
        try:
            return int(value), False
        except (TypeError, ValueError):
            return None, True
    if spec.type == "bool":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, str) and value.lower() in ("true", "false", "yes", "no"):
            return value.lower() in ("true", "yes"), False
        return None, True
    # str / date / datetime：一律以字串原樣送（格式由測試者自負——壞格式即負面路徑）
    if not isinstance(value, str):
        return None, True
    if len(value) > _MAX_PARAM_LEN:
        return None, True
    return value, False


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
        "resolved_params": c.resolved_params,              # 本次實際用的合併後參數（設計 §5，報告可追溯）
        "steps": c.steps,                                  # 逐步 HTTP 交易（HTTP 稽核）
        "remediation": remediation(c.error_category),      # 錯誤除錯建議（錯誤分析）
        "failing_step": first_failure(c),                  # 第一個失敗的 step（錯誤分析）
    }
