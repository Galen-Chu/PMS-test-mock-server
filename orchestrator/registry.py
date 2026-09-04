# orchestrator/registry.py
"""模組化情境註冊表。

對齊現有「廠商 Strategy 模式」但補上「案例層」的掛點：
- 新增廠商 → 加 server/<mod>/vendors/vendor_XXX.py（現狀）
- 新增案例 → 在該模組下用 @register_scenario(...) 掛 runner
- 新增模組 → 加 blueprint（現狀��+ 在 runners/ 各模組檔登錄該模組的案例

三種擴充都變成「加檔案 + 註冊」，不再改編排核心。
"""
from typing import Callable, Dict, List, Optional

from .models import Scenario, RunContext, CaseResult, ParamSpec


class ScenarioRegistry:
    """全域案例註冊表（單例）。"""

    def __init__(self) -> None:
        self._by_id: Dict[str, Scenario] = {}

    # ---- 註冊 ----------------------------------------------------------
    def register(
        self,
        id: str,
        *,
        module: str,
        vendor: str,
        name: str,
        endpoint: str,
        runner: Optional[Callable[[RunContext], CaseResult]] = None,
        expected_key: Optional[str] = None,
        params: Optional[List[ParamSpec]] = None,
    ) -> Scenario:
        if id in self._by_id:
            raise ValueError(f"Scenario id 衝突: {id}")
        sc = Scenario(
            id=id, module=module, vendor=vendor, name=name,
            endpoint=endpoint, runner=runner, expected_key=expected_key,
            params=tuple(params or ()),
        )
        self._by_id[id] = sc
        return sc

    def register_unimplemented(
        self, id: str, *, module: str, vendor: str, name: str, endpoint: str
    ) -> Scenario:
        """登錄中繼資料但無 runner：UI 顯示「待開發」，不阻塞其他案例。"""
        return self.register(id, module=module, vendor=vendor, name=name, endpoint=endpoint, runner=None)

    # ---- 查詢 ----------------------------------------------------------
    def get(self, id: str) -> Optional[Scenario]:
        return self._by_id.get(id)

    def all(self) -> List[Scenario]:
        return list(self._by_id.values())

    def by_module(self) -> Dict[str, List[Scenario]]:
        """以模組分組（供 /scenarios 與 UI 矩陣用）。"""
        out: Dict[str, List[Scenario]] = {}
        for sc in self._by_id.values():
            out.setdefault(sc.module, []).append(sc)
        return out

    def ids(self) -> List[str]:
        return list(self._by_id.keys())

    # ---- 參數（設計 §3/§5）----------------------------------------------
    def resolve_defaults(self, case_id: str, ctx: Optional[RunContext] = None) -> Dict[str, object]:
        """求值案例的預設參數（動態 default 此時以 ctx 求值）。

        未宣告參數或案例不存在 → {}。engine 於 run 開始時對每個案例呼叫一次，
        同 run 內動態值（時間戳）一致。
        """
        sc = self._by_id.get(case_id)
        if sc is None or not sc.params:
            return {}
        out: Dict[str, object] = {}
        for spec in sc.params:
            out[spec.key] = spec.default(ctx) if callable(spec.default) else spec.default
        return out


def params_meta(scenario: Scenario, ctx: Optional[RunContext] = None) -> List[Dict[str, object]]:
    """ParamSpec → /scenarios 序列化形式（參數宣告即文件，UI 表單零硬編）。

    動態 default 以 ctx 求值展示 + ``dynamic: true``（UI 顯示「每次執行自動產生」placeholder）。
    """
    out = []
    for spec in scenario.params:
        dynamic = callable(spec.default)
        out.append({
            "key": spec.key,
            "label": spec.label,
            "type": spec.type,
            "default": (spec.default(ctx) if dynamic else spec.default),
            "dynamic": dynamic,
            "hint": spec.hint,
            "required": spec.required,
        })
    return out


# 全域單例 —— 各模組的 runners 檔 import 它並註冊
registry = ScenarioRegistry()


def register_scenario(
    id: str,
    *,
    module: str,
    vendor: str,
    name: str,
    endpoint: str,
    expected_key: Optional[str] = None,
    params: Optional[List[ParamSpec]] = None,
):
    """裝飾器：把一個 runner 函式註冊成案例。

    用法：
        @register_scenario("amenity_charge", module="amenity", vendor="BR_AIELLO",
                           name="備品入帳", endpoint="/room-pay", expected_key="Scenario_1_Room_Nos_To_Billing",
                           params=[ParamSpec("room_no", "房號", "str", "11101", echo_fields=("roomNos",))])
        def run(ctx: RunContext) -> CaseResult:
            ...
    """
    def deco(fn: Callable[[RunContext], CaseResult]) -> Callable[[RunContext], CaseResult]:
        registry.register(
            id, module=module, vendor=vendor, name=name,
            endpoint=endpoint, runner=fn, expected_key=expected_key, params=params,
        )
        return fn
    return deco
