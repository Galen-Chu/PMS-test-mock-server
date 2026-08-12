# orchestrator/__init__.py
"""測試編排層：可註冊的情境 + Run/Case 模型 + Flask API。

import 本套件即觸發 runners 註冊（裝飾器副作用）。
"""
from .models import (  # noqa: F401
    Scenario, RunContext, CaseResult, Run,
    CASE_PASS, CASE_FAIL, CASE_SKIP,
    RUN_QUEUED, RUN_RUNNING, RUN_DONE, RUN_PARTIAL_FAIL,
)
from .registry import registry, register_scenario  # noqa: F401
from . import engine  # noqa: F401

# 觸發案例註冊（runner 模組內的 @register_scenario / register_unimplified 副作用）
from . import runners  # noqa: F401
