# tests_localFullStackClose/test_local_sandbox.py
"""沙盒核心離線單元測試。

完全離線、離網:不需要 Flask 伺服器,也不對外發送任何請求。
供 dashboard「內部閉環測試報告」分頁的 Pytest 按鈕,以及 CI pipeline 使用。
"""
import os
import sys

# 確保專案根目錄在 sys.path,讓 `pytest`(非 `python -m pytest`)也能 import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def test_env_matrix_completeness():
    """每個環境矩陣 entry 必須齊備基底 URL / Token / 識別碼 / Headers,
    否則 dashboard 動態切環境時會因缺欄位而炸掉。"""
    required = {"BASE_URL_EXTERNAL", "TOKEN", "ATHENA_ID", "HOTEL_COD", "HEADERS"}
    for env_name, env_cfg in config.ENV_MATRIX.items():
        missing = required - set(env_cfg.keys())
        assert not missing, f"ENV_MATRIX['{env_name}'] 缺少欄位: {missing}"


def test_real_envs_carry_bacchus_identity():
    """REAL 環境採無 Token 鑑別,Headers 必須帶 bacchus-athenaid / bacchus-hotelcod——
    這是雲端識別旅館的唯一依據(REAL_UG 已實測驗證此機制可行)。"""
    for env_name in ("REAL_QA", "REAL_UG"):
        headers = config.ENV_MATRIX[env_name]["HEADERS"]
        assert "bacchus-athenaid" in headers, f"{env_name} 缺 bacchus-athenaid"
        assert "bacchus-hotelcod" in headers, f"{env_name} 缺 bacchus-hotelcod"


def test_simulator_imports_cleanly():
    """simulate_speaker 必須能乾淨 import。過去曾因 config 屬性重構後,整支模組
    import 即炸,連帶讓所有引用它的測試與 dashboard 一起壞掉——本測試守護此迴歸。"""
    from hardware import simulate_speaker as ss

    assert callable(ss.run_all_expanded_scenarios)
    assert callable(ss.execute_request)
