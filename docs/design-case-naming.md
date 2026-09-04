# 🏷️ 測試案例命名規則(Case Naming Convention)v1

> 版本:v1(2026-09-03,源自 UI 驗收回饋:各模組路由命名參差,統一以獲得一致 UX)
> 適用範圍:`@register_scenario(..., name=...)` 的顯示名稱(UI 案例矩陣/結果頁/報告)。
> case_id(endpoint 鍵)不在此規則內——那是程式鍵,穩定不改名。

## 規則

1. **主名稱 =「動詞 + 受詞」的中文業務語意**,建議 ≤ 12 字。
   - 不含模組前綴詞(「公版」「正規」「管線」「跨模組」不當前綴,移入括號標籤)
   - 不含廠商名(UI 已按模組 × 廠商分組,名稱重複反而冗餘)
2. **括號 = 結構化標籤**,以「・」分隔,**依固定順序**呈現,無資訊可補則整個括號省略:
   | 順序 | 標籤 | 範例 |
   |---|---|---|
   | a | 方向 / 介面族(模組內雙向或有多介面族時才標) | `(推播)` `(回推)` `(公版)` `(沙盒內部)` |
   | b | 合約 / SA 動作代號或端點簡稱 | `(CKI・填checkinTime)` `(B4・ROOM_STA)` `(roomer/add)` |
   | c | 負面碼:HTTP 碼・SA code | `(417・1001)` |
   | d | 多步管線:N步・首步→末步 | `(2步・查租約→銷帳)` |
   | e | 特殊行為 | `兩筆連發` `閉環` `重刪404` `SA未定義` |
3. **分隔符統一**:標籤內用「・」(不用 `/`、`+`);步驟鏈用「→」。
4. **name 與 endpoint 分工**:name 講「做什麼」(業務),endpoint 講「打哪裡」(技術)——名稱不重複路徑。
5. **負面路徑**主名稱以「查無 / 缺(欄位) / 重複 / 無效 / 非法」開頭,錯誤碼進括號 c 段。

## 對照表(2026-09-03 套用)

### 🦏 amenity / BR_AIELLO
| case_id | 舊名 | 新名 |
|---|---|---|
| room_nos_query | 房號查詢 | 房號查詢住客 |
| mifare_query | Mifare 卡號查詢 | 卡號查詢住客(Mifare) |
| amenity_charge | 備品入帳 | 備品入帳(2步・查房→過帳) |
| amenity_cancel | 入帳沖銷 | 掛帳沖銷(2步・掛帳→作廢) |
| billing_sync | 帳務同步 | 餐廳住掛 |
| room_nos_query_notfound | 查無房號(417/1001) | 查無房號(417・1001) |
| mifare_query_notfound | 查無房卡卡號(417/1001) | 查無卡號(417・1001) |
| amenity_billing_notfound | 備品入帳無住客(417/1001) | 入帳無住客(417・1001) |
| amenity_pay_duplicate | 重複掛帳(417/1010) | 重複掛帳(417・1010) |
| amenity_cancel_notfound | 取消查無單號(417/2001) | 沖銷查無單(417・2001) |

### 🚗 parking / SHIN_YEONG
| case_id | 舊名 | 新名 |
|---|---|---|
| car_arrival | 車輛抵達回推 | 車輛抵達(回推) |
| checkin_sync | 住客入住同步 | 住客入住(推播) |
| whitelist_update | PMS 白名單異動 | 白名單總覽(沙盒內部) |
| night_audit | 夜核名單同步 | 夜核名單(推播) |
| change_checkout | 延長/修改退房 | 修改退房時間(推播) |
| change_car_nos | 車牌三態異動 | 車牌異動(推播) |
| check_in_cancel | 取消入住 | 取消入住(推播) |
| parking_sync_checkin | 公版入住啟用 | 入住啟用(公版) |
| parking_sync_change_car | 公版換車號(舊停用+新啟用兩筆) | 換車號(公版・兩筆連發) |
| parking_sync_disable | 公版清除車號(停用) | 清除車號(公版) |
| parking_sync_cancel | 公版取消入住(當日結束) | 取消入住(公版) |
| parking_sync_invalid | 公版參數錯誤(is_enabled 非法) | 非法參數(公版・1000) |
| car_arrival_missing_field | 車輛抵達缺必填(417/1000) | 缺必填欄位(回推・417・1000) |

### 🚗 parking / PAYTRONEX
| case_id | 舊名 | 新名 |
|---|---|---|
| car_arrival_pt | 新增房客預約(車輛抵達) | 新增房客預約(roomer/add) |
| car_arrival_retry | 車牌逆查(逾時重試) | 車牌逆查租約(find) |
| paytronex_cancel_checkin | 取消入住管線(查租約→更新銷帳) | 取消入住(2步・查租約→銷帳) |
| paytronex_clear_plate | 清除車號管線(查租約→空車牌更新) | 清除車號(2步・查租約→清牌) |
| paytronex_change_plate | 更新車號管線(查舊牌→新牌更新) | 更新車號(2步・查舊牌→換新牌) |
| paytronex_change_checkout | 修改退房管線(查租約→新EndTime更新) | 修改退房(2步・查租約→改EndTime) |
| paytronex_find_unknown | 查無車牌(動態虛擬租約・SA未定義) | 查無車牌(SA未定義・虛擬租約) |

### 🔑 keycard / WAFERLOCK・LIVEAM
| case_id | 舊名 | 新名 |
|---|---|---|
| keycard_login | 登入取得Token | 登入取得Token(Auth) |
| keycard_room_lookup | 房號轉房間編號 | 房號轉編號(getRoomIdByName) |
| keycard_make_card | 正規製卡管線(訂單→讀卡→綁定) | 製卡(3步・訂單→讀卡→綁定) |
| keycard_checkin_open | 入住開門(CKI・填checkinTime) | (不變,已符合) |
| keycard_checkout_invalidate | 退房取消失效(填checkoutTime) | 退房失效(CIX・填checkoutTime) |
| keycard_change_checkout | 修改退房時間(改PreOutTime) | (不變,已符合) |
| keycard_revoke_card | 刪卡(DELETE + 重刪404) | 刪卡(重刪404) |
| keycard_bad_token | 無效Token(401) | (不變,已符合) |
| card_lifecycle | 跨模組卡片生命週期閉環(真實管線製卡→mifare 刷回房號) | 卡片生命週期(跨模組閉環) |
| card_issue_exception | 製卡例外重試 | 製卡例外重試(LIVEAM客製) |

### 🌡️ roomcontrol / MINXON・CHAOFENG
| case_id | 舊名 | 新名 |
|---|---|---|
| rc_{vendor}_room_sta_push | 房況推送 ROOM_STA/B4(民笙…) | 房況推送(B4・ROOM_STA) |
| rc_{vendor}_room_inf | 房況查詢 ROOM_INF/A6(民笙…) | 房況查詢(A6・ROOM_INF) |
| rc_{vendor}_return | 全房況查詢 RETURN/A10(民笙…) | 全房況查詢(A10・RETURN) |

### 🌡️ roomcontrol RC2 新增(2026-09-04,新案直接依規則命名,非改名)
| case_id | 名稱 | 說明 |
|---|---|---|
| rc_{vendor}_clean | 清潔狀態推送(B4・CLEAN) | ACTION_STA=位元9 值域 0-4 |
| rc_{vendor}_rmtemp | 室溫推送(B4・RMTEMP) | #RMTEMP#26C#;A7 前台顯示 |
| rc_{vendor}_keybox | 插拔卡現況推送(B5・KeyBox) | REVE 4390;ACTION_STA 1插/0拔 |
| rc_{vendor}_bad_xml | 無效XML(417) | 負面:壞格式 XML |
| rc_{vendor}_unknown_action | 無效動作代碼(RETN・9999) | 負面:未知 ACTION_COD |
| rc_{vendor}_missing_room_nos | 缺房號欄位(417) | 負面:ROOM_NOS 缺欄 |

## 新案例 checklist(DoD)

新增案例時:名稱照 §規則 1–5;PR 自查「同名 across 模組是否語意混淆」「括號標籤順序是否一致」;
本文件對照表同步補列。
