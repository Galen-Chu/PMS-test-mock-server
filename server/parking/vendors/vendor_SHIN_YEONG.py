# server/parking/vendors/vendor_shin_yeong.py
from .base import BaseParkingVendorStrategy

class VendorShinYeongStrategy(BaseParkingVendorStrategy):
    """現行對齊德安官方 4 欄位規格之 ShinYeong 廠商策略"""
    
    def parse_pms_checkin(self, data):
        # 💡 洗滌與對齊欄位名稱（無論是真實雲端嵌套結構還是本地 Pytest 傳入）
        sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
        
        # 處理 Swagger 修改車牌時的 List 嵌套結構防禦
        if "parkingSyncDataList" in data and len(data["parkingSyncDataList"]) > 0:
            sync_data = data["parkingSyncDataList"][0]
            
        guest_id = str(data.get("guest_id") or sync_data.get("ciSerial") or sync_data.get("ciSer") or "").strip()
        car_number = str(data.get("car_number") or sync_data.get("carNos") or "QA-8888").strip()
        guest_name = str(data.get("guest_name") or sync_data.get("altName") or "未帶姓名").strip()
        
        return {
            "guest_id": guest_id,
            "car_number": car_number,
            "guest_name": guest_name
        }

    def transform_car_arrival_payload(self, local_guest_data, current_time):
        # 🎯 逆向通信：組裝絕對符合官方 SA 規格的 4 欄位 Request Body
        return {
            "guest_id": local_guest_data["guest_id"],
            "car_number": local_guest_data["car_number"],
            "guest_name": local_guest_data["guest_name"],
            "arrival_time": current_time
        }