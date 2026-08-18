"""tool-scheduler 端到端验证：新建 research-collab 会话，确认 scheduler 工具对模型可见。

通过 host RPC（session.create → prompt → history）驱动一个全新会话，
让模型报告其工具目录里是否有名为 scheduler 的工具。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:3080/api"
CWD = r"F:\deepseek"


def rpc(method: str, payload: dict) -> dict:
    body = json.dumps({"type": "client-request", "rpcId": f"e2e-{time.time_ns()}",
                       "method": method, "payload": payload}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/{method}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        envelope = json.loads(resp.read().decode("utf-8"))
    result = envelope["result"]
    if not result.get("ok"):
        raise RuntimeError(f"{method} failed: {result.get('error')}")
    return result["value"]


def all_events(session_id: str) -> list:
    events: dict[int, dict] = {}
    before = None
    for _ in range(50):
        payload = {"sessionId": session_id, "maxMessages": 400}
        if before is not None:
            payload["beforeSeq"] = before
        page = rpc("session.history", payload)
        evs = page.get("events", [])
        if not evs:
            break
        for item in evs:
            ev = item.get("event", item)
            events[ev["seq"]] = ev
        if not page.get("hasMore"):
            break
        before = min(e["seq"] for e in events)
    return [events[k] for k in sorted(events)]


def main() -> int:
    sid = rpc("session.create", {"agentPreset": "research-collab", "cwd": CWD})["sessionId"]
    print("session:", sid)
    try:
        rpc("session.rename", {"sessionId": sid, "title": "sched-plugin-e2e"})
    except Exception:  # noqa: BLE001
        pass
    prompt = ("请只检查你的可用工具列表：其中是否存在一个名为 scheduler 的工具？"
              "只回答一行：有 或 没有。不要调用任何工具，不要解释。")
    rpc("session.prompt", {"sessionId": sid, "mode": "queue",
                           "content": [{"type": "text", "text": prompt}]})
    deadline = time.time() + 240
    answer = ""
    while time.time() < deadline:
        events = all_events(sid)
        if any(e["type"] == "turn/end" for e in events):
            for ev in events:
                if ev.get("type") == "assistant/message":
                    m = (ev.get("data") or {}).get("message") or {}
                    for block in m.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text":
                            answer += block.get("text", "")
            break
        time.sleep(5)
    answer = answer.strip()
    print("model answer:", answer or "(empty)")
    has = ("有" in answer) and ("没有" not in answer.replace("没有", "")) if answer else False
    # 简单判定：出现"有"且非"没有"
    verdict = "TOOL_VISIBLE" if (answer.startswith("有") or answer == "有") else \
              ("TOOL_NOT_VISIBLE" if "没有" in answer else "UNCLEAR")
    print("verdict:", verdict)
    return 0 if verdict == "TOOL_VISIBLE" else 1


if __name__ == "__main__":
    sys.exit(main())
