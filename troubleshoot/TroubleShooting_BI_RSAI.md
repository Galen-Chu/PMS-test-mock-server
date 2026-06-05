# 🪵 API 自動化測試整合除錯日誌 (Troubleshooting & Architecture Log)
# 🦏 TroubleShooting_BI_RSAI.md —— 小美犀 (BR) 房務備品與入帳自動化串接日誌

本文件持續記錄德安 Athena PMS 系統與外部智慧語音系統聯調自動化框架時，所遭遇的**環境配置、網路拓撲、資料結構（Schema）以及商業邏輯校驗**之核心挑戰與處理解法。

---

## 🛠️ 核心 API 路由合約矩陣

| # | HTTP Method | API 路由端點 | 業務功能分類 | 觸發時機與物理現實 |
|---|-------------|--------------------------------------------|--------------|-------------------|
| 1 | `GET` | `/external/vendor-sync-data/room-pay/room-nos` | 被動房號查詢 | 客人用語音點餐/備品前，查驗在店住客記帳權限。 |
| 2 | `GET` | `/external/vendor-sync-data/room-pay/mifare-nos` | 被動卡號查詢 | 客人於場域刷房卡時，逆查綁定之房號與住客主檔。 |
| 3 | `POST` | `/external/vendor-sync-data/room-pay` | 餐廳住掛入帳 | 服務/餐點送達後，將消費金額正式打入 Folio 房間帳。|
| 4 | `POST` | `/external/vendor-sync-data/room-pay-cancel` | 餐廳住掛取消 | 餐點沖正或客人退點時，執行紅字作廢帳項交易。 |
| 5 | `POST` | `/external/vendor-sync-data/room-billing` | 房務服務入帳 | 異質備品付費或房務部衍生雜項之獨立扣款流程。 |

---

## 📅 Log 27: 異質系統平台化擴充——開闢小美犀房務備品 `amenity` 藍圖模組
* **日期**：2026-06-04
* **戰術定位**：
  宣布停車辨識模組成功達到 Production-ready 驗收。因應全新「小美犀房務備品物聯網串接」測試需求，正式發動平台化（Platform-level）擴充。
* **架構演進實作 (Blueprint Scale-up)**：
  1. **無痛解耦掛載**：於 `server/` 底下新增 `amenity/` 封閉目錄，嚴格遵循職責分離（SoC）原則，切斷與 `parking/` 模組的交叉干擾。
  2. **單一隧道多路複用**：於根目錄 `main.py` 透過 `app.register_blueprint(amenity_bp)` 進行聯調路由大一統註冊。專案維持共用 Port 5000 與單一 ngrok 穿透隧道，大幅免除重新校準雲端 Webhook 與網路配置之手工維運成本。
* **效益**：
  驗證了本測試沙盒框架極強的「多異質系統並存與高擴充性」底層基因。技術基礎設施正式跨入智慧飯店語音備品派工的全新領域知識（Domain Know-How）驗證期。
  
---

## 📅 Log 28: 小美犀 BR 房務串接啟動——五大雙向路由規格確立與日誌開闢
* **日期**：2026-06-05
* **架構背景**：
  停車辨識測試完全收網。跨入第二階段「小美犀語音備品與物聯網入帳」功能串接。本案涉及飯店業最嚴謹的「帳務處理（Folio Auditing）」與「身分查驗（In-House Auth）」，相較於車辨的白名單異動，此模組具備更高的交易原子性（Atomicity）要求。
* **技術戰術實施**：
  1. 開闢專屬維運文件 `TroubleShooting_BI_RSAI.md`，實施異質系統日誌解耦。
  2. 規劃「2支GET被動防禦查詢」與「3支POST非同步帳務匯入」之路由邊界，完全適配 Flask 藍圖與策略模式骨架。
* **預期效益**：
  透過沙盒平台化多路複用的優勢，不改動網路與 ngrok 基礎設施，直接進入小美犀數據流量清洗與高傳真帳務測試期。