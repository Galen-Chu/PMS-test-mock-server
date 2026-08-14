# orchestrator/engine.py
"""編排引擎：建立 Run、逐案例執行、收 CaseResult、算 diff+歸類。

設計：
- build_run_context 把 config.ENV_MATRIX 解析成 RunContext（沿用 dashboard apply_env_to_config 的對齊邏輯，
  但抽成純函式、不寫回全域 config）。
- start_run 同步執行（第一版；結構保留 RUN_RUNNING 給未來背景執行 + UI polling）。
- 環境就緒狀態（ready=False）由 API 層在進入 start_run 前擋掉（回 409）。
"""
import time
import uuid
import threading
from datetime import datetime

import config
from .models import (
    Run, CaseResult, RunContext,
    CASE_PASS, CASE_FAIL, CASE_SKIP, RUN_RUNNING,
)
from .registry import registry
from . import expected as expected_mod
from . import classify as classify_mod

# 全域 run 存放（程序記憶體；重啟即清）+ 並行安全鎖
_RUNS = {}
_RUNS_LOCK = threading.RLock()


def store_run(run):
    """把 Run 存入記憶體表（thread-safe）。"""
    with _RUNS_LOCK:
        _RUNS[run.run_id] = run


def get_run(run_id):
    with _RUNS_LOCK:
        return _RUNS.get(run_id)


def snapshot_run(run_id):
    """取 Run 的淺拷貝快照供序列化（避免序列化時 cases list 被背景執行緒改動）。"""
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
        if run is None:
            return None
        snap = Run(
            run_id=run.run_id, triggered_at=run.triggered_at, environment=run.environment,
            status=run.status, total_cases=run.total_cases, passed=run.passed,
            failed=run.failed, duration_ms=run.duration_ms,
        )
        snap.cases = list(run.cases)
        return snap


def build_run_context(environment: str) -> RunContext:
    """從 config.ENV_MATRIX[environment] 組出 RunContext（不寫回全域 config）。"""
    cfg = config.ENV_MATRIX.get(environment, config.ENV_MATRIX["LOCAL_OFFLINE"])
    use_real = environment.startswith("REAL")
    base = cfg["BASE_URL_EXTERNAL"]
    headers = dict(cfg["HEADERS"])
    params_parking = {
        "bacchus-hotelcod": cfg["HOTEL_COD"],
        "bacchus-athenaid": cfg["ATHENA_ID"],
        "thirdParty": "SHIN_YEONG",
    }
    params_amenity = {
        "bacchus-hotelcod": cfg["HOTEL_COD"],
        "bacchus-athenaid": cfg["ATHENA_ID"],
        "thirdParty": "BR",
    }
    # LOCAL / LOCAL_OFFLINE 模式：runner 是「客戶端」，要打到本地 Flask 伺服器。
    # LOCAL_OFFLINE 的攔截（不出站）發生在「伺服器路由內部」，所以客戶端仍指向 localhost。
    if not use_real:
        server_base = config.LOCAL_SERVER_BASE            # 伺服器根，給非 vendor-sync 路由用
        base = config.LOCAL_SERVER_BASE + "/external/vendor-sync-data"
        # 本地 mock 的車辨 car_arrival 路由有 auth gate（Authorization 须 = LOCAL_TOKEN 或 CURRENT_TOKEN）
        # runner 在本地模式帶 LOCAL_TOKEN，確保通過；REAL 模式由各環境 bacchus header 鑑別。
        headers["Authorization"] = config.LOCAL_TOKEN
    else:
        server_base = config.ENV_MATRIX[environment].get("BASE_URL_EXTERNAL", "").replace("/external/vendor-sync-data", "") or config.ENV_MATRIX[environment].get("PMS_URL", "")
    urls = {
        "room_nos": f"{base}/room-pay/room-nos",
        "mifare_nos": f"{base}/room-pay/mifare-nos",
        "room_pay": f"{base}/room-pay",
        "room_pay_cancel": f"{base}/room-pay-cancel",
        "room_billing": f"{base}/room-billing",
        "car_arrival": f"{base}/car-arrival",
        # 非 vendor-sync 路由（停車的 PMS→廠商方向與內部端點）
        "check_in": f"{server_base}/pms-sync-data/check-in",
        "night_audit": f"{server_base}/pms-sync-data/night-audit",
        "change_checkout": f"{server_base}/pms-sync-data/change-checkout-datetime",
        "change_car_nos": f"{server_base}/pms-sync-data/change-car-nos",
        "check_in_cancel": f"{server_base}/pms-sync-data/check-in-cancel",
        "whitelist": f"{server_base}/parking/internal/whitelist",
        # PAYTRONEX 專屬路由（/parktron/hpms/services/roomer/*）
        "paytronex_add": f"{server_base}/parktron/hpms/services/roomer/add",
        "paytronex_find": f"{server_base}/parktron/hpms/services/roomer/findByLicensePlate",
        # 門禁 keycard 廠商 API 面（PMS→vendor 製卡方向；非 vendor-sync 前綴）
        "keycard_order": f"{server_base}/api/Order",
        "keycard_ordercard": f"{server_base}/api/OrderCard",
    }
    return RunContext(
        environment=environment, use_real=use_real, base_url=base,
        headers=headers, params_parking=params_parking, params_amenity=params_amenity,
        urls=urls,
    )


def _build_case_result(case_id, run_id, scenario, status, duration_ms,
                       request_payload=None, response_payload=None) -> CaseResult:
    cr = CaseResult(
        case_id=case_id, run_id=run_id,
        module=scenario.module, vendor=scenario.vendor,
        scenario_name=scenario.name, endpoint=scenario.endpoint,
        status=status, duration_ms=duration_ms,
        request_payload=request_payload, response_payload=response_payload,
    )
    # diff + expected
    exp = expected_mod.get_expected(scenario.expected_key, scenario.endpoint)
    cr.expected_payload = exp
    cr.diff = expected_mod.compute_diff(response_payload, exp)
    cr.error_category = classify_mod.classify(cr)
    return cr


def _execute_run(run, scenario_ids, ctx):
    """背景執行緒主體：逐案例執行，每案完成即 append + recompute（鎖保護 cases list）。"""
    run_id = run.run_id
    for sid in scenario_ids:
        ctx.recorder = []  # 逐步錄製槽每案重置（ctx 跨案例共用）
        sc = registry.get(sid)
        if sc is None:
            cr = CaseResult(
                case_id=sid, run_id=run_id, module="?", vendor="?",
                scenario_name=sid, endpoint="?", status=CASE_FAIL,
                error_category="UNKNOWN_SCENARIO",
            )
        elif not sc.implemented:
            cr = _build_case_result(sid, run_id, sc, CASE_SKIP, 0)
            cr.error_category = classify_mod.UNIMPLEMENTED
        else:
            t0 = time.perf_counter()
            try:
                cr = sc.runner(ctx)
                cr.run_id = run_id
                if cr.expected_payload is None and sc.expected_key:
                    cr.expected_payload = expected_mod.get_expected(sc.expected_key, sc.endpoint)
                    cr.diff = expected_mod.compute_diff(cr.response_payload, cr.expected_payload)
                if cr.error_category is None:
                    cr.error_category = classify_mod.classify(cr)
                cr.duration_ms = cr.duration_ms or int((time.perf_counter() - t0) * 1000)
            except Exception as e:
                dur = int((time.perf_counter() - t0) * 1000)
                cr = _build_case_result(
                    sid, run_id, sc, CASE_FAIL, dur,
                    response_payload={"__error__": f"{type(e).__name__}: {e}"},
                )
        cr.steps = list(ctx.recorder)  # 把本案例逐步 HTTP 交易錄進結果（UI「HTTP 稽核」來源）
        with _RUNS_LOCK:
            run.cases.append(cr)
            run.recompute()

    # 全部案例跑完才定終局狀態：執行緒在這裡把 status 從 RUNNING 翻成 DONE / PARTIAL_FAIL。
    # 若在逐案途中就翻成 DONE，UI 第一次 polling 即會誤判完成並停止，後續案例結果永遠進不來。
    with _RUNS_LOCK:
        run.recompute()
        run.finalize_status()


def _new_run(environment: str) -> Run:
    return Run(
        run_id=uuid.uuid4().hex[:12],
        triggered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        environment=environment,
        status=RUN_RUNNING,
    )


def start_run(scenario_ids, environment: str) -> Run:
    """同步執行一組案例，回傳完整 Run（跑完才回）。供需要同步語意的呼叫端用。"""
    ctx = build_run_context(environment)
    run = _new_run(environment)
    _execute_run(run, scenario_ids, ctx)
    return run


def start_run_async(scenario_ids, environment: str) -> Run:
    """非同步執行：背景執行緒跑案例，立即回傳 status=RUNNING 的 Run。

    client 用 GET /runs/<id> polling(snapshot_run 給序列化安全快照)直到 status != RUNNING。
    Run 先 store_run 入記憶體表(鎖保護)，背景執行緒逐案 append + recompute。
    """
    ctx = build_run_context(environment)
    run = _new_run(environment)
    store_run(run)
    t = threading.Thread(target=_execute_run, args=(run, scenario_ids, ctx), daemon=True)
    t.start()
    return run

