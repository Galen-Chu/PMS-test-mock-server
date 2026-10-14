# orchestrator/case_logs.py
"""📜 案例級雙端 Log(結果頁「Server Log / Client Log 分離顯示」支撐)。

架構前提:沙盒的編排端(runner)與 Flask 路由端同 process(loopback HTTP),
因此伺服器側日誌可在本程序內攔截、無需跨程序傳輸:

- **Server log**(路由端視角):客戶端發砲時帶 ``X-Sandbox-Case-Id`` header;
  ``before_app_request`` 鉤子把它掛到 ``flask.g``;``CaseServerLogHandler``
  掛在 root logger——路由 logger(如 ``ParkingSandbox``/``PbxPmsSandbox``)
  於請求處理期間 emit 的紀錄,依 ``g`` 上的案例鍵收進該案例緩衝。
  引擎在案例跑完後 ``take_server_log`` 取回塞進 ``CaseResult.server_log``。
- **Client log**(編排端視角):``RunContext.client_log`` 逐案重置;
  ``execute_for_ctx`` 每筆 HTTP 交易前後各記一行(→ 出發 / ← 回應 / ✖ 失敗),
  引擎補 START/END 框線後塞進 ``CaseResult.client_log``。

REAL 環境:header 不出站(避免對雲端送內部欄位),遠端伺服器 log 本就不在
沙盒視野 → server_log 為空,UI 顯示提示。另外 ``print()`` 輸出不在
logging 管道內,不攔截(路由端慣例為 named logger,見各 routes.py 頂部)。
"""
import logging
import threading
from datetime import datetime

# 客戶端 → 伺服器的案例關聯 header(僅 LOCAL 模式出站)
CASE_HEADER = "X-Sandbox-Case-Id"

# 案例鍵 → 伺服器側日誌行緩衝(run_id:case_id 為鍵,跨 run 不互撞)
_SERVER_LOGS = {}
_LOCK = threading.Lock()


def begin_case(case_key):
    """案例開始:初始化(清空)該鍵的伺服器側緩衝,隔離殘留。"""
    with _LOCK:
        _SERVER_LOGS[case_key] = []


def append_server_line(case_key, line):
    with _LOCK:
        _SERVER_LOGS.setdefault(case_key, []).append(line)


def take_server_log(case_key):
    """案例結束:取回整份伺服器側日誌並清鍵(不殘留記憶體)。"""
    with _LOCK:
        return _SERVER_LOGS.pop(case_key, [])


# ---- Client log 行格式工具(engine / execute_for_ctx 共用) ------------------
def now_ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def client_line(mark, text):
    """組一行 client log:「[HH:MM:SS.mmm] mark text」(mark: →/←/✖/▶/■)。"""
    return f"[{now_ts()}] {mark} {text}"


# ---- 伺服器側攔截:root logger handler + Flask 請求鉤子 ---------------------
class CaseServerLogHandler(logging.Handler):
    """把「案例關聯請求期間」發出的 logging 紀錄收進該案例緩衝。

    只在 Flask request context 內且有 ``g._sandbox_case_id`` 時收單;
    其他(引擎執行緒、背景排程)一律放行不管。emit 內絕不拋錯,
    避免影響路由本身的日誌行為。
    """

    def emit(self, record):
        try:
            from flask import g, has_request_context
            if not has_request_context():
                return
            case_key = g.get("_sandbox_case_id", None)
            if not case_key:
                return
            append_server_line(case_key, self.format(record))
        except Exception:
            pass


# 與 main.py 原 console 格式一致(📋 層級 模組:訊息),雙端呈現時兩側風格對齊
_FMT = "[%(asctime)s] %(levelname)s [%(name)s]: %(message)s"


def install_server_log_capture():
    """把攔截 handler 掛上 root logger(冪等;任何 app 註冊 orchestrator_bp 即生效)。

    維持 main.py 原本的 console 輸出行為:若 root 尚無 console handler
    (本安裝先於 main.py 的 ``logging.basicConfig`` 時,basicConfig 會因
    root 已有 handler 而跳過),補上同格式的 StreamHandler 並開 INFO。
    """
    root = logging.getLogger()
    if any(isinstance(h, CaseServerLogHandler) for h in root.handlers):
        return
    cap = CaseServerLogHandler()
    cap.setFormatter(logging.Formatter(_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(cap)
    has_console = any(isinstance(h, logging.StreamHandler)
                      and not isinstance(h, CaseServerLogHandler)
                      for h in root.handlers)
    if not has_console:
        con = logging.StreamHandler()
        con.setFormatter(logging.Formatter("📋 " + _FMT, datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(con)
    if root.level in (logging.NOTSET, logging.WARNING):   # 尚未有人調過 → 對齊 main.py INFO
        root.setLevel(logging.INFO)
