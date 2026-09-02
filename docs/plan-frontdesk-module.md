# 🏨 Front Desk 櫃台模組開發規劃(新模組:frontdesk)

> 版本:v1(2026-09-02)
> 決策背景:2026-09-02 裁定 Front Desk 以**新模組 `frontdesk`** 開發(與 parking/amenity/keycard 平行);**首廠商(vendor)尚未確定**。
> 本文 = vendor 無關的模組骨架規劃 + 情境選單 + 待決策清單;實作排程接在案例參數化(`design-case-parameterization.md`,已合併 e9b92cb)之後。
> 關聯:收編 `plan-vendor-expansion.md` §3(Front Desk 切片)——若首廠商確定為華豫寧 LiveAM,該文件 F1 的 Front Desk 部分(換房二情境、改預住日、客製路由)改掛本模組執行。

---

## 0. 摘要

- `frontdesk` = 第四模組,承載「**櫃台作業情境**」(業務事件層:入住/退房/換房/改期…),
  與 keycard(製卡技術管線)分工。vendor 槽位開放,遵循既有 Strategy 模式。
- **FD0 骨架可在 vendor 確定前立即動工**:blueprint + 策略介面 + 案例選單(UNIMPLEMENTED +
  ParamSpec 草案)→ UI 直接顯示「待開發」選單,供 SA/業務確認範圍。
- 三個決策點見 §5(vendor 選定、keycard 狀態機案例是否遷移、認證模型)。

---

## 1. 模組邊界(核心設計問題)

櫃台動作有兩種理解,本規劃採 (a) 為主、(b) 為後續擴充:

- **(a) 平行模組(v1 採用)**:frontdesk 是「PMS 櫃台業務事件 × 某廠商 API」的情境層,
  與 parking/amenity/keycard 同形(blueprint + vendors 策略 + runners 註冊)。
- **(b) 跨廠商編排(未來)**:一個櫃台動作同時落到多廠商(換房 → 停車白名單改 + 房卡重綁)。
  先例已在:`card_lifecycle`(keycard 製卡 → amenity mifare 刷回)就是單一 runner 跨模組 URL 的閉環;
  待 (a) 站穩後以組合案例形式加入,不另立層。

### 動作歸屬建議

| 櫃台動作 | 建議歸屬 | 說明 |
|---|---|---|
| CKI 開門 / CIX・CKO 卡失效 / 改退房日 | **frontdesk**(若首廠商=LiveAM,自 keycard 遷入,見 §5-D2) | 業務狀態機,不是製卡技術 |
| 換房(製卡後 CHANGE_ASSIGN_ROOM / 入住後 ROOM_CHG) | **frontdesk**(新) | `plan-vendor-expansion.md` §3 盤點:零件全在、只缺 runner |
| 改預住日(CHANGE_RESERVATION 補 preInTime) | **frontdesk**(新) | 同上,半覆蓋補全 |
| 製卡/刪卡/讀卡/卡權限/Token 生命週期 | **keycard(留)** | 製卡技術管線,與櫃台業務正交 |
| WalkIn 製卡鈕 | 不做 | sa6 明示「可以不要 call api」 |
| 停車白名單事件(入住/取消入住/改車號…) | parking(留) | 已在線上 13 案,不動 |

---

## 2. 情境選單(vendor 無關——PMS 櫃台事件是常數,差異只在廠商 API)

| case_id(建議命名) | 情境 | ParamSpec 草案(key,label,type,default) |
|---|---|---|
| `fd_checkin` | 櫃台入住報到(開權限) | room_no 房號 str;guest_name 住客名 str |
| `fd_checkout` | 退房結算(權限失效) | room_no;guest_name |
| `fd_cancel_checkin` | 取消入住 | room_no |
| `fd_change_checkout` | 延長/修改退房日 | room_no;new_checkout datetime |
| `fd_change_prein` | 改預住日 | room_no;new_prein datetime |
| `fd_room_change_assign` | 換房——製卡後未入住(getRoomId→改 roomID) | old_room_no;new_room_no;guest_name |
| `fd_room_change_inhouse` | 換房——已入住(改 roomID + 帶 checkinTime 重綁) | old_room_no;new_room_no;guest_name |
| `fd_walkin` | WalkIn(暫緩,sa6 明示可略) | — |

- 負面路徑(查無訂單/房號、Token 失效)依 §參數化設計「不開放」原則,以固定劇本案例呈現,**不宣告 params**。
- 所有案例註冊必須宣告 ParamSpec(hint 用 SA/廠商術語、echo_fields 標回映欄位)——設計 §9/§12 硬性約束。

---

## 3. 架構(vendor 無關,完全沿用 registry.py 文件記載的三層擴充路徑)

```
server/frontdesk/__init__.py        # frontdesk_bp 掛載(main.py register_blueprint 一行)
server/frontdesk/routes.py          # 櫃台事件路由(等 FD1 才有內容;FD0 可為空殼+健康檢查)
server/frontdesk/vendors/base.py    # FrontDeskVendorStrategy 介面(解析/轉換/負面碼)
orchestrator/runners.py             # module="frontdesk" 案例註冊(FD0 全 UNIMPLEMENTED + params 草案)
```

- **UI 觸點只有兩處**:`api.py` `_MODULE_LABEL` 與 `app.js` `moduleLabel()` 各加一行 `"frontdesk": "🏨 櫃台作業"`;
  其餘(案例清單、參數表單、結果頁)全由 `/scenarios` 詮釋資料驅動——這正是參數化設計 §8 的驗收:需要改 UI 結構即架構警訊。
- **engine urls**:首廠商確定後在 `build_run_context` 增加該 vendor 端點區塊(集中管理,runner 不自拼 URL)。
- **registry 小擴充**:`register_unimplemented` 增加可選 `params` 參數(FD0 讓待開發案例也預覽參數欄位)。
- **expected 種子**:情境轉正時逐案入 `tests_data_pool/verified_payload_logs.json`(歷史通關 payload)。

---

## 4. 分期

| 期 | 內容 | 工作量 | 前提 |
|---|---|---|---|
| **FD0 模組骨架(vendor 無關,可立即動工)** | blueprint 空殼 + 策略介面 + registry 模組掛載 + UI label + §2 選單以 UNIMPLEMENTED 入表(含 ParamSpec 草案)+ 離線測試(註冊完整性) | 約 0.5 天 | 無 |
| **FD1 首廠商轉正** | vendor 策略檔 + 前 3 情境(候選:`fd_room_change_assign`、`fd_room_change_inhouse`、`fd_change_prein`——零件已全在) | 約 1 天 | **D1 vendor 確認** |
| **FD2 keycard 遷移決策執行** | 若首廠商=LiveAM:CKI/CIX/改退房三案自 keycard 遷入(一次性,同步改測試斷言與 case_id 對照表;歷史報告標註對應) | 約 0.5 天 | D2 |
| **FD3 選單補齊 + REAL 驗證** | 其餘情境 + 負面路徑 + 種子 + REAL 環境實測一輪 | 約 1 天 | 契約確定 |

---

## 5. 待決策清單

| # | 決策 | 影響 | 建議 |
|---|---|---|---|
| D1 | **首廠商是誰**(LiveAM?其他?) | FD1 起全部 | LiveAM 契約最完備(sa6/sa7),且沙盒已有 9 案與五組 URL 可沿用——除非業務另有指示 |
| D2 | keycard 狀態機三案(CKI/CIX/改退房)是否遷入 frontdesk | 模組語意 vs 遷移成本 | 若 D1=LiveAM → 建議遷(一次到位);否則 keycard 留原生情境,frontdesk 以新廠商情境為主 |
| D3 | 認證模型(vendor 專屬 header?login token 生命週期?) | 策略介面與 routes 設計 | 依 D1 結果;LiveAM 已有 login/Token 模式可套 |
| D4 | 與 `plan-vendor-expansion.md` 的 Front Desk 切片歸屬 | 文件單一事實來源 | 本文收編(該文件已加指向註記) |

---

## 6. 驗收準則(沿用 plan-vendor-expansion §6,重申兩條硬約束)

1. 每支新情境:`@register_scenario` + **ParamSpec 宣告**(hint 用 SA 術語、echo_fields 標回映);UI 零改動(僅 FD0 的 label 兩處)。
2. 每支新情境補離線測試;`tests_localFullStackClose/` 全量(現 33,離線 26)全綠;無 overrides 行為不變。
3. LOCAL(loopback)實跑通(含負面斷言,如換房後舊房卡應失效);REAL 至少一輪,前提不足處標「待驗」。
