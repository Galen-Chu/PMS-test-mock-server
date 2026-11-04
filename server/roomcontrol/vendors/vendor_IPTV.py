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

# sa10 A1:PMS→廠商 C/I 出站訊息代碼(TT 樣板;實際帶廠商代號)
REVE_CKI_TT = "03009010TT"


def reve_cki(vendor_code: str) -> str:
    """CKI 出站 REVE-CODE:03009010 + 廠商代號(雲朗 IPTV=70 → 0300901070)。"""
    return f"03009010{vendor_code}"
