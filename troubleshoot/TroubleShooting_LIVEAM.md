# 🔑 TroubleShooting_KEYCARD.md —— 維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM) & 華豫寧 (WAFERLOCK & LIVEAM) 門禁製卡自動化串接日誌

本文件專職紀錄維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁電子鎖系統（LIVEAM）與德安 Athena PMS 系統對接之沙盒實作、訂單卡片狀態機演進以及跨模組小美犀卡號逆查聯調日誌。

---

## 🛠️ 核心 API 路由合約矩陣

| # | HTTP Method | API 路由端點 | 業務功能分類 | 觸發時機與實體場域物理現實 |
|---|-------------|--------------------------------------------|--------------|-------------------|
| 1 | `POST` | `/api/Auth/login` | 廠商身份鑑權 | 德安 PMS 定時或製卡前主動調用，取得有效期 72 小時的憑證代幣（Token）。 |
| 2 | `POST` | `/api/Order` | 建立入住訂單 | 德安前台辦理日常入住（CKI）時發動，在門禁系統內預先建立「身分 ➔ 房號」的靜態權限約束。 |
| 3 | `PUT` | `/api/Order` | 啟用客房權限 | 前台實質完成 Check-In 接待。德安將 `checkinTime` 填入當下時間，正式解鎖客房感應進場之實體開門憑證。 |
| 4 | `POST` | `/api/OrderCard` | 新增訂單卡片 | 櫃檯將實體 Mifare 卡片感應，德安將特定訂單（OrderID）與卡片唯一碼（cardUid）進行物理綁定。 |
| 5 | `DELETE`| `/api/OrderCard/{oid}/{cuid}` | 刪除註銷卡片 | 旅客退房（CKO）、取消入住（CIX）或卡片遺失補發時觸發，德安主動下發指令，銷毀該卡片之客房感應權限。 |
| 6 | `POST` | `/api/Operation/getCardInfo/{pmrId}` | 卡片資產逆查 | 模擬實體讀卡機感應卡片瞬間，拿卡片 CUID 逆查門禁主檔，提供跨模組小美犀刷卡記帳（mifare-nos）的動態對照原料。 |

---

## 📊 德安 PMS 資料庫 Action_cod 與 維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM) API 映射矩陣 (PMS Config Mapping)

本矩陣用以定義德安 Athena PMS 內部核心異動代碼（`Action_cod`）與維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁沙盒（LIVEAM）底層狀態機的實體映射邊界。此表為未來 PMS 參數設定（Config Setup）與封包稽核之最高指導原則。

| 序號 | 德安資料庫動作代碼 (`Action_cod`) | 飯店前台物理事件場景 | 維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)沙盒對應 HTTP Method & API 端點 | 沙盒內部狀態機運作與防禦邏輯 |
|:---:|:---|:---|:---|:---|
| **1** | `CKI` | **日常入住登記** | `POST /api/Order`<br>➔ `PUT /api/Order` | 德安雙擊連發：先 POST 建立「房號➔身分」約束，隨後 PUT 寫入 `checkinTime` 激活客房感應權限。 |
| **2** | `CREATE_CARD` | **前台製作/發放實體卡** | `POST /api/OrderCard` | 接收卡片內碼 `cardUid` 進行物理綁定，**並自動反查 roomID 跨模組注入小美犀對照表**。 |
| **3** | `DELETE_CARD` | **退房銷卡 / 換卡註銷** | `DELETE /api/OrderCard/{oid}/{cuid}` | 從記憶體卡片庫物理銷毀該卡片資產，同步撤銷小美犀跨模組刷卡掛帳權限。 |
| **4** | `CIX` | **取消入住 (Cancel CKI)** | `DELETE /api/OrderCard/{oid}/{cuid}` | 旅客取消訂房，德安主動下發銷卡指令，強制封鎖並註銷已發放之開門憑證，防禦非法入侵。 |
| **5** | `CHANGE_RESERVATION` | **變更/修改住客訂房檔** | `PUT /api/Order` | 客人變更姓名、聯絡資訊時觸發，沙盒採非破壞性覆寫（Update）更新主檔。 |
| **6** | `CHANGE_ASSIGN_ROOM` | **前台換房 (Switch Room)** | `PUT /api/Order` | 客人要求更換房間，德安帶著全新 `roomID` 進行 PUT 覆寫，實時轉移實體客房感應權限。 |
| **7** | `CHANGE_CKO_DATE_TIME`| **變更預退時間 (續住延遲)**| `PUT /api/Order` | 旅客要求延遲退房（Late CKO），德安動態更新 `preOutTime`（落日截止線）實施授權延展。 |
| **8** | `READ_CARD` | **讀卡機驗卡 / 逆查** | `POST /api/Operation/getCardInfo/{pmrId}` | 物理感應瞬間，拿卡片 UID 逆查門禁主檔，實現 InMemory JOIN 撈取關聯房號與訂單。 |
| **9** | `RMC` | **移除房間 (Remove Room)**| `PUT /api/Order` 或 獨立銷帳 | 清除或隔離該訂單掛鉤的 `roomID`，通常與前台未排房、取消排房之落日防禦邏輯連動。 |

---

## 📅 Log 41: 異質整合下一階段評估——提出「模擬第三方製卡機 (Keycard Mock Server)」戰略藍圖
* **日期**：2026-06-08
* **戰略評估背景 (Architectural Evaluation)**：
  於真實德安 QA 雲端環境（USE_REAL_SERVER = True）聯調期，發現房卡卡號逆查（`/mifare-nos`）高度依賴實體場域之製卡機硬體寫入與動態對照。在無實體硬體連線狀態下，雲端資料庫之卡號映射處於真空狀態，導致聯調受阻。
* **技術解決藍圖 (Keycard Sandbox Proposal)**：
  評估利用現有大一統 Flask 藍圖架構，增設 `server/keycard/` 平行模組。反向扮演「製卡機廠商（如 VingCard/Salto）」，被動接收德安前台 CKI 階段下發之製卡號令（POST），並於沙盒內部記憶體動態生成虛擬 Mifare 流水號並實施自動綁定（Auto-binding）。
* **預期測試效益**：
  徹底切斷對實體製卡硬體與人肉前台製卡操作的依賴。使 Staging 平台具備「德安自動點火製卡 ➔ 沙盒動態吃單對照 ➔ 小美犀刷卡無痛逆查」的全物聯網（Full IoT）閉環自動化對撞能力。

---

## 📅 Log 42: 門禁製卡沙盒啟動——解耦角色轉換思維與大一統製卡路由矩陣確立
* **日期**：2026-06-09
* **架構定位澄清 (Native Strategy)**：
  評估維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)電子鎖系統之聯調特性。確認門禁系統在飯店物聯網中屬於「被動命令執行者（HTTP Server）」。因此，本沙盒無須像車辨或音箱一樣進行發射端（Client）之角色轉換。本模組直接以「維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)廠商原生視角」開闢端點，迎擊德安 PMS 主動下發之製卡號令。
* **技術戰術實施**：
  1. 開闢專屬維運日誌 `TroubleShooting_KEYCARD.md`。
  2. 確立 1 支 Auth 登入、2 支 Order 訂單控制（POST/PUT）以及 2 支 Card 卡片資產控制（POST/DELETE）之核心大一統矩陣。
* **預期效益**：
  建構「德安前台點擊製卡 ➔ 沙盒實時吃單並動態生產卡號對照表」的高真權限閉環，徹底炸開真實 QA 雲端環境中房卡逆查（`/mifare-nos`）的資料真空瓶頸。
  
---

## 📅 Log 43: 實作維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)第一支 API——身份鑑權發卡與 400 欄位防禦
* **日期**：2026-06-09
* **技術重構點 (Auth Token Generation)**：
  1. **建立權限保險箱**：於 `routes.py` 內置 `liveam_session_vault` 記憶體集合，用以追蹤與檢索沙盒簽發出的有效 Session。
  2. **合約精準洗滌**：於 `VendorLiveamStrategy.authenticate_login` 嚴格對齊 Swagger 規格。驗證成功時輸出雙欄位 JSON 結構（`id`/`token`）；未命中時反向輸出包含 `error`、`desc`、`msg` 三維度的 `HTTP 400` 報錯合約。
* **效益**：
  維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)沙盒之第一道通關大門完全落成，為後續德安主動下發訂單與卡片號令提供了合法權限基礎。
  
---

## 📅 Log 44: 實作維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)第二、三支 API——訂單動態權限狀態機與多態攔截（401/404/409）
* **日期**：2026-06-09
* **技術重構點 (Order Lifecycle Implementation)**：
  1. ** Token 安全護城河**：封裝全域 `verify_liveam_token` 安全切面，對所有 Order 路由實施 401 Unauthorized 攔截，確保 Staging 安全邊界。
  2. **唯一性約束與 409 防禦**：於 `/api/Order` (POST) 內置 `liveam_order_db` 暫存字典。當 `id`（訂單單號）發生資源衝突時，精準外發 HTTP 409 報錯。
  3. **非破壞性覆寫與 404 防禦**：於 `/api/Order` (PUT) 實現動態狀態機演進。精準偵測當單號真空時拋出 404；成功時覆寫 `checkinTime`，完美模擬實體卡鎖從「預備狀態 ➔ 實質感應解鎖」的物理現實。
* **效益**：
  維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁系統在沙盒底層具備了完整的「權限宣告」與「權限激活」雙狀態演進能力，完全有實力承接德安 PMS 點擊入住時的主動流量。
  
---

## 📅 Log 45: 實作維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)第四、五支 API——實體發卡綁定與銷卡註銷（解鎖跨模組小美犀大連動）
* **日期**：2026-06-09
* **技術重構點 (Card Asset Implementation & Cross-BP Mapping)**：
  1. **資產綁定與衝突防禦**：實作 `/api/OrderCard` (POST)。校驗 `orderID` 是否存在、且 `cardUid` 未被佔用（409 防禦），成功則將卡片資產歸戶儲存。
  2. **跨模組反向數據注入（核心突破）**：發卡成功瞬間，系統自動反查訂單綁定的 `roomID`，並**實時、自動跨模組注入小美犀路由的 `mock_card_mapping_db` 中**。完美實現「德安前台製卡 ➔ 沙盒自動生成卡號映射 ➔ 小美犀刷卡順暢掛帳」的 100% 全自動化物聯網閉環。
  3. **註銷消卡與安全清洗**：實作 `/api/OrderCard/{oid}/{cuid}` (DELETE)。支援從 Path 參數提取主鍵並執行物理銷毀，成功時同步從小美犀記憶體中抽回房卡掛帳權限，高真還原退房消卡的財務稽核安全邊界。
* **效益**：
  維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)（LIVEAM）門禁製卡模組全量落成！沙盒正式具備與德安前台製卡功能 100% 對撞的實力，卡號真空瓶頸被一舉擊碎。

---

## 📅 Log 46: 實作維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)第六支 API——卡片資產跨表逆查與 Staging 聯調跨藍圖收網
* **日期**：2026-06-09
* **技術重構點 (Cross-Module Portal Joint)**：
  1. **動態 Path 參數攔截**：實作 `/api/Operation/getCardInfo/{pmrId}`。精準捕獲 Path 中的 `{pmrId}`（卡片唯一內碼 CUID），實施 Token 防禦性校驗。
  2. **記憶體內多表關聯查詢（InMemory JOIN）**：打破資料孤島。當卡片命中時，以 `orderID` 為紐帶，非破壞性地逆向跨表檢索 `liveam_order_db`，動態提取出最關鍵的物理資產——`roomID`（房號）。
  3. **格式完全適配**：於 `VendorLiveamStrategy.transform_card_info_response` 還原真實門禁系統之卡片屬性與查詢時戳（QueryTimestamp），提供 100% 高真度之硬體回執。
* **大一統結案宣告**：
  維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)門禁製卡系統（LIVEAM）全量 6 支 API 端點在沙盒內全線落成。本模組與小美犀（BR）完成了深度的記憶體對照綁定。至此，整個 Mock Server 已進化為同時具備「車辨流量洗滌、語音消費掛帳、門禁訂單狀態機演進」的三合一飯店全場景自動化測試 Staging 平台。

---

## 📅 Log 47: 破冰大重構——透過 Swagger 修正 Header 錯位與 Token 真空狀態
* **日期**：2026-06-09
* **實戰發現（SA 文件重大落差）**：
  經由 Swagger UI 成功封包逆向工程分析，揪出德安後端實際部署之 API 規格與原 SA 文件存在實質錯位：
  1. **Header 欄位更名**：原 `athena`/`hotel` 於真實系統被強制覆寫為 `bacchus-athenaid`/`bacchus-hotelcod`。
  2. **Token 防禦真空**：小美犀查核端點底層未鎖定 `Authorization` 承載權限（Bearer Token），純靠 Nginx 集團標頭放行。
* **重構實施**：
  1. 覆寫 `config.py`，拔除小美犀無效 Token 宣告，全面改採 `bacchus-` 高真標頭字典。
  2. 精簡 `simulate_speaker.py` 通信引擎，一鍵模擬 Swagger 物理流量。
* **效益**：
  徹底驅散因文件不對齊導致的 500/400 灰色迷霧。腳本正式具備與德安真實雲端完全重合的通關密碼。

---

## 📅 Log 48: 數據庫行為代碼大一統對齊——完成門禁高內聚映射矩陣記檔
* **日期**：2026-06-10
* **架構優化背景 (Audit Trail Alignment)**：
  透過逆向檢索德安 PMS 資料庫之交易行為異動檔（`Action_cod`），揪出前台高達 9 種細分之會計與接待事件。為了防禦未來在 Staging 設定聯調時的組態錯位，必須在軟體設計層面完成「多對一」高內聚邏輯收攏。
* **技術對照點**：
  確立了德安前台縱向細分的 9 大操作（如 `CHANGE_ASSIGN_ROOM`、`CHANGE_CKO_DATE_TIME`），在維夫拉克 & 華豫寧 (WAFERLOCK & LIVEAM)地端控制器視角中，皆能完備地收攏於 `PUT /api/Order`、`POST /api/OrderCard` 與 `DELETE` 等 5 支核心狀態機 API 中，大幅減輕 Mock 路由維護成本。
* **效益**：
  本維運日誌正式成為具備商業標準的「系統對撞互查字典」，為下一階段德安前台網址綁定與全功能整合測試提供 100% 的組態依據。
