# server/parking/vendors/vendor_a.py
from .base import BaseParkingVendorStrategy
from datetime import datetime

class VendorAStrategy(BaseParkingVendorStrategy):
    def parse_pms_checkin(self, data):
        # A 廠商的欄位解析邏輯
        sync_data = data.get("parkingSyncData", {})
        return {
            "guest_id": str(data.get("guest_id") or sync_data.get("ciSer") or "").strip(),
            "car_number": str(data.get("car_number") or sync_data.get("carNos") or "").strip(),
            "guest_name": str(data.get("guest_name") or sync_data.get("altName") or "未帶姓名").strip()
        }

    def transform_car_arrival_payload(self, local_data):
        # A 廠商逆向打回 PMS 的 4 欄位合約
        return {
            "guest_id": local_data["guest_id"],
            "car_number": local_data["car_number"],
            "guest_name": local_data["guest_name"],
            "arrival_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }