# 🌡️ Room Control 房控模組開發規劃(新模組:roomcontrol)

> 版本:v1(2026-09-02)
> 決策背景:2026-09-02 與 SA 確認——**frontdesk 模組之廠商不做了**(原規劃 `plan-frontdesk-module.md` 取消);
> 改以 **roomcontrol 模組為優先**,且 **ACTION_COD = `ROOM_STA`(房況推送)與 `ROOM_INF`(房況查詢)兩類 API 必須先做**。
> 本文 = 契約盤點(已入庫的 sa8/sa9 範例)+ 模組設計 + 分期 + 規格缺口清單。
> 前置:案例參數化已合併(e9b92cb);所有新案例必須宣告 ParamSpec(design §9/§12 硬約束)。

---

## 0. 摘要

- `roomcontrol` = 第四模組(parking/amenity/keycard 之外),vendor = 華豫寧 LIVEAM
  (sa6 標題即「PMS **房控**房卡梯控串接 華豫寧 LIVEAM」;與 keycard 同廠商、不同關注點)。
- **ROOM_STA / ROOM_INF 是「廠商→PMS」方向的 XML 匯入介面**(HTTP 端點 `POST /third-party/import-sync-files`,
  sa8 QA / sa9 SIT 皆已定義)——房控系統把房況推給 PMS、或查詢 PMS 房況。
  這是沙盒**第一個 XML-over-JSON 介面**(requestBody 是包在 JSON 裡的 XML 字串)。
- RC0(骨架 + ROOM_STA/ROOM_INF 兩案,mock XML 管線)**可立即動工**,不需等 SA;
  位元語意/ROOM_INF 回應形狀等規格缺口見 §2,不阻塞 RC0 的閉環斷言(先斷言 procStatus + RETN-CODE)。

---

## 1. 契約盤點(全部已在 sa_docs,附出處)

> ✅ 2026-09-03 SA 正式文件入庫:**`sa_docs/sa10_a7_pms_xml.txt`**(A7PMS串接信息XML說明 V1.2,2026-09-02 改版)
> ——本節原由 sa8/sa9 swagger 範例反推的契約已全數獲得正式文件證實,並補齊位元表/代碼表/回應形狀。

### 1.0 傳輸層(sa10「訊息交換呼叫方式」+ sa8/sa9 swagger)

- **HTTP GET 閘門版**(sa10 明載):`德安網址?athena=25&hotel=01&thirdParty=TT&TxnData=<XML>&Randomstr=1&istom=1`
  (istom=1 TxnData 用 URLEncode、4 用 Base64;URL 內 `#` 需寫 `%23`;實際 URL 客戶環境備妥時提供)
- **REST 版**(sa8/sa9):`POST /third-party/import-sync-files`(請求 C001.xml,回傳 C001.xml)
- **RC0 實作 REST 版**(在 QA/SIT swagger 有定義、可測);REAL 實測用哪版待 SA 確認。

### 1.1 REST 版契約(sa8/sa9)

```
請求  VendorImportSyncDataRequest  { athenaId, hotelCode, thirdPartyCode,
                                      requestDataList: [ { requestBody: <XML 字串>, fileName: "C001.xml" } ] }
回應  200 → [ VendorImportSyncDataResponse { id, athenaId, hotelCode,
              procStatus,           # true=成功(小程式移檔) / false=失敗(xxx_ret_err.xml)
              responseBody: <回應 XML 字串>, fileName } ]
錯誤  400 / 417 ApiDataValidErrorResponse、500 ApiResponse   ← 與既有 vendor-sync 家族同款錯誤信封
```
- 識別欄位對齊現有環境矩陣:`athenaId`/`hotelCode` = 各環境 `ATHENA_ID`/`HOTEL_COD`;
  `thirdPartyCode` = 廠商代碼(**實際值待確認**,暫定 "LIVEAM")。

### 1.2 ROOM_STA — 廠商推送房況(請求/回應 XML 範例:sa8 VendorRequestData / VendorImportSyncDataResponse example)

```xml
<!-- 請求(SAMPLE 2:送全部房況) -->           <!-- 回應 -->
<ROWSET><ROW>                                <ROWSET><ROW>
  <REVE-CODE>0300TT4190 </REVE-CODE>           <SEND-CODE>0300TT4190</SEND-CODE>
  <ROOM_NOS>2403</ROOM_NOS>                    <ACTION_COD>#ROOM_STA#0101001100100000#</ACTION_COD>
  <ACTION_COD>#ROOM_STA#010101011001#</ACTION_COD>   <RETN-CODE>0000</RETN-CODE>
  <ACTION_STA>1</ACTION_STA>                   <RETN-CODE-DESC>1112 Set #ROOM_STA#...</RETN-CODE-DESC>
  <ACTION_DAT>2009/06/03 10:06:43</ACTION_DAT> <MSG-ID>0000</MSG-ID><MSG-DESC>Transaction done successfully.</MSG-DESC>
</ROW></ROWSET>                               </ROW></ROWSET>
```
- 同族 action 範例(同一段 sa8 example,RC2 候選):`CLEAN`(清潔動作,ACTION_STA=1)、`#RMTEMP#26C#`(室溫,A7 前台顯示)。
- `REVE-CODE`(廠商→PMS)與回應 `SEND-CODE` 成對:ROOM_STA/RMTEMP/CLEAN = `0300TT4190`。

### 1.3 ROOM_INF — 廠商查詢 PMS 房況(含多個住客的帳務編號)

```xml
<ROWSET><ROW>
  <REVE-CODE>0300TT1090</REVE-CODE>
  <ACTION_COD>ROOM_INF</ACTION_COD>
  <ROOM_NOS>0770</ROOM_NOS>
  <ACTION_DAT>2009/06/03 10:06:43</ACTION_DAT>
</ROW></ROWSET>
```
- ⚠️ **回應 XML 形狀 sa8/sa9 皆未附範例**(房況內容 + 帳務編號的欄位結構未知)——§2 缺口 Q2。

### 1.4 sa7(LiveAM 側)房控面——後期(RC3)

`GET /api/Room/getRoomIOData/{id}`(房控狀態)、`getAirConditionData/{id}`(溫控)、`getRoomIOData`(全房)、
RoomCtrl 18 端點(強制供電/預冷/空調/溫度/風速/窗簾/燈迴/服務燈/解鎖/電梯)——**PMS→廠商**方向,契約完整,屬 RC3。

---

## 2. 規格缺口(2026-09-03 sa10 入庫後更新)

| # | 問題 | 狀態 |
|---|---|---|
| Q1 | `#ROOM_STA#` **16 位房況字串定義** | ✅ sa10「房間房況順序說明」:1 Keyhouse(1拔卡0插卡)/2 Keybox(1插卡0拔卡)/3 冷氣/4 總電源/5 鐵捲門/6 一氧化碳(1動作0無)/7 防盜(0動作1無)/8 緊急(0動作1無,F=OFF_LINE)/**9 房間清潔(1請打掃/2打掃中/3待巡房/4巡房中/0清潔完成——德安收 0 設乾淨房)**/10 勿擾/11 房門(0開1關)/12–16 保留;預設 `#1000001100100000#`;**RC2.5 sa11**:A7 落庫為 PBX_DT 欄位級解碼(mock 同步),位8=F 斷線三連動(SOS=off/RCU_ONLINE=N/CLEAN_ROOM 保舊值);MAIN_POWER 單值族極性與位4 相反(寫入反轉歸一) |
| Q2 | **ROOM_INF 回應 XML 形狀** | ✅ sa10 A6:一住客一 ROW;ROOM_STA CHAR(1) O住人/S參觀/V空房;GUEST_STA K關帳/O開帳;CI_SER/ALT_NAM/稱謂/姓名/CI_DAT/CI_TIM/ECO_DAT/TEL_NOS/BIRTH_DAT/ADVBAL_AMT/CCARD_AMT/LANG/VIP_STA + RETN 尾列;**RC2.5 sa11 補強**:A7 實際先查 ROOM_MN——O 逐住客列、V/R/S 全欄位空值單列(僅 ADVBAL_AMT/CCARD_AMT=0)、未登錄房 → RETN 9999「ROOM not found.」、內部錯 → RETN 1001(失敗信封無 ROOM_NOS/ACTION_DAT) |
| Q3 | `ACTION_STA` 值域與語意 | ✅ sa10 B4:1=設定、0=清除;逐 action 對照(勿擾/緊急/房門/清潔 0–4)已入 vendor 模組註解 |
| Q4 | REVE-CODE/SEND-CODE 完整代碼表 | ✅ sa10 訊息列表(雙向全表):PMS→廠商 CKI/CKO/RMC/CIX/COX/QUERY/CLEAN_STA/SET_PRECOOL(0300901xTT 系);廠商→PMS ROOM_INF 0300TT1090/BILL_LIST 0300TT1190/RETURN 0300TT4290/ROOM_STA 系 0300TT4190/KeyBox 0300TT4390 |
| Q5 | `thirdPartyCode` 實際值 + REAL 端點 + 鑑別 | 🔶 **部分解(2026-09-03)**:廠商代碼已定——**MINXON 民笙=81、CHAOFENG 超烽=86**(掛雙廠商各三案);REAL_QA 實測:REST 端點 `/third-party/import-sync-files` 可用、免 Authorization(僅 bacchus 身分 Header)、**ROOM_INF 已回 XML 實料**(房 101→ROOM_STA=V、RETN 0000)。⚠️ 遺留:(a) **A10 RETURN 經 REST 回 procStatus=false+全 null**(雙廠皆同——支援方式待 SA 確認,測試已標 xfail);(b) QA 不驗 thirdParty 代碼(假代碼也收);(c) CHAOFENG 回應 data[] 混 [null 失敗殼, 成功實料](runner 已掃描挑項);(d) 回應 SEND-CODE 固定回 TT 模板形式(0300TT1090)而非回映廠商代碼——mock 維持 sa10 契約(同 REVE),實測差異記錄於此;(e) **RC2 實測(2026-09-04,雙廠一致)**:CLEAN/#RMTEMP# 推送 → procStatus=false + RETN 9999「ADD item」、B5 KeyBox(4390) → 全 null 殼——與 A10 RETURN 同群待 SA;推送回應 SEND-CODE 有正確回映廠商代碼(030081/0300864190);QA 負面拒收風格 = 200 信封 + 全 null 殼(壞 XML/未知 action)或 9999 + 「Room configuration not found…Room null」(缺房號)——mock 契約(417/9999 XML)差異已固化測試 |
| Q6 | `procStatus=false` 的錯誤處理與重送契約 | ⏳ sa10 僅檔案介面側註解(procStatus=false → xxx_ret_err.xml 不移檔);REAL_QA 的 RETURN 失敗形狀已實錄(全 null 項) |
| Q7 | 真實測試台房控設備前提(實體/模擬/無) | ⏳ RC3 的 REAL 驗證深度 |

---

## 3. 模組設計(沿用 registry.py 三層擴充路徑)

```
server/roomcontrol/__init__.py       # roomcontrol_bp 掛載(main.py 一行)
server/roomcontrol/routes.py         # POST /third-party/import-sync-files(mock PMS 側)
server/roomcontrol/vendors/base.py   # 策略介面:XML 組裝(build_*)/解析(parse_*)/回應判定
server/roomcontrol/vendors/vendor_LIVEAM.py
mock_roomcontrol_db                  # {room_no: {status_bits, temperature, last_clean, updated_at}}
orchestrator/runners.py              # module="roomcontrol" 案例(發砲端=模擬房控廠商)
```

- **mock 路由行為**:解析 requestDataList 內 XML → ROOM_STA 更新 `mock_roomcontrol_db[room_no]` →
  回 `[{procStatus: true, responseBody: <SEND-CODE/RETN-CODE 0000 XML>}]`;ROOM_INF 回該房現況
  (形狀待 Q2,先最小對稱實作);XML 壞格式 → 417 ApiDataValidErrorResponse(對齊錯誤信封)。
- **閉環斷言(房控版;2026-09-03 依 sa10 修正)**:ROOM_INF 回的是「住客現況 + ROOM_STA(O/S/V)」,
  不回 16 位房況字串——故閉環走 **push 落庫 → `GET /roomcontrol/internal/state` 回讀位元串一致**
  (LOCAL only;前例 parking `/parking/internal/whitelist`);ROOM_INF 案則斷言一住客一 ROW + ROOM_STA + RETN-CODE 0000。
- **XML 稽核**:發送時 `steps.request_body` 自然存原始 XML 字串(HTTP 稽核);
  runner 另以**結構化 dict**(room_no/action_cod/action_sta…)存 `request_payload` 供 JSON 稽核與 diff——
  種子與 diff 都對結構化形狀比對,不對整段 XML 字串 diff(避免宣告/空白噪音)。
- **engine urls**:`import_sync` 區塊(各環境 `{base}/third-party/import-sync-files`);header 沿用環境鑑別。
- **UI 觸點僅兩行 label**:`api.py` `_MODULE_LABEL` 與 `app.js` `moduleLabel()` 加 `"roomcontrol": "🌡️ 房控"`。

### RC0 案例選單(兩案先行,ParamSpec 草案)

| case_id | 情境 | ParamSpec 草案 |
|---|---|---|
| `rc_room_status_push` | ROOM_STA 推送房況(RETN-CODE 0000 + 1112 Set) | room_no 房號 str "2403";status_bits 房況位元串 str "010101011001"(hint:位元定義待 SA) |
| `rc_room_status_query` | ROOM_INF 查詢房況(procStatus + RETN-CODE 0000) | room_no 房號 str "0770" |

負面路徑(RC2):壞 XML→417、未知 ACTION_COD、ROOM_NOS 缺欄——固定劇本,不宣告 params(參數化設計「不開放」原則)。

---

## 4. 分期

| 期 | 內容 | 工作量 | 前提 |
|---|---|---|---|
| **RC0** | 模組骨架 + XML 管線(組裝/解析/417)+ ROOM_STA/ROOM_INF 兩案 + push 落庫閉環 + 離線測試 + UI label | ✅ **2026-09-03 完成**;同日升級**雙廠商**(MINXON 81/CHAOFENG 86 × push/room_inf/return 六案)+ A10 RETURN mock(含位元串第 9 位→CLEAN_STA 推導閉環) | 無 |
| **RC1** | REAL_QA 實測 + 通關種子入庫 | ✅ **2026-09-04 SA 確認收尾**:ROOM_INF 雙廠回實料(`test_real_roomcontrol_qa.py` 2 passed)+ ROOM_STA 推送經主控台手動實測 OK(2026-09-03);廠商×模組架構已有雛型。遺留(不阻塞,追蹤於 Q5a):A10 RETURN 經 REST 回 procStatus=false+全 null——支援方式待 SA(測試已標 xfail) | — |
| **RC2** | 同族 action(CLEAN/RMTEMP/KeyBox B5)+ 位元級驗證 + 負面路徑補齊 | ✅ **2026-09-04 完成**:雙廠商 × 6 新案(B4 CLEAN→位9 / RMTEMP→室溫 / B5 KeyBox→位2+卡片資訊;負面:壞XML→417・未知ACTION_COD→RETN 9999・缺ROOM_NOS→417),LOCAL 位元級回讀閉環全綠(49 passed);**mock 修正 RC0 潛伏瑕疵**——MSG-DESC/RETN-DESC 雙句點 → 對齊 sa10 單句點。**REAL_QA 實測輪(2026-09-04,引擎發砲 12 案)**:CLEAN/RMTEMP → 9999「ADD item」、KeyBox → 全 null 殼(皆待 SA,Q5e);負面路徑 QA 形狀已固化 `test_real_roomcontrol_qa.py`(8 passed + 8 xfail) | —(sa10 已補齊 Q1/Q3/Q4) |
| **RC2.5** | 逼真度強化(**sa11** = A7 收到廠商 XML 的 SQL 處理,德安內部文件 2026-11-03 取得,原文僅存本機不入庫):①`RETN-CODE-DESC`=`{房號} Set {ACTION_COD}`(sa10「1112」實為房號)②ROOM_MN 房間主檔先行——未知房 → procStatus=false+RETN 9999「ROOM not found.」、沙盒 E 模擬房 → RETN 1001;③V/R/S 空房 → 全欄位空值單列(ADVBAL_AMT/CCARD_AMT=0);④PBX_DT 欄位級解碼(16 位 → KEY_HOUSE/KEY_BOX/AC_STA/MAIN_POWER/RSD/CO_ONE/BG_ALARM/SOS/RCU_ONLINE/CLEAN_ROOM/DND/DOOR_STA);⑤**位8=F 斷線三連動**:SOS=off、RCU_ONLINE=N、CLEAN_ROOM 保舊值不更新;⑥**MAIN_POWER 極性反轉**(第一種單值族 0=on/1=off ↔ 位元串位4 1=開,寫入時反轉歸一);⑦RMTEMP 附 `api=RCU`+RMUPD_DAT;⑧A10 RETURN 改走房間主檔(R/S 如實、E 不入回報);⑨自助端點 `internal/rooms`(登錄動態房號)+`internal/reset`(還原種子)。雙廠 × 3 新案(room_not_found/internal_error/room_sta_offline)→ 24 案 | ✅ **2026-11-03 完成**;RC4(出站 CKI/CKO/COX/RMC/預冷 77987)、03009042TT(暫不使用)、QUERY 排程——暫緩待需求 | sa11 |
| **RC4a** | **IPTV 雲朗(thirdParty=70,2026-11-04 確認)** — sa11 THIRDPARTY_DT_CONF 住客顯示名稱參數切片:`guest_display_name`(GROUP_NOS/ROOM_NOS/LAST_NAM/FIRST_NAM/ALT_NAM/USER_DEFINED 單選,無參數→預設 ALT_NAM)+`user_defined_display_name`(自由輸入;USER_DEFINED 時**不論有無值皆如實傳送,空值=廠商收無資料**)。落地:mock 增 `POST /roomcontrol/internal/thirdparty-conf`(THIRDPARTY_DT_CONF 模擬,值 None=清除)+出站觸發端點(sa10 A1 CKI 出站 XML,REVE=03009010+70,姓名欄 ALT_NAM 依參數解析,房間主檔轉 O;RC4b 起 generalize 為 `/internal/outbound`);ParamSpec 增 `choices` 單選選項(UI 渲染下拉);案例 LOCAL_ONLY(CKI 由 A7 端 C/I 觸發,REAL → SKIP)。新廠商 IPTV ×3 案 → 模組 27 案 | ✅ **2026-11-04 完成**;離線/在線 127 passed・20 skipped | sa11 參數表 |
| **RC4b** | **補齊 QA 參數其餘 action_cod**(2026-11-04 QA DB 截圖:廠商 70 之 THIRDPARTY_DT_CONF 掛 **CKI/RMC/COX/ROOM_INF** 四 action,各帶 `guest.display.name`/`user.defined.display.name`,THIRDPARTY_VERSION=DEFAULT XML)——CKI 之外再補三向:①**RMC**(sa10 A3 換房出站,REVE=03009030+70,OROOM/NROOM 欄,舊房清空 V、新房住人 O;案例後反向換回還原種子);②**COX**(sa10 A5 C/O 還原出站,REVE=03009021+70,欄位同 CKI 形);③**ROOM_INF**(sa10 A6 查房**回應**的 ALT_NAM 依 ROOM_INF action 參數解析;案例同時證明各 action 參數獨立——CKI 設 LAST_NAM 不污染 ROOM_INF 回應)。結構調整:conf 模型升為 `{TP:{ACTION:{PARAM_COD:VAL}}}`、參數鍵改 QA 逐字 PARAM_COD(dotted)、`/internal/cki` → `/internal/outbound`(action_cod 入參)、種子房 +2408。IPTV ×3 新案(皆 LOCAL_ONLY)→ 模組 **30 案** | ✅ **2026-11-04 完成**;離線 130 passed・20 skipped。CKO(A2)/CIX(A4)見 RC4c | sa10 A3/A5/A6 + QA 截圖 |
| **RC4c** | **補齊原始 6 API 串接案例**(2026-11-04 QA DB THIRDPARTY_DT 截圖:廠商 70 掛載 **6 API=出站 5(CKI/RMC/COX/CKO/CIX)+入站 1(ROOM_INF)**;參數表僅蓋 4 個 action_cod——CKO/CIX 出站僅 REVE/ACTION_COD/ROOM_NOS/ACTION_DAT 四欄、**無住客姓名欄**,本就無參數可言)——①**CKO**(sa10 A2 退房出站,REVE=03009020+70,房間轉 V);②**CIX**(sa10 A4 C.I還原出站(客製,力廣參數指定),REVE=03009011+70,重點「不改髒房」,mock 房況值域無髒房 → 同回 V)。兩案皆兩步流程(CKI 入住 V→O → 觸發 O→V),結束自我還原種子可重複跑;房況非 O → 400。IPTV ×2 新案(LOCAL_ONLY)→ **6 API 全覆蓋、模組 32 案** | ✅ **2026-11-04 完成**;離線 132 passed・20 skipped;/runs 兩輪 8 案全 PASS | sa10 A2/A4 + QA THIRDPARTY_DT 截圖 |
| **RC5** | **A7 出站接收端**(`/third-party/outbound-receive`)——沙盒兼扮演**廠商側**,收 A7 於 C/I、C/O、換房等時機主動推送的出站 XML(sa10:「廠商須提供一個 URL,接收德安傳送的入住、退房、換房資訊」)。緣起:使用者要在 QA DB `THIRDPARTY_DT`(廠商 70,TRANS_TYP=URL)填 `THIRDPARTY_URL`——沙盒原本只有反方向 `/third-party/import-sync-files`(廠商→PMS),無 PMS→廠商接收面。落地:形狀全相容(GET ?TxnData= istom 1=URLEncode/4=Base64、POST raw/JSON requestBody/multipart,後綴路徑亦收)、記 `outbound_received` 供回讀(`/roomcontrol/internal/outbound-received`)、回 sa10 ACK XML(SEND-CODE 回映 REVE、RETN 0000;壞 XML → 9999);隧道卡 register_urls 增 `IPTV_70` 鍵供一鍵複製 | ✅ **2026-11-05 完成**(離線測試 + ngrok 外部自測) | sa10 出站說明 + QA THIRDPARTY_DT 截圖 |
| **RC3** | sa7 PMS→廠商房控面(讀取 ×3 + 高值寫入:unlockDoor/switchAC/mandatoryPower) | 約 1 天 | Q7 設備前提 |

---

## 5. 待決策

| # | 決策 | 狀態 |
|---|---|---|
| D1 | ~~frontdesk 模組~~ | ❌ 2026-09-02 SA 確認廠商不做,規劃取消、文件移除 |
| D2 | roomcontrol 優先、ROOM_STA/ROOM_INF 先行 | ✅ 2026-09-02 SA 確認(本文) |
| D3 | ROOM_INF 回應形狀的 mock 定案 | 等 Q2;RC0 先最小對稱實作,SA 定案後改斷言 |
| D4 | 與 keycard 模組共用資源(房號→roomID 轉換) | RC3 視需要,暫不耦合 |

---

## 6. 驗收準則(DoD)

1. 每支新情境:`@register_scenario` + **ParamSpec 宣告**(hint 用 SA 術語;room_no 可標 echo_fields 對應 XML 內 ROOM_NOS);
   UI 零改動(僅 RC0 的 label 兩處)。
2. XML 契約:組裝/解析對齊 sa8/sa9 範例逐欄(REVE-CODE/SEND-CODE/ACTION_COD/ACTION_STA/ACTION_DAT);
   偏離處註明原因;XML 宣告與 UTF-8 編碼一致。
3. 斷言雙層:HTTP procStatus **且** responseBody 內 RETN-CODE=0000(任一不符即 FAIL)。
4. 種子入 `tests_data_pool/verified_payload_logs.json`(結構化形狀);新案例補離線測試,
   `tests_localFullStackClose/` 全量(2026-10-07 計 70;local 三檔離線自動 skip、real 檔 @skipif 防護)全綠;無 overrides 行為不變。
5. LOCAL(loopback)閉環實跑通(push→query 回讀一致);REAL 至少一輪(RC1),前提不足處標「待驗」。
