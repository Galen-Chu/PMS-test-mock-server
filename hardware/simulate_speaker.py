# hardware/simulate_speaker.py
import sys
import os
import time
from datetime import datetime
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

USE_REAL = config.USE_REAL_SERVER
HEADERS = config.CURRENT_HEADERS_BACCHUS
BASE_PARAMS = config.CURRENT_PARAMS_AMENITY

def print_banner(title):
    print("\n" + "="*70)
    print(f" 🦏 [小美犀物聯網模擬器] >>> {title}")
    print("="*70)

# ====================================================================
# 🎬 情境一：標準智慧音箱下單 ➔ 派送機器人送達財務落帳生命週期
# ====================================================================
def run_scenario_one_robot_delivery(target_room=""):
    print_banner(f"【情境一】 智慧音箱語音點餐 ➔ 機器人實體送餐入帳流 (目標房號: {target_room})")
    
    # --- 階段一：GET 房號身分與權限查驗 (動態提取測資) ---
    print(f"\n[Phase 1] 🤖 機器人出車前，向沙盒發動 GET 認證房號 【{target_room}】...")
    get_url = config.REAL_URL_BR_ROOM_NOS if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-pay/room-nos"
    get_params = {**BASE_PARAMS, "keyword": target_room}
    
    try:
        res1 = requests.get(get_url, params=get_params, headers=HEADERS, timeout=8)
        if res1.status_code != 200:
            print(f" 🛑 [認證終止] 沙盒或德安拒絕該房號。原因: {res1.text}")
            return
            
        # 🎯 核心突破：動態資產繼承！直接從回傳的 JSON 陣列中剝離出真實的住客序號
        guest_data_list = res1.json()
        dynamic_ci_serial = guest_data_list[0].get("checkInSerial")
        dynamic_guest_name = guest_data_list[0].get("altName")
        
        print(f" 🟢 [認證通過] 成功攔截並繼承動態測資！")
        print(f"   👤 住客姓名: {dynamic_guest_name} | 🔑 真實住客序號(ciSerial): 【{dynamic_ci_serial}】")
        
    except Exception as e:
        print(f" 🚨 [網路層崩潰]: {e}")
        return

    time.sleep(1.5)

    # --- 階段二：POST 餐廳消費住掛房間帳 (使用剛剛繼承的測資) ---
    print(f"\n[Phase 2] 🤖 機器人抵達房間，住客簽收！發動 POST 實時入帳...")
    post_url = config.REAL_URL_BR_ROOM_PAY if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-pay"
    unique_order_nos = f"BR-ORD-{datetime.now().strftime('%m%d%H%M%S')}"
    
    # 🌟 完美將第一階段動態撈到的房號與住客序號，無縫灌入 Payload！
    room_pay_payload = {
        "roomPayMain": {
            "ciSerial": dynamic_ci_serial, # 💡 動態繼承
            "roomNos": target_room,         # 💡 動態繼承
            "orderNos": unique_order_nos,
            "needTransfer": "N",
            "rsptCode": "BUFFET",
            "rsptName": "自助餐",
            "mTimeCode": "LUNCH",
            "mTimeName": "午餐",
            "deskNos": "ROBOT-101",
            "payAmount": 680.00, # 情境一模擬送一客豪華簡餐
            "custType": "ADULT",
            "acuAmount": 0.00,
            "precreditTotal": 0.00
        },
        "roomPayDetail": [
            {"sequenceNos": 1, "productName": "機器人派送頂級牛排", "orderQuantity": 1, "specialAmount": 680.00, "precreditAmount": 0.00}
        ]
    }
    
    print(f" 🚀 正在發射過帳 Payload，憑證單號: {unique_order_nos}...")
    try:
        res2 = requests.post(post_url, params=BASE_PARAMS, json=room_pay_payload, headers=HEADERS, timeout=8)
        print(f" 📥 [Server 回應碼]: HTTP {res2.status_code}")
        if res2.status_code == 200:
            print(f" 🟢 [情境一通關成功] 德安會計傳票單號: 【{res2.json().get('acctNos')}】")
        else:
            print(f" 🛑 [落帳失敗]: {res2.text}")
    except Exception as e:
        print(f" 🚨 [過帳網路崩潰]: {e}")

if __name__ == "__main__":
    # ⚡ 執行測試：拿你在 Swagger 跑通的 101 真實房號開砲，體驗 100% 動態繼承的流暢感
    run_scenario_one_robot_delivery(target_room="104")