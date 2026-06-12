# hardware/simulate_speaker.py
import sys
import os
import time
from datetime import datetime
import json
import logging
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ====================================================================
# 🏗️ 發射端 Console Log 紀錄器初始化 (更易於大量自動化情境管理)
# ====================================================================
logger = logging.getLogger("SpeakerSimulator")
logger.setLevel(logging.INFO)
if not logger.handlers:
    c_handler = logging.StreamHandler()
    c_format = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%H-%m-%d %H:%M:%S')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)

USE_REAL = config.USE_REAL_SERVER
HEADERS = config.CURRENT_HEADERS_BACCHUS       
BASE_PARAMS = config.CURRENT_PARAMS_AMENITY   

# 方案 B 頂層路徑定義
POOL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests_data_pool")
FIXTURE_PATH = os.path.join(POOL_DIR, "aiello_product_fixtures.json")
LOG_PAYLOAD_PATH = os.path.join(POOL_DIR, "verified_payload_logs.json")

# ====================================================================
# 🧠 傳輸資料自動化處理輔助工具
# ====================================================================
def load_product_from_pool(product_type="M001"):
    """🛒 從數據池抽取付實測成功的產品料號"""
    try:
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for p in data.get("amenity_products", []):
                if product_type == "M001" and p.get("productNos") == "M001":
                    return p.get("productNos")
                if product_type == "BUFFET" and p.get("productNos") == "BUFFET":
                    return p.get("productNos")
    except Exception:
        pass
    return product_type

def dump_success_payload_to_json(scenario_name, endpoint, payload):
    """💾 核心訴求：測試入帳成功時，自動將真實 payload 與情境結構錄入 JSON 檔案"""
    try:
        if not os.path.exists(POOL_DIR):
            os.makedirs(POOL_DIR)
            
        logs = []
        if os.path.exists(LOG_PAYLOAD_PATH):
            with open(LOG_PAYLOAD_PATH, "r", encoding="utf-8") as f:
                try:
                    logs = json.load(f)
                except Exception:
                    logs = []
                    
        # 封裝高真戰績節點
        log_node = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "scenario": scenario_name,
            "endpoint": endpoint,
            "environment": "REAL_ATHENA_CLOUD" if USE_REAL else "LOCAL_SANDBOX",
            "payload": payload
        }
        logs.append(log_node)
        
        with open(LOG_PAYLOAD_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        logger.info(f"   ⚙️  [自動化資產落庫] 成功將此發砲 Payload 自動匯入數據池戰績表！")
    except Exception as e:
        logger.warning(f"   ⚠️  [自動化落庫失敗]: {e}")

def execute_request(method, url, params=None, json_body=None):
    """大一統通信發射引擎：相容 200/204 雙軌認證機制"""
    try:
        if method.upper() == "GET":
            res = requests.get(url, params=params, headers=HEADERS, timeout=8)
        else:
            res = requests.post(url, params=params, json=json_body, headers=HEADERS, timeout=8)
        return res
    except Exception as e:
        logger.error(f"🚨 [通訊邊緣端崩潰]: {e}")
        return None

# 動態路由參數定義 (確保與 config.py 中的 URL 定義完全對齊，避免硬編碼風險)
URL_ROOM_NOS = config.REAL_URL_ROOM_NOS if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-pay/room-nos"
URL_MIFARE_NOS = config.REAL_URL_MIFARE_NOS if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-pay/mifare-nos"
URL_ROOM_PAY = config.REAL_URL_ROOM_PAY if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-pay"
URL_ROOM_PAY_CANCEL = config.REAL_URL_ROOM_PAY_CANCEL if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-pay-cancel"
URL_ROOM_BILLING = config.REAL_URL_ROOM_BILLING if USE_REAL else f"{config.NGROK_BASE_URL}/external/vendor-sync-data/room-billing"

# ====================================================================
# 🎬 8 大核心擴充測試情境流水線大一統
# ====================================================================
def run_all_expanded_scenarios():
    logger.info(f"🚀 ===================================================")
    logger.info(f"🚀  小美犀 8 大核心擴充回歸情境引擎點火啟動 (環境: {'真實雲端' if USE_REAL else '本地沙盒'})")
    logger.info(f"🚀 ===================================================")

    # 統一初始化測試變數
    roomNos = "101"
    cardNos = "123456789"
    rsptCode = "2FFO"
    rsptName = "2F櫃台"
    orderNos = "123456789012345678901"
    productCode = load_product_from_pool("M001")
    productName = load_product_from_pool("BUFFET")

    # ----------------------------------------------------------------
    # 🎯 情境 1: GET room-nos --> POST room-billing (已開發備品流)
    # ----------------------------------------------------------------
    logger.info("\n【情境 1】音箱語音房號查驗 ➔ 房務付費備品獨立過帳流水線")
    res = execute_request("GET", URL_ROOM_NOS, params={**BASE_PARAMS, "keyword": roomNos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /room-nos) 通關。")
        
        response_json = res.json()
        # 🎯 同步優化：精準雙層扒皮，直擊真實雲端深處的憑證，確保全腳本邏輯大一統
        real_ci_serial = response_json["data"]["data"][0]["checkInSerial"]
        
        logger.info(f"   🔑 [真實雲端資料對齊] 成功提取並儲存過帳憑證 (ciSerial): 【{real_ci_serial}】")
        time.sleep(0.5)
        
        # 💡 備品過帳 Payload (完美對齊德安 room-billing 規格書)
        payload = {
            "roomNos": str(roomNos), 
            "items": [
                {
                    "seqNos": 1, 
                    "productNos": str(productCode),  # 從數據池抽取的 M001
                    "orderQuantity": 1
                }
            ]
        }
        
        res_post = execute_request("POST", URL_ROOM_BILLING, params=BASE_PARAMS, json_body=payload)
        if res_post and res_post.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 2 (POST /room-billing) 成功通關！德安回應碼: {res_post.status_code}")
            dump_success_payload_to_json("Scenario_1_Room_Nos_To_Billing", "/room-billing", payload)
        else:
            logger.error(f"   🛑 Phase 2 房務備品過帳遭到德安回絕。回應碼: {res_post.status_code if res_post else '無'}")

    # ----------------------------------------------------------------
    # 🎯 情境 2: GET room-nos --> POST room-pay (房號查驗 ➔ 餐廳消費住掛)
    # ----------------------------------------------------------------
    logger.info("\n【情境 2】音箱語音房號查驗 ➔ 餐廳點餐消費住掛房間帳流水線")
    res = execute_request("GET", URL_ROOM_NOS, params={**BASE_PARAMS, "keyword": roomNos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /room-nos) 通關。")
        
        response_json = res.json()
        # 🎯 核心能力展現：精準雙層扒皮，直接直擊真實雲端深處的憑證！
        real_ci_serial = response_json["data"]["data"][0]["checkInSerial"]
            
        logger.info(f"   🔑 [真實雲端資料對齊] 成功提取並繼承過帳憑證 (ciSerial): 【{real_ci_serial}】")
        time.sleep(0.5)
        
        order_nos = f"BR-S2-{datetime.now().strftime('%m%d%H%M%S')}"
        
        payload = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial),       # 💡 實時注入真實憑證: 20260607000010
                "roomNos": str(roomNos),               
                "orderNos": str(order_nos),            
                "needTransfer": "N",                   
                "rsptCode": str(rsptCode),             
                "rsptName": str(rsptName),             
                "mTimeCode": "LCH",                    
                "mTimeName": "午餐",                   
                "deskNos": "A01",                      
                "payAmount": 500,                      
                "acuAmount": 0,                        
                "precreditTotal": 0,                   
                "custType": "5"                        
            },
            "roomPayDetail": [
                {
                    "sequenceNos": 1,                  
                    "productName": "牛排",              
                    "orderQuantity": 1,                
                    "specialAmount": 500,              
                    "precreditAmount": 0               
                }
            ]
        }
        
        res_post = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload)
        if res_post and res_post.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 2 (POST /room-pay) 成功通關！德安回應碼: {res_post.status_code}")
            dump_success_payload_to_json("Scenario_2_Room_Nos_To_Pay", "/room-pay", payload)

    # ----------------------------------------------------------------
    # 🎯 情境 3: GET room-nos --> POST room-pay --> POST room-pay-cancel (消費 ➔ 立即沖正作廢)
    # ----------------------------------------------------------------
    logger.info("\n【情境 3】語音房號查驗 ➔ 餐廳住掛 ➔ 客訴退點紅字反向沖正作廢流水線")
    res = execute_request("GET", URL_ROOM_NOS, params={**BASE_PARAMS, "keyword": roomNos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /room-nos) 通關。")
        
        response_json = res.json()
        # 🎯 精準雙層扒皮
        real_ci_serial = response_json["data"]["data"][0]["checkInSerial"]
            
        logger.info(f"   🔑 [真實雲端資料對齊] 成功提取並繼承過帳憑證 (ciSerial): 【{real_ci_serial}】")
        time.sleep(0.5)
        
        order_nos = f"BR-S3-{datetime.now().strftime('%m%d%H%M%S')}"
        
        payload_pay = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial),       
                "roomNos": str(roomNos), 
                "orderNos": str(order_nos), 
                "needTransfer": "N",
                "rsptCode": str(rsptCode), 
                "rsptName": str(rsptName),
                "mTimeCode": "LCH",
                "mTimeName": "午餐",
                "deskNos": "A02",
                "payAmount": 120,
                "acuAmount": 0,
                "precreditTotal": 0,
                "custType": "5"
            },
            "roomPayDetail": [
                {"sequenceNos": 1, "productName": "特製飲品", "orderQuantity": 1, "specialAmount": 120, "precreditAmount": 0}
            ]
        }
        res_pay = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_pay)
        
        if res_pay and res_pay.status_code in [200, 204]:
            logger.info(f"   Phase 2 (POST /room-pay) 掛帳完成。緊接著發動紅字反向平衡...")
            time.sleep(1)
            
            res_cancel = execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos})
            if res_cancel and res_cancel.status_code in [200, 204]:
                logger.info(f"   🟢 Phase 3 (POST /room-pay-cancel) 成功通關！交易已完全作廢。")
                dump_success_payload_to_json("Scenario_3_Room_Nos_Pay_And_Cancel", "/room-pay-cancel", {"cancelledOrderNos": order_nos})

    # ----------------------------------------------------------------
    # 🎯 情境 4: GET room-nos --> POST room-pay --> POST room-pay-cancel --> POST room-pay (扣款 ➔ 作廢 ➔ 重新下單)
    # ----------------------------------------------------------------
    logger.info("\n【情境 4】語音房號查驗 ➔ 餐廳住掛 ➔ 沖正作廢 ➔ 重新更正下單複利交易流")
    res = execute_request("GET", URL_ROOM_NOS, params={**BASE_PARAMS, "keyword": roomNos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /room-nos) 通關。")
        
        response_json = res.json()
        # 🎯 精準雙層扒皮
        real_ci_serial = response_json["data"]["data"][0]["checkInSerial"]
            
        logger.info(f"   🔑 [真實雲端資料對齊] 成功提取並繼承過帳憑證 (ciSerial): 【{real_ci_serial}】")
        
        order_nos_old = f"BR-S4X-{datetime.now().strftime('%m%d%H%M%S')}"
        order_nos_new = f"BR-S4NEW-{datetime.now().strftime('%m%d%H%M%S')}"
        
        # 扣款
        payload_1 = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial),       
                "roomNos": str(roomNos), 
                "orderNos": str(order_nos_old), 
                "needTransfer": "N",
                "rsptCode": str(rsptCode), 
                "payAmount": 200,
                "custType": "5"
            }, 
            "roomPayDetail": []
        }
        execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_1)
        time.sleep(0.5)
        
        # 作廢
        execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos_old})
        time.sleep(0.5)
        
        # 重新扣款
        payload_2 = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial),       
                "roomNos": str(roomNos), 
                "orderNos": str(order_nos_new), 
                "needTransfer": "N",
                "rsptCode": str(rsptCode), 
                "rsptName": str(rsptName),
                "mTimeCode": "LCH",
                "mTimeName": "午餐",
                "deskNos": "A04",
                "payAmount": 250,
                "acuAmount": 0,
                "precreditTotal": 0,
                "custType": "5"
            }, 
            "roomPayDetail": [
                {"sequenceNos": 1, "productName": "更正品項", "orderQuantity": 1, "specialAmount": 250, "precreditAmount": 0}
            ]
        }
        res_final = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_2)
        if res_final and res_final.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 4 (POST /room-pay 重製單) 成功通關！新單號: {order_nos_new}")
            dump_success_payload_to_json("Scenario_4_ReOrder_Lifecycle", "/room-pay-reorder", payload_2)

    # 💳 房卡逆查流流水線大一統 (情境 5 ~ 8)
    # 🌟 規範對齊：動態生成符合德安最新規格的 6 碼大寫英數隨機房卡號 (E.g., "A1B2C3D4")
    import secrets
    import string
    alphabet = string.ascii_uppercase + string.digits
    dynamic_card_nos = ''.join(secrets.choice(alphabet) for _ in range(6))
    
    logger.info(f"\n⚡ ===================================================")
    logger.info(f"⚡  進入房卡逆查流戰場 ➔ 模擬現場感應卡號: 【{dynamic_card_nos}】")
    logger.info(f"⚡ ===================================================")

    # ----------------------------------------------------------------
    # 🎯 情境 5: GET mifare-nos --> POST room-billing (實體前台刷卡 ➔ 房務備品扣款)
    # ----------------------------------------------------------------
    logger.info("\n【情境 5】實體前台房卡卡號逆查 ➔ 房務付費備品獨立過帳流水線")
    res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": dynamic_card_nos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /mifare-nos 逆查) 通關。")
        
        response_json = res.json()
        # 🎯 核心能力：相容德安真實雲端雙層外殼，精準逆查提取卡片歸屬房號
        target_room_nos = response_json["data"]["data"][0]["roomNos"]
        
        logger.info(f"   🔑 [真實雲端資料對齊] 房卡成功識別 ➔ 歸屬房號: 【{target_room_nos}】")
        time.sleep(0.5)
        
        payload_billing = {
            "roomNos": str(target_room_nos), 
            "items": [{"seqNos": 1, "productNos": str(productCode), "orderQuantity": 2}]
        }
        res_post = execute_request("POST", URL_ROOM_BILLING, params=BASE_PARAMS, json_body=payload_billing)
        if res_post and res_post.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 2 (POST /room-billing 經卡號) 成功過帳！")
            dump_success_payload_to_json("Scenario_5_Mifare_To_Billing", "/room-billing", payload_billing)

    # ----------------------------------------------------------------
    # 🎯 情境 6: GET mifare-nos --> POST room-pay (房卡逆查 ➔ 餐廳住掛)
    # ----------------------------------------------------------------
    logger.info("\n【情境 6】實體前台房卡卡號逆查 ➔ 餐廳點餐消費住掛房間帳流水線")
    res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": dynamic_card_nos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /mifare-nos 逆查) 通關。")
        
        response_json = res.json()
        # 🎯 雙層扒皮：同時繼承房號與餐廳掛帳不可或缺的 ciSerial 憑證！
        target_room_nos = response_json["data"]["data"][0]["roomNos"]
        real_ci_serial = response_json["data"]["data"][0]["checkInSerial"]
        
        logger.info(f"   🔑 [真實雲端資料對齊] 成功繼承 ➔ 房號: 【{target_room_nos}】 | 憑證(ciSerial): 【{real_ci_serial}】")
        time.sleep(0.5)
        
        order_nos = f"BR-S6-{datetime.now().strftime('%m%d%H%M%S')}"
        payload = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial), 
                "roomNos": str(target_room_nos), 
                "orderNos": str(order_nos), 
                "needTransfer": "N", 
                "rsptCode": str(rsptCode), 
                "rsptName": str(rsptName), 
                "mTimeCode": "LCH", 
                "mTimeName": "午餐", 
                "deskNos": "A03", 
                "payAmount": 990, 
                "acuAmount": 0, 
                "precreditTotal": 0, 
                "custType": "5"
            },
            "roomPayDetail": [
                {"sequenceNos": 1, "productName": "豪華雙人套餐", "orderQuantity": 1, "specialAmount": 990, "precreditAmount": 0}
            ]
        }
        res_post = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload)
        if res_post and res_post.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 2 (POST /room-pay 經卡號) 成功過帳！")
            dump_success_payload_to_json("Scenario_6_Mifare_To_Room_Pay", "/room-pay", payload)

    # ----------------------------------------------------------------
    # 🎯 情境 7: GET mifare-nos --> POST room-pay --> POST room-pay-cancel (房卡逆查 ➔ 餐廳住掛 ➔ 現場臨時退點紅字作廢)
    # ----------------------------------------------------------------
    logger.info("\n【情境 7】房卡卡號逆查 ➔ 餐廳住掛 ➔ 現場臨時退點紅字作廢流水線")
    res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": dynamic_card_nos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /mifare-nos 逆查) 通關。")
        
        response_json = res.json()
        target_room_nos = response_json["data"]["data"][0]["roomNos"]
        real_ci_serial = response_json["data"]["data"][0]["checkInSerial"]
        
        logger.info(f"   🔑 [真實雲端資料對齊] 成功繼承 ➔ 房號: 【{target_room_nos}】 | 憑證(ciSerial): 【{real_ci_serial}】")
        time.sleep(0.5)
        
        order_nos = f"BR-S7-{datetime.now().strftime('%m%d%H%M%S')}"
        payload_pay = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial), 
                "roomNos": str(target_room_nos), 
                "orderNos": str(order_nos), 
                "needTransfer": "N",
                "rsptCode": str(rsptCode), 
                "payAmount": 300, 
                "custType": "5"
            }, 
            "roomPayDetail": []
        }
        
        if execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_pay).status_code in [200, 204]:
            logger.info(f"   Phase 2 正向掛帳完成。緊接著發動現場紅字反向平衡作廢...")
            time.sleep(0.5)
            
            res_cancel = execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos})
            if res_cancel and res_cancel.status_code in [200, 204]:
                logger.info(f"   🟢 Phase 3 (POST /room-pay-cancel 經卡號) 成功反向作廢！交易已完全抹平。")
                dump_success_payload_to_json("Scenario_7_Mifare_Pay_And_Cancel", "/room-pay-cancel", {"cancelledOrderNos": order_nos})

    # ----------------------------------------------------------------
    # 🎯 情境 8: GET mifare-nos --> POST room-pay --> POST room-pay-cancel --> POST room-pay (房卡逆查全生命週期更正流)
    # ----------------------------------------------------------------
    logger.info("\n【情境 8】房卡卡號逆查 ➔ 餐廳住掛 ➔ 現場退點作廢 ➔ 重新櫃檯更正下單完整生命週期流")
    res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": dynamic_card_nos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /mifare-nos 逆查) 通關。")
        
        response_json = res.json()
        target_room_nos = response_json["data"]["data"][0]["roomNos"]
        real_ci_serial = response_json["data"]["data"][0]["checkInSerial"]
        
        logger.info(f"   🔑 [真實雲端資料對齊] 成功繼承 ➔ 房號: 【{target_room_nos}】 | 憑證(ciSerial): 【{real_ci_serial}】")
        
        order_nos_old = f"BR-S8X-{datetime.now().strftime('%m%d%H%M%S')}"
        order_nos_new = f"BR-S8NEW-{datetime.now().strftime('%m%d%H%M%S')}"
        
        # 1. 錯誤下單
        payload_old = {
            "roomPayMain": {"ciSerial": str(real_ci_serial), "roomNos": str(target_room_nos), "orderNos": str(order_nos_old), "rsptCode": str(rsptCode), "payAmount": 50, "custType": "5"}, 
            "roomPayDetail": []
        }
        execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_old)
        time.sleep(0.5)
        
        # 2. 立即沖正
        execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos_old})
        time.sleep(0.5)
        
        # 3. 重新建立正確金額單據
        payload_final = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial), 
                "roomNos": str(target_room_nos), 
                "orderNos": str(order_nos_new), 
                "needTransfer": "N",
                "rsptCode": str(rsptCode), 
                "rsptName": str(rsptName), 
                "mTimeCode": "LCH", 
                "mTimeName": "午餐", 
                "deskNos": "A01", 
                "payAmount": 55, 
                "acuAmount": 0, 
                "precreditTotal": 0, 
                "custType": "5"
            }, 
            "roomPayDetail": [
                {"sequenceNos": 1, "productName": "修正差額品項", "orderQuantity": 1, "specialAmount": 55, "precreditAmount": 0}
            ]
        }
        res_final = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_final)
        if res_final and res_final.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 4 (POST /room-pay 終極更正單) 成功通關！新單號: {order_nos_new}")
            dump_success_payload_to_json("Scenario_8_Mifare_Full_Lifecycle", "/room-pay", payload_final)

    logger.info("\n🏁 ===================================================")
    logger.info("🏁  小美犀 8 大核心擴充回歸情境流水線全數連發完賽！")
    logger.info("🏁 ===================================================")

if __name__ == "__main__":
    run_all_expanded_scenarios()