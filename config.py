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

# 本地端點配置 (完美對齊 Flask 路由定義)
LOCAL_GET_WHITELIST = f"{NGROK_BASE_URL}/internal/debug/whitelist"
LOCAL_TOKEN = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"

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
REAL_URL_BR_ROOM_NOS   = f"{PMS_BASE_URL_EXTERNAL}/room-pay/room-nos"
REAL_URL_BR_MIFARE_NOS = f"{PMS_BASE_URL_EXTERNAL}/room-pay/mifare-nos"
REAL_URL_BR_ROOM_PAY   = f"{PMS_BASE_URL_EXTERNAL}/room-pay"
REAL_URL_BR_PAY_CANCEL = f"{PMS_BASE_URL_EXTERNAL}/room-pay-cancel"
REAL_URL_BR_BILLING    = f"{PMS_BASE_URL_EXTERNAL}/room-billing"

# 小美犀專屬全域 URL Params 字典
REAL_PARAMS_AMENITY = {
    "hotel": "01",
    "athena": "16",
    "thirdParty": "BR"
}

# 執行期動態路由 URL Params
CURRENT_PARAMS_PARKING = REAL_PARAMS_PARKING if USE_REAL_SERVER else {}
CURRENT_PARAMS_AMENITY = REAL_PARAMS_AMENITY if USE_REAL_SERVER else {}