# server/pbx/billing.py
"""☎️ 交換機模組 M4 — 帳務面(PTX 電話入帳 / MBT Mini bar;計費系統→德安)。

依據:交換機SA規格.docx(A7 介接 v1.16)§7.2.1.1「PTX電話入帳」+
pbx_interface.doc「Telephone / Mini bar (pms to host)」記錄佈局。
方向:交換機(計費系統)寫 PMS2HOST → 德安讀取入帳;
沙盒以 HTTP 承載同一份 192-byte 記錄(POST /pbx/billing/ptx|mbt)。

SA §7.2.1.1 規則落地:
1. Trans_typ='XXX' → 直接 skip(豐菱傳XXX為無法確定的資料,不處理)
2. trans_amt 依館別參數 round_hfd 四捨五入(null 算 0);
   talk_tim 係以秒數轉時分秒(6碼),>86399→235959、>89999→245959
3. 分機判斷方式(pbx_phone_nos_way):PHONE_RF→phone_rf 捉不到入 pbx_err;
   ROOM_NOS→phone_rf 捉,無設定時直接認定入住客帳(以 PTX.Phone_nos 入帳)
4. phone_rf.act_cod:Y→住客帳(guest_dt)、N→事務分機帳(smdr_dt)
5. 住客帳:捉在館客(guest_sta='O' 且 aci_sys_dat<=通話開始時間,v1.7);
   捉不到→K(關帳)失敗入 pbx_err、C(已結帳)改入現金帳
   (v1.8:gutel ikey='****'/seq 0;現金帳關帳則用現金帳卡號);
   零元依 pbx_zero_fee_insert_guest(不入仍入 gutel_dt);服務項目 LDC/LOC/INT→
   pbx_tel_local_item、OSC→pbx_tel_nation_item;guest_dt 固定 shift_cod='Z'/ins_usr='PBX'/
   bill_dat=PTX.Start_dat/rspt_cod=n2400_rspt_cod;gutel_dt 一律要入(入帳失敗也要入 pbx_err)
6. 事務帳:cost_amt = round(trans_amt / pbx_smdr_plus_rate, round_hfd)

MBT:SA 無細則(A7 未做,bypass)→沙盒自定義:同住客帳選客規則,
服務項目自擴參數 pbx_mbt_item,不入 gutel_dt(非電話明細)。
"""
import itertools
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, request, jsonify

from .routes import PBX_ROOMS
from .pms_side import _pbx_err
from .vendors.vendor_PABX import parse_record

billing_bp = Blueprint('pbx_billing', __name__)

# ---- 館別參數(HOTEL_SVAL_MN;SA規格參數設定表 + 自擴 MBT 項目) --------------
DEFAULT_PARAMS = {
    "rent_cal_dat": "",                  # 滾房租日(reset 帶入今天)
    "round_hfd": 1,                      # 前檯小數位數
    "pbx_phone_nos_way": "ROOM_NOS",     # PHONE_RF:依分機代號 / ROOM_NOS:依房號
    "pbx_zero_fee_insert_guest": "Y",    # 零元入不入住客帳
    "pbx_tel_local_item": "LOCAL",       # 市內話服務項目(LDC/LOC/INT)
    "pbx_tel_nation_item": "INTL",       # 國際電話服務項目(OSC)
    "pbx_smdr_plus_rate": 1.1,           # 事務電話加成率
    "pbx_cash_account": "9999",          # 電話入帳已C/O時現金帳號碼(v1.8)
    "n2400_rspt_cod": "HC1",             # 夜核入帳廳別(含PBX)出納廳最小代號
    "pbx_mbt_item": "MB",                # 自擴:MBT Mini bar 服務項目
}

mock_hotel_params = {}     # 館別參數(值)
mock_phone_rf = {}         # 分機代號對照:phone_nos → {room_nos, dept_cod, act_cod}
mock_guest_mn = []         # 住客主檔視景(room/ci_ser/guest_sta O、K、C/ikey/aci_sys_dat…)
mock_guest_dt = []         # 住客帳明細(入帳結果)
mock_gutel_dt = []         # 住客電話帳明細表
mock_smdr_dt = []          # 事務電話帳明細表
mock_cash_guest = None     # 現金帳住客(master_sta='C' 視景):{room_nos, guest_sta, ikey, ikey_seq_nos, ci_ser}

_key_seq = itertools.count(1)     # gutel_dt.key_nos / smdr_dt.seq_nos 流水
_acct_seq = itertools.count(1)    # guest_dt.acct_nos 流水
_ci_ser_seq = itertools.count(1)  # guest_mn.ci_ser 流水
_room_ser_seq = itertools.count(1)


def _seed_defaults():
    mock_hotel_params.clear()
    mock_hotel_params.update(DEFAULT_PARAMS)
    mock_hotel_params["rent_cal_dat"] = datetime.now().strftime("%Y%m%d")
    mock_phone_rf.clear()
    for room in PBX_ROOMS:                      # 房號→住客帳
        mock_phone_rf[room] = {"room_nos": room, "dept_cod": "", "act_cod": "Y"}
    # 事務分機樣本(act_cod=N → 入 smdr_dt)
    mock_phone_rf["9001"] = {"room_nos": "", "dept_cod": "FRONT", "act_cod": "N"}
    mock_phone_rf["9002"] = {"room_nos": "", "dept_cod": "HSKP", "act_cod": "N"}
    mock_guest_mn.clear()
    mock_guest_dt.clear()
    mock_gutel_dt.clear()
    mock_smdr_dt.clear()
    global mock_cash_guest
    mock_cash_guest = None


_seed_defaults()


# ---- 共用工具 --------------------------------------------------------------
def _round_hfd(value, digits):
    """四捨五入至前檯小數位數(Python round 為銀行二捨,採用 Decimal HALF_UP)。"""
    q = Decimal(1).scaleb(-int(digits))
    return float(Decimal(str(value if value not in (None, "") else 0)).quantize(q, rounding=ROUND_HALF_UP))


def _signed_amount(trans_amt, sign_typ, digits):
    amt = _round_hfd(trans_amt, digits)
    return -amt if (sign_typ or "").strip() == "-" else amt


def _talk_hhmmss(seconds):
    """秒數→時分秒(6碼);>86399→235959、>89999→245959(SA 規則 2 上限)。"""
    try:
        sec = int(str(seconds).strip() or 0)
    except ValueError:
        sec = 0
    if sec > 89999:
        return "245959"
    if sec > 86399:
        return "235959"
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}{m:02d}{s:02d}"


def _norm_dt(dat, tim):
    """YYYYMMDD+HHMMSS → 'YYYY-MM-DD HH:MM:SS'(字串比較即可);無效以現在代。"""
    try:
        return datetime.strptime(f"{dat}{tim}", "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---- guest_mn 視景(pms_side 動作掛鉤 + 測試入口) --------------------------
def note_checkin(room, ikey, alt_nam="Mr. TEST,GUEST"):
    mock_guest_mn.append({
        "room_nos": room, "ci_ser": next(_ci_ser_seq), "room_ser": next(_room_ser_seq),
        "guest_sta": "O", "master_sta": "G", "ikey": ikey, "ikey_seq_nos": 1,
        "alt_nam": alt_nam, "aci_sys_dat": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ci_dat": datetime.now().strftime("%Y%m%d"),
    })


def note_checkout(room):
    for g in mock_guest_mn:
        if g["room_nos"] == room and g["guest_sta"] == "O":
            g["guest_sta"] = "C"          # 已結帳(v1.8 → 現金帳)


def note_room_change(old, new):
    for g in mock_guest_mn:
        if g["room_nos"] == old and g["guest_sta"] == "O":
            g["room_nos"] = new


def _select_open_guest(room, start_dt):
    """SA 1.1:在館客(guest_sta='O')且 aci_sys_dat<=通話開始時間(v1.7);
    排序 ci_dat desc → room_ser → aci_sys_dat desc 取第一筆。"""
    cands = [g for g in mock_guest_mn
             if g["room_nos"] == room and g["guest_sta"] == "O" and g["aci_sys_dat"] <= start_dt]
    cands.sort(key=lambda g: g["room_ser"])
    cands.sort(key=lambda g: (g["ci_dat"], g["aci_sys_dat"]), reverse=True)
    return cands[0] if cands else None


def _select_closed_guest(room, start_dt):
    """SA 1.2:捉不到在館客→先 K(關帳)再 C(已結帳)。"""
    cands = [g for g in mock_guest_mn
             if g["room_nos"] == room and g["guest_sta"] in ("K", "C")
             and g["aci_sys_dat"] <= start_dt]
    cands.sort(key=lambda g: g["room_ser"])
    cands.sort(key=lambda g: (g["guest_sta"], g["ci_dat"], g["aci_sys_dat"]), reverse=True)
    return cands[0] if cands else None


def _cash_flow():
    """現金帳(v1.8):無開/關帳現金帳→自動開立(master_sta='C' 視景)。"""
    global mock_cash_guest
    if mock_cash_guest is None:
        mock_cash_guest = {"room_nos": mock_hotel_params["pbx_cash_account"],
                           "guest_sta": "O", "ikey": f"CS{mock_hotel_params['pbx_cash_account']}",
                           "ikey_seq_nos": 0, "ci_ser": "CASH"}
    return mock_cash_guest


def _service_item(trans_typ):
    """SA 1.5:LDC/LOC/INT→市內話服務項目、OSC→國際電話服務項目。"""
    return (mock_hotel_params["pbx_tel_nation_item"] if (trans_typ or "").strip() == "OSC"
            else mock_hotel_params["pbx_tel_local_item"])


# ---- PTX 入帳(SA §7.2.1.1) ----------------------------------------
def _post_guest_tel(rec, rf, amt, talk):
    """住客帳路徑(含零元/K/C 現金帳分岔)+ gutel_dt 一律入檔。"""
    params = mock_hotel_params
    room = rf["room_nos"] or (rec.get("phone_nos") or "").strip()
    start_dt = _norm_dt(rec.get("start_dat"), rec.get("start_tim"))

    guest = _select_open_guest(room, start_dt)
    mode, err_rmk = "GUEST", ""
    if amt == 0 and params["pbx_zero_fee_insert_guest"] == "N":
        mode, err_rmk = "ZERO_SKIP", "零元入不入住客帳"          # SA 1.3
    elif guest is None:
        closed = _select_closed_guest(room, start_dt)
        if closed is None:
            mode = "FAIL_NO_GUEST"
            err_rmk = f"房號{room} 查無住客資料(在館/關帳/已結帳皆無)"
        elif closed["guest_sta"] == "K":
            mode = "FAIL_CLOSED_K"                                # 關帳:失敗入 pbx_err
            err_rmk = (f"{closed['aci_sys_dat']} 房號{room}.{closed['room_ser']} "
                       f"訂房卡號:{closed['ikey']}.{closed['ikey_seq_nos']} "
                       f"住客:{closed['alt_nam']} 為關帳")
        else:                                                      # C 已結帳 → 現金帳(v1.8)
            cash = _cash_flow()
            mode = "CASH"
            err_rmk = (f"房號{room}.{closed['room_ser']} "
                       f"訂房卡號:{closed['ikey']}.{closed['ikey_seq_nos']} "
                       f"為已結帳,改入現金帳{cash['room_nos']}")

    # 入 guest_dt(SA 1.6;ZERO_SKIP/FAIL 不入)
    acct, guest_ref = "", guest
    if mode in ("GUEST", "CASH"):
        cash = _cash_flow() if mode == "CASH" else None
        if mode == "CASH":
            guest_ref = {**cash,
                         "ikey": cash["ikey"] if cash["guest_sta"] == "K" else "****",
                         "ikey_seq_nos": cash["ikey_seq_nos"] if cash["guest_sta"] == "K" else 0}
        acct = f"AC{next(_acct_seq):05d}"
        mock_guest_dt.append({
            "acct_nos": acct, "room_nos": room, "ci_ser": guest_ref["ci_ser"],
            "item_cod": _service_item(rec.get("trans_typ")), "item_amt": amt,
            "rspt_cod": params["n2400_rspt_cod"], "shift_cod": "Z",
            "acc_dat": params["rent_cal_dat"], "bill_dat": rec.get("start_dat"),
            "ins_usr": "PBX",
            "remark3": (f"from 房號:{room} TEL_DAT:{start_dt} "
                        f"TEL_NOS:{(rec.get('tel_nos') or '').strip()}") if mode == "CASH" else "",
            "remark4": f"{(rec.get('tel_nos') or '').strip()} {talk}",
            "ikey": guest_ref["ikey"], "ikey_seq_nos": guest_ref["ikey_seq_nos"],
        })

    # 入 gutel_dt(SA 1.7:不論入帳成功失敗一律要入;ikey 來自 1.1/1.2 捉到的客)
    closed = _select_closed_guest(room, start_dt) if guest is None else None
    if guest is not None:
        ref = guest
    elif mode == "CASH":
        cash = _cash_flow()
        ref = {"ikey": cash["ikey"] if cash["guest_sta"] == "K" else "****",
               "ikey_seq_nos": cash["ikey_seq_nos"] if cash["guest_sta"] == "K" else 0,
               "ci_ser": cash["ci_ser"]}
    elif closed is not None:
        ref = {"ikey": closed.get("ikey", ""), "ikey_seq_nos": closed.get("ikey_seq_nos", ""),
               "ci_ser": closed.get("ci_ser", "")}
    else:
        ref = {"ikey": "", "ikey_seq_nos": "", "ci_ser": ""}
    gutel = {
        "key_nos": next(_key_seq), "acct_nos": acct, "batch_dat": params["rent_cal_dat"],
        "room_nos": room, "ci_ser": ref["ci_ser"], "tel_nos": (rec.get("tel_nos") or "").strip(),
        "start_dat": rec.get("start_dat"), "start_tim": rec.get("start_tim"),
        "talk_tim": talk, "trans_amt": amt, "trans_typ": (rec.get("trans_typ") or "").strip(),
        "tel_sta": "HAD_TRANS" if acct else "NOT_TRANS", "err_rmk": err_rmk,
        "ikey": ref["ikey"], "ikey_seq_nos": ref["ikey_seq_nos"],
    }
    mock_gutel_dt.append(gutel)

    if mode.startswith("FAIL"):
        _pbx_err("PTX", room, {"FAIL_CLOSED_K": "住客為關帳",
                               "FAIL_NO_GUEST": "查無住客資料"}[mode], err_rmk)
    return {"seq_nos": rec.get("seq_nos"), "inst_cod": "PTX", "phone_nos": rec.get("phone_nos"),
            "result": mode, "acct_nos": acct, "err_rmk": err_rmk, "gutel_key_nos": gutel["key_nos"]}


def _post_smdr(rec, rf, amt, talk):
    """事務分機帳(SA:cost=四捨五入(trans_amt/加成率,round_hfd))。"""
    params = mock_hotel_params
    rate = float(params["pbx_smdr_plus_rate"]) or 1.0
    cost = _round_hfd(amt / rate, params["round_hfd"])
    row = {
        "batch_dat": params["rent_cal_dat"], "seq_nos": next(_key_seq),
        "dept_cod": rf.get("dept_cod", ""), "phone_nos": (rec.get("phone_nos") or "").strip(),
        "tel_nos": (rec.get("tel_nos") or "").strip(), "start_dat": rec.get("start_dat"),
        "start_tim": rec.get("start_tim"), "talk_tim": talk, "trans_amt": amt,
        "cost_amt": cost, "trans_typ": (rec.get("trans_typ") or "").strip(),
    }
    mock_smdr_dt.append(row)
    return {"seq_nos": rec.get("seq_nos"), "inst_cod": "PTX", "phone_nos": rec.get("phone_nos"),
            "result": "SMDR", "cost_amt": cost, "smdr_seq_nos": row["seq_nos"]}


def process_ptx(rec):
    """單筆 PTX 記錄 → 入帳結果摘要(SA §7.2.1.1 全流程)。"""
    if (rec.get("trans_typ") or "").strip() == "XXX":
        return {"seq_nos": rec.get("seq_nos"), "inst_cod": "PTX", "phone_nos": rec.get("phone_nos"),
                "result": "SKIPPED_XXX", "note": "Trans_typ=XXX 無法確定資料,直接 skip"}
    amt = _signed_amount(rec.get("trans_amt"), rec.get("sign_typ"), mock_hotel_params["round_hfd"])
    talk = _talk_hhmmss(rec.get("talk_tim"))
    phone = (rec.get("phone_nos") or "").strip()
    rf = mock_phone_rf.get(phone)
    if mock_hotel_params["pbx_phone_nos_way"] == "PHONE_RF" and rf is None:
        _pbx_err("PTX", phone, "分機對照無此分機", f"phone_rf 無此分機:{phone}")
        return {"seq_nos": rec.get("seq_nos"), "inst_cod": "PTX", "phone_nos": phone,
                "result": "ERR_PHONE_NOT_FOUND"}
    if rf is None:                       # ROOM_NOS 且無設定 → 直接認定入住客帳
        rf = {"room_nos": phone, "dept_cod": "", "act_cod": "Y"}
    if rf["act_cod"] == "Y" and rf["room_nos"] not in PBX_ROOMS:
        _pbx_err("PTX", phone, "ROOM_NOT_FOUND", f"入住客帳但房號不在 universe:{phone}")
        return {"seq_nos": rec.get("seq_nos"), "inst_cod": "PTX", "phone_nos": phone,
                "result": "ERR_ROOM_NOT_FOUND"}
    if rf["act_cod"] == "N":
        return _post_smdr(rec, rf, amt, talk)
    return _post_guest_tel(rec, rf, amt, talk)


# ---- MBT(Mini bar;SA 無細則,沙盒自定義:同選客規則入住客帳) ------
def process_mbt(rec):
    amt = _signed_amount(rec.get("trans_amt"), rec.get("sign_typ"), mock_hotel_params["round_hfd"])
    phone = (rec.get("phone_nos") or "").strip()
    if phone not in PBX_ROOMS:
        _pbx_err("MBT", phone, "ROOM_NOT_FOUND", f"房號不在 universe:{phone}")
        return {"seq_nos": rec.get("seq_nos"), "inst_cod": "MBT", "phone_nos": phone,
                "result": "ERR_ROOM_NOT_FOUND"}
    start_dt = _norm_dt(rec.get("trans_dat"), rec.get("trans_tim"))
    guest = _select_open_guest(phone, start_dt)
    mode, err_rmk = "GUEST", ""
    if amt == 0 and mock_hotel_params["pbx_zero_fee_insert_guest"] == "N":
        mode, err_rmk = "ZERO_SKIP", "零元入不入住客帳"
    elif guest is None:
        closed = _select_closed_guest(phone, start_dt)
        if closed is None:
            mode, err_rmk = "FAIL_NO_GUEST", f"房號{phone} 查無住客資料"
        elif closed["guest_sta"] == "K":
            mode, err_rmk = "FAIL_CLOSED_K", f"房號{phone} 住客為關帳"
        else:
            mode, err_rmk = "CASH", f"房號{phone} 已結帳,改入現金帳"
    acct = ""
    if mode in ("GUEST", "CASH"):
        cash = _cash_flow() if mode == "CASH" else None
        ref = guest if mode == "GUEST" else {
            "ci_ser": cash["ci_ser"],
            "ikey": cash["ikey"] if cash["guest_sta"] == "K" else "****",
            "ikey_seq_nos": cash["ikey_seq_nos"] if cash["guest_sta"] == "K" else 0}
        acct = f"AC{next(_acct_seq):05d}"
        mock_guest_dt.append({
            "acct_nos": acct, "room_nos": phone, "ci_ser": ref["ci_ser"],
            "item_cod": mock_hotel_params["pbx_mbt_item"], "item_amt": amt,
            "rspt_cod": mock_hotel_params["n2400_rspt_cod"], "shift_cod": "Z",
            "acc_dat": mock_hotel_params["rent_cal_dat"], "bill_dat": rec.get("trans_dat"),
            "ins_usr": "PBX",
            "remark3": (f"from 房號:{phone} MBT:{start_dt}") if mode == "CASH" else "",
            "remark4": f"MBT {(rec.get('trans_dat') or '')}{(rec.get('trans_tim') or '')}",
            "ikey": ref["ikey"], "ikey_seq_nos": ref["ikey_seq_nos"],
        })
    if mode.startswith("FAIL"):
        _pbx_err("MBT", phone, "住客為關帳" if mode == "FAIL_CLOSED_K" else "查無住客資料", err_rmk)
    return {"seq_nos": rec.get("seq_nos"), "inst_cod": "MBT", "phone_nos": phone,
            "result": mode, "acct_nos": acct, "err_rmk": err_rmk}


# ---- 端點 --------------------------------------------------------------
def _handle_records(inst_cod, processor):
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
            if rec["inst_cod"] != inst_cod:
                raise ValueError(f"expect {inst_cod} record, got {rec['inst_cod']}")
            parsed.append(rec)
        except ValueError as e:
            return jsonify({"code": "417", "message": f"record parse error: {e}"}), 417
    return jsonify({"results": [processor(rec) for rec in parsed]}), 200


@billing_bp.route('/pbx/billing/ptx', methods=['POST'])
def billing_ptx():
    """接收 PTX 電話入帳記錄(交換機→德安),逐筆依 SA §7.2.1.1 入帳。"""
    return _handle_records("PTX", process_ptx)


@billing_bp.route('/pbx/billing/mbt', methods=['POST'])
def billing_mbt():
    """接收 MBT Mini bar 記錄(交換機→德安;沙盒自定義入住客帳)。"""
    return _handle_records("MBT", process_mbt)


@billing_bp.route('/pbx/billing/params', methods=['POST'])
def billing_params():
    """館別參數覆寫(測試鈕:round_hfd/零元/溝通方式/加成率/現金帳…)。"""
    body = request.get_json(silent=True) or {}
    unknown = [k for k in body if k not in DEFAULT_PARAMS]
    if unknown:
        return jsonify({"code": "400",
                        "message": f"unknown params: {unknown}; available: {sorted(DEFAULT_PARAMS)}"}), 400
    mock_hotel_params.update(body)
    return jsonify({"ok": True, "params": dict(mock_hotel_params)}), 200


@billing_bp.route('/pbx/billing/guests', methods=['POST'])
def billing_guests():
    """guest_mn 測試入口(沙盒自擴):設定該房住客狀態(K 關帳情境專用);
    無該房資料時可直接建立一筆指定狀態的住客。"""
    body = request.get_json(silent=True) or {}
    room = body.get("room_nos")
    if room not in PBX_ROOMS:
        return jsonify({"code": "400", "message": f"unknown room: {room}"}), 400
    sta = body.get("guest_sta", "O")
    if sta not in ("O", "K", "C"):
        return jsonify({"code": "400", "message": "guest_sta must be O/K/C"}), 400
    rows = [g for g in mock_guest_mn if g["room_nos"] == room]
    if rows:
        for g in rows:
            g["guest_sta"] = sta
            for k in ("ikey", "ikey_seq_nos", "aci_sys_dat", "alt_nam"):
                if body.get(k):
                    g[k] = body[k]
    else:
        mock_guest_mn.append({
            "room_nos": room, "ci_ser": next(_ci_ser_seq), "room_ser": next(_room_ser_seq),
            "guest_sta": sta, "master_sta": "G", "ikey": body.get("ikey", f"IK{room}"),
            "ikey_seq_nos": int(body.get("ikey_seq_nos", 1)), "alt_nam": body.get("alt_nam", "Mr. TEST,GUEST"),
            "aci_sys_dat": body.get("aci_sys_dat", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "ci_dat": datetime.now().strftime("%Y%m%d"),
        })
    return jsonify({"ok": True, "guests": [g for g in mock_guest_mn if g["room_nos"] == room]}), 200


@billing_bp.route('/pbx/billing/phone-rf', methods=['POST'])
def billing_phone_rf():
    """phone_rf 分機對照覆寫(事務分機 act_cod=N 情境專用)。"""
    body = request.get_json(silent=True) or {}
    phone = body.get("phone_nos")
    if not phone:
        return jsonify({"code": "400", "message": "phone_nos is required"}), 400
    if body.get("act_cod") not in (None, "Y", "N"):
        return jsonify({"code": "400", "message": "act_cod must be Y/N"}), 400
    base = mock_phone_rf.get(phone, {"room_nos": "", "dept_cod": "", "act_cod": "Y"})
    base.update({k: v for k, v in body.items() if k != "phone_nos"})
    mock_phone_rf[phone] = base
    return jsonify({"ok": True, "phone_rf": base}), 200


@billing_bp.route('/pbx/billing/internal/state', methods=['GET'])
def billing_internal_state():
    """帳務內部回讀(閉環斷言用):params/phone_rf/guest_mn/guest_dt/gutel_dt/smdr_dt/現金帳。"""
    return jsonify({"params": dict(mock_hotel_params), "phone_rf": dict(mock_phone_rf),
                    "guest_mn": mock_guest_mn, "guest_dt": mock_guest_dt,
                    "gutel_dt": mock_gutel_dt, "smdr_dt": mock_smdr_dt,
                    "cash_guest": mock_cash_guest}), 200


@billing_bp.route('/pbx/billing/internal/reset', methods=['POST'])
def billing_reset():
    """測試隔離:帳務狀態與參數回預設(pms 側 reset 亦會連同重置)。"""
    _seed_defaults()
    return jsonify({"code": "2000", "message": "pbx billing state reset"}), 200
