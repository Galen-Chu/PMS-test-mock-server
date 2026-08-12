# orchestrator/expected.py
"""期望值種子：�� tests_data_pool/verified_payload_logs.json 建 index，
供 Diff 視圖（spec §6.3）比對「實際 vs 期望」欄位。

每筆 log 是「真實通關過的 request body」，剛好可當成功 payload 的期望值。
"""
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


def compute_diff(actual: Any, expected: Any) -> List[Dict[str, Any]]:
    """欄位層級比對：逐欄位比 expected vs actual。

    第一版策略：
    - expected 為 dict 時，逐 key 比對（actual 缺欄位 → MISSING；值不同 → MISMATCH）。
    - actual 非 dict 或 expected 非 dict → 整體比對。
    - 回傳 [{field, expected, actual}] 供 UI 直接渲染。
    """
    if expected is None:
        return []
    rows: List[Dict[str, Any]] = []

    if isinstance(expected, dict):
        actual_d = actual if isinstance(actual, dict) else {}
        for k, exp_v in expected.items():
            act_v = actual_d.get(k, _MISSING)
            if act_v is _MISSING:
                rows.append({"field": k, "expected": exp_v, "actual": None})
            elif act_v != exp_v:
                rows.append({"field": k, "expected": exp_v, "actual": act_v})
        return rows

    # 非 dict：整體比對
    if actual != expected:
        rows.append({"field": "(root)", "expected": expected, "actual": actual})
    return rows


class _Missing:
    """區分「actual 沒這欄」與「actual 欄位值是 None」。"""
    __slots__ = ()

    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()
