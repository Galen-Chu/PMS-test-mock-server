# server/keycard/routes.py
from flask import Blueprint, request, jsonify
from .vendors.vendor_WAFERLOCK_LIVEAM import VendorWaferlockLiveamStrategy
import config  # 💡 匯入頂層的 config 檔案，用以讀取真實的 JWT Token
import datetime

keycard_bp = Blueprint('keycard', __name__)
WaferlockLiveam_strategy = VendorWaferlockLiveamStrategy()

# 🔑 記憶體權限保險箱：儲存所有已簽發、具效力的 Token
WaferlockLiveam_session_vault = set()

# 🗃️ 維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)訂單暫存資料庫 (主鍵為訂單 id)
WaferlockLiveam_order_db = {}

# 🗃️ 維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)實體卡片資產庫 (主鍵為 cardUid)
WaferlockLiveam_card_db = {}

def verify_WaferlockLiveam_token():
    """👮‍♂️ 雙軌制權限驗證：相容沙盒自簽 Token 與德安真實環境的 PMS_QA_ATHENA_TOKEN"""
    token = config.CURRENT_TOKEN if config.USE_REAL_SERVER else request.headers.get('Authorization')
    
    # 🎯 檢查是否為沙盒自己簽發的 Token
    if token in WaferlockLiveam_session_vault:
        return True
        
    # 🎯 檢查是否為德安 PMS 真實雲端環境打過來的真實 Token
    if token == config.PMS_QA_ATHENA_TOKEN:
        return True
        
    return False

# ====================================================================
# 🔑 🚀 1. 廠商身份鑑權端點 (POST /api/Auth/login)
# ====================================================================
@keycard_bp.route('/api/Auth/login', methods=['POST'])
def keycard_vendor_login():
    if not request.is_json:
        return jsonify({"error": 99, "desc": "Unsupported Media Type", "msg": "請使用 JSON 傳輸規格"}), 415
        
    body_data = request.get_json()
    print(f"\n🔑 [維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁 Mock] 收到德安 PMS 登入請求 -> ID: {body_data.get('id')}")
    
    response_payload, status_code = WaferlockLiveam_strategy.authenticate_login(body_data)
    
    if status_code == 200:
        generated_token = response_payload["token"]
        WaferlockLiveam_session_vault.add(generated_token)
        print(f" 🟢 [鑑權成功] 簽發有效代幣: 【{generated_token}】 | 綁定製卡機: 【{response_payload['encoderCode']}】")
    else:
        print(f" 🔴 [鑑權失敗] 原因: {response_payload.get('msg')}")
        
    return jsonify(response_payload), status_code

# ====================================================================
# 🔑 🚀 2. 【維夫拉克 WAFERLOCK】新增門禁訂單端點 (POST /api/Order)
# ====================================================================
# 🌟 核心重構：同時監聽標準路徑與德安真實環境噴過來的拼接畸形路徑
@keycard_bp.route('/api/Order', methods=['POST'])
@keycard_bp.route('/api/Order/api/Order', methods=['POST'])     # 👈 完美收容德安真實環境流量
@keycard_bp.route('/api/OrderCard/api/Order', methods=['POST']) # 👈 完美收容德安真實環境流量
def create_keycard_order():
    incoming_path = request.path
    
    # 🎯 雙軌制權限驗證 (調用你優化後的動態強制綁定版本)
    if not verify_WaferlockLiveam_token():
        print(f"\n🔴 [維夫拉克 & 門禁] Token 驗證失敗，阻擋請求。")
        return jsonify({"error": "Invalid or expired token."}), 401

    if not request.is_json:
        return jsonify({"error": 400, "msg": "Payload 必須為 JSON"}), 400
        
    body_data = request.get_json()
    cleaned_order = WaferlockLiveam_strategy.clean_order_payload(body_data)
    
    # 💡 健壯性防禦：真實環境從頭訂房時，德安傳入的主鍵可能是 ikey 或 id
    order_id = str(body_data.get("ikey") or body_data.get("id") or "").strip()
    if not order_id:
        # 如果真的都沒有，動態用時間戳生成，確保流程絕對不卡死
        order_id = f"AUTO-ORD-{int(datetime.datetime.now().timestamp())}"
        
    cleaned_order["id"] = order_id
    room_nos = str(body_data.get("roomNos") or cleaned_order.get("roomID") or "101").strip()
    cleaned_order["roomID"] = room_nos

    print(f"\n🔒 [維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁] 收到建立/推播訂單請求 ➔ 路由: {incoming_path}")
    print(f"   🎯 乾淨解析 ➔ 訂單ID(ikey): 【{order_id}】| 房號: 【{room_nos}】| 住客: 【{cleaned_order['guestName']}】")

    # 💾 乾淨落庫與複寫機制
    if order_id in WaferlockLiveam_order_db:
        print(f" 🟢 [維夫拉克存在複寫] 訂單 ID 【{order_id}】已存在，執行非破壞性覆寫更新。")
        WaferlockLiveam_order_db[order_id].update(cleaned_order)
    else:
        WaferlockLiveam_order_db[order_id] = cleaned_order
        print(f" 🟢 [維夫拉克同步成功] 全新門禁開門權限已乾淨預備就緒！")
        
    return jsonify(cleaned_order), 201

# ====================================================================
# 🔑 🚀 3. 修改/啟用門禁訂單端點 (PUT /api/Order)
# ====================================================================
@keycard_bp.route('/api/Order', methods=['PUT'])
def update_keycard_order():
    if not verify_WaferlockLiveam_token():
        return jsonify({"error": "Invalid or expired token."}), 401
    if not request.is_json:
        return jsonify({"error": 400, "msg": "Payload 必須為 JSON"}), 400
        
    body_data = request.get_json()
    cleaned_order = WaferlockLiveam_strategy.clean_order_payload(body_data)
    order_id = cleaned_order["id"]

    print(f"\n🔑 [維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁 Mock] 收到修改訂單請求 ➔ 訂單ID: 【{order_id}】")

    if order_id not in WaferlockLiveam_order_db:
        print(f" 🔴 [修改失敗] 查無訂單 ID 【{order_id}】")
        return jsonify({"error": 4041, "msg": "查無此訂單 ID"}), 404

    old_order = WaferlockLiveam_order_db[order_id]
    old_order.update(cleaned_order)
    print(f" 🟢 [修改成功] 實體開門權限已啟用。")
    return jsonify({}), 200

# ====================================================================
# 🔑 🚀 4. 【維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)】新增訂單卡片端點 (POST /api/OrderCard)
# ====================================================================
@keycard_bp.route('/api/OrderCard', methods=['POST'])
def create_keycard_asset():
    if not verify_WaferlockLiveam_token():
        return jsonify({"error": "Unauthorized"}), 401
    if not request.is_json:
        return jsonify({"error": 400, "msg": "Payload 必須為 JSON"}), 400
        
    body_data = request.get_json()
    
    # 🎯 兼容性洗滌：同時相容本地測試欄位與德安 PMS 真實轉發欄位
    order_id = str(body_data.get("ikey") or body_data.get("orderID") or "").strip()
    encoder_code = str(body_data.get("pmrId") or "").strip()
    room_nos = str(body_data.get("roomNos") or "101").strip()
    
    print(f"\n🛠️ [維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM) 製卡系統] 收到德安轉發製卡請求")
    print(f"   📥 原始 Payload: {body_data}")
    print(f"   🎯 解析 ➔ 訂單(ikey): 【{order_id}】| 指定製卡機(pmrId): 【{encoder_code}】| 房號: 【{room_nos}】")

    if not order_id:
        return jsonify({"error": 4002, "msg": "ikey (orderID) 不可為空"}), 400

    # 🌟 核心修正：德安此時沒給實體卡號(cardUid)，我們必須模擬「實體製卡機感應晶片」動態生成一組 8 碼大寫英數卡號！
    import secrets
    import string
    alphabet = string.ascii_uppercase + string.digits
    simulated_card_uid = ''.join(secrets.choice(alphabet) for _ in range(8))
    
    print(f"   ⚡ [實體製卡機動作] 偵測到製卡機 【{encoder_code}】 壓卡成功！動態寫入晶片卡號: 【{simulated_card_uid}】")

    # 🔗 跨系統關聯防禦放寬：串接真實環境時，德安 PMS 可能還沒呼叫 /api/Order 建立門禁，
    # 為了不讓製卡流程卡死，若維夫拉克找不到訂單，我們自動幫他補一筆，確保聯調暢通！
    if order_id not in WaferlockLiveam_order_db:
        print(f"   ⚠️ [維夫拉克門禁真空] 查無門禁主檔，自動為其補全虛擬門禁權限...")
        WaferlockLiveam_order_db[order_id] = {
            "id": order_id,
            "roomID": room_nos,
            "guestName": body_data.get("guestName", "真實雲端住客")
        }

    # 💾 維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM) 卡片資產落庫
    card_node = {
        "ikey": order_id,
        "orderID": order_id,
        "cardUid": simulated_card_uid,
        "type": "card",
        "ikeySeqNos": body_data.get("ikeySeqNos", 1)
    }
    WaferlockLiveam_card_db[simulated_card_uid] = card_node
    
    # ⚡ 跨模組重大連動：同步回寫小美犀映射表，讓後續的【情境 5】刷卡流可以直接用這張卡
    try:
        from server.amenity.routes import mock_card_mapping_db
        mock_card_mapping_db[simulated_card_uid] = room_nos
        print(f"   ⚙️  [數據閉環] 卡號 【{simulated_card_uid}】 與房號 【{room_nos}】 已同步注入小美犀！")
    except Exception as e:
        pass

    # 完美對齊高真回應：把維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)系統最終生成的實體卡號與狀態吐回給德安 PMS
    response_payload = {
        "ikey": order_id,
        "ikeySeqNos": card_node["ikeySeqNos"],
        "cardUid": simulated_card_uid,
        "status": "SUCCESS",
        "msg": "製卡成功"
    }
    
    print(f" 🟢 [維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)製卡成功] 已將卡片資產回傳德安中台。")
    return jsonify(response_payload), 201

# ====================================================================
# 🔑 🚀 5. 刪除註銷卡片端點
# ====================================================================
@keycard_bp.route('/api/OrderCard/<string:oid>/<string:cuid>', methods=['DELETE'])
def delete_keycard_asset(oid, cuid):
    if not verify_WaferlockLiveam_token():
        return jsonify({"error": "Unauthorized"}), 401
        
    order_id = str(oid).strip()
    card_uid = str(cuid).strip()
    
    print(f"\n🔑 [維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁 Mock] 收到註銷銷卡請求 ➔ 訂單: 【{order_id}】| 卡號: 【{card_uid}】")

    if card_uid not in WaferlockLiveam_card_db or WaferlockLiveam_card_db[card_uid]["orderID"] != order_id:
        return jsonify({"error": 4043, "msg": "查無此卡片資產綁定紀錄"}), 404

    del WaferlockLiveam_card_db[card_uid]
    
    try:
        from server.amenity.routes import mock_card_mapping_db
        if card_uid in mock_card_mapping_db:
            del mock_card_mapping_db[card_uid]
            print(f"   ⚙️  [跨模組連動] 已從小美犀記憶體中撤銷卡號 【{card_uid}】 的掛帳權限。")
    except Exception as e:
        pass

    print(f" 🟢 [銷卡成功] 卡片已完成回收註銷。")
    return jsonify({}), 200

# ====================================================================
# 🔑 🚀 6. 【維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)】模擬讀卡機卡片逆查端點
# ====================================================================
# 🌟 核心重構：同時監聽標準路徑與德安真實環境拼接出來的 getCardInfoDef 畸形路由
@keycard_bp.route('/api/Operation/getCardInfo/<string:pmrId>', methods=['POST'])
@keycard_bp.route('/api/OrderCard/api/Operation/getCardInfoDef/<string:pmrId>', methods=['POST']) # 👈 完美收容 404 流量
def get_keycard_info_by_uid(pmrId):
    # 1. 👮‍♂️ 呼叫雙軌制權限驗證
    if not verify_WaferlockLiveam_token():
        return jsonify({"error": "Unauthorized"}), 401
        
    # 🌟 完美校準：全面更名為 doorcard_machine 對齊 PMS 規格
    doorcard_machine = str(pmrId).strip()
    print(f"\n🔑 [維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM) 製卡] ⚡ 蟲洞讀卡逆查觸發 ➔ 收到德安要求讀取製卡機 【{doorcard_machine}】 上的卡片")

    # 2. 物理模擬：動態生成 6 碼大寫英數隨機空卡卡號
    import secrets
    import string
    alphabet = string.ascii_uppercase + string.digits
    simulated_card_uid = ''.join(secrets.choice(alphabet) for _ in range(6))
    
    # 3. 構造虛擬的卡片資產節點
    simulated_card_node = {
        "orderID": "",  
        "cardUid": simulated_card_uid,
        "type": "card"
    }
    
    # 4. 調用策略層封裝回應
    # 💡 檢查點：確保內部傳入的是新宣告的 doorcard_machine (如果策略層有改的話)
    # 如果策略層還是吃原始 room_id，這裡維持不變
    formatted_response = WaferlockLiveam_strategy.transform_card_info_response(simulated_card_node, room_id=0) #
    
    # 外掛外殼欄位，確保德安中台能精準解讀
    formatted_response["cardUid"] = simulated_card_uid
    formatted_response["pmrId"] = doorcard_machine  # 👈 檢查這裡！原本可能手誤寫成 encoder_code 導致 500！
    
    print(f"   🟢 [物理模擬成功] 成功回報德安 ➔ 機器 【{doorcard_machine}】 偵測到實體空卡 UID: 【{simulated_card_uid}】")
    return jsonify(formatted_response), 200