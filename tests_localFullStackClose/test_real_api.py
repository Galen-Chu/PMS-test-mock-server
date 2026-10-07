# test_real_api.py
import os
import sys

import pytest
import requests

# 確保專案根目錄在 sys.path,讓 `pytest`(非 `python -m pytest`)也能 import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402  💡 引入我們的設定檔

# 真實雲端測試:只在指向 REAL_QA / REAL_UG 時執行(同 test_real_scenario.py 慣例),
# 避免本地沙盒或 CI(LOCAL_OFFLINE)誤觸對外發砲
_REAL_ONLY = pytest.mark.skipif(
    not config.USE_REAL_SERVER,
    reason="僅在 ENV_SWITCH 指向 REAL_* 雲端時執行。",
)


@_REAL_ONLY
def test_car_arrival_integration():
    """整合測試：廠商→PMS 車輛抵達端點（依 ENV_SWITCH 輪替 REAL_QA / REAL_UG 雲端網址）"""

    headers = {
        "Authorization": config.CURRENT_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "guest_id": "G12345",
        "car_number": "ABC-1234",
        "guest_name": "Galen Chu",
        "arrival_time": "2026-05-25 16:30:00"
    }

    # 發送請求（自動帶入對應環境的 URL、Headers 與 Params）
    response = requests.post(
        config.REAL_URL_CAR_ARRIVAL,
        json=payload,
        headers=headers,
        params=config.CURRENT_PARAMS_PARKING
    )

    print(f"\n[目前測試環境]: {'真實雲端' if config.USE_REAL_SERVER else '本地 Flask'}")
    print(f"[伺服器回應狀態碼]: {response.status_code}")
    print(f"[伺服器回應內容]: {response.text}")

    # 斷言驗證
    assert response.status_code == 200
