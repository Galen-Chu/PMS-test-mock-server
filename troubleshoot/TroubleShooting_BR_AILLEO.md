# 🪵 API 自動化測試整合除錯日誌 (Troubleshooting & Architecture Log)
# 🦏 TroubleShooting_BI_RSAI.md —— 小美犀 (BR) 房務備品與入帳自動化串接日誌

本文件持續記錄德安 Athena PMS 系統與外部智慧語音系統聯調自動化框架時，所遭遇的**環境配置、網路拓撲、資料結構（Schema）以及商業邏輯校驗**之核心挑戰與處理解法。

---

## 🛠️ 核心 API 路由合約矩陣

| # | HTTP Method | API 路由端點 | 業務功能分類 | 觸發時機與物理現實 |
|---|-------------|--------------------------------------------|--------------|-------------------|
| 1 | `GET` | `/external/vendor-sync-data/room-pay/room-nos` | 被動房號查詢 | 客人用語音點餐/備品前，查驗在店住客記帳權限。 |
| 2 | `GET` | `/external/vendor-sync-data/room-pay/mifare-nos` | 被動卡號查詢 | 客人於場域刷房卡時，逆查綁定之房號與住客主檔。 |
| 3 | `POST` | `/external/vendor-sync-data/room-pay` | 餐廳住掛入帳 | 服務/餐點送達後，將消費金額正式打入 Folio 房間帳。|
| 4 | `POST` | `/external/vendor-sync-data/room-pay-cancel` | 餐廳住掛取消 | 餐點沖正或客人退點時，執行紅字作廢帳項交易。 |
| 5 | `POST` | `/external/vendor-sync-data/room-billing` | 房務服務入帳 | 異質備品付費或房務部衍生雜項之獨立扣款流程。 |

---

## 📅 Log 27: 異質系統平台化擴充——開闢小美犀房務備品 `amenity` 藍圖模組
* **日期**：2026-06-04
* **戰術定位**：
  宣布停車辨識模組成功達到 Production-ready 驗收。因應全新「小美犀房務備品物聯網串接」測試需求，正式發動平台化（Platform-level）擴充。
* **架構演進實作 (Blueprint Scale-up)**：
  1. **無痛解耦掛載**：於 `server/` 底下新增 `amenity/` 封閉目錄，嚴格遵循職責分離（SoC）原則，切斷與 `parking/` 模組的交叉干擾。
  2. **單一隧道多路複用**：於根目錄 `main.py` 透過 `app.register_blueprint(amenity_bp)` 進行聯調路由大一統註冊。專案維持共用 Port 5000 與單一 ngrok 穿透隧道，大幅免除重新校準雲端 Webhook 與網路配置之手工維運成本。
* **效益**：
  驗證了本測試沙盒框架極強的「多異質系統並存與高擴充性」底層基因。技術基礎設施正式跨入智慧飯店語音備品派工的全新領域知識（Domain Know-How）驗證期。
  
---

## 📅 Log 28: 小美犀 BR 房務串接啟動——五大雙向路由規格確立與日誌開闢
* **日期**：2026-06-05
* **架構背景**：
  停車辨識測試完全收網。跨入第二階段「小美犀語音備品與物聯網入帳」功能串接。本案涉及飯店業最嚴謹的「帳務處理（Folio Auditing）」與「身分查驗（In-House Auth）」，相較於車辨的白名單異動，此模組具備更高的交易原子性（Atomicity）要求。
* **技術戰術實施**：
  1. 開闢專屬維運文件 `TroubleShooting_BI_RSAI.md`，實施異質系統日誌解耦。
  2. 規劃「2支GET被動防禦查詢」與「3支POST非同步帳務匯入」之路由邊界，完全適配 Flask 藍圖與策略模式骨架。
* **預期效益**：
  透過沙盒平台化多路複用的優勢，不改動網路與 ngrok 基礎設施，直接進入小美犀數據流量清洗與高傳真帳務測試期。

---

## 📅 Log 29: 全域環境變數升級——建立小美犀帳務端點與專屬查詢參數（Params 合約）
* **日期**：2026-06-05
* **重構背景**：
  為了讓同一個沙盒引擎能並行處理車辨（SHIN_YEONG）與備品入帳（BR）兩種不同廠商的帳務、通信流量，必須對全域核心資產 `config.py` 進行環境變數的多路複用（Multi-plexing）擴充。
* **技術重構點 (Config Schema Scale-up)**：
  1. **廠商代碼解耦**：獨立開闢 `REAL_PARAMS_AMENITY`，將 `thirdParty` 變數指名為 `"BR"`，以因應德安雲端對帳務推播的異質洗滌規範。
  2. **端點路由矩陣化**：封裝 `REAL_BASE_URL_AMENITY` 基底，完整衍生出 2 支 GET 身份查驗與 3 支 POST 消費入帳之全量真實 QA 雲端 URL，為後續 `routes.py` 與模擬主動音箱發砲腳本提供乾淨的靜態依賴基礎。
* **效益**：
  在配置層面完成了雙異質系統的平滑切分，確保測試流量在打向真實 QA 雲端時，不會發生帳務代碼污染車辨日誌的非預期損害。

---

## 📅 Log 30: 實作小美犀第一支 API——房號被動查詢與 417 異常代碼防禦
* **日期**：2026-06-05
* **技術重構點 (In-House Auth Implementation)**：
  1. **建立在店暫存主檔**：於 `server/amenity/routes.py` 內置 `mock_inhouse_db` 記憶體字典，高真重現飯店在店（In-House）住客多維度帳項模型。
  2. **合約多態洗滌**：於 `VendorBRStrategy` 實作 `transform_room_nos_query_response`，將沙盒數據轉換為符合官方範例之 JSON Array 列表嵌套結構，並實施 `guestStatus` 與 `chargeInfo` 的布林映射。
  3. **417 語意對齊**：嚴格實作當 `keyword`（房號）未命中時，外發 `HTTP Status 417` 與指定 `{"code": "1001"}` 報錯合約，完美解決德安 TraceLog 偵測邊界。
* **效益**：
  小美犀事前身分校驗鏈路順暢打通，沙盒正式具備應對智慧音箱被動查帳的防禦能力。

---

## 📅 Log 31: 實作小美犀第二支 API——房卡晶片內碼逆查與 417 卡號防禦
* **日期**：2026-06-05
* **技術重構點 (Card-to-Room Reverse Lookup)**：
  1. **製卡關係對照表**：於 `routes.py` 擴充 `mock_card_mapping_db` 記憶體對照表，還原飯店前台實體 Mifare 晶片發卡的時空關係。
  2. **多維度鏈路檢索**：實現「卡號 ➔ 房號 ➔ 住客主檔」的雙層逆向檢索鏈路，並由 `VendorBRStrategy` 複用高內聚洗滌機制，輸出一致的 12 欄位 Array。
  3. **異常語意攔截**：未命中卡號時外發 `HTTP 417` 與指定的 `{"code": "1002"}` 代碼，徹底補齊身分查驗防禦線的第二道灰色地帶。
* **效益**：
  小美犀在實體場域（餐廳/販賣機）刷卡消費的事前校驗功能全量封裝完畢。

---

## 📅 Log 32: 實作小美犀第三支 API——餐廳消費主明細入帳與 Folio 房間帳動態累加
* **日期**：2026-06-05
* **技術重構點 (Financial Settlement Implementation)**：
  1. **主明細合約洗滌**：於 `VendorBRStrategy` 擴充 `parse_pms_room_pay` 策略，將 `roomPayMain` 與 `roomPayDetail` 的複雜嵌套欄位進行原子化抽取。
  2. **交易流存檔與累加**：於路由層開闢 `mock_transaction_db` 歷史單據庫，鎖定 `orderNos` 作為唯一憑證主鍵；並在入帳成功時，將金額實時增量累加（Delta Add）至在店住客主檔之 `sum_item_total`，實現帳務鏈路高真傳真。
  3. **身分不對齊防禦**：當 `ciSerial` 與 `roomNos` 發生 race condition 或不對齊時，外發 `HTTP 417` 與指定 `{"code": "1001"}` 訊息，阻斷非法入帳。
* **效益**：
  沙盒平台正式具備對異質物聯網系統執行記帳與 Folio 房間帳增量更新的記帳能力。

---

## 📅 Log 33: 實作小美犀第四支 API——餐廳住掛紅字反向沖正與官方非標準語意防禦
* **日期**：2026-06-05
* **技術重構點 (Financial Reversal Implementation)**：
  1. **單號交易狀態機追溯**：於 `/room-pay-cancel` 路由攔截 URL `orderNos` 參數，對齊歷史交易庫 `mock_transaction_db`，執行 Idempotency 校验，嚴防重複沖正。
  2. **紅字反向扣除（Folio Purge）**：查核無誤後，發動邏輯反轉（Delta Subtraction），將原入帳金額從住客主檔之 `sum_item_total` 中扣除。並結合沙盒布林狀態（`enabled=False`），高真模擬「客房已結帳禁止取消」之會計邊界。
  3. **非標準合約語意還原**：於 `VendorBRStrategy.transform_room_pay_cancel_success_response` 內強制模擬官方大寫開頭 `Code`/`Message` 與小寫開頭 `acctNos` 混雜的特殊 JSON 結構，精準保護小美犀聯調端不崩潰。
* **效益**：
  餐廳消費「日常入帳 ➔ 逆向沖正」的財務雙向閉環在沙盒環境完全攻克落地。

---

## 📅 Log 34: 實作小美犀第五支 API──房務付費備品平面明細入帳與五大雙向路由大成大合龍
* **日期**：2026-06-05
* **技術重構點 (Housekeeping Billing Complete)**：
  1. **平面清單合約解析**：於 `VendorBRStrategy` 實作 `parse_pms_room_billing` 策略，將平面 `roomNos` 搭配物資 `items` 陣列的產品編號、數量進行精準抽取。
  2. **歷史庫擴充與防禦**：於路由層擴充 `mock_inhouse_db`，導入 2403 實戰房號；並在入帳期校驗住客的「邏輯啟用狀態（`enabled`）」，完美還原「已退房結帳禁止入帳」之房務邊界。
  3. **空回執合約對齊**：入帳成功時，外發標準 `HTTP 200 OK` 與極簡 JSON 空物件，完美適配小美犀物聯網中繼平台的通信回執規格。
* **大一統結案宣告**：
  至此，小美犀（thirdparty=BR）五大核心 API 在沙盒框架內全面落成。與既有之停車車辨（SHIN_YEONG）模組各司其職、並存運作，專案正式躍升為跨領域的「大一統飯店異質系統 Staging 沙盒平台」。

---

## 📅 Log 35: 串接時序與角色鏡像釐清——宣告沙盒平台之「小美犀廠商扮演者」立場
* **日期**：2026-06-05
* **架構心法澄清 (Role Alignment & Mirror Theory)**：
  明確定義本 Staging 沙盒專案在小美犀（`thirdparty=BR`）模組中的角色定位。雖然 API 規格書（SA 文件）源自德安 PMS（Server 端規範），但本專案在實施 `USE_REAL_SERVER = True` 的跨系統整合測試時，本質上是**「反過來全面扮演小美犀（Client 廠商端）」**。
* **數據流向確立 (Data Directionality)**：
  1. **被動路由作為規格參照**：本地 `routes.py` 內建的 5 支端點負責在本地隔離環境中（`USE_REAL_SERVER = False`）進行契約自我驗證。
  2. **主動腳本發動真實進攻**：在實戰聯調期，將由前端腳本（如即將開發之 `simulate_speaker.py`）全權複製小美犀官方的 Request Body 欄位結構，主動向遠端德安 QA 雲端發動串接轟炸，並被動接收德安回傳之財務單號（Response），藉此達成雙向高傳真聯調。
* **效益**：
  徹底理清了 Request（原料發送者）與 Response（收條回傳者）在異質系統對撞時的時空倒錯感，為下一階段「實打實進攻真實 QA 雲端」奠定了毫無認知偏差的底層邏輯。

---

## 📅 Log 36: 實作大一統主動測試腳本——解鎖小美犀故事線全生命週期雙向對撞測試
* **日期**：2026-06-05
* **架構決策 (Testing Strategy Decision)**：
  否定將「音箱查詢」與「機器人送餐」拆分為獨立腳本的冗餘構想。採取「單一腳本、五階段故事流水線（Scenario Pipeline）」設計。確保跨路由的核心財務單號憑證（`orderNos`）能在一體化記憶體週期內完美傳遞，杜絕資料斷層。
* **技術戰術工程點**：
  1. 實作 `hardware/simulate_speaker.py` 腳本，完美抄襲小美犀與派送機器人中繼平台之官方 Request Header 與主明細 Body 序列化結構。
  2. 貫通「Phase 1 房號校驗 ➔ Phase 2 卡號查驗 ➔ Phase 3 餐廳入帳 ➔ Phase 4 房務扣款 ➔ Phase 5 紅字沖正」之 100% 商業閉環控制鏈路。
  3. 支援雙模環境調度，切換 `USE_REAL_SERVER = True` 即可攜帶大腦身份金鑰（REAL_TOKEN）實打實攻克真實德安 Athena QA 雲端。
* **效益**：
  本專案正式具備了高內聚、高自動化的主動對撞聯調戰力。CLI 輸出可一鍵還原飯店物聯網實體世界之「查詢、出車、扣款、沖帳」全量軌跡，專案完整度達到商業完全體水準。

---

## 📅 Log 37: 遠端雲端聯調環境校準——德安真實測資動態對齊與會計邊界攻堅
* **日期**：2026-06-08
* **聯調瓶頸突破 (Live Environment Alignment)**：
  發現在 `USE_REAL_SERVER = True` 狀態下，模擬腳本因使用靜態寫死之房號與單號，遭遠端德安 QA 雲端之會計核心與住客主檔校驗（SQL Constraint）攔截。確認異質系統聯調之大前提為「數據狀態時空對齊」。
* **測試戰術調整 (Live Data Mocking)**：
  1. **前台狀態機連動**：確立測試前置作業——必須先於德安 Athena 前台實質完成特定客房（如 `2403`）之 Check-in 入住與 Mifare 房卡綁定，使雲端資料庫產生實時在店（In-House）之住客資產。
  2. **參數動態餵入**：將前台產生之真實 `checkInSerial`（住客序號）與卡號提取並反向灌入 `simulate_speaker.py`，確保 GET 查詢與 POST 入帳之原料 100% 契合真實雲端之會計科目防禦線。
* **效益**：
  理清了自動化測試腳本與實體生產環境資料庫之間的動態依賴關係，為後續多場景、大流量的實打實帳務對撞清除了最後一哩路。

---
