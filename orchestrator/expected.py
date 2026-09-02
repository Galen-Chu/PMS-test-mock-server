# orchestrator/expected.py
"""期望值種子：�� tests_data_pool/verified_payload_logs.json 建 index，
供 Diff 視圖（spec §6.3）比對「實際 vs 期望」欄位。

每筆 log 是「真實通關過的 request body」，剛好可當成功 payload 的期望值。
"""
import copy
import json
import os
from typing import Any, Dict, List, Optional

_POOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests_data_pool", "verified_payload_logs.json",
)

# (scenario_name, endpoint) → payload
_index: Dict[tuple, Any] = {}
_loaded = False


def _load():
    global _loaded, _index
    if _loaded:
        return
    _loaded = True
    if not os.path.exists(_POOL):
        return
    try:
        with open(_POOL, "r", encoding="utf-8") as f:
            for entry in json.load(f):
                key = (entry.get("scenario"), entry.get("endpoint"))
                if key[0] and not _index.get(key):
                    _index[key] = entry.get("payload")
    except Exception:
        # 種子載入失敗不該阻斷測試；diff 退化為「無期望值」
        _index = {}


def get_expected(scenario_name: Optional[str], endpoint: Optional[str]) -> Optional[Any]:
    """依 (scenario, endpoint) 取期望 payload；沒有就 None。"""
    _load()
    if not scenario_name:
        return None
    return _index.get((scenario_name, endpoint))


def backfill_echo_fields(expected: Any, echo_map: Dict[str, Any]) -> Any:
    """種子參數回填（設計 §7 兩層對策的第 1 層）。

    比對前把 expected 中屬於 ParamSpec.echo_fields 的欄位值，以本次 resolved
    參數值替換——否則測試者覆寫房號後，回應 echo 的房號會被誤報 MISMATCH，
    噪音淹死真差異。只替換既存欄位（路徑不存在則跳過），一律回傳拷貝、
    不改動種子 index。
    """
    if not expected or not isinstance(expected, dict) or not echo_map:
        return expected
    out = copy.deepcopy(expected)
    for dotted, value in echo_map.items():
        keys = dotted.split(".")
        node = out
        for k in keys[:-1]:
            if not isinstance(node, dict) or k not in node:
                node = None
                break
            node = node[k]
        if isinstance(node, dict) and keys[-1] in node:
            node[keys[-1]] = value
    return out


def compute_diff(actual: Any, expected: Any, param_values: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """欄位層級比對：逐欄位比 expected vs actual（回傳列增 ``kind`` 分級，設計 §7 第 2 層）。

    - expected 為 dict 時，逐 key 比對：actual 缺欄位 → kind="missing"；
      值不同 → actual 等於本次 resolved 參數值（參數回映）→ kind="param_echo"（灰），
      否則 kind="mismatch"（紅，真差異）。
    - param_values：{頂層欄位名: 本次 resolved 值}；未給時全部回 mismatch（舊行為）。
    - actual 非 dict 或 expected 非 dict → 整體比對。
    """
    if expected is None:
        return []
    rows: List[Dict[str, Any]] = []
    pv = param_values or {}

    if isinstance(expected, dict):
        actual_d = actual if isinstance(actual, dict) else {}
        for k, exp_v in expected.items():
            act_v = actual_d.get(k, _MISSING)
            if act_v is _MISSING:
                rows.append({"field": k, "expected": exp_v, "actual": None, "kind": "missing"})
            elif act_v != exp_v:
                kind = "param_echo" if k in pv and act_v == pv[k] else "mismatch"
                rows.append({"field": k, "expected": exp_v, "actual": act_v, "kind": kind})
        return rows

    # 非 dict：整體比對
    if actual != expected:
        rows.append({"field": "(root)", "expected": expected, "actual": actual, "kind": "mismatch"})
    return rows


class _Missing:
    """區分「actual 沒這欄」與「actual 欄位值是 None」。"""
    __slots__ = ()

    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()
