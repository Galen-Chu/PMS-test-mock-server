# config.py 升級版：全新結構化與模組化配置，支持多廠商多模組的靈活切換與擴展

# ====================================================================
# ⚠️ 戰略總開關：切换為 True 即實打實進攻真實 QA 雲端環境
# ====================================================================
USE_REAL_SERVER = True  # True = 真實 Athena QA 雲端 | False = 本地 Flask 沙盒環境

# # 本地 Flask 沙盒環境端點 (測試用)
# LOCAL_URL_PMS_TO_VENDOR = "http://127.0.0.1:5000/vendor/pms-sync-data/check-in"
# LOCAL_URL_VENDOR_TO_PMS = "http://127.0.0.1:5000/external/vendor-sync-data/car-arrival"
# LOCAL_TOKEN = "Bearer eyJhbGciOiJSUzI1Ni..."
# LOCAL_URL_CHECKIN = f"{NGROK_BASE_URL}/pms-sync-data/check-in"
# REAL_URL_CHECKIN = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/pms-sync-data/check-in"
# URL_CHECKIN = REAL_URL_CHECKIN if USE_REAL_SERVER else LOCAL_URL_CHECKIN

# ====================================================================
# 📡 基礎設施：ngrok 公網隧道與本地安全憑證配置
# ====================================================================
LOCAL_TOKEN = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"
NGROK_BASE_URL = "https://e9b6-118-163-122-183.ngrok-free.app"
PMS_BASE_URL = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms"
PMS_BASE_URL_EXTERNAL = f"{PMS_BASE_URL}/external/vendor-sync-data"

# ====================================================================
# 🚗 模組一：新詠停車場車辨系統 (thirdparty=SHIN_YEONG) 
# ====================================================================
# 1. 遠端雲端與本地端點對齊
LOCAL_URL_CAR_ARRIVAL = f"{NGROK_BASE_URL}/external/vendor-sync-data/car-arrival"
REAL_URL_CAR_ARRIVAL = f"{PMS_BASE_URL_EXTERNAL}/car-arrival"

# 2. 停車模組專屬遠端 Parameters 查詢參數
REAL_PARAMS_PARKING = {
    "hotel": "01",
    "athena": "16",
    "thirdParty": "SHIN_YEONG"
}

# 3. 業務安全邏輯微調參數
CIX_BUFFER_MINUTES = 30  # 取消入住時，給予住客車輛限時出閘之逃生緩衝時間

# ====================================================================
# 🦏 模組二：小美犀房務備品與物聯網入帳系統 (thirdparty=BR) 
# ====================================================================
# 1. 真實 Athena QA 雲端環境小美犀 5 支大一統端點基底 URL
REAL_URL_AMENITY = f"{PMS_BASE_URL_EXTERNAL}/room-pay"  # 💡 小美犀核心帳務 URL 基底，後續會在此基礎上拼接具體功能路徑

# 2. ⚡ 核心擴充：小美犀 5 支核心 API 遠端 URL 矩陣
REAL_URL_BR_ROOM_NOS   = f"{REAL_URL_AMENITY}/room-pay/room-nos"
REAL_URL_BR_MIFARE_NOS = f"{REAL_URL_AMENITY}/room-pay/mifare-nos"
REAL_URL_BR_ROOM_PAY   = f"{REAL_URL_AMENITY}/room-pay"
REAL_URL_BR_PAY_CANCEL = f"{REAL_URL_AMENITY}/room-pay-cancel"
REAL_URL_BR_BILLING    = f"{REAL_URL_AMENITY}/room-billing"

# 3. 🎯 關鍵調整：小美犀專屬遠端 Parameters 查詢參數
REAL_PARAMS_AMENITY = {
    "hotel": "01",
    "athena": "16",
    "thirdParty": "BR"  # 💡 完美對齊小美犀廠商代碼，確保帳務能精準落入 PMS 傳輸日誌
}

# ====================================================================
# 🔑 全域安全通行金鑰 (Bearer Token)
# ====================================================================
# 💡 保持你今天最新從 Athena 網頁抓取之智慧身份憑證
REAL_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJRcV9OU2F6QUt5aVgxVDZ3WG1hNlZUSmN5RXVrQ2xQc09tVF81dW1seWswIn0.eyJleHAiOjE3Nzk2OTg2NjQsImlhdCI6MTc3OTY5Njg2NCwiYXV0aF90aW1lIjoxNzc5Njg1ODQ1LCJqdGkiOiJvZnJ0cnQ6NDc3OThkNWUtOTk0Ni00MzUyLTgzNDEtZjRkNDllYjg0OGNiIiwiaXNzIjoiaHR0cHM6Ly9hdXRoLmF0aGVuYS5jb20udHcvcmVhbG1zLzE2IiwiYXVkIjoiYWNjb3VudCIsInN1YiI6IjM2ODBhYWY1LTkwMGQtNDk3ZC1iMTQzLWZkZTRmYTk2YzVhNSIsInR5cCI6IkJlYXJlciIsImF6pCI6ImludGVybmFsIiwic2lkIjoiOTU1YmM2NGUtMGFhMC00NjEyLTkyZWQtOWZiZDk3NGM0MjVlIiwiYWNyIjoiMSIsImFsbG93ZWQtb3JpZ2lucyI6WyIqIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJkZWZhdWx0LXJvbGVzLTE2Iiwib2ZmbGluZV9hY2Nlc3MiLCJCVVlFUiIsInVtYV9hdXRob3JpemF0aW9uIiwiVVNFUiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoib3BlbmlkIHByb2ZpbGUgZW1haWwgb2ZmbGluZV9hY2Nlc3MiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiYXRoZW5hX3VzZXJfaWQiOiJhMjUwMDIiLCJjdXJyZW50Q29tcGFueUNvZGUiOiJaWkFUSEVOQSIsImN1cnjenRIb3RlbENvZGUiOiIwMSIsInByZWZlcnJlZF91c2VybmFtZSI6ImEyNTAwMiIsImdpdmVuX25hbWUiOiIiLCJsb2NhbGUiOiJ6aC1UVyIsImZhbWlseV9uYW1lIjoiIiwiZW1haWwiOiJnYWxlbi5jaHVAYXRoZW5hLmNvbS50dyJ9.AMrrEtR-dL7ehyj3kMeyeWzgvG2puyv22V_IzYpVlBFp6PiwWYyw1NTJ-_bOEjVcfcSfUeySgWYcrzLiiR-lpUOIHiCyO4tmVWihG329HDSeqVecca2xn9YC_3pm2qo5PtBbH_IhtBlFzIjsfUWDyReth5wGPEj49S8hLYc1j7S0scwt9CWM1_v7gopnEy53GmYScjuWLPwVMDBMYsh3LP2ILc4xuhfVmrLMLjb48awDWMJpCr8uOSFcEt6vcQ6pv0TANIEMDgegCo06FsBDUkrJGEhc5lKC2V-L9kBziYF6SiqtYGPtmVpupwug64xokWDwrKd0E4XV-i33UrwvTg"

# ====================================================================
# 🎛️ 動態路由動態調度開關 (解耦後的全域環境變數)
# ====================================================================
CURRENT_TOKEN = REAL_TOKEN if USE_REAL_SERVER else LOCAL_TOKEN

# 停車辨識執行期變數
URL_CAR_ARRIVAL = REAL_URL_CAR_ARRIVAL if USE_REAL_SERVER else LOCAL_URL_CAR_ARRIVAL
CURRENT_PARAMS_PARKING = REAL_PARAMS_PARKING if USE_REAL_SERVER else {}

# 小美犀入帳執行期變數 (預留給主動測試腳本調度)
CURRENT_PARAMS_AMENITY = REAL_PARAMS_AMENITY if USE_REAL_SERVER else {}