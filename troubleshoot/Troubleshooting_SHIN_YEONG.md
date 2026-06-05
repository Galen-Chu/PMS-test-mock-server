# 🪵 API 自動化測試整合除錯日誌 (Troubleshooting & Architecture Log)
# 🚗 TroubleShooting_SHIN_YEONG.md —— 新詠 (SHIN_YEONG) 停車場與車辨自動化串接日誌

本文件持續記錄德安 Athena PMS 系統與外部車牌辨識系統聯調自動化框架時，所遭遇的**環境配置、網路拓撲、資料結構（Schema）以及商業邏輯校驗**之核心挑戰與處理解法。

---

## 🛠️ 核心 API 路由合約矩陣

| # | HTTP Method | API 路由端點 | 業務功能分類 | 觸發時機與物理現實 |
|---|-------------|--------------------------------------------|--------------|-------------------|
| 1 | `POST` | `/pms-sync-data/check-in` | 日常入住接收 | 當住客入住成功時，推播住客主檔與車牌資料將其實施增量落庫（Upsert），並將憑證初始化為 `enabled: True`，`arrival_time` 預設留空。 |
| 2 | `POST` | `/pms-sync-data/change-checkout-datetime` | 退房延展接收 | 當住客要求延遲退房時觸發，精準覆寫該住客的授權落日截止線（`end_date`），其餘車牌與時間資產原封不動。 |
| 3 | `POST` | `/pms-sync-data/change-car-nos` | 櫃檯車牌異動接收 | 適配前台「新增、清除、更新」車牌三態行為，更新車牌時會收到連續兩發 Webhook（舊車牌停用➔新車牌啟用）依此進行憑證開關切換。|
| 4 | `POST` | `/pms-sync-data/check-in-cancel` | 取消入住接收 | 為防禦實體車輛卡在出口閘門引發客訴，沙盒維持 `enabled: True`，但將 `end_date` 強制縮短為「當下主機時間 + 逃生緩衝分鐘數」。 |
| 5 | `POST` | `/pms-sync-data/night-audit` | 批次夜核名單接收 | 凌晨夜審排程執行時，批次推播隔日預進且有車號之住客原料，沙盒以 `guest_id` 為主鍵進行大量字典堆疊與 Upsert，不執行全盤清空。|
| 6 | `POST` | `/external/vendor-sync-data/car-arrival` | 逆向行車抵達發砲 | 模擬地下室實體相機拍到車牌當下，即時抓取主機當前時間注入 `arrival_time`，逆向砸回真實 PMS 雲端寫入行車日誌。 |
| 7 | `GET`  | `/internal/debug/whitelist` | 內部除錯名單拉取 | 沙盒專屬端點，供自動化相機腳本（`simulate_camera.py`）一鍵撈取全量記憶體資料庫，用以執行邊緣端的狀態感知過濾。 |

---

## 📅 Log 01: Windows 運行時環境隔離與全域套件衝突
* **日期：** 2026-05-25
* **模組/端點：** Pytest 基礎環境建置
* **錯誤現象：** 執行 `pytest test_mock_api.py -v -s` 指令時，系統拋出大面積紅字錯誤：
  `E ModuleNotFoundError: No module named 'responses'`
* **底層原因分析：**
  Windows 作業系統的 `PATH` 環境變數中，微軟商店（Microsoft Store）安裝的全域 Python 路徑權限優先級過高。直接呼叫 `pytest` 時，**路徑搜尋機制 (Path Lookup)** 錯位，導致系統調用了全域編譯器，而非當前專案隔離環境 `.venv` 內部的虛擬編編譯器。因全域冰箱內無 `responses` 套件，進而觸發運行時環境隔離阻斷。
* **解決方案（治本）：**
  貫徹「依賴明確性 (Explicit Dependencies)」，在 CLI 中改用以下明確指令：
  ```bash
  python -m pytest test_mock_api.py -v -s

---

## 📅 Log 02: 本地自建模擬沙盒與真實雲端路由阻斷 (Not Found)
* **日期：** 2026-05-25
* **模組/端點：** 階段一（住客資料同步 - 盲猜端點）
* **錯誤現象：**
  將環境開關切換至真實 QA 雲端環境（`USE_REAL_SERVER = True`）後，調用我們在本地自訂的接收端點，系統直接噴出 Java Tomcat 標準錯誤網頁：
  `HTTP Status 404 – Not Found`
* **底層原因分析：**
  此為典型的**網路拓撲（Network Topology）與角色架構錯位**問題。
  在本地端（Flask + Pytest）的內部互打中，我們可以自由建立 `http://127.0.0.1:5000/vendor/api/...` 作為接收端。但在真實世界中，該資料流屬於 **Webhook (事件推送)** 機制——由 PMS 雲端主動打向廠商公網。
  若直接將此自訂網址硬掛上 Athena 的雲端網域發送（試圖由外部主動 Push 給 PMS），雲端伺服器的網關（API Gateway）根本沒有註冊此路由，因而直接阻斷並回報 404。
* **解決方案：**
  1. **短期戰術：** 調整自動化腳本，在實打真實雲端時，優先略過此未開放的 Inbound 端點，專注於已開放的逆向回傳端點。
  2. **長期戰略：** 深入挖掘官方開發者 Swagger 文件，放棄盲猜路由，改為尋找真實存在於 PMS 雲端的官方 Inbound 同步節點（隨後成功定位出 `/pms-sync-data/` 系列端點）。

---

## 📅 Log 03: 真實官方 Schema 整合時的商業邏輯與外鍵阻斷
* **日期：** 2026-05-26
* **模組/端點：** `/pms-sync-data/check-in` (官方 Swagger 端點)
* **錯誤現象：**
  成功更換為官方 Swagger 提供的複雜 JSON Request Body 後，腳本執行依然回報 `404 Not Found` 或 `500 Internal Server Error`。
* **底層原因分析：**
  真實企業級 ERP/PMS 雲端環境具備強烈的**「資料庫參照完整性（Referential Integrity）」**與防禦性商業邏輯校驗。
  自動化腳本若為了防止資料重複而完全隨機產生 `ciSerial`（入住流水號）或未在系統主檔（Master Data）註冊的 `roomNos`（如動態產生的隨機房號 `A1730`），後端 ORM 框架在進行資料庫關聯查詢（Table Join）失敗時，會判定為「無效資源/幽靈房間」並拒絕寫入，因而拋出 404。
* **對照調校方案（Data-Driven Strategy）：**
  捨棄完全隨機的模擬測資，改採**資料驅動測試（Data-Driven Testing）對照組策略**：
  * **策略一（基線測試）：** 完整封裝 Swagger 提供的 Mock 模型範例（如房號 `"1010"`、流水號 `"20191019000012"`）直接進行基線撞擊。
  * **策略二（實機調校）：** 登入真實 PMS 系統 UAT 前端網頁，複製一組當日合法已 Check-in 的真實住客與實體房號數據，硬編碼（Hardcode）填入 `checkin_payload` 中，藉此順利突破雲端防線。

---

## 📅 Log 04: 官方 Swagger 端點網址路由（Context Path）錯位與成功攻堅
* **日期：** 2026-05-26
* **模組/端點：** `/pms-sync-data/check-in` (真實雲端環境)
* **錯誤現象：** 即便參考了 Swagger 的 Request Body，最初調用時依舊回報 `404 Not Found`。
* **底層原因分析：**
  真實雲端環境的 API Gateway 路由設計較為複雜。在 `config.py` 初始化配置時，盲猜的 Context Path 為：
  `.../pms/api/v3.0/vendor/api/receive-guest-checkin`
  隨後對照 Swagger 修正時，不小心將路徑拼成了：
  `.../pms/api/v3.0/pms-sync-data/check-in`
  經二次交叉比對 Swagger 官方實體請求的完整 URL 後，發現真實的 Gateway 路由節點應為 **`/pms/pms-sync-data/check-in`**（多了一層 `/pms/` 命名空間）。
* **解決方案：**
  修正 `config.py` 終端路徑為：
  ```python
  REAL_URL_CHECKIN = "[https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/pms-sync-data/check-in](https://qa-cloud.athena.com.tw/pms/api/v3.0/pms/pms-sync-data/check-in)"

---

## 📅 Log 05: 真實環境 Webhook 流量攔截與 Swagger 規格滯後之「欄位對齊」
* **日期：** 2026-05-26
* **模組/端點：** `/pms-sync-data/check-in` (真實雲端實機聯調)
* **錯誤現象：** 當真實 PMS 前端網頁觸發 Check-in 業務時，本地 Flask 接收到公網請求，但拋出 `400 Bad Request` 拒收。
* **底層原因分析：**
  此為異質系統整合時常見的 **「文件與真實環境脫節 (Documentation Drift)」**。
  官方 Swagger 提供的是 PMS 內部底層 Table 的全面欄位（如 `roomNos`, `ciSerial`）。但真實 PMS 對外發送 Webhook 給車辨廠商時，經過了隱私過濾層與業務轉換層，實際拋出的 JSON 捨棄了 `roomNos`（房號隱私保護），並將 `ciSerial` 封裝對齊為 `guest_id`，且額外衍生了 `start_date` 與 `end_date` 的有效期限生命週期欄位。
* **解決方案：**
  利用 ngrok 與微型攔截器（Interceptor）成功實施公網「抓包」，獲取最真實的第一手 Production JSON 生產數據。重構 `mock_server.py` 的解包邏輯，全面改採 `data.get("guest_id")` 與 `data.get("guest_name")` 進行防禦性合約綁定，徹底打通真實 PMS 到外部廠商的數據鏈結。

---

  ## 📅 Log 06: PMS 異質系統「全生命週期業務路由」擴增與多型解包防禦
* **日期**：2026-05-28
* **新增端點**：
  1. `POST /pms-sync-data/check-in-cancel` (撤銷刪除)
  2. `POST /pms-sync-data/change-car-nos` (動態更新)
  3. `POST /pms-sync-data/change-checkout-datetime` (生命週期變更)
  4. `POST /pms-sync-data/night-audit` (快取清空)
* **核心設計思維 (Dialectical Design)**：
  在面對多變的 RESTful API 擴增時，面臨「嚴格遵循原始嵌套文檔（如 `parkingSyncDataList`）」與「相容真實雲端客製化極簡 Body」的決策衝突。
  最終採用 **「相容性多型解包（Adaptive Unpacking）」**，優先偵測特定嵌套 Key 是否存在，若無則降級採取扁平化解包。此法能在不重啟、不修改後端代碼的情況下，同時完美吞下自動化盲測腳本與真實公網操作流量。
* **實作成果**：
  成功實作虛擬資料庫字典的 CRUD 完整閉環。透過 `mock_vendor_db.pop()` 與 `mock_vendor_db.clear()` 確保多主機操作下的記憶體資料一致性，達到完全適配 Production 環境的模擬要求。

  ## 📅 Log 07: PMS 狀態機防禦機制與飯店業領域知識（滾房租與接客時序限制）
* **日期**：2026-06-02
* **目標 Table**：`hfd_car_arrival_log` (住客行車抵達記錄表)
* **底層攔截原理 (Domain Logic Analysis)**：
  發現真實 PMS API 在 `200 OK` 的外殼下，內部封裝了嚴格的業務狀態機（State Machine）校驗。
  資料要成功落地至 `hfd_car_arrival_log`，必須滿足雙重合約：
  1. 廠商明細參數啟用（System Configuration Configured）。
  2. 住客生命週期狀態必須滿足 `[System Date == Night Audit Date]` 且 `[Status == Expected Arrival (未入住)]`。
* **架構重構思維**：
  此規則證實了先前將 Mock Server 重構為「雙路由解耦（被動接收與主動相機模擬分離）」的遠見。
  為了驗證此 Log 寫入，必須將測試戰術調整為「前置車辨通知模式」——在 PMS 訂單未辦理 check-in 前，主動由 Mock Server 路由 B 發動逆向通信轟炸，方可突破 PMS 內部狀態機的防禦閘門。

## 📅 Log 08: 相機動態匯入與 Mock Server 資料庫「批次迴圈連發」架構重構
* **日期**：2026-06-03
* **重構核心**：
  解決先前 `simulate_camera.py` 只能單筆盲發、以及與 `mock_server.py` 記憶體暫存資料庫無法關聯的痛點。
  全面打破手工傳參的限制，將發砲機制重構成「全自動動態匯入與 Array 迭代連發」架構。
* **程式碼重構點 (Code Refactoring Details)**：
  1. **Mock Server 端點解鎖**：
     於 `mock_server.py` 開闢 `/internal/debug/whitelist` 除錯路由，將本地 `mock_vendor_db` 字典以 JSON 格式完整外洩，供外部相機腳本提取。
  2. **相機腳本邏輯重構 (解耦死資料)**：
     拔除 `simulate_camera.py` 尾端硬編碼的 `guest_id`。改為先利用 `GET` 請求將 Mock Server 的暫存資料整包匯入。
  3. **Array 遍歷與 For 迴圈機制引入**：
     使用 `for index, target_guest in enumerate(db_data.values())` 迴圈機制，動態遍歷所有從真實 PMS 接收到的有效住客名單。
  4. **合約欄位與時序動態對齊**：
     迴圈內部每筆資料皆動態產生當前的 `arrival_time`，確保 `guest_id`, `car_number`, `guest_name`, `arrival_time` 標準 4 規格 Payload 毫無誤差，以 0.5 秒的頻率緩衝連續逆向推播，直奔真實 PMS 檢核最底層。
* **重構效益**：
  實現了「真實雲端 Webhook 灌水 ➔ 廠商後端自動收集 ➔ 相機迴圈批次連發轟炸」的全自動工業級測試閉環，在操作上達成一鍵自動對齊的雙效目標。

  ## 📅 Log 09: 專案架構微服務化與職責分離 (SoC) 重構
* **日期**：2026-06-03
* **重構核心**：
  為了解決多腳本並存（本地盲測、被動伺服器、主動硬體模擬）導致的專案膨脹與管理混亂，實施物理層級的「職責分離（Separation of Concerns）」。
* **架構分流**：
  1. `server/`：收納 `mock_server.py`，專職 Webhook 流量洗滌與狀態機控制。
  2. `hardware/`：收納 `simulate_camera.py`，模擬邊緣相機硬體之批次迴圈行為。
  3. `tests/`：封存早期離線測試資產，建立雙模測試矩陣（Live-Staging / Local-Sandbox）。
* **技術效益**：
  透過 `sys.path.append` 消除跨目錄引用之耦合性。重構後大幅降低認知負載，專案結構達到 Production 生產級水平，完美支援未來異質系統（如綜合櫃台、退房延長等端點）的模組化擴充。

  ## 📅 Log 10: 包裝初始化機制 `__init__.py` 之角色職責與路徑優化
* **日期**：2026-06-03
* **核心思維**：
  分析 Python 套件初始化機制 `__init__.py` 於模組化分流架構中的三種戰術定位（空白宣告、門面提升、環境預載）。
* **架構優化手段**：
  1. **優化引入路徑**：透過在 `server/__init__.py` 封裝 `from .mock_server import app`，實現高層級模組對核心微服務實例的直取（Direct Access），降低跨模組通信之語法複雜度。
  2. **消除重複代碼**：利用 `hardware/__init__.py` 作為邊緣硬體設備套件的入口閘門，在套件加載首期注入 `sys.path.append` 全域根路徑防禦，徹底斬斷子模組腳本內部的路徑硬編碼依賴。
* **效益**：
  將專案從「多檔案拼湊」升級為標準的「Python SDK 套件模型」，為未來的跨館別多機聯調與自動化 CI/CD 架構鋪平道路。

  ## 📅 Log 11: 專案完全體落地、生產級架構封裝與雲端同步
* **日期**：2026-06-03
* **新增資產**：
  1. `server/mock_server.py` (全事件狀態機控制微服務)
  2. `hardware/simulate_camera.py` (全自動動態匯入批次連發腳本)
  3. `hardware/__init__.py` (全域套件環境與路徑防禦層)
* **架構演進成果 (Final Evolution)**：
  徹底解決初期開發時多腳本雜亂、手動複製參數的痛點。
  透過「物理層職責分離（SoC）」，成功將外部被動 Webhook 監聽、邊緣硬體相機感應、本地單元盲測三者完全解耦。
  在既有德安 PMS 的「夜審營業日時序限制」邊界內，提煉出最優雅的自動化批次對齊測試流，兼顧了測試的「高效率」與「高傳真效果」。
* **專案狀態**：
  已清除所有敏感私鑰字串，完成全模組化重構，程式碼與技術指引正式推播至遠端 GitHub Repository，初版 Staging 沙盒基礎設施完美宣告落成。

  ## 📅 Log 12: Git 分散式版本控制——遠端進度分歧與衝突消解
* **日期**：2026-06-03
* **異常現象**：
  執行 `git push` 時觸發 `Updates were rejected because the tip of your current branch is behind` 阻擋。
* **底層原理 (Git Architecture Analysis)**：
  這是分散式版本控制系統（DVCS）的保護機制。當遠端 Counterpart（GitHub）存在本地儲存庫未包含的 Commit 時，Git 會拒絕非快進式（Non-fast-forward）的推播，以防止盲目覆蓋他人代碼或引發歷史紀錄斷層。
* **解法辯證 (Dialectical Workaround)**：
  1. **方案 A (協作流)**：透過 `git pull` 進行遠端變更整合，透過三方合併（3-way merge）對齊時間軸，防禦性最高。
  2. **方案 B (強攻流)**：在確認個人專案且本地具備「絕對正確真相來源（Source of Truth）」的前提下，使用 `git push -f` 實施強制線性歷史覆蓋。本專案因經歷大幅度 SoC 架構重構，採用強攻流能確保遠端目錄結構達到最純淨的重組狀態。

  ## 📅 Log 13: 多異質系統整合測試架構——利用 Flask Blueprint 實施多廠商模組化分流
* **日期**：2026-06-03
* **決策背景**：
  面對未來新增多個第三方（如門禁、自助機）整合測試需求，評估「多獨立腳本」與「另起專案」之弊端（Port 衝突、ngrok 隧道膨脹、環境變數斷層）。
* **架構決策 (Architectural Decision)**：
  維持單一專案與單一 ngrok 隧道基礎設施，於 `server/` 目錄下引入 Flask Blueprint（藍圖）機制，實施「單一入口、多廠商路由分流」架構演進。
* **技術效益**：
  1. **維運高效率**：多廠商共用 Port 5000 與單一穿透網址，免除繁瑣的網路與隧道對齊成本。
  2. **高擴充效果**：各廠商之記憶體暫存資料庫各自獨立，完全物理隔離，符合職責分離（SoC）原則。

## 📅 Log 14: 多廠商客製化規格解耦——引入策略模式 (Strategy Pattern) 消除路由冗餘
* **日期**：2026-06-03
* **核心挑戰**：
  同功能整合（車辨停車）因不同硬體廠商 API 微調需求不同（如欄位名稱、層級結構差異），導致接收端點出現大量 `if/else` 分支，破壞 Staging 沙盒的泛用性。
* **解決手段 (Design Pattern Application)**：
  1. 於 `server/parking/` 下建立 `vendors/` 策略庫，定義 `BaseParkingVendorStrategy` 抽象介面合約。
  2. 實作 `vendor_a.py` 策略檔，隔離特定廠商專屬的 `parse` 與 `transform` 欄位洗滌邏輯。
  3. 於 `routes.py` 實作策略工廠動態調度，徹底將「路由通信層」與「廠商規格序列化層」完全解耦。
* **優化效益**：
  完全符合「開放封閉原則（OCP）」。未來面對任意新廠商規格微調，僅需擴充策略實作類別，核心骨幹完全免除改動成本。

## 📅 Log 15: 號令型 Webhook 的防禦性編程——夜審路由灰色參數洗滌防禦
* **日期**：2026-06-04
* **架構反思**：
  分析德安 PMS 於 `/night-audit` 端點不攜帶參數之原始 SA 假設，建立沙盒應對遠端系統無預警升級、或底層框架附帶追蹤參數之防禦性設計。
* **防禦優化手段 (Defensive Implementation)**：
  1. **介面抽象化**：於 `BaseParkingVendorStrategy` 擴充 `parse_pms_night_audit` 介組合約。
  2. **非破壞性解碼**：於路由層調用 `request.get_json(silent=True)`，強制包容空 Body 與非標準 JSON 傳輸。
  3. **安全降級（Fail-safe）**：建立 `try-except` 路由最終防線，確保任何未知異常下皆能對外回覆 `200 OK`，杜絕卡死真實 PMS 帳務過天排程。

## 📅 Log 16: 真實流量逆向修正——廢除夜審清空機制改實施動態狀態機 Upsert
* **日期**：2026-06-04
* **流量觀測大發現**：
  經由 ngrok 監聽真實德安 PMS 夜核批次大流量，撈取到完整住客生命週期格式，確認包含 `start_date`, `end_date`, `is_enabled` 等多維度跨度欄位。證實夜審並非純號令，而是具備資料狀態延續性之核心批次傳輸。
* **辯證修正 (Architectural Rectification)**：
  「全面否定一刀切的清空邏輯。」若在 `/night-audit` 路由盲目執行 `clear()`，將毀滅續住（Stay-Over）客人之合法停車憑證。必須改採「增量累積與動態狀態覆寫（Upsert）」策略。

## 📅 Log 17: 異質系統聯調——ngrok 封包通信方向性與 Payload 定位
* **日期**：2026-06-04
* **流量分析判定**：
  確認 ngrok 面板中 `/pms-sync-data/night-audit` 攜帶之 166 bytes `application/json` 數據體為 **HTTP Request Payload**，屬於德安 PMS（Client 端）主動推播至廠商模擬伺服器（Server 端）的入庫原料。
* **業務合約確認**：
  此 Request 的現形，坐實了德安系統在夜審時採用的是「主動批量推播增量資料」之商務邏輯。廠商端之 Response 應維持極簡的狀態回執（如 HTTP 200），將完整運算留於 Request 接收後的 Upsert 儲存期。

## 📅 Log 18: 解決夜審端點實測 Payload 錯位與 PMS TraceLog 報錯異常
* **日期**：2026-06-04
* **異常根因 (Root Cause Analysis)**：
  先前路由因採取「無參數 `clear()`」死邏輯，未實施 JSON 解析與標準回執（Response 合約），導致德安發送引擎之連線日誌（traceLog）判定傳輸失敗並拋出錯誤。
* **重構手段**：
  1. **合約解耦**：於 `VendorAStrategy` 補齊 166 bytes 實測封包的 6 大欄位完整映射洗滌。
  2. **TraceLog 防禦**：路由層補齊 `request.is_json` 格式校驗與標準 JSON 狀態碼（200/400/415）回傳機制，確保德安獲得正確對齊的收條。

## 📅 Log 19: 全路由模組化狀態機重構——全面實施邏輯軟刪除控制
* **日期**：2026-06-04
* **重構核心**：
  配合真實夜審 Payload 狀態欄位的現形，正式宣布廢除虛擬資料庫中粗暴的 `clear()` 與 `pop()` 物理刪除機制。全面將所有串接 PMS 的業務路由（CKI, CIX, CHG_CAR_NOS, NIGHT_AUDIT）轉型為「邏輯狀態機控制（Soft Delete / Status Toggle）」之增量 Upsert 模型。

## 📅 Log 20: 跨系統聯調時空對齊優化——日常業務路由真實起迄時間戳洗滌落庫
* **日期**：2026-06-04
* **核心挑戰**：
  先前日常入住（CKI）與退房延長端點盲目調用本地 `datetime.now()` 覆寫，導致沙盒時間與真實 PMS 測試環境之停滯營業日時序嚴重錯位，無法支援未來生產級硬體邊緣開閘之時間區間過濾。
* **重構手段 (Time-Axis Alignment)**：
  1. **私有型態正規化**：引入 `_normalize_datetime` 函數，自動相容德安斜線（`/`）與橫線（`-`）多元時間格式，統一收攏為標準 ISO 規格字串。
  2. **動態提取與兜底**：優先從 Webhook 數據體（如 `ciDat`, `coDat`）精準截取 PMS 原生時間，僅於缺省欄位時發動本地時鐘補全。

## 📅 Log 21: 業務路由微創分流——日常入住與延長退房職責完全解耦
* **日期**：2026-06-04
* **重構核心**：
  消除先前日常入住（CKI）與延長退房（CHANGE_CKO_DATE_TIME）共用同一洗滌函數的高耦合壞味道（Code Smell）。
* **技術重構點**：
  1. **策略介面原子化**：於策略庫派生出獨立的 `parse_pms_change_checkout` 函數合約，專職處理退房時間之洗滌。
  2. **區域增量更新**：在延長退房時僅更新 `end_date` 與啟用狀態，完美鎖定原入住階段寫入之姓名與起日資產。

## 📅 Log 22: 憑證變更職責收攏——拔除車牌異動路由之時間戳覆寫污染
* **日期**：2026-06-04
* **核心思維 (Separation of State and Event)**：
  釐清「靜態憑證修改」與「實體行車事件觸發」之邊界。車牌變更（`CHG_CAR_NOS`）本質上只是修改靜態授權憑證，車子尚未通過閘門。
* **重構手段**：
  重構 `/change-car-nos` 路由，當 ID 命中時採局部增量覆寫，僅變更 `car_number` 與 `enabled` 狀態。徹底拔除該路由內部對時間軸的修改，使既有入住起迄時間與抵達時間原封不動留存。

## 📅 Log 23: 工業級狀態機優化——車牌變更三態適配與 CIX 逃生落日緩衝實作
* **日期**：2026-06-04
* **核心實戰發現**：
  1. 綜合櫃檯車牌變更（`CHG_CAR_NOS`）具備新增、清除、更新之「三態行為」。其中「更新」行為會觸發兩次連續 Webhook（舊車牌停用 ➔ 新車牌啟用）。
  2. 取消入住（`CIX`）並非物理刪除，而是基於場域客訴防禦機制，傳送啟用狀態，但實質上將落日截止線縮短至「取消當下主機時間 + 限時逃生緩衝」。
* **重構手段**：
  於 `parse_pms_cancel` 中引入 `timedelta` 運算，動態結合全域 `config.CIX_BUFFER_MINUTES`，強制產生標準 ISO 的限時逃生落日時間戳（`end_date`）。

## 📅 Log 24: 奧卡姆剃刀架構翻轉——回歸事件驅動之極簡行車抵達時間戳機制
* **日期**：2026-06-04
* **核心思維突破**：
  反思先前過度提早初始化 `arrival_time` 的架構冗餘。在車輛未實質壓過感應線圈前，暫存庫內之 `arrival_time` 應神聖保持空值（`""`）。
* **優化手段**：
  全面拔除日常接收路由中不必要的本地時鐘演算，落庫時預設為空字串。直至模擬相機發動真實硬體模擬的物理當下（`/car-arrival` 觸發期），才由路由層調用 `datetime.now()` 封裝現時戳，一體化注入本地庫並逆向砸回德安。

## 📅 Log 25: 飯店前台車流時序校準——異質系統整合之實體物理時序修正
* **日期**：2026-06-04
* **商務邏輯重大翻轉**：
  經實務流程辯證，日常入住（CKI）與櫃檯車牌異動（CHG_CAR_NOS）觸發時，實體車輛多半已完成「開進停車場」之動作；亦即 Webhook 流量本質上落後於實體車流。唯有夜間稽核（NIGHT_AUDIT）屬於完全預進之純白名單前置發送。這更加奠定了廠商接收端將 `arrival_time` 預設初始化為空值（`""`）的正確性與客觀性。

## 📅 Log 26: 自動化框架完全體落成——相機狀態感知解耦與全事件邊緣攔截實作
* **日期**：2026-06-04
* **重構核心**：
  將 `simulate_camera.py` 從「盲目全量發砲」升級為「狀態感知（State-Aware）邊緣防禦流」。
* **技術效益**：
  相機腳本遍歷白名單時，若偵測到住客 `enabled == False`（如 CIX 逃生逾時或車牌已被清除），自動發動在地隔離攔截（Skip），精準重現實體現場的「拒絕開閘行為」，使 CLI 終端機成為 Staging 即時聯調之完全體狀態儀表板。