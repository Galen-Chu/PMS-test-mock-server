import pytest
import requests
import responses  # 引入 Mock 工具

# 被測試的函數：模擬系統呼叫外部 API 的邏輯
def send_car_arrival_data(token, payload):
    url = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/external/vendor-sync-data/car-arrival"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    # 這行是關鍵！responses 會攔截這個 requests.post
    response = requests.post(url, json=payload, headers=headers)
    return response

# 測試案例 1：模擬「成功傳送 (200)」的情境
@responses.activate # 啟動 Mock 攔截器
def test_api_success_behavior():
    target_url = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/external/vendor-sync-data/car-arrival"
    
    # 設定 Mock 代理人：只要看到有人打這個 URL，就給我回傳 200 與指定的 JSON
    responses.add(
        responses.POST, 
        target_url,
        json={"status": "success", "message": "Car arrival recorded"},
        status=200
    )

    # 執行測試
    test_payload = {"guest_id": "G12345", "car_number": "ABC-1234"}
    res = send_car_arrival_data("fake_token_123", test_payload)

    # 斷言 (Assert) 驗證
    assert res.status_code == 200
    assert res.json()["status"] == "success"

# 測試案例 2：模擬「驗證失敗 (401)」的情境（呼應你之前的踩坑經驗！）
@responses.activate
def test_api_unauthorized_behavior():
    target_url = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/external/vendor-sync-data/car-arrival"
    
    # 設定 Mock 代理人：這次模擬過期或錯誤的 Token 導致 401
    responses.add(
        responses.POST,
        target_url,
        body="Unauthorized Access",
        status=401
    )

    test_payload = {"guest_id": "G12345", "car_number": "ABC-1234"}
    res = send_car_arrival_data("expired_token_xyz", test_payload)

    # 驗證你的程式是否能正確捕捉並識別 401 狀態
    assert res.status_code == 401