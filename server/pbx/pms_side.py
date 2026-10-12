# server/pbx/pms_side.py
"""☎️ 交換機模組 — PMS 側業務層模擬(M1)。

依據:SD文件_PMS0210027_交換機.xlsx(頁面按鈕 0200 新增/0300 刪除/1010 開關電話/
1020 限撥/1030 勿擾——規則全指向宏興SD)+ 宏興SD §1.1/1.2/6(排程/刪除/各 API 語意)。
本 SD 證實:交換機無對外 REST 面(介面=DB 表+檔案),故 M1 = 模擬 PMS 頁面動作
經 mcall_mn/pbx_mn 狀態機下達 pbx_interface 指令(經記錄編解碼,與 M0 mock 交換機同構)。

鏈:頁面動作(/pbx/pms-actions) → mcall_mn(NOT_TRANS) → 排程(/pbx/pms-scheduler/tick,
宏興SD 1.2 五規則) → pbx_mn(TRANS) + 即時下達交換機側(routes._process_instruction)
→ 交換機落庫(回讀斷言)。

宏興SD 規則落地:
- 1.1.1 同房同時段 sta=0 已存在 → 不重複入
- 1.1.2 刪晨喚:時間未過且 sta=0 才能刪;TRANS → 直接 insert pbx_mn 下達(不走排程);
  update mcall_sta='D'(結論:只有 MCALL 時間已過不能取消)
- 1.1.4.1 開電話要有住人;無論有無住人都可以關電話;有開電話才可以設限撥/勿擾/mcall
- 1.2 排程:NOT_TRANS + 24hr 內 + 每房最接近現在一筆 + 上一筆已回應;過期未傳 → SKIP
- §6 CKI/CKO/換房對 pbx_dt 與 mcall_mn 的效果
"""
import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify

from .vendors.vendor_PABX import build_host_record, parse_record
from .routes import _process_instruction, PBX_ROOMS

pms_bp = Blueprint('pbx_pms', __name__)

logger = logging.getLogger("PbxPmsSandbox")
logger.setLevel(logging.INFO)

_seq = iter(range(1, 100000))   # pbx_mn.seq_nos 流水(交換機交換檔)

# ---- PMS 側記憶體 DB ----------------------------------------------------
# room_mn 簡化視景(room → {room_sta O/V, ikey});住人由 checkin/checkout 動作驅動
mock_pms_room = {room: {"room_sta": "V", "ikey": ""} for room in PBX_ROOMS}

# pbx_dt(PMS 側持有的房間交換機現狀;宏興SD §6 各 API 的 update 對象)
mock_pms_pbx_dt = {
    room: {"tel_sta": "0", "dnd_cod": "0", "mwl_cod": "0", "tce_cod": "0", "lang_cod": ""}
    for room in PBX_ROOMS
}

# mcall_mn(key=(room, dat YYYYMMDD, tim HHMMSS) → {mcall_sta, trans_pbx_sta, ikey, ins_dat})
mock_pms_mcall_mn = {}

# pbx_mn(交換機交換檔:list,seq/inst_cod/room_nos/data_rmk/sent_at)
mock_pms_pbx_mn = []


def _now():
    return datetime.now()


def _enqueue_and_send(inst_cod, fields, room):
    """入 pbx_mn + 組 192-byte 記錄下達交換機側(in-process),回 (回應摘要, 成功否)。"""
    seq = next(_seq)
    rec = build_host_record(inst_cod, fields, seq)
    parsed = parse_record(rec)
    resp_rec, ok = _process_instruction(parsed)
    mock_pms_pbx_mn.append({
        "seq_nos": str(seq), "inst_cod": inst_cod, "room_nos": room,
        "data_rmk": parsed["data_rmk"].rstrip(),
        "sent_at": _now().strftime("%Y-%m-%d %H:%M:%S"),
        "resp_ok": ok,
    })
    return {"seq_nos": seq, "inst_cod": inst_cod, "resp_ok": ok}, ok


def _guest_checked_in(room):
    return room in mock_pms_room and mock_pms_room[room]["room_sta"] == "O"


def _tel_open(room):
    return mock_pms_pbx_dt.get(room, {}).get("tel_sta") == "1"


def _mcall_expired(dat, tim):
    try:
        due = datetime.strptime(f"{dat}{tim}", "%Y%m%d%H%M%S")
    except ValueError:
        return True
    return due <= _now()


def _act_checkin(body):
    """入住(含 W/I):room_mn 住人 + pbx_dt 重置(宏興SD CKI) + 下達 CKI。"""
    room, guest = body["room_nos"], body.get("guest_nam", "Mr. TEST,GUEST")
    mock_pms_room[room] = {"room_sta": "O", "ikey": body.get("ikey", f"IK{room}")}
    mock_pms_pbx_dt[room].update({"tel_sta": "1", "lang_cod": body.get("lang_cod", "001"),
                                  "dnd_cod": "0", "mwl_cod": "0", "tce_cod": "0"})
    summary, ok = _enqueue_and_send("CKI", {
        "phone_nos": room, "lang_cod": body.get("lang_cod", "001"),
        "vip_sta": body.get("vip_sta", "N"), "master_nos": room,
        "guest_nam": guest, "account_nos": body.get("account_nos", "CI20261012001"),
    }, room)
    return {"ok": ok, "sent": summary}


def _act_checkout(body):
    """退房:未傳送晨喚取消(mcall_sta='D') + pbx_dt 清空 + 下達 CKO(宏興SD §6)。"""
    room = body["room_nos"]
    mock_pms_room[room] = {"room_sta": "V", "ikey": ""}
    mock_pms_pbx_dt[room].update({"tel_sta": "0", "lang_cod": "",
                                  "dnd_cod": "0", "mwl_cod": "0", "tce_cod": "0"})
    for key, mc in mock_pms_mcall_mn.items():
        if key[0] == room and mc["mcall_sta"] == "0" and mc["trans_pbx_sta"] == "NOT_TRANS":
            mc["mcall_sta"] = "D"
    summary, ok = _enqueue_and_send("CKO", {"phone_nos": room}, room)
    return {"ok": ok, "sent": summary}


def _act_set_mcall(body):
    """新增晨喚(頁面 0200):前置=住人+電話開;同房同時段 sta=0 已存在不重複入(宏興SD 1.1.1)。"""
    room, dat, tim = body["room_nos"], body["mcall_dat"], body["mcall_tim"]
    if not _guest_checked_in(room):
        return {"ok": False, "message": f"房號:{room} 無住人,不能設定晨喚"}
    if not _tel_open(room):
        return {"ok": False, "message": f"房號:{room} 電話未打開,不能設定晨喚"}
    key = (room, dat, tim)
    existing = mock_pms_mcall_mn.get(key)
    if existing and existing["mcall_sta"] == "0":
        return {"ok": False, "message": f"房號:{room} {dat}{tim} 已有設定中晨喚,不重複入"}
    mock_pms_mcall_mn[key] = {"mcall_sta": "0", "trans_pbx_sta": "NOT_TRANS",
                              "ikey": mock_pms_room[room]["ikey"],
                              "ins_dat": _now().strftime("%Y-%m-%d %H:%M:%S")}
    return {"ok": True}


def _act_del_mcall(body):
    """刪除晨喚(頁面 0300,宏興SD 1.1.2):時間未過且 sta=0 才能刪;
    TRANS → 直接 insert pbx_mn 下達 MCS D(不走排程);update mcall_sta='D'。"""
    room, dat, tim = body["room_nos"], body["mcall_dat"], body["mcall_tim"]
    key = (room, dat, tim)
    mc = mock_pms_mcall_mn.get(key)
    if mc is None or mc["mcall_sta"] != "0":
        return {"ok": False, "message": f"房號:{room} {dat}{tim} 無可刪除的設定中晨喚"}
    if _mcall_expired(dat, tim):
        return {"ok": False, "message": f"晨喚時間 {dat}{tim} 已過,不能取消"}
    if mc["trans_pbx_sta"] == "TRANS":
        summary, ok = _enqueue_and_send("MCS", {"phone_nos": room, "mcall_dat": dat,
                                                "mcall_tim": tim, "mcall_sta": "D"}, room)
        if not ok:
            return {"ok": False, "message": "交換機拒絕取消指令", "sent": summary}
    mc["mcall_sta"] = "D"
    return {"ok": True}


def _act_open_tel(body):
    """開電話(1010):要有住人才可以開(宏興SD 1.1.4.1)。"""
    room = body["room_nos"]
    if not _guest_checked_in(room):
        return {"ok": False, "message": f"房號:{room} 無住人,不能開電話"}
    mock_pms_pbx_dt[room]["tel_sta"] = "1"
    summary, ok = _enqueue_and_send("CKI", {"phone_nos": room, "lang_cod":
                                            mock_pms_pbx_dt[room]["lang_cod"] or "001",
                                            "vip_sta": "N", "master_nos": room,
                                            "guest_nam": "Mr. TEST,GUEST",
                                            "account_nos": "CI20261012001"}, room)
    return {"ok": ok, "sent": summary}


def _act_close_tel(body):
    """關電話(1010):無論有無住人都可以關(宏興SD 1.1.4.1)。"""
    room = body["room_nos"]
    mock_pms_pbx_dt[room]["tel_sta"] = "0"
    summary, ok = _enqueue_and_send("CKO", {"phone_nos": room}, room)
    return {"ok": ok, "sent": summary}


def _act_tce_dnd(body, inst):
    """限撥(1020)/勿擾(1030):需住人+電話開;pbx_dt 更新+下達(宏興SD §6)。"""
    room, sta = body["room_nos"], str(body.get("status_typ", "1"))
    if not _guest_checked_in(room):
        return {"ok": False, "message": f"房號:{room} 無住人,不能設定"}
    if not _tel_open(room):
        return {"ok": False, "message": f"房號:{room} 電話未打開,不能設定"}
    field = {"DND": "dnd_cod", "TCE": "tce_cod"}[inst]
    mock_pms_pbx_dt[room][field] = sta
    summary, ok = _enqueue_and_send(inst, {"phone_nos": room, "status_typ": sta}, room)
    return {"ok": ok, "sent": summary}


def _act_room_change(body):
    """換房:pbx_dt 搬移+舊房清空、mcall 改綁新房+NOT_TRANS 重送、下達 RMC(宏興SD §6)。"""
    old, new = body["room_nos"], body["new_room_nos"]
    if not _guest_checked_in(old):
        return {"ok": False, "message": f"房號:{old} 無住人,不能換房"}
    mock_pms_room[new] = mock_pms_room.pop(old)
    mock_pms_room[old] = {"room_sta": "V", "ikey": ""}
    mock_pms_pbx_dt[new].update(mock_pms_pbx_dt[old])
    mock_pms_pbx_dt[old].update({"tel_sta": "0", "lang_cod": "",
                                 "dnd_cod": "0", "mwl_cod": "0", "tce_cod": "0"})
    for key in list(mock_pms_mcall_mn):
        if key[0] == old and mock_pms_mcall_mn[key]["mcall_sta"] == "0":
            mc = mock_pms_mcall_mn.pop(key)
            mc["trans_pbx_sta"] = "NOT_TRANS"   # 怕交換機沒移過去,重送
            mock_pms_mcall_mn[(new,) + key[1:]] = mc
    summary, ok = _enqueue_and_send("RMC", {"ophone_nos": old, "nphone_nos": new}, new)
    return {"ok": ok, "sent": summary}


_ACTIONS = {
    "checkin": _act_checkin, "checkout": _act_checkout,
    "set_mcall": _act_set_mcall, "del_mcall": _act_del_mcall,
    "open_tel": _act_open_tel, "close_tel": _act_close_tel,
    "tce": lambda b: _act_tce_dnd(b, "TCE"), "dnd": lambda b: _act_tce_dnd(b, "DND"),
    "room_change": _act_room_change,
}


@pms_bp.route('/pbx/pms-actions', methods=['POST'])
def pms_actions():
    """模擬 PMS0210027 頁面動作/宏興SD §4 八個觸發 API(識別+action+欄位)。"""
    body = request.get_json(silent=True) or {}
    if not body.get("athenaId") or not body.get("hotelCode"):
        return jsonify({"code": "400", "message": "athenaId and hotelCode are required"}), 400
    action = body.get("action")
    fn = _ACTIONS.get(action)
    if fn is None:
        return jsonify({"code": "400",
                        "message": f"unknown action: {action}; available: {sorted(_ACTIONS)}"}), 400
    if not body.get("room_nos"):
        return jsonify({"code": "400", "message": "room_nos is required"}), 400
    room = body["room_nos"]
    if room not in mock_pms_room:
        return jsonify({"code": "400", "message": f"unknown room: {room}"}), 400

    logger.info(f"🎛️ [PMS側] 動作【{action}】房號【{room}】")
    result = fn(body)
    result.setdefault("ok", False)
    return jsonify(result), 200


@pms_bp.route('/pbx/pms-scheduler/tick', methods=['POST'])
def scheduler_tick():
    """排程掃描(宏興SD 1.2,實機 1 分鐘一次;測試以 tick 驅動):
    NOT_TRANS + 24hr 內 + 每房最接近現在一筆 + 上一筆已回應 → 入 pbx_mn(TRANS)+下達 MCS;
    過期未傳(時間已過或超過 24hr)→ SKIP。"""
    now = _now()
    sent, skipped = [], []
    # 每房取最接近現在且尚未回應的一筆做閘門
    by_room = {}
    for key, mc in mock_pms_mcall_mn.items():
        if mc["mcall_sta"] != "0" or mc["trans_pbx_sta"] != "NOT_TRANS":
            continue
        try:
            due = datetime.strptime(f"{key[1]}{key[2]}", "%Y%m%d%H%M%S")
        except ValueError:
            continue
        by_room.setdefault(key[0], []).append((due, key))
    for room, pendings in by_room.items():
        pendings.sort()
        has_unanswered = any(mock_pms_mcall_mn[k]["mcall_sta"] == "0"
                             and mock_pms_mcall_mn[k]["trans_pbx_sta"] == "TRANS"
                             for k in mock_pms_mcall_mn if k[0] == room)
        for due, key in pendings:
            if due <= now:
                mock_pms_mcall_mn[key]["trans_pbx_sta"] = "SKIP"   # 傳送前已超過時間
                skipped.append({"room_nos": room, "mcall_dat": key[1], "mcall_tim": key[2]})
            elif due > now + timedelta(hours=24):
                continue                                            # 超過 24hr,下輪再掃
            elif has_unanswered:
                continue                                            # 上一筆未回應,等它過時
            else:
                summary, ok = _enqueue_and_send(
                    "MCS", {"phone_nos": room, "mcall_dat": key[1],
                            "mcall_tim": key[2], "mcall_sta": "0"}, room)
                mock_pms_mcall_mn[key]["trans_pbx_sta"] = "TRANS"
                summary.update({"room_nos": room, "mcall_dat": key[1], "mcall_tim": key[2]})
                sent.append(summary)
                has_unanswered = True
    return jsonify({"sent": sent, "skipped": skipped}), 200


@pms_bp.route('/pbx/pms/internal/state', methods=['GET'])
def pms_internal_state():
    """PMS 側內部回讀(M1 閉環斷言用):room_mn/pbx_dt/mcall_mn/pbx_mn。"""
    return jsonify({
        "room_mn": mock_pms_room,
        "pbx_dt": mock_pms_pbx_dt,
        "mcall_mn": [{"room_nos": k[0], "mcall_dat": k[1], "mcall_tim": k[2], **v}
                     for k, v in sorted(mock_pms_mcall_mn.items())],
        "pbx_mn_tail": mock_pms_pbx_mn[-30:],
    }), 200


@pms_bp.route('/pbx/pms/internal/reset', methods=['POST'])
def pms_reset():
    """測試隔離:清空 PMS 側狀態(交換機側另有 /pbx/internal/reset)。"""
    for room in mock_pms_room:
        mock_pms_room[room] = {"room_sta": "V", "ikey": ""}
        mock_pms_pbx_dt[room].update({"tel_sta": "0", "dnd_cod": "0", "mwl_cod": "0",
                                      "tce_cod": "0", "lang_cod": ""})
    mock_pms_mcall_mn.clear()
    mock_pms_pbx_mn.clear()
    return jsonify({"code": "2000", "message": "pbx pms-side state reset"}), 200
