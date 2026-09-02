# tests_localFullStackClose/test_param_override.py
"""案例參數化離線單元測試（docs/design-case-parameterization.md §10）。

涵蓋：
- Phase 1 案例宣告 ParamSpec；負面路徑案例刻意不開放
- 無 overrides 行為 100% 不變（硬約束）；覆寫流進 request/結果
- 動態預設（唯一 ID）與 /scenarios 序列化（dynamic 標記）
- validate_overrides 四類 400 路徑與型別轉換
- §7 種子回填（backfill_echo_fields）與 diff 分級（kind: param_echo/mismatch/missing）

全部離線可跑：LOCAL_OFFLINE 的連線失敗不影響——step 在發送前即錄製 request_params。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import orchestrator  # 觸發 runners 註冊
from orchestrator.registry import registry, params_meta
from orchestrator import engine, expected
from orchestrator.api import validate_overrides

# 設計 §9 Phase 1 開放清單（amenity 5 / SHIN_YEONG 10 / PAYTRONEX 2 / keycard 3）
PHASE1 = [
    "room_nos_query", "mifare_query", "amenity_charge", "amenity_cancel", "billing_sync",
    "car_arrival", "checkin_sync", "night_audit", "change_checkout", "change_car_nos",
    "check_in_cancel", "parking_sync_checkin", "parking_sync_change_car",
    "parking_sync_disable", "parking_sync_cancel",
    "car_arrival_pt", "car_arrival_retry",
    "keycard_login", "keycard_room_lookup", "keycard_make_card",
]
# 負面路徑案例：劇本本身即測資，刻意不開放覆寫（設計 §9「不開放」列）
NEGATIVES = [
    "room_nos_query_notfound", "mifare_query_notfound", "amenity_billing_notfound",
    "amenity_pay_duplicate", "amenity_cancel_notfound", "parking_sync_invalid",
    "car_arrival_missing_field", "keycard_bad_token",
]


def test_phase1_cases_declare_params():
    for cid in PHASE1:
        sc = registry.get(cid)
        assert sc is not None and sc.params, f"{cid} 應宣告 ParamSpec"
        for sp in sc.params:
            assert sp.label, f"{cid}.{sp.key} 應有 UI label"
    for cid in NEGATIVES:
        sc = registry.get(cid)
        assert sc is None or not sc.params, f"{cid} 為負面路徑,刻意不開放覆寫"


def test_no_overrides_backward_compat():
    """硬約束：不帶 overrides 時 resolved 值 = 預設 = 參數化前的硬編值。"""
    run = engine.start_run(["room_nos_query"], "LOCAL_OFFLINE")
    cr = run.cases[0]
    assert cr.resolved_params == {"keyword": "11101"}
    # 連線失敗(離線)仍會錄製 request_params——斷言出站帶的關鍵字
    assert cr.steps[0]["request_params"]["keyword"] == "11101"
    assert cr.steps[0]["request_params"]["thirdParty"] == "BR"


def test_override_flows_into_request():
    run = engine.start_run(["room_nos_query"], "LOCAL_OFFLINE",
                           overrides={"room_nos_query": {"keyword": "11205"}})
    cr = run.cases[0]
    assert cr.resolved_params == {"keyword": "11205"}
    assert cr.steps[0]["request_params"]["keyword"] == "11205"


def test_full_payload_with_overrides(monkeypatch):
    """以 mock 回應離線跑通 amenity_charge 全管線：覆寫值應貫穿 GET→POST payload。"""
    import hardware.simulate_speaker as ss
    from hardware.simulate_speaker import load_product_from_pool

    def _resp(status, body):
        m = MagicMock(status_code=status, headers={"Content-Type": "application/json"})
        m.json.return_value = body
        return m

    monkeypatch.setattr(ss.requests, "get", lambda *a, **k: _resp(200, [{"checkInSerial": "CI-77", "roomNos": ["11205"]}]))
    monkeypatch.setattr(ss.requests, "post", lambda *a, **k: _resp(200, {}))

    run = engine.start_run(["amenity_charge"], "LOCAL_OFFLINE",
                           overrides={"amenity_charge": {"room_no": "11205", "quantity": 2}})
    cr = run.cases[0]
    assert cr.status == "PASS"
    assert cr.request_payload["roomNos"] == "11205"
    assert cr.request_payload["items"][0]["orderQuantity"] == 2
    assert cr.request_payload["items"][0]["productNos"] == load_product_from_pool("M001")
    # GET 步的 query 也用覆寫房號
    assert cr.steps[0]["request_params"]["keyword"] == "11205"


def test_dynamic_defaults_unique_per_run():
    """動態預設(唯一 ID)：同 run 求值一次、跨 run 每次不同。"""
    run1 = engine.start_run(["car_arrival"], "LOCAL_OFFLINE")
    run2 = engine.start_run(["car_arrival"], "LOCAL_OFFLINE")
    p1 = run1.cases[0].resolved_params
    p2 = run2.cases[0].resolved_params
    assert p1["car_number"].startswith("ABC-")
    assert p2["car_number"].startswith("ABC-")
    assert p1["car_number"] != p2["car_number"]
    # SA v1.2 時間格式 yyyy/mm/dd hh:mm(無秒)
    assert len(p1["arrival_time"].split(" ")[1]) == 5


def test_scenarios_params_meta_serialization():
    sc = registry.get("room_nos_query")
    meta = params_meta(sc)
    assert meta[0]["key"] == "keyword"
    assert meta[0]["default"] == "11101"
    assert meta[0]["dynamic"] is False
    assert meta[0]["label"]

    sc2 = registry.get("car_arrival")
    meta2 = params_meta(sc2, engine.build_run_context("LOCAL_OFFLINE"))
    by_key = {m["key"]: m for m in meta2}
    assert by_key["car_number"]["dynamic"] is True
    assert by_key["car_number"]["default"].startswith("ABC-")


def test_validate_overrides_reject_paths():
    ok, err = validate_overrides({"no_such_case": {"keyword": "1"}}, ["room_nos_query"])
    assert ok is None and err["error"] == "UNKNOWN_CASE_IN_OVERRIDES"
    ok, err = validate_overrides({"room_nos_query": {"no_such_param": "1"}}, ["room_nos_query"])
    assert ok is None and err["error"] == "UNKNOWN_PARAM"
    assert err["valid"] == ["keyword"]
    ok, err = validate_overrides({"amenity_charge": {"quantity": "x"}}, ["amenity_charge"])
    assert ok is None and err["error"] == "BAD_PARAM_TYPE"
    ok, err = validate_overrides({"room_nos_query": {"keyword": "x" * 65}}, ["room_nos_query"])
    assert ok is None and err["error"] == "BAD_PARAM_TYPE"   # 長度上限 64
    # 負面路徑案例不開放
    ok, err = validate_overrides({"room_nos_query_notfound": {"keyword": "1"}}, ["room_nos_query_notfound"])
    assert ok is None and err["error"] == "CASE_NOT_PARAMETERIZED"
    # overrides 指到「沒在本次清單」的案例 → 拒
    ok, err = validate_overrides({"mifare_query": {"keyword": "1"}}, ["room_nos_query"])
    assert ok is None and err["error"] == "UNKNOWN_CASE_IN_OVERRIDES"


def test_validate_overrides_coercion_and_passthrough():
    clean, err = validate_overrides(
        {"amenity_charge": {"room_no": "11205", "quantity": "3"},
         "room_nos_query": {"keyword": "9999"}},
        ["amenity_charge", "room_nos_query"])
    assert err is None
    assert clean["amenity_charge"]["quantity"] == 3          # "3" → int
    assert clean["room_nos_query"]["keyword"] == "9999"       # 壞值原樣放行(負面路徑是測試本體)
    # 空字串可送(測缺欄負面路徑)
    clean, _ = validate_overrides({"room_nos_query": {"keyword": ""}}, ["room_nos_query"])
    assert clean["room_nos_query"]["keyword"] == ""
    # 空 overrides / None → 直接過
    assert validate_overrides({}, ["room_nos_query"]) == ({}, None)
    assert validate_overrides(None, ["room_nos_query"]) == ({}, None)


def test_backfill_echo_fields():
    seed = {"roomNos": "101", "items": [{"productNos": "M001"}],
            "roomPayMain": {"roomNos": "101", "orderNos": "OLD"}}
    # 頂層 + 巢狀路徑替換
    out = expected.backfill_echo_fields(seed, {"roomNos": "11205", "roomPayMain.roomNos": "11205"})
    assert out["roomNos"] == "11205"
    assert out["roomPayMain"]["roomNos"] == "11205"
    # 不存在路徑跳過;種子原物件不可被改動(拷貝語意)
    assert out["roomPayMain"]["orderNos"] == "OLD"
    assert seed["roomNos"] == "101"
    # 非 dict / 空 map → 原樣
    assert expected.backfill_echo_fields(None, {"a": 1}) is None
    assert expected.backfill_echo_fields(seed, {}) is seed


def test_compute_diff_param_echo_grading():
    exp = {"roomNos": "101", "payAmount": 500}
    actual = {"roomNos": "11205", "payAmount": 999}
    rows = expected.compute_diff(actual, exp, param_values={"roomNos": "11205"})
    kinds = {r["field"]: r["kind"] for r in rows}
    assert kinds["roomNos"] == "param_echo"    # 回映本次參數 → 灰
    assert kinds["payAmount"] == "mismatch"    # 真差異 → 紅
    # 不給 param_values → 舊行為(全部 mismatch 判定,列上多了 kind 鍵)
    rows2 = expected.compute_diff(actual, exp)
    assert all(r["kind"] == "mismatch" for r in rows2)
    # 缺欄
    rows3 = expected.compute_diff({}, exp, param_values={"roomNos": "11205"})
    assert all(r["kind"] == "missing" for r in rows3)


def test_engine_seed_backfill_wiring():
    """§7 接線：覆寫房號後,種子的 echo 欄位以 resolved 值回填(離線連線失敗路徑也會走)。"""
    run = engine.start_run(["amenity_charge"], "LOCAL_OFFLINE",
                           overrides={"amenity_charge": {"room_no": "11205"}})
    cr = run.cases[0]
    assert cr.expected_payload is not None
    assert cr.expected_payload["roomNos"] == "11205"   # 種子原為 101,已按本次參數回填
