"""scheduler P3: selectModel 生效验证（P3 技术前提）。

三步证明模型切换真实生效：
  1. selectModel 后 session.models.current 变为目标模型
  2. 投递一个回合，turn 正常完成
  3. 该回合 request/header config 里的 provider/model = 目标模型（真实路由证据）

用法:
    python verify_select_model.py --preset standard --provider baidu \
        --model qianfan-code-latest [--task "用一句话说明什么是闭包。"]
产物：select_model_verify.json（落盘证据链）
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
    body = json.dumps({"type": "client-request", "rpcId": f"sm-{time.time_ns()}",
                       "method": method, "payload": payload}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/{method}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        envelope = json.loads(resp.read().decode("utf-8"))
    result = envelope["result"]
    if not result.get("ok"):
        raise RuntimeError(f"{method} failed: {result.get('error')}")
    return result["value"]


def all_events(session_id: str) -> list[dict]:
    events: dict[int, dict] = {}
    before = None
    for _ in range(50):
        payload: dict = {"sessionId": session_id, "maxMessages": 400}
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preset", default="standard")
    ap.add_argument("--provider", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--task", default="用一句话说明什么是闭包。")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "select_model_verify.json")
    args = ap.parse_args()

    evidence = {"preset": args.preset, "target": {"provider": args.provider,
                                                   "model": args.model}}
    sid = rpc("session.create", {"agentPreset": args.preset, "cwd": CWD})["sessionId"]
    evidence["session"] = sid
    try:
        rpc("session.rename", {"sessionId": sid, "title": "sched-selectmodel-verify"})
    except Exception:  # noqa: BLE001
        pass

    before = rpc("session.models", {"sessionId": sid})
    evidence["before"] = before.get("current")
    print(f"[1] 切换前 current = {before.get('current')}")

    sel = rpc("session.selectModel", {"sessionId": sid,
                                      "provider": args.provider, "model": args.model})
    evidence["select_response"] = sel
    after = rpc("session.models", {"sessionId": sid})
    evidence["after"] = after.get("current")
    print(f"[2] selectModel 响应 = {sel}")
    print(f"    切换后 current = {after.get('current')}")
    switched = (after.get("current") or {}).get("model") == args.model
    print(f"    current 已变为目标模型: {switched}")

    # 投递回合，取 request/header 真实路由
    rpc("session.prompt", {"sessionId": sid, "mode": "queue",
                           "content": [{"type": "text", "text": args.task}]})
    deadline = time.time() + 300
    header_cfg = None
    turn_ok = False
    answer = ""
    while time.time() < deadline:
        events = all_events(sid)
        for ev in events:
            if ev["type"] == "request/header" and header_cfg is None:
                header_cfg = ((ev.get("data") or {}).get("header") or {}).get("config") or {}
        if any(e["type"] == "turn/end" for e in events):
            turn_ok = True
            for ev in events:
                if ev.get("type") == "assistant/message":
                    m = (ev.get("data") or {}).get("message") or {}
                    for block in m.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text":
                            answer += block.get("text", "")
            break
        time.sleep(5)
    evidence["request_header_config"] = header_cfg
    evidence["turn_completed"] = turn_ok
    evidence["answer_head"] = answer[:200]
    used = {"provider": (header_cfg or {}).get("provider"),
            "model": (header_cfg or {}).get("model")}
    evidence["actually_used"] = used
    print(f"[3] 回合完成 = {turn_ok}")
    print(f"    request/header 实际使用 = {used}")
    real_match = (used.get("provider") == args.provider and used.get("model") == args.model)
    evidence["verdict"] = ("EFFECTIVE" if (switched and turn_ok and real_match)
                           else "NOT_EFFECTIVE")
    print(f"[verdict] {evidence['verdict']}")
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"-> {args.out}")
    return 0 if evidence["verdict"] == "EFFECTIVE" else 1


if __name__ == "__main__":
    sys.exit(main())
