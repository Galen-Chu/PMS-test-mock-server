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

# 訊息代碼(文件中 TT 為佔位,實際代碼上線前由德安提供)
REVE_ROOM_STA = "0300TT4190"   # B4 房況變化告知(廠商→PMS)
REVE_ROOM_INF = "0300TT1090"   # A6 房間現況住客資訊查詢(廠商→PMS)

DEFAULT_STATUS_BITS = "1000001100100000"   # sa10 房間房況預設值
MSG_DONE = "Transaction done successfully."


def action_dat_now() -> str:
    """ACTION_DAT CHAR(21):YYYY/MM/DD HH24:MI:SS。"""
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def build_rowset_xml(rows) -> str:
    """組 sa10 樣式的 ROWSET>ROW XML(單列給 dict、多列給 list[dict];欄位依 dict 順序)。"""
    if isinstance(rows, dict):
        rows = [rows]
    lines = ['<?xml version="1.0"?>', "<ROWSET>"]
    for fields in rows:
        lines.append("<ROW>")
        for k, v in fields.items():
            lines.append(f"<{k}>{escape('' if v is None else str(v))}</{k}>")
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


def build_room_sta_push(room_nos, status_bits, action_dat=None) -> str:
    """B4 送全部房況(SAMPLE2 樣式,含 INS_CARD_INF/INS_CARD_NO 空欄位)。"""
    bits = status_bits.strip().strip("#")
    return build_rowset_xml({
        "REVE-CODE": REVE_ROOM_STA,
        "ROOM_NOS": room_nos,
        "INS_CARD_INF": "",
        "INS_CARD_NO": "",
        "ACTION_COD": f"#ROOM_STA#{bits}#",
        "ACTION_STA": "1",
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_room_inf_query(room_nos, action_dat=None) -> str:
    """A6 房間狀態查詢請求。"""
    return build_rowset_xml({
        "REVE-CODE": REVE_ROOM_INF,
        "ACTION_COD": "ROOM_INF",
        "ROOM_NOS": room_nos,
        "ACTION_DAT": action_dat or action_dat_now(),
    })


def build_ack_response_xml(reve_code, action_cod, retn_desc=None, action_dat=None) -> str:
    """通用回應 XML(RETN-CODE 0000;Set 類請帶 retn_desc='1112 Set <ACTION_COD>')。"""
    return build_rowset_xml({
        "SEND-CODE": reve_code,
        "ACTION_COD": action_cod,
        "RETN-CODE": "0000",
        "RETN-CODE-DESC": retn_desc or (MSG_DONE + "."),
        "MSG-ID": "0000",
        "MSG-DESC": MSG_DONE + ".",
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
        "MSG-DESC": MSG_DONE + ".",
        "ACTION_DAT": action_dat_now(),
    })
