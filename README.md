# 🏨 德安 Athena PMS 全物聯網整合測試大一統 Staging 沙盒平台

本專案（`PMS-test-mock-server`）是一個高度解耦、採用**策略模式（Strategy Pattern）**與**藍圖架構（Flask Blueprints）**建構的**高傳真（High-Fidelity）**整合測試沙盒。透過將架構進行「職責分離（SoC）」重構，完美還原實體行動代號的資料流與第三方廠商後端伺服器的物理通信邊界，並具備全自動批次迴圈連發功能，用以高效驗證串接整合測試。

旨在切斷飯店實體硬體與環境的依賴，一鍵還原並模擬異質物聯網廠商與德安 PMS 系統之間的雙向數據對撞鏈路。

---

## 📂 專案大一統架構圖 (Project Directory Tree)

```text
PMS-test-mock-server/
│
├── config.py                 # ⚙️ 全域設定檔（戰略總開關 ENV_SWITCH + 六環境矩陣）
├── main.py                   # ⚡ Flask 沙盒引擎唯一入口（orchestrator＋隧道＋五模組藍圖，監聽 :5000）
├── orchestrator/             # 🧭 第 0 層測試編排協調層（/environments /scenarios /runs）
│   ├── api.py                #    編排 REST API + 案例參數化 overrides
│   ├── engine.py             #    發砲引擎（各環境 URLs 矩陣 + 鑑別 Header 注入）
│   ├── registry.py           #    @register_scenario 案例註冊表 + ParamSpec 詮釋資料
│   └── runners/              #    各模組案例（parking / amenity / keycard / roomcontrol）
├── static/                   # 🖥️ 測試主控台前端（vanilla ES modules SPA，Flask 直接 serve 於 /）
├── app_dashboard.py          # 🧰（legacy）舊版 Streamlit 控制台——已由 static/ 主控台取代
├── sandbox_tunnel.py         # 🌐 ngrok 隧道控制（/tunnel/*，主控台「對外隧道」卡後端）
├── requirements.txt          # 📦 Python 依賴清單
├── ngrok.exe                 # 🌐 邊緣端 Ngrok 通道（不入庫自行下載；本地沙盒對外暴露用）
│
├── docs/                     # 📚 設計與分期規劃（參數化／案例命名／房控模組／廠商擴張）
├── sa_docs/                  # 📄 SA 端契約文件（sa6～sa10）
├── troubleshoot/             # 📝 各模組維運與狀態機踩坑日誌
├── tests_data_pool/          # 🏗️ 大一統測試資產數據池（通關 payload 種子／備品 fixtures）
│
├── hardware/                 # 📡 邊緣端／廠商主動發砲模擬腳本庫
│   ├── simulate_camera.py    # 🚗 模擬地下室車辨相機拍牌抵達
│   └── simulate_speaker.py   # 🦏 模擬小美犀音箱全生命週期故事線
│
├── server/                   # 🏗️ 沙盒核心引擎（Flask Blueprints + Strategy Pattern）
│   ├── parking/              # 🚗 【模組一：停車車辨系統】
│   │   ├── routes.py         # 接收 PMS 白名單異動 + 車輛抵達逆向回推
│   │   └── vendors/
│   │       ├── base.py                    # 車辨策略基底類別
│   │       ├── vendor_SHIN_YEONG.py       # 新詠資料洗滌與正規化策略
│   │       └── vendor_PAYTRONEX.py        # 博辰（PAYTRONEX）車辨策略
│   │
│   ├── amenity/              # 🦏 【模組二：小美犀房務備品與入帳系統】
│   │   ├── routes.py         # 內置在店住客庫，接收查詢與入帳／沖銷
│   │   └── vendors/
│   │       ├── base.py                    # 房務策略基底類別
│   │       └── vendor_BR_AIELLO.py        # 小美犀 12 大核心欄位與 JSON 語意洗滌
│   │
│   ├── keycard/              # 🔑 【模組三：華豫寧門禁製卡鎖系統】
│   │   ├── routes.py         # 內置訂單／卡片庫，迎擊製卡／消卡／逆查指令
│   │   └── vendors/
│   │       ├── base.py                    # 門禁策略基底類別
│   │       └── vendor_WAFERLOCK_LIVEAM.py # 華豫寧 Token 簽發與訂單狀態機維護
│   │
│   ├── roomcontrol/          # 🌡️ 【模組四：房控】A7 公版 XML 介面（廠商→PMS 方向）
│   │   ├── routes.py         # POST /third-party/import-sync-files（mock PMS 側）+ 內部回讀
│   │   └── vendors/
│   │       ├── vendor_A7_XML.py           # A7 公版 XML 組裝／解析策略（sa10 V1.2）
│   │       ├── vendor_MINXON.py           # 民笙（thirdPartyCode=81）
│   │       └── vendor_CHAOFENG.py         # 超烽（thirdPartyCode=86）
│   │
│   └── pbx/                  # ☎️ 【模組五：交換機晨喚】pbx_interface 192-byte 檔案記錄介面
│       ├── routes.py         # POST /pbx/host-commands（mock 交換機側）+ 內部回讀／重置
│       └── vendors/
│           └── vendor_PABX.py             # 固定長度記錄編解碼（CKI/CKO/MCS/DND/TCE/RMC…）
│
└── tests_localFullStackClose/        # 🧪 【測試】（自動 skip 慣例見下方「測試資產與閉環測試」節）
    ├── conftest.py                   # 共用前置：server_up 沙盒在線探測（未開自動 skip）
    ├── test_mock*.py                 # 離線單元測試（responses 攔截，不需網路與 server）
    ├── test_local_api / test_local_scenario / test_local_roomcontrol   # 本地閉環（需 server 在線；離線自動 skip）
    ├── test_roomcontrol / test_pbx / test_param_override / test_orchestrator 等   # 各模組離線規格比對
    ├── test_real_*.py                # 真實雲端（僅 ENV_SWITCH=REAL_* 執行，@skipif 防護）
    └── test_waferlock_liveam_pipeline.py  # 華豫寧門禁全管線測試
```

---

## 🎛️ 戰略總開關：四模式環境矩陣

一切對外行為由 `config.py` 的 `ENV_SWITCH` 單一變數決定。四種模式：

| 模式 | 用途 | 是否對外發送請求 |
|------|------|------------------|
| `LOCAL_OFFLINE` | 🔒 **閉環規格比對**——路由組好 Payload 後直接回傳供比對 SA 文件欄位，**完全不出站** | ❌ 否 |
| `LOCAL` | 🔵 本地隔離沙盒——走 Ngrok 邊緣端轉發 | ✅ 是（Ngrok） |
| `REAL_QA` | 🟠 真實德安 QA 雲端 E2E 串接（**2026-09-03 起預設**；後續測試資料以 QA 環境為主） | ✅ 是（QA 雲） |
| `REAL_UG` | 🟢 真實德安 UG 雲端 E2E 串接 | ✅ 是（UG 雲） |

> 💡 切換方式：直接改 `config.py` 的 `ENV_SWITCH`，或在 Dashboard 用下拉選單動態切換（詳見下節）。

---

## 🚀 快速啟動

```bash
# 1. 建立虛擬環境並安裝依賴
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. 啟動 Flask 沙盒引擎（監聯 http://127.0.0.1:5000）
python main.py

# 3. 開啟測試主控台（Flask 內建 serve，無需另外啟動）
#    瀏覽器開 http://127.0.0.1:5000/ ——環境切換／案例參數／發砲／結果分析／隧道控制都在這裡
#    （舊版 Streamlit 控制台 app_dashboard.py 已列 legacy，僅備查）

# 4. 跑測試（離線可跑的自動執行；需沙盒在線的自動 skip，不再假紅）
pytest tests_localFullStackClose/
```

> ⚠️ **Windows 環境注意**：`main.py` 內含 emoji 的 `print` 語句，在預設 cp950 編碼的 console 重導向時可能觸發 `UnicodeEncodeError`。若啟動失敗，請加上 UTF-8 環境參數：
> ```bash
> set PYTHONUTF8=1 && python main.py
> ```

---

## 🧰（legacy）舊版 Streamlit 控制台

> ⚠️ **歷史備查**：主控台已由 Flask 直接 serve 的 `static/` SPA 取代——`python main.py` 後開
> <http://127.0.0.1:5000/>，環境切換／案例參數化／發砲／結果分析／ngrok 隧道控制皆在其中。
> `app_dashboard.py` 自 2026-08 起不再隨模組演進維護（不含房控模組、案例參數化、隧道卡），僅保留早期聯調參考。

`app_dashboard.py` 是疊在沙盒引擎之上的**單檔 Web 控制台**——用最少的程式碼把後端的 `config` 戰略總開關、模擬發射腳本與測試資產，全部收攏成一個可點擊的操作介面。設計上不引入任何前端工程，直接以 Python 操縱後端單例。

### 🔑 核心設計理念

1. **延遲資產載入（Lazy Backend Bootstrap）**
   `load_backend_assets()` 以 `@st.cache_resource` 包覆，只在首次渲染時執行一次：載入全域 `config` 模組、並指向 `tests_data_pool/` 內的資產檔案路徑。
   > 💡 此處**刻意不匯入**後端路由的記憶體 DB——沙盒引擎（`main.py`）與 Dashboard 是兩個獨立進程，記憶體不共享，跨進程 import 到的只會是永遠為空的副本。若需觀測 server 端狀態，請改打 server 的 HTTP 端點（如 `GET /parking/internal/whitelist`）。

2. **多環境動態橫移引擎（`apply_env_to_config` + `_refresh_live_config`）**
   使用者在網頁切換環境時，`apply_env_to_config` 會**改寫 `config` 模組的執行期變數**——`ENV_SWITCH`、`USE_REAL_SERVER`、`IS_OFFLINE`、`CURRENT_TOKEN`、所有 `REAL_URL_*` 與 `REAL_PARAMS_*`（鍵名對齊 `bacchus-hotelcod` / `bacchus-athenaid`）——等於在不停程式的前提下「換檔」。
   - **後端路由**在每次請求時讀 `config`，自然拿到最新組態。
   - **模擬發射腳本**（`simulate_speaker`）因模組層會把環境快照凍結，改由 `_refresh_live_config()` 在每次 `run_all_expanded_scenarios()` 開頭即時重讀 `config`，確保「切換環境 → 重發」真正生效。

3. **分頁級隔離（`st.session_state`）**
   `config` 是 process 共享的全域模組，多人共用同一個 Streamlit process 時，環境切換會互相覆蓋。Dashboard 用 `st.session_state.chosen_env` 讓**每個瀏覽器分頁記住自己的選擇**，並在每次重新渲染、每次動作前都「防禦性校準」回該分頁的選擇，把互相干擾的窗口縮到最小。
   > ⚠️ 這仍非真正的多人隔離——後端狀態依然共享同一份 process。若要完全互不干擾，每位測試者應各自啟動一份獨立的 Streamlit process（不同 port）。

### 🗂️ 三大功能 Tab

| Tab | 名稱 | 職責 |
|-----|------|------|
| 🚀 | **實時聯調點火中心** | 環境狀態指示燈＋`CURRENT_TOKEN` 指標；一鍵發射小美犀 8 大情境回歸腳本，並把 `logging` 透過自訂 `StreamlitLogHandler` 即時串流進網頁。 |
| 📊 | **內部閉環測試報告** | 以 `subprocess` 呼叫 pytest 執行離線盲測；讀取 `verified_payload_logs.json` 呈現最新 5 筆通關 Payload 戰績。 |
| 🗃️ | **數據池資產檢視** | 將 `tests_data_pool/` 的靜態 Fixture（`aiello_product_fixtures.json`）直接 `st.json` 視覺化，便於核對標準測資。 |

---

## 🧩 模組與廠商策略對應

每個領域藍圖下掛多個**廠商策略**，新增廠商只需實作該模組 `vendors/` 的策略介面（`base.py`；房控為 `vendor_A7_XML.py`），不必改動路由層：

| 模組 | 藍圖 | 已實作廠商策略 |
|------|------|----------------|
| 🚗 停車車辨 | `parking_bp` | `vendor_SHIN_YEONG`（新詠）、`vendor_PAYTRONEX`（博辰） |
| 🦏 房務備品 | `amenity_bp` | `vendor_BR_AIELLO`（小美犀） |
| 🔑 門禁製卡 | `keycard_bp` | `vendor_WAFERLOCK_LIVEAM`（華豫寧） |
| 🌡️ 房控 | `roomcontrol_bp` | `vendor_A7_XML`（A7 公版 XML）＋ `vendor_MINXON`（民笙 81）、`vendor_CHAOFENG`（超烽 86） |
| ☎️ 交換機晨喚 | `pbx_bp` | `vendor_PABX`（pbx_interface 公版 192-byte 記錄；PMS0210120 晨喚／電話設定） |

---

## 🧪 測試資產與閉環測試

- **離線可跑（不需網路與 server）**：`test_mock*.py` 以 `responses` 攔截 HTTP 的單元測試，加上
  `test_local_sandbox.py`、`test_orchestrator.py`、`test_roomcontrol.py`（房控規格比對）、
  `test_param_override.py`（參數化）、`test_waferlock_liveam_pipeline.py`（門禁管線）等離線測試。
- **需沙盒在線**：`test_local_api.py`、`test_local_scenario.py`、`test_local_roomcontrol.py`（房控閉環）
  打 `127.0.0.1:5000`，請先 `python main.py`（建議設 `LOCAL_OFFLINE` 模式）；沙盒未開時經
  `conftest.py` 的 `server_up` fixture **自動 skip**，不再噴 ConnectionRefused 假紅。
- **需網路＋有效 Token**：`test_real_*.py` 直打真實德安雲端，一律以 `@pytest.mark.skipif` 防護
  （僅 `ENV_SWITCH=REAL_*` 時執行），CI／離線不會誤觸；`test_real_roomcontrol_qa.py` 為房控 A7 公版
  REAL_QA 串接探測（thirdParty 實際代碼到位後設 `A7_THIRD_PARTY` 環境變數重跑即轉正式斷言）。
- **CI**：`.gitlab-ci.yml` 兩個 job 皆 `LOCAL_OFFLINE`——`offline-unit-tests` 全量收集（前提不足者自動
  skip）；`local-closed-loop` 在 CI 內啟動沙盒引擎，讓 local 三檔閉環真的執行。

---

## 🎛️ 案例參數化（Case Parameterization）

設計文件：`docs/design-case-parameterization.md`。每個測試案例可宣告「可調輸入欄位」（`ParamSpec`），
UI 表單預填 SA 合法預設值、測試者改一個欄位即可重發；**不帶覆寫時行為與原本 100% 相同**。

- **UI**：案例清單上有 ⚙ 的案例可展開參數表單（預填預設值；⚡ 動態欄位留白＝每次執行自動產生唯一值；
  「↺ 還原預設」回復）。只有動過的欄位會進請求。結果頁案例標題列會顯示本次實際使用的參數 chip。
- **API**：`POST /runs` 增加可選 `overrides`：
  ```json
  { "environment": "LOCAL_OFFLINE",
    "scenario_ids": ["room_nos_query"],
    "overrides": { "room_nos_query": { "keyword": "11205" } } }
  ```
  驗證採「刻意寬鬆」：擋未知案例／未知參數鍵／型別轉換失敗／超過 64 字元（400 附可用清單），
  但**不擋不合法值**——填壞值就是在測負面路徑（417/1000），分類器會接住。
- **新增案例欄位**：在 `orchestrator/runners/<module>.py` 的 `@register_scenario(..., params=[ParamSpec(...)])`
  加一行宣告即可，`/scenarios` 自動帶出、UI 免改。負面路徑案例（缺欄位/壞格式/查無）刻意不開放覆寫。
- **Diff 分級**：覆寫造成的回應差異標「參數覆寫」（灰），真差異維持「真差異」（紅）、缺欄琥珀色；
  期望值種子的 echo 欄位會先以本次參數回填再比對（避免誤報淹死真差異）。

---

## 🌐 真實環境串接（ngrok 對外隧道）

真實 PMS 雲端（QA / SIT / UG / MAS）要能把「**PMS→廠商**」方向的推播（新詠、博辰、華豫寧）
送進本沙盒，沙盒必須有一個雲端打得到的公網 URL —— 透過 **ngrok 隧道**把本機 `:5000` 暴露出去。
主控台「① 環境/案例設定」頁的「🌐 對外隧道」卡可一鍵啟動/停止並複製各廠商登錄 URL。

### 為什麼一定要「固定網域」
- ngrok 免費**隨機 URL** 每次重啟都會變 → 登錄進 PMS 設定的 URL 立即失效，每次都要重設。
- 免費隨機 URL 有瀏覽器警告頁（interstitial），會**直接擋掉 PMS 的機器請求**。
- 免費帳號可申請 **1 個固定網域（static domain）**：URL 永不變、無警告頁 → PMS 設定一次永久有效。

### 一次性設定（約 10 分鐘）
0. **安裝 ngrok**：[ngrok.com/download](https://ngrok.com/download) 下載後解壓，
   把 `ngrok.exe` 放進專案根目錄（或安裝到系統 PATH 皆可，沙盒兩處都會找）。
1. 註冊/登入 [ngrok](https://ngrok.com)（免費帳號，完成 Email 驗證）。
2. **取得固定網域**：Dashboard 左側 `Domains` → 免費帳號由系統**直接配發 1 個**
   （不可自取名，網域為 `xxxx.ngrok-free.dev` 結尾；若畫面不給新增，用配發的那個即可）。
3. **設定 authtoken**：Dashboard `Your Authtoken` 頁複製 token → 本機執行：
   ```bash
   ./ngrok.exe config add-authtoken <your_token>
   ```
4. **把固定網域告訴沙盒**（二選一）：
   - 專案根目錄 `token_local.py`（未入庫）加一行：`NGROK_STATIC_DOMAIN = "xxxx.ngrok-free.app"`
   - 或環境變數 `NGROK_STATIC_DOMAIN`

### 日常啟動
- **UI（建議）**：主控台 →「① 環境/案例設定」→「🌐 對外隧道」卡 → **▶ 啟動隧道**
  （綠燈亮起後，卡上可直接複製各廠商登錄 URL；停止鈕僅對沙盒自己啟動的隧道有效）
- **手動**：`./ngrok.exe http --url=xxxx.ngrok-free.app 5000`

### 各環境 PMS「第三方廠商設定」要登錄的 URL
設 `{URL}` = 你的固定網域：

| 廠商 | 登錄 URL | 備註 |
|---|---|---|
| 新詠 SHIN_YEONG | `{URL}/parking/sync` | SA v1.2 公版單一端點 |
| 博辰 PAYTRONEX | `{URL}`（PMS 拼 `/parktron/hpms/services/roomer/*`） | add / findByLicensePlate / update |
| 華豫寧 LIVEAM | `{URL}`（PMS 拼 `/api/*`） | Auth/login、Order、OrderCard… |
| 小美犀 BR | **不需登錄 inbound URL** | 方向為我方主動呼叫 PMS |

> 💡 PMS 的公開 API 沒有「寫入第三方廠商 URL 設定」的端點，登錄動作須由後台/資料庫手動完成（一次性）。

### 注意事項
- 電腦關機或 ngrok 停止 → 隧道斷線，PMS 推播會失敗；測試期間保持沙盒＋隧道開啟。
- **MAS（正式環境）的資料會流經 ngrok 外部服務** —— 資安上有疑慮時，長期方案是把沙盒
  部署到公司內部 VM（穩定內部 URL，完全不需要 ngrok）。
- 鑑別 Header：四環境 vendor-sync 實測皆**免 Authorization**，沙盒自動雙帶
  `athena`/`hotel` + `bacchus-athenaid`/`bacchus-hotelcod`。
