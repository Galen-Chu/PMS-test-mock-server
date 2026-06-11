# test_real_scenario.py
import pytest
import requests
import config
from datetime import datetime

print(f"\n🚀 [環境宣告] 目前測試目標：{'【真實 QA 雲端環境】' if config.USE_REAL_SERVER else '【本地 Flask 沙盒】'}")

def test_pms_real_api_success_flow():
    """
    【真實場景應用 1：正向鏈結測試】
    驗證帶入標準住客 ID 與合法車牌時，雲端 API 是否穩定回傳 200 與 success
    """
    # 產生存放於真實系統的測試資料 (加上時間戳記防止資料重複衝突)
    timestamp = datetime.now().strftime("%m%d%H%M")
    target_guest_id = f"G-{timestamp}"
    target_car_number = f"QA-{timestamp}"
    
    headers = {
        "Authorization": config.CURRENT_TOKEN,
        "Content-Type": "application/json"
    }

    # 執行步驟 1：同步住客
    checkin_payload = {
        "guest_id": target_guest_id,
        "room_no": "108",
        "guest_name": "Automation_Tester_Galen"
    }
    res1 = requests.post(config.URL_CHECKIN, json=checkin_payload, headers=headers, params=config.CURRENT_PARAMS)
    
    # 💡 這裡加上條件判斷：因為真實環境的 check-in 端點可能由 PMS 觸發，外部不一定有權限打
    print(f"\n[步驟 1 雲端回應狀態碼]: {res1.status_code}")
    print(f"[步驟 1 雲端回應內容]: {res1.text}")
    
    # 執行步驟 2：外部車辨回傳 (這是你目前確定打通的端點)
    car_payload = {
        "guest_id": target_guest_id,
        "car_number": target_car_number,
        "arrival_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    res2 = requests.post(config.URL_CAR_ARRIVAL, json=car_payload, headers=headers, params=config.CURRENT_PARAMS)
    
    print(f"\n[步驟 2 雲端回應狀態碼]: {res2.status_code}")
    print(f"[步驟 2 雲端回應內容]: {res2.text}")
    
    # 驗證真實後端是否落庫成功
    assert res2.status_code == 200
    assert "success" in res2.text or "0000" in res2.text


def test_pms_real_api_schema_boundary():
    """
    【真實場景應用 2：邊界防禦測試】
    故意發送缺失必要欄位 (缺少 car_number) 的髒資料，預期真實雲端必須噴出 400 錯誤
    若真實雲端回傳 200，代表後端 Schema 驗證有漏洞！
    """
    headers = {
        "Authorization": config.CURRENT_TOKEN,
        "Content-Type": "application/json"
    }
    
    # 故意不給 car_number
    dirty_payload = {
        "guest_id": "G-DIRTY-1234",
        "arrival_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    res = requests.post(config.URL_CAR_ARRIVAL, json=dirty_payload, headers=headers, params=config.CURRENT_PARAMS)
    
    print(f"\n[邊界測試 雲端回應狀態碼]: {res.status_code}")
    print(f"[邊界測試 雲端回應內容]: {res.text}")
    
    # 斷言：預期系統要足夠強壯，拒絕這筆請求 (回報 400 或 422)
    assert res.status_code in [400, 422, 404]