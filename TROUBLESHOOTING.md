# 🪵 API 自動化測試整合除錯日誌 (Troubleshooting & Architecture Log)

本文件持續記錄在構建 PMS (物業管理系統) 與外部車牌辨識系統聯調自動化框架時，所遭遇的**環境配置、網路拓撲、資料結構（Schema）以及商業邏輯校驗**之核心挑戰與處理解法。

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