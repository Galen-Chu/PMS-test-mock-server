# mock_server.py (最終真機聯調對齊版)
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
# 🚀 1. 辦理入住端點 (保持原有完美功能)
# ====================================================================
@app.route('/pms-sync-data/check-in', methods=['POST'])
def receive_guest_checkin():
    if not request.is_json:
        return jsonify({"error": "Unsupported Media Type"}), 415
        
    data = request.get_json()
    
    # 💡 洗滌與對齊欄位名稱（無論是真實雲端還是本地 Pytest 傳入）
    guest_id = str(data.get("guest_id") or data.get("ciSerial") or "").strip()
    car_number = str(data.get("car_number") or data.get("carNos") or "QA-8888").strip()
    guest_name = str(data.get("guest_name") or data.get("altName") or "未帶姓名").strip()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not guest_id:
        return jsonify({"error": "Bad Request", "message": "Missing key"}), 400
    
    source = "真實 Athena 雲端 (ngrok)" if "guest_id" in data else "本地 Pytest 閉環模擬"

    # ========================================================
    # 💡 1. 嚴格按照官方要求的 4 個欄位名稱落庫儲存（先寫入）
    # ========================================================
    guest_record = {
        "guest_id": guest_id,
        "car_number": car_number,
        "guest_name": guest_name,
        "arrival_time": current_time
    }
    
    # 真正落庫
    mock_vendor_db[guest_id] = guest_record
    
    print(f"\n📥 [外部廠商 Server] 成功接收 Check-in 同步！來源: 【{source}】")
    print(f"🖥️ [當前廠商資料庫狀態]: {guest_record}") # 💡 修正：直接印局部變數，絕對不噴 KeyError！
    # print(f"🖥️ [當前廠商資料庫狀態]: {mock_vendor_db[guest_id]}") 

    # ====================================================================
    # 💡 2. 關鍵條件管理：如果來自「真實業務操作」，0.5秒內順發自動逆向轟炸！
    # ====================================================================
    if "guest_id" in data:
        print(f"🚀 [逆向通信] 偵測到真實環境操作，立刻同步停車狀態至真實的 Athena PMS 雲端...")
        
        pms_headers = {
            "Authorization": config.REAL_TOKEN,  # 💡 直接引用 config 的真實雲端 Token
            "Content-Type": "application/json"
        }
        
        try:
            print(f"📡 正在發送合約校準資料至: {config.REAL_URL_CAR_ARRIVAL}")
            print(f"📡 Body Payload: {guest_record}")
            
            response = requests.post(
                config.REAL_URL_CAR_ARRIVAL, 
                json=guest_record, # 💡 毫無誤差，直接將對齊好的 4 個欄位資料拋給真實 PMS
                headers=pms_headers, 
                params=config.REAL_PARAMS,
                timeout=5
            )
            print(f"📡 【真實雲端即時回應】狀態碼: {response.status_code}")
            print(f"📡 【真實雲端即時回應】內容: {response.text}")
            
        except Exception as e:
            print(f"❌ [逆向傳送失敗]: {e}")
            
    return jsonify({"status": "success", "message": "Sync completed."}), 200

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
# 🚀 5. 夜審端點 (新增)
# ====================================================================
@app.route('/pms-sync-data/night-audit', methods=['POST'])
def receive_night_audit():
    # 💡 依據規格，夜審無引數與 Request Body，直接執行跨日清檔
    print(f"\n🌙 [Webhook - Night Audit] 執行飯店夜間稽核程序...")
    print(f" -> 清除前準備，當前白名單總數: {len(mock_vendor_db)} 筆。")
    
    # 執行資料庫清空 (Clear)
    mock_vendor_db.clear()
    
    print(f"🧹 廠商白名單快取已全數清空歸零。資料庫目前狀態: {mock_vendor_db}")
    return jsonify({"status": "success", "message": "Night audit completed. Vendor database flushed."}), 200


# ====================================================================
# 🚗 🚀 路由 OUT：保留給本地全自動 Pytest 閉環使用的舊端點
# ====================================================================
@app.route('/external/vendor-sync-data/car-arrival', methods=['POST'])
def car_arrival():
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header != config.CURRENT_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    guest_id = data.get("guest_id")
    car_number = data.get("car_number")

    if guest_id not in mock_vendor_db:
        print(f"\n🚨 [車辨警告] 找不到此識別碼: {guest_id}，拒絕開啟閘門！")
        return jsonify({"status": "error", "message": "ID not found."}), 404

    # 更新本地模擬資料庫狀態
    mock_vendor_db[guest_id]["car_number"] = car_number
    mock_vendor_db[guest_id]["arrival_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n📸 [本地模擬相機感應] 車牌 [{car_number}] 已開進停車場！內容已更新。")
    
    return jsonify({"status": "success", "message": "Local car arrival recorded."}), 200

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)