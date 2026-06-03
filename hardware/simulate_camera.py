# hardware/simulate_camera.py (全自動批次迴圈連發版)
import sys
import os
# 💡 同步進行路徑防禦
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import config  # 💡 完美引入全域設定檔
from datetime import datetime
import time

# 統一經由 NGROK 或本地端點進行內部通訊
URL_GET_WHITELIST = f"{config.NGROK_BASE_URL}/internal/debug/whitelist"
URL_CAR_ARRIVAL = f"{config.NGROK_BASE_URL}/external/vendor-sync-data/car-arrival"
LOCAL_TOKEN = config.LOCAL_TOKEN

def batch_trigger_camera():
    headers = {
        "Authorization": LOCAL_TOKEN,
        "Content-Type": "application/json"
    }
    
    # 🔄 1. 核心優化：直接從 mock_server.py 匯入暫存資料庫的全部資料
    print("📡 [相機自動匯入] 正在向本地模擬 Server 撈取暫存資料庫...")
    try:
        res = requests.get(URL_GET_WHITELIST, timeout=5)
        db_data = res.json() if res.status_code == 200 else {}
        
        if not db_data:
            print("\n📭 [提示] 當前本地暫存資料庫內沒有任何住客資料！")
            print("💡 請在真實 PMS 網頁上對今日訂單做日常修改，讓真實 Webhook 資料流進 Flask 後，再來執行我。")
            return
            
        total_records = len(db_data)
        print(f"✅ [成功匯入] 共計撈出 {total_records} 筆住客白名單，開始迴圈車辨連發...\n")
        print("============================================================================")
        
    except Exception as e:
        print(f"❌ 匯入暫存資料庫失敗: {e}")
        return

    # 🎯 2. 核心重構：利用 for 迴圈將所有資料撈出來依序回傳
    success_count = 0
    for index, target_guest in enumerate(db_data.values(), start=1):
        guest_id = target_guest["guest_id"]
        car_number = target_guest["car_number"]
        guest_name = target_guest["guest_name"]
        
        print(f"🚗 【批次車辨中 {index}/{total_records}】")
        print(f" 📸 [相機感應] 逼逼！地感線圈觸發！")
        print(f" 📷 辨識結果 ➔ 姓名: {guest_name} | ID: {guest_id} | 車牌: {car_number}")
        
        # 🎯 毫無誤差，每一筆都封裝當前時間，確保對齊 4 規格 Payload
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "guest_id": guest_id,
            "car_number": car_number,
            "guest_name": guest_name,
            "arrival_time": current_time
        }
        
        try:
            print(f" 📡 正在發送車辨結果至廠商 Server...")
            response = requests.post(URL_CAR_ARRIVAL, json=payload, headers=headers, timeout=5)
            print(f" 📥 [廠商 Server 回應狀態碼]: {response.status_code} | {response.text}")
            
            if response.status_code == 200:
                success_count += 1
                
        except Exception as e:
            print(f" ❌ 傳送車辨事件發生異常: {e}")
            
        print("----------------------------------------------------------------------------")
        time.sleep(0.5)  # 稍微停頓，保護 ngrok 隧道頻率

    print(f"\n🎉 【批次連發結束】成功處理 {success_count} / {total_records} 筆車辨數據同步！")

if __name__ == "__main__":
    batch_trigger_camera()