# main.py (沙盒平台入口：第0層 Orchestrator 協調 + 互動系統層)
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory
# 🏗️ 第 0 層：測試編排協調層 (Orchestrator) — 統籌底下所有互動系統的測試編排
from orchestrator.api import orchestrator_bp
# 🌐 ngrok 對外隧道控制(UI「對外隧道」卡後端;/tunnel/*)
from sandbox_tunnel import tunnel_bp
# 🔌 互動系統層（被測系統）：目前三個廠商模組，後續可擴充房控、刷卡等其他互動系統
from server.parking.routes import parking_bp
from server.amenity.routes import amenity_bp
from server.keycard.routes import keycard_bp

import logging

# 🎯 宣告全域大閘門：讓所有 logger 的 INFO 以上級別全數通關並導向 Terminal
logging.basicConfig(
    level=logging.INFO,
    format='📋 [%(asctime)s] %(levelname)s [%(name)s]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = Flask(__name__)

# ====================================================================
# 🏗️ 分層掛載：Orchestrator 協調層先掛(第 0 層)，互動系統在後(被測系統)
# 協調層負責 /environments /scenarios /runs，編排底下互動系統的測試案例；
# 互動系統負責各自廠商的 vendor-sync 路由與狀態機。兩層正交、可獨立擴充。
# ====================================================================
app.register_blueprint(orchestrator_bp)   # 第 0 層：編排協調
app.register_blueprint(tunnel_bp)          # 對外隧道控制(/tunnel/status|start|stop)
app.register_blueprint(parking_bp)        # 互動系統 1：停車車辨
app.register_blueprint(amenity_bp)        # 互動系統 2：房務備品
app.register_blueprint(keycard_bp)        # 互動系統 3：門禁製卡


# ====================================================================
# 🖥️ 測試主控台前端（vanilla SPA）：Flask 直接 serve static/，前端 fetch 編排 API
# ====================================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(_HERE, "static")


@app.route('/')
def console_index():
    return send_from_directory(_STATIC, "index.html")

if __name__ == '__main__':
    print("🚀 [大一統沙盒平台] 核心微服務 Engine 完全體點火成功！")
    print("📡 正在分層掛載：")
    print("   第0層 [測試編排協調層 (Orchestrator)] -> ⚡已在線，統籌 /environments /scenarios /runs")
    print("   ── 互動系統層（被測系統，可持續擴充）──")
    print("   1. [停車車辨系統 (Parking)] -> ⚡已在線，支援全生命週期邏輯 Upsert")
    print("   2. [房務備品系統 (Amenity)] -> ⚡已在線，支援全生命週期邏輯 Upsert")
    print("   3. [門禁卡鎖系統 (Keycard)] -> ⚡已在線，支援全生命週期邏輯 Upsert")
    # 💡 保持 debug 模式看報錯，但明確關閉會背刺記憶體的 reloader
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)