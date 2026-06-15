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
            return {
                "roomer": {
                    "rentId": target_roomer["rentId"],
                    "roomNumber": target_roomer["roomNumber"],
                    "createTime": target_roomer["createTime"],
                    "startTime": target_roomer["startTime"],
                    "endTime": target_roomer["endTime"],
                    "licensePlateList": target_roomer["licensePlateList"],
                    "isRenting": target_roomer["isRenting"]
                }
            }, 200
        else:
            # 💡 動態就地合法防禦
            virtual_rent_id = f"v-rent-{str(uuid.uuid4())[:8]}"
            self.mock_roomer_db[virtual_rent_id] = {
                "rentId": virtual_rent_id, "roomNumber": "101", "createTime": "2026-06-15T00:00:00",
                "startTime": "2026-06-15T00:00:00", "endTime": "2026-06-16T15:00:00",
                "licensePlateList": [search_plate], "isRenting": False
            }
            return {
                "roomer": {
                    "rentId": virtual_rent_id, "roomNumber": "101", "createTime": "2026-06-15T00:00:00",
                    "startTime": "2026-06-15T00:00:00", "endTime": "2026-06-16T15:00:00",
                    "licensePlateList": [search_plate], "isRenting": False
                }
            }, 200

    def update_roomer(self, body_data):
        """🔄 處理更新/取消入住銷帳"""
        roomer_data = body_data.get("Roomer", {})
        rent_id = str(roomer_data.get("RentId", "")).strip()
        
        if rent_id not in self.mock_roomer_db:
            return {"resultCode": "4045", "message": "RentId not found"}, 200
            
        target_info = self.mock_roomer_db[rent_id]
        new_plates = roomer_data.get("LicensePlateList", [])
        
        target_info["roomNumber"] = roomer_data.get("RoomNumber", target_info["roomNumber"])
        target_info["startTime"] = roomer_data.get("StartTime", target_info["startTime"])
        target_info["endTime"] = roomer_data.get("EndTime", target_info["endTime"])
        target_info["licensePlateList"] = [str(p).strip().upper() for p in new_plates]
        
        if len(new_plates) == 0:
            target_info["isRenting"] = False
            
        return {"resultCode": "0000", "message": "Success"}, 200