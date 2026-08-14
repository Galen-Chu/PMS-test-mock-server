import pytest
import requests
import config

# 本機 Mock Server 的網址
CHECKIN_URL = "http://127.0.0.1:5000/pms-sync-data/check-in"
BASE_URL = "http://127.0.0.1:5000/external/vendor-sync-data/car-arrival"
# 💡 沙盒實際驗證的是裸字串 Token（比照 hardware/simulate_camera.py 的用法），不帶 "Bearer " 前綴
MOCK_TOKEN = config.LOCAL_TOKEN

def test_car_arrival_success():
    """測試案例 1：帶入正確 Token 與 JSON 格式，預期成功 (200)"""
    # 車輛抵達前，車辨白名單必須先存在該住客（比照真實 CKI Webhook 流程）
    requests.post(CHECKIN_URL, json={
        "guest_id": "G12345",
        "car_number": "ABC-1234",
        "guest_name": "Galen Chu"
    })

    headers = {
        "Authorization": MOCK_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "guest_id": "G12345",
        "car_number": "ABC-1234",
        "guest_name": "Galen Chu",
        "arrival_time": "2026-05-25 15:30:00"
    }

    response = requests.post(BASE_URL, json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["code"] == "0000"  # 💡 SA v1.2 回應格式 {code, message}

def test_car_arrival_unauthorized():
    """測試案例 2：故意帶入錯誤的 Token，預期被攔截 (401)"""
    headers = {
        "Authorization": "Bearer wrong_token_xyz",
        "Content-Type": "application/json"
    }
    payload = {"guest_id": "G12345", "car_number": "ABC-1234"}
    
    response = requests.post(BASE_URL, json=payload, headers=headers)
    
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["error"]