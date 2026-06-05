# server/amenity/routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import config
from .vendors.vendor_BI_RSAI import VendorBRStrategy

amenity_bp = Blueprint('amenity', __name__)

# 策略工廠動態載入
vendor_strategy = VendorBRStrategy()

# 💡 模擬飯店內部的「在店住客資料庫 (In-House Guest Database)」
# 預先初始化測試房號：1001
mock_inhouse_db = {
    "1001": [
        {
            "guest_id": "20260413001",
            "room_nos": "1001",
            "room_serial": "001",
            "guest_name": "王小明",
            "order_remark": "備註事項：高樓層、不要靠電梯",
            "checkout_remark": "退房通知：需開立統編發票",
            "sum_item_total": 1000.00,
            "sum_advc_total": 500.00,
            "pre_credit_amount": 0.00,
            "group_nos": "TA-G001",
            "enabled": True  # True=可住掛(O) | False=不可住掛(K)
        }
    ]
}

# 💡 新增模擬：飯店實體前台製卡發放的「房卡卡號 ➔ 房號對照資料庫」
mock_card_mapping_db = {
    "123456789": "1001"  # 實體房卡卡號 123456789 目前綁定在 1001 房
}

# 💡 新增模擬：飯店帳務歷史交易聯調資料庫 (主鍵為小美犀唯一值 orderNos)
mock_transaction_db = {}

# 💡 虛擬在店住客資料庫 (擴充：補齊 2403 範例房號，達成全量聯調測試)
mock_inhouse_db = {
    "1001": [
        {
            "guest_id": "20260413001",
            "room_nos": "1001",
            "room_serial": "001",
            "guest_name": "王小明",
            "order_remark": "備註事項：高樓層",
            "checkout_remark": "退房通知：需統編",
            "sum_item_total": 1000.00,
            "sum_advc_total": 500.00,
            "pre_credit_amount": 0.00,
            "group_nos": "TA-G001",
            "enabled": True
        }
    ],
    "2403": [
        {
            "guest_id": "20260605044",
            "room_nos": "2403",
            "room_serial": "002",
            "guest_name": "林大華",
            "order_remark": "小美犀高頻測試房",
            "checkout_remark": "房務備品入帳專用房",
            "sum_item_total": 0.00,  # 初始消費為 0
            "sum_advc_total": 0.00,
            "pre_credit_amount": 0.00,
            "group_nos": "",
            "enabled": True
        }
    ]
}

mock_card_mapping_db = {"123456789": "1001"}
mock_transaction_db = {}

# ====================================================================
# 🦏 🚀 1. 房號查詢取得住客端點 (GET /room-pay/room-nos)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay/room-nos', methods=['GET'])
def query_guest_by_room_nos():
    # 1. 👮‍♂️ 第一道防線：校準 Header 必填參數，不對齊直接拒絕，防禦 TraceLog
    athena = request.headers.get('athena')
    hotel = request.headers.get('hotel')
    
    if not athena or not hotel:
        print("🚨 [小美犀 - 房號查詢錯誤] Header 遺失關鍵憑證 athena 或 hotel！")
        return jsonify({"code": "400", "message": "Bad Request. Missing identification headers."}), 400
        
    # 2. 👮‍♂️ 第二道防線：校準 URL Query 必填參數
    third_party = request.args.get('thirdParty')
    keyword_room = request.args.get('keyword') # 房號
    
    if not third_party or not keyword_room:
        print("🚨 [小美犀 - 房號查詢錯誤] URL 參數遺失 thirdParty 或 keyword！")
        return jsonify({"code": "400", "message": "Bad Request. Missing query parameters."}), 400

    room_key = str(keyword_room).strip()
    print(f"\n🦏 [小美犀 Webhook] 收到房號查詢 -> 房號: 【{room_key}】| 廠商: {third_party}")

    # 3. 🔍 第三道防線：檢索虛擬資料庫
    if room_key in mock_inhouse_db and len(mock_inhouse_db[room_key]) > 0:
        target_guests = mock_inhouse_db[room_key]
        
        # 調用小美犀專屬策略，洗滌出 Array 結構
        formatted_response = vendor_strategy.transform_room_nos_query_response(target_guests)
        
        print(f" 🟢 [查詢成功] 房號 {room_key} 處於在店狀態，成功回傳住客清單共 {len(formatted_response)} 筆。")
        return jsonify(formatted_response), 200
    else:
        # 🎯 完美對齊官方合約：查無資料時，必須回傳 HTTP 417 與自訂 code/message
        print(f" 🔴 [查詢失敗] 沙盒內無房號 【{room_key}】 之入住紀錄，發動 417 攔截防禦。")
        return jsonify({
            "code": "1001",
            "message": "查無此房號"
        }), 417
    
# ====================================================================
# 🦏 🚀 2. 房卡卡號查詢取得住客端點 (GET /room-pay/mifare-nos)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay/mifare-nos', methods=['GET'])
def query_guest_by_mifare_nos():
    # 1. 👮‍♂️ Header 必填參數校驗
    athena = request.headers.get('athena')
    hotel = request.headers.get('hotel')
    if not athena or not hotel:
        print("🚨 [小美犀 - 卡號查詢錯誤] Header 遺失 athena 或 hotel！")
        return jsonify({"code": "400", "message": "Bad Request. Missing identification headers."}), 400
        
    # 2. 👮‍♂️ URL Query 必填參數校驗
    third_party = request.args.get('thirdParty')
    keyword_card = request.args.get('keyword') # 房卡卡號
    if not third_party or not keyword_card:
        print("🚨 [小美犀 - 卡號查詢錯誤] URL 參數遺失 thirdParty 或 keyword！")
        return jsonify({"code": "400", "message": "Bad Request. Missing query parameters."}), 400

    card_key = str(keyword_card).strip()
    print(f"\n🦏 [小美犀 Webhook] 收到房卡卡號查詢 -> 卡號: 【{card_key}】| 廠商: {third_party}")

    # 3. 🔍 核心逆查機制：卡號 ➔ 房號 ➔ 住客主檔
    if card_key in mock_card_mapping_db:
        mapped_room = mock_card_mapping_db[card_key]
        print(f" 🎯 [卡號逆查成功] 卡號 【{card_key}】 隸屬於房號: 【{mapped_room}】")
        
        # 向在店住客資料庫索取整包資料
        if mapped_room in mock_inhouse_db and len(mock_inhouse_db[mapped_room]) > 0:
            target_guests = mock_inhouse_db[mapped_room]
            
            # 調用策略層洗滌輸出
            formatted_response = vendor_strategy.transform_mifare_nos_query_response(target_guests)
            
            print(f" 🟢 [查詢成功] 卡號對齊成功，成功回傳住客清單共 {len(formatted_response)} 筆。")
            return jsonify(formatted_response), 200
            
    # 4. 🎯 失敗防禦：若卡號未登記，或該卡號綁定的房號已退房，外發 417
    print(f" 🔴 [查詢失敗] 沙盒內無卡號 【{card_key}】 之有效發卡紀錄，發動 417 攔截。")
    return jsonify({
        "code": "1002",
        "message": "查無此房卡卡號"
    }), 417

# ====================================================================
# 🦏 🚀 3. 餐廳消費住掛入帳端點 (POST /room-pay)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay', methods=['POST'])
def receive_room_pay_settlement():
    # 1. 👮‍♂️ Header 必填參數校驗
    athena = request.headers.get('athena')
    hotel = request.headers.get('hotel')
    if not athena or not hotel:
        print("🚨 [小美犀 - 住掛房帳錯誤] Header 遺失憑證 athena 或 hotel！")
        return jsonify({"code": "400", "message": "Missing identification headers."}), 400
        
    if not request.is_json:
        return jsonify({"code": "415", "message": "Unsupported Media Type. JSON expected."}), 415
        
    data = request.get_json()
    third_party = request.args.get('thirdParty', 'BR')
    
    try:
        # 2. 調用策略層進行複雜主明細 Payload 解析與欄位洗滌
        clean_pay = vendor_strategy.parse_pms_room_pay(data)
        guest_id = clean_pay["guest_id"]
        room_nos = clean_pay["room_nos"]
        order_nos = clean_pay["order_nos"]
        pay_amount = clean_pay["pay_amount"]
        
        print(f"\n🦏 [小美犀 Webhook] 收到消費住掛入帳 -> 房號: 【{room_nos}】| 金額: ${pay_amount} | 訂單號: {order_nos}")

        # 3. 🔍 核心防禦校驗：比對在店住客主檔是否存在且對齊
        guest_matched = False
        if room_nos in mock_inhouse_db:
            for guest in mock_inhouse_db[room_nos]:
                if guest["guest_id"] == guest_id:
                    
                    # 💡 增量落庫邏輯（帳務動態閉環）：累加此住客在店的消費總額
                    guest["sum_item_total"] += pay_amount
                    guest_matched = True
                    break
                    
        if not guest_matched:
            # 🎯 完美對齊官方合約：無符合住客資料時，拋出 HTTP 417
            print(f" 🔴 [入帳失敗] 住客序號 【{guest_id}】 與房號 【{room_nos}】 不對齊或已離店，發動 417 阻擋。")
            return jsonify({
                "code": "1001",
                "message": "無符合的住客資料"
            }), 417

        # 4. 🗃️ 儲存歷史帳務單據 (供未來取消住掛沖帳調用)
        acct_nos = f"ACCT{datetime.now().strftime('%M%S')}" # 產生虛擬入帳單號
        mock_transaction_db[order_nos] = {
            "acct_nos": acct_nos,
            "guest_id": guest_id,
            "room_nos": room_nos,
            "pay_amount": pay_amount,
            "details": clean_pay["details"],
            "status": "SETTLED"  # SETTLED = 已入帳 | CANCELED = 已沖正
        }
        
        # 5. 封裝成功 Response
        formatted_response = vendor_strategy.transform_room_pay_success_response(acct_nos)
        print(f" 🟢 [入帳成功] 帳款整合完畢。產出 PMS 入帳單號: 【{acct_nos}】| 該房當前累計消費: ${mock_inhouse_db[room_nos][0]['sum_item_total']}")
        return jsonify(formatted_response), 200
        
    except Exception as e:
        print(f" 🚨 [住掛房帳崩潰]: {e}")
        return jsonify({"code": "500", "message": f"Internal bookkeeping error: {str(e)}"}), 500
    
# ====================================================================
# 🦏 🚀 4. 餐廳住掛取消沖正端點 (POST /room-pay-cancel)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay-cancel', methods=['POST'])
def receive_room_pay_cancel():
    # 1. 👮‍♂️ Header 必填憑證校驗
    athena = request.headers.get('athena')
    hotel = request.headers.get('hotel')
    if not athena or not hotel:
        print("🚨 [小美犀 - 住掛取消錯誤] Header 遺失憑證 athena 或 hotel！")
        return jsonify({"code": "400", "message": "Missing identification headers."}), 400

    third_party = request.args.get('thirdParty', 'BR')
    order_nos = request.args.get('orderNos')  # 💡 關鍵：由 URL 參數提取欲取消的單號
    
    if not order_nos:
        print("🚨 [小美犀 - 住掛取消錯誤] URL 參數遺失欲沖正之訂單單號 orderNos！")
        return jsonify({"code": "400", "message": "Missing query parameter 'orderNos'."}), 400

    print(f"\n🦏 [小美犀 Webhook] 收到餐廳住掛取消請求 -> 欲沖正單號: 【{order_nos}】| 廠商: {third_party}")

    # 2. 🔍 第一道帳務防禦：歷史單據庫追溯
    if order_nos not in mock_transaction_db:
        print(f" 🔴 [沖正失敗] 歷史單據庫查無此單號 【{order_nos}】，發動 417 拒絕。")
        return jsonify({
            "code": "2007",
            "message": "查無此入帳單號，不可掛帳取消。"
        }), 417
        
    tx_record = mock_transaction_db[order_nos]
    
    # 3. 🔍 第二道帳務防禦：防止重複取消（Idempotency Check）
    if tx_record["status"] == "CANCELED":
        print(f" ⚠️ [沖正警告] 單號 【{order_nos}】 先前已完成取消，不可重複沖正。")
        return jsonify({
            "code": "2007",
            "message": "此帳項已完成取消沖正。"
        }), 417

    room_nos = tx_record["room_nos"]
    guest_id = tx_record["guest_id"]
    refund_amount = tx_record["pay_amount"]

    # 4. 🧠 核心增量反轉：追溯主檔，將 Folio 房帳金額精準扣回（邏輯反轉）
    account_purged = False
    if room_nos in mock_inhouse_db:
        for guest in mock_inhouse_db[room_nos]:
            if guest["guest_id"] == guest_id:
                
                # 💡 模擬結帳防禦：若住客狀態在沙盒已被改成停用(停用=已退房結帳)
                if not guest["enabled"]:
                    print(f" 🔴 [沖正失敗] 住客 【{guest['guest_name']}】 已辦理退房結帳，發動 417 防禦。")
                    return jsonify({
                        "code": "2007",
                        "message": "客房已結帳. 不可掛帳取消"
                    }), 417
                
                # 實施紅字扣除
                guest["sum_item_total"] -= refund_amount
                account_purged = True
                break

    if not account_purged:
        print(f" 🔴 [沖正失敗] 該筆交易對應之住客主檔已不存在沙盒中，發動 417。")
        return jsonify({
            "code": "2007",
            "message": "住客主檔已移出，客房已結帳. 不可掛帳取消"
        }), 417

    # 5. 🗃️ 變更交易單據狀態為 CANCELED 封存
    cancel_acct_nos = f"ACCT{datetime.now().strftime('%M%S')}"
    tx_record["status"] = "CANCELED"
    tx_record["cancel_acct_nos"] = cancel_acct_nos
    
    # 6. 調用策略層封裝特殊 JSON 語意回傳
    formatted_response = vendor_strategy.transform_room_pay_cancel_success_response(cancel_acct_nos)
    print(f" 🟢 [沖正成功] 紅字沖帳完畢！已將 ${refund_amount} 從房帳中扣除。")
    print(f"   產出取消單號: 【{cancel_acct_nos}】 | 該房剩餘消費額: ${mock_inhouse_db[room_nos][0]['sum_item_total']}")
    
    return jsonify(formatted_response), 200

# ====================================================================
# 🦏 🚀 5. 房務服務與付費備品獨立入帳端點 (POST /room-billing)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-billing', methods=['POST'])
def receive_room_billing_settlement():
    # 1. 👮‍♂️ Header 必填參數憑證校驗
    athena = request.headers.get('athena')
    hotel = request.headers.get('hotel')
    if not athena or not hotel:
        print("🚨 [小美犀 - 房務入帳錯誤] Header 遺失憑證 athena 或 hotel！")
        return jsonify({"code": "400", "message": "Missing identification headers."}), 400
        
    if not request.is_json:
        return jsonify({"code": "415", "message": "Unsupported Media Type. JSON expected."}), 415
        
    data = request.get_json()
    third_party = request.args.get('thirdParty', 'BR')
    
    try:
        # 2. 調用策略層進行房務平面明細洗滌
        clean_billing = vendor_strategy.parse_pms_room_billing(data)
        room_nos = clean_billing["room_nos"]
        items = clean_billing["items"]
        
        print(f"\n🦏 [小美犀 Webhook] 收到房務備品入帳 -> 房號: 【{room_nos}】| 品項數: {len(items)} 筆 | 廠商: {third_party}")

        # 3. 🔍 核心在店查核防禦
        if room_nos not in mock_inhouse_db or len(mock_inhouse_db[room_nos]) == 0:
            # 🎯 完美對齊官方合約：此房間無住客或已退房，外發 HTTP 417
            print(f" 🔴 [房務入帳失敗] 沙盒內無房間 【{room_nos}】 之在店住客紀錄，發動 417 攔截。")
            return jsonify({
                "code": "1001",
                "message": "此房間無住客"
            }), 417

        # 4. 🧠 帳務狀態累加閉環 (模擬每件備品扣款，假設每件付費備品在 Staging 環境計價為 $100 元作虛擬累加)
        guest = mock_inhouse_db[room_nos][0]
        
        # 模擬結帳防禦：若住客被設定為停用
        if not guest["enabled"]:
            print(f" 🔴 [房務入帳失敗] 房間 【{room_nos}】 之住客已辦理退房結帳，發動 417 阻擋。")
            return jsonify({
                "code": "1001",
                "message": "此房間無住客"
            }), 417
            
        for item in items:
            simulated_price = 100.00 * item["quantity"]
            guest["sum_item_total"] += simulated_price
            print(f"   📦 [備品扣款成功] 序號: {item['seq_nos']} | 編號: {item['product_nos']} | 數量: {item['quantity']} -> 記帳: ${simulated_price}")

        # 5. 🟢 完美對齊官方成功回應：HTTP 200 (回傳極簡空物件或成功標誌，依據規範直接回傳 200 放行)
        print(f" 🟢 [房務入帳成功] 房務備品清單整合完畢。該房當前累計總帳: ${guest['sum_item_total']}")
        return jsonify({}), 200
        
    except Exception as e:
        print(f" 🚨 [房務入帳崩潰]: {e}")
        return jsonify({"code": "500", "message": f"Internal housekeeping billing failed: {str(e)}"}), 500