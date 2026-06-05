# server/amenity/vendors/base.py

class BaseAmenityVendorStrategy:
    """所有語音音箱/房務備品廠商規格策略的抽象基底類別"""
    
    def transform_room_nos_query_response(self, sandbox_guest_list):
        """將沙盒內部的標準在店住客資料，轉換為該廠商規格要求的成功 Response 格式 (如轉為 Array 結構)"""
        raise NotImplementedError
    
    def transform_mifare_nos_query_response(self, sandbox_guest_list):
        """將卡號查詢結果轉換為小美犀要求的 JSON Array 結構"""
        raise NotImplementedError
    
    def parse_pms_room_pay(self, request_data):
        """解析住掛房帳 Request Body 傳入的住掛帳務主明細結構，洗滌出標準主檔與明細資料"""
        raise NotImplementedError

    def transform_room_pay_success_response(self, acct_nos):
        """封裝符合小美犀合約的成功入帳單號結構回執 Response"""
        raise NotImplementedError
    
    def transform_room_pay_cancel_success_response(self, cancel_acct_nos):
        """封裝符合小美犀合約的大寫 Code/Message 與紅字沖正取消單號結構"""
        raise NotImplementedError
    
    def parse_pms_room_billing(self, request_data):
        """解析房務備品入帳平面結構 Request Body ，洗滌出房號與品項清單"""
        raise NotImplementedError