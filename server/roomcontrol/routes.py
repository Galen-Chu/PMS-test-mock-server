# server/roomcontrol/routes.py
"""🌡️ 房控模組 — mock PMS 側,接收廠商經 A7 公版 XML 介面主動發送的資料。

契約 = sa_docs/sa10_a7_pms_xml.txt(V1.2)+ sa8/sa9 swagger `POST /third-party/import-sync-files`:
- 請求 VendorImportSyncDataRequest { athenaId, hotelCode, thirdPartyCode,
                                   requestDataList: [ { requestBody: <XML 字串>, fileName } ] }
- 回應 200 → [ { procStatus, responseBody: <回應 XML 字串>, fileName } ]
- 錯誤:缺識別/缺 requestBody → 400;XML 壞格式 → 417(對齊 sandbox 既有錯誤信封風格)。

RC0 支援的 ACTION_COD:
- B4 #ROOM_STA#<16位>#(房況變化告知)→ 更新 mock 房控狀態,回 "1112 Set ..."
- A6 ROOM_INF(房間現況住客資訊查詢)→ 依 mock 住客資料回多筆 ROW(ROOM_STA O/S/V)
- A10 RETURN(全部房況回傳查詢)→ 每房一 ROW(CLEAN_STA 由位元 9 推導)

RC2(2026-09-04)支援擴充:
- B4 同族:#RMTEMP#<溫度>#(室溫,回 "1112 Set")、單值族 CLEAN/DND/DOOR/EMG/MAIN_POWER
  (依 sa10 位元語意更新對應房況位元;CLEAN 之 ACTION_STA=位元9 值域 0-4)
- B5 節電器現況(REVE 0300xx4390,無 ACTION_COD):CARD_TYP/CARD_UID/INDOOR_NAME/ACTION_STA(插/拔卡)
  → 更新位元 2 + 記錄卡片資訊;回應無 ACTION_COD tag(對齊 sa10 B5 回應樣本)
- 負面契約:ROOM_NOS 缺欄(除 RETURN)→ 417;B5 缺 CARD_TYP/ACTION_STA → 417;
  未知 ACTION_COD → procStatus=false + RETN-CODE 9999

RC2.5(2026-11-03,sa11 = A7 收到廠商 XML 的 SQL 處理文件)支援擴充:
- 房間主檔 ROOM_MN(room_no → O/V/R/S;E=沙盒模擬內部錯誤房):未知房號 → RETN 9999
  「ROOM not found.」、E 房 → RETN 1001「處理第三方廠商傳送的資料時發生錯誤」(URL 方式須回傳)
- ROOM_INF V/R/S 空房 → 全欄位空值單列(ADVBAL_AMT/CCARD_AMT 為 0;sa11 樣本形狀)
- B4 推送 → PBX_DT 欄位級解碼落庫(KEY_HOUSE…DOOR_STA;位 8=F 斷線三連動:
  SOS=off、RCU_ONLINE=N、CLEAN_ROOM 保舊值);RMTEMP 附 api='RCU';RMUPD_DAT=SYSDATE
- Set 類回應 DESC =「{房號} Set {ACTION_COD}」(sa10 樣本「1112」即房號)
- 單值族 MAIN_POWER 之 ACTION_STA 極性(0=on、1=off)與位元串位 4(1=開)相反 → 寫入前反轉

RC5(2026-11-05)A7 出站接收端 `/third-party/outbound-receive`:沙盒兼扮演廠商側,
  收 A7 出站 XML(QA THIRDPARTY_DT.THIRDPARTY_URL 填此路徑,TRANS_TYP=URL);
  形狀未定義 → GET ?TxnData=(istom 1/4)/POST raw/JSON/multipart 全相容,記錄+回 ACK(RETN 0000),
  回讀 /roomcontrol/internal/outbound-received。

另提供沙盒內部回讀端點(LOCAL 閉環驗證用,前例:parking /parking/internal/whitelist)
與自助端點:POST /roomcontrol/internal/rooms(登錄房間)、POST /roomcontrol/internal/reset(還原種子)。
"""
import base64
import copy
import logging
from datetime import datetime
from urllib.parse import parse_qsl

from flask import Blueprint, Response, request, jsonify

from .vendors.vendor_A7_XML import (
    build_rowset_xml, parse_rowset_xml,
    build_ack_response_xml, build_error_response_xml,
    DEFAULT_STATUS_BITS, MSG_DONE, B4_SINGLE_BIT_INDEX, is_b4_action, set_status_bit,
    decode_status_bits, action_dat_now,
)
from .vendors.vendor_IPTV import (CONF_ACTIONS, OUTBOUND_REVE_PREFIX,
                                   PARAM_DISPLAY_NAME, PARAM_USER_DEFINED,
                                   reve_outbound)

roomcontrol_bp = Blueprint('roomcontrol', __name__)

logger = logging.getLogger("RoomControlSandbox")
logger.setLevel(logging.INFO)

# ---- 沙盒記憶體資料庫 ----------------------------------------------------
# 房控現況(room_no → 最後一次 B4 告知的狀態)
mock_roomcontrol_state = {}

# 房間主檔(sa11 ROOM_MN:O住人/V空房/R修理/S參觀;E=沙盒模擬內部錯誤房,RETN 1001)
mock_room_mn = {
    "2403": "O",                                            # 種子住客房(兩位住客,見 mock_room_guest_db)
    "2404": "V", "2405": "R", "2406": "S",                  # V/R/S 三態樣本房(ROOM_INF 空房形狀)
    "2501": "V", "2601": "V", "2602": "V",                  # 離線測試用房
    "2701": "V", "2702": "V", "2703": "V", "2704": "V", "2705": "V",
    "2407": "V",                                            # CKI 樣本房:預訂未入住(住客資料在、ROOM_MN=V)
    "2408": "V",                                            # RMC 換房目標房(sa10 A3:舊房清空、新房住人)
    "9901": "E",                                            # 模擬內部錯誤房(RETN 1001)
}

# 房間現況住客資料(ROOM_INF 回應來源;種子 = sa10 A6 回應樣本,房號 2403 兩位住客)
mock_room_guest_db = {
    "2403": [
        {"ROOM_SER": "1", "CI_SER": "200605120002001", "ALT_NAM": "張梅稜",
         "SALUTE_NAM": "小姐", "SALUTE_TYP": "1", "FIRST_NAM": "梅稜", "LAST_NAM": "張",
         "GUEST_STA": "O", "CI_DAT": "2026/09/03", "CI_TIM": "18:26:35", "ECO_DAT": "2026/09/10",
         "TEL_NOS": "0922123451", "BIRTH_DAT": "1997/01/01",
         "ADVBAL_AMT": "-3400", "CCARD_AMT": "0", "LANG_COD": "zh_TW", "LANG_NAM": "中文",
         "VIP_STA": "1"},
        {"ROOM_SER": "2", "CI_SER": "200605120003001", "ALT_NAM": "張XX",
         "SALUTE_NAM": "先生", "SALUTE_TYP": "1",
         "GUEST_STA": "O", "CI_DAT": "2026/09/03", "CI_TIM": "18:26:35", "ECO_DAT": "2026/09/10",
         "TEL_NOS": "0922175688", "BIRTH_DAT": "1997/01/01",
         "ADVBAL_AMT": "-1200", "CCARD_AMT": "0", "LANG_COD": "zh_TW", "LANG_NAM": "中文",
         "VIP_STA": "1"},
    ],
    # 2407:CKI 樣本住客(預訂未入住)——sa11 CKI SQL 全欄位來源(GROUP_NOS=訂房名稱/團號)
    "2407": [
        {"ROOM_SER": "1", "CI_SER": "202611040002001", "ALT_NAM": "王小明",
         "SALUTE_NAM": "先生", "SALUTE_TYP": "1", "FIRST_NAM": "小明", "LAST_NAM": "王",
         "GUEST_STA": "O", "CI_DAT": "2026/11/04", "CI_TIM": "14:00:12", "ECO_DAT": "2026/11/06",
         "TEL_NOS": "0912345678", "BIRTH_DAT": "1990/05/15",
         "ADVBAL_AMT": "0", "CCARD_AMT": "0", "LANG_COD": "zh_TW", "LANG_NAM": "中文",
         "VIP_STA": "2", "GROUP_NOS": "GP2026A", "INFO_ISGROUP": "Y",
         "INFO_REMARK": "雲朗年度貴賓團"},
    ],
}

# 第三方廠商設定明細檔(sa11 THIRDPARTY_DT_CONF;PK 含 THIRDPARTY_ACTION_COD):
# {THIRDPARTY_COD: {ACTION_COD: {PARAM_COD: PARAM_VAL}}}(QA DB 70 已見 CKI/RMC/COX/ROOM_INF)
# PARAM_COD 與 QA DB 逐字一致(guest.display.name / user.defined.display.name)。
# 種子為空 = 無參數設定 → 依預設值處理(guest.display.name 預設 ALT_NAM)
mock_thirdparty_dt_conf = {}
DISPLAY_NAME_CHOICES = ("GROUP_NOS", "ROOM_NOS", "LAST_NAM", "FIRST_NAM", "ALT_NAM", "USER_DEFINED")
DEFAULT_DISPLAY_NAME = "ALT_NAM"   # sa11 參數表預設值


def resolve_display_name(params, guest, room_no):
    """sa11 guest_display_name:傳送廠商之住客姓名欄內容解析。

    - 無參數設定/讀取無資料/值非合法選項 → 預設 ALT_NAM
    - USER_DEFINED → user.defined.display.name 內容如實傳送(無值 → 廠商收無資料)
    - 其餘選項 → 住客/訂房對應欄位(GROUP_NOS=訂房名稱團號、ROOM_NOS=房號)
    """
    params = params or {}
    choice = params.get(PARAM_DISPLAY_NAME) or DEFAULT_DISPLAY_NAME
    if choice not in DISPLAY_NAME_CHOICES:
        choice = DEFAULT_DISPLAY_NAME
    if choice == "USER_DEFINED":
        return str(params.get(PARAM_USER_DEFINED) or "")
    src = {"GROUP_NOS": guest.get("GROUP_NOS", ""), "ROOM_NOS": str(room_no),
           "LAST_NAM": guest.get("LAST_NAM", ""), "FIRST_NAM": guest.get("FIRST_NAM", ""),
           "ALT_NAM": guest.get("ALT_NAM", "")}
    return str(src.get(choice) or "")


# 種子快照(/roomcontrol/internal/reset 還原用)
_SEED_ROOM_MN = dict(mock_room_mn)
_SEED_GUESTS = copy.deepcopy(mock_room_guest_db)
_SEED_CONF = {}


def _room_error_xml(reve_code, action_cod, room):
    """房間層錯誤信封(sa11):未知房號 → 9999 ROOM not found;E 模擬房 → 1001 內部錯誤。"""
    sta = mock_room_mn.get(room)
    if sta is None:
        return build_error_response_xml(reve_code, action_cod, "9999", "ROOM not found.")
    if sta == "E":
        return build_error_response_xml(reve_code, action_cod, "1001",
                                        "處理第三方廠商傳送的資料時發生錯誤")
    return None


def _retn_tail():
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    return {"ACTION_DAT": now, "RETN-CODE": "0000",
            "RETN-CODE-DESC": MSG_DONE, "MSG-ID": "0000", "MSG-DESC": MSG_DONE}


def _room_inf_vacant_row(room_nos, reve_code, room_sta):
    """V/R/S 空房回應列(sa11 樣本:住客欄全空值、ADVBAL_AMT/CCARD_AMT 為 0)。"""
    return {"SEND-CODE": reve_code, "ACTION_COD": "ROOM_INF", "ROOM_NOS": room_nos,
            "ROOM_SER": "", "ROOM_STA": room_sta, "CI_SER": "", "ALT_NAM": "",
            "SALUTE_NAM": "", "SALUTE_TYP": "", "FIRST_NAM": "", "LAST_NAM": "",
            "GUEST_STA": "", "CI_DAT": "", "CI_TIM": "", "ECO_DAT": "", "TEL_NOS": "",
            "BIRTH_DAT": "", "ADVBAL_AMT": "0", "CCARD_AMT": "0", "LANG_COD": "",
            "LANG_NAM": "", "VIP_STA": "", **_retn_tail()}


def _room_inf_rows(room_nos, reve_code, tp_code=""):
    """組 ROOM_INF 回應 ROW(依 ROOM_MN:O → 每住客一 ROW;V/R/S → 全空欄單列)。

    RC4b:ALT_NAM 依「該廠商 ROOM_INF action」的 THIRDPARTY_DT_CONF 參數解析
    (QA DB 截圖:ROOM_INF 亦掛 guest.display.name;FIRST_NAM/LAST_NAM 維持原值)。
    呼叫端已先擋未知房號(9999)與 E 房(1001);防禦:O 房無住客種子 → O 空欄單列。
    """
    sta = mock_room_mn.get(room_nos, "V")
    guests = mock_room_guest_db.get(room_nos)
    if sta != "O" or not guests:
        return [_room_inf_vacant_row(room_nos, reve_code, sta)]
    conf = (mock_thirdparty_dt_conf.get(tp_code) or {}).get("ROOM_INF") or {}
    rows = []
    for gst in guests:
        row = {**gst, "ALT_NAM": resolve_display_name(conf, gst, room_nos)}
        rows.append({"SEND-CODE": reve_code, "ACTION_COD": "ROOM_INF", "ROOM_NOS": room_nos,
                     "ROOM_STA": "O", **row, **_retn_tail()})
    return rows


def _clean_sta_from_bits(bits) -> str:
    """房況位元串第 9 位(房間清潔)→ A10 CLEAN_STA 值域(sa10:0=清潔完成→C、3=待巡房→S、其餘→D)。"""
    try:
        c = int(str(bits)[8])
    except (ValueError, IndexError):
        return "C"
    return {0: "C", 3: "S"}.get(c, "D")


def _return_rows(reve_code):
    """組 A10 RETURN 回應:每房一 ROW(ROOM_STA O住人/V空房;CLEAN_STA 由位元串第 9 位推導)。"""
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    tail = {"ACTION_DAT": now, "RETN-CODE": "0000",
            "RETN-CODE-DESC": MSG_DONE, "MSG-ID": "0000", "MSG-DESC": MSG_DONE}
    rooms = sorted(r for r, sta in mock_room_mn.items() if sta != "E")   # E 模擬房不入回報
    rows = []
    for room in rooms:
        state = mock_roomcontrol_state.get(room) or {}
        rows.append({"SEND-CODE": reve_code, "ACTION_COD": "RETURN", "ROOM_NOS": room,
                     "ROOM_STA": mock_room_mn.get(room, "V"),
                     "CLEAN_STA": _clean_sta_from_bits(state.get("status_bits", "")),
                     **tail})
    return rows


def _refresh_pbx_dt(state):
    """RC2.5:位元串 → PBX_DT 欄位級解碼(sa11 對照表;F 斷線時 CLEAN_ROOM 保舊值)。"""
    prev = (state.get("pbx_dt") or {}).get("CLEAN_ROOM", "0")
    state["pbx_dt"] = decode_status_bits(state.get("status_bits", DEFAULT_STATUS_BITS), prev)


def _apply_b4_push(row):
    """B4 房況變化告知 → 更新 mock 房控狀態,回 (ack_xml, ok)。

    RC2(2026-09-04):單值族 action 依 sa10 位元語意更新對應房況位元
    (CLEAN→位9、DND→位10、DOOR→位11、EMG→位8、MAIN_POWER→位4);
    回應 DESC 依 sa10 B4 回應樣本——Set 類(#...#)為 "1112 Set ...",單值 action 為 MSG_DONE。
    """
    room = row.get("ROOM_NOS", "")
    action_cod = row.get("ACTION_COD", "")
    reve = row.get("REVE-CODE", "")
    state = mock_roomcontrol_state.setdefault(room, {"status_bits": DEFAULT_STATUS_BITS})
    state["updated_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    state["last_action_sta"] = row.get("ACTION_STA", "")

    if action_cod.startswith("#ROOM_STA#"):
        bits = action_cod.split("#")[2]      # "#ROOM_STA#<bits>#" → ['', 'ROOM_STA', bits, '']
        state["status_bits"] = bits
        desc = f"{room} Set {action_cod}"
    elif action_cod.startswith("#RMTEMP#"):
        state["temperature"] = action_cod.split("#")[2]
        state["api"] = "RCU"                 # sa11:RMTEMP 更新時附 api='RCU'
        desc = f"{room} Set {action_cod}"
    else:
        # 單值族 action(ACTION_STA 帶狀態值;CLEAN 為 0-4,餘為 0/1)
        # sa11 極性差:第一種 MAIN_POWER ACTION_STA 0=on、1=off,與位元串位 4(1=開)相反 → 反轉
        sta = row.get("ACTION_STA", "1")
        bit_val = ("1" if sta == "0" else "0") if action_cod == "MAIN_POWER" else sta
        state["status_bits"] = set_status_bit(state.get("status_bits", DEFAULT_STATUS_BITS),
                                              B4_SINGLE_BIT_INDEX[action_cod], bit_val)
        state["last_action_cod"] = action_cod
        desc = MSG_DONE
    _refresh_pbx_dt(state)                   # RC2.5:位元串 → PBX_DT 欄位級解碼落庫
    state["rmupd_dat"] = state["updated_at"]  # sa11:RMUPD_DAT = SYSDATE
    return build_ack_response_xml(reve, action_cod, desc), True


def _apply_keybox_push(row):
    """B5 節電器現況(插/拔卡)→ 更新位元 2(Keybox 1=插卡 0=拔卡)+ 記錄卡片資訊,回 (ack_xml, ok)。

    sa10 B5 回應契約無 ACTION_COD 欄位(build_rowset_xml 對 None 值省略 tag)。
    """
    room = row.get("ROOM_NOS", "")
    reve = row.get("REVE-CODE", "")
    sta = row.get("ACTION_STA", "1")
    state = mock_roomcontrol_state.setdefault(room, {"status_bits": DEFAULT_STATUS_BITS})
    state["updated_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    state["status_bits"] = set_status_bit(state.get("status_bits", DEFAULT_STATUS_BITS), 1, sta)
    state["keybox"] = {"card_typ": row.get("CARD_TYP", ""), "card_uid": row.get("CARD_UID", ""),
                       "indoor_name": row.get("INDOOR_NAME", ""), "action_sta": sta}
    _refresh_pbx_dt(state)
    state["rmupd_dat"] = state["updated_at"]
    return build_ack_response_xml(reve, None), True


@roomcontrol_bp.route('/third-party/import-sync-files', methods=['POST'])
def import_sync_files():
    """處理廠商主動發送的資料(請求 C001.xml,回傳 C001.xml)。"""
    body = request.get_json(silent=True) or {}
    # sa10:athena / hotel / thirdParty 三元組必填(值由德安提供;沙盒記錄不驗值)
    missing = [k for k in ("athenaId", "hotelCode", "thirdPartyCode") if not body.get(k)]
    if missing:
        return jsonify({"code": "400", "message": f"Missing identity: {', '.join(missing)}"}), 400
    data_list = body.get("requestDataList") or []
    if not data_list:
        return jsonify({"code": "400", "message": "requestDataList is required"}), 400

    results = []
    for item in data_list:
        xml_str = item.get("requestBody")
        file_name = item.get("fileName", "C001.xml")
        if not xml_str:
            return jsonify({"code": "400", "message": "requestDataList[].requestBody is required"}), 400
        try:
            rows = parse_rowset_xml(xml_str)
        except Exception as e:
            logger.warning(f"[房控沙盒] XML 解析失敗({file_name}): {e}")
            return jsonify({"code": "417", "message": f"XML parse error: {e}"}), 417

        row = rows[0]
        action_cod = row.get("ACTION_COD", "")
        reve = row.get("REVE-CODE", "")
        room = row.get("ROOM_NOS", "")
        logger.info(f"📥 [房控沙盒] 匯入 {file_name} ➔ REVE-CODE:【{reve}】ACTION_COD:【{action_cod}】房號:【{room}】")

        # ROOM_NOS 必填(A10 RETURN 查全房除外——契約本就無房號欄)
        if not room and action_cod != "RETURN":
            return jsonify({"code": "417", "message": "ROOM_NOS is required"}), 417
        # RC2.5 房間層守衛(sa11:先檢查房間——未知房號 9999 / E 模擬房 1001;B5 無 ACTION_COD 不回映)
        err_xml = (_room_error_xml(reve, None if reve.endswith("4390") else action_cod, room)
                   if room else None)
        if err_xml is not None:
            resp_xml, proc = err_xml, False
        elif reve.endswith("4390"):
            # B5 節電器現況:訊息無 ACTION_COD;sa10 標 * 必填 = REVE/ROOM_NOS/CARD_TYP/ACTION_STA/ACTION_DAT
            if not row.get("CARD_TYP") or row.get("ACTION_STA", "") == "":
                return jsonify({"code": "417",
                                "message": "CARD_TYP and ACTION_STA are required for B5"}), 417
            resp_xml, proc = _apply_keybox_push(row)
        elif action_cod == "ROOM_INF":
            resp_xml = build_rowset_xml(_room_inf_rows(room, reve, str(body.get("thirdPartyCode") or "")))
            proc = True
        elif action_cod == "RETURN":
            resp_xml = build_rowset_xml(_return_rows(reve))
            proc = True
        elif is_b4_action(action_cod):
            resp_xml, proc = _apply_b4_push(row)
        else:
            # 未知 ACTION_COD → sa10:RETN 非 0000 = 資料處理異常;procStatus=false
            resp_xml = build_error_response_xml(reve, action_cod, "9999", f"Unknown ACTION_COD: {action_cod}")
            proc = False
        results.append({"procStatus": proc, "responseBody": resp_xml, "fileName": file_name})

    return jsonify(results), 200


# ---- A7 出站接收端(PMS→廠商)---------------------------------------------
# sa10:「廠商須提供一個 URL,接收德安傳送的入住、退房、換房資訊」——沙盒兼扮演廠商側
# (如 IPTV 廠商 70)收 A7 出站 XML(CKI/CKO/RMC/CIX/COX…),記錄供閉環驗證。
# 出站傳輸形狀 sa10 未定義 → GET ?TxnData=(istom 1/4)/POST raw/JSON/multipart 全形狀相容。
outbound_received = []


def _extract_push_xml():
    """從任意傳輸形狀抽取 A7 出站 XML 字串;抽不到回 None(仍記錄原樣供稽核)。

    - GET 查詢參數 TxnData(istom=1 URLEncode / 4 Base64;sa10 呼叫德安同款參數)
    - POST JSON:requestBody 或 requestDataList[].requestBody(import-sync-files 同款)
    - POST multipart:任一 file 內容;POST form:TxnData / requestBody 欄位
    - 其餘:raw body(urlencoded 型 body 再解一層 TxnData)
    """
    txn = request.args.get("TxnData")
    if txn:
        if request.args.get("istom") == "4":
            try:
                txn = base64.b64decode(txn).decode("utf-8", "replace")
            except Exception:
                pass
        return txn.strip() or None
    if request.is_json:
        body = request.get_json(silent=True) or {}
        data_list = body.get("requestDataList") or []
        return (body.get("requestBody")
                or (data_list[0].get("requestBody") if data_list else None))
    if request.files:
        for f in request.files.values():
            raw = f.read().decode("utf-8", "replace").strip()
            if raw:
                return raw
    form = request.form.get("TxnData") or request.form.get("requestBody")
    if form:
        return form.strip()
    raw = (request.get_data(cache=True, as_text=True) or "").strip()
    if raw and not raw.startswith("<"):
        for k, v in parse_qsl(raw):
            if k == "TxnData" and v.strip():
                return v.strip()
    return raw or None


def record_outbound_and_ack():
    """A7 出站共通處理:抽取 XML → 記錄 outbound_received → 回 sa10 ACK XML 響應。"""
    raw = _extract_push_xml()
    entry = {"received_at": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
             "method": request.method, "path": request.path,
             "args": {k: v for k, v in request.args.items() if k != "TxnData"},
             "raw_xml": raw, "fields": {}, "parse_ok": False}
    if raw:
        try:
            entry["fields"] = parse_rowset_xml(raw)[0]
            entry["parse_ok"] = True
        except Exception as e:
            entry["parse_error"] = str(e)
    outbound_received.append(entry)
    f = entry["fields"]
    if entry["parse_ok"]:
        logger.info(f"📤 [房控沙盒] A7 出站接收 ➔ REVE-CODE:【{f.get('REVE-CODE', '')}】"
                    f"ACTION_COD:【{f.get('ACTION_COD', '')}】房號:【{f.get('ROOM_NOS', '')}】")
        xml = build_ack_response_xml(f.get("REVE-CODE", ""), f.get("ACTION_COD", ""))
    else:
        logger.warning(f"📤 [房控沙盒] A7 出站接收未解析({entry.get('parse_error', '空內容')})")
        xml = build_error_response_xml("", "", "9999",
                                       f"A7 outbound parse error: {entry.get('parse_error', 'empty payload')}")
    return Response(xml, mimetype="application/xml; charset=utf-8")


def intercept_a7_outbound():
    """全域 TxnData 攔截(main.py 掛 app.before_request;2026-11-09 QA 實測補)。

    實測:A7 出站不用 THIRDPARTY_URL 的路徑部分,一律 GET host 根路徑 ?TxnData=<XML>
    (不帶 istom/athena… 參數)→ 原本落在 SPA index.html(200 HTML,A7 拿不到 XML ACK)。
    內部端點/UI 皆不用 TxnData 查詢參數,零誤傷。
    """
    if "TxnData" in request.args:
        return record_outbound_and_ack()
    return None


@roomcontrol_bp.route('/third-party/outbound-receive', methods=['GET', 'POST'],
                      defaults={'subpath': ''})
@roomcontrol_bp.route('/third-party/outbound-receive/<path:subpath>',
                      methods=['GET', 'POST'])
def outbound_receive(subpath):
    """A7 出站接收端:QA THIRDPARTY_DT.THIRDPARTY_URL(TRANS_TYP=URL)填入本路徑。

    沙盒 = 廠商側:收 A7 於 C/I、C/O、換房等時機推送的出站 XML,記入 outbound_received;
    回 sa10 ACK XML(SEND-CODE 回映 REVE、RETN 0000);帶任意後綴路徑亦收(保險:A7 自行拼子路徑)。
    2026-11-09 實測:A7 只打根路徑 → 真正入口是 main.py 的 intercept_a7_outbound 閘門。
    """
    return record_outbound_and_ack()


@roomcontrol_bp.route('/roomcontrol/internal/outbound-received', methods=['GET'])
def get_outbound_received():
    """A7 出站接收記錄回讀(LOCAL 驗證用;?clear=1 讀後清空)。"""
    out = list(outbound_received)
    if request.args.get("clear"):
        outbound_received.clear()
    return jsonify({"count": len(out), "received": out})


@roomcontrol_bp.route('/roomcontrol/internal/state', methods=['GET'])
def get_internal_state():
    """沙盒內部回讀(LOCAL 閉環驗證用;REAL 環境無此端點,runner 會跳過回讀斷言)。

    RC2.5:加 room_mn(房間主檔);room_control_state 每房另含 pbx_dt(欄位級解碼視圖)。
    """
    return jsonify({"room_control_state": mock_roomcontrol_state,
                    "room_guest_rooms": sorted(mock_room_guest_db.keys()),
                    "room_mn": dict(mock_room_mn),
                    "thirdparty_dt_conf": {tp: {a: dict(p) for a, p in acts.items()}
                                           for tp, acts in mock_thirdparty_dt_conf.items()}}), 200


@roomcontrol_bp.route('/roomcontrol/internal/rooms', methods=['POST'])
def add_rooms():
    """沙盒自助:登錄/更新房間主檔(LOCAL 動態房號閉環用;前例:/pbx/internal/reset)。

    body = {"rooms": {"91234": "V", ...}};ROOM_STA 限 O/V/R/S/E(E=模擬內部錯誤房)。
    """
    body = request.get_json(silent=True) or {}
    rooms = body.get("rooms")
    if not isinstance(rooms, dict) or not rooms:
        return jsonify({"code": "400", "message": "rooms is required"}), 400
    for r, sta in rooms.items():
        if sta not in ("O", "V", "R", "S", "E"):
            return jsonify({"code": "400",
                            "message": f"invalid ROOM_STA {sta!r} for {r}"}), 400
    mock_room_mn.update(rooms)
    return jsonify({"room_mn": dict(mock_room_mn)}), 200


@roomcontrol_bp.route('/roomcontrol/internal/reset', methods=['POST'])
def reset_state():
    """沙盒自助:還原種子(房控狀態清空、房間主檔與住客種子還原)。"""
    mock_roomcontrol_state.clear()
    mock_room_mn.clear()
    mock_room_mn.update(_SEED_ROOM_MN)
    mock_room_guest_db.clear()
    mock_room_guest_db.update(copy.deepcopy(_SEED_GUESTS))
    mock_thirdparty_dt_conf.clear()
    mock_thirdparty_dt_conf.update(copy.deepcopy(_SEED_CONF))
    return jsonify({"ok": True}), 200


# ---- sa11 THIRDPARTY_DT_CONF + PMS→廠商出站(雲朗 IPTV=70;RC4a 2026-11-04 / RC4b 補齊 action_cod) --

@roomcontrol_bp.route('/roomcontrol/internal/thirdparty-conf', methods=['GET', 'POST'])
def thirdparty_conf():
    """第三方廠商參數設定(sa11 THIRDPARTY_DT_CONF 模擬;PK 含 ACTION_COD)。

    POST body = {"third_party_code": "70", "action_cod": "RMC",
                 "params": {"guest.display.name": "USER_DEFINED",
                            "user.defined.display.name": "貴賓"}}
    action_cod 限 CONF_ACTIONS(QA DB 70 已見 CKI/RMC/COX/ROOM_INF);參數鍵 = QA PARAM_COD。
    值 None/空字串 = 清除該參數(回到無參數設定 → 預設值);guest.display.name 限合法選項。
    """
    if request.method == "GET":
        return jsonify({"thirdparty_dt_conf":
                        {tp: {a: dict(p) for a, p in acts.items()}
                         for tp, acts in mock_thirdparty_dt_conf.items()}}), 200
    body = request.get_json(silent=True) or {}
    tp = str(body.get("third_party_code") or "")
    action = str(body.get("action_cod") or "CKI").upper()
    params = body.get("params")
    if not tp or not isinstance(params, dict):
        return jsonify({"code": "400",
                        "message": "third_party_code and params are required"}), 400
    if action not in CONF_ACTIONS:
        return jsonify({"code": "400",
                        "message": f"action_cod must be one of {CONF_ACTIONS}"}), 400
    slot = mock_thirdparty_dt_conf.setdefault(tp, {}).setdefault(action, {})
    for k, v in params.items():
        if v is None or v == "":
            slot.pop(k, None)                     # 清除 → 無參數設定
            continue
        v = str(v)
        if k == PARAM_DISPLAY_NAME and v not in DISPLAY_NAME_CHOICES:
            return jsonify({"code": "400",
                            "message": f"{PARAM_DISPLAY_NAME} must be one of {DISPLAY_NAME_CHOICES}"}), 400
        if len(v) > 2000:                          # sa11 PARAM_VAL NVARCHAR2(2000)
            return jsonify({"code": "400", "message": f"{k} exceeds 2000 chars"}), 400
        slot[k] = v
    return jsonify({"third_party_code": tp, "action_cod": action, "params": dict(slot)}), 200


@roomcontrol_bp.route('/roomcontrol/internal/outbound', methods=['POST'])
def trigger_outbound():
    """模擬 A7 出站 XML 推送廠商(sa10 A1 CKI / A2 CKO / A3 RMC / A4 CIX / A5 COX;沙盒觸發版)。

    body = {"action_cod": "CKI", "room_no": "2407", "third_party_code": "70"}
           RMC 另帶 "to_room_no": "2408"(換房:舊房清空變空房、新房變住人)
    行為:取該房最小 CI_SER 住客,依「該廠商×該 action」THIRDPARTY_DT_CONF 解析
    住客姓名欄 → 組出站 XML(REVE=訊息樣板+廠商代號);CKI/COX 房間轉 O、RMC 搬移住客、
    CKO(退房)/CIX(C.I還原)房間轉 V(出站僅四欄、無住客姓名欄,display_name=None)。
    回傳 {"responseBody": <將送達廠商的 XML>, "display_name": <解析後姓名欄>, "room_sta"}。
    """
    body = request.get_json(silent=True) or {}
    action = str(body.get("action_cod") or "CKI").upper()
    room = str(body.get("room_no") or "")
    to_room = str(body.get("to_room_no") or "")
    tp = str(body.get("third_party_code") or "70")
    if action not in OUTBOUND_REVE_PREFIX:
        return jsonify({"code": "400",
                        "message": f"action_cod must be one of {tuple(OUTBOUND_REVE_PREFIX)}"}), 400
    if not room:
        return jsonify({"code": "400", "message": "room_no is required"}), 400
    if action == "RMC" and not to_room:
        return jsonify({"code": "400", "message": "to_room_no is required for RMC"}), 400
    sta = mock_room_mn.get(room)
    if sta is None:
        return jsonify({"code": "9999", "message": "ROOM not found."}), 404
    if sta == "E":
        return jsonify({"code": "1001", "message": "處理第三方廠商傳送的資料時發生錯誤"}), 500
    if action == "RMC":
        to_sta = mock_room_mn.get(to_room)
        if to_sta is None:
            return jsonify({"code": "9999", "message": f"ROOM not found: {to_room}"}), 404
        if to_sta == "E":
            return jsonify({"code": "1001", "message": "處理第三方廠商傳送的資料時發生錯誤"}), 500
    guests = mock_room_guest_db.get(room)
    if not guests:
        return jsonify({"code": "400", "message": f"no guest data for room {room}"}), 400
    # sa11:取得第一個 & 最小入住的 CI_SER 帳務編號(一房間只送一筆住客)
    guest = min(guests, key=lambda g: str(g.get("CI_SER", "")))
    conf = (mock_thirdparty_dt_conf.get(tp) or {}).get(action) or {}
    display_name = None if action in ("CKO", "CIX") else resolve_display_name(conf, guest, room)
    if action in ("CKO", "CIX"):
        # sa10 A2/A4:退房/C.I還原出站僅 REVE/ACTION_COD/ROOM_NOS/ACTION_DAT 四欄;
        # 無住客姓名欄 → 不適用顯示名稱參數(QA 參數表僅 CKI/RMC/COX/ROOM_INF);
        # 房間轉空房(CIX 客製重點「不改髒房」,mock 房況值域無髒房 → 同回 V)
        if sta != "O":
            return jsonify({"code": "400",
                            "message": f"room {room} is not check-in (sta={sta}); "
                                       f"{action} requires an in-house room"}), 400
        mock_room_mn[room] = "V"
        room_sta = mock_room_mn[room]
        row = {"REVE-CODE": reve_outbound(action, tp), "ACTION_COD": action,
               "ROOM_NOS": room, "ACTION_DAT": action_dat_now()}
    elif action == "RMC":
        # sa10 A3:換房——舊房清空變未入住、新房住人;廠商須將舊房資訊改設到新房
        mock_room_guest_db[to_room] = mock_room_guest_db.pop(room)
        mock_room_mn[room] = "V"
        mock_room_mn[to_room] = "O"
        room_sta = {"old": mock_room_mn[room], "new": mock_room_mn[to_room]}
        row = {
            "REVE-CODE": reve_outbound(action, tp), "ACTION_COD": action,
            "OROOM_NOS": room, "NROOM_NOS": to_room,
            "ROOM_SER": guest.get("ROOM_SER", "1"), "CI_SER": guest.get("CI_SER", ""),
            "ALT_NAM": display_name,                # sa11:住客姓名欄依顯示名稱參數解析
            "SALUTE_NAM": guest.get("SALUTE_NAM", ""), "SALUTE_TYP": guest.get("SALUTE_TYP", ""),
            "CI_DAT": guest.get("CI_DAT", ""), "ECO_DAT": guest.get("ECO_DAT", ""),
            "LANG_COD": guest.get("LANG_COD", ""), "LANG_NAM": guest.get("LANG_NAM", ""),
            "VIP_STA": guest.get("VIP_STA", ""), "CI_TIM": guest.get("CI_TIM", ""),
            "ACTION_DAT": action_dat_now(),
        }
    else:
        # CKI(C/I)與 COX(C/O 還原)欄位形狀同 sa10 A1/A5 樣本;房間主檔皆為住人
        mock_room_mn[room] = "O"
        room_sta = mock_room_mn[room]
        row = {
            "REVE-CODE": reve_outbound(action, tp), "ACTION_COD": action, "ROOM_NOS": room,
            "ROOM_SER": guest.get("ROOM_SER", "1"), "CI_SER": guest.get("CI_SER", ""),
            "ALT_NAM": display_name,                # sa11:住客姓名欄依顯示名稱參數解析
            "SALUTE_NAM": guest.get("SALUTE_NAM", ""), "SALUTE_TYP": guest.get("SALUTE_TYP", ""),
            "FIRST_NAM": guest.get("FIRST_NAM", ""), "LAST_NAM": guest.get("LAST_NAM", ""),
            "CI_DAT": guest.get("CI_DAT", ""), "ECO_DAT": guest.get("ECO_DAT", ""),
            "LANG_COD": guest.get("LANG_COD", ""), "LANG_NAM": guest.get("LANG_NAM", ""),
            "VIP_STA": guest.get("VIP_STA", ""), "CI_TIM": guest.get("CI_TIM", ""),
            "INFO_ISGROUP": guest.get("INFO_ISGROUP", "N"),
            "INFO_REMARK": guest.get("INFO_REMARK", ""),
            "ACTION_DAT": action_dat_now(),
        }
    xml_str = build_rowset_xml(row)
    logger.info(f"📤 [房控沙盒] {action} 出站 ➔ 廠商{tp} 房號:{room}"
                + (f"→{to_room}" if action == "RMC" else "")
                + (f" 姓名欄:{display_name!r}(參數解析)" if display_name is not None
                   else " (sa10 A2/A4 四欄出站,無住客姓名欄)"))
    return jsonify({"procStatus": True, "responseBody": xml_str, "action_cod": action,
                    "display_name": display_name, "room_sta": room_sta,
                    "conf": dict(conf)}), 200
