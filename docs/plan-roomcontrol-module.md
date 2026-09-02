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

### 1.1 傳輸層(sa8/sa9:`POST /third-party/import-sync-files`「處理廠商主動發送的資料(請求C001.xml,回傳C001.xml)」)

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

## 2. 規格缺口(向 SA 索取清單;不阻塞 RC0)

| # | 問題 | 影響 |
|---|---|---|
| Q1 | `#ROOM_STA#010101011001#` **位元字串每一位的定義**(順序/長度/語意) | RC0 僅能原樣轉發斷言;位元級驗證要等 |
| Q2 | **ROOM_INF 回應 XML 形狀**(房況欄位 + 多住客帳務編號結構) | RC0 的查詢案先只斷言 procStatus + RETN-CODE 0000 |
| Q3 | `ACTION_STA` 值域與語意(CLEAN=1?);`ACTION_DAT` 格式確定 yyyy/mm/dd hh:mm:ss? | 負面路徑與種子 |
| Q4 | REVE-CODE/SEND-CODE 完整代碼表(已知:房控推播 0300TT4190、房況查詢 0300TT1090) | 解析器嚴謹度 |
| Q5 | `thirdPartyCode` 實際值;import-sync-files 的**鑑別**(比照 vendor-sync 免 Authorization?或需 token) | REAL_QA/SIT 實測(RC1) |
| Q6 | `procStatus=false` 的錯誤處理與重送契約 | 負面路徑 |
| Q7 | 真實測試台房控設備前提(實體/模擬/無) | RC3 的 REAL 驗證深度 |

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
- **閉環斷言(房控版)**:`rc_room_status_push` 推位元串 → `rc_room_status_query` 查同房號 →
  斷言查得的房況 = 推送的位元串(下命令→回讀,同 keycard checkinTime 模式)。
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
| **RC0(可立即動工)** | 模組骨架 + XML 管線(組裝/解析/417)+ ROOM_STA/ROOM_INF 兩案 + push→query 閉環 + 離線測試 + UI label | 約 1 天 | 無 |
| **RC1** | REAL_QA/SIT 實測一輪(import-sync-files)+ 通關種子入庫 | 約 0.5 天 | Q5 鑑別資訊 |
| **RC2** | 同族 action(CLEAN/RMTEMP)+ 位元級驗證 + 負面路徑補齊 | 約 1 天 | Q1/Q3/Q4 |
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
