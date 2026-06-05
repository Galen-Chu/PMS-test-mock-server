# 📸 PMS 停車辨識廠商自動化整合 Staging 沙盒框架

本專案（`PMS-test-mock-server`）為一套專門針對德安 Athena PMS 系統開發的**高傳真（High-Fidelity）生產級外部廠商模擬沙盒**。透過將架構進行「職責分離（SoC）」重構，完美還原實體車辨相機與廠商後端伺服器的物理通信邊界，並具備全自動批次迴圈連發功能，用以高效驗證住客行車紀錄之落地。

---

## 📂 專案目錄結構 (Architecture)

本專案採用微服務化模組架構，將被動監聽、邊緣硬體主動發砲、以及離線盲測完全解耦：

```text
PMS-test-mock-server/
│
├── config.py                 # 全域核心設定檔 (集中管理所有外部雲端與本地 Token)
├── main.py                   # ⚡ 專案唯一啟動入口 (負責註冊所有廠商藍圖並掛載 Port 5000)
├── GUIDE.md                  # 技術框架與維運操作指引說明文件
├── .gitignore                # 排除環境變數快取
│
├── server/                   # 📦 【模擬後端核心模組】
│   ├── __init__.py           # 套件宣告
│   │
│   ├── parking/              # 🚗 【車辨停車功能整合模組】(由原 mock_server.py 切割重組)
│   │   ├── __init__.py       # 初始化並宣告 parking 藍圖 (Blueprint)
│   │   ├── routes.py         # 統一的外部通信路由 (不含廠商死邏輯，只調度 Strategy)
│   │   │
│   │   └── vendors/                    # 🗃️ 規格策略庫 (Strategy Pattern)
│   │       ├── __init__.py             # 策略套件入口
│   │       ├── base.py                 # 定義所有車辨廠商必須遵循的標準接口合約 (Abstract Class)
│   │       ├── vendor_SHIN_YEONG.py    # SHIN_YEONG 廠商規格實作檔 (對齊目前的現行 4 欄位官方規格)
│   │       └── vendor_PAYTRONEX.py     # PAYTRONEX 廠商規格實作檔 (用來驗證未來欄位變更、微調的客製化規格)
│   │
│   └── amenity/              # 🦏 【房務備品系統整合模組】
│       ├── __init__.py       # 初始化並宣告 amenity 藍圖 (Blueprint)
│       ├── routes.py         # 統一的外部通信路由 (負責接 Webhook 與逆向同步)
│       │
│       └── vendors/                    # 🗃️ 規格策略庫 (Strategy Pattern)
│           ├── __init__.py             # 策略套件入口
│           ├── base.py                 # 定義音箱語音解析必須遵循的標準接口合約 (Abstract Class)
│           └── vendor_BI_RSAI.py       # BI_RSAI 廠商規格實作檔 (JSON 規格序列化策略)
│
├── hardware/                 # 📸 【模擬前端硬體】
│   ├── __init__.py           # 全域環境初始化與自動路徑防禦注入 (免除子腳本重複 append 路徑)
│   └── simulate_camera.py    # 專職批次車辨發砲迴圈腳本 (不需修改，直接適配新路由)
│
└── tests/                    # 🧪 【本地閉環盲測】
    ├── __init__.py
    └── test_local_sandbox.py # 封存的離線離網單元 Pytest 測試腳本