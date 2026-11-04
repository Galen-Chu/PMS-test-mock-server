# server/roomcontrol/vendors/vendor_IPTV.py
"""IPTV 雲朗 — A7 公版房控廠商(2026-11-04 廠商代號 70 確認)。

thirdParty 代碼 70;REVE-CODE TT 代換 70(如 CKI 出站 03009010TT → 0300901070)。
差異定位:MINXON/CHAOFENG 走「廠商→PMS」匯入面;IPTV 另測 sa11 THIRDPARTY_DT_CONF
住客顯示名稱參數(guest_display_name / user_defined_display_name)作用於
PMS→廠商 CKI 出站 XML 的住客姓名欄(ALT_NAM)。
公版介面,無專屬轉換邏輯——XML 組裝/解析共用 vendor_A7_XML 工具。
"""
VENDOR_ID = "IPTV"
VENDOR_LABEL = "雲朗IPTV"
THIRD_PARTY_CODE = "70"

# sa10 出站訊息代碼樣板(PMS→廠商;TT 帶實際廠商代號):
# CKI=A1 C/I / RMC=A3 換房 / COX=A5 C/O還原 / CKO=A2 退房 / CIX=A4 C.I還原(客製)
OUTBOUND_REVE_PREFIX = {"CKI": "03009010", "RMC": "03009030", "COX": "03009021",
                        "CKO": "03009020", "CIX": "03009011"}
REVE_CKI_TT = "03009010TT"

# QA THIRDPARTY_DT(廠商70)掛載的 6 API:出站 5(CKI/RMC/COX/CKO/CIX)+ 入站 1(ROOM_INF);
# CKO/CIX 出站僅 REVE/ACTION_COD/ROOM_NOS/ACTION_DAT 四欄、無住客姓名欄 → 不適用顯示名稱參數

# QA 端 THIRDPARTY_DT_CONF(廠商70)已見參數的 THIRDPARTY_ACTION_COD
# (2026-11-04 QA DB 截圖:CKI/RMC/COX/ROOM_INF 各掛兩參數,THIRDPARTY_VERSION=DEFAULT XML)
CONF_ACTIONS = ("CKI", "RMC", "COX", "ROOM_INF")

# sa11/QA 參數代碼(PARAM_COD,與 QA DB 逐字一致)
PARAM_DISPLAY_NAME = "guest.display.name"
PARAM_USER_DEFINED = "user.defined.display.name"


def reve_outbound(action_cod: str, vendor_code: str) -> str:
    """出站 REVE-CODE:訊息樣板前綴 + 廠商代號(如 RMC×70 → 0300903070)。"""
    return f"{OUTBOUND_REVE_PREFIX[action_cod]}{vendor_code}"


def reve_cki(vendor_code: str) -> str:
    """CKI 出站 REVE-CODE:03009010 + 廠商代號(雲朗 IPTV=70 → 0300901070)。"""
    return reve_outbound("CKI", vendor_code)
