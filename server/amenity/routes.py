# server/amenity/routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import config
from .vendors.vendor_BR_AIELLO import VendorBRAielloStrategy

amenity_bp = Blueprint('amenity', __name__)
vendor_strategy = VendorBRAielloStrategy()

# 💡 高高傳真虛擬在店住客資料庫 (完美對齊德安 Swagger 吐出的真實數據結構與房號)
mock_inhouse_db = {
    "101": [
        {
            "guest_id": "20260605000001",
            "room_nos": "101",
            "room_serial": "1",
            "guest_name": "壹梯環境",
            "order_remark": "Swagger 真實測資 1",
            "checkout_remark": "",
            "sum_item_total": 11854.00,
            "sum_advc_total": 0.00,
            "pre_credit_amount": 0.00,
            "group_nos": "壹梯環境",
            "enabled": True
        }
    ],
    "102": [
        {
            "guest_id": "20260603000003",
            "room_nos": "102",
            "room_serial": "1",
            "guest_name": "Galen Galen_777",
            "order_remark": "Galen 專屬測試房",
            "checkout_remark": "",
            "sum_item_total": 23708.00,
            "sum_advc_total": 0.00,
            "pre_credit_amount": 0.00,
            "group_nos": "Galen",
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
            "sum_item_total": 0.00,
            "sum_advc_total": 0.00,
            "pre_credit_amount": 0.00,
            "group_nos": "",
            "enabled": True
        }
    ]
}

mock_card_mapping_db = {
    "123456789": "102" # 讓實體卡片綁定在你的 Galen_777 房
}
mock_transaction_db = {}

# ====================================================================
# 🦏 🚀 1. 房號查詢取得住客端點 (GET /room-pay/room-nos)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay/room-nos', methods=['GET'])
def query_guest_by_room_nos():
    # 1. 👮‍♂️ 第一道防線：精準對齊德安實體系統的 bacchus- 系列 Header
    athena_id = request.headers.get('bacchus-athenaid') or request.headers.get('athena')
    hotel_cod = request.headers.get('bacchus-hotelcod') or request.headers.get('hotel')
    
    if not athena_id or not hotel_cod:
        print(f"🚨 [小美犀 Webhook] 拒絕連線：Header 缺乏 bacchus 憑證！ 拿到的是: athenaid={athena_id}, hotelcod={hotel_cod}")
        return jsonify({"code": "400", "message": "Bad Request. Missing bacchus identification headers."}), 400
        
    # 2. 👮‍♂️ 第二道防線：校準 URL Query 參數 (thirdParty 為必填，keyword 變更為純可選)
    third_party = request.args.get('thirdParty')
    keyword_room = request.args.get('keyword') 

    if not third_party:
        print("🚨 [小美犀 Webhook] 拒絕連線：URL 參數遺失必填之 thirdParty 代碼！")
        return jsonify({"code": "400", "message": "Bad Request. Missing thirdParty parameter."}), 400

    # 3. 🔍 核心機制分流
    # 🎯 情境 A：德安未傳送 keyword -> 啟動「全量房號資料夾拉取」
    if not keyword_room or str(keyword_room).strip() == "":
        print(f"\n🦏 [小美犀 Webhook] 📥 接收德安 PMS 主動號令 ➔ 觸發【全量房號名單同步】| 廠商: {third_party}")
        all_guests = []
        for room_list in mock_inhouse_db.values():
            all_guests.extend(room_list)
            
        formatted_response = vendor_strategy.transform_room_nos_query_response(all_guests)
        print(f" 🟢 [全量同步回執] 成功將沙盒記憶體共 {len(formatted_response)} 筆高真在店資產打包回傳德安。")
        return jsonify(formatted_response), 200

    # 🎯 情境 B：德安傳送單一房號 -> 精準過濾
    room_key = str(keyword_room).strip()
    print(f"\n🦏 [小美犀 Webhook] 📥 接收德安 PMS 主動號令 ➔ 收到單一房號查詢: 【{room_key}】| 廠商: {third_party}")
    
    if room_key in mock_inhouse_db and len(mock_inhouse_db[room_key]) > 0:
        formatted_response = vendor_strategy.transform_room_nos_query_response(mock_inhouse_db[room_key])
        return jsonify(formatted_response), 200
    else:
        print(f" 🔴 [查詢未命中] 沙盒內查無房號 【{room_key}】，外發 417。")
        return jsonify({"code": "1001", "message": "查無此房號"}), 417

# ====================================================================
# 🦏 🚀 2. 房卡卡號查詢取得住客端點 (GET /room-pay/mifare-nos)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay/mifare-nos', methods=['GET'])
def query_guest_by_mifare_nos():
    # 1. 👮‍♂️ Header 憑證校驗
    athena_id = request.headers.get('bacchus-athenaid') or request.headers.get('athena')
    hotel_cod = request.headers.get('bacchus-hotelcod') or request.headers.get('hotel')
    if not athena_id or not hotel_cod:
        return jsonify({"code": "400", "message": "Bad Request. Missing bacchus headers."}), 400
        
    # 2. 👮‍♂️ URL Query 校驗 (移除對 keyword_card 的強行必填限制)
    third_party = request.args.get('thirdParty')
    keyword_card = request.args.get('keyword')

    if not third_party:
        return jsonify({"code": "400", "message": "Bad Request. Missing thirdParty."}), 400

    # 3. 🔍 核心逆查機制
    # 🎯 情境 A：未傳送卡號 -> 啟動「全量房卡卡號逆查同步」
    if not keyword_card or str(keyword_card).strip() == "":
        print(f"\n🦏 [小美犀 Webhook] 📥 接收德安 PMS 主動號令 ➔ 觸發【全量房卡名單同步】| 廠商: {third_party}")
        all_guests = []
        for card_no, room_no in mock_card_mapping_db.items():
            if room_no in mock_inhouse_db:
                all_guests.extend(mock_inhouse_db[room_no])
                
        formatted_response = vendor_strategy.transform_mifare_nos_query_response(all_guests)
        print(f" 🟢 [全量同步回執] 成功將沙盒記憶體共 {len(formatted_response)} 筆綁卡資產打包回傳德安。")
        return jsonify(formatted_response), 200

    # 🎯 情境 B：單一卡號逆查
    card_key = str(keyword_card).strip()
    print(f"\n🦏 [小美犀 Webhook] 📥 接收德安 PMS 主動號令 ➔ 收到單一房卡查詢: 【{card_key}】")
    
    if card_key in mock_card_mapping_db:
        mapped_room = mock_card_mapping_db[card_key]
        if mapped_room in mock_inhouse_db and len(mock_inhouse_db[mapped_room]) > 0:
            formatted_response = vendor_strategy.transform_mifare_nos_query_response(mock_inhouse_db[mapped_room])
            return jsonify(formatted_response), 200
            
    return jsonify({"code": "1002", "message": "查無此房卡卡號"}), 417

# ====================================================================
# 🦏 🚀 3. 餐廳消費住掛入帳端點 (POST /room-pay)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay', methods=['POST'])
def receive_room_pay_settlement():
    athena_id = request.headers.get('bacchus-athenaid') or request.headers.get('athena')
    hotel_cod = request.headers.get('bacchus-hotelcod') or request.headers.get('hotel')
    if not athena_id or not hotel_cod:
        return jsonify({"code": "400", "message": "Missing bacchus identification headers."}), 400
        
    if not request.is_json:
        return jsonify({"code": "415", "message": "Unsupported Media Type. JSON expected."}), 415
        
    data = request.get_json()
    
    try:
        clean_pay = vendor_strategy.parse_pms_room_pay(data)
        guest_id = clean_pay["guest_id"]
        room_nos = clean_pay["room_nos"]
        order_nos = clean_pay["order_nos"]
        pay_amount = clean_pay["pay_amount"]
        
        print(f"\n🦏 [小美犀 Webhook] 📥 接收德安主動落帳 ➔ 房號: 【{room_nos}】| 金額: ${pay_amount} | 訂單號: {order_nos}")

        guest_matched = False
        if room_nos in mock_inhouse_db:
            for guest in mock_inhouse_db[room_nos]:
                if guest["guest_id"] == guest_id:
                    guest["sum_item_total"] += pay_amount
                    guest_matched = True
                    break
                    
        if not guest_matched:
            print(f" 🔴 [入帳失敗] 住客序號 【{guest_id}】 與房號 【{room_nos}】 不匹配，發動 417。")
            return jsonify({"code": "1001", "message": "無符合的住客資料"}), 417

        acct_nos = f"ACCT{datetime.now().strftime('%M%S')}"
        mock_transaction_db[order_nos] = {
            "acct_nos": acct_nos, "guest_id": guest_id, "room_nos": room_nos,
            "pay_amount": pay_amount, "details": clean_pay["details"], "status": "SETTLED"
        }
        
        formatted_response = vendor_strategy.transform_room_pay_success_response(acct_nos)
        print(f" 🟢 [入帳成功] 產出明細單號: 【{acct_nos}】| 該房當前總帳: ${mock_inhouse_db[room_nos][0]['sum_item_total']}")
        return jsonify(formatted_response), 200
        
    except Exception as e:
        print(f" 🚨 [住掛房帳崩潰]: {e}")
        return jsonify({"code": "500", "message": str(e)}), 500

# ====================================================================
# 🦏 🚀 4. 餐廳住掛取消沖正端點 (POST /room-pay-cancel)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay-cancel', methods=['POST'])
def receive_room_pay_cancel():
    athena_id = request.headers.get('bacchus-athenaid') or request.headers.get('athena')
    hotel_cod = request.headers.get('bacchus-hotelcod') or request.headers.get('hotel')
    if not athena_id or not hotel_cod:
        return jsonify({"code": "400", "message": "Missing bacchus identification headers."}), 400

    order_nos = request.args.get('orderNos')
    if not order_nos:
        return jsonify({"code": "400", "message": "Missing query parameter 'orderNos'."}), 400

    print(f"\n🦏 [小美犀 Webhook] 📥 接收德安主動沖正 ➔ 欲取消單號: 【{order_nos}】")

    if order_nos not in mock_transaction_db:
        return jsonify({"code": "2007", "message": "查無此入帳單號，不可掛帳取消。"}), 417
        
    tx_record = mock_transaction_db[order_nos]
    if tx_record["status"] == "CANCELED":
        return jsonify({"code": "2007", "message": "此帳項已完成取消沖正。"}), 417

    room_nos = tx_record["room_nos"]
    guest_id = tx_record["guest_id"]
    refund_amount = tx_record["pay_amount"]

    account_purged = False
    if room_nos in mock_inhouse_db:
        for guest in mock_inhouse_db[room_nos]:
            if guest["guest_id"] == guest_id:
                if not guest["enabled"]:
                    return jsonify({"code": "2007", "message": "客房已結帳. 不可掛帳取消"}), 417
                guest["sum_item_total"] -= refund_amount
                account_purged = True
                break

    if not account_purged:
        return jsonify({"code": "2007", "message": "住客主檔已移出，客房已結帳. 不可掛帳取消"}), 417

    cancel_acct_nos = f"ACCT{datetime.now().strftime('%M%S')}"
    tx_record["status"] = "CANCELED"
    tx_record["cancel_acct_nos"] = cancel_acct_nos
    
    formatted_response = vendor_strategy.transform_room_pay_cancel_success_response(cancel_acct_nos)
    print(f" 🟢 [沖正成功] 紅字沖帳完畢！已將 ${refund_amount} 從房帳扣除。取消單號: 【{cancel_acct_nos}】")
    return jsonify(formatted_response), 200

# ====================================================================
# 🦏 🚀 5. 房務服務與付費備品獨立入帳端點 (POST /room-billing)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-billing', methods=['POST'])
def receive_room_billing_settlement():
    athena_id = request.headers.get('bacchus-athenaid') or request.headers.get('athena')
    hotel_cod = request.headers.get('bacchus-hotelcod') or request.headers.get('hotel')
    if not athena_id or not hotel_cod:
        return jsonify({"code": "400", "message": "Missing bacchus identification headers."}), 400
        
    if not request.is_json:
        return jsonify({"code": "415", "message": "Unsupported Media Type. JSON expected."}), 415
        
    data = request.get_json()
    
    try:
        clean_billing = vendor_strategy.parse_pms_room_billing(data)
        room_nos = clean_billing["room_nos"]
        items = clean_billing["items"]
        
        print(f"\n🦏 [小美犀 Webhook] 📥 接收德安房務備品入帳 ➔ 房號: 【{room_nos}】| 品項數: {len(items)} 筆")

        if room_nos not in mock_inhouse_db or len(mock_inhouse_db[room_nos]) == 0:
            return jsonify({"code": "1001", "message": "此房間無住客"}), 417

        guest = mock_inhouse_db[room_nos][0]
        if not guest["enabled"]:
            return jsonify({"code": "1001", "message": "此房間無住客"}), 417
            
        for item in items:
            simulated_price = 100.00 * item["quantity"]
            guest["sum_item_total"] += simulated_price
            print(f"   📦 [備品記帳成功] 編號: {item['product_nos']} | 數量: {item['quantity']} -> 記帳: ${simulated_price}")

        print(f" 🟢 [房務入帳成功] 備品鏈路整合完畢。該房累計總帳: ${guest['sum_item_total']}")
        return jsonify({}), 200
        
    except Exception as e:
        print(f" 🚨 [房務入帳崩潰]: {e}")
        return jsonify({"code": "500", "message": str(e)}), 500