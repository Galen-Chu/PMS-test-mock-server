# config.py

# ==========================================
# ⚠️ 戰略開關：切換為 True 即實打實進攻真實 QA 雲端環境
# ==========================================
USE_REAL_SERVER = True # = 本地 Flask 沙盒環境 (預設) | True = 真實 QA 雲端環境

# # 1. 本地 Flask 沙盒環境端點
# LOCAL_URL_PMS_TO_VENDOR = "http://127.0.0.1:5000/vendor/pms-sync-data/check-in"
# LOCAL_URL_VENDOR_TO_PMS = "http://127.0.0.1:5000/external/vendor-sync-data/car-arrival"
# LOCAL_TOKEN = "Bearer eyJhbGciOiJSUzI1Ni..."

# config.py 升級

# 1. 這裡直接換成 ngrok 的公網網址
# 💡 換上你剛剛熱騰騰出爐的 ngrok 完整公網網址
NGROK_BASE_URL = "https://7913-118-163-122-183.ngrok-free.app"

# 重新定義端點路由
LOCAL_URL_CHECKIN = f"{NGROK_BASE_URL}/pms-sync-data/check-in"
LOCAL_URL_CAR_ARRIVAL = f"{NGROK_BASE_URL}/external/vendor-sync-data/car-arrival"
LOCAL_TOKEN = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"

# 2. 真實 Athena QA 雲端環境端點 (根據你實際對接的 URL 調整)
REAL_URL_CHECKIN = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/pms-sync-data/check-in"
REAL_URL_CAR_ARRIVAL = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/external/vendor-sync-data/car-arrival"
# ⚠️ 記得貼上今天最新從網頁拿到的 Bearer Token
REAL_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJRcV9OU2F6QUt5aVgxVDZ3WG1hNlZUSmN5RXVrQ2xQc09tVF81dW1seWswIn0.eyJleHAiOjE3Nzk2OTg2NjQsImlhdCI6MTc3OTY5Njg2NCwiYXV0aF90aW1lIjoxNzc5Njg1ODQ1LCJqdGkiOiJvZnJ0cnQ6NDc3OThkNWUtOTk0Ni00MzUyLTgzNDEtZjRkNDllYjg0OGNiIiwiaXNzIjoiaHR0cHM6Ly9hdXRoLmF0aGVuYS5jb20udHcvcmVhbG1zLzE2IiwiYXVkIjoiYWNjb3VudCIsInN1YiI6IjM2ODBhYWY1LTkwMGQtNDk3ZC1iMTQzLWZkZTRmYTk2YzVhNSIsInR5cCI6IkJlYXJlciIsImF6cCI6ImludGVybmFsIiwic2lkIjoiOTU1YmM2NGUtMGFhMC00NjEyLTkyZWQtOWZiZDk3NGM0MjVlIiwiYWNyIjoiMSIsImFsbG93ZWQtb3JpZ2lucyI6WyIqIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJkZWZhdWx0LXJvbGVzLTE2Iiwib2ZmbGluZV9hY2Nlc3MiLCJCVVlFUiIsInVtYV9hdXRob3JpemF0aW9uIiwiVVNFUiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoib3BlbmlkIHByb2ZpbGUgZW1haWwgb2ZmbGluZV9hY2Nlc3MiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiYXRoZW5hX3VzZXJfaWQiOiJhMjUwMDIiLCJjdXJyZW50Q29tcGFueUNvZGUiOiJaWkFUSEVOQSIsImN1cnJlbnRIb3RlbENvZGUiOiIwMSIsInByZWZlcnJlZF91c2VybmFtZSI6ImEyNTAwMiIsImdpdmVuX25hbWUiOiIiLCJsb2NhbGUiOiJ6aC1UVyIsImZhbWlseV9uYW1lIjoiIiwiZW1haWwiOiJnYWxlbi5jaHVAYXRoZW5hLmNvbS50dyJ9.AMrrEtR-dL7ehyj3kMeyeWzgvG2puyv22V_IzYpVlBFp6PiwWYyw1NTJ-_bOEjVcfcSfUeySgWYcrzLiiR-lpUOIHiCyO4tmVWihG329HDSeqVecca2xn9YC_3pm2qo5PtBbH_IhtBlFzIjsfUWDyReth5wGPEj49S8hLYc1j7S0scwt9CWM1_v7gopnEy53GmYScjuWLPwVMDBMYsh3LP2ILc4xuhfVmrLMLjb48awDWMJpCr8uOSFcEt6vcQ6pv0TANIEMDgegCo06FsBDUkrJGEhc5lKC2V-L9kBziYF6SiqtYGPtmVpupwug64xokWDwrKd0E4XV-i33UrwvTg" 

# 3. 實際雲端必要的 Query Parameters (例如飯店代碼、廠商編號)
REAL_PARAMS = {
    "hotel": "01",
    "athena": "16",
    "thirdParty": "SHIN_YEONG"
}

# --- 動態路由解析庫 ---
# 動態路由解析
URL_CHECKIN = REAL_URL_CHECKIN if USE_REAL_SERVER else LOCAL_URL_CHECKIN
URL_CAR_ARRIVAL = REAL_URL_CAR_ARRIVAL if USE_REAL_SERVER else LOCAL_URL_CAR_ARRIVAL
CURRENT_TOKEN = REAL_TOKEN if USE_REAL_SERVER else LOCAL_TOKEN
CURRENT_PARAMS = REAL_PARAMS if USE_REAL_SERVER else {}# config.py