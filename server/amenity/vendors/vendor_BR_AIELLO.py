# server/amenity/vendors/vendor_BR_AIELLO.py
from .base import BaseAmenityVendorStrategy

class VendorBRAielloStrategy(BaseAmenityVendorStrategy):
    """對齊小美犀 (BR | AIELLO) 廠商官方規格之序列化策略實作"""
    
    def transform_room_nos_query_response(self, sandbox_guest_list):
        response_list = []
        for guest in sandbox_guest_list:
            is_enabled = guest.get("enabled", True)
            guest_status = "O" if is_enabled else "K"
            charge_info = "" if is_enabled else "櫃檯已設定禁止客房掛帳 (No Post)。"
            
            vendor_node = {
                "guestStatus": guest_status,
                "roomNos": str(guest.get("room_nos", "")),
                "roomSerial": str(guest.get("room_serial", "001")),
                "altName": str(guest.get("guest_name", "匿名客")),
                "checkInSerial": str(guest.get("guest_id", "")),
                "orderRemark": str(guest.get("order_remark", "")),
                "checkOutRemark": str(guest.get("checkout_remark", "")),
                "sumItemTotal": float(guest.get("sum_item_total", 0.00)),
                "sumAdvcTotal": float(guest.get("sum_advc_total", 0.00)),
                "preCreditAmount": float(guest.get("pre_credit_amount", 0.00)),
                "groupNos": str(guest.get("group_nos", "")),
                "chargeInfo": charge_info
            }
            response_list.append(vendor_node)
        return response_list

    def transform_mifare_nos_query_response(self, sandbox_guest_list):
        return self.transform_room_nos_query_response(sandbox_guest_list)

    def parse_pms_room_pay(self, data):
        """🎯 核心升級：精準扒皮德安 Main 結構，支援任何動態房號資料提取"""
        if not data or "roomPayMain" not in data:
            raise ValueError("Invalid roomPay JSON structure")
            
        main_part = data["roomPayMain"]
        return {
            "guest_id": str(main_part.get("ciSerial", "")).strip(),
            "room_nos": str(main_part.get("roomNos", "")).strip(),
            "order_nos": str(main_part.get("orderNos", "")).strip(),
            "pay_amount": float(main_part.get("payAmount", 0.00)),
            "details": data.get("roomPayDetail", [])
        }

    def transform_room_pay_success_response(self, acct_nos):
        return {"acctNos": str(acct_nos)}
    
    def transform_room_pay_cancel_success_response(self, cancel_acct_nos):
        return {"Code": "200", "Message": "", "acctNos": str(cancel_acct_nos)}
    
    def parse_pms_room_billing(self, data):
        if not data:
            raise ValueError("Payload dictionary is empty")
        return {
            "room_nos": str(data.get("roomNos", "")).strip(),
            "items": data.get("items", [])
        }