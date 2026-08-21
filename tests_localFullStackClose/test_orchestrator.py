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
    assert len(amenity) == 10  # 5 happy path + 5 SA 負面路徑(417 錯誤碼)
    assert all(s.implemented for s in amenity)
    amenity_ids = {s.id for s in amenity}
    assert {"room_nos_query_notfound", "mifare_query_notfound", "amenity_billing_notfound",
            "amenity_pay_duplicate", "amenity_cancel_notfound"} <= amenity_ids
    parking = by_mod["parking"]
    assert len(parking) == 20  # SHIN_YEONG 13(7 事件路由 + 6 SA 公版) + PAYTRONEX 7(2 + 5 管線情境)
    parking_vendors = {s.vendor for s in parking}
    assert parking_vendors == {"SHIN_YEONG", "PAYTRONEX"}
    parking_ids = {s.id for s in parking}
    # 新詠 6 條串接 API 都要有 runner（含 3 條新補 + SA v1.2 公版 6 情境）
    assert {"change_checkout", "change_car_nos", "check_in_cancel",
            "parking_sync_checkin", "parking_sync_change_car", "parking_sync_disable",
            "parking_sync_cancel", "parking_sync_invalid", "car_arrival_missing_field"} <= parking_ids
    # 博辰 SA find→update 管線 4 事件 + 查無車牌
    assert {"paytronex_cancel_checkin", "paytronex_clear_plate", "paytronex_change_plate",
            "paytronex_change_checkout", "paytronex_find_unknown"} <= parking_ids
    assert all(s.implemented for s in parking), "parking 20 案例應都已實作"
    keycard = by_mod["keycard"]
    assert len(keycard) == 10  # WAFERLOCK 9(Swagger 真實合約情境) + LIVEAM 1(待開發)
    keycard_vendors = {s.vendor for s in keycard}
    assert keycard_vendors == {"WAFERLOCK", "LIVEAM"}
    keycard_ids = {s.id for s in keycard}
    # Swagger 真實管線/狀態機情境
    assert {"keycard_login", "keycard_room_lookup", "keycard_make_card", "keycard_checkin_open",
            "keycard_checkout_invalidate", "keycard_change_checkout", "keycard_revoke_card",
            "keycard_bad_token", "card_lifecycle"} <= keycard_ids
    # LIVEAM card_issue_exception 為 UNIMPLEMENTED,其餘已實作
    assert any(not s.implemented for s in keycard if s.vendor == "LIVEAM")


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
        assert "change_checkout" in ctx.urls      # 新詠 3 條新補 URL
        assert "change_car_nos" in ctx.urls
        assert "check_in_cancel" in ctx.urls
        assert isinstance(ctx.recorder, list)      # 逐步錄製槽存在
        # 階段二:鑑別 Header 雙帶(SA athena/hotel + QA Swagger bacchus-*,衝突待裁決)
        assert ctx.headers_amenity.get("athena") is not None
        assert ctx.headers_amenity.get("bacchus-athenaid") is not None
        assert ctx.headers_parking.get("hotel") is not None
        assert ctx.headers_parking.get("bacchus-hotelcod") is not None


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


def test_shin_yeong_sa_is_enabled_parsing():
    """新詠解析器對齊 SA v1.2:is_enabled(Yes/No)讀取、change_car_nos flat 狀態、cancel end_date 直通。"""
    from server.parking.vendors.vendor_SHIN_YEONG import VendorShinYeongStrategy
    s = VendorShinYeongStrategy()

    base = {"guest_id": "G1", "car_number": "A-1", "guest_name": "測試客",
            "start_date": "2026/08/14 15:00", "end_date": "2026/08/15 11:00"}
    assert s.parse_pms_checkin({**base, "is_enabled": "Yes"})["enabled"] is True
    assert s.parse_pms_checkin({**base, "is_enabled": "No"})["enabled"] is False
    # 舊 key "enabled" 保留相容
    assert s.parse_pms_checkin({**base, "enabled": "Y"})["enabled"] is True

    # 舊版 flat 分支未讀狀態(恆為啟用)的回歸守護:停用必須被正確解析
    assert s.parse_pms_change_car_nos({"guest_id": "G1", "car_number": "NEW-1", "is_enabled": "No"})["enabled"] is False

    # SA v1.2 範例 5:取消入住採用 PMS 傳入的 end_date(緩衝計算降為 fallback)
    cix = s.parse_pms_cancel_checkin({"guest_id": "G1", "car_number": "A-1",
                                      "end_date": "2026/08/14 23:59", "is_enabled": "Yes"})
    assert cix["end_date"] == "2026-08-14 23:59:00"
    assert cix["enabled"] is True

    assert s.parse_pms_night_audit({"guest_id": "G2", "is_enabled": "No"})["enabled"] is False


def test_execute_for_ctx_records_steps(monkeypatch):
    """execute_for_ctx 應把每筆 HTTP 交易錄進 ctx.recorder（以 mock 假造回應，離線可跑）。"""
    import types as _types
    from unittest.mock import MagicMock
    from hardware.simulate_speaker import execute_for_ctx
    import hardware.simulate_speaker as ss

    def _resp(status, body):
        m = MagicMock(status_code=status, headers={"Content-Type": "application/json"})
        m.json.return_value = body
        return m

    monkeypatch.setattr(ss.requests, "get", lambda *a, **k: _resp(200, {"ok": True}))
    monkeypatch.setattr(ss.requests, "post", lambda *a, **k: _resp(417, {"err": "no guest"}))

    ctx = _types.SimpleNamespace(headers={"Authorization": "t"}, recorder=[])
    execute_for_ctx(ctx, "GET", "http://mock/room-nos", params={"keyword": "11101"})
    execute_for_ctx(ctx, "POST", "http://mock/pay", json_body={"roomNos": "11101"})

    assert len(ctx.recorder) == 2
    assert ctx.recorder[0]["method"] == "GET"
    assert ctx.recorder[0]["status_code"] == 200
    assert ctx.recorder[0]["response_body"] == {"ok": True}
    assert ctx.recorder[0]["request_params"] == {"keyword": "11101"}
    assert ctx.recorder[1]["status_code"] == 417
    # classify 應能從 steps 判定 STATUS_CODE（非 2xx）
    cr = models.CaseResult("c", "r", "amenity", "BR", "n", "/e", status=models.CASE_FAIL, steps=ctx.recorder)
    assert classify.classify(cr) == classify.STATUS_CODE
