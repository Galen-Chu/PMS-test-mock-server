# 🎛️ 案例參數化設計(Design: Case Parameterization)

> 版本:v1 草案(2026-09-01)
> 定位:**內部整合驗證為主**;介面設計需保留未來「推展給廠商自助測試」的空間。
> 非目標:**不做通用 API 發射器**——任選路由 + 自編請求 + 看回應是 Swagger UI / Postman 的領域,
> 沙盒的價值在「狀態 + SA 規格 + 雙向視野」,參數化是把這三者的觸角延伸,不是重複造輪子。

---

## 0. 摘要

讓每個測試案例宣告「可調輸入欄位」(declarative params):UI 表單預填 SA 合法預設值,
測試者改一個欄位即可重發;不帶覆寫時行為與現況 100% 相同(向後相容)。
參數宣告即文件——`/scenarios` API 自動帶出詮釋資料驅動 UI 表單,新增案例欄位 = 加一行宣告,UI 免改。

---

## 1. 現況與痛點

- 39 個案例皆可單獨勾選執行(`POST /runs {scenario_ids}`)——「每條路由獨立測」的顆粒度其實已存在。
- 缺的是:**測資寫死在 runner 裡**(房號 `"11101"`、mifare `"1A2B3C"`、料號 `M001`)。
  想換一間房、換一塊車牌 → 改 `orchestrator/runners.py` → 重啟 → 門檻高,廠商完全無法自助。
- `car_arrival` 等案例已有時間戳動態唯一 ID(`G-0901152134`)——證明「動態預設」模式已在線上,
  參數化是把這件事正規化、可見化。

## 2. 資料流總覽

```
UI 參數表單(預填預設值)
   │  POST /runs { environment, scenario_ids, overrides }
   ▼
engine.build_run_context(env, overrides)
   │  逐案例合併:ParamSpec.default(動態者此時求值)← override 覆蓋
   ▼
RunContext.params[case_id] ──► runner 以 ctx 取參數組 payload
   │                                │
   │                                ▼
   │                        request_payload 自然進 steps 稽核(不變)
   ▼
CaseResult.resolved_params(新增欄位)→ 結果頁顯示「這次用了什麼參數」
```

## 3. 資料模型(`orchestrator/models.py` / `registry.py`)

```python
@dataclass
class ParamSpec:
    key: str                 # runner 內部鍵,如 "keyword"
    label: str               # UI 顯示,如「房號關鍵字」
    type: str = "str"        # str / int / bool / date / datetime
    default: Any = None      # 靜態值,或 callable(RunContext) -> 值(動態唯一 ID)
    hint: str = ""           # SA 規格提示(格式、負面行為),UI tooltip
    required: bool = True
    echo_fields: tuple = ()  # 此參數會被回應/種子回映的欄位名(§7 diff 用)
```

- `register_scenario(..., params=[ParamSpec(...), ...])`:註冊即宣告;`Scenario` dataclass 增存 `params`。
- **動態預設求值時點**:run 開始時逐案例求值一次(同 run 內一致,避免兩案例拿到不同時間戳)。
- 序列化進 `/scenarios`:`default` 為 callable 者 → 求值展示 + `dynamic: true`(UI 顯示「每次執行自動產生」)。

## 4. API 變更(向後相容)

- `POST /runs` 增加可選欄位:
  ```json
  { "environment": "REAL_QA",
    "scenario_ids": ["room_nos_query"],
    "overrides": { "room_nos_query": { "keyword": "11205" } } }
  ```
- 驗證(400 附可用清單):未知 `case_id`、未知 `param_key`、型別轉換失敗、長度上限(64 字元)。
  參數**只進 JSON body / query string,永不拼接 URL 路徑**(防路徑注入)。
- **刻意寬鬆**:不擋「不合法值」——測試者故意填壞值就是在測負面路徑(417/1000),
  分類器(`classify.py`)本來就會接住。Postman 驗證是為了「打對」;我們是為了「**可控��打錯**」。

## 5. Engine 變更(`engine.py`)

- `RunContext` 增 `params: dict[str, dict]`(case_id → 合併後參數)。
- `start_run_async(scenario_ids, environment, overrides=None)`;`_execute_run` 傳入。
- `CaseResult` 增 `resolved_params` 欄位(序列化進 `/runs/<id>/results`)。

## 6. Runner 改寫模式(最小侵入)

現況:
```python
params = {**ctx.params_amenity, "keyword": "11101"}
... request_payload={"keyword": "11101"}   # 硬編兩處,改資料要改兩行
```
改法:
```python
p = ctx.params["room_nos_query"]            # engine 已合併好(預設或覆寫)
params = {**ctx.params_amenity, "keyword": p["keyword"]}
... request_payload={"keyword": p["keyword"]}
```
- **組合案例只暴露種子參數**:`amenity_charge`(GET 取 ciSerial → POST billing)、
  `card_lifecycle`、`paytronex` find→update 等,只開「初始房號/車牌/卡號」,
  下游步驟沿用同一值,保證步驟間一致——這是參數化不能破壞的不變量。

## 7. 期望值(diff)與參數的互動 ⚠️ 本設計最關鍵的細節

**問題**:`expected.py` 的種子來自 `verified_payload_logs.json`(歷史通關 payload,房號=11101)。
測試者覆寫成 11205 後,回應 echo 的房號會被 `compute_diff` 誤報 MISMATCH——噪音會淹死真差異。

**對策(兩層)**:
1. **種子參數回填**:比對前,把 expected 中屬於 `ParamSpec.echo_fields` 的欄位值,
   以本次 resolved 參數值替換。未覆寫時替換前後相同 → 行為不變(離線測試可守)。
2. **diff 分級渲染**:參數回映造成的差異標「參數覆寫」(灰),真實差異維持 MISMATCH(紅)。
   `compute_diff` 回傳列增 `kind: "param_echo" | "mismatch" | "missing"`。
3. LOCAL_OFFLINE 規格比對同理:比「結構 + 非參數欄位」對 SA,參數欄位跟著 resolved 值走。

## 8. UI 設計(`static/app.js` / `index.html`)

- 案例清單:有參數的案例 chip 加 ⚙;選中時展開「參數」表單
  (label + 輸入框預填 default;dynamic 顯示「自動」placeholder;hint 做 tooltip)。
- 「↺ 還原預設」(單案例);**沒動過的案例不進 overrides payload**(保持請求乾淨)。
- 結果頁 case 標題列加參數摘要 chip(如 `房號=11205`),點開可見完整 resolved_params。
- **廠商推展伏筆**:表單完全由 `/scenarios` 詮釋資料驅動 → 未來「廠商視角」
  只需過濾 module/vendor + 範本鎖,UI 結構零改動。

## 9. 分期開放清單

| Phase | 範圍 | 原則 |
|---|---|---|
| **1** | amenity:`room_nos_query`(keyword)、`mifare_query`(keyword)、`amenity_charge`(房號/料號/數量)、`amenity_cancel`、`billing_sync`;parking SHIN_YEONG:`car_arrival`(guest_name/車牌/時間,guest_id 動態)、check-in 系(seed 住客/房/車/日期)、`parking_sync` 系;PAYTRONEX:`paytronex_find`(車牌)、`paytronex_add`、`car_arrival_pt`;keycard:`keycard_login`(帳密/專案)、`keycard_make_card`(房/住客/日期)、`keycard_room_lookup`(姓名) | 每案例 **2–5 欄**,過多即表單噪音 |
| **2** | 其餘正規案例補齊;`card_issue_exception` 補 runner 時一併宣告 | — |
| **不開放** | 負面路徑案例(缺欄位/壞格式/查無)——它們的「參數」就是劇本本身,開放覆寫反而破壞測資語意 | 固定 |

## 10. 測試計畫

- 單元:`ParamSpec` 註冊/序列化(dynamic default)、override 合併與求值、400 路徑、echo 欄位 diff 分級。
- 回歸:**現有 15 個離線測試必須全綠**——無 overrides 時行為 100% 不變是本設計的硬約束。
- 手動:LOCAL_OFFLINE 與 REAL_QA 各跑一輪「帶覆寫」run(換房號重跑 room_nos_query 驗證 417 → 換回有住客房號驗證 200)。

## 11. 工作量估計

| 項目 | 規模 |
|---|---|
| models / registry / engine / api | 小(約 0.5 天) |
| runners 39 案改讀參數 + 宣告(機械化但量大) | 約 1–1.5 天 |
| UI 表單 + 結果頁參數 chip | 中(約 0.5 天) |
| diff echo 分級(§7) | 中(約 0.5 天) |
| 測試 | 約 0.5 天 |
| **合計** | **約 3 個工作天(2–3 個開發 session)** |

## 12. 與廠商推展的介面(未來,本期不做,但設計已守住)

- vendor mode:限縮模組視角、範本鎖(參數唯讀預設集)、批次回歸 + 報告匯出。
- 本期必須守住的約束:(a) 參數宣告式、UI 零硬編;(b) `hint` 用廠商/SA 術語撰寫;
  (c) `resolved_params` 入結果——報告可追溯「哪次測試用了什麼資料」。
