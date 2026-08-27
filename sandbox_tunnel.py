# sandbox_tunnel.py — ngrok 對外隧道控制(測試主控台「🌐 對外隧道」卡後端)
#
# 用途:真實 PMS 雲端要把「PMS→廠商」方向的推播(新詠/博辰/華豫寧)打進本沙盒,
# 沙盒需有公網 URL。本模組以子進程管理 ngrok(agent API: 127.0.0.1:4040),
# 並產出各廠商要登錄進 PMS 第三方廠商設定的完整 URL。
# 固定網域設定:config.NGROK_STATIC_DOMAIN(token_local.py / 環境變數),申請步驟見 README。
import os
import shutil
import subprocess
import time

import requests
from flask import Blueprint, jsonify

import config

tunnel_bp = Blueprint("tunnel", __name__)

_NGROK_API = "http://127.0.0.1:4040/api/tunnels"
_NGROK_PORT = 5000
_proc = None  # 本沙盒 spawn 的 ngrok 子進程 handle(stop 僅能停自己啟動的)

# 💡 本機 4040 查詢專用 session:不吃系統 proxy(部分環境 proxy 層會讓連線失敗拖到 2 秒)
_local = requests.Session()
_local.trust_env = False


def _ngrok_exe():
    """ngrok 執行檔位置:專案根目錄優先,其次 PATH(shutil.which)。找不到回 None。"""
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ngrok.exe")
    if os.path.exists(local):
        return local
    return shutil.which("ngrok")


def _query():
    """向本機 ngrok agent API 查隧道狀態;回 (agent_running, public_https_url)。"""
    try:
        r = _local.get(_NGROK_API, timeout=0.5)
        tunnels = (r.json() or {}).get("tunnels", [])
        https = [t.get("public_url") for t in tunnels
                 if str(t.get("public_url", "")).startswith("https")]
        return True, (https[0] if https else None)
    except Exception:
        return False, None


def _register_urls(public_url):
    """各廠商登錄進 PMS 第三方廠商設定的 URL(對照 README 表)。"""
    return {
        "SHIN_YEONG": f"{public_url}/parking/sync",                  # SA v1.2 公版單一端點
        "PAYTRONEX": f"{public_url}/parktron/hpms/services/roomer",  # PMS 拼 add/findByLicensePlate/update
        "LIVEAM": public_url,                                        # PMS 拼 /api/Auth/login、/api/Order…
    }


@tunnel_bp.route("/tunnel/status", methods=["GET"])
def tunnel_status():
    running, url = _query()
    return jsonify({
        "running": bool(running and url),
        "public_url": url,
        "spawned_by_sandbox": _proc is not None and _proc.poll() is None,
        "static_domain": config.NGROK_STATIC_DOMAIN,
        "register_urls": _register_urls(url) if url else None,
    })


@tunnel_bp.route("/tunnel/start", methods=["POST"])
def tunnel_start():
    global _proc
    running, url = _query()
    if running and url:
        return jsonify({"ok": True, "already_running": True, "public_url": url,
                        "register_urls": _register_urls(url)})

    exe = _ngrok_exe()
    if not exe:
        return jsonify({"ok": False, "error": "找不到 ngrok:請將 ngrok.exe 放進專案根目錄或安裝至 PATH"
                                              "(下載:https://ngrok.com/download,步驟見 README)"}), 500

    cmd = [exe, "http"]
    if config.NGROK_STATIC_DOMAIN:
        cmd += ["--url", config.NGROK_STATIC_DOMAIN]
    cmd += [str(_NGROK_PORT)]
    try:
        # 輸出導流避免阻塞;新行程群組讓 ngrok 不隨單一請求結束
        _proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    except Exception as e:
        return jsonify({"ok": False, "error": f"ngrok 啟動失敗: {e}"}), 500

    for _ in range(24):  # 輪詢等待 agent API 就緒(免費版連線約需數秒;上限約 30 秒)
        time.sleep(0.8)
        running, url = _query()
        if running and url:
            return jsonify({"ok": True, "public_url": url, "register_urls": _register_urls(url)})
    return jsonify({"ok": False, "error": "ngrok 未在 30 秒內就緒。常見原因:"
                                          "尚未設定 authtoken(./ngrok.exe config add-authtoken <token>)"
                                          "或固定網域名稱不正確。"}), 500


@tunnel_bp.route("/tunnel/stop", methods=["POST"])
def tunnel_stop():
    global _proc
    running, _ = _query()
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except Exception:
            _proc.kill()
        _proc = None
        return jsonify({"ok": True, "stopped": True})
    if running:
        return jsonify({"ok": False, "error": "隧道非本沙盒啟動(外部執行中),請手動關閉 ngrok。"}), 409
    return jsonify({"ok": True, "stopped": False, "message": "隧道本來就未啟動"})
