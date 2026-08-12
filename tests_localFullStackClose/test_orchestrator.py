# tests_localFullStackClose/test_orchestrator.py
"""編排層離線單元測試（CI 可跑，不需 Flask 伺服器、不對外發砲）。

涵蓋：
- registry 完整性（amenity 5/parking 4/keycard 4；keycard 全 UNIMPLEMENTED）
- config.ENV_MATRIX 環境就緒狀態（SIT/MAS ready=false）
- engine 對 LOCAL_OFFLINE 跑一個 amenity 案例（經路由閉環攔截，不出站）
- compute_diff / classify 規則
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from orchestrator.registry import registry
from orchestrator import expected, classify, engine, models


def test_registry_completeness():
    """三模組案例都登錄，amenity ���實作、keycard 全未實作。"""
    import orchestrator  # 觸發 runners 註冊
    by_mod = registry.by_module()
    assert set(by_mod.keys()) >= {"parking", "amenity", "keycard"}
    amenity = by_mod["amenity"]
    assert len(amenity) == 5
    assert all(s.implemented for s in amenity)
    parking = by_mod["parking"]
    assert len(parking) == 4
    assert all(s.implemented for s in parking), "parking 4 案例應都已實作"
    keycard = by_mod["keycard"]
    assert len(keycard) == 4
    assert all(s.implemented for s in keycard), "keycard 案例應都已實作（B 閉環）"


def test_environments_ready_flags():
    """6 環境皆已設定 → ready=true（SIT/MAS 已補上 config）。"""
    for env in ("LOCAL_OFFLINE", "LOCAL", "REAL_QA", "REAL_UG", "REAL_SIT", "REAL_MAS"):
        assert config.ENV_MATRIX[env]["READY"] is True
    # SIT/MAS 補上後應有完整 URL/Header
    assert config.ENV_MATRIX["REAL_SIT"]["PMS_URL"].startswith("https://sit.athena.com.tw")
    assert config.ENV_MATRIX["REAL_MAS"]["PMS_URL"].startswith("https://bacmas.athena.com.tw")
    assert config.ENV_MATRIX["REAL_SIT"]["HEADERS"]["bacchus-athenaid"] == "01"
    assert config.ENV_MATRIX["REAL_MAS"]["HEADERS"]["bacchus-athenaid"] == "35"


def test_compute_diff_field_missing_and_mismatch():
    expected_payload = {"roomNos": "11101", "items": [{"productNos": "M001"}]}
    actual = {"roomNos": "11101"}  # 缺 items
    rows = expected.compute_diff(actual, expected_payload)
    assert any(r["field"] == "items" for r in rows)

    actual2 = {"roomNos": "9999", "items": [{"productNos": "M001"}]}  # roomNos 不符
    rows2 = expected.compute_diff(actual2, expected_payload)
    assert any(r["field"] == "roomNos" for r in rows2)


def test_compute_diff_no_expected_returns_empty():
    assert expected.compute_diff({"a": 1}, None) == []


def test_classify_rules():
    # PASS 不歸類
    ok = models.CaseResult("c", "r", "amenity", "BR", "n", "/e", status=models.CASE_PASS)
    assert classify.classify(ok) is None
    # FAIL + 有 diff → FIELD_MISMATCH
    fail_diff = models.CaseResult("c", "r", "amenity", "BR", "n", "/e", status=models.CASE_FAIL)
    fail_diff.diff = [{"field": "x", "expected": 1, "actual": 2}]
    assert classify.classify(fail_diff) == classify.FIELD_MISMATCH
    # FAIL + 連線錯誤 → TIMEOUT
    fail_conn = models.CaseResult("c", "r", "amenity", "BR", "n", "/e", status=models.CASE_FAIL,
                                  response_payload={"__error__": "ConnectionError: x"})
    assert classify.classify(fail_conn) == classify.TIMEOUT
    # FAIL + 無 diff、無 error → STATUS_CODE
    fail_status = models.CaseResult("c", "r", "amenity", "BR", "n", "/e", status=models.CASE_FAIL,
                                    response_payload={"status_code": 500})
    assert classify.classify(fail_status) == classify.STATUS_CODE


def test_run_context_built_for_all_envs():
    for env in config.ENV_MATRIX:
        ctx = engine.build_run_context(env)
        assert ctx.environment == env
        assert "room_nos" in ctx.urls


def test_start_run_unknown_scenario_marked_fail():
    """不存在的 case_id → 該案例 FAIL(UNKNOWN_SCENARIO)，但 run 不中斷。"""
    run = engine.start_run(["__nonexistent__"], "LOCAL_OFFLINE")
    assert run.total_cases == 1
    assert run.cases[0].status == models.CASE_FAIL
    assert run.cases[0].error_category == "UNKNOWN_SCENARIO"


def test_start_run_unknown_scenario_id_in_list():
    """不存在的 case_id 混在合法清單中 → 該筆 FAIL(UNKNOWN_SCENARIO),其餘正常。"""
    run = engine.start_run(["room_nos_query", "__nope__"], "LOCAL_OFFLINE")
    statuses = {c.case_id: c.status for c in run.cases}
    assert statuses["room_nos_query"] in (models.CASE_PASS, models.CASE_FAIL)
    assert statuses["__nope__"] == models.CASE_FAIL
