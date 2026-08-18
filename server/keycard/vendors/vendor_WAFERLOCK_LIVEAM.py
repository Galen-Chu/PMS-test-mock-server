# server/keycard/vendors/vendor_WAFERLOCK_LIVEAM.py
import datetime
import secrets

class VendorWaferlockLiveamStrategy:
    """維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM) (WAFERLOCK / LIVEAM) 門禁系統之認證與狀態機策略實作"""
    
    def __init__(self):
        # 💡 Staging 環境預設合法鑑權資產
        self.valid_id = "athena_pms"
        self.valid_password = "liveam_password_123"
        self.valid_project_id = "PRJ-01"
        # 🌟 最新補足：德安 PMS 串接設定所需之 10 碼純數字製卡機機型代號
        self.doorcard_machine = "0000000101"

    def authenticate_login(self, body_data):
        """🎯 對齊 Swagger LoginPara/TokenInfo:校驗 {id, password, projectID},回 {id, token}。

        💡 projectID 依 Swagger 為必填;沙盒採寬鬆策略(帳密對即可,projectID 僅要求非空)。
        """
        if not body_data:
            return {"error": 1, "desc": "Empty Payload", "msg": "未傳送登入參數"}, 400

        req_id = body_data.get("id")
        req_password = body_data.get("password")
        req_project = body_data.get("projectID")

        # 👮‍♂️ 鑑權防禦(Swagger LoginPara:projectID 必填)
        if not req_project:
            return {"error": 1, "desc": "projectID is required", "msg": "projectID 為必填"}, 400
        if req_id == self.valid_id and req_password == self.valid_password:
            # 簽發一組高真的門禁 Session Token
            simulated_token = f"LIVEAM-STAGING-TOKEN-{secrets.token_hex(12).upper()}"

            # TokenInfo(Swagger):{id, token};encoderCode 為沙盒附加(供 PMS 設定製卡機)
            success_payload = {
                "id": str(req_id),
                "token": simulated_token,
                "encoderCode": self.doorcard_machine
            }
            return success_payload, 200
        else:
            return {
                "error": 4001,
                "desc": "Authentication Failed",
                "msg": "帳號或密碼不符合維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)系統設定"
            }, 400
    
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
        """🎯 對齊 Swagger CardPermission:getCardInfo 成功回應。

        {errorCode:int(0=成功), description, cardUid, type:int, name, activation, expiration, deviceList}
        💡 cardUid 由本端點生成(模擬讀卡機感應實體卡)——真實流程:先 getCardInfo 拿卡號,再 OrderCard 綁定。
        """
        now = datetime.datetime.now()
        return {
            "errorCode": 0,
            "description": "Success",
            "cardUid": str(card_node.get("cardUid", "")),
            "type": int(card_node.get("type", 1)),  # 💡 Swagger type 為 integer(類型代碼,1=卡片,值待與廠商確認)
            "name": str(card_node.get("name", "")),
            "activation": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "expiration": (now + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            "deviceList": card_node.get("deviceList", []),
        }