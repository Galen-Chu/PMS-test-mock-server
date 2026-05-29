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