# server/parking/vendors/vendor_b.py
from .base import BaseParkingVendorStrategy

class VendorBStrategy(BaseParkingVendorStrategy):
    def parse_pms_checkin(self, data):
        # 假設 B 廠商規格怪異，層級與欄位代碼完全不同
        custom_node = data.get("CustomVendorNode", {})
        return {
            "guest_id": str(custom_node.get("UID") or "").strip(),
            "car_number": str(custom_node.get("PLATE_NUM") or "").strip(),
            "guest_name": str(custom_node.get("GUEST_NAME") or "No Name").strip()
        }

    def transform_car_arrival_payload(self, local_data):
        # B 廠商要求的逆向 Payload 規格
        return {
            "pms_ci_serial": local_data["guest_id"],
            "pms_car_nos": local_data["car_number"],
            "timestamp": local_data["arrival_time"] # 不需要姓名
        }