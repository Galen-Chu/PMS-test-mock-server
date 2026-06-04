# main.py
from flask import Flask
from server.parking.routes import parking_bp

app = Flask(__name__)

# 🎯 核心：在這裡將所有廠商藍圖註冊進同一個 Flask 引擎
app.register_blueprint(parking_bp)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)