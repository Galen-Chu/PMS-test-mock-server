# test_real_api.py
import pytest
import requests
import config # 💡 引入我們的設定檔

def test_car_arrival_integration():
    """整合測試：根據 config 設定，動態切換打本地或真實環境"""
    
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
        config.CURRENT_URL, 
        json=payload, 
        headers=headers, 
        params=config.CURRENT_PARAMS
    )
    
    print(f"\n[目前測試環境]: {'真實雲端' if config.USE_REAL_SERVER else '本地 Flask'}")
    print(f"[伺服器回應狀態碼]: {response.status_code}")
    print(f"[伺服器回應內容]: {response.text}")
    
    # 斷言驗證
    assert response.status_code == 200