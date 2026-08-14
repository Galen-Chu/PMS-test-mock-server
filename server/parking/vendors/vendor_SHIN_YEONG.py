# server/parking/vendors/vendor_SHIN_YEONG.py
from .base import BaseParkingVendorStrategy
from datetime import datetime, timedelta

class VendorShinYeongStrategy(BaseParkingVendorStrategy):
    """對齊 ShinYeong 廠商官方規格之序列化策略實作"""
    
    def _normalize_datetime(self, dt_str):
        """私有輔助函數：將 PMS 各式時間格式統一轉換為標準 YYYY-MM-DD HH:MM:SS"""
        if not dt_str:
            return None
        dt_str = str(dt_str).strip()
        try:
            # 優先嘗試解析 ngrok 抓到的斜線格式 "2026/06/04 15:00" 或 "2026/06/04 15:00:00"
            if "/" in dt_str:
                if len(dt_str.split(":")) == 2: # 缺少秒數
                    return datetime.strptime(dt_str, "%Y/%m/%d %H:%M").strftime("%Y-%m-%d %H:%M:%S")
                return datetime.strptime(dt_str, "%Y/%m/%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
            # 嘗試解析橫線格式 "2026-06-04 15:00:00"
            elif "-" in dt_str:
                if len(dt_str.split(":")) == 2:
                    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M:%S")
                return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        return dt_str # 若解析失敗則原樣保留，不做破壞性變更
    
    def parse_pms_checkin(self, data):
        """🎯 專職日常入住 (CKI)：初始化完整住客主檔"""
        sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
        if "parkingSyncDataList" in data and len(data["parkingSyncDataList"]) > 0:
            sync_data = data["parkingSyncDataList"][0]
            
        guest_id = str(data.get("guest_id") or sync_data.get("ciSerial") or sync_data.get("ciSer") or "").strip()
        car_number = str(data.get("car_number") or sync_data.get("carNos") or "").strip()
        guest_name = str(data.get("guest_name") or sync_data.get("altName") or "未帶姓名").strip()
        
        start_date = data.get("start_date") or sync_data.get("ciDat") or sync_data.get("ciDate")
        end_date = data.get("end_date") or sync_data.get("coDat") or sync_data.get("coDate")

        # 💡 SA v1.2:欄位為 is_enabled("Yes"/"No");舊 key "enabled"(True/"Yes"/"Y")保留相容
        pms_enabled = sync_data.get("is_enabled", sync_data.get("enabled", True))
        is_enabled = True if pms_enabled in [True, "Yes", "Y"] else False

        return {
            "guest_id": guest_id,
            "car_number": car_number,
            "guest_name": guest_name,
            "start_date": self._normalize_datetime(start_date),
            "end_date": self._normalize_datetime(end_date),
            "enabled": is_enabled
        }

    def parse_pms_change_checkout(self, data):
        """🎯 專職延長/修改退房 (CHANGE_CKO_DATE_TIME)：專注於退房時間異動"""
        sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
        if "parkingSyncDataList" in data and len(data["parkingSyncDataList"]) > 0:
            sync_data = data["parkingSyncDataList"][0]
            
        guest_id = str(data.get("guest_id") or sync_data.get("ciSerial") or sync_data.get("ciSer") or "").strip()
        
        # 延長退房最核心關心的就是新退房日期 (coDat)
        end_date = data.get("end_date") or sync_data.get("coDat") or sync_data.get("coDate")
        
        # 備用提取，若有傳送則一併更新
        car_number = str(data.get("car_number") or sync_data.get("carNos") or "").strip()
        # 💡 SA v1.2:is_enabled("Yes"/"No");舊 key "enabled" 保留相容
        pms_enabled = sync_data.get("is_enabled", sync_data.get("enabled", True))
        is_enabled = True if pms_enabled in [True, "Yes", "Y"] else False
        
        return {
            "guest_id": guest_id,
            "car_number": car_number,
            "end_date": self._normalize_datetime(end_date),
            "enabled": is_enabled
        }

    def parse_pms_change_car_nos(self, data):
        """🎯 實作微調：精準捕捉櫃檯車牌三態 (新增/清除/更新) 傳送過來的車牌與啟用狀態"""
        guest_id = data.get("guest_id")
        car_number = data.get("car_number")
        # 💡 SA v1.2:flat payload 亦帶 is_enabled("Yes"/"No");舊版 flat 分支未讀狀態(恆為啟用)已修正。
        # 舊 key "enabled" 保留相容。
        pms_enabled = data.get("is_enabled", data.get("enabled", True))

        if "parkingSyncDataList" in data and len(data["parkingSyncDataList"]) > 0:
            nested_data = data["parkingSyncDataList"][0]
            guest_id = nested_data.get("ciSer") or nested_data.get("ciSerial")
            car_number = nested_data.get("carNos")
            pms_enabled = nested_data.get("is_enabled", nested_data.get("enabled", True))

        guest_id = str(guest_id or "").strip()
        car_number = str(car_number or "").strip()

        # 🔑 三態分流核心：將德安傳過來的狀態（包含 Y/N, Yes/No, True/False）對齊
        is_enabled = True if pms_enabled in [True, "Yes", "Y"] else False
        
        return {
            "guest_id": guest_id,
            "car_number": car_number,
            "enabled": is_enabled
        }

    def parse_pms_cancel_checkin(self, data):
        """🎯 實戰修正：取消入住 CIX。德安系統依然會回傳車號以供廠商處理「停車離廠」，因此必須精準提取車牌，絕不留空！"""
        sync_data = data.get("parkingSyncData", {}) if "parkingSyncData" in data else data
        if "parkingSyncDataList" in data and len(data["parkingSyncDataList"]) > 0:
            sync_data = data["parkingSyncDataList"][0]
            
        guest_id = str(data.get("guest_id") or sync_data.get("ciSer") or "").strip()

        # 🎯 核心補齊：精準撈取取消入住時，PMS 同步送過來的原車牌
        car_number = str(data.get("car_number") or sync_data.get("carNos") or "").strip()

        # 💡 SA v1.2:is_enabled("Yes"/"No");舊 key "enabled" 保留相容
        pms_enabled = sync_data.get("is_enabled", sync_data.get("enabled", True))
        is_enabled = True if pms_enabled in [True, "Yes", "Y"] else False

        # 💡 SA v1.2 範例 5:取消入住的結束時間由德安 PMS 計算後傳入(當日最晚離場時間)，
        # 廠商應採用傳入值。未帶時才以「取消入住離場緩衝分鐘數」自行補算(舊行為降級為 fallback)。
        end_date = data.get("end_date") or sync_data.get("coDat") or sync_data.get("coDate")
        if end_date:
            final_end_date = self._normalize_datetime(end_date)
        else:
            import config
            buffer_mins = getattr(config, 'CIX_BUFFER_MINUTES', 30)
            final_end_date = (datetime.now() + timedelta(minutes=buffer_mins)).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "guest_id": guest_id,
            "car_number": car_number,  # 守住車牌！
            "end_date": final_end_date,
            "enabled": is_enabled
        }

    def parse_pms_night_audit(self, data):
        """🎯 適配真實夜審 166 bytes 封包大流量 (NIGHT_AUDIT)"""
        guest_id = str(data.get("guest_id") or "").strip()
        car_number = str(data.get("car_number") or "").strip()
        guest_name = str(data.get("guest_name") or "未帶姓名").strip()
        start_date = str(data.get("start_date") or "").strip()
        end_date = str(data.get("end_date") or "").strip()
        
        # 💡 is_enabled 為 SA v1.2 欄位;舊 key "enabled" 保留相容
        pms_enabled = data.get("is_enabled", data.get("enabled", "Yes"))
        is_enabled = True if pms_enabled in ["Yes", "Y", True] else False
        
        return {
            "guest_id": guest_id,
            "car_number": car_number,
            "guest_name": guest_name,
            "start_date": start_date,
            "end_date": end_date,
            "enabled": is_enabled
        }

    def transform_car_arrival_payload(self, local_guest_data, current_time):
        return {
            "guest_id": local_guest_data["guest_id"],
            "car_number": local_guest_data["car_number"],
            "guest_name": local_guest_data["guest_name"],
            "arrival_time": current_time
        }