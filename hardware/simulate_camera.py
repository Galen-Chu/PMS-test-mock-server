# hardware/simulate_camera.py (大一統架構 - 狀態感知與極簡時間戳版)
import sys
import os
# 💡 透過 __init__.py 建立的環境，此處可直接完美引入全域設定檔 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import config
import time

# 統一經由 NGROK 或本地端點進行內部通訊
# 依據 config 戰略開關，決定進攻真實德安雲端還是本地沙盒
USE_REAL = config.USE_REAL_SERVER
URL_GET_WHITELIST = config.LOCAL_GET_WHITELIST
URL_CAR_ARRIVAL = config.REAL_URL_CAR_ARRIVAL
LOCAL_TOKEN = config.LOCAL_TOKEN

def batch_trigger_camera():
    headers = {
        "Authorization": LOCAL_TOKEN,
        "Content-Type": "application/json"
    }
    
    print("📡 [相機自動匯入] 正在向大一統沙盒 Server 撈取最新白名單資料庫...")
    try:
        res = requests.get(URL_GET_WHITELIST, timeout=5)

        # 💡 增強防禦：如果不是 200，直接印出真實狀態碼（例如 404 或 500）
        if res.status_code != 200:
            print(f"🛑 [通訊攔截] 撈取失敗！Server 回應狀態碼: {res.status_code}，請檢查 URL: {URL_GET_WHITELIST}")
            return
        
        db_data = res.json()
        
        if not db_data:
            print("\n📭 [提示] 當前本地暫存資料庫內沒有任何住客資料！")
            return
            
        total_records = len(db_data)
        print(f"✅ [成功匯入] 共計撈出 {total_records} 筆住客紀錄，開始狀態機感知校準...\n")
        print("============================================================================")
        
    except Exception as e:
        print(f"❌ 匯入暫存資料庫失敗: {e}")
        return

    success_count = 0
    skipped_count = 0
    
    for index, (guest_id, target_guest) in enumerate(db_data.items(), start=1):
        car_number = target_guest.get("car_number", "")
        guest_name = target_guest.get("guest_name", "未帶姓名")
        
        # 🎯 配合狀態機進行邊緣端權限感知
        is_enabled = target_guest.get("enabled", True)
        
        print(f"🚗 【批次檢索中 {index}/{total_records}】-> 住客: {guest_name} | ID: {guest_id}")
        
        if not is_enabled:
            # 💡 實施反向驗證攔截：若已被 PMS 停用，在地防禦不發砲
            print(f" 🛑 [邊緣端隔離] 車牌 [{car_number}] 權限目前為【停用】狀態！")
            print(f"   ℹ️ 根因分析: 該旅客可能已取消入住(CIX)或已被前台清除車牌，相機拒絕開閘，不推播至 PMS。")
            skipped_count += 1
            print("----------------------------------------------------------------------------")
            continue

        print(f" 📸 [相機感應] 逼逼！地感線圈觸發！車牌 [{car_number}] 狀態確認為【啟用】")
        
        # 🎯 修正點 1：在相機觸發當下，動態生成真實德安要的標準橫線時間戳 (YYYY-MM-DD HH:mm:ss)
        from datetime import datetime
        current_arrival_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 🎯 修正點 2：將變數來源從錯誤的 local_guest 改為合法的 target_guest，確保資料不為空
        pms_car_payload = {
            "guest_id": str(guest_id),
            "car_number": str(car_number),
            "guest_name": str(guest_name),
            "arrival_time": current_arrival_time
        }
        
        api_headers = {
            "accept": "*/*",
            "bacchus-athenaid": str(config.active_cfg["ATHENA_ID"]),
            "bacchus-hotelcod": str(config.active_cfg["HOTEL_COD"]),
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://bacug.athena.com.tw/pms/swagger-ui/index.html",
            "Origin": "https://bacug.athena.com.tw"
        }

        # 🎯 修正點 3：直接確保路由後面有掛好廠商識別參數
        target_url = f"{config.REAL_URL_CAR_ARRIVAL}?thirdParty=SHIN_YEONG"

        try:
            print(f" 🚀 正在主動向 Server 發動逆向車辨轟炸...")
            print(f" 📦 [發送 Payload 核對]: {pms_car_payload}")

            response = requests.post(
                target_url, 
                json=pms_car_payload, 
                headers=api_headers, 
                timeout=5
            )
            print(f" 📥 [廠商 Server 回應]: 狀態碼 {response.status_code} | {response.text}")
            
            if response.status_code == 200:
                success_count += 1
                
        except Exception as e:
            print(f" ❌ 傳送車辨事件發生異常: {e}")
            
        print("----------------------------------------------------------------------------")
        time.sleep(0.5)  # 稍微停頓，保護 ngrok 隧道頻率

    print(f"\n🎉 【批次連發結束】")
    print(f" ✅ 成功發砲通關: {success_count} 筆")
    print(f" 🛑 邊緣安全防禦攔截: {skipped_count} 筆")
    print(f" 📊 總計處理解耦資料: {total_records} 筆")

if __name__ == "__main__":
    batch_trigger_camera()