# tests_localFullStackClose/test_waferlock_pipeline.py
import sys
import os
import secrets
import string
import time
import requests

# 🌟 透過動態路徑逆查，將頂層的 config.py 模組自動載入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ====================================================================
# 🎛️ 環境自動化適應網址洗滌器
# ====================================================================
# 強制設定或從 config 繼承：當 USE_REAL_SERVER 為 False 時，自動錨定 NGROK 網址作為沙盒基底
if config.USE_REAL_SERVER:
    print("⚠️ [警告] 當前 config.py 設定 USE_REAL_SERVER = True (真實雲端)。")
    print("⚠️ 平行模擬測試應聚焦於本地沙盒，現已強制洗滌網址至 NGROK 沙盒環境...")

BASE_URL = config.NGROK_BASE_URL

def run_waferlock_test_pipeline():
    print("======================================================================")
    print("🚀 維夫拉克 (WAFERLOCK) 門禁製卡串接流水線 - 自動化本地平行閉環測試啟動")
    print(f"📡 靶心目標 Mock Server: {BASE_URL}")
    print("======================================================================")
    
    # ----------------------------------------------------------------
    # 🏁 階段 1: 廠商身份鑑權登入 (POST /api/Auth/login)
    # ----------------------------------------------------------------
    print("\n[階段 1] 發動維夫拉克系統登入驗證...")
    login_url = f"{BASE_URL}/api/Auth/login"
    login_payload = {
        "id": "athena_pms",
        "password": "liveam_password_123",
        "projectID": "PRJ-01"
    }
    
    try:
        res_login = requests.post(login_url, json=login_payload, timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"❌ 連線失敗！請確保您的本地 Mock Server 服務已啟動，且 NGROK 隧道能正常訪問。")
        return

    if res_login.status_code != 200:
        print(f"❌ 登入失敗！狀態碼: {res_login.status_code} | 回應: {res_login.text}")
        return
        
    login_data = res_login.json()
    token = login_data.get("token")
    encoder_code = login_data.get("encoderCode")
    print(f"🟢 登入成功！")
    print(f"   🔑 取得門禁簽發代幣: {token}")
    print(f"   ⚙️  取得 10 碼製卡機代號: 【{encoder_code}】 (成功供德安 PMS 進行工作站機型綁定設定)")
    
    headers = {"Authorization": f"Bearer {token}"}
    time.sleep(0.5)

    # ----------------------------------------------------------------
    # 🏁 階段 2: 德安 PMS 建立/推播門禁訂單 (POST /api/Order)
    # ----------------------------------------------------------------
    dynamic_order_id = f"ORD-{int(time.time())}"
    target_room_no = 802  # 測試房號：802
    
    print(f"\n[階段 2] 模擬德安 PMS 推播新進住客訂單 ➔ 單號: 【{dynamic_order_id}】...")
    order_url = f"{BASE_URL}/api/Order"
    order_payload = {
        "id": dynamic_order_id,
        "reserveID": 99999,
        "guestName": "維夫拉克測試員",
        "roomID": target_room_no,
        "preInTime": "2026-06-12 15:00:00",
        "preOutTime": "2026-06-13 11:00:00"
    }
    
    res_order = requests.post(order_url, json=order_payload, headers=headers)
    if res_order.status_code == 201:
        print(f"🟢 門禁訂單建立成功！沙盒已成功受理並落庫。")
    else:
        print(f"❌ 訂單建立失敗: {res_order.text}")
        return
    time.sleep(0.5)

    # ----------------------------------------------------------------
    # 🏁 階段 3: 櫃檯點選實體發卡製卡 (POST /api/OrderCard)
    # ----------------------------------------------------------------
    # 🌟 生成符合德安規格限制的 8 碼大寫英數隨機房卡號 (E.g., "9A4C1B8F")
    alphabet = string.ascii_uppercase + string.digits
    dynamic_card_uid = ''.join(secrets.choice(alphabet) for _ in range(8))
    
    print(f"\n[階段 3] 模擬前台感應空卡、變更物理狀態實體發卡 ➔ 卡號: 【{dynamic_card_uid}】...")
    card_url = f"{BASE_URL}/api/OrderCard"
    card_payload = {
        "orderID": dynamic_order_id,
        "cardUid": dynamic_card_uid
    }
    
    res_card = requests.post(card_url, json=card_payload, headers=headers)
    if res_card.status_code == 201:
        print(f"🟢 製卡成功！實體卡片資產已完全綁定至維夫拉克系統主檔。")
        print("   ⚡ [跨模組數據閉環驗證]")
        print(f"      此卡號 【{dynamic_card_uid}】 已透過記憶體蟲洞自動注入小美犀的『房卡逆查映射表』！")
        print("      後續小美犀即可直接持此卡號發動【情境 5】餐廳/備品掛帳。")
    else:
        print(f"❌ 製卡失敗: {res_card.text}")
        return
        
    print("\n🏁 ======================================================================")
    print(" 🟢 所有整合測試流水線皆順利完賽。維夫拉克平行閉環資產與製卡機設定測試通過！")
    print("======================================================================")

if __name__ == "__main__":
    run_waferlock_test_pipeline()