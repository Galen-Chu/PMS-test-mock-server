# server/keycard/routes.py
from flask import Blueprint, request, jsonify
from .vendors.vendor_LIVEAM import VendorLiveamStrategy

keycard_bp = Blueprint('keycard', __name__)
liveam_strategy = VendorLiveamStrategy()

# 🔑 記憶體權限保險箱：儲存所有已簽發、具效力的 Token
liveam_session_vault = set()

# 🗃️ 華豫寧訂單暫存資料庫 (主鍵為訂單 id)
liveam_order_db = {}

# 🗃️ 3. 華豫寧實體卡片資產庫 (主鍵為 cardUid)
liveam_card_db = {}

def verify_liveam_token():
    """👮‍♂️ 內部防禦：查驗 Header 中的 Token 是否合法"""
    auth_header = request.headers.get("Authorization", "")
    
    # 相容 Token 帶有 Bearer 或純字串的洗滌
    token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
    
    if not token or token not in liveam_session_vault:
        return False
    return True

# ====================================================================
# 🔑 🚀 1. 廠商身份鑑權端點 (POST /api/Auth/login)
# ====================================================================
@keycard_bp.route('/api/Auth/login', methods=['POST'])
def keycard_vendor_login():
    if not request.is_json:
        return jsonify({"error": 99, "desc": "Unsupported Media Type", "msg": "請使用 JSON 傳輸規格"}), 415
        
    body_data = request.get_json()
    print(f"\n🔑 [華豫寧門禁 Mock] 收到德安 PMS 登入請求 -> ID: {body_data.get('id')} | ProjectID: {body_data.get('projectID')}")
    
    # 執行策略層鑑權洗滌
    response_payload, status_code = liveam_strategy.authenticate_login(body_data)
    
    if status_code == 200:
        # 將簽發的 Token 鎖入保險箱，供後續 Order / Card 路由檢索
        generated_token = response_payload["token"]
        liveam_session_vault.add(generated_token)
        print(f" 🟢 [鑑權成功] 已簽發 72 小時有效代幣: 【{generated_token}】")
    else:
        print(f" 🔴 [鑑權失敗] 認證未通過，拋出 400 阻擋。原因: {response_payload.get('msg')}")
        
    return jsonify(response_payload), status_code

# ====================================================================
# 🔑 🚀 2. 新增門禁訂單端點 (POST /api/Order)
# ====================================================================
@keycard_bp.route('/api/Order', methods=['POST'])
def create_keycard_order():
    # 1. 👮‍♂️ 安全校驗：驗證 Token 權限
    if not verify_liveam_token():
        return jsonify({"error": "Invalid or expired token."}), 401
        
    if not request.is_json:
        return jsonify({"error": 400, "desc": "Bad Request", "msg": "Payload 必須為 JSON"}), 400
        
    body_data = request.get_json()
    cleaned_order = liveam_strategy.clean_order_payload(body_data)
    order_id = cleaned_order["id"]
    
    print(f"\n🔑 [華豫寧門禁 Mock] 收到新增訂單請求 ➔ 訂單ID: 【{order_id}】| 房號ID: {cleaned_order['roomID']}")

    # 2. 🛑 409 衝突防禦：主鍵唯一性校驗
    if order_id in liveam_order_db:
        print(f" 🔴 [新增失敗] 訂單 ID 【{order_id}】 已存在於門禁系統，觸發 409 衝突阻擋。")
        return jsonify({
            "error": 4091,
            "desc": "Order Conflict",
            "msg": f"訂單單號 {order_id} 已存在，不可重複建立。"
        }), 409

    # 3. 💾 落庫儲存
    liveam_order_db[order_id] = cleaned_order
    print(f" 🟢 [新增成功] 訂單預備落庫完成。住客: {cleaned_order['guestName']} | 狀態: 0 (預備狀態)")
    
    # 完美對齊 201 Created 回傳整包物件合約
    return jsonify(cleaned_order), 201

# ====================================================================
# 🔑 🚀 3. 修改/啟用門禁訂單端點 (PUT /api/Order)
# ====================================================================
@keycard_bp.route('/api/Order', methods=['PUT'])
def update_keycard_order():
    # 1. 👮‍♂️ 安全校驗
    if not verify_liveam_token():
        return jsonify({"error": "Invalid or expired token."}), 401
        
    if not request.is_json:
        return jsonify({"error": 400, "desc": "Bad Request", "msg": "Payload 必須為 JSON"}), 400
        
    body_data = request.get_json()
    cleaned_order = liveam_strategy.clean_order_payload(body_data)
    order_id = cleaned_order["id"]

    print(f"\n🔑 [華豫寧門禁 Mock] 收到修改訂單請求 ➔ 訂單ID: 【{order_id}】")

    # 2. 🛑 404 查無訂單防禦
    if order_id not in liveam_order_db:
        print(f" 🔴 [修改失敗] 門禁系統內查無訂單 ID 【{order_id}】，外發 404 攔截。")
        return jsonify({
            "error": 4041,
            "desc": "Order Not Found",
            "msg": "查無此訂單 ID，無法進行客房權限修改。"
        }), 404

    # 3. 🧠 權限激活核心：非破壞性覆寫，模擬實體客房開門權限解鎖
    old_order = liveam_order_db[order_id]
    old_order.update(cleaned_order) # 動態更新包含 checkinTime 的新資產
    
    print(f" 🟢 [修改成功] 權限啟用完畢！")
    print(f"   🔓 實體權限區間: 【{old_order['checkinTime']}】 ➔ 【{old_order['preOutTime']}】 可感應進房。")
    
    # 完美對齊 200 OK 成功合約 (通常回傳 200 或空物件，依規格直接回傳 200 放行)
    return jsonify({}), 200

# ====================================================================
# 🔑 🚀 4. 新增訂單卡片端點 (POST /api/OrderCard)
# ====================================================================
@keycard_bp.route('/api/OrderCard', methods=['POST'])
def create_keycard_asset():
    # 1. 👮‍♂️ 安全校驗
    if not verify_liveam_token():
        return jsonify({"error": "Unauthorized"}), 401
        
    if not request.is_json:
        return jsonify({"error": 400, "desc": "Bad Request", "msg": "Payload 必須為 JSON"}), 400
        
    body_data = request.get_json()
    order_id = str(body_data.get("orderID", "")).strip()
    card_uid = str(body_data.get("cardUid", "")).strip()
    
    print(f"\n🔑 [華豫寧門禁 Mock] 收到製卡發卡請求 ➔ 訂單: 【{order_id}】| 卡號: 【{card_uid}】")

    # 2. 🛑 400 參數檢驗與 404 訂單不存在檢驗
    if not order_id or not card_uid:
        return jsonify({"error": 4002, "desc": "Bad Request", "msg": "orderID 或 cardUid 不可為空"}), 400
        
    if order_id not in liveam_order_db:
        print(f" 🔴 [製卡失敗] 門禁系統內無此訂單 【{order_id}】，無法綁定實體卡片。")
        return jsonify({"error": 4042, "desc": "Order Not Found", "msg": "找不到對應的訂單主檔"}), 404

    # 3. 🛑 409 卡片資產衝突防禦
    if card_uid in liveam_card_db:
        print(f" 🔴 [製卡失敗] 卡號 【{card_uid}】 已被其他訂單佔用，發動 409 攔截。")
        return jsonify({"error": 4092, "desc": "Card Conflict", "msg": "此實體卡片已被使用中"}), 409

    # 4. 💾 卡片落庫
    card_node = {
        "orderID": order_id,
        "cardUid": card_uid,
        "type": "card" # 預設為實體卡片，若為手機可傳 ios/android
    }
    liveam_card_db[card_uid] = card_node
    
    # ⚡ 跨模組重大連動（數據自動閉環）：
    # 藉由 orderID 反查該單在門禁系統登記的房號 (roomID)，並實時灌入小美犀的卡片對照表！
    target_room_id = str(liveam_order_db[order_id]["roomID"])
    try:
        from server.amenity.routes import mock_card_mapping_db
        mock_card_mapping_db[card_uid] = target_room_id
        print(f"   ⚙️  [跨模組連動成功] 已自動將卡號 【{card_uid}】 與房號 【{target_room_id}】 綁定關係注入小美犀記憶體！")
    except Exception as e:
        print(f"   ⚠️  [跨模組連動提示] 注入小美犀對照表失敗 (可能尚未掛載藍圖): {e}")

    print(f" 🟢 [製卡成功] 實體卡片發放完畢並完成綁定。")
    # 完美對齊 201 Created 成功合約
    return jsonify(card_node), 201

# ====================================================================
# 🔑 🚀 5. 刪除註銷卡片端點 (DELETE /api/OrderCard/{oid}/{cuid})
# ====================================================================
@keycard_bp.route('/api/OrderCard/<string:oid>/<string:cuid>', methods=['DELETE'])
def delete_keycard_asset(oid, cuid):
    # 1. 👮‍♂️ 安全校驗
    if not verify_liveam_token():
        return jsonify({"error": "Unauthorized"}), 401
        
    order_id = str(oid).strip()
    card_uid = str(cuid).strip()
    
    print(f"\n🔑 [華豫寧門禁 Mock] 收到註銷銷卡請求 ➔ 訂單: 【{order_id}】| 卡號: 【{card_uid}】")

    # 2. 🛑 404 查無資產防禦
    if card_uid not in liveam_card_db or liveam_card_db[card_uid]["orderID"] != order_id:
        print(f" 🔴 [銷卡失敗] 系統內查無卡號 【{card_uid}】 與訂單 【{order_id}】 的綁定紀錄，發動 404。")
        return jsonify({"error": 4043, "desc": "Card Asset Not Found", "msg": "查無此卡片資產綁定紀錄"}), 404

    # 3. 🗑️ 執行物理移除銷毀
    del liveam_card_db[card_uid]
    
    # ⚡ 跨模組反向數據清洗（Soft/Hard 清洗閉環）：
    # 同步將此卡號從小美犀的刷卡對照表中拔除，防禦退房旅客非法掛帳！
    try:
        from server.amenity.routes import mock_card_mapping_db
        if card_uid in mock_card_mapping_db:
            del mock_card_mapping_db[card_uid]
            print(f"   ⚙️  [跨模組連動成功] 已從小美犀記憶體中撤銷卡號 【{card_uid}】 的掛帳權限。")
    except Exception as e:
        pass

    print(f" 🟢 [銷卡成功] 卡片已完成回收/註銷銷毀。")
    # 完美對齊 200 OK 成功合約 (通常返回空或 200)
    return jsonify({}), 200

# ====================================================================
# 🔑 🚀 6. 模擬讀卡機卡片逆查端點 (POST /api/Operation/getCardInfo/{pmrId})
# ====================================================================
@keycard_bp.route('/api/Operation/getCardInfo/<string:pmrId>', methods=['POST'])
def get_keycard_info_by_uid(pmrId):
    # 1. 👮‍♂️ 安全校驗：驗證門禁專屬 Token
    if not verify_liveam_token():
        return jsonify({"error": "Unauthorized"}), 401
        
    card_uid = str(pmrId).strip()
    print(f"\n🔑 [華豫寧門禁 Mock] ⚡ 蟲洞端點觸發 ➔ 實體感應讀卡逆查 CUID: 【{card_uid}】")

    # 2. 🔍 第一步：去卡片資產庫檢索這張卡有沒有被製作出來
    if card_uid not in liveam_card_db:
        print(f" 🔴 [逆查失敗] 門禁卡片庫中無卡號 【{card_uid}】 的發卡紀錄，發動 404 阻擋。")
        return jsonify({
            "error": 4044,
            "desc": "Card Not Found",
            "msg": "此卡片未發卡或已被消卡註銷"
        }), 404

    card_node = liveam_card_db[card_uid]
    order_id = card_node["orderID"]

    # 3. 🔍 第二步：透過關聯 orderID 摸回訂單庫，抓取實體綁定的 roomID (房號)
    room_id = 0
    if order_id in liveam_order_db:
        room_id = liveam_order_db[order_id]["roomID"]
        print(f"   🎯 [InMemory JOIN 成功] 卡號 【{card_uid}】 ➔ 關聯訂單 【{order_id}】 ➔ 鎖定實體房號: 【{room_id}】")
    else:
        print(f" ⚠️ [逆查警告] 雖有卡片資產，但對應之訂單主檔已真空遺失。")

    # 4. 🧼 調用策略層封裝高真回應
    formatted_response = liveam_strategy.transform_card_info_response(card_node, room_id)
    
    print(f" 🟢 [逆查成功] 已將門禁系統內的物理綁定關係全量回傳。")
    return jsonify(formatted_response), 200