# orchestrator/models.py
"""測試編排層的資料模型（對齊設計規格 §7 Run/Case）。

與被測系統（server/* 的 Flask blueprints 與廠商策略）正交：
- Strategy（server/*/vendors/）：負責「廠商規格轉換」（被測系統內部）。
- Scenario/Runner（本模組）：負責「案例編排」（發砲端，產生結構化 CaseResult）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# 案例與 Run 的狀態枚舉（字串常數，方便序列化）
CASE_PASS = "PASS"
CASE_FAIL = "FAIL"
CASE_SKIP = "SKIP"
RUN_QUEUED = "QUEUED"
RUN_RUNNING = "RUNNING"
RUN_DONE = "DONE"
RUN_PARTIAL_FAIL = "PARTIAL_FAIL"


@dataclass
class RunContext:
    """單次 Run 的執行環境快照。Runner 拿它來知道打哪、帶什麼 header/params。"""
    environment: str                 # e.g. "LOCAL_OFFLINE" / "REAL_UG"
    use_real: bool                   # config.USE_REAL_SERVER 對應值
    base_url: str                    # 該環境對外的基底 URL（LOCAL 時為 ngrok）
    headers: dict                    # 該環境的鑑別/內容 header
    params_parking: dict             # 停車模組的 query params（含 thirdParty）
    params_amenity: dict             # 房務模組的 query params（含 thirdParty）
    # 預先解析好的端點 URL，runner 直接取用，避免各自重算
    urls: dict = field(default_factory=dict)
    # 逐步 HTTP 交易錄製槽：execute_for_ctx 每發一筆就 append 一個 step dict。
    # engine 在每個案例執行前重置、執行後拷進 CaseResult.steps（ctx 跨案例共用故需重置）。
    recorder: list = field(default_factory=list)


@dataclass
class Scenario:
    """一個可被編排的測試案例中繼資料 + 執行器。

    runner=None 表示該案例「已登錄但尚無執行器」��UNIMPLEMENTED），
    /scenarios 會標記給 UI 顯示「待開發」，不阻塞其他案例。
    """
    id: str                          # 全域唯一，如 "amenity_charge"
    module: str                      # "parking" / "amenity" / "keycard"
    vendor: str                      # "SHIN_YEONG" / "BR_AIELLO" / ...
    name: str                        # 中文顯示名
    endpoint: str                    # 對應路由（展示用）
    runner: Optional[Callable[[RunContext], "CaseResult"]] = None
    expected_key: Optional[str] = None  # 對應 verified_payload_logs 的 scenario 名（diff 期望值索引）

    @property
    def implemented(self) -> bool:
        return self.runner is not None


@dataclass
class CaseResult:
    """單一案例執行結果（對齊 spec §7 Case）。5 個結果檢視都讀這一份。"""
    case_id: str
    run_id: str
    module: str
    vendor: str
    scenario_name: str
    endpoint: str
    status: str = CASE_SKIP          # PASS / FAIL / SKIP
    duration_ms: int = 0
    request_payload: Any = None
    response_payload: Any = None
    expected_payload: Any = None
    diff: list = field(default_factory=list)          # [{field, expected, actual}, ...]
    error_category: Optional[str] = None              # FIELD_MISMATCH / STATUS_CODE / TIMEOUT / UNIMPLEMENTED
    # 逐步 HTTP 交易紀錄（UI 的「HTTP 稽核」檢視來源）：每筆含 method/url/請求/回應/計時/錯誤。
    steps: list = field(default_factory=list)


@dataclass
class Run:
    """一次測試執行的摘要（對齊 spec §7 Run）。"""
    run_id: str
    triggered_at: str                # ISO 時間字串
    environment: str
    status: str = RUN_QUEUED         # QUEUED / RUNNING / DONE / PARTIAL_FAIL
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    duration_ms: int = 0
    cases: list = field(default_factory=list)         # List[CaseResult]

    def recompute(self):
        """重算 pass/fail/total/duration 計數。

        刻意不碰 ``status``：本方法在逐案 append 後被呼叫，若於此翻成 DONE 會讓
        UI 在第一案完成後就誤判「整批完成」並停止 polling（其餘案例結果永遠進不來）。
        終局狀態由執行緒於「全部案例跑完」後以 :meth:`finalize_status` 設定一次。
        """
        self.total_cases = len(self.cases)
        self.passed = sum(1 for c in self.cases if c.status == CASE_PASS)
        self.failed = sum(1 for c in self.cases if c.status == CASE_FAIL)
        self.duration_ms = sum(c.duration_ms for c in self.cases)

    def finalize_status(self):
        """全部案例執行完畢後決定 Run 終局狀態（failed=0 → DONE，否則 PARTIAL_FAIL）。"""
        self.status = RUN_DONE if self.failed == 0 else RUN_PARTIAL_FAIL
