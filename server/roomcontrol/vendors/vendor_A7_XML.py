# server/roomcontrol/vendors/vendor_A7_XML.py
"""A7 公版房控 XML 介面策略(sa_docs/sa10_a7_pms_xml.txt V1.2)。

契約要點:
- 訊息 XML:ROWSET>ROW,主要欄位 REVE-CODE / ACTION_COD / ROOM_NOS / ACTION_STA / ACTION_DAT
  (ACTION_DAT CHAR(21),格式 YYYY/MM/DD HH24:MI:SS)。
- 回應 XML:SEND-CODE(=REVE-CODE)/ ACTION_COD(回映)/ RETN-CODE(0000=正常,其他=異常)/
  RETN-CODE-DESC / MSG-ID(0000) / MSG-DESC;Set 類(#...#)回應 DESC = "1112 Set <ACTION_COD>"。
- B4 ROOM_STA(房況變化告知,廠商→PMS):ACTION_COD = #ROOM_STA#<16位房況字串>#;
  同族另有 CLEAN / DND / DOOR / EMG / MAIN_POWER / #RMTEMP#<室溫>#。
- A6 ROOM_INF(房間現況住客資訊查詢,廠商→PMS):回應多筆住客 ROW(一住客一 ROW),
  ROOM_STA CHAR(1):O住人 / S參觀房 / V空房;GUEST_STA:K關帳 / O開帳。
- 16 位房況字串(sa10「房間房況順序說明」;預設 #1000001100100000#):
    1 Keyhouse(1拔卡,0插卡)   2 Keybox(1插卡,0拔卡)     3 冷氣(1開,0關)
    4 總電源(1開,0關)          5 鐵捲門(1開,0關)          6 一氧化碳(1動作,0無)
    7 防盜(0動作,1無)          8 緊急按鈕(0動作,1無;F=房間OFF_LINE)
    9 房間清潔(1請打掃/2打掃中/3待巡房/4巡房中/0清潔完成——德安收 0 設為乾淨房,餘皆髒房)
   10 勿擾(1動作,0無)         11 房門(0開,1關)          12–16 保留
- 傳輸:HTTP GET「德安網址?athena=&hotel=&thirdParty=TT&TxnData=<XML>&istom=1」(URL 內 # 需 %23),
  另有 REST 版 POST /third-party/import-sync-files(sa8/sa9 swagger);沙盒 RC0 實作後者。
"""
from datetime import datetime
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

# 訊息代碼:0300 + <2 碼廠商代號> + <4 碼動作>(sa10;文件以 TT 佔位)
# 2026-09-03 使用者提供實際代碼:MINXON 民笙=81、CHAOFENG 超烽=86
REVE_ROOM_STA = "0300TT4190"   # B4 房況變化告知(廠商→PMS)
REVE_ROOM_INF = "0300TT1090"   # A6 房間現況住客資訊查詢(廠商→PMS)
REVE_RETURN = "0300TT4290"     # A10 全部房況回傳查詢(廠商→PMS)
REVE_KEYBOX = "0300TT4390"     # B5 節電器(KeyBox)現況告知(廠商→PMS)

# B4 單值 action → 房況位元索引(0 基;sa10「房間房況順序說明」對應位)
#   CLEAN=位9清潔(ACTION_STA 0-4)/ DND=位10勿擾 / DOOR=位11房門 / EMG=位8緊急 / MAIN_POWER=位4總電源
B4_SINGLE_BIT_INDEX = {"CLEAN": 8, "DND": 9, "DOOR": 10, "EMG": 7, "MAIN_POWER": 3}


def reve_room_sta(vendor_code="TT") -> str:
    return f"0300{vendor_code}4190"


def reve_room_inf(vendor_code="TT") -> str:
    return f"0300{vendor_code}1090"


def reve_return(vendor_code="TT") -> str:
    return f"0300{vendor_code}4290"


def reve_keybox(vendor_code="TT") -> str:
    return f"0300{vendor_code}4390"


def is_b4_action(action_cod: str) -> bool:
    """是否為 B4 已知 action(單值族 CLEAN/DND/DOOR/EMG/MAIN_POWER 或 #...# 帶值族)。"""
    if action_cod in B4_SINGLE_BIT_INDEX:
        return True
    return action_cod.startswith("#ROOM_STA#") or action_cod.startswith("#RMTEMP#")


def set_status_bit(bits: str, index: int, value) -> str:
    """更新 16 位房況字串指定位置(0 基)為單字元值;非 16 位或索引超界 → 原樣回傳(防禦)。"""
    if len(bits) != 16 or not (0 <= index < 16):
        return bits
    return bits[:index] + str(value) + bits[index + 1:]


DEFAULT_STATUS_BITS = "1000001100100000"   # sa10 房間房況預設值
MSG_DONE = "Transaction done successfully."


def action_dat_now() -> str:
    """ACTION_DAT CHAR(21):YYYY/MM/DD HH24:MI:SS。"""
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def build_rowset_xml(rows) -> str:
    """組 sa10 樣式的 ROWSET>ROW XML(單列給 dict、多列給 list[dict];欄位依 dict 順序)。

    值為 None 的欄位整個省略(B5 回應契約無 ACTION_COD,據此省略該 tag);空字串仍輸出空 tag。
    """
    if isinstance(rows, dict):
        rows = [rows]
    lines = ['<?xml version="1.0"?>', "<ROWSET>"]
    for fields in rows:
        lines.append("<ROW>")
        for k, v in fields.items():
            if v is None:
                continue
            lines.append(f"<{k}>{escape(str(v))}</{k}>")
        lines.append("</ROW>")
    lines.append("</ROWSET>")
    return "\n".join(lines)


def parse_rowset_xml(xml_str: str):
    """解 ROWSET>ROW → list[dict](一 ROW 一 dict,tag→text,前後空白去除)。

    XML 格式錯誤或無 ROW → ValueError(mock 路由據此回 417)。
    """
    root = ET.fromstring(xml_str)
    rows = []
    for row in root.iter("ROW"):
        rows.append({child.tag: (child.text or "").strip() for child in row})
    if not rows:
        raise ValueError("ROWSET 內無 ROW")
    return rows


def build_room_sta_push(room_nos, status_bits, action_dat=None, vendor_code="TT") -> str:
    """B4 送全部房況(SAMPLE2 樣式,含 INS_CARD_INF/INS_CARD_NO 空欄位)。"""
    bits = status_bits.strip().strip("#")
    return build_rowset_xml({
        "REVE-CODE": reve_room_sta(vendor_code),
        "ROOM_NOS": room_nos,
        "INS_CARD_INF": "",
        "INS_CARD_NO": "",
        "ACTION_COD": f"#ROOM_STA#{bits}#",
        "ACTION_STA": "1",
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_room_inf_query(room_nos, action_dat=None, vendor_code="TT") -> str:
    """A6 房間狀態查詢請求(單房現況住客資訊)。"""
    return build_rowset_xml({
        "REVE-CODE": reve_room_inf(vendor_code),
        "ACTION_COD": "ROOM_INF",
        "ROOM_NOS": room_nos,
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_return_query(action_dat=None, vendor_code="TT") -> str:
    """A10 全部房況回傳查詢請求(無房號欄位;回應為每房一 ROW)。"""
    return build_rowset_xml({
        "REVE-CODE": reve_return(vendor_code),
        "ACTION_COD": "RETURN",
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_clean_push(room_nos, clean_state, action_dat=None, vendor_code="TT") -> str:
    """B4 SAMPLE1:清掃動作(ACTION_COD=CLEAN;ACTION_STA=清潔狀態,即位元 9 值域 0-4)。"""
    return build_rowset_xml({
        "REVE-CODE": reve_room_sta(vendor_code),
        "ROOM_NOS": room_nos,
        "ACTION_COD": "CLEAN",
        "ACTION_STA": str(clean_state),
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_rmtemp_push(room_nos, temperature, action_dat=None, vendor_code="TT") -> str:
    """B4 SAMPLE3:房間室溫(#RMTEMP#26C#;A7 前台顯示;ACTION_STA 契約不處理可省略,依樣本補 1)。"""
    return build_rowset_xml({
        "REVE-CODE": reve_room_sta(vendor_code),
        "ROOM_NOS": room_nos,
        "ACTION_COD": f"#RMTEMP#{temperature}#",
        "ACTION_STA": "1",
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_keybox_push(room_nos, card_typ, card_uid, indoor_name, action_sta,
                      action_dat=None, vendor_code="TT") -> str:
    """B5 節電器現況(REVE 0300xx4390;無 ACTION_COD 欄位,以 CARD_TYP/ACTION_STA 表插拔卡)。"""
    return build_rowset_xml({
        "REVE-CODE": reve_keybox(vendor_code),
        "ROOM_NOS": room_nos,
        "CARD_TYP": card_typ,
        "CARD_UID": card_uid,
        "INDOOR_NAME": indoor_name,
        "ACTION_STA": str(action_sta),
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_ack_response_xml(reve_code, action_cod, retn_desc=None, action_dat=None) -> str:
    """通用回應 XML(RETN-CODE 0000;Set 類請帶 retn_desc='1112 Set <ACTION_COD>')。"""
    return build_rowset_xml({
        "SEND-CODE": reve_code,
        "ACTION_COD": action_cod,
        "RETN-CODE": "0000",
        "RETN-CODE-DESC": retn_desc or (MSG_DONE),
        "MSG-ID": "0000",
        "MSG-DESC": MSG_DONE,
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_error_response_xml(reve_code, action_cod, retn_code, retn_desc) -> str:
    """處理異常回應(非 0000;sa10:RETN-CODE 其他=資料處理異常)。"""
    return build_rowset_xml({
        "SEND-CODE": reve_code,
        "ACTION_COD": action_cod,
        "RETN-CODE": retn_code,
        "RETN-CODE-DESC": retn_desc,
        "MSG-ID": "0000",
        "MSG-DESC": MSG_DONE,
        "ACTION_DAT": action_dat_now(),
    })
