# 🔌 LiveAM / Room Control / Front Desk API 串接可行性評估

> 版本:v2(2026-09-02;v1 為全廠商擴張盤點,依指示聚焦改寫)
> 範圍:**華豫寧 LiveAM 平台**之三個 API 面——LiveAM 核心(Auth/卡片操作)、Front Desk(櫃台訂單/製卡作業)、Room Control(房控)。
> 依據:`sa_docs/sa6_liveam.txt`(德安 PMS↔華豫寧 SA)、`sa_docs/sa7_liveam_swagger.json`(LiveAM 完整 Swagger)、沙盒現行程式碼(`orchestrator/runners.py`、`server/keycard/`)。
> 本文為評估規劃,不含實作;實作排程在參數化(`design-case-parameterization.md`)合併之後(2026-09-02 序列決策)。

---

## 0. 結論摘要

| API 面 | 串接可行性(沙盒 LOCAL) | 契約完備度 | 主要缺口 | 決策依賴 |
|---|---|---|---|---|
| **LiveAM 核心**(Auth/Operation/卡片) | ✅ 高——模式已在線上(9 案例) | sa7 Swagger 完整 | getToken/resetCard/權限查詢/logout 未案例化 | 無 |
| **Front Desk**(櫃台訂單/製卡) | ✅ 高——sa6 情境 × 沙盒對照僅缺 3 情境 | sa6 + sa7 齊 | 換房二情境、CHANGE_RESERVATION 改 C/I、客製路由 5 條無 runner | AppLink/密碼面待業務確認 |
| **Room Control**(房控) | ⚠️ 中高——契約最完整,但範圍待確認 | sa7 Swagger 完整(23 端點全定義) | 沙盒完全沒有房控面(0 端點 0 案例) | **sa6 未列房控為 PMS 串接範圍**;真實環境設備前提 |

一句話:**前兩面是「補案例」(路由/契約大都已在),房控面是「開新面」(值得,但要先確認範圍)。**

---

## 1. 沙盒現況(keycard 模組)

- 已上線 **9 個有 runner 案例 + 1 個 UNIMPLEMENTED**(`card_issue_exception`),全部 vendor=WAFERLOCK/LIVEAM。
- 沙盒路由(`server/keycard/routes.py`)其實**比案例多**:另有 read-card、delete-card、door-card、door-cards、`/api/Operation/getToken` 五條已實作、無案例。
- 策略檔 `vendor_WAFERLOCK_LIVEAM.py`:登入鑑權(帳密/專案)、訂單 payload 洗滌、卡片資訊回應——新增端點沿用此模式。
- 引擎側(`engine.py` urls)已有 keycard_login / roomid / getcardinfo / order / ordercard 五組 URL;新端點加一行即可。
- 回歸基準:`tests_localFullStackClose/` 現 33 測試(離線可跑 26)全綠——含 2026-09-02 參數化 Phase 1 新增 11 檔。

---

## 2. LiveAM 核心面(Auth / Operation / 卡片)— 可行性:高

### 2.1 sa6 定義的整合前提(已在沙盒落地)
- 每支 API 都要 Token;失效回傳代碼,重取要先 login(沙盒:`keycard_bad_token` 已守護 401 路徑)。
- Token 72 小時有效(sa6);登入帳密/專案由測試環境提供(sa6 有測試台資訊,沙盒用 staging 值)。
- 卡機編號(pmrId)為本機環境設定(sa6 測試台 `E8EB1BCCE94F1`,沙盒預設 `801F12A3D8CA`)。

### 2.2 缺口(契約在 sa7,沙盒補路由+案例即可)

| 候選 | 端點 | 現況 | 備註 |
|---|---|---|---|
| 取得操作 Token | POST `/api/Operation/getToken` | **路由已存在、無案例** | sa6 製卡流程第一步行之替代路徑 |
| 重置卡片 | POST `/api/Operation/resetCard/{pmrId}` | 無路由 | 製卡例外流程搭檔(見 §3 card_issue_exception) |
| 查詢房客卡權限 | GET `/api/OrderCard/permissions/{orderId}/{cardUid}` | 無路由 | **加值最高**:製卡後驗權限,讓製卡管線有真正的閉環斷言 |
| 查詢訂單卡片 | GET `/api/OrderCard/{oid}` | 無路由 | — |
| 登出 | POST `/api/Auth/logout` | 無路由 | Token 生命週期完備(login→用→logout) |

風險:低。全部是讀取或可冪等模擬的操作,mock DB 已有訂單/卡片狀態可支撐。

---

## 3. Front Desk 櫃台面(訂單/製卡作業)— 可行性:高

> ⚠️ 2026-09-02 SA 確認:**frontdesk 模組之廠商不做了**,獨立 frontdesk 模組規劃取消(文件已移除)。
> 本節保留為契約盤點參考;其中已在 keycard 上線的情境(CKI/CIX/改退房/製卡/刪卡)不受影響,缺口情境(換房二情境等)暫緩。

### 3.1 sa6 櫃台動作 × 沙盒案例對照(核心價值表)

sa6「德安製卡作業/流程」定義的 ACTION_COD 動作,逐一對照 `runners.py`:

| sa6 動作 | 內容 | 沙盒現況 |
|---|---|---|
| CREATE_CARD | login→Order→getCardInfo→OrderCard | ✅ `keycard_make_card` |
| CKI | PUT Order 填 checkinTime → 開門 | ✅ `keycard_checkin_open` |
| CIX | PUT Order 填 checkoutTime → 卡失效 | ✅ `keycard_checkout_invalidate` |
| CHANGE_CKO_DATE_TIME | PUT Order 改 preOutTime | ✅ `keycard_change_checkout` |
| CHANGE_RESERVATION | PUT Order 改 **preInTime、preOutTime** | ⚠️ 半覆蓋——只改 preOutTime,改 preInTime(改預住日)無案例 |
| **CHANGE_ASSIGN_ROOM**(製卡後換房) | GET getRoomIdByName(新房號)→ PUT Order 改 roomID | ❌ **無案例** |
| **ROOM_CHG**(入住後換房) | 同上,但訂單已 C/I,須帶 checkinTime 重綁新房 | ❌ **無案例** |
| DELETE_CARD | DELETE OrderCard(可退房還原不建回) | ✅ `keycard_revoke_card` |
| WalkIn 製卡鈕 | sa6:「可以不要 call api」(無訂單還原功能) | 不做(sa6 明示可略) |

**技術可行性:換房二情境的零件全部已在**——`_kc_room_id`(房號→roomID)與 `PUT /api/Order`(routes.py:203)皆存在,只缺 runner 組裝。`clean_order_payload` 已含 roomID 欄位。這是 Front Desk 面最高 CP 值的缺口。

### 3.2 客製路由補 runner(路由已存在、registry 已掛或未掛)

| 候選 | 路由 | 現況 |
|---|---|---|
| 製卡例外重試 | POST `/key-card-management/liveam/create-card` | UNIMPLEMENTED(`card_issue_exception`)——參數化設計 §9 已預告補 runner 時一併宣告 params |
| 讀卡 | GET `/key-card-management/liveam/read-card/{pmrId}` | 路由在、無案例 |
| 刪卡(客製) | DELETE `/key-card-management/liveam/delete-card` | 路由在、無案例 |
| 門卡查詢 | GET `/key-card-management/door-card/{mifareNos}` | 路由在、無案例 |
| 門卡批次刪 | DELETE `/key-card-management/door-cards` | 路由在、無案例 |

### 3.3 App/密碼面(契約在、業務前提待確認)

- **AppLink**(POST/GET `/api/AppLink/*`):sa6 有完整流程(先建訂單→取 startup 欄位→簡訊/Email/QR 給手機,首機 Master)+ 廠商 QA 結論「**不能與德安會員 app 結合**」。技術可行,但要不要推給測試單位是業務決策。
- **RoomPasswd**(訂單密碼,`/api/RoomPasswd/*`):對應 App 辦理入住;sa6 明載 LIVEAM_ORDER_MN 對照欄位,且 `canAppCheckin` 目前**皆為 N**——業務開關未開,建議等決策。

---

## 4. Room Control 房控面 — 可行性:中高(**2026-09-02 SA 確認優先開發**)

> ✅ 2026-09-02 SA 確認:房控**升為優先**,且 ACTION_COD=`ROOM_STA`(房況推送)與 `ROOM_INF`(房況查詢)兩類 API 先行。
> 開發規劃移至 **`plan-roomcontrol-module.md`**(含 sa8/sa9 XML 匯入介面契約盤點與 RC0–RC3 分期);本節 §4.3 的 Q1(範圍)已解除。

### 4.1 契約盤點(sa7,23 端點全部有定義)

兩個相似視角,擇一優先即可:

- **Room 客房視角**(建議優先——`getRoomIdByName` 已在用,房號→id 轉換路徑一致):
  - 讀取:GET `/api/Room/getRoomIOData/{id}`(房控狀態:emergency/doorOpened/doorOnline/powerSaverOn/service/roomStatus/acPowerOn/temperature/devices)、GET `/api/Room/getAirConditionData/{id}`
  - 寫入:POST `/api/Room/unlockDoor/{id}`、POST `/api/Room/switchAC/{power}/{id}`、POST `/api/Room/stopEmergency/{id}`
- **RoomCtrl 門控視角**(18 端點):getRooms/getDevices/getRoomIOState/getAirConditionState + 控制類 PUT——mandatoryPower(強制供電)、precooling(預冷)、SwitchAC、setTemperature、setFanMode、conditionMode、CtrlCurtain(窗簾)、lightsOn/lightsOff/lightsMaster(燈迴)、serviceLight(服務燈)、unlockByUuid、remoteUnlockElevatorFloor(電梯樓層)。

**參數/回應模式極一致**:路徑帶 room id(integer)+ 小 body(`OnlyIntValue`/`OnlyStringValue`/`TimeoutPara`),回應 `RoomIOData`/`RoomIOState`/`RoomAirConditionState`/`ResponseInfo`。契約完備度是三面中最高。

### 4.2 沙盒模擬策略(LOCAL 完全可行)

- 狀態機 mock:per-room 房控狀態物件(電源/空調開關/溫度/風速/模式/燈迴/窗簾/服務燈),寫入端點改狀態 → 讀取端點回新值 → **下命令→回讀**閉環斷言(同 keycard checkinTime 的驗證模式)。
- 種子:幾間房的房控設備對應(`RoomIOData.devices`),沿用 mock DB 模式。
- LOCAL_OFFLINE:組 payload 對 sa7 schema 逐欄規格比對,既有閉環機制直接套用。

### 4.3 風險與決策依賴(這是「中高」而非「高」的原因)

1. **範圍決策**:sa6 的德安 PMS 串接清單(thirdparty_dt:CKI/CKO/CIX/COX/改C/O日,加 type=梯控)**未包含房控**。房控可能是 LiveAM 平台具備、但德安 PMS 本期不用的面——沙盒做不做,先與 SA/業務確認。
2. **梯控交錯**:`remoteUnlockElevatorFloor` 與 sa6「若要梯控加 type」呼應,和 sa6 明載的 `POST /api/Order/elevator/{id}`(電梯權限)同屬梯控決策,建議一併問。
3. **REAL 驗證深度**:真實 LiveAM 測試台是否有房控設備(或僅模擬)決定 REAL 環境驗證能到哪層;沙盒 LOCAL/OFFLINE 不受影響。

---

## 5. 建議分期(聚焦三面;均排於參數化之後)

| 期 | 內容 | 工作量 | 前提 |
|---|---|---|---|
| **F1** | LiveAM 核心 + Front Desk 補案例:換房二情境(CHANGE_ASSIGN_ROOM、ROOM_CHG)+ CHANGE_RESERVATION 補 preInTime + 客製路由補 runner ×5(含 card_issue_exception 轉正) | 約 1 天 | 僅參數化合併 |
| **F2** | 閉環加值包:OrderCard permissions 權限查詢 + OrderCard/{oid} + getToken 案例化 + logout | 約 0.5 天 | 無 |
| **F3** | Room Control 讀取面(GET 狀態 ×3 + getRooms)+ 高值寫入(unlockDoor、switchAC、mandatoryPower) | 約 1 天 | **§4.3 範圍確認** |
| **F4** | Room Control 其餘寫入(溫度/風速/模式/窗簾/燈迴/服務燈)+ 梯控二端點 | 約 1 天 | §4.3 範圍+梯控決策 |
| **F5** | App/密碼面(AppLink ×2、RoomPasswd) | 約 0.5 天 | §3.3 業務決策 |

---

## 6. 驗收準則(每支新 API 的 Definition of Done)

1. 沙盒路由契約(請求/回應/錯誤碼)逐欄對齊 sa7 Swagger(schema 名稱可對照),偏離處註明原因。
2. `@register_scenario` + **ParamSpec 宣告**(hint 用 sa6/sa7 術語,echo_fields 標回映欄位)——參數化設計 §9/§12 硬性約束。
3. expected 種子入庫,LOCAL_OFFLINE 規格比對可跑。
4. 新案例補離線測試;`tests_localFullStackClose/` 全量(現 33,離線 26)全綠。
5. LOCAL(loopback)實跑通,含負面斷言(如換房後舊房卡應失效的驗證)。
6. REAL(LiveAM 測試台)至少實測一輪;設備/前提不足處明確標「待驗」。
7. UI 零改動(詮釋資料驅動);需要改 UI 即架構警訊,先回設計。

---

## 7. 待確認清單(本聚焦範圍)

| # | 問題 | 影響 |
|---|---|---|
| Q1 | ~~房控(Room Control)是否屬德安 PMS↔LiveAM 本期整合範圍?(sa6 未列)~~ | ✅ 2026-09-02 SA 確認:屬範圍且優先(ROOM_STA/ROOM_INF 先行,見 `plan-roomcontrol-module.md`) |
| Q2 | 梯控:`/api/Order/elevator/{id}` 與 `remoteUnlockElevatorFloor` 是否啟用?(sa6:「目前沒做」) | F4 |
| Q3 | AppLink/RoomPasswd(App 入住)是否推展給測試單位? | F5 |
| Q4 | 真實 LiveAM 測試台的房控設備前提(實體/模擬/無) | F3/F4 的 REAL 驗收深度 |
| Q5 | (沿自 v1)每廠商選用 API 清單、PAYTRONEX 回應契約、各環境 DB 測資——非本聚焦範圍,見 v1 盤點,SA 附件抵達後再議 | 其他模組 |

---

*v1(同日草案,已被本聚焦版覆寫、未入庫)曾涵蓋 amenity 錯誤碼補齊、PAYTRONEX 邊界、Athena CRS 面等全廠商盤點;依 2026-09-02 指示移出聚焦範圍,SA 附件抵達後重新擴編。*
