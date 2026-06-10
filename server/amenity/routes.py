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

    # 🎯 核心演進：模擬德安前台主動下發/廠商定期 Pull 全量名單
    # 若德安未傳 keyword，或我們在進行端對端聯調，沙盒採取動態快取策略
    print(f"\n🦏 [小美犀 Webhook] 📥 接收德安 PMS 查詢號令 ➔ 房號關鍵字: 【{keyword_room if keyword_room else '全量同步'}】")

    # 模擬從德安資料庫撈出的最新動態數據 (此處會在階段一由腳本/真實流量觸發時進行覆寫)
    # 為了展示完整 E2E，若記憶體真空，我們預載德安 Swagger 現存的真實黃金測資
    if not mock_inhouse_db:
        print("   💾 [資料庫初始化] 偵測到暫存真空，動態 Upsert 德安實時在店白名單...")
        preset_guests = [
            {"guest_id": "20260605000001", "room_nos": "101", "room_serial": "1", "guest_name": "壹梯環境", "group_nos": "壹梯環境"},
            {"guest_id": "20260603000003", "room_nos": "102", "room_serial": "1", "guest_name": "Galen Galen_777", "group_nos": "Galen"},
            {"guest_id": "20260605044", "room_nos": "2403", "room_serial": "002", "guest_name": "林大華", "group_nos": ""}
        ]
        for g in preset_guests:
            mock_inhouse_db[g["room_nos"]] = [{
                "guest_id": g["guest_id"], "room_nos": g["room_nos"], "room_serial": g["room_serial"],
                "guest_name": g["guest_name"], "order_remark": "沙盒動態快取資產", "checkout_remark": "",
                "sum_item_total": 0.00, "sum_advc_total": 0.00, "pre_credit_amount": 0.00,
                "group_nos": g["group_nos"], "enabled": True
            }]

    # 分流回傳
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
        
        print(f"\n🦏 [小美犀 Webhook] 📥 接收房務備品入帳 ➔ 房號: 【{room_nos}】")

        if room_nos in mock_inhouse_db:
            guest = mock_inhouse_db[room_nos][0]
            for item in clean_billing["items"]:
                simulated_price = 150.00 * item["quantity"]
                guest["sum_item_total"] += simulated_price
                print(f"   📦 [備品累加成功] 料號: {item['product_nos']} ➔ 累計帳務: ${simulated_price}")
            print(f"   🟢 [財務更新完畢] 房間 {room_nos} 當前總帳餘額: ${guest['sum_item_total']}")
        return jsonify({}), 200
    except Exception as e:
        return jsonify({"code": "500", "message": str(e)}), 500