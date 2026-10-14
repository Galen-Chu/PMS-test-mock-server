# server/pbx/vendors/vendor_PABX.py
"""☎️ 交換機(PABX)介面策略 — pbx_interface.doc 固定長度記錄編解碼。

契約(pbx_interface.doc「交換機(PABX)與系統連結界面說明」):
- 檔案介面:HOST2PMS.DAT/.IDX(德安→計費系統)、PMS2HOST.DAT/.IDX(反向);
  沙盒以 HTTP 承載同一份 192-byte 記錄字串(mock 不模擬檔案輪替 index 機制,見計畫文件 §2)。
- data record 192 bytes:Record_typ X(1)/'I'指令'R'回應、Record_nos 9(7)、Seq_nos 9(7)、
  Insert_dat 9(8) YYYYMMDD、Insert_tim 9(6) HHMMSS、Data_rmk X(161) @30~190、CR+LF @191~192。
- 排版規則:數字欄位靠右、前面填空白;文字欄位靠左、後面填空白。
- 回應記錄(Data_rmk):inst_cod ∈ {SUC,ERR,SKP} + 原指令 Insert_dat/tim/Seq_nos +
  Msg_cod X(40)(列舉:ROOM_NOT_FOUND/MSG_FORMAT/TIME_OUT/…) + Session_cod X(6)。

Data_rmk 佈局(區段內 1-based;對外絕對位置 = 29 + 區段位置):
- CKI/COX(入住開電話/退房還原):inst X(3) phone X(6) lang X(3) vip X(1) master X(6)
  guest_nam X(30) account X(20)
- CKO/CIX(退房關電話/C-I還原):inst phone
- RMC(換房):inst ophone X(6) nphone X(6)
- MCS(晨呼,雙向):inst phone mcall_dat 9(8) mcall_tim 9(6) mcall_sta X(1)
- DND/MWL/TCE/OOO:inst phone status_typ 9(1)('1'設定 '0'取消)
- PTX(電話入帳,pms→host)/MBT(Mini bar):佈局見 HOST_INST_LAYOUTS 註記(M4 帳務面)
"""
from datetime import datetime

RECORD_LEN = 192            # 含尾端 CR+LF
DATA_RMK_START = 29         # 0-based 起切點(絕對位置 30)
DATA_RMK_LEN = 161

# 指令代碼(pbq_interface「資料格式」各節)
HOST_INST_LAYOUTS = {
    # inst_cod: [(欄位, kind 'X'|'9', 長度), ...](Data_rmk 區段內依序排列)
    "CKI": [("phone_nos", "X", 6), ("lang_cod", "X", 3), ("vip_sta", "X", 1),
            ("master_nos", "X", 6), ("guest_nam", "X", 30), ("account_nos", "X", 20)],
    "COX": [("phone_nos", "X", 6), ("lang_cod", "X", 3), ("vip_sta", "X", 1),
            ("master_nos", "X", 6), ("guest_nam", "X", 30), ("account_nos", "X", 20)],
    "CKO": [("phone_nos", "X", 6)],
    "CIX": [("phone_nos", "X", 6)],
    "RMC": [("ophone_nos", "X", 6), ("nphone_nos", "X", 6)],
    "MCS": [("phone_nos", "X", 6), ("mcall_dat", "9", 8), ("mcall_tim", "9", 6),
            ("mcall_sta", "X", 1)],
    "DND": [("phone_nos", "X", 6), ("status_typ", "9", 1)],
    "MWL": [("phone_nos", "X", 6), ("status_typ", "9", 1)],
    "TCE": [("phone_nos", "X", 6), ("status_typ", "9", 1)],
    "OOO": [("phone_nos", "X", 6), ("status_typ", "9", 1)],
    # 帳務面(計費系統→德安;pbx_interface「Telephone/Mini bar (pms to host)」)
    # PTX @絕對30-103:phone 33-38、tel_nos 39-58、trans_dat 59-66、trans_tim 67-72、
    # trans_typ 73-75、sign_typ 76、trans_amt 77-83、start_dat 84-91、start_tim 92-97、
    # talk_tim 98-103(記錄帶秒數,入帳時才轉時分秒)
    "PTX": [("phone_nos", "X", 6), ("tel_nos", "X", 20), ("trans_dat", "9", 8),
            ("trans_tim", "9", 6), ("trans_typ", "X", 3), ("sign_typ", "X", 1),
            ("trans_amt", "9", 7), ("start_dat", "9", 8), ("start_tim", "9", 6),
            ("talk_tim", "9", 6)],
    # MBT @絕對30-60:phone 33-38、trans_dat 39-46、trans_tim 47-52、sign_typ 53、trans_amt 54-60
    "MBT": [("phone_nos", "X", 6), ("trans_dat", "9", 8), ("trans_tim", "9", 6),
            ("sign_typ", "X", 1), ("trans_amt", "9", 7)],
}
# 帶 Status_typ 的開關族(DND 勿擾/MWL 留言燈/TCE 限撥/OOO 修理房)
STATUS_INSTS = {"DND", "MWL", "TCE", "OOO"}
# 回應碼(Record_typ='R' 時 Data_rmk 首欄)
RESP_SUC, RESP_ERR, RESP_SKP = "SUC", "ERR", "SKP"


def _pad_text(value, n: int) -> str:
    """X(n):文字靠左、後面填空白;超長截斷。"""
    return str(value or "")[:n].ljust(n)


def _pad_num(value, n: int) -> str:
    """9(n):數字靠右、前面填空白;超長截斷(保留尾碼)。"""
    s = str(value if value is not None else "").strip()
    return s[-n:].rjust(n) if s else " " * n


def _fmt(kind: str, value, n: int) -> str:
    return _pad_text(value, n) if kind == "X" else _pad_num(value, n)


def build_data_rmk(inst_cod: str, fields: dict) -> str:
    """組 Data_rmk(161 chars):依 HOST_INST_LAYOUTS 佈局依序排版,其餘補空白。"""
    layout = HOST_INST_LAYOUTS.get(inst_cod)
    if layout is None:
        raise ValueError(f"Unknown inst_cod: {inst_cod}")
    buf = _pad_text(inst_cod, 3)
    for name, kind, n in layout:
        buf += _fmt(kind, fields.get(name, ""), n)
    return buf.ljust(DATA_RMK_LEN)[:DATA_RMK_LEN]


def parse_data_rmk(inst_cod: str, data_rmk: str) -> dict:
    """解 Data_rmk → {欄位: 去空白值}(數字欄位 strip 前導空白;文字欄位 strip 尾空白)。"""
    layout = HOST_INST_LAYOUTS.get(inst_cod)
    if layout is None:
        return {}
    out, pos = {}, 3      # 首 3 碼 = inst_cod 本身
    for name, kind, n in layout:
        out[name] = data_rmk[pos:pos + n].strip()
        pos += n
    return out


def build_host_record(inst_cod: str, fields: dict, seq_nos: int,
                      record_nos: int = 1, when: datetime = None) -> str:
    """組完整 192-byte 指令記錄(Record_typ='I';尾端 CR+LF)。"""
    when = when or datetime.now()
    head = ("I"
            + _pad_num(record_nos, 7)
            + _pad_num(seq_nos, 7)
            + _pad_num(when.strftime("%Y%m%d"), 8)
            + _pad_num(when.strftime("%H%M%S"), 6))
    return head + build_data_rmk(inst_cod, fields) + "\r\n"


def build_response_record(resp_cod: str, orig_dat: str, orig_tim: str, orig_seq,
                          msg_cod: str = "", session_cod: str = "") -> str:
    """組 192-byte 回應記錄(Record_typ='R';回映原指令識別 + Msg_cod/Session_cod)。"""
    head = ("R" + _pad_num(1, 7) + _pad_num(0, 7)
            + _pad_num(datetime.now().strftime("%Y%m%d"), 8)
            + _pad_num(datetime.now().strftime("%H%M%S"), 6))
    body = (_pad_text(resp_cod, 3)        # 30~32 回應碼
            + _pad_num(orig_dat, 8)       # 33~40 原指令 Insert_dat
            + _pad_num(orig_tim, 6)       # 41~46 原指令 Insert_tim
            + _pad_num(orig_seq, 7)       # 47~53 原指令 Seq_nos
            + _pad_text(msg_cod, 40)      # 54~93 Msg_cod
            + _pad_text(session_cod, 6))  # 94~99 Session_cod
    return head + body.ljust(DATA_RMK_LEN)[:DATA_RMK_LEN] + "\r\n"


def parse_response_fields(record: str) -> dict:
    """解 192-byte 回應記錄的 Data_rmk → {resp_cod, msg_cod, session_cod, 回映識別}。

    佈局:resp_cod X(3) @1-3、原指令 dat 9(8) @4-11、tim 9(6) @12-17、seq 9(7) @18-24、
    msg_cod X(40) @25-64、session_cod X(6) @65-70(Data_rmk 區段內 1-based)。
    """
    d = record[DATA_RMK_START:DATA_RMK_START + DATA_RMK_LEN]
    return {"resp_cod": d[0:3].strip(),
            "orig_insert_dat": d[3:11].strip(),
            "orig_insert_tim": d[11:17].strip(),
            "orig_seq_nos": d[17:24].strip(),
            "msg_cod": d[24:64].strip(),
            "session_cod": d[64:70].strip()}


def parse_record(record: str) -> dict:
    """解 192-byte 記錄 → dict(含 data_rmk 原文與依 inst_cod 解好的欄位)。

    結構不符(長度≠192/非 CRLF 結尾/Record_typ 非 I,R)→ ValueError(路由層轉 417)。
    """
    if not isinstance(record, str) or len(record) != RECORD_LEN or not record.endswith("\r\n"):
        raise ValueError(f"record length/ending invalid (expect {RECORD_LEN} bytes with CRLF)")
    record_typ = record[0]
    if record_typ not in ("I", "R"):
        raise ValueError(f"Record_typ must be 'I' or 'R', got {record_typ!r}")
    data_rmk = record[DATA_RMK_START:DATA_RMK_START + DATA_RMK_LEN]
    out = {
        "record_typ": record_typ,
        "record_nos": record[1:8].strip(),
        "seq_nos": record[8:15].strip(),
        "insert_dat": record[15:23].strip(),
        "insert_tim": record[23:29].strip(),
        "inst_cod": data_rmk[:3].strip(),
        "data_rmk": data_rmk,
    }
    if record_typ == "I":
        out.update(parse_data_rmk(out["inst_cod"], data_rmk))
    return out
