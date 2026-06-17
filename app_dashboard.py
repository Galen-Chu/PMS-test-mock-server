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
    # 物理路徑定義
    pool_dir = os.path.join(current_dir, "tests_data_pool")
    log_json_path = os.path.join(pool_dir, "verified_payload_logs.json")
    fixture_product = os.path.join(pool_dir, "aiello_product_fixtures.json")
    fixture_car = os.path.join(pool_dir, "shin_yeong_car_fixtures.json")
    
    # 嘗試導入後端記憶體 DB（供視覺化觀測）
    try:
        from server.keycard.routes import WaferlockLiveam_card_mapping_db
        from server.parking.vendors.vendor_PAYTRONEX import mock_paytronex_roomer_db
    except Exception:
        WaferlockLiveam_card_mapping_db, mock_paytronex_roomer_db = {}, {}
        
    return config, log_json_path, fixture_product, fixture_car, WaferlockLiveam_card_mapping_db, mock_paytronex_roomer_db

config, LOG_JSON_PATH, FIXTURE_PRODUCT, FIXTURE_CAR, card_db, parking_db = load_backend_assets()

# ====================================================================
# 🎛️ 導覽列：切換「實時聯調中心」與「內部閉環報告」
# ====================================================================
st.title("🎛️ PMS AIoT 跨廠商大一統測試沙盒系統")
st.markdown("---")

# ====================================================================
# 🎛️ 戰略升級：多真實環境動態橫移大閘門
# ====================================================================
# 1. 在網頁渲染一個下拉選單，預設停留在 config.py 當前設定的環境
env_options = ["LOCAL", "REAL_QA", "REAL_UG"]
default_index = env_options.index(getattr(config, "ENV_SWITCH", "LOCAL"))

chosen_env = st.selectbox(
    "🎯 **選擇當前聯調戰場環境 (Dynamic Environment Switch)**", 
    options=env_options, 
    index=default_index
)

# 2. 當使用者在網頁切換時，動態改寫 config 的變數並重新洗滌齒輪
if chosen_env != config.ENV_SWITCH:
    config.ENV_SWITCH = chosen_env
    config.USE_REAL_SERVER = chosen_env.startswith("REAL")
    
    # 重新對齊 config 內部的所有變數與 Headers
    active_cfg = config.ENV_MATRIX.get(chosen_env, config.ENV_MATRIX["LOCAL"])
    config.CURRENT_TOKEN = active_cfg["TOKEN"]
    config.CURRENT_HEADERS_BACCHUS = active_cfg["HEADERS"]
    
    # 重新洗滌小美犀 URLs 與 Params
    _base_ext = active_cfg["BASE_URL_EXTERNAL"]
    config.REAL_URL_ROOM_NOS   = f"{_base_ext}/room-pay/room-nos"
    config.REAL_URL_MIFARE_NOS = f"{_base_ext}/room-pay/mifare-nos"
    config.REAL_URL_ROOM_PAY   = f"{_base_ext}/room-pay"
    config.REAL_URL_ROOM_PAY_CANCEL = f"{_base_ext}/room-pay-cancel"
    config.REAL_URL_ROOM_BILLING    = f"{_base_ext}/room-billing"
    config.REAL_PARAMS_AMENITY["hotel"] = active_cfg["HOTEL_COD"]
    config.REAL_PARAMS_AMENITY["athena"] = active_cfg["ATHENA_ID"]
    config.CURRENT_PARAMS_AMENITY = config.REAL_PARAMS_AMENITY if config.USE_REAL_SERVER else {}
    
    # 重新洗滌車辨 URLs 與 Params
    config.REAL_URL_CAR_ARRIVAL = f"{_base_ext}/car-arrival"
    config.REAL_PARAMS_PARKING["hotel"] = active_cfg["HOTEL_COD"]
    config.REAL_PARAMS_PARKING["athena"] = active_cfg["ATHENA_ID"]
    config.CURRENT_PARAMS_PARKING = config.REAL_PARAMS_PARKING if config.USE_REAL_SERVER else {}
    
    st.toast(f"🚀 環境成功動態切換至：【{chosen_env}】！後端發砲燃料已完成動態校準。", icon="🔄")
    time.sleep(0.5)
    st.rerun()

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["🚀 實時聯調點火中心", "📊 內部閉環測試報告", "🗃️ 數據池資產 (Fixtures) 檢視"])

# --------------------------------------------------------------------
# 🚀 TAB 1：實時聯調點火中心 (原有的高強健點火引擎)
# --------------------------------------------------------------------
with tab1:
    col_env1, col_env2 = st.columns(2)
    with col_env1:
        if config.ENV_SWITCH == "REAL_UG":
            st.success("🟢 當前環境：真實德安 UG 雲端 (REAL_UG_CLOUD)")
        elif config.ENV_SWITCH == "REAL_QA":
            st.warning("🟠 當前環境：真實德安 QA 雲端 (REAL_QA_CLOUD)")
        else:
            st.info("🔵 當前環境：本地隔離沙盒 (LOCAL_SANDBOX)")
    with col_env2:
        st.metric(label="全域通訊金鑰 (CURRENT_TOKEN)", value=str(getattr(config, "CURRENT_TOKEN", "None"))[:30] + "...")

    st.markdown("---")
    col_l, col_r = st.columns([1, 1.2])
    
    with col_l:
        st.subheader("📡 廠商即時記憶體快取 (Live Cache)")
        with st.expander("💳 華豫寧門禁 Mapping DB 狀態", expanded=True):
            st.json(card_db)
        with st.expander("🚗 博辰車辨 Roomer DB 狀態", expanded=True):
            st.json(parking_db)

    with col_r:
        st.subheader("🔥 模擬發射器 (Simulators)")
        fire_speaker = st.button("🔥 啟動小美犀 1 ~ 8 全情境回歸發砲", type="primary", use_container_width=True)
        
        log_container = st.empty()
        log_container.code("⏳ 等待點火指令下達... 系統就緒。")

        if fire_speaker:
            log_container.code("🚀 正在加載自動化故事線，開始對真實雲端發砲...")
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
with tab2:
    st.header("📊 內部完全閉環自動化測試報告")
    
    col_rep1, col_rep2 = st.columns([1, 2])
    
    with col_rep1:
        st.subheader("🧪 離線盲測發動機 (Pytest Runner)")
        st.markdown("直接調用 `tests_localFullStackClose/test_local_sandbox.py` 進行沙盒核心極限測試。")
        
        run_pytest = st.button("🧪 執行本地單元盲測 (Pytest)", use_container_width=True)
        pytest_log = st.empty()
        
        if run_pytest:
            with st.spinner("正在執行 Pytest 斷言校驗中..."):
                # 使用 subprocess 直接呼叫本地 pytest 
                result = subprocess.run(
                    ["pytest", "tests_localFullStackClose/test_local_sandbox.py", "-v"], 
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
with tab3:
    st.header("🏗️ 測試資產數據池靜態燃料 (Static Fixtures)")
    st.markdown("這些是與業務代碼完全平級的標準測資，確保測試的可重現性。")
    
    col_fix1, col_fix2 = st.columns(2)
    
    with col_fix1:
        st.subheader("🦏 小美犀備品與財務科目清單")
        if os.path.exists(FIXTURE_PRODUCT):
            with open(FIXTURE_PRODUCT, "r", encoding="utf-8") as f:
                st.json(json.load(f))
        else:
            st.caption("未找到 aiello_product_fixtures.json")
            
    with col_fix2:
        st.subheader("🚗 車辨常用白名單車牌清單")
        if os.path.exists(FIXTURE_CAR):
            with open(FIXTURE_CAR, "r", encoding="utf-8") as f:
                st.json(json.load(f))
        else:
            st.caption("未找到 shin_yeong_car_fixtures.json")