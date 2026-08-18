"""scheduler P3: 各 preset 会话默认模型探测。

对四个 preset 各开一个会话读 session.models.current——确定 selectModel 的
"切换前"基线。结果落盘 probe_preset_defaults.json。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:3080/api"
CWD = r"F:\deepseek"
PRESETS = ["research-collab", "qa-gate", "daily-assistant", "standard"]


def rpc(method: str, payload: dict) -> dict:
    body = json.dumps({"type": "client-request", "rpcId": f"pd-{time.time_ns()}",
                       "method": method, "payload": payload}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/{method}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        envelope = json.loads(resp.read().decode("utf-8"))
    result = envelope["result"]
    if not result.get("ok"):
        raise RuntimeError(f"{method} failed: {result.get('error')}")
    return result["value"]


def main() -> int:
    out = {}
    for preset in PRESETS:
        sid = rpc("session.create", {"agentPreset": preset, "cwd": CWD})["sessionId"]
        try:
            rpc("session.rename", {"sessionId": sid,
                                   "title": f"sched-probe-default {preset}"})
        except Exception:  # noqa: BLE001
            pass
        m = rpc("session.models", {"sessionId": sid})
        out[preset] = {"session": sid, "current": m.get("current"),
                       "routable": m.get("routable")}
        print(f"{preset} -> {m.get('current')} routable={m.get('routable')}")
    p = Path(__file__).resolve().parent / "probe_preset_defaults.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
