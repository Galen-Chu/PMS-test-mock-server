# server/amenity/routes.py
from flask import Blueprint, request, jsonify, g
from datetime import datetime
import logging
import config
from .vendors.vendor_BR_AIELLO import VendorBRAielloStrategy

amenity_bp = Blueprint('amenity', __name__)
vendor_strategy = VendorBRAielloStrategy()

logger = logging.getLogger("AmenitySandbox")
logger.setLevel(logging.INFO)

# ====================================================================
# 💾 沙盒記憶體資料庫 (結構化重構：完全對齊德安 POST 帳單規格)
# ====================================================================
# 房卡與房號對應表
mock_card_mapping_db = {"1A2B3C": "11101"}

# 統一主資料庫：兼具住客檢索 (GET) 與餐廳過帳紀錄槽 (POST)
mock_inhouse_db = {}

def initialize_room_sandbox_node(room_nos: str) -> dict:
    """🎯 核心重構：在 GET 觸發時或初始化時，建立 100% 相容 POST 結構的沙盒節點"""
    return {
        # --- GET /room-nos 基礎欄位 ---
        "guestStatus": "O",
        "roomNos": room_nos,
        "roomSerial": "1",
        "altName": "Galen",
        "checkInSerial": "20250430000014",
        "orderRemark": None,
        "checkOutRemark": "",
        "sumItemTotal": 0,
        "sumAdvcTotal": 0,
        "preCreditAmount": 0,
        "groupNos": "Galen",
        "chargeInfo": "",
        
        # --- 預留儲存空間：依據 POST /room-pay Request Body 結構微整型 ---
        "roomPayMain": None,
        "roomPayDetail": [],
        
        # --- 交易生命週期狀態控制欄位 ---
        "acctNos": None,
        "transactionStatus": "INITIALIZED"  # INITIALIZED -> SETTLED -> CANCELED
    }

@amenity_bp.before_request
def verify_and_align_params():
    """外層閘道：單純處理驗證，保持下方路由純淨清晰"""
    g.third_party = request.args.get('thirdParty') or request.args.get('vendor') or 'BR'
    g.keyword = request.args.get('keyword')
    
    if config.USE_REAL_SERVER:
        auth_header = request.headers.get('Authorization') or request.headers.get('bacchus-athenaid')
        if not auth_header or (auth_header != config.CURRENT_TOKEN and auth_header != config.REAL_HEADERS_BACCHUS.get('bacchus-athenaid')):
            return jsonify({"code": "401", "message": "Unauthorized."}), 401

# ====================================================================
# 🦏 🚀 1. 房號查詢取得住客端點 (GET /room-pay/room-nos)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay/room-nos', methods=['GET'])
def query_guest_by_room_nos():
    if not g.third_party:
        return jsonify({"code": "400", "message": "Missing thirdParty parameter."}), 400

    if not g.keyword:
        return jsonify({"code": "400", "message": "Missing keyword parameter."}), 400

    room_key = str(g.keyword).strip()
    logger.info(f"📥 [沙盒流量] 房號身分拉取 ➔ 關鍵字: 【{room_key}】")

    # 🎯 規則要求：GET 方法一開始無條件初始化該房號的暫存資料結構
    mock_inhouse_db[room_key] = initialize_room_sandbox_node(room_key)

    target_data = mock_inhouse_db[room_key]
    return jsonify(vendor_strategy.transform_room_nos_query_response(target_data)), 200

# ====================================================================
# 🦏 🚀 2. 房卡卡號逆查取得住客端點 (GET /room-pay/mifare-nos)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay/mifare-nos', methods=['GET'])
def query_guest_by_mifare_nos():
    if not g.third_party:
        return jsonify({"code": "400", "message": "Missing thirdParty parameter."}), 400

    # 🎯 接收發射端傳過來的 8 碼動態大寫英數卡號
    card_key = str(g.keyword).strip() if g.keyword else "A1B2C3D4"
    
    # 如果 mock_card_mapping_db 查不到，就動態綁定到 101 房，確保測試暢行無阻
    mapped_room = mock_card_mapping_db.get(card_key, "101")
    logger.info(f"📥 [沙盒流量] 房卡卡號逆查 ➔ 動態卡號: 【{card_key}】 ➔ 動態映射房號: 【{mapped_room}】")

    # 執行初始化
    mock_inhouse_db[mapped_room] = initialize_room_sandbox_node(mapped_room)

    target_data = mock_inhouse_db[mapped_room]
    return jsonify(vendor_strategy.transform_mifare_nos_query_response(target_data)), 200

# ====================================================================
# 🦏 🚀 3. 餐廳消費住掛入帳端點 (POST /room-pay)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay', methods=['POST'])
def receive_room_pay_settlement():
    if not request.is_json:
        return jsonify({"code": "415", "message": "JSON expected."}), 415
    
    req_body = request.get_json()
    
    try:
        # 透過策略層驗證與拆解 Payload
        clean_pay = vendor_strategy.parse_pms_room_pay(req_body)
        room_nos = clean_pay['roomNos']
        order_nos = clean_pay['orderNos']
        
        logger.info(f"📥 [沙盒流量] 接收餐廳掛帳 ➔ 房號: 【{room_nos}】| 單號: 【{order_nos}】| 金額: ${clean_pay['payAmount']}")

        # 🚀 健壯性防禦：如果先前提哨沒打（例如沒跑 GET 就跑 POST），則自動補初始化
        if room_nos not in mock_inhouse_db:
            mock_inhouse_db[room_nos] = initialize_room_sandbox_node(room_nos)
            
        # 🎯 核心訴求：直接依據 POST Request Body 完整鏡像儲存至資料變數槽位
        mock_inhouse_db[room_nos]["roomPayMain"] = req_body.get("roomPayMain")
        mock_inhouse_db[room_nos]["roomPayDetail"] = req_body.get("roomPayDetail", [])
        
        # 生成入帳憑證並變更狀態
        acct_nos = f"ACCT{datetime.now().strftime('%M%S')}"
        mock_inhouse_db[room_nos]["acctNos"] = acct_nos
        mock_inhouse_db[room_nos]["transactionStatus"] = "SETTLED"
        
        return jsonify(vendor_strategy.transform_room_pay_success_response(acct_nos)), 200
    except Exception as e:
        return jsonify({"code": "500", "message": str(e)}), 500

# ====================================================================
# 🦏 🚀 4. 餐廳住掛取消沖正端點 (POST /room-pay-cancel)
# ====================================================================
@amenity_bp.route('/external/vendor-sync-data/room-pay-cancel', methods=['POST'])
def receive_room_pay_cancel():
    order_nos = request.args.get('orderNos')
    if not order_nos:
        return jsonify({"code": "400", "message": "Missing 'orderNos'."}), 400

    # 🔍 全域遍歷查找該 orderNos 歸屬的房號節點
    target_room = None
    for room_key, node in mock_inhouse_db.items():
        if node["roomPayMain"] and node["roomPayMain"].get("orderNos") == order_nos:
            target_room = room_key
            break

    if not target_room:
        return jsonify({"code": "2007", "message": "查無此入帳單號"}), 417
        
    # 變更狀態為已沖正作廢
    mock_inhouse_db[target_room]["transactionStatus"] = "CANCELED"
    cancel_acct_nos = f"CX{datetime.now().strftime('%M%S')}"
    
    return jsonify(vendor_strategy.transform_room_pay_cancel_success_response(cancel_acct_nos)), 200

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
        logger.info(f"📥 [沙盒流量] 接收備品扣款 ➔ 房號: 【{clean_billing['roomNos']}】| 品項數: {len(clean_billing['items'])} 筆")
        return jsonify({}), 200
    except Exception as e:
        return jsonify({"code": "500", "message": str(e)}), 500