# server/mock_server.py (最終真機聯調對齊版 - 批次修復優化)
import sys
import os
# 💡 動態將專案根目錄加入 Python 搜尋路徑，確保跨資料夾順利引入 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from datetime import datetime
import requests
import config  # 💡 完美引入全域設定檔

app = Flask(__name__)

# 💡 模擬外部廠商本地的「住客白名單資料庫」
mock_vendor_db = {}

# ====================================================================
# 🚀 路由 IN：被動接收端點 (專門負責讓真實 PMS 雲端推播住客資料落庫)
# ====================================================================
# ====================================================================
# 🚀 1. 辦理入住端點 白名單接收端點 (夜審項目 E1010 執行時，PMS 會一筆一筆把今日預計入住資料 POST 到這裡)
# ====================================================================
@app.route('/pms-sync-data/check-in', methods=['POST'])
def receive_guest_checkin():
    if not request.is_json:
        return jsonify({"error": "Unsupported Media Type"}), 415
        
    data = request.get_json()
    
    # 💡 洗滌與對齊欄位名稱（無論是真實雲端還是本地 Pytest 傳入）
    sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
    guest_id = str(data.get("guest_id") or sync_data.get("ciSerial") or sync_data.get("ciSer") or "").strip()
    car_number = str(data.get("car_number") or sync_data.get("carNos") or "QA-8888").strip()
    guest_name = str(data.get("guest_name") or sync_data.get("altName") or "未帶姓名").strip()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not guest_id:
        return jsonify({"error": "Bad Request", "message": "Missing key"}), 400
    
    source = "真實 Athena 雲端 (ngrok)" if "guest_id" in data else "本地 Pytest 閉環模擬"

    # ========================================================
    # 💡 1-1. 嚴格按照官方要求的 4 個欄位名稱落庫儲存（先寫入）
    # ========================================================
    guest_record = {
        "guest_id": guest_id,
        "car_number": car_number,
        "guest_name": guest_name,
        "arrival_time": current_time
    }
    
    # 真正落庫
    mock_vendor_db[guest_id] = guest_record
    
    print(f"\n📥 [名單同步] 成功接收來自 PMS (可能是夜審 E1010 或前台) 的名單: ID: {guest_id} | 車牌: {car_number}")
    return jsonify({"status": "success", "message": "Whitelist synchronised."}), 200


# ====================================================================
# 🚀 2. 取消入住端點 (新增)
# ====================================================================
@app.route('/pms-sync-data/check-in-cancel', methods=['POST'])
def receive_checkin_cancel():
    if not request.is_json:
        return jsonify({"error": "Unsupported Media Type"}), 415
        
    data = request.get_json()
    sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
    guest_id = str(data.get("guest_id") or sync_data.get("ciSer") or "").strip()
    
    if not guest_id:
        return jsonify({"error": "Bad Request", "message": "Missing identifier (guest_id/ciSer)"}), 400
        
    print(f"\n🛑 [Webhook - Cancel] 收到取消入住通知！正在撤銷識別碼: {guest_id}")
    
    # 執行資料庫撤銷 (Delete)
    if guest_id in mock_vendor_db:
        removed_data = mock_vendor_db.pop(guest_id)
        print(f"🗑️ 已成功將住客 [{removed_data['guest_name']}] 移出停車白名單。")
        return jsonify({"status": "success", "message": "Check-in canceled, white-list removed."}), 200
    else:
        print(f"⚠️ 警告：嘗試取消一個不存在的 ID [{guest_id}]，可能是重複發送。")
        return jsonify({"status": "success", "message": "ID not found, but cancel accepted."}), 200


# ====================================================================
# 🚀 3. 修改車牌端點 (新增)
# ====================================================================
@app.route('/pms-sync-data/change-car-nos', methods=['POST'])
def receive_change_car_nos():
    if not request.is_json:
        return jsonify({"error": "Unsupported Media Type"}), 415
        
    data = request.get_json()
    
    # 💡 處理 Swagger 的 List 嵌套結構，防禦真實與模擬的格式脫節
    guest_id = data.get("guest_id")
    car_number = data.get("car_number")
    
    if "parkingSyncDataList" in data and len(data["parkingSyncDataList"]) > 0:
        nested_data = data["parkingSyncDataList"][0]
        guest_id = nested_data.get("ciSer")
        car_number = nested_data.get("carNos")
        
    guest_id = str(guest_id or "").strip()
    car_number = str(car_number or "").strip()
    
    if not guest_id or not car_number:
        return jsonify({"error": "Bad Request", "message": "Missing guest_id or car_number"}), 400
        
    print(f"\n🔄 [Webhook - Change Car] 收到更換車牌請求！ID: {guest_id} -> 欲更換為: {car_number}")
    
    # 執行資料庫更新 (Update)
    if guest_id in mock_vendor_db:
        old_car = mock_vendor_db[guest_id]["car_number"]
        mock_vendor_db[guest_id]["car_number"] = car_number
        mock_vendor_db[guest_id]["arrival_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ 車牌更換成功！[{mock_vendor_db[guest_id]['guest_name']}]：{old_car} ➔ {car_number}")
        return jsonify({"status": "success", "message": "Car number updated."}), 200
    else:
        print(f"🚨 錯誤：更換車牌失敗，白名單資料庫找不到此 ID [{guest_id}]")
        return jsonify({"status": "error", "message": "Identifier not found in vendor database."}), 404


# ====================================================================
# 🚀 4. 修改退房時間端點 (新增)
# ====================================================================
@app.route('/pms-sync-data/change-checkout-datetime', methods=['POST'])
def receive_change_checkout_datetime():
    if not request.is_json:
        return jsonify({"error": "Unsupported Media Type"}), 415
        
    data = request.get_json()
    sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
    guest_id = str(data.get("guest_id") or sync_data.get("ciSer") or "").strip()
    
    # 擷取官方傳過來的預計退房日期與時間
    eco_date = data.get("ecoDate") or "未指定日期"
    eco_time = data.get("ecoTime") or "未指定時間"
    
    if not guest_id:
        return jsonify({"error": "Bad Request", "message": "Missing identifier"}), 400
        
    print(f"\n⏰ [Webhook - Change Checkout] 收到變更退房時間通知！ID: {guest_id} -> 變更為: {eco_date} {eco_time}")
    
    if guest_id in mock_vendor_db:
        # 在實際場景中，此處會延長白名單在停車場閘門系統的有效 Epoch Time
        print(f"✅ 成功延長住客 [{mock_vendor_db[guest_id]['guest_name']}] 的車牌臨停權限至 {eco_date} {eco_time}。")
        return jsonify({"status": "success", "message": "Checkout datetime extension recorded."}), 200
    else:
        print(f"🚨 警告：退房變更失敗，找不到此 ID [{guest_id}]")
        return jsonify({"status": "error", "message": "Identifier not found."}), 404


# ====================================================================
# 🚀 5. 夜審端點 (新增)夜審過天通知 (維持純粹：清空昨日過期快取)
# ====================================================================
@app.route('/pms-sync-data/night-audit', methods=['POST'])
def receive_night_audit():
    print(f"\n🌙 [Webhook - Night Audit] 接收到 Athena PMS 夜核開關觸發通知...")
    print(f" -> 清除昨日過期快取，當前白名單總數: {len(mock_vendor_db)} 筆。")
    
    mock_vendor_db.clear() # 清空資料庫，準備迎接今天夜審批次匯入的新住客
    
    print(f"🧹 廠商白名單快取已全數清空歸零。資料庫目前狀態: {mock_vendor_db}")
    return jsonify({"status": "success", "message": "Night audit notification received. Cache flushed."}), 200


# ====================================================================
# 🚗 🚀 路由 OUT：主動相機模擬端點 (當白天客人開車進場，由此發動逆向車辨轟炸)
# ====================================================================
@app.route('/external/vendor-sync-data/car-arrival', methods=['POST'])
def car_arrival():
    auth_header = request.headers.get('Authorization')
    # 💡 保持原有雙模金鑰校驗
    if not auth_header or auth_header != config.CURRENT_TOKEN and auth_header != config.LOCAL_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    guest_id = str(data.get("guest_id") or "").strip()
    car_number = str(data.get("car_number") or "").strip()

    # 去字典（白名單）裡查，夜審有沒有把這個人送進來
    if guest_id not in mock_vendor_db:
        print(f"\n🚨 [車辨失敗] 閘門感應到未知 Guest ID: {guest_id}，本地無此白名單，拒絕開閘！")
        return jsonify({"status": "error", "message": "Guest ID not found."}), 404

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mock_vendor_db[guest_id]["car_number"] = car_number
    mock_vendor_db[guest_id]["arrival_time"] = current_time
    
    target_guest = mock_vendor_db[guest_id]
    print(f"\n📸 [相機感應] 車牌 [{car_number}] 抵達閘門！車主: {target_guest['guest_name']}")

    # 💡 在住客「未入住」的完美時機點，逆向砸回真實 PMS，觸發 hfd_car_arrival_log 寫入
    print(f"🚀 [逆向通信] 正在推播『住客行車抵達訊息』至真實的 Athena PMS 雲端...")
    
    pms_car_payload = {
        "guest_id": guest_id,
        "car_number": car_number,
        "guest_name": target_guest["guest_name"],
        "arrival_time": current_time
    }
    
    try:
        # 🎯 關鍵修正：打向真實外部雲端，必須帶上 config.REAL_TOKEN
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
# 🔓 🚀 路由 C：內部除錯對齊端點 (專門讓相機模擬腳本拿走完整的白名單字典)
# ====================================================================
@app.route('/internal/debug/whitelist', methods=['GET'])
def get_internal_whitelist():
    return jsonify(mock_vendor_db), 200

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)