# server/amenity/vendors/vendor_BR_AIELLO.py
from .base import BaseAmenityVendorStrategy

class VendorBRAielloStrategy(BaseAmenityVendorStrategy):
    """對齊小美犀 (BR | AIELLO) 廠商官方規格之序列化策略實作"""
    
    def transform_room_nos_query_response(self, sandbox_guest_list):
        """🎯 核心對齊：將沙盒格式洗滌並包裝成小美犀要求的 JSON Array 結構"""
        response_list = []
        
        for guest in sandbox_guest_list:
            is_enabled = guest.get("enabled", True)
            
            # 🔑 狀態門牌映射：根據沙盒狀態決定是否可住掛
            guest_status = "O" if is_enabled else "K"
            charge_info = "" if is_enabled else "櫃檯已設定禁止客房掛帳 (No Post) 或已辦理退房。"
            
            # 完美對齊官方 12 個欄位合約
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
        """🎯 實作新增：房卡查詢複用高規格洗滌機器，確保輸出格式完全一致"""
        return self.transform_room_nos_query_response(sandbox_guest_list)
    
    def parse_pms_room_pay(self, data):
        """🎯 核心實作：洗滌小美犀複雜的主明細嵌套帳務結構"""
        if not data:
            raise ValueError("Payload dictionary is empty")
            
        main_data = data.get("roomPayMain", {})
        detail_data = data.get("roomPayDetail", [])
        
        guest_id = str(main_data.get("ciSerial", "")).strip()
        room_nos = str(main_data.get("roomNos", "")).strip()
        order_nos = str(main_data.get("orderNos", "")).strip()
        pay_amount = float(main_data.get("payAmount", 0.00))
        
        # 提取明細檔洗滌（備用，供未來擴充查帳使用）
        cleaned_details = []
        for item in detail_data:
            cleaned_details.append({
                "sequence_nos": int(item.get("sequenceNos", 1)),
                "product_name": str(item.get("productName", "未知品項")),
                "quantity": int(item.get("orderQuantity", 1)),
                "special_amount": float(item.get("specialAmount", 0.00))
            })
            
        return {
            "guest_id": guest_id,
            "room_nos": room_nos,
            "order_nos": order_nos,
            "pay_amount": pay_amount,
            "details": cleaned_details
        }

    def transform_room_pay_success_response(self, acct_nos):
        """🎯 核心對齊：封裝成功 HTTP 200 回傳欄位"""
        return {
            "acctNos": str(acct_nos)
        }
    
    def transform_room_pay_cancel_success_response(self, cancel_acct_nos):
        """🎯 核心實作：還原官方成功範例大雜燴結構，防止小美犀解析噴錯"""
        return {
            "Code": "200",
            "Message": "",
            "acctNos": str(cancel_acct_nos)
        }
    
    def parse_pms_room_billing(self, data):
        """
        🎯 核心實作：洗滌小美犀房務備品專屬的平面 items 結構
        """
        if not data:
            raise ValueError("Payload dictionary is empty")
            
        room_nos = str(data.get("roomNos", "")).strip()
        items_data = data.get("items", [])
        
        cleaned_items = []
        for item in items_data:
            cleaned_items.append({
                "seq_nos": int(item.get("seqNos", 1)),
                "product_nos": str(item.get("productNos", "")).strip(),
                "quantity": int(item.get("orderQuantity", 0))
            })
            
        return {
            "room_nos": room_nos,
            "items": cleaned_items
        }