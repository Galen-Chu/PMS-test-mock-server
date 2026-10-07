# tests_localFullStackClose/conftest.py
"""共用測試前置。

server_up:本地沙盒在線探測——test_local_api / test_local_scenario / test_local_roomcontrol
皆需 Flask 沙盒(python main.py,監聽 127.0.0.1:5000)在線;未啟動時整檔自動 skip,
而非噴 ConnectionRefused 假紅(CI 的離線 job 亦靠此跳過 local 三檔)。
"""
import os
import sys

import pytest
import requests

# 讓 bare `pytest`(非 `python -m pytest`)也 import 得到專案根的 config——
# pytest 只把「測試目錄」掛上 sys.path,不含專案根(CI 即以 bare pytest 執行)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:5000"  # 與 local 三檔測試端點同源(main.py 固定監聽處)


@pytest.fixture(scope="module")
def server_up():
    """前置:本地沙盒須在線,否則整檔跳過(GET /scenarios 驗活,不只驗 port)。"""
    try:
        r = requests.get(f"{BASE}/scenarios", timeout=3)
        assert r.status_code == 200
    except Exception:
        pytest.skip("本地 Flask 沙盒未啟動(先 PYTHONUTF8=1 python main.py)")
    return True
