"""scheduler P3: 编码模型映射 A/B（预注册 model-map-v1）。

A=baidu/qianfan-code-latest（映射）vs B=china/Qwen3.8-Max（默认），
均在 standard preset 会话；判分=代码块提取→测试断言运行→pass/fail（确定性）。
配对单位=同任务双臂；exact McNemar；决定规则见 model_map.json（预注册）。

用法: python coding_model_ab.py [--out ab_results] [--timeout 300] [--pace 5]
产物: coding_ab_results.json、ab_work/<task>_<arm>.py（被测代码+断言留档）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:3080/api"
CWD = r"F:\deepseek"
ARMS = {
    "A": {"provider": "baidu", "model": "qianfan-code-latest"},
    "B": None,  # 默认模型（china/Qwen3.8-Max），不切换
}
BACKOFFS = [30, 60, 120, 240, 480]
QUOTA_MARKERS = ("429", "rate limit", "rate_limit", "quota", "token_plan")
CODE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def rpc(method: str, payload: dict) -> dict:
    body = json.dumps({"type": "client-request", "rpcId": f"ab-{time.time_ns()}",
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


def run_arm(task: dict, arm: str, framing: str, timeout_s: int, work: Path) -> dict:
    rec = {"task_id": task["id"], "arm": arm, "pass": None, "status": "ok",
           "extracted": False, "sessionId": "", "retries": 0}
    try:
        sid = rpc("session.create", {"agentPreset": "standard", "cwd": CWD})["sessionId"]
        rec["sessionId"] = sid
        try:
            rpc("session.rename", {"sessionId": sid,
                                   "title": f"sched-ab {arm} {task['id']}"})
        except Exception:  # noqa: BLE001
            pass
        target = ARMS[arm]
        if target:
            rpc("session.selectModel", {"sessionId": sid,
                                        "provider": target["provider"],
                                        "model": target["model"]})
        for attempt in range(len(BACKOFFS) + 1):
            events_before = all_events(sid)
            before_turns = sum(1 for e in events_before if e.get("type") == "turn/end")
            before_user = max((e.get("seq", -1) for e in events_before
                               if e.get("type") == "user/message"), default=-1)
            rpc("session.prompt", {"sessionId": sid, "mode": "queue",
                                   "content": [{"type": "text",
                                                "text": framing + "\n\n" + task["prompt"]}]})
            user_seq = before_user
            u_deadline = time.time() + 60
            while time.time() < u_deadline:
                user_seq = max((e.get("seq", -1) for e in all_events(sid)
                                if e.get("type") == "user/message"), default=before_user)
                if user_seq > before_user:
                    break
                time.sleep(2)
            deadline = time.time() + timeout_s
            turn_end = None
            while time.time() < deadline:
                events = all_events(sid)
                ends = [e for e in events if e.get("type") == "turn/end"]
                if len(ends) >= before_turns + 1:
                    turn_end = ends[-1]
                    break
                time.sleep(5)
            if turn_end is None:
                rec["status"] = "timeout"
                break
            reason = ((turn_end.get("data") or {}).get("reason") or {})
            if reason.get("kind") == "error":
                msg = str((reason.get("error") or {}).get("message", ""))
                if any(m in msg.lower() for m in QUOTA_MARKERS) and attempt < len(BACKOFFS):
                    rec["retries"] += 1
                    time.sleep(BACKOFFS[attempt])
                    continue
                rec["status"] = f"turn-error: {msg[:120]}"
                break
            texts = []
            for ev in all_events(sid):
                if ev.get("type") == "assistant/message" and ev.get("seq", 0) > user_seq:
                    m = (ev.get("data") or {}).get("message") or {}
                    for block in m.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text":
                            texts.append(block.get("text", ""))
            answer = "\n".join(texts)
            mt = CODE_RE.search(answer)
            code = mt.group(1) if mt else None
            if code is None:
                rec["status"] = "extraction-failed"
                rec["pass"] = 0  # 错误计入分母
                return rec
            rec["extracted"] = True
            # 测试运行（确定性判分）
            work.mkdir(parents=True, exist_ok=True)
            tf = work / f"{task['id']}_{arm}.py"
            tf.write_text(code + "\n\n" + "\n".join(task["tests"])
                          + "\nprint('TESTS_OK')\n", encoding="utf-8")
            try:
                proc = subprocess.run([sys.executable, str(tf)],
                                      capture_output=True, text=True, timeout=30)
                rec["pass"] = 1 if (proc.returncode == 0
                                    and "TESTS_OK" in proc.stdout) else 0
                if rec["pass"] == 0:
                    rec["status"] = "tests-failed"
                    rec["test_stderr"] = proc.stderr[-300:]
            except subprocess.TimeoutExpired:
                rec["pass"] = 0
                rec["status"] = "test-timeout"
            return rec
        # timeout/turn-error 兜底：错误计入分母
        rec["pass"] = 0
    except Exception as e:  # noqa: BLE001
        rec["status"] = f"error: {e}"
        rec["pass"] = 0
    return rec


def exact_mcnemar_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2.0 * sum(comb(n, i) for i in range(k + 1)) / (2 ** n))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "coding_ab_results.json")
    ap.add_argument("--tasks", type=Path, default=HERE / "coding_ab_tasks.json",
                    help="任务集 JSON（fleet-r4 用 coding_r4_tasks.json）")
    ap.add_argument("--work", type=Path, default=None,
                    help="被测代码留档目录（缺省 ab_work）")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--pace", type=float, default=5.0)
    args = ap.parse_args()

    spec = json.loads(args.tasks.read_text(encoding="utf-8"))
    tasks, framing = spec["tasks"], spec["framing"]
    work = args.work if args.work is not None else HERE / "ab_work"
    results = []
    total = len(tasks) * 2
    for i, task in enumerate(tasks):
        order = ["A", "B"] if i % 2 == 0 else ["B", "A"]
        for arm in order:
            print(f"[ab {len(results) + 1}/{total}] {task['id']} arm={arm}", flush=True)
            rec = run_arm(task, arm, framing, args.timeout, work)
            results.append(rec)
            print(f"  -> pass={rec['pass']} status={rec['status']} "
                  f"retries={rec['retries']}", flush=True)
            args.out.write_text(json.dumps({"results": results},
                                           ensure_ascii=False, indent=2),
                                encoding="utf-8")
            time.sleep(args.pace)

    by_task = {}
    for r in results:
        by_task.setdefault(r["task_id"], {})[r["arm"]] = r["pass"]
    b = sum(1 for t in by_task.values() if t.get("A") == 1 and t.get("B") == 0)
    c = sum(1 for t in by_task.values() if t.get("A") == 0 and t.get("B") == 1)
    ties_win = sum(1 for t in by_task.values() if t.get("A") == 1 and t.get("B") == 1)
    ties_lose = sum(1 for t in by_task.values() if t.get("A") == 0 and t.get("B") == 0)
    p = exact_mcnemar_p(b, c)
    acc_a = sum(1 for r in results if r["arm"] == "A" and r["pass"] == 1) / len(tasks)
    acc_b = sum(1 for r in results if r["arm"] == "B" and r["pass"] == 1) / len(tasks)
    if p < 0.05 and b > c:
        decision = "promote_mapping"
    elif p < 0.05 and c > b:
        decision = "rollback_mapping"
    else:
        decision = "keep_with_disclosure"
    summary = {"n_tasks": len(tasks), "acc_A_mapped": acc_a, "acc_B_default": acc_b,
               "b_Awin": b, "c_Bwin": c, "ties_win": ties_win, "ties_lose": ties_lose,
               "p_exact": p, "decision": decision,
               "note": "预注册 model-map-v1 决定规则；n=6 功效有限（见 power_declaration）"}
    final = {"plan_id": "model-map-v1", "summary": summary, "results": results}
    args.out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] acc A={acc_a:.3f} B={acc_b:.3f} | b={b} c={c} p={p:.4f} "
          f"-> {decision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
