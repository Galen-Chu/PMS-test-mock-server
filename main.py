# main.py (大一統沙盒平台入口點火)
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
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

# 🎯 核心調度：一條 ngrok 通道，橫著走兩個完全不同的第三方整合系統
app.register_blueprint(parking_bp)
app.register_blueprint(amenity_bp)
app.register_blueprint(keycard_bp)

if __name__ == '__main__':
    print("🚀 [大一統沙盒平台] 核心微服務 Engine 完全體點火成功！")
    print("📡 正在掛載功能模組：")
    print("   1. [停車車辨系統 (Parking Blueprint)] -> ⚡已在線，支援全生命週期邏輯 Upsert")
    print("   2. [房務備品系統 (Amenity Blueprint)] -> ⚡已在線，支援全生命週期邏輯 Upsert")
    print("   3. [門禁卡鎖系統 (Keycard Blueprint)] -> ⚡已在線，支援全生命週期邏輯 Upsert")
    # 💡 保持 debug 模式看報錯，但明確關閉會背刺記憶體的 reloader
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)