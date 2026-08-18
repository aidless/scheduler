"""scheduler P3: 模型目录探测（session.models）。

开一个最小会话，读部署的模型路由目录：current（当前选择）/routable（可否切换）/
groups（provider→模型清单）/failures（目录加载失败项）。
结果落盘 probe_models.json——P3 映射表设计的输入。

用法: python probe_models.py [--out probe_models.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:3080/api"
CWD = r"F:\deepseek"


def rpc(method: str, payload: dict) -> dict:
    body = json.dumps({"type": "client-request", "rpcId": f"pm-{time.time_ns()}",
                       "method": method, "payload": payload}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/{method}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        envelope = json.loads(resp.read().decode("utf-8"))
    if envelope.get("type") != "server-response":
        raise RuntimeError(f"bad envelope from {method}: {envelope}")
    result = envelope["result"]
    if not result.get("ok"):
        raise RuntimeError(f"{method} failed: {result.get('error')}")
    return result["value"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "probe_models.json")
    args = ap.parse_args()
    sid = rpc("session.create", {"agentPreset": "minimal", "cwd": CWD})["sessionId"]
    try:
        rpc("session.rename", {"sessionId": sid, "title": "sched-probe-models"})
    except Exception:  # noqa: BLE001
        pass
    models = rpc("session.models", {"sessionId": sid})
    payload = {"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "session": sid, "models": models}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"current: {models.get('current')}")
    print(f"routable: {models.get('routable')}")
    for g in models.get("groups", []):
        ids = [m["id"] for m in g.get("models", [])]
        print(f"provider {g.get('id')} ({g.get('name')}): {ids}")
    for f in models.get("failures", []):
        print(f"failure: {f}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
