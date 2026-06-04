# server/parking/vendors/base.py

class BaseParkingVendorStrategy:
    """所有車辨廠商規格策略的抽象基底類別"""
    
    def parse_pms_checkin(self, request_data):
        """解析日常入住之 Webhook 資料體 (CKI)"""
        raise NotImplementedError
        
    def parse_pms_change_checkout(self, request_data):
        """解析修改/延長退房時間之 Webhook 資料體 (CHANGE_CKO_DATE_TIME)"""
        raise NotImplementedError
        
    def parse_pms_night_audit(self, request_data):
        """解析夜審大流量推播之真實資料體 (NIGHT_AUDIT)"""
        raise NotImplementedError
        
    def parse_pms_change_car_nos(self, request_data):
        """解析綜合櫃台車牌異動/清除/更新之資料體 (CHG_CAR_NOS)"""
        raise NotImplementedError
        
    def parse_pms_cancel(self, request_data):
        """解析取消入住之資料體 (CIX)"""
        raise NotImplementedError
        
    def transform_car_arrival_payload(self, local_guest_data, current_time):
        """將本地資料庫的標準資料，轉換為逆向打回真實 PMS 時所需的特定 Request Body"""
        raise NotImplementedError