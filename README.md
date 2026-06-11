# 🏨 德安 Athena PMS 全物聯網整合測試大一統 Staging 沙盒平台

本專案（`PMS-test-mock-server`）是一個高度解耦、採用**策略模式（Strategy Pattern）**與**藍圖架構（Flask Blueprints）**建構的**高傳真（High-Fidelity）**整合測試沙盒。透過將架構進行「職責分離（SoC）」重構，完美還原實體行動代號的資料流與第三方廠商後端伺服器的物理通信邊界，並具備全自動批次迴圈連發功能，用以高效驗證串接整合測試。
旨在切斷飯店實體硬體與環境的依賴，一鍵還原並模擬異質物聯網廠商與德安 PMS 系統之間的雙向數據對撞鏈路。

---

## 📂 專案大一統架構圖 (Project Directory Tree)

```text
PMS-test-mock-server/
│
├── config.py                 # 全域設定檔 (動態切換本地沙盒/真實德安 QA 雲端)
├── main.py                   # ⚡ 專案唯一入口 (大一統註冊三個平行領域藍圖)
│
├── TroubleShooting_SHIN_YEONG.md  # 🚗 模組一：新詠停車場維運與狀態機日誌
├── TroubleShooting_BI_RSAI.md     # 🦏 模組二：小美犀房務備品與落帳維運日誌
├── TroubleShooting_KEYCARD.md     # 🔑 模組三：華豫寧門禁製卡系統維運日誌
│
├── tests_data_pool/          # 🏗️ 大一統測試資產數據池 (與業務程式碼完全平級)
│   ├── liveam_action_fixtures.json  # 🔑 門禁 9 大 Action_cod 測資清單
│   ├── aiello_product_fixtures.json # 🦏 小美犀備品料號與財務科目清單
│   └── shin_yeong_car_fixtures.json # 🚗 車辨常用白名單車牌清單
│
├── hardware/                 # 📡 邊緣端/廠商主動發砲模擬腳本庫
│   ├── simulate_camera.py    # 🚗 模擬地下室車辨相機拍牌抵達腳本
│   └── simulate_speaker.py   # 🦏 模擬小美犀音箱全生命週期故事線腳本
│
├── server/                   # 🏗️ 沙盒核心引擎
│   ├── __init__.py
│   │
│   ├── parking/              # 🚗 【模組一：新詠停車辨識系統】
│   │   ├── __init__.py       # 導出 parking_bp 藍圖
│   │   ├── routes.py         # 接收 PMS 白名單異動與發動車輛抵達路由
│   │   └── vendors/
│   │       ├── base.py                 # 車辨策略基底類別
│   │       └── vendor_shin_yeong.py    # 新詠資料洗滌與正規化策略實作
│   │
│   ├── amenity/              # 🦏 【模組二：小美犀房務備品與入帳系統】
│   │   ├── __init__.py       # 導出 amenity_bp 藍圖
│   │   ├── routes.py         # 內置在店住客庫，接收 2 支 GET 查詢與 3 支 POST 入帳
│   │   └── vendors/
│   │       ├── base.py                 # 房務策略基底類別
│   │       └── vendor_br_aiello.py     # 小美犀 12 大核心欄位與特殊 JSON 語意洗滌
│   │
│   └── keycard/              # 🔑 【模組三：華豫寧門禁製卡鎖系統】
│       ├── __init__.py       # 導出 keycard_bp 藍圖
│       ├── routes.py         # 內置訂單/卡片庫，迎擊德安 6 支製卡/消卡/逆查指令
│       └── vendors/
│           ├── base.py                 # 門禁策略基底類別
│           └── vendor_liveam.py        # 華豫寧 72小時 Token 簽發與訂單狀態機維護
│
└── tests/                    # 🧪 【本地閉環盲測】
    ├── __init__.py
    └── test_local_sandbox.py # 封存的離線離網單元 Pytest 測試腳本