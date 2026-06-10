# hardware/simulate_speaker.py
import sys
import os
import time
from datetime import datetime

# 💡 透過路徑防禦，精準引入根目錄的全域設定檔 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import requests

# 依據 config 戰略開關，決定進攻真實德安雲端還是本地沙盒
USE_REAL = config.USE_REAL_SERVER
URL_AMENITY = config.REAL_URL_AMENITY
# CURRENT_TOKEN = config.CURRENT_TOKEN

# 🚀 根據廠商代碼與飯店規範封裝大一統的 Parameters 查詢參數
# 真實德安雲端需要 hotel="01", athena="16", thirdParty="BR"
USE_PARAMS = config.CURRENT_PARAMS_AMENITY if USE_REAL else {}

def print_banner(title):
    print("\n" + "="*70)
    print(f" 🦏 [小美犀 BR 物聯網模擬器] >>> {title}")
    print("="*70)

def send_request(method, url_suffix, custom_params=None, json_body=None):
    """大一統通信發射引擎"""
    url = f"{URL_AMENITY}{url_suffix}"
    
    # 組合基本參數與客製化 URL 參數 (如 keyword, orderNos)
    final_params = {**USE_PARAMS}  # 基於 config 的核心參數
    if custom_params:
        final_params.update(custom_params)
        
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # 真實德安環境要求 athena 與 hotel 也要在 Header 內
    headers["athena"] = "16"
    headers["hotel"] = "01"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, params=final_params, headers=headers, timeout=8)
        else:
            response = requests.post(url, params=final_params, json=json_body, headers=headers, timeout=8)
            
        return response
    except Exception as e:
        print(f" 🚨 [網路層崩潰] 無法連線至目標伺服器: {e}")
        return None

# ====================================================================
# 🎬 腳本大一統流水線故事鏈 (Scenario Pipeline)
# ====================================================================
def run_smart_hotel_scenario():
    print_banner("智慧飯店語音備品與機器人派送全鏈路 Staging 測試開始")
    print(f" 📡 當前戰略進攻環境: 【{'真實德安 QA 雲端' if USE_REAL else '本地 Flask 沙盒'}】")
    print(f" 🔗 目標基底網址: {URL_AMENITY}")
    
    # 預設測試資產 (完美對齊前台規格)
    test_room = "101"       # 德安房務測試房
    test_mifare = "123456789" # 測試房卡卡號
    unique_order = f"BR-ORD-{datetime.now().strftime('%m%d%H%M%S')}" # 唯一單號资產
    
    # ----------------------------------------------------------------
    # 🎯 階段一：小美犀智慧音箱「語音房號身分查驗」 (GET)
    # ----------------------------------------------------------------
    print("\n[Phase 1] 客人對著音箱說：『小美犀，幫我點餐送到房。』")
    print(f" 📡 正在向 PMS 驗證房號 【{test_room}】 的客房住掛記帳權限...")
    
    res1 = send_request("GET", "/external/vendor-sync-data/room-pay/room-nos", {"keyword": test_room})
    if not res1 or res1.status_code != 200:
        print(f" 🛑 [驗證失敗] 德安攔截回傳碼: {res1.status_code if res1 else '無回應'} | 內容: {res1.text if res1 else ''}")
        return
        
    guest_info_list = res1.json()
    print(f" 🟢 [驗證成功] 真實雲端認證通過！")
    print(f"   👤 住客姓名: {guest_info_list[0].get('altName')} | 住客序號(ciSerial): {guest_info_list[0].get('checkInSerial')}")
    
    ci_serial = guest_info_list[0].get('checkInSerial')
    
    time.sleep(1)

    # ----------------------------------------------------------------
    # 🎯 階段二：實體販賣機/餐廳「刷房卡卡號查驗」 (GET)
    # ----------------------------------------------------------------
    print("\n[Phase 2] 客人移步到販賣機，刷實體房卡消費...")
    print(f" 📡 正在向 PMS 逆查房卡內碼 【{test_mifare}】 的住客狀態...")
    
    res2 = send_request("GET", "/external/vendor-sync-data/room-pay/mifare-nos", {"keyword": test_mifare})
    if res2 and res2.status_code == 200:
        print(f" 🟢 [房卡查核成功] 卡號綁定房號為: {res2.json()[0].get('roomNos')}")
    else:
        print(f" ℹ️ [提示] 房卡逆查未命中有色邊界（若為真實雲端需視 QA 環境有無該卡號對照）")

    time.sleep(1)

    # ----------------------------------------------------------------
    # 🎯 階段三：機器人送達，發動「餐廳消費住掛房帳」 (POST)
    # ----------------------------------------------------------------
    print(f"\n[Phase 3] 🤖 派送機器人抵達 {test_room} 房門口，客人取餐成功！")
    print(f" 🚀 機器人平台發動 POST 請求，將餐廳消費款項匯入房間 Folio 帳主檔...")
    print(f"   🔑 本次交易追溯唯一憑證單號 (orderNos): 【{unique_order}】")
    
    # 依據德安 Main & Detail 範例精準封裝 Request Body
    room_pay_payload = {
        "roomPayMain": {
            "ciSerial": ci_serial,
            "roomNos": test_room,
            "orderNos": unique_order,
            "needTransfer": "N",
            "rsptCode": "BUFFET",
            "rsptName": "自助餐",
            "mTimeCode": "LUNCH",
            "mTimeName": "午餐",
            "deskNos": "ROBOT-01",
            "payAmount": 500.00,
            "custType": "ADULT",
            "acuAmount": 0.00,
            "precreditTotal": 0.00
        },
        "roomPayDetail": [
            {
                "sequenceNos": 1,
                "productName": "小美犀派送牛排",
                "orderQuantity": 1,
                "specialAmount": 500.00,
                "precreditAmount": 0.00
            }
        ]
    }
    
    res3 = send_request("POST", "/external/vendor-sync-data/room-pay", json_body=room_pay_payload)
    if not res3 or res3.status_code != 200:
        print(f" 🛑 [扣款失敗] 財務落帳遭德安拒絕！狀態碼: {res3.status_code if res3 else '無'} | {res3.text if res3 else ''}")
        return
        
    pms_acct_nos = res3.json().get("acctNos")
    print(f" 🟢 [落帳成功] 實時扣款大獲全勝！")
    print(f"   💸 德安系統回傳之正式會計傳票單號 (acctNos): 【{pms_acct_nos}】")
    print("   💡 備忘：此時可登入德安網頁前台，點開 2403 房間帳，查驗這筆 $500 元是否在 Folio 內。")

    time.sleep(1.5)

    # ----------------------------------------------------------------
    # 🎯 階段四：房務部衍生入帳「獨立房務備品入帳」 (POST)
    # ----------------------------------------------------------------
    print(f"\n[Phase 4] 🤖 機器人二度出車，為 {test_room} 房送達付費客製化備品...")
    print(f" 🚀 房務系統發動獨立的備品扣款要求 (room-billing)...")
    
    billing_payload = {
        "roomNos": test_room,
        "items": [
            {
                "seqNos": 1,
                "productNos": "AMN-66089", # 備品料號
                "orderQuantity": 1
            }
        ]
    }
    
    res4 = send_request("POST", "/external/vendor-sync-data/room-billing", json_body=billing_payload)
    if res4 and res4.status_code == 200:
        print(f" 🟢 [房務入帳成功] 付費備品費用已順暢歸戶。")
    else:
        print(f" 🛑 [房務入帳失敗] 狀態碼: {res4.status_code if res4 else '無'}")

    time.sleep(1.5)

    # ----------------------------------------------------------------
    # 🎯 階段五：反向測試驗證「取消住掛帳務沖正」 (POST)
    # ----------------------------------------------------------------
    print("\n[Phase 5] 辦理反向財務功能驗證：客訴退點，小美犀要求作廢原訂單...")
    print(f" 📡 正在向德安雲端發動【紅字沖正】，欲撤銷唯一單號: 【{unique_order}】")
    
    # 取消住掛規格要求 orderNos 必須帶在 URL 參數中
    res5 = send_request("POST", "/external/vendor-sync-data/room-pay-cancel", custom_params={"orderNos": unique_order})
    if res5 and res5.status_code == 200:
        print(f" 🟢 [沖正成功] 德安會計帳項撤銷成功！")
        print(f"   🔺 德安產出之作廢沖正傳票單號 (acctNos): 【{res5.json().get('acctNos')}】")
        print("   💡 備忘：此時重新刷德安網頁前台，該筆 $500 元消費應已被紅字沖帳平衡。")
    else:
        print(f" 🛑 [沖正失敗] 德安拒絕退款。狀態碼: {res5.status_code if res5 else '無'} | 原因: {res5.text if res5 else ''}")

    print_banner("小美犀物聯網全功能故事鏈自動化 Staging 聯調測試順暢結案")

if __name__ == "__main__":
    run_smart_hotel_scenario()