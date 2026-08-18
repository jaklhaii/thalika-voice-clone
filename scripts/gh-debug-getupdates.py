"""Debug helper for GH Actions: dump the last getUpdates poll result.
Uses env BOT_TOKEN (falls back to bot.py hardcoded token)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import urllib.parse
import urllib.request

try:
    token = os.environ.get("BOT_TOKEN", "") or __import__("bot").BOT_TOKEN
except Exception:
    token = ""

url = "https://api.telegram.org/bot%s/%s" % (token or "PUT_TOKEN_HERE", urllib.parse.quote("getUpdates"))
data = json.dumps({"offset": 0, "timeout": 5, "allowed_updates": ["message"]}).encode()
req = urllib.request.Request(url, data, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
        res = d.get("result", [])
        print("ok:", d.get("ok"), "updates:", len(res))
        for u in res[:6]:
            m = u["message"]
            print(u["update_id"], m.get("from", {}).get("id"), repr((m.get("text") or "")[:40]))
except Exception as e:
    print("getUpdates error:", e)
