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
        time.sleep(0.5)
        
        payload = {"roomNos": roomNos, "items": [{"seqNos": 1, "productNos": productCode, "orderQuantity": 1}]}
        res_post = execute_request("POST", URL_ROOM_BILLING, params=BASE_PARAMS, json_body=payload)
        if res_post and res_post.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 2 (POST /room-billing) 成功通關！德安回應碼: {res_post.status_code}")
            dump_success_payload_to_json("Scenario_1_Room_Nos_To_Billing", "/room-billing", payload)

    # ----------------------------------------------------------------
    # 🎯 情境 2: GET room-nos --> POST room-pay (房號查驗 ➔ 餐廳消費住掛)
    # ----------------------------------------------------------------
    logger.info("\n【情境 2】音箱語音房號查驗 ➔ 餐廳點餐消費住掛房間帳流水線")
    res = execute_request("GET", URL_ROOM_NOS, params={**BASE_PARAMS, "keyword": roomNos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /room-nos) 通關。")
        
        response_json = res.json()
        
        # 🎯 標準路徑提取：因為兩端結構 100% 仿照文件對齊，直接獲取 data[0] 的 checkInSerial
        # 🎯 安全路徑提取：兼容 List、Dict 異常回傳結構，並加上安全防禦
        raw_data = response_json.get("data", [])
        real_ci_serial = "20260605000001"  # 預設保底憑證

        if isinstance(raw_data, list) and len(raw_data) > 0:
            first_node = raw_data[0]
            if isinstance(first_node, dict):
                real_ci_serial = first_node.get("checkInSerial", real_ci_serial)
        elif isinstance(raw_data, dict):
            # 防禦機制：萬一後端直接把大物件塞在 data 欄位而不是 Array
            real_ci_serial = raw_data.get("checkInSerial", real_ci_serial)
        else:
            logger.warning(f"   ⚠️ [結構異常] 收到未預期的 data 型態: {type(raw_data)}, 原始內容: {response_json}")
            
        time.sleep(0.5)
        
        order_nos = f"BR-S2-{datetime.now().strftime('%m%d%H%M%S')}"
        
        # 🌟 構造 100% 仿照最新補足規格書、編碼限制與碼數限制的 Payload 結構
        payload = {
            "roomPayMain": {
                "ciSerial": str(real_ci_serial),       # 💡 精準填入 GET 拿到的真實凭證
                "roomNos": str(roomNos),               # String(6) 房號
                "orderNos": str(order_nos),            # String(21) 唯一單號
                "needTransfer": "N",                   # String(1) 固定填 N
                "rsptCode": str(rsptCode),             # String(4) 銷售點代號 (限 4 碼：BUFF)
                "rsptName": str(rsptName),             # String(10) 自助餐
                "mTimeCode": "LCH",                    # String(4) 餐廳代號 (限 4 碼：LCH)
                "mTimeName": "午餐",                   # String(10)
                "deskNos": "A01",                      # String(10) 桌號
                "payAmount": 500,                      # Number 住掛總金額
                "acuAmount": 0,                        # Number 可積點金額
                "precreditTotal": 0,                   # Number 內含代支總額
                "custType": "5"                        # String(1) 規格書強制要求填 "5"
            },
            "roomPayDetail": [
                {
                    "sequenceNos": 1,                  # Integer 從 1 開始
                    "productName": "牛排",              # String(30)
                    "orderQuantity": 1,                # Integer 數量
                    "specialAmount": 500,              # Number 金額小計
                    "precreditAmount": 0               # Number 代支金額
                }
            ]
        }
        
        res_post = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload)
        if res_post and res_post.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 2 (POST /room-pay) 成功通關！德安回應碼: {res_post.status_code}")
            dump_success_payload_to_json("Scenario_2_Room_Nos_To_Pay", "/room-pay", payload)
        else:
            logger.error(f"   🛑 Phase 2 遭到德安回絕。回應碼: {res_post.status_code if res_post else '無'}")

    # ----------------------------------------------------------------
    # 🎯 情境 3: GET room-nos --> POST room-pay --> POST room-pay-cancel (消費 ➔ 立即沖正作廢)
    # ----------------------------------------------------------------
    logger.info("\n【情境 3】語音房號查驗 ➔ 餐廳住掛 ➔ 客訴退點紅字反向沖正作廢流水線")
    res = execute_request("GET", URL_ROOM_NOS, params={**BASE_PARAMS, "keyword": roomNos})
    if res and res.status_code == 200:
        logger.info(f"   Phase 1 (GET /room-nos) 通關。")
        
        response_json = res.json()
        
        # 🎯 安全憑證提取（沿用情境 2 成功的防禦邏輯）
        raw_data = response_json.get("data", [])
        real_ci_serial = "20260605000001"
        if isinstance(raw_data, list) and len(raw_data) > 0:
            first_node = raw_data[0]
            if isinstance(first_node, dict):
                real_ci_serial = first_node.get("checkInSerial", real_ci_serial)
        elif isinstance(raw_data, dict):
            real_ci_serial = raw_data.get("checkInSerial", real_ci_serial)
            
        logger.info(f"   🔑 [憑證繼承] 成功取得過帳憑證 (ciSerial): {real_ci_serial}")
        time.sleep(0.5)
        
        # 動態生成這次測試的唯一單號
        order_nos = f"BR-S3-{datetime.now().strftime('%m%d%H%M%S')}"
        
        # 1. 發動正向掛帳 POST /room-pay
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
                {
                    "sequenceNos": 1,
                    "productName": "特製飲品",
                    "orderQuantity": 1,
                    "specialAmount": 120,
                    "precreditAmount": 0
                }
            ]
        }
        
        res_pay = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_pay)
        
        if res_pay and res_pay.status_code in [200, 204]:
            logger.info(f"   🟢 Phase 2 (POST /room-pay) 掛帳完成。德安回應: {res_pay.json() if res_pay.status_code==200 else '204'}")
            logger.info(f"   ⏳ 模擬現場客訴/點錯單，緊接著發動紅字反向平衡...")
            time.sleep(1) # 停留 1 秒模擬真實體感
            
            # 2. 發動反向沖正 POST /room-pay-cancel (注意：這支 API 規格通常是透過 Query String 帶入 orderNos)
            res_cancel = execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos})
            
            if res_cancel and res_cancel.status_code in [200, 204]:
                logger.info(f"   🟢 Phase 3 (POST /room-pay-cancel) 成功通關！交易已完全作廢。")
                
                # 自動錄入 JSON 戰績表，格式完全收容
                dump_success_payload_to_json(
                    "Scenario_3_Room_Nos_Pay_And_Cancel", 
                    "/room-pay-cancel", 
                    {
                        "originalOrderNos": order_nos,
                        "cancelResponse": res_cancel.json() if res_cancel.status_code == 200 else "204"
                    }
                )
            else:
                logger.error(f"   🛑 Phase 3 沖正失敗。回應碼: {res_cancel.status_code if res_cancel else '無'}")
        else:
            logger.error(f"   🛑 Phase 2 正向掛帳即遭回絕，無法執行 Phase 3。")

    # # ----------------------------------------------------------------
    # # 🎯 情境 4: GET room-nos --> POST room-pay --> POST room-pay-cancel --> POST room-pay (扣款 ➔ 作廢 ➔ 重新下單)
    # # ----------------------------------------------------------------
    # logger.info("\n【情境 4】語音房號查驗 ➔ 餐廳住掛 ➔ 沖正作廢 ➔ 重新更正下單複利交易流")
    # res = execute_request("GET", URL_ROOM_NOS, params={**BASE_PARAMS, "keyword": room_101})
    # if res and res.status_code == 200:
    #     logger.info(f"   Phase 1 通關。")
    #     order_nos_old = f"BR-S4X-{datetime.now().strftime('%m%d%H%M%S')}"
    #     order_nos_new = f"BR-S4NEW-{datetime.now().strftime('%m%d%H%M%S')}"
        
    #     # 扣款
    #     payload_1 = {"roomPayMain": {"ciSerial": f"DYNAMIC-CI-{room_101}", "roomNos": room_101, "orderNos": order_nos_old, "rsptCode": product_buffet, "payAmount": 200.00}, "roomPayDetail": []}
    #     execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_1)
    #     # 作廢
    #     execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos_old})
    #     # 重新扣款
    #     payload_2 = {"roomPayMain": {"ciSerial": f"DYNAMIC-CI-{room_101}", "roomNos": room_101, "orderNos": order_nos_new, "rsptCode": product_buffet, "payAmount": 250.00}, "roomPayDetail": [{"sequenceNos": 1, "productName": "更正品項", "specialAmount": 250.00}]}
    #     res_final = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_2)
    #     if res_final and res_final.status_code in [200, 204]:
    #         logger.info(f"   🟢 Phase 4 (POST /room-pay 重製單) 成功通關！新單號: {order_nos_new}")
    #         dump_success_payload_to_json("Scenario_4_ReOrder_Lifecycle", "/room-pay-reorder", payload_2)

    # # ----------------------------------------------------------------
    # # 🎯 情境 5: GET mifare-nos --> POST room-billing (實體前台刷卡 ➔ 房務備品扣款)
    # # ----------------------------------------------------------------
    # logger.info("\n【情境 5】實體前台房卡卡號逆查 ➔ 房務付費備品獨立過帳流水線")
    # res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": card_123})
    # if res and res.status_code == 200:
    #     logger.info(f"   Phase 1 (GET /mifare-nos 逆查) 通關。")
    #     time.sleep(0.5)
        
    #     payload = {"roomNos": room_101, "items": [{"seqNos": 1, "productNos": product_m001, "orderQuantity": 2}]}
    #     res_post = execute_request("POST", URL_ROOM_BILLING, params=BASE_PARAMS, json_body=payload)
    #     if res_post and res_post.status_code in [200, 204]:
    #         logger.info(f"   🟢 Phase 2 (POST /room-billing 經卡號) 成功通關！")
    #         dump_success_payload_to_json("Scenario_5_Mifare_To_Billing", "/room-billing", payload)

    # # ----------------------------------------------------------------
    # # 🎯 情境 6: GET mifare-nos --> POST room-pay (房卡逆查 ➔ 餐廳住掛)
    # # ----------------------------------------------------------------
    # logger.info("\n【情境 6】實體前台房卡卡號逆查 ➔ 餐廳點餐消費住掛房間帳流水線")
    # res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": card_123})
    # if res and res.status_code == 200:
    #     logger.info(f"   Phase 1 (GET /mifare-nos 逆查) 通關。")
    #     time.sleep(0.5)
        
    #     order_nos = f"BR-S6-{datetime.now().strftime('%m%d%H%M%S')}"
    #     payload = {
    #         "roomPayMain": {"ciSerial": f"DYNAMIC-CI-{room_101}", "roomNos": room_101, "orderNos": order_nos, "rsptCode": product_buffet, "payAmount": 990.00},
    #         "roomPayDetail": [{"sequenceNos": 1, "productName": "豪華雙人套餐", "orderQuantity": 1, "specialAmount": 990.00}]
    #     }
    #     res_post = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload)
    #     if res_post and res_post.status_code in [200, 204]:
    #         logger.info(f"   🟢 Phase 2 (POST /room-pay 經卡號) 成功通關！")
    #         dump_success_payload_to_json("Scenario_6_Mifare_To_Room_Pay", "/room-pay", payload)

    # # ----------------------------------------------------------------
    # # 🎯 情境 7: GET mifare-nos --> POST room-pay --> POST room-pay-cancel
    # # ----------------------------------------------------------------
    # logger.info("\n【情境 7】房卡卡號逆查 ➔ 餐廳住掛 ➔ 現場臨時退點紅字作廢流水線")
    # res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": card_123})
    # if res and res.status_code == 200:
    #     logger.info(f"   Phase 1 通關。")
    #     order_nos = f"BR-S7-{datetime.now().strftime('%m%d%H%M%S')}"
    #     payload_pay = {"roomPayMain": {"ciSerial": f"DYNAMIC-CI-{room_101}", "roomNos": room_101, "orderNos": order_nos, "rsptCode": product_buffet, "payAmount": 300.00}, "roomPayDetail": []}
        
    #     if execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_pay).status_code in [200, 204]:
    #         time.sleep(0.5)
    #         res_cancel = execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos})
    #         if res_cancel and res_cancel.status_code in [200, 204]:
    #             logger.info(f"   🟢 Phase 3 (POST /room-pay-cancel 經卡號) 成功作廢！")
    #             dump_success_payload_to_json("Scenario_7_Mifare_Pay_And_Cancel", "/room-pay-cancel", {"cancelledOrderNos": order_nos})

    # # ----------------------------------------------------------------
    # # 🎯 情境 8: GET mifare-nos --> POST room-pay --> POST room-pay-cancel --> POST room-pay
    # # ----------------------------------------------------------------
    # logger.info("\nblock 【情境 8】房卡卡號逆查 ➔ 餐廳住掛 ➔ 現場退點作廢 ➔ 重新櫃檯更正下單完整生命週期流")
    # res = execute_request("GET", URL_MIFARE_NOS, params={**BASE_PARAMS, "keyword": card_123})
    # if res and res.status_code == 200:
    #     logger.info(f"   Phase 1 通關。")
    #     order_nos_old = f"BR-S8X-{datetime.now().strftime('%m%d%H%M%S')}"
    #     order_nos_new = f"BR-S8NEW-{datetime.now().strftime('%m%d%H%M%S')}"
        
    #     execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body={"roomPayMain": {"ciSerial": f"DYNAMIC-CI-{room_101}", "roomNos": room_101, "orderNos": order_nos_old, "rsptCode": product_buffet, "payAmount": 50.00}, "roomPayDetail": []})
    #     execute_request("POST", URL_ROOM_PAY_CANCEL, params={**BASE_PARAMS, "orderNos": order_nos_old})
        
    #     payload_final = {"roomPayMain": {"ciSerial": f"DYNAMIC-CI-{room_101}", "roomNos": room_101, "orderNos": order_nos_new, "rsptCode": product_buffet, "payAmount": 55.00}, "roomPayDetail": [{"sequenceNos": 1, "productName": "修正差額品項", "specialAmount": 55.00}]}
    #     res_final = execute_request("POST", URL_ROOM_PAY, params=BASE_PARAMS, json_body=payload_final)
    #     if res_final and res_final.status_code in [200, 204]:
    #         logger.info(f"   🟢 Phase 4 (POST /room-pay 終極更正單) 成功通關！")
    #         dump_success_payload_to_json("Scenario_8_Mifare_Full_Lifecycle", "/room-pay", payload_final)

    # logger.info("\n🏁 ===================================================")
    # logger.info("🏁  8 大擴充回歸情境流水線全數連發完賽！請至 tests_data_pool 查收成功 Payload 戰績。")
    # logger.info("🏁 ===================================================")

if __name__ == "__main__":
    run_all_expanded_scenarios()