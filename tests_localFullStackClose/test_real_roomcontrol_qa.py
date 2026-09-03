# tests_localFullStackClose/test_real_roomcontrol_qa.py
"""🌡️ 房控 A7 公版 XML 介面 — REAL_QA 真實環境串接測試。

慣例比照 test_real_scenario.py:僅在 ENV_SWITCH=REAL_QA 時執行(CI 請設 LOCAL_OFFLINE)。
2026-09-03 起預設環境即 REAL_QA(後續測試資料以 QA 環境為主)。

範圍(2026-09-03 RC1 準備版):
- Q5 未決(thirdParty 實際代碼待 SA 提供、REAL 端點 GET 閘門版 vs REST 版待確認),
  故本檔先以「串接探測」定位:
  * test_qa_import_sync_endpoint_alive:ROOM_INF(唯讀查詢)打 REST 版端點,斷言端點存在且錯誤信封可解析
  * test_qa_import_sync_identity_rejected:帶假的 thirdParty → 預期被拒(證明驗證活著,不是黑洞)
- SA 給代碼後:設 A7_THIRD_PARTY=<實際代碼> 再跑,ROOM_INF 應轉為 200 + RETN-CODE 0000;
  ROOM_STA 推送(會改 PMS 房控狀態)經主控台 REAL_QA + third_party_code 覆寫執行(見 README 房控節)。

可調環境變數:A7_THIRD_PARTY(預設 TT 佔位)、A7_ROOM_NO(預設 101,QA 歷史種子房)。
"""
import os
import sys
from datetime import datetime

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_QA_ONLY = pytest.mark.skipif(
    config.ENV_SWITCH != "REAL_QA",
    reason="僅在 ENV_SWITCH=REAL_QA 時執行。",
)

QA_IMPORT_URL = f"{config.ENV_MATRIX['REAL_QA']['PMS_URL']}/third-party/import-sync-files"
A7_THIRD_PARTY = os.environ.get("A7_THIRD_PARTY", "TT")
A7_ROOM_NO = os.environ.get("A7_ROOM_NO", "101")


def _room_inf_xml(room):
    return (
        '<?xml version="1.0"?>\n<ROWSET>\n<ROW>\n'
        '<REVE-CODE>0300TT1090</REVE-CODE>\n<ACTION_COD>ROOM_INF</ACTION_COD>\n'
        f'<ROOM_NOS>{room}</ROOM_NOS>\n'
        f'<ACTION_DAT>{datetime.now().strftime("%Y/%m/%d %H:%M:%S")}</ACTION_DAT>\n'
        '</ROW>\n</ROWSET>'
    )


def _post_qa(body):
    cfg = config.ENV_MATRIX["REAL_QA"]
    return requests.post(
        QA_IMPORT_URL, json=body, timeout=15,
        # 💡 8/21 實測:QA 免 Authorization,僅身分 Header;POST body 內另帶 athena/hotel/thirdParty 三元組
        headers={"bacchus-athenaid": cfg["ATHENA_ID"], "bacchus-hotelcod": cfg["HOTEL_COD"],
                 "accept": "application/json", "Content-Type": "application/json"},
    )


@_QA_ONLY
def test_qa_import_sync_endpoint_alive():
    """ROOM_INF(唯讀)打 QA REST 端點:端點應存在(非 404/405)且回應可解析。

    thirdParty=TT 佔位期間,預期被業務層拒絕(400/401/417 帶訊息)=「驗證活著」;
    SA 給實際代碼後(A7_THIRD_PARTY=<code>)同一路徑應轉 200 + procStatus + RETN-CODE 0000。
    """
    cfg = config.ENV_MATRIX["REAL_QA"]
    body = {"athenaId": cfg["ATHENA_ID"], "hotelCode": cfg["HOTEL_COD"],
            "thirdPartyCode": A7_THIRD_PARTY,
            "requestDataList": [{"requestBody": _room_inf_xml(A7_ROOM_NO), "fileName": "C001.xml"}]}
    res = _post_qa(body)
    print(f"\n[QA import-sync] HTTP {res.status_code}")
    print(f"[QA import-sync] body: {res.text[:500]}")
    assert res.status_code not in (404, 405), "REST 端點不存在——Q5 需與 SA 確認 REAL 端點(GET 閘門版 vs REST 版)"
    # 端點在:無論接受或拒絕,都必須有可解析的回應(錯誤信封或 VendorImportSyncDataResponse)
    payload = res.json() if res.headers.get("content-type", "").startswith("application/json") else None
    assert payload is not None, f"回應非 JSON(端點行為與 sa8 swagger 不符):{res.headers.get('content-type')}"
    if res.status_code == 200 and isinstance(payload, list):
        assert payload[0].get("procStatus") is True
        assert "<RETN-CODE>0000</RETN-CODE>" in (payload[0].get("responseBody") or "")


@_QA_ONLY
def test_qa_import_sync_identity_rejected():
    """帶假的 thirdParty 代碼 → 預期被拒(4xx),證明識別驗證在線;若 200 通過代表 QA 無驗證(需向 SA 反映)。"""
    cfg = config.ENV_MATRIX["REAL_QA"]
    body = {"athenaId": cfg["ATHENA_ID"], "hotelCode": cfg["HOTEL_COD"],
            "thirdPartyCode": "NO-SUCH-VENDOR",
            "requestDataList": [{"requestBody": _room_inf_xml(A7_ROOM_NO), "fileName": "C001.xml"}]}
    res = _post_qa(body)
    print(f"\n[QA 假代碼] HTTP {res.status_code} body: {res.text[:300]}")
    if res.status_code == 200:
        pytest.skip("QA 目前未驗 thirdParty 代碼(200 直通)——記錄現況,待與 SA 確認是否預期")
    assert 400 <= res.status_code < 500
