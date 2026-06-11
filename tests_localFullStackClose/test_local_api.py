import pytest
import requests

# 本機 Mock Server 的網址
BASE_URL = "http://127.0.0.1:5000/external/vendor-sync-data/car-arrival"
MOCK_TOKEN = "Bearer eyJhbGciOiJSUzI1Ni..."

def test_car_arrival_success():
    """測試案例 1：帶入正確 Token 與 JSON 格式，預期成功 (200)"""
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
    assert response.json()["status"] == "success"

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