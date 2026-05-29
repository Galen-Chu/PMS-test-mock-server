# test_local_scenario.py
import pytest
import requests

# 定義本地兩個不同的 API 端點
URL_PMS_TO_VENDOR = "http://127.0.0.1:5000/vendor/pms-sync-data/check-in"
URL_VENDOR_TO_PMS = "http://127.0.0.1:5000/external/vendor-sync-data/car-arrival"

MOCK_TOKEN = "Bearer eyJhbGciOiJSUzI1Ni..."

def test_full_hotel_stay_scenario():
    """
    【情境整合測試】
    目標：驗證從住客 Check-in 到車輛抵達的完整雙向資料鏈
    """
    # 測試用的共享資料（Stateful Data）
    shared_guest_id = "G-TAIWAN-2026"
    shared_car_number = "ABC-8888"
    
    print("\n\n=== [開始執行：完整使用者場景自動化測試] ===")

    # ----------------------------------------------------
    # 階段一：Pytest 模擬 PMS 發送住客資料給外部廠商 (Check-in)
    # ----------------------------------------------------
    checkin_payload = {
        "guest_id": shared_guest_id,
        "room_no": "606",
        "guest_name": "Galen Chu"
    }
    
    print(f"\n[步驟 1] Pytest 模擬 PMS 系統發出 Check-in 通知...")
    response_1 = requests.post(URL_PMS_TO_VENDOR, json=checkin_payload)
    
    # 斷言：廠商伺服器必須要成功收件並回傳 200
    assert response_1.status_code == 200
    assert response_1.json()["status"] == "success"
    print("-> 步驟 1 成功：外部廠商已成功為住客建立白名單。")

    # ----------------------------------------------------
    # 階段三：Pytest 模擬外部廠商辨識到車牌，回傳車辨資訊給 PMS
    # ----------------------------------------------------
    car_payload = {
        "guest_id": shared_guest_id,      # 💡 關鍵：帶入同一個識別碼才能串起來
        "car_number": shared_car_number,
        "arrival_time": "2026-05-25 18:00:00"
    }
    headers = {
        "Authorization": MOCK_TOKEN,
        "Content-Type": "application/json"
    }
    
    print(f"\n[步驟 2] Pytest 模擬車牌辨識硬體觸發，發送車輛抵達資料回 PMS...")
    response_2 = requests.post(URL_VENDOR_TO_PMS, json=car_payload, headers=headers)
    
    # 斷言：PMS 必須成功收件
    assert response_2.status_code == 200
    assert response_2.json()["status"] == "success"
    print(f"-> 步驟 2 成功：車牌 [{shared_car_number}] 與住客狀態已在 PMS 完成閉環閉鎖！")