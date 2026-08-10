# test_real_scenario.py
import os
import sys
import pytest
import requests
from datetime import datetime

# 確保專案根目錄在 sys.path,讓 `pytest`(非 `python -m pytest`)也能 import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

print(f"\n🚀 [環境宣告] 目前測試目標：{'【真實雲端環境】' if config.USE_REAL_SERVER else '【本地 Flask 沙盒】'}")

# 真實雲端測試:只在指向 REAL_QA / REAL_UG 時執行,避免本地沙盒或 CI 誤觸對外發砲
_REAL_ONLY = pytest.mark.skipif(
    not config.USE_REAL_SERVER,
    reason="僅在 ENV_SWITCH 指向 REAL_* 雲端時執行。",
)


@_REAL_ONLY
def test_pms_real_api_success_flow():
    """
    【真實場景應用 1:正向鏈結測試】
    驗證帶入標準住客 ID 與合法車牌時,雲端車辨回傳 API 是否穩定回傳 200。

    注意:check-in(住客同步)屬 PMS→廠商方向,目前 sandbox 無對真實雲端的
    check-in 寫入權限,故本測試僅覆蓋廠商→PMS 的車辨抵達端點。
    """
    timestamp = datetime.now().strftime("%m%d%H%M")
    target_guest_id = f"G-{timestamp}"
    target_car_number = f"QA-{timestamp}"

    headers = {
        "Authorization": config.CURRENT_TOKEN,
        "Content-Type": "application/json",
    }

    # 廠商→PMS:車牌辨識回傳車輛抵達
    car_payload = {
        "guest_id": target_guest_id,
        "car_number": target_car_number,
        "arrival_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    res = requests.post(
        config.REAL_URL_CAR_ARRIVAL,
        json=car_payload,
        headers=headers,
        params=config.CURRENT_PARAMS_PARKING,
    )

    print(f"\n[車辨回傳 雲端回應狀態碼]: {res.status_code}")
    print(f"[車辨回傳 雲端回應內容]: {res.text}")

    # 驗證真實後端是否落庫成功
    assert res.status_code == 200
    assert "success" in res.text or "0000" in res.text


@_REAL_ONLY
def test_pms_real_api_schema_boundary():
    """
    【真實場景應用 2:邊界防禦測試】
    故意發送缺失必要欄位(缺少 car_number)的髒資料,預期真實雲端必須拒絕(400 / 422)。
    若真實雲端回傳 200,代表後端 Schema 驗證有漏洞!
    """
    headers = {
        "Authorization": config.CURRENT_TOKEN,
        "Content-Type": "application/json",
    }

    # 故意不給 car_number
    dirty_payload = {
        "guest_id": "G-DIRTY-1234",
        "arrival_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    res = requests.post(
        config.REAL_URL_CAR_ARRIVAL,
        json=dirty_payload,
        headers=headers,
        params=config.CURRENT_PARAMS_PARKING,
    )

    print(f"\n[邊界測試 雲端回應狀態碼]: {res.status_code}")
    print(f"[邊界測試 雲端回應內容]: {res.text}")

    # 斷言:預期系統要足夠強壯,拒絕這筆請求
    assert res.status_code in [400, 422, 404]
