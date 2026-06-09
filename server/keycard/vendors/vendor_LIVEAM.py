# server/keycard/vendors/vendor_LIVEAM.py
import datetime
import secrets

class VendorLiveamStrategy:
    """華豫寧 (LIVEAM) 門禁系統之認證與狀態機策略實作"""
    
    def __init__(self):
        # 💡 Staging 環境預設合法鑑權資產
        self.valid_id = "athena_pms"
        self.valid_password = "liveam_password_123"
        self.valid_project_id = "PRJ-01"

    def authenticate_login(self, body_data):
        """🎯 核心對齊：校驗德安傳入的登入欄位，並產出高真回應結構"""
        if not body_data:
            return {"error": 1, "desc": "Empty Payload", "msg": "未傳送登入參數"}, 400
            
        req_id = body_data.get("id")
        req_password = body_data.get("password")
        req_project_id = body_data.get("projectID")
        
        # 👮‍♂️ 鑑權防禦：可根據實測彈性放寬或嚴格比對
        if req_id == self.valid_id and req_password == self.valid_password:
            # 簽發一組高真的門禁 Session Token
            simulated_token = f"LIVEAM-STAGING-TOKEN-{secrets.token_hex(12).upper()}"
            
            # 完美對齊 200 OK 成功合約
            success_payload = {
                "id": str(req_id),
                "token": simulated_token
            }
            return success_payload, 200
        else:
            # 完美對齊 400 Bad Request 失敗合約
            error_payload = {
                "error": 4001,
                "desc": "Authentication Failed",
                "msg": "帳號、密碼或專案代碼(projectID)不符合華豫寧系統設定"
            }
            return error_payload, 400
    
    def clean_order_payload(self, body_data):
        """🎯 核心實作：洗滌並標準化德安傳入的門禁訂單模型"""
        if not body_data:
            return None
            
        return {
            "id": str(body_data.get("id", "")).strip(),
            "reserveID": int(body_data.get("reserveID", 0)),
            "batchID": str(body_data.get("batchID", "")),
            "guestName": str(body_data.get("guestName", "未命名住客")),
            "passport": str(body_data.get("passport", "")),
            "mailTo": str(body_data.get("mailTo", "")),
            "mobile": str(body_data.get("mobile", "")),
            "roomID": int(body_data.get("roomID", 0)), # 💡 實體對應房號
            "preInTime": body_data.get("preInTime"),
            "preOutTime": body_data.get("preOutTime"),
            "checkinTime": body_data.get("checkinTime"),
            "checkoutTime": body_data.get("checkoutTime"),
            "canAppCheckin": bool(body_data.get("canAppCheckin", True)),
            "status": int(body_data.get("status", 0))
        }
    
    def transform_card_info_response(self, card_node, room_id):
        """
        🎯 核心對齊：封裝高真的華豫寧卡片逆查成功回應
        """
        return {
            "orderID": str(card_node.get("orderID", "")),
            "cardUid": str(card_node.get("cardUid", "")),
            "type": str(card_node.get("type", "card")),
            "roomID": int(room_id), # 💡 動態反查注入的實體房號
            "queryTimestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }