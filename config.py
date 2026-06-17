# config.py

# ====================================================================
# ⚠️ 戰略總開關：[LOCAL = 本地沙盒 | REAL_QA = 真實QA雲端 | REAL_UG = 真實UG雲端]
# ====================================================================
ENV_SWITCH = "REAL_UG"  # 💡 唯一的戰略指針！可切換為: "LOCAL", "REAL_QA", "REAL_UG"
USE_REAL_SERVER = ENV_SWITCH.startswith("REAL")

# 本地邊緣端 Ngrok 轉發基底
NGROK_BASE_URL = "https://2e5a-118-163-122-183.ngrok-free.app"
LOCAL_TOKEN = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"

# ====================================================================
# 📊 環境配置矩陣 (Environment Matrix)
# ====================================================================
ENV_MATRIX = {
    "LOCAL": {
        "BASE_URL_EXTERNAL": f"{NGROK_BASE_URL}/external/vendor-sync-data",
        "TOKEN": LOCAL_TOKEN,
        "ATHENA_ID": "1",
        "HOTEL_COD": "HOTEL01",
        "HEADERS": {
            "athena": "1",
            "hotel": "HOTEL01",
            "accept": "application/json",
            "Content-Type": "application/json"
        }
    },
    "REAL_QA": {
        "BASE_URL_EXTERNAL": "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/external/vendor-sync-data",
        "TOKEN": "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJRcV9OU2F6QUt5aVgxVDZ3WG1hNlZUSmN5RXVrQ2xQc09tVF81dW1seWswIn0...", # 為了排版縮短
        "ATHENA_ID": "16",
        "HOTEL_COD": "01",
        "HEADERS": {
            "bacchus-athenaid": "16",
            "bacchus-hotelcod": "01",
            "accept": "*/*",
            "Content-Type": "application/json"
        }
    },
    "REAL_UG": {
        "BASE_URL_EXTERNAL": "https://bacug.athena.com.tw/pms/api/v3.0/pms/external/vendor-sync-data",
        "TOKEN": "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJtZVZGeGpnODZLMkYxX2JSSjcxWmxYSER2YUprUENHX1FQM3p6ejVkV0xjIn0...", # 為了排版縮短
        "ATHENA_ID": "28",
        "HOTEL_COD": "01",
        "HEADERS": {
            "bacchus-athenaid": "28",
            "bacchus-hotelcod": "01",
            "accept": "*/*",
            "Content-Type": "application/json"
        }
    }
}

# ====================================================================
# 🌊 執行期動態洗滌與大一統對齊 (Runtime Dynamic Resolution)
# ====================================================================
# 安全閥：防範手滑打錯字，預設退回 LOCAL
active_cfg = ENV_MATRIX.get(ENV_SWITCH, ENV_MATRIX["LOCAL"])

# 0. 👮‍♂️ 網關通行金鑰層對齊
CURRENT_TOKEN = active_cfg["TOKEN"]
CURRENT_HEADERS_BACCHUS = active_cfg["HEADERS"]

_base_ext = active_cfg["BASE_URL_EXTERNAL"]

# 1. 🚗 模組一：新詠/博辰車辨辨識系統 URLs 封裝
REAL_URL_CAR_ARRIVAL = f"{_base_ext}/car-arrival"
REAL_PARAMS_PARKING = {
    "bacchus-hotelcod": active_cfg["HOTEL_COD"],
    "bacchus-athenaid": active_cfg["ATHENA_ID"],
    "thirdParty": "SHIN_YEONG" # "PAYTRONEX"
}

CURRENT_PARAMS_PARKING = REAL_PARAMS_PARKING if USE_REAL_SERVER else {}

# 2. 🦏 模組二：小美犀房務備品與物聯網入帳系統 URLs 封裝
REAL_URL_ROOM_NOS        = f"{_base_ext}/room-pay/room-nos"
REAL_URL_MIFARE_NOS      = f"{_base_ext}/room-pay/mifare-nos"
REAL_URL_ROOM_PAY        = f"{_base_ext}/room-pay"
REAL_URL_ROOM_PAY_CANCEL = f"{_base_ext}/room-pay-cancel"
REAL_URL_ROOM_BILLING    = f"{_base_ext}/room-billing"

REAL_PARAMS_AMENITY = {
    "bacchus-hotelcod": active_cfg["HOTEL_COD"],
    "bacchus-athenaid": active_cfg["ATHENA_ID"],
    "thirdParty": "BR"
}
CURRENT_PARAMS_AMENITY = REAL_PARAMS_AMENITY if USE_REAL_SERVER else {}

# 💡 保留本地調試端點相容
LOCAL_GET_WHITELIST = f"{NGROK_BASE_URL}/parking/internal/whitelist"