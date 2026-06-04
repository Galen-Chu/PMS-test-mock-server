# server/parking/vendors/base.py

class BaseParkingVendorStrategy:
    """所有車辨廠商規格策略的抽象基底類別"""
    
    def parse_pms_checkin(self, request_data):
        """解析並洗滌 PMS 打過來的 Check-in 資料，統一回傳標準內部格式"""
        raise NotImplementedError
        
    def transform_car_arrival_payload(self, local_guest_data):
        """將本地資料庫的格式，轉換為該廠商逆向打回真實 PMS 時所需的特定 Request Body"""
        raise NotImplementedError