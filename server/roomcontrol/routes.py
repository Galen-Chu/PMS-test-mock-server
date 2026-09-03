# server/roomcontrol/routes.py
"""🌡️ 房控模組 — mock PMS 側,接收廠商經 A7 公版 XML 介面主動發送的資料。

契約 = sa_docs/sa10_a7_pms_xml.txt(V1.2)+ sa8/sa9 swagger `POST /third-party/import-sync-files`:
- 請求 VendorImportSyncDataRequest { athenaId, hotelCode, thirdPartyCode,
                                   requestDataList: [ { requestBody: <XML 字串>, fileName } ] }
- 回應 200 → [ { procStatus, responseBody: <回應 XML 字串>, fileName } ]
- 錯誤:缺識別/缺 requestBody → 400;XML 壞格式 → 417(對齊 sandbox 既有錯誤信封風格)。

RC0 支援的 ACTION_COD:
- B4 #ROOM_STA#<16位>#(房況變化告知)→ 更新 mock 房控狀態,回 "1112 Set ..."
  (同族 CLEAN/DND/RMTEMP 等寬鬆收下、記錄狀態,完整支援排 RC2)
- A6 ROOM_INF(房間現況住客資訊查詢)→ 依 mock 住客資料回多筆 ROW(ROOM_STA O/S/V)

另提供沙盒內部回讀端點(LOCAL 閉環驗證用,前例:parking /parking/internal/whitelist)。
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify

from .vendors.vendor_A7_XML import (
    build_rowset_xml, parse_rowset_xml,
    build_ack_response_xml, build_error_response_xml,
    DEFAULT_STATUS_BITS, MSG_DONE,
)

roomcontrol_bp = Blueprint('roomcontrol', __name__)

logger = logging.getLogger("RoomControlSandbox")
logger.setLevel(logging.INFO)

# ---- 沙盒記憶體資料庫 ----------------------------------------------------
# 房控現況(room_no → 最後一次 B4 告知的狀態)
mock_roomcontrol_state = {}

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
}


def _room_inf_rows(room_nos):
    """組 ROOM_INF 回應 ROW(有住客 → 每人一 ROW / ROOM_STA=O;查無 → 單 ROW / ROOM_STA=V)。"""
    guests = mock_room_guest_db.get(room_nos)
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    tail = {"ACTION_DAT": now, "RETN-CODE": "0000",
            "RETN-CODE-DESC": MSG_DONE + ".", "MSG-ID": "0000", "MSG-DESC": MSG_DONE + "."}
    if not guests:
        return [{"SEND-CODE": "0300TT1090", "ACTION_COD": "ROOM_INF", "ROOM_NOS": room_nos,
                 "ROOM_STA": "V", **tail}]
    rows = []
    for gst in guests:
        rows.append({"SEND-CODE": "0300TT1090", "ACTION_COD": "ROOM_INF", "ROOM_NOS": room_nos,
                     "ROOM_STA": "O", **gst, **tail})
    return rows


def _apply_b4_push(row):
    """B4 房況變化告知 → 更新 mock 房控狀態,回 (ack_xml, ok)。"""
    room = row.get("ROOM_NOS", "")
    action_cod = row.get("ACTION_COD", "")
    reve = row.get("REVE-CODE", "")
    state = mock_roomcontrol_state.setdefault(room, {"status_bits": DEFAULT_STATUS_BITS})
    state["updated_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    state["last_action_sta"] = row.get("ACTION_STA", "")

    if action_cod.startswith("#ROOM_STA#"):
        bits = action_cod.split("#")[2]      # "#ROOM_STA#<bits>#" → ['', 'ROOM_STA', bits, '']
        state["status_bits"] = bits
        desc = f"1112 Set {action_cod}"
    elif action_cod.startswith("#RMTEMP#"):
        state["temperature"] = action_cod.split("#")[2]
        desc = f"1112 Set {action_cod}"
    else:
        # 同族單值 action(CLEAN/DND/DOOR/EMG/MAIN_POWER...)——RC2 才細分,先記錄
        state["last_action_cod"] = action_cod
        desc = MSG_DONE + "."
    return build_ack_response_xml(reve, action_cod, desc), True


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

        if action_cod == "ROOM_INF":
            resp_xml = build_rowset_xml(_room_inf_rows(room))
            proc = True
        elif reve.endswith("4190") or action_cod:
            resp_xml, proc = _apply_b4_push(row)
        else:
            resp_xml = build_error_response_xml(reve, action_cod, "9999", f"Unknown ACTION_COD: {action_cod}")
            proc = False
        results.append({"procStatus": proc, "responseBody": resp_xml, "fileName": file_name})

    return jsonify(results), 200


@roomcontrol_bp.route('/roomcontrol/internal/state', methods=['GET'])
def get_internal_state():
    """沙盒內部回讀(LOCAL 閉環驗證用;REAL 環境無此端點,runner 會跳過回讀斷言)。"""
    return jsonify({"room_control_state": mock_roomcontrol_state,
                    "room_guest_rooms": sorted(mock_room_guest_db.keys())}), 200
