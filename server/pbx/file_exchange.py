# server/pbx/file_exchange.py
"""☎️ 交換機模組 M3 — 真檔案交換媒介層(HOST2PMS/PMS2HOST 四檔 + W/P cycle 輪替)。

契約(pbx_interface「File specification」+ 交換機SA規格「程式流程/例子」):
- 每方向一對檔:DAT(file_size 筆 × 192-byte 記錄,定長環狀)+ IDX(192-byte 單記錄)。
- IDX 欄位(1-based):Record_len 9(3)=192 @1-3、File_size 9(7) @4-10、Wcycle_typ X(1) @11、
  Wseq_nos 9(7) @12-18、Windex_nos 9(7) @19-25、Pcycle_typ X(1) @26、Pindex_nos 9(7) @27-33、
  Filler @34-190、CR+LF @191-192。排版鐵則同 data record(數字靠右)。
- 輪替:Windex > File_size → 歸 1 並翻 cycle(A↔B);讀方同理。
- 覆寫守衛(情況一/二):寫方位置不得落到「讀方未讀」的槽位——
  Wcycle≠Pcycle 且 Windex==Pindex 時代表上一圈資料未讀完 → 等待(不寫)。
- 指標語意(spec「想法」):初始雙方 index=1;Windex=下一個可寫位置,Pindex=下一個未讀位置。
- 編碼:**ANSI(cp950)非 UTF8**(SA規格明載);USE_CHINA_NAM=N 時中文姓名改送房號
  (pbx_interface「Host module 必須過濾中文資料」)——本層寫入前套用此政策。
"""
import os
from pathlib import Path

from flask import Blueprint, request, jsonify

from .vendors.vendor_PABX import build_host_record, parse_record
from .routes import _process_instruction, PBX_ROOMS

file_bp = Blueprint('pbx_file', __name__)

IDX_LEN = 192
REC_LEN = 192
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "pbx_exchange")


def _num(value, n):
    s = str(value if value is not None else "").strip()
    return s[-n:].rjust(n) if s else " " * n


class PbxFileChannel:
    """單方向交換檔對(DAT+IDX)的環狀緩衝:寫方維護 W 指標、讀方維護 P 指標。

    同一 channel 物件同時持有兩側指標(沙盒單機模擬雙進程);真實環境各側只改自己的指標。
    """

    def __init__(self, directory, name, file_size=3000, allow_china=False):
        self.dir = Path(directory)
        self.name = name.upper()                      # HOST2PMS / PMS2HOST
        self.file_size = max(2, int(file_size))
        self.allow_china = allow_china
        self.dat_path = self.dir / f"{self.name}.DAT"
        self.idx_path = self.dir / f"{self.name}.IDX"
        self.wcycle, self.wseq, self.windex = "A", 0, 1
        self.pcycle, self.pindex = "A", 1

    # ---- 檔案初始化 ------------------------------------------------------
    def ensure(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        if not self.dat_path.exists() or self.dat_path.stat().st_size != self.file_size * REC_LEN:
            with open(self.dat_path, "wb") as f:
                f.write(b" " * (self.file_size * REC_LEN))
        self._write_idx()

    def _write_idx(self):
        rec = (_num("192", 3) + _num(self.file_size, 7)
               + self.wcycle + _num(self.wseq, 7) + _num(self.windex, 7)
               + self.pcycle + _num(self.pindex, 7))
        rec = rec.ljust(REC_LEN - 2)[:REC_LEN - 2] + "\r\n"
        with open(self.idx_path, "wb") as f:
            f.write(rec.encode("cp950"))

    def idx_snapshot(self):
        return {"file_size": self.file_size, "wcycle_typ": self.wcycle,
                "wseq_nos": self.wseq, "windex_nos": self.windex,
                "pcycle_typ": self.pcycle, "pindex_nos": self.pindex}

    # ---- 中文姓名政策(pbx_interface:Host module 必須過濾中文資料) --------
    def _apply_china_policy(self, record):
        if self.allow_china:
            return record
        try:
            parsed = parse_record(record)
        except ValueError:
            return record
        guest = parsed.get("guest_nam", "")
        if guest and any(ord(ch) > 127 for ch in guest):
            fields = {k: parsed.get(k, "") for k in
                      ("phone_nos", "lang_cod", "vip_sta", "master_nos", "account_nos")}
            fields["guest_nam"] = parsed.get("phone_nos", "")   # 中文 → 改送房號
            return build_host_record(parsed["inst_cod"], fields, self.wseq + 1,
                                     record_nos=int(parsed.get("record_nos") or 1))
        return record

    # ---- 寫入(寫方) ------------------------------------------------------
    def write(self, record_str):
        """寫一筆 192-byte 記錄於 Windex 位置並前進指標;環滿(對方未讀)回 (None, wait)。"""
        if self.wcycle != self.pcycle and self.windex == self.pindex:
            return None, f"wait: reader behind (P={self.pcycle}{self.pindex}, W={self.wcycle}{self.windex})"
        record_str = self._apply_china_policy(record_str)
        data = record_str.encode("cp950", errors="replace")
        if len(data) > REC_LEN:
            # 含中文(cp950 雙位元組)超出 192 bytes → 截內容、保結尾 CRLF;
            # 截斷處可能切在雙位元組字中線(解碼以 replacement 代),位置偏移屬已知限制(Q10)
            data = data[:REC_LEN - 2] + b"\r\n"
        else:
            data = data.ljust(REC_LEN)
        with open(self.dat_path, "r+b") as f:
            f.seek((self.windex - 1) * REC_LEN)
            f.write(data)
        self.wseq = (self.wseq + 1) % 10_000_000       # 溢位歸零循環(spec)
        self.windex += 1
        if self.windex > self.file_size:               # 繞回 → 翻 cycle
            self.windex = 1
            self.wcycle = "B" if self.wcycle == "A" else "A"
        self._write_idx()
        return self.wseq, None

    # ---- 讀取(讀方) ------------------------------------------------------
    def read_pending(self):
        """讀走對方已寫而未讀的記錄(依 cycle 比對),前進 P 指標。"""
        out = []
        while True:
            if self.pcycle == self.wcycle and self.pindex == self.windex:
                break                                  # 無新資料
            with open(self.dat_path, "rb") as f:
                f.seek((self.pindex - 1) * REC_LEN)
                raw = f.read(REC_LEN)
            text = raw.decode("cp950", errors="replace")
            if not text.startswith(("I", "R")):
                break                                  # 防禦:未寫入槽位(全空白)
            # cp950 雙位元組字解碼後字元數 <192 → 補回 192 維持 parse_record 長度契約
            # (位置對齊以位元組為準;含中文記錄的後段欄位解析為已知偏移,見計畫 Q10 註記)
            if len(text) < REC_LEN:
                text = text[:REC_LEN - 2].ljust(REC_LEN - 2) + "\r\n"
            out.append(text[:REC_LEN])
            self.pindex += 1
            if self.pindex > self.file_size:
                self.pindex = 1
                self.pcycle = "B" if self.pcycle == "A" else "A"
        self._write_idx()
        return out

    def load_state(self):
        """從 IDX 檔還原指標(模擬重啟)。"""
        if not self.idx_path.exists():
            return
        with open(self.idx_path, "rb") as f:
            rec = f.read(IDX_LEN).decode("cp950", errors="replace")
        self.wcycle, self.wseq = rec[10], int(rec[11:18] or 0)
        self.windex = int(rec[18:25] or 1)
        self.pcycle, self.pindex = rec[25], int(rec[26:33] or 1)
        self.file_size = int(rec[3:10] or self.file_size)


# ---- 沙盒單例(ensure 端點建立;run-cycle 驅動雙側) ------------------------
_state = {"dir": DEFAULT_DIR, "file_size": 3000, "allow_china": False,
          "host2pms": None, "pms2host": None}


def _channels():
    h = _state["host2pms"] or PbxFileChannel(_state["dir"], "host2pms",
                                             _state["file_size"], _state["allow_china"])
    p = _state["pms2host"] or PbxFileChannel(_state["dir"], "pms2host",
                                             _state["file_size"], _state["allow_china"])
    _state.update(host2pms=h, pms2host=p)
    return h, p


@file_bp.route('/pbx/file/ensure', methods=['POST'])
def file_ensure():
    """建立/重置交換檔(模擬雙側初次部署)。body:{file_size?=3000, allow_china?=false, reset?=true}"""
    body = request.get_json(silent=True) or {}
    _state.update(dir=body.get("directory") or DEFAULT_DIR,
                  file_size=int(body.get("file_size") or 3000),
                  allow_china=bool(body.get("allow_china", False)),
                  host2pms=None, pms2host=None)
    h, p = _channels()
    h.ensure()
    p.ensure()
    return jsonify({"ok": True, "directory": str(h.dir),
                    "file_size": h.file_size, "allow_china": h.allow_china}), 200


@file_bp.route('/pbx/file/run-cycle', methods=['POST'])
def file_run_cycle():
    """模擬 C# 定時流程一輪(SA規格 wf_read_host/wf_read_pms):
    ① PMS 側把 pbx_mn 未處理(DELETE_STA=N)寫 HOST2PMS(滿載則等待)並標 Y
    ② 交換機側讀 HOST2PMS → 逐筆執行狀態機 → 回應記錄寫 PMS2HOST
    ③ PMS 側讀 PMS2HOST 回應(SUC 記錄;ERR 入 pbx_err)。"""
    from .pms_side import mock_pms_pbx_mn, mock_pms_pbx_err
    h, p = _channels()
    if not h.dat_path.exists():
        return jsonify({"code": "400", "message": "exchange files not initialized; POST /pbx/file/ensure first"}), 400

    written, waited = [], []
    for entry in mock_pms_pbx_mn:
        if entry.get("delete_sta", "N") != "N":
            continue
        rec = build_host_record(entry["inst_cod"],
                                _fields_from_rmk(entry["inst_cod"], entry.get("data_rmk", "")),
                                int(entry["seq_nos"]))
        seq, wait = h.write(rec)
        if wait:
            waited.append({"seq_nos": entry["seq_nos"], "reason": wait})
            break
        entry["delete_sta"] = "Y"
        written.append({"seq_nos": entry["seq_nos"], "inst_cod": entry["inst_cod"]})

    instructions = h.read_pending()
    processed, responses = [], []
    for rec in instructions:
        parsed = parse_record(rec)
        resp_rec, ok = _process_instruction(parsed)
        responses.append(resp_rec)
        processed.append({"inst_cod": parsed["inst_cod"], "room_nos":
                          parsed.get("phone_nos") or parsed.get("ophone_nos") or "",
                          "ok": ok})
        p.write(resp_rec)

    reply_bodies = p.read_pending()
    handled = []
    from .vendors.vendor_PABX import parse_response_fields
    for rec in reply_bodies:
        f = parse_response_fields(rec)
        handled.append(f)
        if f["resp_cod"] != "SUC":
            mock_pms_pbx_err.append({"err_dat": _now_str(), "inst_cod": f["resp_cod"],
                                     "room_nos": "", "error_cod": f["msg_cod"] or f["resp_cod"],
                                     "data_rmk": f"file reply seq={f['orig_seq_nos']}"})
    return jsonify({"written": written, "waited": waited,
                    "processed": processed, "handled_replies": handled}), 200


def _now_str():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fields_from_rmk(inst_cod, data_rmk):
    """pbx_mn.data_rmk(161 區段)→ build_host_record 所需欄位 dict(依佈局切位)。"""
    from .vendors.vendor_PABX import HOST_INST_LAYOUTS
    fields, pos = {}, 3
    for name, kind, n in HOST_INST_LAYOUTS.get(inst_cod, []):
        fields[name] = data_rmk[pos:pos + n].strip()
        pos += n
    return fields


@file_bp.route('/pbx/file/state', methods=['GET'])
def file_state():
    h, p = _channels()
    if not h.dat_path.exists():
        return jsonify({"initialized": False}), 200
    return jsonify({"initialized": True, "directory": str(h.dir),
                    "host2pms": h.idx_snapshot(), "pms2host": p.idx_snapshot()}), 200
