# app_dashboard.py
import streamlit as st
import sys
import os
import json
import time
import subprocess
from datetime import datetime

# 確保路徑完全對齊
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# ====================================================================
# 🎨 頂層配置：保證網頁渲染大氣流暢
# ====================================================================
st.set_page_config(page_title="PMS AIoT 沙盒測試控制台", page_icon="🎛️", layout="wide")

# ====================================================================
# 🔒 延遲安全匯入後端資產，防禦初始化死鎖
# ====================================================================
@st.cache_resource
def load_backend_assets():
    import config
    # 物理路徑定義（後端記憶體 DB 屬另一個 Flask 進程，無法跨進程共享，故不在此匯入）
    pool_dir = os.path.join(current_dir, "tests_data_pool")
    log_json_path = os.path.join(pool_dir, "verified_payload_logs.json")
    fixture_product = os.path.join(pool_dir, "aiello_product_fixtures.json")

    return config, log_json_path, fixture_product

config, LOG_JSON_PATH, FIXTURE_PRODUCT = load_backend_assets()

# ====================================================================
# 🎛️ 導覽列：切換「實時聯調中心」與「內部閉環報告」
# ====================================================================
st.title("🎛️ PMS AIoT 跨廠商大一統測試沙盒系統")
st.markdown("---")

# ====================================================================
# 🎛️ 戰略升級：多真實環境動態橫移大閘門
# ====================================================================
# 💡 config 是 process 共享的全域模組，多人共用同一個 Streamlit process 時
#    寫入它會互相覆蓋。這裡用 st.session_state 記住「這個瀏覽器分頁自己選了什麼」，
#    並在每次重新渲染、每次動作觸發前都強制把 config 校準回本分頁的選擇，
#    大幅縮小互相干擾的窗口。但這仍不是真正的多人隔離——若要完全不互相影響，
#    每位同事應各自啟動一份獨立的 Streamlit process（不同 port）。
def apply_env_to_config(target_env: str):
    config.ENV_SWITCH = target_env
    config.USE_REAL_SERVER = target_env.startswith("REAL")
    config.IS_OFFLINE = target_env == "LOCAL_OFFLINE"

    active_cfg = config.ENV_MATRIX.get(target_env, config.ENV_MATRIX["LOCAL"])
    config.CURRENT_TOKEN = active_cfg["TOKEN"]
    config.CURRENT_HEADERS_BACCHUS = active_cfg["HEADERS"]

    _base_ext = active_cfg["BASE_URL_EXTERNAL"]
    config.REAL_URL_ROOM_NOS   = f"{_base_ext}/room-pay/room-nos"
    config.REAL_URL_MIFARE_NOS = f"{_base_ext}/room-pay/mifare-nos"
    config.REAL_URL_ROOM_PAY   = f"{_base_ext}/room-pay"
    config.REAL_URL_ROOM_PAY_CANCEL = f"{_base_ext}/room-pay-cancel"
    config.REAL_URL_ROOM_BILLING    = f"{_base_ext}/room-billing"
    # 💡 鍵名必須對齊 config.py 真正送給德安雲端的 bacchus-* 查詢參數（修復原本誤寫成 hotel/athena）
    config.REAL_PARAMS_AMENITY["bacchus-hotelcod"] = active_cfg["HOTEL_COD"]
    config.REAL_PARAMS_AMENITY["bacchus-athenaid"] = active_cfg["ATHENA_ID"]
    config.CURRENT_PARAMS_AMENITY = config.REAL_PARAMS_AMENITY if config.USE_REAL_SERVER else {}

    config.REAL_URL_CAR_ARRIVAL = f"{_base_ext}/car-arrival"
    config.REAL_URL_CHECKIN     = f"{_base_ext}/check-in"
    config.REAL_PARAMS_PARKING["bacchus-hotelcod"] = active_cfg["HOTEL_COD"]
    config.REAL_PARAMS_PARKING["bacchus-athenaid"] = active_cfg["ATHENA_ID"]
    config.CURRENT_PARAMS_PARKING = config.REAL_PARAMS_PARKING if config.USE_REAL_SERVER else {}


# 1. 每個瀏覽器分頁第一次載入時，記住當下的環境作為自己的起點
if "chosen_env" not in st.session_state:
    st.session_state.chosen_env = getattr(config, "ENV_SWITCH", "LOCAL")

env_options = ["LOCAL_OFFLINE", "LOCAL", "REAL_QA", "REAL_UG"]

chosen_env = st.selectbox(
    "🎯 **選擇當前聯調戰場環境 (Dynamic Environment Switch)**",
    options=env_options,
    index=env_options.index(st.session_state.chosen_env)
)

# 2. 當使用者在網頁切換時，記住這個分頁自己的選擇，並套用到全域 config
if chosen_env != st.session_state.chosen_env:
    st.session_state.chosen_env = chosen_env
    apply_env_to_config(chosen_env)
    st.toast(f"🚀 環境成功動態切換至：【{chosen_env}】！後端發砲燃料已完成動態校準。", icon="🔄")
    time.sleep(0.5)
    st.rerun()

# 🔒 防禦性校準：就算其他分頁在中間動過全域 config，這裡一律以「本分頁記住的選擇」為準再套用一次
apply_env_to_config(st.session_state.chosen_env)

st.markdown("---")
st.caption("⚠️ 多人同時開啟同一個 Streamlit process 測試時，環境切換仍共享同一份後端狀態；如需完全互不干擾，請每位測試者各自啟動獨立的 Streamlit process。")

# 💡 用 st.radio 取代 st.tabs：radio 的選取值會自動保留於 session_state，
#    點擊按鈕觸發 rerun 後不會跳回第一個分頁（修復 st.tabs 一律重置為 Tab 0 的摩擦）。
_TAB_OPTIONS = ["🚀 實時聯調點火中心", "📊 內部閉環測試報告", "🗃️ 數據池資產 (Fixtures) 檢視"]
st.markdown("""
<style>
/* 把水平 radio 偽裝成 tabs：隱藏圓點、加上底部分隔線與作用中標示 */
div[role="radiogroup"][aria-orientation="horizontal"] { border-bottom: 1px solid rgba(49,51,63,0.12); padding-bottom: 0.4rem; }
div[role="radiogroup"][aria-orientation="horizontal"] label input { display: none; }
div[role="radiogroup"][aria-orientation="horizontal"] label { padding-right: 1.2rem; cursor: pointer; }
div[role="radiogroup"][aria-orientation="horizontal"] label[aria-checked="true"] p { color: #ff4b4b; font-weight: 600; }
</style>
""", unsafe_allow_html=True)
active_tab = st.radio("導覽列", _TAB_OPTIONS, horizontal=True, label_visibility="collapsed", key="active_tab")

# --------------------------------------------------------------------
# 🚀 TAB 1：實時聯調點火中心 (原有的高強健點火引擎)
# --------------------------------------------------------------------
if active_tab == _TAB_OPTIONS[0]:
    col_env1, col_env2 = st.columns(2)
    with col_env1:
        if config.ENV_SWITCH == "REAL_UG":
            st.success("🟢 當前環境：真實德安 UG 雲端 (REAL_UG_CLOUD) — E2E 串接測試")
        elif config.ENV_SWITCH == "REAL_QA":
            st.warning("🟠 當前環境：真實德安 QA 雲端 (REAL_QA_CLOUD) — E2E 串接測試")
        elif config.ENV_SWITCH == "LOCAL_OFFLINE":
            st.info("🔒 當前環境：閉環規格比對 (LOCAL_OFFLINE) — 不對外發送任何請求，僅比對 API Payload 是否符合規格")
        else:
            st.info("🔵 當前環境：本地隔離沙盒 (LOCAL_SANDBOX)")
    with col_env2:
        st.metric(label="全域通訊金鑰 (CURRENT_TOKEN)", value=str(getattr(config, "CURRENT_TOKEN", "None"))[:30] + "...")

    st.markdown("---")
    st.subheader("🔥 模擬發射器 (Simulators)")
    fire_speaker = st.button("🔥 啟動小美犀 1 ~ 8 全情境回歸發砲", type="primary", use_container_width=True)

    log_container = st.empty()
    log_container.code("⏳ 等待點火指令下達... 系統就緒。")

    if fire_speaker:
        log_container.code("🚀 正在加載自動化故事線，開始發砲...")
        from hardware.simulate_speaker import run_all_expanded_scenarios
        import logging

        class StreamlitLogHandler(logging.Handler):
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget
                self.log_txt = ""
            def emit(self, record):
                self.log_txt += self.format(record) + "\n"
                self.text_widget.code(self.log_txt)

        speaker_logger = logging.getLogger("SpeakerSimulator")
        handler = StreamlitLogHandler(log_container)
        speaker_logger.addHandler(handler)

        try:
            run_all_expanded_scenarios()
            st.balloons()
            st.success("🏁 全數擴充回歸情境流水線發射完賽！")
        except Exception as e:
            st.error(f"🚨 發射期中斷: {e}")
        finally:
            speaker_logger.removeHandler(handler)

# --------------------------------------------------------------------
# 📊 TAB 2：內部閉環測試報告 (完整記錄與報告中心)
# --------------------------------------------------------------------
elif active_tab == _TAB_OPTIONS[1]:
    st.header("📊 內部完全閉環自動化測試報告")
    
    col_rep1, col_rep2 = st.columns([1, 2])
    
    with col_rep1:
        st.subheader("🧪 離線盲測發動機 (Pytest Runner)")
        st.markdown("直接調用本地沙盒核心測試（`test_local_api.py` / `test_local_scenario.py`）。⚠️ 需先以 `python main.py` 啟動沙盒引擎（:5000）。")

        run_pytest = st.button("🧪 執行本地單元盲測 (Pytest)", use_container_width=True)
        pytest_log = st.empty()

        if run_pytest:
            with st.spinner("正在執行 Pytest 斷言校驗中..."):
                # 使用 subprocess 直接呼叫本地 pytest（以 sys.executable 確保用對 venv 的核心）
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "tests_localFullStackClose/test_local_api.py", "tests_localFullStackClose/test_local_scenario.py", "-v"],
                    capture_output=True, text=True, encoding="utf-8"
                )
                if result.returncode == 0:
                    st.success("✅ Pytest 內部斷言全數通過 (PASS)！")
                else:
                    st.error("🛑 部分單元測試斷言失敗 (FAIL)，請排查狀態機。")
                pytest_log.code(result.stdout if result.stdout else result.stderr)

    with col_rep2:
        st.subheader("📈 歷史入帳成功的真實戰績表 (Asset Logs)")
        
        # 讀取自動化資產落庫的 JSON 日誌
        if os.path.exists(LOG_JSON_PATH):
            try:
                with open(LOG_JSON_PATH, "r", encoding="utf-8") as f:
                    logs_data = json.load(f)
                
                st.markdown(f"目前數據池已安全收容 **{len(logs_data)}** 筆真實通關 Payload 資產。")
                
                # 簡單整理成易讀的格式呈現
                for i, log in enumerate(reversed(logs_data[-5:])): # 只顯示最新的 5 筆
                    with st.container(border=True):
                        st.markdown(f"**【紀錄 {i+1}】 情境：{log.get('scenario')}**")
                        st.caption(f"時間戳：{log.get('timestamp')} | 路由端點：`{log.get('endpoint')}` | 環境：{log.get('environment')}")
                        with st.expander("🔍 檢視完整入帳發砲 Payload 結構"):
                            st.json(log.get("payload"))
            except Exception as e:
                st.warning(f"讀取戰績日誌時發生異常: {e}")
        else:
            st.info("⏳ 目前尚無歷史入帳成功的 Payload 戰績紀錄，請先前往點火中心發砲。")

# --------------------------------------------------------------------
# 🗃️ TAB 3：數據池資產 (Fixtures) 檢視
# --------------------------------------------------------------------
elif active_tab == _TAB_OPTIONS[2]:
    st.header("🏗️ 測試資產數據池靜態燃料 (Static Fixtures)")
    st.markdown("這些是與業務代碼完全平級的標準測資，確保測試的可重現性。")
    
    st.subheader("🦏 小美犀備品與財務科目清單")
    if os.path.exists(FIXTURE_PRODUCT):
        with open(FIXTURE_PRODUCT, "r", encoding="utf-8") as f:
            st.json(json.load(f))
    else:
        st.caption("未找到 aiello_product_fixtures.json")

    st.caption("💡 目前數據池中唯一的靜態 Fixture 為 aiello_product_fixtures.json；其餘資產（如 verified_payload_logs.json）屬動態落庫紀錄，已於 Tab 2 呈現。")