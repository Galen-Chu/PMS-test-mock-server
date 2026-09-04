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
| Q1 | `#ROOM_STA#` **16 位房況字串定義** | ✅ sa10「房間房況順序說明」:1 Keyhouse(1拔卡0插卡)/2 Keybox(1插卡0拔卡)/3 冷氣/4 總電源/5 鐵捲門/6 一氧化碳(1動作0無)/7 防盜(0動作1無)/8 緊急(0動作1無,F=OFF_LINE)/**9 房間清潔(1請打掃/2打掃中/3待巡房/4巡房中/0清潔完成——德安收 0 設乾淨房)**/10 勿擾/11 房門(0開1關)/12–16 保留;預設 `#1000001100100000#` |
| Q2 | **ROOM_INF 回應 XML 形狀** | ✅ sa10 A6:一住客一 ROW;ROOM_STA CHAR(1) O住人/S參觀/V空房;GUEST_STA K關帳/O開帳;CI_SER/ALT_NAM/稱謂/姓名/CI_DAT/CI_TIM/ECO_DAT/TEL_NOS/BIRTH_DAT/ADVBAL_AMT/CCARD_AMT/LANG/VIP_STA + RETN 尾列 |
| Q3 | `ACTION_STA` 值域與語意 | ✅ sa10 B4:1=設定、0=清除;逐 action 對照(勿擾/緊急/房門/清潔 0–4)已入 vendor 模組註解 |
| Q4 | REVE-CODE/SEND-CODE 完整代碼表 | ✅ sa10 訊息列表(雙向全表):PMS→廠商 CKI/CKO/RMC/CIX/COX/QUERY/CLEAN_STA/SET_PRECOOL(0300901xTT 系);廠商→PMS ROOM_INF 0300TT1090/BILL_LIST 0300TT1190/RETURN 0300TT4290/ROOM_STA 系 0300TT4190/KeyBox 0300TT4390 |
| Q5 | `thirdPartyCode` 實際值 + REAL 端點 + 鑑別 | 🔶 **部分解(2026-09-03)**:廠商代碼已定——**MINXON 民笙=81、CHAOFENG 超烽=86**(掛雙廠商各三案);REAL_QA 實測:REST 端點 `/third-party/import-sync-files` 可用、免 Authorization(僅 bacchus 身分 Header)、**ROOM_INF 已回 XML 實料**(房 101→ROOM_STA=V、RETN 0000)。⚠️ 遺留:(a) **A10 RETURN 經 REST 回 procStatus=false+全 null**(雙廠皆同——支援方式待 SA 確認,測試已標 xfail);(b) QA 不驗 thirdParty 代碼(假代碼也收);(c) CHAOFENG 回應 data[] 混 [null 失敗殼, 成功實料](runner 已掃描挑項);(d) 回應 SEND-CODE 固定回 TT 模板形式(0300TT1090)而非回映廠商代碼——mock 維持 sa10 契約(同 REVE),實測差異記錄於此 |
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
| **RC2** | 同族 action(CLEAN/RMTEMP/KeyBox B5)+ 位元級驗證 + 負面路徑補齊 | 約 1 天 | —(sa10 已補齊 Q1/Q3/Q4) |
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
   `tests_localFullStackClose/` 全量(現 33,離線 26)全綠;無 overrides 行為不變。
5. LOCAL(loopback)閉環實跑通(push→query 回讀一致);REAL 至少一輪(RC1),前提不足處標「待驗」。
