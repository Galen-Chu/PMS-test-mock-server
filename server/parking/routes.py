# server/parking/routes.py
from flask import Blueprint, app, request, jsonify
from datetime import datetime
import requests
import config
import logging
from server.parking.vendors.vendor_SHIN_YEONG import VendorShinYeongStrategy
from server.parking.vendors.vendor_PAYTRONEX import VendorPaytronexStrategy

# 建立停車功能獨立藍圖
parking_bp = Blueprint('parking', __name__)

# 💡 工廠機制：依據全域 config 動態載入當前配合的廠商策略實例
# ====================================================================
# 🎛️ 架構優化：孿生並存機制 (Parallel Multi-Instantiation)
# 🛑 拒絕排他性 if-else，強行同時拉起兩家廠商的策略實例，確保全路由大一統暢通
# ====================================================================
shin_yeong_strategy = VendorShinYeongStrategy()
paytronex_strategy = VendorPaytronexStrategy()

logger = logging.getLogger("ParkingSandbox")
# 💡 安全防禦：確保全域字典只會被初始化一次。如果模組被重載，保底不被清空
if 'mock_vendor_db' not in globals():
    mock_vendor_db = {}

# ====================================================================
# 🚗 廠商 1：新詠停車場 (SHIN_YEONG) 專屬分流區
# ====================================================================
# ====================================================================
# 🚀 路由 IN：被動接收端點 (專門負責讓真實 PMS 雲端推播住客資料落庫)
# ====================================================================
# ====================================================================
# 🚀 1. 日常入住端點 (CKI)
# ====================================================================
@parking_bp.route('/pms-sync-data/check-in', methods=['POST'])
def receive_pms_checkin():
    if not request.is_json:
        return jsonify({"error": "JSON expected"}), 415
    data = request.get_json()
    
    try:
        clean = shin_yeong_strategy.parse_pms_checkin(data)
        guest_id = clean["guest_id"]
        if not guest_id:
            return jsonify({"error": "Missing identification"}), 400
            
        fallback_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_date = clean["start_date"] or fallback_time
        end_date = clean["end_date"] or fallback_time
        
        mock_vendor_db[guest_id] = {
            "guest_id": guest_id,
            "car_number": clean["car_number"],
            "guest_name": clean["guest_name"],
            "start_date": start_date,
            "end_date": end_date,
            "enabled": clean["enabled"],
            "arrival_time": fallback_time
        }
        
        print(f"📥 [Webhook - CKI 入住] 新名單落庫 -> ID: {guest_id} | 車牌: {clean['car_number']} | 狀態: 【{clean['enabled']}】")
        return jsonify({"status": "success", "message": "Check-in integrated successfully."}), 200
    except Exception as e:
        print(f"🚨 [CKI 異常]: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# ====================================================================
# 🚀 2. 修改/延長退房時間端點 (CHANGE_CKO_DATE_TIME)
# ====================================================================
@parking_bp.route('/pms-sync-data/change-checkout-datetime', methods=['POST'])
def receive_pms_change_checkout():
    if not request.is_json:
        return jsonify({"error": "JSON expected"}), 415
    data = request.get_json()
    
    try:
        # 調用專屬的延長退房清洗策略
        clean = shin_yeong_strategy.parse_pms_change_checkout(data)
        guest_id = clean["guest_id"]
        if not guest_id:
            return jsonify({"error": "Missing identification"}), 400
            
        fallback_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 🎯 核心增量異動：只更新退房時間與狀態，不破壞原本入住時錄入的姓名與起日
        if guest_id in mock_vendor_db:
            old_cko = mock_vendor_db[guest_id]["end_date"]
            mock_vendor_db[guest_id]["end_date"] = clean["end_date"] or mock_vendor_db[guest_id]["end_date"]
            mock_vendor_db[guest_id]["enabled"] = clean["enabled"]
            if clean["car_number"]: # 若綜合櫃台有順便異動車牌則同步更新
                mock_vendor_db[guest_id]["car_number"] = clean["car_number"]
            
            print(f"🔄 [Webhook - CKO 延長退房] 住客 [{mock_vendor_db[guest_id]['guest_name']}] 時間異動：{old_cko} ➔ {mock_vendor_db[guest_id]['end_date']}")
        else:
            # 防禦性落庫
            mock_vendor_db[guest_id] = {
                "guest_id": guest_id,
                "car_number": clean["car_number"],
                "guest_name": clean["guest_name"],
                "start_date": fallback_time,
                "end_date": clean["end_date"] or fallback_time,
                "enabled": clean["enabled"],
                "arrival_time": fallback_time
            }
            print(f"⚠️ [Webhook - CKO 延長退房] 收到未在白名單之 ID: {guest_id}，自動補登建立狀態。")
            
        return jsonify({"status": "success", "message": "Checkout extension timestamp updated."}), 200
    except Exception as e:
        print(f"🚨 [CKO 延長退房異常]: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# ====================================================================
# 🚀 3. 綜合櫃台車牌異動 (CHG_CAR_NOS - 支援新增/清除/更新三態)
# ====================================================================
@parking_bp.route('/pms-sync-data/change-car-nos', methods=['POST'])
def receive_change_car_nos():
    if not request.is_json:
        return jsonify({"error": "JSON expected"}), 415
    data = request.get_json()
    
    try:
        clean = shin_yeong_strategy.parse_pms_change_car_nos(data)
        guest_id = clean["guest_id"]
        if not guest_id:
            return jsonify({"error": "Missing identifying key 'guest_id'"}), 400
            
        if guest_id in mock_vendor_db:
            old_car = mock_vendor_db[guest_id]["car_number"]
            
            # 🎯 核心重構：直接信任策略層洗出來的車牌與狀態。
            # 更新車牌時，舊車牌那一發會進來把對應車牌改為 False；新車牌那一發進來會把新車牌改為 True。
            mock_vendor_db[guest_id]["car_number"] = clean["car_number"]
            mock_vendor_db[guest_id]["enabled"] = clean["enabled"]
            
            status_log = "啟用" if clean["enabled"] else "停用"
            print(f"🔄 [Webhook - CHG_CAR_NOS 三態變更]")
            print(f"   👤 住客: [{mock_vendor_db[guest_id]['guest_name']}] | 車牌軌跡: {old_car} ➔ {clean['car_number']} | 憑證狀態: 【{status_log}】")
        else:
            fallback_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mock_vendor_db[guest_id] = {
                "guest_id": guest_id,
                "car_number": clean["car_number"],
                "guest_name": clean["guest_name"],
                "start_date": fallback_time,
                "end_date": fallback_time,
                "enabled": clean["enabled"],
                "arrival_time": ""
            }
            print(f"⚠️ [Webhook - CHG_CAR_NOS] 發現未登錄主檔之 ID: {guest_id}，已完成防禦性補登。")
            
        return jsonify({"status": "success", "message": "Car number status synchronised successfully."}), 200
    except Exception as e:
        print(f"🚨 [CHG_CAR_NOS 異常]: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# ====================================================================
# 🚀 4. 取消入住端點 (CIX - 完美保留車牌離廠版)
# ====================================================================
@parking_bp.route('/pms-sync-data/check-in-cancel', methods=['POST'])
def receive_checkin_cancel():
    if not request.is_json:
        return jsonify({"error": "JSON expected"}), 415
    data = request.get_json()
    
    try:
        clean = shin_yeong_strategy.parse_pms_cancel_checkin(data)
        guest_id = clean["guest_id"]
        if not guest_id:
            return jsonify({"error": "Missing identifying key 'guest_id'"}), 400
            
        if guest_id in mock_vendor_db:
            old_car = mock_vendor_db[guest_id]["car_number"]
            old_end = mock_vendor_db[guest_id]["end_date"]
            
            # 🎯 核心重構：絕對不改為空值！如果 Webhook 有帶新車牌就更新，沒帶就沿用本地原本的車牌
            if clean["car_number"]:
                mock_vendor_db[guest_id]["car_number"] = clean["car_number"]
                
            mock_vendor_db[guest_id]["end_date"] = clean["end_date"]
            mock_vendor_db[guest_id]["enabled"] = clean["enabled"]
            
            print(f"🗑️ [Webhook - CIX 取消入住逃生安全閘]")
            print(f"   👤 住客: [{mock_vendor_db[guest_id]['guest_name']}] | 鎖定離廠車牌: 【{mock_vendor_db[guest_id]['car_number']}】")
            print(f"   ⏳ 狀態維持啟用，退房截止線強制縮短至: {clean['end_date']}（逾時拒開）")
        else:
            # 防禦性補登：萬一原本本地沒有這筆單，也必須幫他把車牌註冊進去，確保他能順利開車離場
            fallback_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mock_vendor_db[guest_id] = {
                "guest_id": guest_id,
                "car_number": clean["car_number"],
                "guest_name": clean["guest_name"],
                "start_date": fallback_time,
                "end_date": clean["end_date"],
                "enabled": clean["enabled"],
                "arrival_time": ""
            }
            print(f"⚠️ [Webhook - CIX] 收到未登錄主檔之 ID: {guest_id}，已完成車牌【{clean['car_number']}】之限時離場憑證補登。")
            
        return jsonify({"status": "success", "message": "Check-in canceled. Exit validation token retained."}), 200
    except Exception as e:
        print(f"🚨 [CIX 異常]: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# ====================================================================
# 🌙 5. 夜核端點 (NIGHT_AUDIT) 夜核過天通知 (維持純粹：清空昨日過期快取)
# ====================================================================
@parking_bp.route('/pms-sync-data/night-audit', methods=['POST'])
def receive_night_audit():
    # 💡 第一道防線：確保有收到 JSON，若無則優雅拋出錯誤，防禦 TraceLog
    if not request.is_json:
        print("🚨 [NIGHT_AUDIT 錯誤] 接收到非 JSON 格式的非法請求！")
        return jsonify({"status": "error", "message": "Unsupported Media Type. JSON expected."}), 415
        
    data = request.get_json()
    
    try:
        # 1. 調用策略層進行真實 Payload 欄位清洗
        clean_audit = shin_yeong_strategy.parse_pms_night_audit(data)
        guest_id = clean_audit["guest_id"]
        
        # 💡 安全降級防禦：萬一德安突然傳了一筆空資料，不讓系統崩潰
        if not guest_id:
            print("⚠️ [NIGHT_AUDIT 警告] 收到夜核請求，但未包含有效 guest_id 欄位，維持現有白名單狀態。")
            return jsonify({"status": "success", "message": "Signal accepted but empty data payload ignored."}), 200

        # 2. 🎯 核心翻轉：廢除 clear()！實施動態字典累加覆寫機制（Upsert）
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        mock_vendor_db[guest_id] = {
            "guest_id": guest_id,
            "car_number": clean_audit["car_number"],
            "guest_name": clean_audit["guest_name"],
            "start_date": clean_audit["start_date"],
            "end_date": clean_audit["end_date"],
            "enabled": clean_audit["enabled"],
            "arrival_time": current_time
        }
        
        print(f"🌙 [NIGHT_AUDIT 增量落庫] 成功接收來自德安夜核名單！")
        print(f" 💾 住客: {clean_audit['guest_name']} | 車牌: {clean_audit['car_number']} | 狀態: {clean_audit['enabled']}")
        print(f" 🖥️ [當前廠商暫存資料庫累計數]: {len(mock_vendor_db)} 筆。")
        
        # 3. 🎯 消除 TraceLog 報錯的核心：回傳 200 OK 與明確的完成狀態語意
        return jsonify({
            "status": "success", 
            "message": "Night audit data integrated successfully.",
            "synchronized_id": guest_id
        }), 200
        
    except Exception as e:
        # 拋出明確的 400 錯誤，讓 PMS 的 TraceLog 能精準捕捉到是廠商端哪裡解析失敗
        print(f"🚨 [NIGHT_AUDIT 異常]: {e}")
        return jsonify({"status": "error", "message": f"Internal mapping failed: {str(e)}"}), 400

# ====================================================================
# 🚗 🚀 路由 OUT：主動相機模擬端點 (當白天客人開車進場，由此發動逆向車辨轟炸)
# ====================================================================
@parking_bp.route('/external/vendor-sync-data/car-arrival', methods=['POST'])
def car_arrival():
    auth_header = request.headers.get('Authorization')
    if not auth_header or (auth_header != config.CURRENT_TOKEN and auth_header != config.LOCAL_TOKEN):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    guest_id = str(data.get("guest_id") or "").strip()
    car_number = str(data.get("car_number") or "").strip()

    if guest_id not in mock_vendor_db:
        print(f"🚨 [車辨失敗] 未知 Guest ID: {guest_id}，本地無名單，拒開！")
        return jsonify({"status": "error", "message": "Guest ID not found."}), 404

    # ====================================================================
    # 🎯 SA 終極對齊優化：動態時間洗滌引擎 (Business Date Alignment)
    # 🛑 廢除 datetime.now()！直接繼承該住客在德安合法的 start_date 
    # ====================================================================
    local_guest = mock_vendor_db[guest_id]
    
    # 🎯 修正點 1：對齊德安 Swagger 格式，時間字串必須為 YYYY/MM/DD HH:mm:ss (斜線)
    # 優先嘗試將原本帶橫線的 start_date 轉換成斜線格式
    matched_arrival_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    mock_vendor_db[guest_id]["car_number"] = car_number
    mock_vendor_db[guest_id]["arrival_time"] = matched_arrival_time
    
    # 🎯 修正點 2：直接建立與 Swagger 100% 相同的大一統實體 Payload，防止 Strategy 層漏欄位
    pms_car_payload = {
        "guest_id": local_guest.get("guest_id"),
        "car_number": car_number,
        "guest_name": local_guest.get("guest_name"),
        "arrival_time": matched_arrival_time
    }
    
    print(f"📸 [相機感應] 車牌 [{car_number}] 抵達，準備推播回真實德安雲端...")
    print(f"📦 抵達時間: {matched_arrival_time}")
    print(f"📦 [Payload 對齊驗證]: {pms_car_payload}")

    # 🎯 修正點 3：依據 Swagger 成功範例，移除 Authorization Header
    api_headers = {
        "accept": "*/*",
        "bacchus-athenaid": str(config.active_cfg["ATHENA_ID"]),
        "bacchus-hotelcod": str(config.active_cfg["HOTEL_COD"]),
        "Content-Type": "application/json",
    }

    target_url = f"{config.REAL_URL_CAR_ARRIVAL}?thirdParty=SHIN_YEONG"
    
    try:
        response = requests.post(
            target_url, 
            json=pms_car_payload, 
            headers=api_headers, 
            timeout=5
        )
        print(f"📡 【真實雲端回應】狀態碼: {response.status_code} | 內容: {response.text}")
        return jsonify({"status": "success", "pms_response": response.text}), 200
    except Exception as e:
        print(f"❌ [逆向傳送失敗]: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ====================================================================
# 🔓 🚀 路由 CROSS：內部除錯對齊端點 (專門讓相機模擬腳本拿走完整的白名單字典)
# ====================================================================
@parking_bp.route('/parking/internal/whitelist', methods=['GET'])
def get_internal_whitelist():
    return jsonify(mock_vendor_db), 200

# ====================================================================
# 🚗 廠商 2：博辰車辨 (PAYTRONEX) 官方標準分流區
# ====================================================================
# 🎯 情境 A：入住 CKI / 綜合櫃台新增車號 ➔ 新增房客預約資料
@parking_bp.route('/parktron/hpms/services/roomer/add', methods=['POST'])
def paytronex_add_roomer():
    body_data = request.get_json() or {}
    room_number = body_data.get("Roomer", {}).get("RoomNumber", "未知")
    logger.info(f"🚗 [博辰車辨 ➔ 大門路由] 收到新增房客預約請求 (房號: 【{room_number}】)")
    
    # 精準分流給博辰策略物件處理
    response_payload, status_code = paytronex_strategy.add_roomer(body_data)
    return jsonify(response_payload), status_code

# 🎯 情境 B：取消入住 CIX / 變更或清除車號 ➔ 依車牌查詢房客租約 (取 RentId)
@parking_bp.route('/parktron/hpms/services/roomer/findByLicensePlate', methods=['POST'])
def paytronex_find_by_plate():
    body_data = request.get_json() or {}
    search_plate = body_data.get("LicensePlate", "未知")
    logger.info(f"🔍 [博辰車辨 ➔ 大門路由] 收到依車牌逆查租約請求 (車牌: 【{search_plate}】)")
    
    # 精準分流給博辰策略物件處理
    response_payload, status_code = paytronex_strategy.find_by_license_plate(body_data)
    return jsonify(response_payload), status_code

# 🎯 情境 C：拿著 RentId 傳送更新 / 變更退房日期 / 註銷清空車牌
@parking_bp.route('/parktron/hpms/services/roomer/update', methods=['POST'])
def paytronex_update_roomer():
    body_data = request.get_json() or {}
    rent_id = body_data.get("Roomer", {}).get("RentId", "未知")
    logger.info(f"🔄 [博辰車辨 ➔ 大門路由] 收到更新/註銷房客預約請求 (RentId: 【{rent_id}】)")
    
    # 精準分流給博辰策略物件處理
    response_payload, status_code = paytronex_strategy.update_roomer(body_data)
    return jsonify(response_payload), status_code