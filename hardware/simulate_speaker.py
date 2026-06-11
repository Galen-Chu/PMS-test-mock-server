# hardware/simulate_speaker.py
import sys
import os
import time
from datetime import datetime
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# 🎯 全量引用 config 模組化變數作為核心維護機制
USE_REAL = config.USE_REAL_SERVER
HEADERS = config.CURRENT_HEADERS_BACCHUS    # 💡 完美對齊全域大一統標頭
BASE_PARAMS = config.CURRENT_PARAMS_AMENITY # 💡 完美對齊全域大一統小美犀參數

def print_banner(title):
    print("\n" + "="*70)
    print(f" 🦏 [小美犀 BR 物聯網模擬器] >>> {title}")
    print("="*70)

def run_smart_hotel_scenario():
    print_banner("大一統參數拆分注入模式 ➔ 小美犀實戰開跑")
    
    # 🎯 業務資料流對齊核心：使用唯一情境房號變數橫向貫穿兩大階段
    test_room = "101"       
    unique_order = f"BR-ORD-{datetime.now().strftime('%m%d%H%M%S')}" 
    
    # ----------------------------------------------------------------
    # 🎯 階段一：小美犀智慧音箱「語音房號身分查驗」 (GET)
    # ----------------------------------------------------------------
    print(f"\n[Phase 1] 🚀 模擬音箱發動 GET 房號身分查驗... (目標房號: {test_room})")
    
    get_url = config.REAL_URL_BR_ROOM_NOS if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-pay/room-nos"
    get_params = {**BASE_PARAMS, "keyword": test_room} # 🎯 自動解耦拼接成 ?thirdParty=BR&keyword=101
    
    print(f" 📡 目標網址: {get_url}")
    print(f" 📋 注入 Params: {get_params}")
    
    try:
        res1 = requests.get(get_url, params=get_params, headers=HEADERS, timeout=8)
        print(f" 📥 [德安回應碼]: HTTP {res1.status_code}")
        if res1.status_code == 200:
            print(" 🟢 [驗證成功] 真實雲端認證通過！")
            print(res1.text[:300])
        else:
            print(f" 🛑 [驗證失敗]: {res1.text}")
            return
    except Exception as e:
        print(f" 🚨 [網路層崩潰]: {e}")
        return

    time.sleep(1.5) # 給予 Staging/沙盒環境充足的緩衝物理時間

    # ----------------------------------------------------------------
    # 🎯 階段二：房務部衍生入帳「獨立房務備品入帳」 (POST)
    # ----------------------------------------------------------------
    print(f"\n[Phase 2] 🚀 模擬機器人送達，發動 POST 房務備品入帳... (對齊情境房號: {test_room})")
    
    post_url = config.REAL_URL_BR_BILLING if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-billing"
    
    # 💡 數據流對齊：徹底拔除不相關的 2403 房號，自動繼承 Phase 1 的 test_room
    billing_payload = {
        "roomNos": str(test_room),  # 🎯 完美對齊同一個業務情境
        "items": [
            {
                "seqNos": 1,
                "productNos": "M001",
                "orderQuantity": 1
            }
        ]
    }
    
    print(f" 📡 目標網址: {post_url}")
    print(f" 📋 注入 Params: {BASE_PARAMS}")
    print(f" 📦 砸入 Body: {billing_payload}")
    
    try:
        res2 = requests.post(post_url, params=BASE_PARAMS, json=billing_payload, headers=HEADERS, timeout=8)
        print(f" 📥 [德安回應碼]: HTTP {res2.status_code}")
        
        # 🎯 核心傳輸優化點：相容德安的 200 (有回執) 與 204 (無內容但落帳成功) 雙軌旗標
        if res2.status_code in [200, 204]:
            print(f" 🟢 [房務入帳驗證成功] 實時扣款完美通關！")
            print(f"   ℹ️ 財務稽核狀態: HTTP {res2.status_code} 代表德安已成功受理、拆帳並過帳至房號 【{test_room}】。")
        else:
            print(f" 🛑 [房務入帳失敗]: {res2.text if res2.text else '德安回絕，且未提供錯誤內文'}")
    except Exception as e:
        print(f" 🚨 [網路層崩潰]: {e}")

if __name__ == "__main__":
    run_smart_hotel_scenario()