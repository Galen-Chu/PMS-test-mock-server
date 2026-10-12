# 📞 交換機/晨喚模組開發規劃(新模組:pbx)

> 版本:v1(2026-10-12)
> 背景:PMS0210120「接待交換機管理」(v7.0.0,修訂至 2026-09-14 v1.6 晨喚異常)待測,
> 三份契約文件到齊——①PMS0210120_接待交換機管理.docx(PMS 側程式規格)、
> ②多筆晨呼設定與pbx_mn送出規格.docx(宏興 API SD,v1.4)、③pbx_interface.docx(交換機介面)。
> 2026-10-12 補④交換機SA規格.docx(A7 交換機介接規格 v1.16,修訂至 2024/12)——C# 交換機程式實作規格,
> 結案 Q4/Q8、證實 Q3、修正 Q5 語意、補齊 M2 全部素材(MCS 回應五規則/pbx_err/RMS/PTX/DELETE_STA)。
> 本文 = 契約盤點 + 模組設計 + 分期 + 規格缺口清單;M0/M1 已於 2026-10-12 完成(§4)。

---

## 0. 摘要

- `pbx` = 第五模組(parking/amenity/keycard/roomcontrol 之外),被測第三方 = 飯店交換機(PABX/計費系統)。
- 介面本質 = **檔案交換**(HOST2PMS.DAT/.IDX、PMS2HOST.DAT/.IDX 四檔;192-byte 固定長度記錄;
  德安 C# 交換機程式居中讀寫,pbx_mn 為指令佇列)——沙盒 M0 以 **HTTP 承載同一份記錄字串**模擬。
- mock 對象 = 交換機側(計費系統 PMS MODULE):收德安 HOST 指令 → 執行狀態機(pbx_dt/mcall_mn 落庫)
  → 回 Response 記錄(R/SUC/ERR/SKP);沙盒發砲端 = 模擬德安 HOST 組記錄下指令。
- REAL 雲端發砲(M1)的硬前提 = PMS0210120 的 REST API SD(func_id 1011-1027),文件僅列功能代碼、
  無端點/schema——待 SA。

---

## 1. 契約盤點(三份文件,附出處)

### 1.1 傳輸與記錄格式(pbx_interface)

- 四檔:index(192-byte 單記錄:Record_len=192 常數、File_size、W/P cycle A/B 輪替、W/P index)+
  data(每筆 192-byte)。
- data record:Record_typ X(1)('I'指令/'R'回應)、Record_nos 9(7)、Seq_nos 9(7)、
  Insert_dat 9(8) YYYYMMDD、Insert_tim 9(6) HHMMSS、Data_rmk X(161) @30-190、CR+LF @191-192。
- **排版鐵則:數字欄位靠右、前面填空白;文字欄位靠左、後面填空白。**
- 指令集(Data_rmk 佈局,區段內位置):CKI/COX(inst+phone X(6)+lang X(3)+vip X(1)+master X(6)+
  guest_nam X(30)+account X(20))、CKO/CIX(inst+phone)、RMC(inst+ophone+nphone)、
  MCS(inst+phone+mcall_dat 9(8)+mcall_tim 9(6)+mcall_sta X(1),雙向)、
  DND/MWL/TCE/OOO(inst+phone+status_typ 9(1))、RMS(房況回報,pms→host)、
  MBT/PTX/PTV(帳務,pms→host)、GFT/PDC/PTS/GMS/GMR/DSP/NAM/ITM/BAL(帳務/留言/顯示)。
- 回應記錄(Record_typ='R'):inst ∈ {SUC,ERR,SKP} + 原指令 dat/tim/seq + Msg_cod X(40)
  (列舉:ROOM_NOT_FOUND/MSG_FORMAT/TIME_OUT/…)+ Session_cod X(6)。
- mcall_sta 值域(=PMS0210120 mcall_mn.mcall_sta):0=Set、1=Answered、2=Busy、3=No Answer、
  4=Block、5=Call Termination to ATTCON、D=刪除設定、C=關閉電話(關帳時)、F=設定交換機 MCALL 失敗。

### 1.2 狀態機與觸發(宏興 SD)

- mcall_mn → pbx_mn 排程規則:NOT_TRANS、24hr 內、最接近現在的一筆、房有住人(K/O)同 ikey、
  上一筆已回應;1 分鐘掃一次(參數)。
- 刪晨喚:時間未過且 mcall_sta=0 才能刪;TRANS 時直接 insert pbx_mn(不走排程);update mcall_sta='D'。
- 2020/7/31 規則:**開電話要有住人;無論有無住人都可以關電話;有開電話才可以設限撥、勿擾、mcall**。
- API 觸發 insert pbx_mn 的 8 個 PMS 作業:換房/入住(含W/I)/退房/入住還原/退房還原/開帳/關帳/序號最小結帳。
- 各指令的 pbx_dt 效果:CKI/COX(tel=1+lang+dnd/mwl/tce=0)、CKO/CIX(全清)、RMC(搬移+晨呼 NOT_TRANS)、
  DND/TCE/MWL(住人+電話開前置)、RIU(僅 lang)。
- 姓名組法(RM8761):參數 pbx_send_china_name;英文模式 Miss/Mr.+last+','+first、過濾 A~Za~z、
  空白改送房號、取前 30 碼。
- 館別參數:ghist_mn_lang_cod(預設語言)、smdr_online(有無使用交換機)、pbx_lang_cod、pbx_send_china_name。

### 1.4 A7 交換機程式實作面(交換機SA規格 v1.16)

- **A7 已做**:CKI/CKO/RMC/COX(有規格沒用到)/DND/TCE/MCS(雙向)/RMS/PTX;
  **未做即 bypass**:RIU/MWL/OOO/PDC/GFT/PTS/PayTV-PTX/GMS/GMR/NAM/ITM/BAL/DSP/MBT。
- **MCS 回應處理(wf_read_pms)五規則**:回應 mcall_dat 空白→以 ins_dat 代(v1.6);
  只更新 trans_pbx_sta='TRANS' 且 mcall_sta='0'(v1.12);有給 mcall_tim→精準更新,
  沒給→排序取最小時間一筆(v1.14/1.9);收到 sta='0' 且不存在→INSERT mcall_mn(INS_USR='PBX',TRANS);
  **回應 sta∉{0,1,3}→入 pbx_err**(Busy/Block/ATTCON/關帳/刪除/失敗皆入)。
- **ERR 回應機制**:pms2host Record_typ='R'+ERR → 入 pbx_err(ERROR_COD='指令失敗--請重試',
  依原指令 seq 回撈 pbx_mn 記錄)。
- **pbx_mn.DELETE_STA**:N未處理/S跳過(未知指令)/Y已處理;AthenaJobService 30 秒,
  一次抓 150 筆(DELETE_STA='N' 依 ins_dat,seq_nos 排序)。
- **pbx_log**:direction I收/O送/**M訊息**;只留 3000 筆;入帳時帶 ikey/ikey_seq_nos/alt_nam。
- **RMS 房況**:3 小時內才處理(逾期入 log);C→clean_sta C/check_sta C、S→D/S、D→D/D、B 不處理。
- **PTX 電話入帳**:gutel_dt/smdr_dt/已 C/O 改入現金帳(v1.8)/通話秒數換算上限/服務項目參數對應。
- **檔案**:編碼 **ANSI 非 UTF8**(中文姓名 2 bytes);idx 檢查 reclen=192、file_size=3000,
  雙方 idx cycle 比對不可覆寫、鎖定 retry;phone_rf 分機對照(參數 USE=PHONE_RF/ROOM_NOS)。
- **維運**:每日刪 pbx_mn/pbx_err/mcall_mn 滾房租日-100天。

### 1.3 PMS 側程式面(PMS0210120)

- 功能:0100 查詢/1011 新增晨喚/1012 取消晨喚/1021 開電話/1022 關電話/1023 勿擾/1024 取消勿擾/
  1025 限撥/1026 取消限撥/1027 設定語言/1030 交換機重送/晨喚異常;Option=PMS_PBX。
- **API:1011/1012/1021-1026(對外 REST,契約未附——M1 前提)**。
- 交換機重送(Ver1.4):空房重送 CKO、住人房 CKO→CKI→限撥/勿擾→重設晨呼(NOT_TRANS)。
- 晨喚異常(v1.6):當天+TRANS+mcall_sta∈{2,3,4,5}+未處理;30 秒週期刷新計數;已處理流程。
- 資料表:mcall_mn、pbx_mn(seq/PRO_ID/ROOM_NOS/INST_COD/DATA_RMK)、pbx_dt(TEL_STA/DND_COD/
  MWL_COD/TCE_COD/lang_cod)、pbx_log(direction I/O、succ_flg、data_rmk)、hotel_lang_dt(pbx_lang 對應)。

---

## 2. 模組設計(M0 落地形狀)

```
server/pbx/__init__.py            # pbx_bp 掛載(main.py 一行)
server/pbx/routes.py              # mock 交換機側:POST /pbx/host-commands + 內部回讀/重置
server/pbx/vendors/vendor_PABX.py # 192-byte 記錄編解碼(組裝/解析/排版鐵則)
mock_pbx_dt / mock_pbx_mcall / mock_pbx_log   # 沙盒記憶體 DB(對齊 PMS0210120 表 3-5)
orchestrator/runners/pbx.py       # module="pbx" 案例(M0:發砲端=模擬德安 HOST)
server/pbx/pms_side.py            # M1:PMS 側業務層(動作端點/排程 tick/內部回讀)
orchestrator/runners/pbx_ui.py    # M1 案例(vendor=PMS_UI:模擬 PMS0210027 頁面動作全鏈)
```

- **HTTP 承載決策**:runner 把 192-byte 記錄字串放進 `POST /pbx/host-commands` 的
  `records` 陣列(等同 HOST2PMS.DAT 一批);mock 逐筆執行狀態機,逐筆回 R 記錄。
  **未模擬**:index 檔 W/P cycle 輪替機制(Q6,M3 視需要)——HTTP 無覆寫風險,輪語意不影響指令處理。
- **閉環斷言**:指令 SUC + `GET /pbx/internal/state` 回讀 pbx_dt/mcall_mn 一致
  (LOCAL only;前例 roomcontrol 位元回讀)。
- **壞記錄分層**:結構壞(長度≠192/非 CRLF/Record_typ 非 I)→ HTTP 417(對齊沙盒錯誤信封);
  語意壞(未知指令/房號/前置不符)→ 200 + R/ERR + Msg_cod(對齊 pbx_interface 回應機制)。
- **REAL 環境**:交換機介面為檔案交換、無雲端 URL → M0 案例一律 SKIP(REAL_NOT_SUPPORTED),
  UI 可見但不誤觸發砲。

### M0 案例選單(十案,ParamSpec 宣告)

| case_id | 情境 | 斷言重點 |
|---|---|---|
| pbx_checkin_open_tel | CKI 入住開電話 | SUC + pbx_dt tel_sta=1/room_sta=O/lang 落庫 |
| pbx_morning_call_set | MCS 晨喚設定(CKI 前置) | SUC + mcall_mn mcall_sta=0 |
| pbx_morning_call_cancel | MCS 取消(設→刪) | SUC + mcall_sta=D |
| pbx_dnd_set / pbx_tce_set | DND/TCE 設定(CKI 前置) | SUC + 對應欄落庫 |
| pbx_checkout_close_tel | CKO(CKI+MCS 前置) | SUC + tel_sta=0 + 晨呼全 C |
| pbx_room_change | RMC 換房(CKI 前置) | SUC + 新房開/舊房清 + 晨呼移房 |
| pbx_unknown_room | CKI 至未知房號(負面) | R/ERR + ROOM_NOT_FOUND |
| pbx_bad_record | 壞記錄(負面) | HTTP 417 |
| pbx_dnd_without_guest | 空房設勿擾(負面) | R/ERR + GUEST_NOT_IN |

---

## 3. 規格缺口

| # | 問題 | 狀態 |
|---|---|---|
| Q1 | ~~PMS0210120 REST API SD~~ | ✅ **2026-10-12 結案(SD文件_PMS0210027_交換機.xlsx)**:交換機**無對外 REST 面**——網頁版按鈕(0200 新增/0300 刪除/1010 開關電話/1020 限撥/1030 勿擾)規則全指向「入 pbx_mn + 宏興SD」,經框架 func_id 直入 DB,不暴露雲端端點;值域表(trans_pbx_sta/mcall_sta)與本模組 M0 契約完全一致。**故 REAL 雲端發砲路不存在,M1 改為沙盒內 PMS 側業務層全鏈模擬(已完成)** |
| Q2 | Msg_cod 值域 | ✅ **自定義定案(2026-10-12 裁定,mock 依功能自訂不待 SA)**:契約列舉 ROOM_NOT_FOUND/MSG_FORMAT/TIME_OUT 之外,沙盒自擴 GUEST_NOT_IN(空房前置)/TEL_NOT_OPEN(電話未開前置)/MCALL_NOT_FOUND(取消無設定)——語意自明,SA 若日後列舉值域再對齊 |
| Q3 | 刪晨喚的介面形狀 | ✅ 大致證實:SA規格 MCS 雙向 sta 值域含 'D'(Delete set)/'C'(Close Account);M0/M1 的 MCS+D 實作方向正確 |
| Q4 | ~~mcall_mn PK 定義分歧~~ | ✅ 結案:**IKEY 版**——SA規格 v1.9/v1.14 更新 SQL 以 (mcall_dat, mcall_tim, room_nos, ikey) 為鍵 |
| Q5 | CKO 後晨呼回報值 | ✅ **自定義定案(2026-10-12 裁定)**:PMS 側 CKO 僅 NOT_TRANS→'D'(宏興SD 原文);交換機側 mock 於 CKO 將 sta=0 晨喚標 'C'(SA 值域成員,模擬交換機清除晨呼的回報)——兩側各按文件行為,差異即測試觀察點 |
| Q6 | index 檔 W/P cycle 輪替機制 | 🔶 SA規格補齊實作依據(idx 檢查 192/3000、雙方 cycle 比對、retry、實例);M0 未模擬(HTTP 承載無覆寫風險);真檔案交換屬 M3 |
| Q7 | QA 環境前提 | ✅ **自定義定案(2026-10-12 裁定,不阻塞)**:沙盒自持房號 universe(0101-0109)+room_mn 視景,LOCAL 模擬不依賴環境;Option PMS_PBX/smdr_online/交換機廠商型號僅影響未來 REAL 驗證深度(現無 REAL 路,見 Q1) |
| Q8 | ~~MWL 留言燈~~ | ✅ 結案:**A7 未做**(SA規格「未做之功能就 bypass」清單含 MWL/RIU/OOO/留言族/帳務顯示族)——不案例化 |
| Q9 | 帳務/房況/留言面 | 🔶 SA規格補齊 RMS(3hr 效期)與 PTX 入帳全規則;A7 未做留言/顯示族——屬 M2(RMS)/M3(PTX 帳務) |
| Q10 | 檔案編碼 ANSI(中文 2 bytes) | ⏳ SA規格明載 host2pms/pms2host 為 ANSI 非 UTF8(A7 現況標問號)——M3 檔案化時的硬前提 |

---

## 4. 分期

| 期 | 內容 | 工作量 | 前提 | 狀態 |
|---|---|---|---|---|
| **M0** | 模組骨架 + 記錄編解碼 + mock 交換機狀態機 + 十案 + 雙層負面 + 內部回讀閉環 + 離線/閉環測試 + UI label | — | 無(三份文件) | ✅ **2026-10-12 完成**:離線 13 測試 + 閉環 3 測試全綠(全量 66 passed/0 failed);REAL 案例自動 SKIP |
| **M1** | ~~PMS REST API 發砲~~→ **PMS 側業務層模擬**(Q1 結案後改向):`server/pbx/pms_side.py` 動作端點(入住/退房/開關電話/限撥/勿擾/設刪晨喚/換房)+ 排程 tick(宏興SD 1.2 五規則)+ in-process 下達交換機側 + 七案(全鏈/取消已傳/退房連動/換房重送/過時 SKIP/負面二) | — | Q1 結案(SD 證實無 REST) | ✅ **2026-10-12 完成**:離線 9 測試 + 閉環 1 測試全綠 |
| **M2** | 重送(1030)/換房深鏈/設定語言(CKO+CKI+重入晨呼)/晨喚異常生成與已處理/RMS 房況回報(3hr);MCS 回報 1-5 模擬(ring 觸發+回應五規則+pbx_err) | 約 1.5 天 | 文件已齊(④SA規格 2026-10-12 到);僅剩 Q7 環境資訊影響 REAL 驗證深度 |
| **M3** | 真檔案交換(HOST2PMS/PMS2HOST 四檔 + W/P cycle 輪替)或帳務面(MBT/PTX/GFT) | 視需求 | Q6/Q9 + 環境 |

---

## 5. 驗收準則(DoD,比照 roomcontrol)

1. 每支新情境:`@register_scenario` + ParamSpec 宣告(hint 用 pbx_interface/宏興SD 術語);
   UI 零改動(僅 M0 的 label 兩處)。
2. 記錄契約:組裝/解析逐欄對齊 pbx_interface 位置表;排版鐵則(數字右/文字左)以測試釘死;
   偏離處註明原因(Q2/Q3/Q5)。
3. 斷言雙層:HTTP 200 + 逐筆 resp_cod=SUC(負面:ERR+Msg_cod 或 417)且 LOCAL 回讀落庫一致。
4. 新案例補離線測試;`tests_localFullStackClose/` 全量全綠;REAL 案例SKIP 不誤觸。
5. LOCAL(loopback)閉環實跑通(經 /runs 編排)。
