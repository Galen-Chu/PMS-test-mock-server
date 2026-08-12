# orchestrator/registry.py
"""模組化情境註冊表。

對齊現有「廠商 Strategy 模式」但補上「案例層」的掛點：
- 新增廠商 → 加 server/<mod>/vendors/vendor_XXX.py（現狀）
- 新增案例 → 在該模組下用 @register_scenario(...) 掛 runner
- 新增模組 → 加 blueprint（現狀��+ 在 runners.py 登錄該模組的案例

三種擴充都變成「加檔案 + 註冊」，不再改編排核心。
"""
from typing import Callable, Dict, List, Optional

from .models import Scenario, RunContext, CaseResult


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
    ) -> Scenario:
        if id in self._by_id:
            raise ValueError(f"Scenario id 衝突: {id}")
        sc = Scenario(
            id=id, module=module, vendor=vendor, name=name,
            endpoint=endpoint, runner=runner, expected_key=expected_key,
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
):
    """裝飾器：把一個 runner 函式註冊成案例。

    用法：
        @register_scenario("amenity_charge", module="amenity", vendor="BR_AIELLO",
                           name="備品入帳", endpoint="/room-pay", expected_key="Scenario_1_Room_Nos_To_Billing")
        def run(ctx: RunContext) -> CaseResult:
            ...
    """
    def deco(fn: Callable[[RunContext], CaseResult]) -> Callable[[RunContext], CaseResult]:
        registry.register(
            id, module=module, vendor=vendor, name=name,
            endpoint=endpoint, runner=fn, expected_key=expected_key,
        )
        return fn
    return deco
