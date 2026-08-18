# fetch_liveam_swagger.py — 下載華豫寧 LiveAM 測試環境的 OpenAPI 規格檔(SA 文件明載之測試環境)
# 來源:https://liveamcore1.waferlock.com:10001/swagger/v1/swagger.json(規格檔公開,僅呼叫 API 需 JWT)
import json
import re
import sys

import requests

URL = "https://liveamcore1.waferlock.com:10001/swagger/v1/swagger.json"

r = requests.get(URL, timeout=30)
r.raise_for_status()
doc = r.json()

with open("sa_docs/sa7_liveam_swagger.json", "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)

paths = doc.get("paths", {})
print("total paths:", len(paths))
targets = [p for p in paths if re.search(r"/api/(Order|Auth|Operation|Room|AppLink)", p)]
for p in sorted(targets):
    for m, op in paths[p].items():
        if m in ("get", "post", "put", "delete", "patch"):
            body = [q.get("schema", {}).get("$ref", "") for q in op.get("parameters", []) if q.get("in") == "body"]
            print(f"{m.upper():6} {p}  {op.get('summary', '')}  body={body}")
