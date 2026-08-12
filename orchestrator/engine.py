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
from datetime import datetime

import config
from .models import (
    Run, CaseResult, RunContext,
    CASE_PASS, CASE_FAIL, CASE_SKIP, RUN_RUNNING,
)
from .registry import registry
from . import expected as expected_mod
from . import classify as classify_mod


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
        base = config.LOCAL_SERVER_BASE + "/external/vendor-sync-data"
    urls = {
        "room_nos": f"{base}/room-pay/room-nos",
        "mifare_nos": f"{base}/room-pay/mifare-nos",
        "room_pay": f"{base}/room-pay",
        "room_pay_cancel": f"{base}/room-pay-cancel",
        "room_billing": f"{base}/room-billing",
        "car_arrival": f"{base}/car-arrival",
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


def start_run(scenario_ids, environment: str) -> Run:
    """同步執行一組案例，回傳完整 Run。

    - UNIMPLEMENTED 案例（無 runner）→ SKIP + error_category=UNIMPLEMENTED。
    - runner 拋例外 → FAIL + TIMEOUT（連線/程式錯誤），不中斷整個 run。
    """
    ctx = build_run_context(environment)
    run_id = uuid.uuid4().hex[:12]
    run = Run(
        run_id=run_id,
        triggered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        environment=environment,
        status=RUN_RUNNING,
    )

    for sid in scenario_ids:
        sc = registry.get(sid)
        if sc is None:
            run.cases.append(CaseResult(
                case_id=sid, run_id=run_id, module="?", vendor="?",
                scenario_name=sid, endpoint="?", status=CASE_FAIL,
                error_category="UNKNOWN_SCENARIO",
            ))
            continue

        if not sc.implemented:
            run.cases.append(_build_case_result(
                sid, run_id, sc, CASE_SKIP, 0))
            run.cases[-1].error_category = classify_mod.UNIMPLEMENTED
            continue

        t0 = time.perf_counter()
        try:
            cr = sc.runner(ctx)
            # runner 可能只回部分欄位；補上 run_id 與分類
            cr.run_id = run_id
            if cr.expected_payload is None and sc.expected_key:
                cr.expected_payload = expected_mod.get_expected(sc.expected_key, sc.endpoint)
                cr.diff = expected_mod.compute_diff(cr.response_payload, cr.expected_payload)
            if cr.error_category is None:
                cr.error_category = classify_mod.classify(cr)
            cr.duration_ms = cr.duration_ms or int((time.perf_counter() - t0) * 1000)
            run.cases.append(cr)
        except Exception as e:
            dur = int((time.perf_counter() - t0) * 1000)
            run.cases.append(_build_case_result(
                sid, run_id, sc, CASE_FAIL, dur,
                response_payload={"__error__": f"{type(e).__name__}: {e}"},
            ))

    run.recompute()
    return run

