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
from plan_executor import (PLANNER_PROMPT, aggregate, execute_plan,  # noqa: E402
                           extract_plan_json, verify_plan)

ROUTABLE = ["research-collab", "qa-gate", "daily-assistant", "standard"]
REGISTRY = Path(__file__).resolve().parent / "sched_sessions.json"


def _prompt_turn(text: str, preset: str, timeout_s: int, title: str) -> tuple:
    """通用单回合：开会话→提示→等 turn/end→取文本。返回 (answer, session_id, status)。"""
    backoffs = [30, 60, 120, 240, 480]
    quota = ("429", "rate limit", "rate_limit", "quota", "token_plan")
    try:
        sid = rpc("session.create", {"agentPreset": preset, "cwd": CWD})["sessionId"]
        try:
            rpc("session.rename", {"sessionId": sid, "title": title})
        except Exception:  # noqa: BLE001
            pass
        for attempt in range(len(backoffs) + 1):
            events_before = all_events(sid)
            before_turns = sum(1 for e in events_before if e.get("type") == "turn/end")
            before_user = max((e.get("seq", -1) for e in events_before
                               if e.get("type") == "user/message"), default=-1)
            rpc("session.prompt", {"sessionId": sid, "mode": "queue",
                                   "content": [{"type": "text", "text": text}]})
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
                return "", sid, "timeout"
            reason = ((turn_end.get("data") or {}).get("reason") or {})
            if reason.get("kind") == "error":
                msg = str((reason.get("error") or {}).get("message", ""))
                if any(m in msg.lower() for m in quota) and attempt < len(backoffs):
                    print(f"  [retry {attempt + 1}] quota 429，退避 {backoffs[attempt]}s",
                          flush=True)
                    time.sleep(backoffs[attempt])
                    continue
                return "", sid, f"turn-error: {msg[:120]}"
            texts = []
            for ev in all_events(sid):
                if ev.get("type") == "assistant/message" and ev.get("seq", 0) > user_seq:
                    m = (ev.get("data") or {}).get("message") or {}
                    for block in m.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text":
                            texts.append(block.get("text", ""))
            return "\n".join(texts), sid, "ok"
        return "", sid, "retries-exhausted"
    except Exception as e:  # noqa: BLE001
        return "", "", f"error: {e}"


def run_planner(need: str, timeout_s: int) -> tuple:
    """规划器：单调用产出子任务 DAG JSON。"""
    text = PLANNER_PROMPT.replace("{need}", need)
    return _prompt_turn(text, "minimal", timeout_s, "sched-plan")


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


def dispatch_single(need: str, preset: str, timeout_s: int,
                    model: dict | None = None) -> dict:
    rec = {"preset": preset, "answer": "", "steps": 0, "status": "ok",
           "sessionId": "", "retries": 0, "model": None}
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
        if model:  # P3 模型匹配：selectModel 生效已验证（verify_select_model.py）
            rpc("session.selectModel", {"sessionId": sid,
                                        "provider": model["provider"],
                                        "model": model["model"]})
            rec["model"] = model
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
    ap.add_argument("need", nargs="?", default=None, help="用户需求文本")
    ap.add_argument("--plan-only", action="store_true",
                    help="只出分类/拆分计划与预算预估，不执行投递")
    ap.add_argument("--resume", type=Path, default=None, metavar="STATE_JSON",
                    help="断点续跑：从 state.json 恢复，跳过 ok，重跑 pending/fail")
    ap.add_argument("--use-model-map", action="store_true",
                    help="P3：按 model_map.json 为 dispatched 会话 selectModel"
                         "（judge/planner 会话不适用——校准谱系绑定）")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", type=Path, default=Path("sched_out"))
    args = ap.parse_args()

    # --resume：从检查点恢复（跳过分类与规划，直接续跑未完成子任务）
    if args.resume is not None:
        state = json.loads(args.resume.read_text(encoding="utf-8"))
        if "plan" not in state or "subtasks" not in state:
            print("[resume] state.json 无 plan/subtasks，无法续跑")
            return 1
        out_dir = args.resume.parent
        state["state_path"] = str(args.resume.resolve())
        r_model_map = {}
        if state.get("model_map"):
            r_model_map = json.loads(
                (Path(__file__).resolve().parent / "model_map.json")
                .read_text(encoding="utf-8")).get("mapping", {})

        def r_dispatch(text: str, preset: str, timeout_s: int) -> dict:
            return dispatch_single(text, preset, timeout_s,
                                   model=r_model_map.get(preset))

        before = {k: v["status"] for k, v in state["subtasks"].items()}
        execute_plan(state, r_dispatch, args.timeout, out_dir)
        agg = aggregate(state, out_dir)
        args.resume.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        changed = {k: f"{before[k]}->{state['subtasks'][k]['status']}"
                   for k in before if before[k] != state["subtasks"][k]["status"]}
        print(f"[resume] 重跑结果: {changed or '无变化（其余均 ok/awaiting-user/skip）'}")
        print(f"汇总: {agg}")
        return 0
    if not args.need:
        ap.error("need 必填（或用 --resume）")

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
    summary_written = False

    # P3 模型匹配（opt-in）：只对 dispatched 工作会话生效；
    # classify/planner 会话不切换（校准谱系绑定 baidu/qianfan-code-latest）
    model_map = {}
    if args.use_model_map:
        map_file = Path(__file__).resolve().parent / "model_map.json"
        model_map = json.loads(map_file.read_text(encoding="utf-8")).get("mapping", {})
        state["model_map"] = True

    def dispatch_with_map(text: str, preset: str, timeout_s: int) -> dict:
        return dispatch_single(text, preset, timeout_s,
                               model=model_map.get(preset))

    if args.plan_only and label != "composite":
        state["decision"] = f"plan-only: 分类={label}，未执行"
    elif label in ROUTABLE:
        picked = model_map.get(label)
        print(f"[dispatch] → {label}"
              + (f"（model={picked['provider']}/{picked['model']}）" if picked else ""),
              flush=True)
        d = dispatch_with_map(args.need, label, args.timeout)
        state["dispatch"] = d
        state["decision"] = (f"routed:{label} status={d['status']}"
                             if d["status"] == "ok" else
                             f"routed:{label} FAIL: {d['status']}")
        if d["status"] == "ok":
            (args.out / f"transcript_{task_id}.md").write_text(
                f"# 调度结果 {task_id}\n\n- 需求: {args.need}\n- 路由: {label}\n"
                + (f"- 模型: {picked['provider']}/{picked['model']}\n" if picked else "")
                + f"- 会话: {d['sessionId']}\n\n## 回答\n\n{d['answer']}\n",
                encoding="utf-8")
    elif label == "composite":
        print("[planner] 拆分中（minimal 会话单调用）…", flush=True)
        raw, plan_sid, plan_status = run_planner(args.need, args.timeout)
        if plan_sid:
            register_session("planner", "minimal", plan_sid, args.need)
        state["planner"] = {"session": plan_sid, "status": plan_status}
        plan = extract_plan_json(raw) if plan_status == "ok" else None
        if plan is None:
            state["decision"] = (f"escalate: 规划器无有效输出（{plan_status}），"
                                 "不猜——请重新提交或手动拆分")
        else:
            errors, cleaned = verify_plan(plan)
            if errors:
                state["decision"] = "escalate: 拆分计划校验失败——" + "；".join(errors[:5])
                state["planner"]["raw"] = raw[:2000]
            else:
                state["plan"] = cleaned
                state["subtasks"] = {s["id"]: {"status": "pending", "answer": "",
                                                "sessionId": ""}
                                     for s in cleaned["subtasks"]}
                n = len(cleaned["subtasks"])
                if args.plan_only:
                    state["decision"] = (f"plan-only: 拆分为 {n} 个子任务，"
                                         f"预估调用 ≈ {n + 2}（分类+规划+子任务），未执行")
                else:
                    state["state_path"] = str((args.out / "state.json").resolve())
                    execute_plan(state, dispatch_with_map, args.timeout, args.out)
                    agg = aggregate(state, args.out)
                    summary_written = True
                    counts = {}
                    for s in state["subtasks"].values():
                        counts[s["status"]] = counts.get(s["status"], 0) + 1
                    state["decision"] = f"plan-executed: {counts}（汇总见 {agg.name}）"
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
    if not summary_written:  # composite 已执行时 aggregate() 已写过完整汇总
        (args.out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[done] {state['decision']}")
    print(f"汇总: {args.out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
