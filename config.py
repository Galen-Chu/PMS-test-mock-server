# config.py
import os

# ====================================================================
# ⚠️ 戰略總開關：[LOCAL_OFFLINE = 閉環規格比對(不出站) | LOCAL = 本地沙盒 | REAL_QA = 真實QA雲端 | REAL_UG = 真實UG雲端]
# ====================================================================
ENV_SWITCH = os.environ.get("ENV_SWITCH", "REAL_UG")  # 💡 唯一的戰略指針！可由環境變數覆寫(CI 用 LOCAL_OFFLINE)；可切換為: "LOCAL_OFFLINE", "LOCAL", "REAL_QA", "REAL_UG"
USE_REAL_SERVER = ENV_SWITCH.startswith("REAL")
# 💡 閉環規格比對模式：路由組好 Payload 後直接回傳供比對，完全不對外發送任何請求
IS_OFFLINE = ENV_SWITCH == "LOCAL_OFFLINE"

# 本地邊緣端 Ngrok 轉發基底
NGROK_BASE_URL = "https://2e5a-118-163-122-183.ngrok-free.app"
LOCAL_TOKEN = "2pKET7v9JqFxCzpj9bbT6dC17uM_wnTdoVjQtd1WbRPB48T7"
# 本地 Flask 沙盒基底（main.py 跑在 127.0.0.1:5000）；LOCAL/LOCAL_OFFLINE 編排時直接打這裡
LOCAL_SERVER_BASE = os.environ.get("LOCAL_SERVER_BASE", "http://127.0.0.1:5000")

# ====================================================================
# 📊 環境配置矩陣 (Environment Matrix)
# ====================================================================
ENV_MATRIX = {
    "LOCAL_OFFLINE": {
        # 💡 純規格比對用：URL/Token 僅供組裝 Payload 展示，路由層會在送出前攔截、永遠不會真的打出去
        "BASE_URL_EXTERNAL": "OFFLINE://spec-check-no-egress",
        "TOKEN": LOCAL_TOKEN,
        "ATHENA_ID": "1",
        "HOTEL_COD": "HOTEL01",
        "HEADERS": {
            "athena": "1",
            "hotel": "HOTEL01",
            "accept": "application/json",
            "Content-Type": "application/json"
        },
        "READY": True,    # 編排層是否允許執行（False → POST /runs 回 409）
        "PMS_URL": ""     # UI「真實環境提示卡」顯示用；LOCAL_* 無對外 URL
    },
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
        },
        "READY": True,
        "PMS_URL": NGROK_BASE_URL
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
        },
        "READY": True,
        "PMS_URL": "https://qa-cloud.athena.com.tw/pms/api/v3.0/pms"
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
        },
        "READY": True,
        "PMS_URL": "https://bacug.athena.com.tw/pms/api/v3.0/pms"
    },
    "REAL_SIT": {
        # 💡 預留：尚未取得 SIT 雲端的 URL/Token/Header，READY=False 讓 UI 顯示「尚未設定」、API 拒絕執行
        "BASE_URL_EXTERNAL": "",
        "TOKEN": "",
        "ATHENA_ID": "",
        "HOTEL_COD": "",
        "HEADERS": {"accept": "*/*", "Content-Type": "application/json"},
        "READY": False,
        "PMS_URL": ""
    },
    "REAL_MAS": {
        # 💡 預留：尚未取得 MAS 雲端的 URL/Token/Header，READY=False
        "BASE_URL_EXTERNAL": "",
        "TOKEN": "",
        "ATHENA_ID": "",
        "HOTEL_COD": "",
        "HEADERS": {"accept": "*/*", "Content-Type": "application/json"},
        "READY": False,
        "PMS_URL": ""
    }
}

# 🎨 環境 UI metadata（對齊設計規格 §3 / 原型 ENV_META）：顯示名稱、狀態點顏色、二列佈局
ENV_UI_META = {
    "LOCAL_OFFLINE": {"desc": "閉環規格比對，不對外發送任何請求", "color": "#9aa0ac"},
    "LOCAL":         {"desc": "本地沙盒，走 Ngrok 邊緣端轉發",     "color": "#4da3ff"},
    "REAL_QA":       {"desc": "真實德安 QA 雲端 E2E 串接",          "color": "#f472b6"},
    "REAL_SIT":      {"desc": "真實德安 SIT 測試雲端 E2E 串接（config 待開發）", "color": "#c084fc"},
    "REAL_UG":       {"desc": "真實德安 UG 雲端 E2E 串接（預設）",  "color": "#35d399"},
    "REAL_MAS":      {"desc": "真實德安 MAS 雲端 E2E 串接（config 待開發）", "color": "#ff8a3d"},
}
ENV_UI_ROWS = [["LOCAL_OFFLINE", "LOCAL", "REAL_QA"], ["REAL_SIT", "REAL_UG", "REAL_MAS"]]

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
# 💡 PMS→廠商方向的住客同步端點（比照 car-arrival 同基底）；真實雲端此端點多由 PMS 觸發，外部未必有權限直打
REAL_URL_CHECKIN   = f"{_base_ext}/check-in"
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