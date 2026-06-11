# test_real_official_scenario.py
import pytest
import requests
import config
from datetime import datetime

print(f"\n🚀 [真實官方 Schema 攻堅] 目前目標環境：{'【真實 QA 雲端】' if config.USE_REAL_SERVER else '【本地 Flask】'}")

def test_official_pms_checkin_and_car_arrival_flow():
    # ----------------------------------------------------------------===
    # 【官方真實 Schema 聯調測試】
    # 步驟 1：發送官方格式的複雜 JSON 到 /pms-sync-data/check-in
    # 步驟 2：提取步驟 1 的關鍵識別碼，發送至 /car-arrival 完成資料鏈閉環
    # ----------------------------------------------------------------===
    # --- 動態測資產生器 (動態產生流水號，避免真實資料庫唯一鍵衝突) ---
    timestamp_serial = datetime.now().strftime("%Y%m%d%H%M%S")
    dynamic_ci_serial = f"CI-{timestamp_serial}" 
    dynamic_car_no = "QA-8888"
    current_date = datetime.now().strftime("%Y-%m-%d")

    headers = {
        "Authorization": config.CURRENT_TOKEN,
        "Content-Type": "application/json"
    }

    # ----------------------------------------------------------------===
    # 步驟 1：完整帶入官方真實 Swagger 提供的 Request Body
    # ----------------------------------------------------------------===
    official_checkin_payload = {
        "roomNos": "101",          # 💡 根據官方測資，這裡是房號的欄位名稱，不是 room_no
        "roomSerial": "1",
        "ikey": "00002510",
        "ikeySeqNos": 1,
        "ciSerial": dynamic_ci_serial,  # 💡 核心識別碼 1 ，動態變數
        "altName": "德安先生_自動化測試",
        "saluteName": "小姐",
        "saluteType": "1",
        "firstName": "安",
        "lastName": "德",
        "ciDate": current_date,
        "ecoDate": current_date,
        "langCode": "zh_TW",
        "langName": "繁體中文",
        "vipStatus": "1",
        "ciTime": datetime.now().strftime("%H:%M:%S"),
        "infoIsGroup": "Y",
        "infoRemark": "Pytest 自動化測試生成",
        "eciTime": "1500",
        "ecoTime": "1200",
        "carNos": dynamic_car_no,
        # 💡 巢狀物件處理
        "parkingSyncData": {
            "ciSer": dynamic_ci_serial, # 💡 核心識別碼 2 ，動態變數 (必須與外部相同)
            "carNos": dynamic_car_no,
            "altName": "德安先生_自動化測試",
            "ciDate": current_date,
            "acoDate": current_date,
            "enabled": True
        }
    }
    
    print(f"\n[步驟 1] 正在向官方 Check-in 端點發送複雜 JSON 資料...")
    print(f" -> 動態生成的 ciSerial: {dynamic_ci_serial}")
    
    res1 = requests.post(config.URL_CHECKIN, json=official_checkin_payload, headers=headers, params=config.CURRENT_PARAMS)
    
    print(f" -> 步驟 1 回應狀態碼: {res1.status_code}")
    print(f" -> 步驟 1 回應內容: {res1.text}")
    
    # 驗證步驟 1
    assert res1.status_code == 200

    # ----------------------------------------------------------------===
    # 步驟 2：呼叫車輛抵達 API (利用剛才 Check-in 的同一個唯一識別碼)
    # ----------------------------------------------------------------===
    # 💡 思考點：你的 /car-arrival API 原本預期的是 guest_id。
    # 根據官方的新欄位，請確認這裏是要帶入 ciSerial 還是 roomNos。這裡我們先以 ciSerial 作為關聯鍵。
    car_payload = {
        # 本地與真實腳本統一使用的真實 Payload 格式
        "guest_id": dynamic_ci_serial,
        "car_number": "QWE-5555",
        "guest_name": "Automation_Tester_Galen",
        "start_date": "2026/05/19 15:00",
        "end_date": "2026/05/20 15:00",
        "is_enabled": "Yes"
    }
    
    print(f"\n[步驟 2] 正在向車輛抵達端點發送回傳資料...")
    res2 = requests.post(config.URL_CAR_ARRIVAL, json=car_payload, headers=headers, params=config.CURRENT_PARAMS)
    
    print(f" -> 步驟 2 回應狀態碼: {res2.status_code}")
    print(f" -> 步驟 2 回應內容: {res2.text}")
    
    assert res2.status_code == 200
    print(f"\n🎉 [大功告成] 真實官方 Schema 雙向場景聯調成功！")