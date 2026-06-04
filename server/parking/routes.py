# server/parking/routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import requests
import config
from server.parking.vendors.vendor_SHIN_YEONG import VendorShinYeongStrategy

# 建立停車功能獨立藍圖
parking_bp = Blueprint('parking', __name__)

# 💡 模擬外部廠商本地的「住客白名單資料庫」
mock_vendor_db = {}

# 💡 工廠機制：依據全域 config 動態載入當前配合的廠商策略實例
if getattr(config, 'CURRENT_PARKING_VENDOR', 'VENDOR_SHIN_YEONG') == 'VENDOR_SHIN_YEONG':
    vendor_strategy = VendorShinYeongStrategy()
else:
    # 未來若有 other VENDOR，直接在此擴充引入即可
    vendor_strategy = VendorShinYeongStrategy()

# ====================================================================
# 🚀 1. 辦理入住 / 修改車牌 / 修改退房時間 端點 (大一統接收端)
# ====================================================================
@parking_bp.route('/pms-sync-data/check-in', methods=['POST'])
@parking_bp.route('/pms-sync-data/change-car-nos', methods=['POST'])
@parking_bp.route('/pms-sync-data/change-checkout-datetime', methods=['POST'])
def receive_pms_webhook():
    if not request.is_json:
        return jsonify({"error": "Unsupported Media Type"}), 415
        
    data = request.get_json()
    
    try:
        # 🎯 核心抽象：交給當前廠商策略去洗滌，出來的一定是標準乾淨格式
        clean_data = vendor_strategy.parse_pms_checkin(data)
        guest_id = clean_data["guest_id"]
        
        if not guest_id:
            return jsonify({"error": "Bad Request", "message": "Missing key identifier"}), 400
            
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 執行資料庫更新或寫入
        if request.path == '/pms-sync-data/change-car-nos' and guest_id in mock_vendor_db:
            old_car = mock_vendor_db[guest_id]["car_number"]
            mock_vendor_db[guest_id]["car_number"] = clean_data["car_number"]
            mock_vendor_db[guest_id]["arrival_time"] = current_time
            print(f"✅ [車牌變更] {mock_vendor_db[guest_id]['guest_name']}: {old_car} ➔ {clean_data['car_number']}")
        else:
            mock_vendor_db[guest_id] = {
                "guest_id": guest_id,
                "car_number": clean_data["car_number"],
                "guest_name": clean_data["guest_name"],
                "arrival_time": current_time
            }
            print(f"📥 [名單落庫] ID: {guest_id} | 車牌: {clean_data['car_number']} | 姓名: {clean_data['guest_name']}")
            
        return jsonify({"status": "success", "message": "Synchronised successfully."}), 200
    except Exception as e:
        print(f"🚨 [接收異常]: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# ====================================================================
# 🚀 2. 取消入住端點 (CIX)
# ====================================================================
@parking_bp.route('/pms-sync-data/check-in-cancel', methods=['POST'])
def receive_checkin_cancel():
    data = request.get_json() or {}
    sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
    guest_id = str(data.get("guest_id") or sync_data.get("ciSer") or "").strip()
    
    if not guest_id:
        return jsonify({"error": "Bad Request", "message": "Missing guest_id"}), 400
        
    if guest_id in mock_vendor_db:
        removed = mock_vendor_db.pop(guest_id)
        print(f"🗑️ [撤銷白名單] 住客 [{removed['guest_name']}] 已成功移出。")
        return jsonify({"status": "success", "message": "Removed from whitelist."}), 200
    return jsonify({"status": "success", "message": "ID not found, accepted."}), 200

# ====================================================================
# 🌙 3. 夜審過天端點 (NIGHT_AUDIT)
# ====================================================================
@parking_bp.route('/pms-sync-data/night-audit', methods=['POST'])
def receive_night_audit():
    print(f"\n🌙 [NIGHT_AUDIT] 接收到德安夜審通知，清空昨日舊快取...")
    mock_vendor_db.clear()
    return jsonify({"status": "success", "message": "Cache flushed."}), 200

# ====================================================================
# 🚗 🚀 4. 住客行車抵達 (CAR_ARRIVAL) - 逆向回擊
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

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mock_vendor_db[guest_id]["car_number"] = car_number
    mock_vendor_db[guest_id]["arrival_time"] = current_time
    
    # 🎯 核心調度：利用 Strategy 生成對齊該廠商規格的逆向 Payload
    pms_car_payload = vendor_strategy.transform_car_arrival_payload(mock_vendor_db[guest_id], current_time)
    
    print(f"\n📸 [相機感應] 車牌 [{car_number}] 抵達，準備推播回真實德安雲端...")
    try:
        response = requests.post(
            config.REAL_URL_CAR_ARRIVAL, 
            json=pms_car_payload, 
            headers={"Authorization": config.REAL_TOKEN, "Content-Type": "application/json"}, 
            params=config.REAL_PARAMS,
            timeout=5
        )
        print(f"📡 【真實雲端回應】狀態碼: {response.status_code} | 內容: {response.text}")
        return jsonify({"status": "success", "pms_response": response.text}), 200
    except Exception as e:
        print(f"❌ [逆向傳送失敗]: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ====================================================================
# 🔓 5. 內部除錯對齊端點 (供相機腳本迴圈拉取)
# ====================================================================
@parking_bp.route('/internal/debug/whitelist', methods=['GET'])
def get_internal_whitelist():
    return jsonify(mock_vendor_db), 200