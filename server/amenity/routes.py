# server/amenity/routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import config
from .vendors.vendor_BR_AIELLO import VendorBRAielloStrategy

amenity_bp = Blueprint('amenity', __name__)
vendor_strategy = VendorBRAielloStrategy()

# 💡 進化：沙盒動態記憶體資料庫 (支援實時覆寫與動態動態繼承)
mock_inhouse_db = {}
mock_card_mapping_db = {}
mock_transaction_db = {}

# ====================================================================
# 🦏 🚀 1. 房號查詢取得住客端點 (GET /room-pay/room-nos)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay/room-nos', methods=['GET'])
def query_guest_by_room_nos():
    athena = request.headers.get('bacchus-athenaid') or request.headers.get('athena')
    hotel = request.headers.get('bacchus-hotelcod') or request.headers.get('hotel')
    if not athena or not hotel:
        return jsonify({"code": "400", "message": "Missing identification headers."}), 400
        
    third_party = request.args.get('thirdParty')
    keyword_room = request.args.get('keyword') 

    if not third_party:
        return jsonify({"code": "400", "message": "Missing thirdParty parameter."}), 400

    print(f"\n🦏 [小美犀 Webhook] 📥 接收 PMS 查詢號令 ➔ 房號關鍵字: 【{keyword_room if keyword_room else '全量同步'}】")

    # 🎯 核心設計演進：動態覆寫與測資預熱機制
    # 當腳本或真實 PMS 戳這支 GET 介面時，我們為指定房號動態建立/更新基礎暫存，確保資料流絕對對齊！
    if keyword_room:
        room_key = str(keyword_room).strip()
        
        # 💡 如果沙盒記憶體目前沒有這筆房號資產，實時執行 Upsert 覆寫，對齊業務情境！
        if room_key not in mock_inhouse_db:
            print(f"   💾 [資料流動態覆寫] 偵測到房號 【{room_key}】 首次進場，實時建立 Staging 暫存主檔...")
            
            # 依據查詢房號動態生成對齊的真實帳務外鍵 (ciSerial)
            simulated_ci_serial = f"20260610{room_key}001"
            simulated_guest_name = f"Galen 客戶情境房_{room_key}"
            
            mock_inhouse_db[room_key] = [{
                "guest_id": simulated_ci_serial,
                "room_nos": room_key,
                "room_serial": "1",
                "guest_name": simulated_guest_name,
                "order_remark": "經由 GET 流量動態快取覆寫生成",
                "checkout_remark": "",
                "sum_item_total": 0.00,  # 初始帳務欄位
                "sum_advc_total": 0.00,
                "pre_credit_amount": 0.00,
                "group_nos": "Galen_Group",
                "enabled": True          # 啟用住掛權限
            }]

    # 🧼 呼叫策略層清洗並包裝成小美犀要求格式，分流回傳
    if not keyword_room or str(keyword_room).strip() == "":
        all_guests = []
        for room_list in mock_inhouse_db.values():
            all_guests.extend(room_list)
        return jsonify(vendor_strategy.transform_room_nos_query_response(all_guests)), 200

    room_key = str(keyword_room).strip()
    if room_key in mock_inhouse_db:
        print(f"   🟢 [快取命中] 成功撈出房號 【{room_key}】 之動態暫存資產：{mock_inhouse_db[room_key][0]['guest_name']}")
        return jsonify(vendor_strategy.transform_room_nos_query_response(mock_inhouse_db[room_key])), 200
    else:
        return jsonify({"code": "1001", "message": "查無此房號"}), 417

# ====================================================================
# 🦏 🚀 3. 餐廳消費住掛入帳端點 (POST /room-pay)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay', methods=['POST'])
def receive_room_pay_settlement():
    if not request.is_json:
        return jsonify({"code": "415", "message": "JSON expected."}), 415
    data = request.get_json()
    
    try:
        clean_pay = vendor_strategy.parse_pms_room_pay(data)
        room_nos = clean_pay["room_nos"]
        pay_amount = clean_pay["pay_amount"]
        order_nos = clean_pay["order_nos"]
        
        print(f"\n🦏 [小美犀 Webhook] 📥 接收入帳請求 ➔ 房號: 【{room_nos}】| 金額: ${pay_amount}")

        # 🎯 核心演進：動態覆寫與帳務狀態更新
        if room_nos in mock_inhouse_db:
            guest = mock_inhouse_db[room_nos][0]
            guest["sum_item_total"] += pay_amount # 實時更新沙盒內部財務欄位
            print(f"   ⚙️  [帳務狀態異動] 房號 {room_nos} 總帳更新為: ${guest['sum_item_total']}")
        else:
            # 房號不存在時，沙盒展現極高防禦力，動態建立影子賬單，確保端到端不崩潰
            mock_inhouse_db[room_nos] = [{
                "guest_id": clean_pay["guest_id"], "room_nos": room_nos, "room_serial": "1",
                "guest_name": "動態生成影子住客", "order_remark": "", "checkout_remark": "",
                "sum_item_total": pay_amount, "sum_advc_total": 0.00, "pre_credit_amount": 0.00,
                "group_nos": "", "enabled": True
            }]

        acct_nos = f"ACCT{datetime.now().strftime('%M%S')}"
        mock_transaction_db[order_nos] = {
            "acct_nos": acct_nos, "guest_id": clean_pay["guest_id"], "room_nos": room_nos,
            "pay_amount": pay_amount, "status": "SETTLED"
        }
        return jsonify(vendor_strategy.transform_room_pay_success_response(acct_nos)), 200
    except Exception as e:
        return jsonify({"code": "500", "message": str(e)}), 500

# ====================================================================
# 🦏 🚀 5. 房務服務與付費備品獨立入帳端點 (POST /room-billing)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-billing', methods=['POST'])
def receive_room_billing_settlement():
    if not request.is_json:
        return jsonify({"code": "415", "message": "JSON expected."}), 415
    data = request.get_json()
    
    try:
        clean_billing = vendor_strategy.parse_pms_room_billing(data)
        room_nos = clean_billing["room_nos"]
        items = clean_billing["items"]
        
        print(f"\n🦏 [小美犀 Webhook] 📥 接收房務備品入帳 ➔ 房號: 【{room_nos}】")

        # 🎯 核心防禦與資料流繼承檢驗
        # 如果前面的 GET 階段一有成功覆寫，此處的 room_nos 必然 100% 存在於記憶體中！
        if room_nos not in mock_inhouse_db:
            print(f" 🔴 [財務防禦攔截] 沙盒記憶體查無房號 【{room_nos}】 的暫存主檔，發動 417 阻斷壞帳。")
            return jsonify({"code": "1001", "message": "此房間無住客"}), 417

        # 🧠 實時作業欄位更新至帳務相關欄位
        guest = mock_inhouse_db[room_nos][0]
        for item in items:
            # 模擬付費備品單價，執行記帳更新
            simulated_price = 150.00 * item["quantity"]
            guest["sum_item_total"] += simulated_price
            print(f"   📦 [帳務更新] 備品品項: {item['product_nos']} * {item['quantity']} ➔ 沙盒 Folio 總帳更新為: ${guest['sum_item_total']}")

        print(f" 🟢 [情境演練成功] 房號 【{room_nos}】 財務資料異動完成。即將原封不動準備後續 POST 給德安 PMS。")
        return jsonify({}), 200
    except Exception as e:
        return jsonify({"code": "500", "message": str(e)}), 500