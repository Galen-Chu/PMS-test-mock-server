# config.py
# ====================================================================
# ⚠️ 戰略總開關：切換為 True 即實打實進攻真實 QA 雲端環境
# ====================================================================
USE_REAL_SERVER = True  # True = 真實 Athena QA 雲端 | False = 本地 Flask 沙盒環境

# ====================================================================
# 📡 基礎設施：網址基底配置 (校準修正：徹底移除路徑多黏尾巴的隱患)
# ====================================================================
NGROK_BASE_URL = "https://2e5a-118-163-122-183.ngrok-free.app"
PMS_BASE_URL = "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms"

# 🎯 大一統網關通信路徑 (純淨基底)
PMS_BASE_URL_EXTERNAL = f"{PMS_BASE_URL}/external/vendor-sync-data"
PMS_QA_ATHENA_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJRcV9OU2F6QUt5aVgxVDZ3WG1hNlZUSmN5RXVrQ2xQc09tVF81dW1seWswIn0.eyJleHAiOjE3ODExNjA1NjEsImlhdCI6MTc4MTE1ODc2MSwiYXV0aF90aW1lIjoxNzgxMTM2NjIwLCJqdGkiOiJvZnJ0cnQ6OTRiNjVmMDEtMWU2NC04NDZmLWRmMzctNmFlZmZlZDAwYWM5IiwiaXNzIjoiaHR0cHM6Ly9hdXRoLmF0aGVuYS5jb20udHcvcmVhbG1zLzE2IiwiYXVkIjoiYWNjb3VudCIsInN1YiI6IjM2ODBhYWY1LTkwMGQtNDk3ZC1iMTQzLWZkZTRmYTk2YzVhNSIsInR5cCI6IkJlYXJlciIsImF6cCI6ImludGVybmFsIiwic2lkIjoiOUdmMTdsZTZPNDVOZFU0ZWdzTEhFdkJ3IiwiYWNyIjoiMSIsImFsbG93ZWQtb3JpZ2lucyI6WyIqIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJkZWZhdWx0LXJvbGVzLTE2Iiwib2ZmbGluZV9hY2Nlc3MiLCJCVVlFUiIsInVtYV9hdXRob3JpemF0aW9uIiwiVVNFUiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoib3BlbmlkIHByb2ZpbGUgZW1haWwgb2ZmbGluZV9hY2Nlc3MiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiYXRoZW5hX3VzZXJfaWQiOiJhMjUwMDIiLCJjdXJyZW50Q29tcGFueUNvZGUiOiJaWkFUSEVOQSIsImN1cnJlbnRIb3RlbENvZGUiOiIwMSIsInByZWZlcnJlZF91c2VybmFtZSI6ImEyNTAwMiIsImdpdmVuX25hbWUiOiIiLCJsb2NhbGUiOiJ6aC1UVyIsImZhbWlseV9uYW1lIjoiIiwiZW1haWwiOiJnYWxlbi5jaHVAYXRoZW5hLmNvbS50dyJ9.g6KCJA3skNQRU9gqhXYu3aY9Q90lu5mVP-wRSVgyZ1FuXpBqqeNH39nXnsN3zGaEoDM64n8r5EuujTh6Czv7KUkHgNZ1ZVDAXTmDz5XxwOGh2fbMaXzf3t_Y9Xy3lksPncxhf_6N9_idqK9BG1qlLaDmtME7HOFRkFlmHjHfatr-7diqSGCW-SbXkFn4oppgqcBo7LZdtGYOom-EoGJTJ_AKS1L62_yuSq-YA6n4OyAEpC54atzb_4DaTZKuGcgsoOYu89ok3Gy7p7QXgmtTLjQaMewqMV3xpLdY78R3YbsMlKhV3aSJhsGZQp2Ic8UpxrmsTHN7UqHBr0Dv2oLbPA"

# 本地端點配置 (完美對齊 Flask 路由定義)
LOCAL_GET_WHITELIST = f"{NGROK_BASE_URL}/internal/debug/whitelist"
LOCAL_TOKEN = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"

# 真實端點配置 (完美對齊 Athena QA 環境實測成功之真實網址)
CURRENT_TOKEN = PMS_QA_ATHENA_TOKEN if USE_REAL_SERVER else LOCAL_TOKEN

# ====================================================================
# 👮‍♂️ 網關通行金鑰層 (大一統 Header 字典，確保程式碼易於統一維護)
# ====================================================================
REAL_HEADERS_BACCHUS = {
    "bacchus-athenaid": "16",
    "bacchus-hotelcod": "01",
    "accept": "*/*",
    "Content-Type": "application/json"
}

LOCAL_HEADERS_BACCHUS = {
    "athena": "1",
    "hotel": "HOTEL01",
    "accept": "application/json",
    "Content-Type": "application/json"
}

# 💡 執行期動態路由大一統 Header (小美犀與車辨直接共用此變數，極易管理維護)
CURRENT_HEADERS_BACCHUS = REAL_HEADERS_BACCHUS if USE_REAL_SERVER else LOCAL_HEADERS_BACCHUS

# ====================================================================
# 🚗 模組一：新詠停車場車辨系統
# ====================================================================
REAL_URL_CAR_ARRIVAL = f"{PMS_BASE_URL_EXTERNAL}/car-arrival"
REAL_PARAMS_PARKING = {
    "hotel": "01",
    "athena": "16",
    "thirdParty": "SHIN_YEONG"
}

# ====================================================================
# 🦏 模組二：小美犀房務備品與物聯網入帳系統 (thirdparty=BR)
# ====================================================================
# 🎯 網址純淨化：完美對齊 Swagger 實測成功之真實網址物理路徑
REAL_URL_ROOM_NOS   = f"{PMS_BASE_URL_EXTERNAL}/room-pay/room-nos"
REAL_URL_MIFARE_NOS = f"{PMS_BASE_URL_EXTERNAL}/room-pay/mifare-nos"
REAL_URL_ROOM_PAY   = f"{PMS_BASE_URL_EXTERNAL}/room-pay"
REAL_URL_ROOM_PAY_CANCEL = f"{PMS_BASE_URL_EXTERNAL}/room-pay-cancel"
REAL_URL_ROOM_BILLING    = f"{PMS_BASE_URL_EXTERNAL}/room-billing"

# 小美犀專屬全域 URL Params 字典
REAL_PARAMS_AMENITY = {
    "hotel": "01",
    "athena": "16",
    "thirdParty": "BR"
}

# 執行期動態路由 URL Params
CURRENT_PARAMS_PARKING = REAL_PARAMS_PARKING if USE_REAL_SERVER else {}
CURRENT_PARAMS_AMENITY = REAL_PARAMS_AMENITY if USE_REAL_SERVER else {}