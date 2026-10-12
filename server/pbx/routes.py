# server/pbx/routes.py
"""☎️ 交換機模組 — mock 交換機側(計費系統/PMS MODULE),接收德安 HOST 下達的指令記錄。

沙盒角色對映(真實架構見 pbx_interface.doc 硬體設備節):
- 德安 HOST(C# 交換機程式,寫 HOST2PMS.DAT)→ 沙盒 runner 模擬(發砲端);
- 交換機側(計費系統 PMS MODULE,讀檔/回應)→ 本路由模擬(mock 被測端)。
- 檔案傳輸媒介以 HTTP 承載:POST /pbx/host-commands 帶 192-byte 記錄字串陣列,
  每筆回一個 Record_typ='R' 回應記錄(SUC/ERR/SKP + Msg_cod)。

狀態機規則(宏興 SD「多筆晨呼設定與pbx_mn送出規格.docx」§6 API):
- CKI/COX:tel_sta=1 + lang + dnd/mwl/tce=0,房況住人(O)
- CKO/CIX:pbx_dt 全清、房況空房(V),未回應晨呼(mcall_sta=0)全數取消
- RMC:pbx_dt 舊房→新房搬移、舊房清空、晨呼跟著移房
- DND/TCE/MWL/OOO:需「有住人 且 電話開」(SD 2020/7/31 規則;有開電話才可設限撥/勿擾/mcall)
- MCS:mcall_sta=0 設定落庫;'D' 取消該房詞該時段設定
- 前置不符 → 回 ERR + Msg_cod(ROOM_NOT_FOUND/MSG_FORMAT 為契約列舉;
  GUEST_NOT_IN/TEL_NOT_OPEN/MCALL_NOT_FOUND 為沙盒自擴值域,待 SA 確認——計畫文件 Q2)

另提供沙盒內部端點(LOCAL 閉環驗證/測試隔離):/pbx/internal/state、/pbx/internal/reset。
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify

from .vendors.vendor_PABX import (
    build_response_record, parse_record,
    RESP_SUC, RESP_ERR,
)

pbx_bp = Blueprint('pbx', __name__)

logger = logging.getLogger("PbxSandbox")
logger.setLevel(logging.INFO)

# ---- 沙盒記憶體資料庫 ----------------------------------------------------
# 交換機已知房號 universe(房號=分機;未列房號 → ROOM_NOT_FOUND)
PBX_ROOMS = [f"010{i}" for i in range(1, 10)]   # 0101..0109

# pbx_dt:房間交換機現狀(room → {tel_sta, dnd_cod, mwl_cod, tce_cod, lang_cod, room_sta})
# 初始全空房:tel_sta=0、無住人(PMS0210120 表4;room_sta 沙盒自持,模擬 CKI 更新房況)
mock_pbx_dt = {
    room: {"tel_sta": "0", "dnd_cod": "0", "mwl_cod": "0", "tce_cod": "0",
           "lang_cod": "", "room_sta": "V"}
    for room in PBX_ROOMS
}

# mcall_mn:晨喚設定((room, mcall_dat, mcall_tim) → {mcall_sta, updated_at})
mock_pbx_mcall = {}

# pbx_log:交換機日誌(direction I/O、inst_cod、succ_flg;PMS0210120 表5 欄位對齊)
mock_pbx_log = []


def _log(direction, inst_cod, room_nos, succ_flg, data_rmk):
    mock_pbx_log.append({
        "ins_dat": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "direction": direction,          # I:收(傳入) O:送(傳出)
        "inst_cod": inst_cod,
        "room_nos": room_nos,
        "succ_flg": succ_flg,            # Y/N
        "data_rmk": (data_rmk or "").rstrip(),
    })


def _err(orig, msg_cod):
    """組 ERR 回應記錄 + 記失敗 log。"""
    _log("O", RESP_ERR, orig.get("phone_nos") or orig.get("ophone_nos") or "", "N",
         f"msg_cod={msg_cod}")
    return build_response_record(RESP_ERR, orig["insert_dat"], orig["insert_tim"],
                                 orig["seq_nos"], msg_cod=msg_cod), False


def _apply_checkin(rec, room):
    """CKI/COX:開電話 + 語言入 pbx_dt + dnd/mwl/tce 歸零 + 房況住人。"""
    dt = mock_pbx_dt[room]
    dt.update({"tel_sta": "1", "lang_cod": rec.get("lang_cod", ""),
               "dnd_cod": "0", "mwl_cod": "0", "tce_cod": "0", "room_sta": "O"})
    return None


def _apply_checkout(rec, room):
    """CKO/CIX:pbx_dt 全清 + 房況空房 + 未回應晨呼全數取消。

    mcall_sta='C' 語意依交換機SA規格 = Close Account(關帳);PMS 側 CKO 僅將 NOT_TRANS 晨喚
    改 'D'(宏興SD)。mock 於 CKO 將 TRANS 晨喚標 'C' = 模擬交換機清除晨呼的回報(計畫 Q5)。"""
    dt = mock_pbx_dt[room]
    dt.update({"tel_sta": "0", "lang_cod": "", "dnd_cod": "0",
               "mwl_cod": "0", "tce_cod": "0", "room_sta": "V"})
    for key, mc in mock_pbx_mcall.items():
        if key[0] == room and mc["mcall_sta"] == "0":
            mc["mcall_sta"] = "C"
    return None


def _apply_room_change(rec, room):
    """RMC:pbx_dt 舊房→新房搬移 + 舊房清空 + 晨呼跟著移房(介面:也要處理晨呼更換至新房間)。"""
    ophone, nphone = room, rec["nphone_nos"]
    mock_pbx_dt[nphone].update(mock_pbx_dt[ophone])
    mock_pbx_dt[ophone].update({"tel_sta": "0", "lang_cod": "", "dnd_cod": "0",
                                "mwl_cod": "0", "tce_cod": "0", "room_sta": "V"})
    for key in list(mock_pbx_mcall):
        if key[0] == ophone:
            mc = mock_pbx_mcall.pop(key)
            mock_pbx_mcall[(nphone,) + key[1:]] = mc
    return None


def _guest_tel_precheck(inst_cod, rec):
    """DND/TCE/MWL/MCS 共用前置(宏興 SD 共用 function):房號存在 → 有住人 → 電話開。"""
    room = rec.get("phone_nos", "")
    if room not in mock_pbx_dt:
        return None, f"ROOM_NOT_FOUND: {room}"
    dt = mock_pbx_dt[room]
    if dt["room_sta"] != "O":
        return None, f"GUEST_NOT_IN: {room}"
    if dt["tel_sta"] != "1":
        return None, f"TEL_NOT_OPEN: {room}"
    return room, None


def _apply_status(rec, room):
    """DND/MWL/TCE/OOO:status_typ(1設定/0取消)寫入 pbx_dt 對應欄(OOO 無對應欄,僅記 log)。"""
    field = {"DND": "dnd_cod", "MWL": "mwl_cod", "TCE": "tce_cod"}.get(rec["inst_cod"])
    if field:
        mock_pbx_dt[room][field] = rec.get("status_typ", "1")
    return None


def _apply_mcall(rec, room):
    """MCS:mcall_sta='0' 設定(upsert)/'D' 取消該房該時段設定。"""
    key = (room, rec.get("mcall_dat", ""), rec.get("mcall_tim", ""))
    if rec.get("mcall_sta", "0") == "D":
        mc = mock_pbx_mcall.get(key)
        if mc is None or mc["mcall_sta"] != "0":
            return f"MCALL_NOT_FOUND: {key}"
        mc["mcall_sta"] = "D"
    else:
        mock_pbx_mcall[key] = {"mcall_sta": "0",
                               "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    return None


def _process_instruction(rec):
    """單筆指令 → (回應記錄, 成功否)。解析層契約:未知 inst → ERR MSG_FORMAT。"""
    inst = rec["inst_cod"]
    room = rec.get("phone_nos") or rec.get("ophone_nos") or ""

    if inst not in ("CKI", "COX", "CKO", "CIX", "RMC", "MCS", "DND", "MWL", "TCE", "OOO"):
        return _err(rec, f"MSG_FORMAT: unknown inst_cod {inst}")
    if inst in ("CKI", "COX", "CKO", "CIX", "RMC"):
        target = rec.get("nphone_nos") if inst == "RMC" else rec.get("phone_nos", "")
        targets = [rec.get("ophone_nos", ""), target] if inst == "RMC" else [target]
        for t in targets:
            if t not in mock_pbx_dt:
                return _err(rec, f"ROOM_NOT_FOUND: {t}")
        if inst == "RMC" and mock_pbx_dt[rec.get("ophone_nos", "")]["room_sta"] != "O":
            return _err(rec, f"GUEST_NOT_IN: {rec.get('ophone_nos', '')}")
    else:
        room, err = _guest_tel_precheck(inst, rec)
        if err:
            return _err(rec, err)

    err = {"CKI": _apply_checkin, "COX": _apply_checkin,
           "CKO": _apply_checkout, "CIX": _apply_checkout,
           "RMC": _apply_room_change,
           "MCS": _apply_mcall,
           "DND": _apply_status, "MWL": _apply_status, "TCE": _apply_status,
           "OOO": _apply_status}[inst](rec, room)
    if err:
        return _err(rec, err)
    _log("I", inst, room, "Y", rec["data_rmk"])
    _log("O", RESP_SUC, room, "Y", "")
    return build_response_record(RESP_SUC, rec["insert_dat"], rec["insert_tim"],
                                 rec["seq_nos"], msg_cod="", session_cod=""), True


@pbx_bp.route('/pbx/host-commands', methods=['POST'])
def host_commands():
    """接收德安 HOST 批次指令記錄,逐筆執行狀態機並回回應記錄陣列。"""
    body = request.get_json(silent=True) or {}
    records = body.get("records") or []
    if not body.get("athenaId") or not body.get("hotelCode"):
        return jsonify({"code": "400", "message": "athenaId and hotelCode are required"}), 400
    if not records:
        return jsonify({"code": "400", "message": "records is required"}), 400

    parsed = []
    for rec_str in records:
        try:
            rec = parse_record(rec_str)
            if rec["record_typ"] != "I":
                raise ValueError("expect instruction record (Record_typ='I')")
            parsed.append(rec)
        except ValueError as e:
            logger.warning(f"[交換機沙盒] 記錄結構無效: {e}")
            return jsonify({"code": "417", "message": f"record parse error: {e}"}), 417

    responses, results = [], []
    for rec in parsed:
        logger.info(f"📥 [交換機沙盒] 指令【{rec['inst_cod']}】房號【{rec.get('phone_nos') or rec.get('ophone_nos') or ''}】seq【{rec['seq_nos']}】")
        resp_rec, ok = _process_instruction(rec)
        responses.append(resp_rec)
        results.append({"inst_cod": rec["inst_cod"],
                        "room_nos": rec.get("phone_nos") or rec.get("ophone_nos") or "",
                        "seq_nos": rec["seq_nos"],
                        "resp_cod": RESP_SUC if ok else RESP_ERR})
    return jsonify({"responses": responses, "results": results}), 200


@pbx_bp.route('/pbx/ring', methods=['POST'])
def ring_mcall():
    """☎️ 晨喚時間到:交換機撥號並回報 MCS 結果(1-5 等)——M2 模擬觸發點。

    交換機側:更新自身 mcall 狀態 → 轉發 PMS 側 handle_mcs_response(依 SA 五規則
    更新 mcall_mn/入 pbx_err)。body:{room_nos, mcall_sta(預設'1'), mcall_dat?, mcall_tim?}。
    """
    from .pms_side import handle_mcs_response   # 延遲 import(pms_side 亦引用本模組)
    body = request.get_json(silent=True) or {}
    room, sta = body.get("room_nos"), str(body.get("mcall_sta", "1"))
    if room not in mock_pbx_dt:
        return jsonify({"code": "400", "message": f"unknown room: {room}"}), 400
    if sta not in ("0", "1", "2", "3", "4", "5", "C", "D", "F"):
        return jsonify({"code": "400", "message": f"invalid mcall_sta: {sta}"}), 400
    dat, tim = body.get("mcall_dat"), body.get("mcall_tim")
    # 交換機側:精準指定或該房首筆未回應(sta=0)晨喚
    cands = [(k, v) for k, v in mock_pbx_mcall.items()
             if k[0] == room and v["mcall_sta"] == "0"]
    if dat:
        cands = [(k, v) for k, v in cands if k[1] == dat]
        if tim:
            cands = [(k, v) for k, v in cands if k[2] == tim]
    if not cands:
        return jsonify({"ok": False, "message": f"房號:{room} 無未回應晨喚可回報"}), 200
    key = min(cands, key=lambda kv: (kv[0][1], kv[0][2]))[0]
    mock_pbx_mcall[key]["mcall_sta"] = sta
    summary, updated = handle_mcs_response(room, key[1], key[2], sta)
    return jsonify({"ok": updated, "switchboard_mcall": {"room_nos": key[0], "mcall_dat": key[1],
                                                         "mcall_tim": key[2], "mcall_sta": sta},
                    "pms_handling": summary}), 200


@pbx_bp.route('/pbx/internal/state', methods=['GET'])
def get_internal_state():
    """沙盒內部回讀(LOCAL 閉環驗證用;前例:roomcontrol /roomcontrol/internal/state)。"""
    return jsonify({"pbx_dt": mock_pbx_dt,
                    "mcall_mn": [{"room_nos": k[0], "mcall_dat": k[1], "mcall_tim": k[2], **v}
                                 for k, v in sorted(mock_pbx_mcall.items())],
                    "pbx_log_tail": mock_pbx_log[-50:]}), 200


@pbx_bp.route('/pbx/internal/reset', methods=['POST'])
def reset_state():
    """測試隔離:清空 mock 狀態與日誌(僅沙盒自用,真實交換機無此對應)。"""
    for room, dt in mock_pbx_dt.items():
        dt.update({"tel_sta": "0", "dnd_cod": "0", "mwl_cod": "0",
                   "tce_cod": "0", "lang_cod": "", "room_sta": "V"})
    mock_pbx_mcall.clear()
    mock_pbx_log.clear()
    return jsonify({"code": "2000", "message": "pbx mock state reset"}), 200
