# server/amenity/vendors/vendor_BR_AIELLO.py
from .base import BaseAmenityVendorStrategy

class VendorBRAielloStrategy(BaseAmenityVendorStrategy):
    """
    小美犀策略層：全面仿照德安官方 API 規格。
    實現單一情境（即用即拋）的傳輸資料處理，取消無謂的欄位轉換。
    """
    
    def transform_room_nos_query_response(self, sandbox_guest_dict):
        """🎯 單筆應對單筆：直接收取仿照 API 規格的內部 Dict，包裝 resultCode 外殼吐回"""
        guest = sandbox_guest_dict if isinstance(sandbox_guest_dict, dict) else {}
        if not guest:
            return {"resultCode": "0000", "data": []}
            
        # 💡 本質歸位：欄位名稱 100% 仿照德安標準 Response 規格
        vendor_node = {
            "guestStatus": str(guest.get("guestStatus", "O")),
            "roomNos": str(guest.get("roomNos", "")),
            "roomSerial": str(guest.get("roomSerial", "1")),
            "altName": str(guest.get("altName", "匿名客")),
            "checkInSerial": str(guest.get("checkInSerial", "20260605000001")),
            "orderRemark": guest.get("orderRemark"),
            "checkOutRemark": str(guest.get("checkOutRemark", "")),
            "sumItemTotal": int(guest.get("sumItemTotal", 0)),
            "sumAdvcTotal": int(guest.get("sumAdvcTotal", 0)),
            "preCreditAmount": int(guest.get("preCreditAmount", 0)),
            "groupNos": str(guest.get("groupNos", "")),
            "chargeInfo": str(guest.get("chargeInfo", ""))
        }
        return {
            "resultCode": "0000",
            "data": [vendor_node]
        }

    def transform_mifare_nos_query_response(self, sandbox_guest_dict):
        return self.transform_room_nos_query_response(sandbox_guest_dict)

    def parse_pms_room_pay(self, data):
        """🎯 餐廳落帳：精準扒皮最新補足的標準 roomPayMain 規格"""
        if not data or "roomPayMain" not in data:
            raise ValueError("Invalid roomPay JSON structure")
            
        main_part = data["roomPayMain"]
        return {
            "ciSerial": str(main_part.get("ciSerial", "")).strip(),
            "roomNos": str(main_part.get("roomNos", "")).strip(),
            "orderNos": str(main_part.get("orderNos", "")).strip(),
            "payAmount": float(main_part.get("payAmount", 0.00)),
            "details": data.get("roomPayDetail", [])
        }

    def transform_room_pay_success_response(self, acct_nos):
        return {"acctNos": str(acct_nos)}
    
    def transform_room_pay_cancel_success_response(self, cancel_acct_nos):
        return {"Code": "200", "Message": "", "acctNos": str(cancel_acct_nos)}
    
    def parse_pms_room_billing(self, data):
        """🎯 備品落帳：精準扒皮最新補足的標準 room-billing 規格"""
        if not data or "roomNos" not in data:
            raise ValueError("Invalid roomBilling JSON structure")
        return {
            "roomNos": str(data.get("roomNos", "")).strip(),
            "items": data.get("items", [])
        }