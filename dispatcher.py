"""scheduler: Agent 群调度器 MVP（P1，设计见 agent-群架构/SCHEDULER_DESIGN.md）。

流程: 用户需求 → 分类（calibrated classify-judge）→
  单一领域 → 投递对应 preset 会话 → 取回结果 → 汇总报告
  composite → 升级报告（拆分能力属 P2，P1 不执行，只声明）
  clarify / 解析失败 → 升级用户（不猜，路由表纪律"拿不准归属：问用户一句"）
串行执行；429 退避 / turn 错误检测沿用 fleet 机制。
会话登记 sched_sessions.json（git 追踪，默认绝不自动删，清理须用户裁决）。
保护层：P1 依赖目标 preset 自身 persona 的保护层纪律（不可逆操作由目标 agent 重述确认）。

用法:
    python dispatcher.py "<需求>" [--plan-only] [--timeout 600] [--out sched_out]
产物（<out>/）：state.json、summary.md、transcript_<task_id>.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_run import (BASE, CWD, LABELS, PROMPT_VERSION,  # noqa: E402
                          all_events, classify_one, rpc)

ROUTABLE = ["research-collab", "qa-gate", "daily-assistant", "standard"]
REGISTRY = Path(__file__).resolve().parent / "sched_sessions.json"


def register_session(purpose: str, preset: str, session_id: str, need: str) -> None:
    entries = []
    if REGISTRY.exists():
        entries = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "purpose": purpose, "preset": preset,
        "sessionId": session_id, "need": need[:200],
        "policy": "no-auto-delete（清理须用户裁决）",
    })
    REGISTRY.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def dispatch_single(need: str, preset: str, timeout_s: int) -> dict:
    rec = {"preset": preset, "answer": "", "steps": 0, "status": "ok",
           "sessionId": "", "retries": 0}
    backoffs = [30, 60, 120, 240, 480]
    quota = ("429", "rate limit", "rate_limit", "quota", "token_plan")
    try:
        sid = rpc("session.create", {"agentPreset": preset, "cwd": CWD})["sessionId"]
        rec["sessionId"] = sid
        try:
            rpc("session.rename", {"sessionId": sid,
                                   "title": f"sched {preset[:6]} {need[:24]}"})
        except Exception:  # noqa: BLE001
            pass
        register_session("dispatch", preset, sid, need)
        for attempt in range(len(backoffs) + 1):
            events_before = all_events(sid)
            before_turns = sum(1 for e in events_before if e.get("type") == "turn/end")
            before_user = max((e.get("seq", -1) for e in events_before
                               if e.get("type") == "user/message"), default=-1)
            rpc("session.prompt", {"sessionId": sid, "mode": "queue",
                                   "content": [{"type": "text", "text": need}]})
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
                return rec
            reason = ((turn_end.get("data") or {}).get("reason") or {})
            if reason.get("kind") == "error":
                msg = str((reason.get("error") or {}).get("message", ""))
                if any(m in msg.lower() for m in quota) and attempt < len(backoffs):
                    rec["retries"] += 1
                    print(f"  [retry {rec['retries']}] quota 429，退避 {backoffs[attempt]}s",
                          flush=True)
                    time.sleep(backoffs[attempt])
                    continue
                rec["status"] = f"turn-error: {msg[:120]}"
                return rec
            texts = []
            for ev in all_events(sid):
                if ev.get("type") == "assistant/message" and ev.get("seq", 0) > user_seq:
                    m = (ev.get("data") or {}).get("message") or {}
                    for block in m.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text":
                            texts.append(block.get("text", ""))
            rec["answer"] = "\n".join(texts)
            rec["steps"] = sum(1 for e in all_events(sid)
                               if e.get("type") == "assistant/message"
                               and e.get("seq", 0) > user_seq)
            return rec
        rec["status"] = "retries-exhausted"
    except Exception as e:  # noqa: BLE001
        rec["status"] = f"error: {e}"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("need", help="用户需求文本")
    ap.add_argument("--plan-only", action="store_true",
                    help="只分类出计划，不执行投递（成本预估）")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", type=Path, default=Path("sched_out"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    task_id = f"t{int(time.time())}"
    print(f"[router] 分类中（classify-judge {PROMPT_VERSION}）…", flush=True)
    cls = classify_one({"sample_id": task_id, "need": args.need, "gold": None},
                       preset="minimal", timeout_s=args.timeout, tag="sched-route")
    register_session("classify", "minimal", cls["sessionId"], args.need)
    label = cls["pred"]
    print(f"[router] pred={label} parse_fail={cls['parse_fail']}", flush=True)

    state = {
        "task_id": task_id, "need": args.need,
        "classify": {"pred": label, "parse_fail": cls["parse_fail"],
                     "prompt_version": PROMPT_VERSION,
                     "classify_session": cls["sessionId"]},
        "plan_only": args.plan_only,
        "dispatch": None, "decision": None,
    }

    if args.plan_only:
        state["decision"] = f"plan-only: 分类={label}，未执行"
    elif label in ROUTABLE:
        print(f"[dispatch] → {label}", flush=True)
        d = dispatch_single(args.need, label, args.timeout)
        state["dispatch"] = d
        state["decision"] = (f"routed:{label} status={d['status']}"
                             if d["status"] == "ok" else
                             f"routed:{label} FAIL: {d['status']}")
        if d["status"] == "ok":
            (args.out / f"transcript_{task_id}.md").write_text(
                f"# 调度结果 {task_id}\n\n- 需求: {args.need}\n- 路由: {label}\n"
                f"- 会话: {d['sessionId']}\n\n## 回答\n\n{d['answer']}\n",
                encoding="utf-8")
    elif label == "composite":
        state["decision"] = ("escalate: composite——需求含多领域子任务，"
                             "拆分/并行/汇总为 P2 能力，P1 不执行；请拆分后分别提交或等 P2")
    elif label == "clarify":
        state["decision"] = ("escalate: clarify——需求信息不足或指代不明，"
                             "请补充：对象是哪个？要做什么？标准是什么？（路由表纪律：不猜）")
    else:
        state["decision"] = ("escalate: 分类失败/低置信——解析不出唯一类别，"
                             "请用户直接指定 preset 或改写需求（不猜）")

    (args.out / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 调度汇总 {task_id}", "",
             f"- 需求: {args.need}",
             f"- 分类: {label}（classify-judge {PROMPT_VERSION}）",
             f"- 决定: {state['decision']}", ""]
    if state.get("dispatch") and state["dispatch"].get("status") == "ok":
        lines += ["## 执行结果", "",
                  f"- preset: {state['dispatch']['preset']}",
                  f"- 会话: {state['dispatch']['sessionId']}",
                  f"- 转录: transcript_{task_id}.md", "",
                  state["dispatch"]["answer"][:2000], ""]
    lines += ["## 主张边界", "",
              "- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；",
              "  分类歧义/失败一律升级用户，不猜。",
              "- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。"]
    (args.out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[done] {state['decision']}")
    print(f"汇总: {args.out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
