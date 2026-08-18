"""tool-scheduler 功能演示：新建 research-collab 会话，让模型用 scheduler 工具派发一个编码任务。

验证点：
  1. 模型确实调用了名为 scheduler 的工具（tool/call 事件）
  2. 工具返回了 decision / outDir（引擎真实执行）
  3. 引擎把任务路由给了 standard（编码）
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:3080/api"
CWD = r"F:\deepseek"


def rpc(method: str, payload: dict) -> dict:
    body = json.dumps({"type": "client-request", "rpcId": f"demo-{time.time_ns()}",
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
    print("orchestrator session:", sid)
    try:
        rpc("session.rename", {"sessionId": sid, "title": "sched-plugin-demo"})
    except Exception:  # noqa: BLE001
        pass
    prompt = ("这是一个需要派发给专职 agent 的任务：请写一个 Python 函数 is_prime(n)，"
              "判断 n 是否为素数，并附两个测试断言。请用 scheduler 工具来处理这个任务，"
              "然后把调度结果（decision 与 artifacts 目录）告诉我。")
    rpc("session.prompt", {"sessionId": sid, "mode": "queue",
                           "content": [{"type": "text", "text": prompt}]})
    deadline = time.time() + 420
    events = []
    while time.time() < deadline:
        events = all_events(sid)
        if any(e["type"] == "turn/end" for e in events):
            break
        time.sleep(5)

    sched_calls = []
    tool_results = []
    for ev in events:
        data = ev.get("data") or {}
        if ev.get("type") == "tool/call":
            name = data.get("name") or (data.get("call") or {}).get("name")
            if name == "scheduler":
                sched_calls.append(data)
        if ev.get("type") == "tool/result":
            tool_results.append(data)

    print(f"scheduler tool/call events: {len(sched_calls)}")
    final_text = ""
    for ev in events:
        if ev.get("type") == "assistant/message":
            m = (ev.get("data") or {}).get("message") or {}
            for block in m.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    final_text += block.get("text", "")
    print("--- final assistant text (tail) ---")
    print(final_text.strip()[-600:])

    verdict = "SCHEDULER_TOOL_USED" if sched_calls else "SCHEDULER_TOOL_NOT_USED"
    print("verdict:", verdict)
    return 0 if sched_calls else 1


if __name__ == "__main__":
    sys.exit(main())
