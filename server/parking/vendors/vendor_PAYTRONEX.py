# server/parking/vendors/vendor_PAYTRONEX.py
import uuid
import datetime

class VendorPaytronexStrategy:
    def __init__(self):
        # 🗃️ 博辰車辨 (PAYTRONEX) 專屬記憶體資料庫
        self.mock_roomer_db = {
            "9bd34535-8e3b-4d31-9823-faf0f3ad83c9": {
                "rentId": "9bd34535-8e3b-4d31-9823-faf0f3ad83c9",
                "roomNumber": "101",
                "createTime": "2026-06-15T13:00:00",
                "startTime": "2026-06-15T00:00:00",
                "endTime": "2026-06-16T15:00:00",
                "licensePlateList": ["ABC123", "BCD241"],
                "isRenting": True
            }
        }

    def add_roomer(self, body_data):
        """🚗 處理新增房客預約資料"""
        roomer_data = body_data.get("Roomer", {})
        room_number = str(roomer_data.get("RoomNumber", "")).strip()
        
        if not room_number:
            return {"message": "RoomNumber is required"}, 400
            
        generated_rent_id = str(uuid.uuid4())
        self.mock_roomer_db[generated_rent_id] = {
            "rentId": generated_rent_id,
            "roomNumber": room_number,
            "createTime": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "startTime": roomer_data.get("StartTime"),
            "endTime": roomer_data.get("EndTime"),
            "licensePlateList": [str(p).strip().upper() for p in roomer_data.get("LicensePlateList", [])],
            "isRenting": True
        }
        return {"resultCode": "0000", "message": "Success", "rentId": generated_rent_id}, 200

    def find_by_license_plate(self, body_data):
        """🔍 依車牌查詢租約 (支援 CIX 逆查動態就地合法)"""
        search_plate = str(body_data.get("LicensePlate", "")).strip().upper()
        
        target_roomer = None
        for r_id, r_info in self.mock_roomer_db.items():
            if search_plate in r_info.get("licensePlateList", []):
                target_roomer = r_info
                break
                
        if target_roomer:
            # 🎯 防禦機制：萬一記憶體內有髒資料是斜線，在吐給 PMS 前強制洗成博辰要的橫線 T 格式
            st = str(target_roomer["startTime"]).replace("/", "-").replace(" ", "T") if "T" not in str(target_roomer["startTime"]) else target_roomer["startTime"]
            et = str(target_roomer["endTime"]).replace("/", "-").replace(" ", "T") if "T" not in str(target_roomer["endTime"]) else target_roomer["endTime"]
            
            return {
                "roomer": {
                    "rentId": target_roomer["rentId"],
                    "roomNumber": target_roomer["roomNumber"],
                    "createTime": target_roomer["createTime"],
                    "startTime": st,
                    "endTime": et,
                    "licensePlateList": target_roomer["licensePlateList"],
                    "isRenting": target_roomer["isRenting"]
                }
            }, 200
        else:
            # 💡 物理破局核心：動態就地合法防禦，時間格式必須 100% 對齊 ISO 8601 (帶 T 的橫線格式)
            virtual_rent_id = f"v-rent-{str(uuid.uuid4())[:8]}"
            
            # 🎯 改為符合博辰 Java 解析器的格式
            valid_start = "2025-05-19T00:00:00"
            valid_end = "2026-06-19T15:00:00"
            
            self.mock_roomer_db[virtual_rent_id] = {
                "rentId": virtual_rent_id, 
                "roomNumber": "101", 
                "createTime": "2026-06-15T00:00:00",
                "startTime": valid_start, 
                "endTime": valid_end,
                "licensePlateList": [search_plate], 
                "isRenting": True
            }
            return {
                "roomer": {
                    "rentId": virtual_rent_id, 
                    "roomNumber": "101", 
                    "createTime": "2026-06-15T00:00:00",
                    "startTime": valid_start, 
                    "endTime": valid_end,
                    "licensePlateList": [search_plate], 
                    "isRenting": True
                }
            }, 200

    def update_roomer(self, body_data):
        """🔄 處理更新/取消入住銷帳 (大一統三態感知版)"""
        roomer_data = body_data.get("Roomer", {})
        rent_id = str(roomer_data.get("RentId", "")).strip()
        
        if rent_id not in self.mock_roomer_db:
            print(f"🚨 [博辰 Strategy 異常] 找不到對應的 RentId: {rent_id}")
            return {"resultCode": "4045", "message": "RentId not found"}, 200
            
        target_info = self.mock_roomer_db[rent_id]
        
        # 1. 擷取 PMS 傳過來的最新欄位
        new_plates = [str(p).strip().upper() for p in roomer_data.get("LicensePlateList", [])]
        new_end_time = roomer_data.get("EndTime")
        new_room_number = roomer_data.get("RoomNumber")
        
        old_plates = target_info.get("licensePlateList", [])
        old_end_time = target_info.get("endTime", "")

        # ====================================================================
        # 🎯 核心業務判斷：精準切分三種可能性
        # ====================================================================
        
        # 可能性一：綜合櫃台【清除車號】 (PMS 傳送空陣列)
        if len(new_plates) == 0 and len(old_plates) > 0:
            print(f"🗑️  [博辰變更感知] 【情境一：清除車號】")
            print(f"   👤 房號: {target_info['roomNumber']} | 移除舊車牌: {old_plates} ➔ 變更為: 【空值】")
            target_info["isRenting"] = False  # 依規格書，清空車號即代表停用或註銷此段租約

        # 可能性二：綜合櫃台【變更車號】 (PMS 傳入新車牌，且與舊車牌不一致)
        elif len(new_plates) > 0 and set(new_plates) != set(old_plates):
            print(f"🔄 [博辰變更感知] 【情境二：修改車號】")
            print(f"   👤 房號: {target_info['roomNumber']} | 車牌軌跡變更: {old_plates} ➔ 替換為: {new_plates}")
            target_info["isRenting"] = True  # 確保車牌仍處於啟用狀態

        # 可能性三：【修改退房日期】 (車牌沒變，但退房時間異動了)
        elif new_end_time and new_end_time != old_end_time:
            print(f"⏳ [博辰變更感知] 【情境三：延長/縮短退房時間】")
            print(f"   👤 房號: {target_info['roomNumber']} | 時間異動: {old_end_time} ➔ 新截止線: {new_end_time}")

        # 其他：單純換房或無異動同步
        else:
            print(f"ℹ️  [博辰變更感知] 收到常態性資料同步 (房號: {new_room_number} | 車牌: {new_plates})")

        # ====================================================================
        # 💾 實體落庫與記憶體置換
        # ====================================================================
        if new_room_number:
            target_info["roomNumber"] = new_room_number
        if roomer_data.get("StartTime"):
            target_info["startTime"] = roomer_data.get("StartTime")
        if new_end_time:
            target_info["endTime"] = new_end_time
            
        # 🚀 確實將新車牌覆寫進去，完成同一住客的 Payload 置換
        target_info["licensePlateList"] = new_plates
        
        return {"resultCode": "0000", "message": "Success"}, 200