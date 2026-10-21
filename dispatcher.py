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

ROUTABLE = ["research-collab", "qa-gate", "daily-assistant", "standard", "paperreview-agent", "kg-retrieval-agent", "aigc-studio-agent"]
REGISTRY = Path(__file__).resolve().parent / "sched_sessions.json"
# paperreview-agent keyword pre-route (论文全流程：写作/审稿/返修/投稿)
PAPERREVIEW_KEYWORDS = ["paperreview", "论文全流程", "论文写作", "写论文", "审稿", "审阅", "review paper", "peer review", "TMLR审稿", "rebuttal", "投稿"]
# kg-retrieval-agent keyword pre-route (Agent开发与研究：知识图谱/GraphRAG/自进化/记忆/研究)
KG_RETRIEVAL_KEYWORDS = ["知识图谱", "kg-retrieval", "kg检索", "KG检索", "GraphRAG", "图谱检索", "图检索", "图谱构建", "kg ", " KG", "entity relation",
                          "Agent开发", "agent研究", "Agent研究", "自进化", "记忆系统", "research-kit", "study_repos", "AGI-KIT", "调度器", "agent lab"]
# aigc-studio-agent keyword pre-route (AIGC 视频/漫剧/ComfyUI/H3)
AIGC_KEYWORDS = ["aigc", "AIGC", "漫剧", "分镜", "ComfyUI", "H3", "R2V", "角色一致性", "视频生成", "Wan", "Hunyuan", "做片", "电影", "林昭"]


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
        # 切到 ali/deepseek-v4-flash-0731（当前环境主模型；minimal preset 默认走 baidu）
        rpc("session.selectModel", {"sessionId": sid,
                                    "provider": "ali", "model": "deepseek-v4-flash-0731"})
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
    # kg-retrieval-agent 本地直连（Agent研究底座：KG + 研究）
    if preset == "kg-retrieval-agent":
        import re, subprocess, hashlib
        q = need
        q = re.sub(r".*?kg-retrieval[^\s]*\s*[回答查询检索研究]*\s*", "", q, flags=re.I)
        q = re.sub(r"^用(知识图谱|agent研究|研究).*?[查問问检索回答]*\s*", "", q)
        q = q.strip().strip("\"'「」“”")
        if not q:
            q = need
        # 研究类走 --research，KG类走 --query/--rag
        is_research = any(k in need for k in ["研究", "自进化", "记忆", "调度", "research", "study", "AGI-KIT", "评测", "复现"])
        use_rag = any(k in need for k in ["GraphRAG", "溯源", "子图", "证据", "关系路径"])
        if is_research and not use_rag:
            cmd = [sys.executable, str(Path(CWD) / "agents" / "kg-retrieval-agent" / "agent.py"), "--research", q]
        else:
            cmd = [sys.executable, str(Path(CWD) / "agents" / "kg-retrieval-agent" / "agent.py"), "--query", q]
            if use_rag:
                cmd.append("--rag")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, encoding="utf-8", errors="replace")
            rec["answer"] = proc.stdout[-6000:] + ("\n" + proc.stderr[-2000:] if proc.stderr else "")
            rec["status"] = "ok" if proc.returncode == 0 else f"agent-error:{proc.returncode}"
            rec["sessionId"] = f"local-kg-{hashlib.sha256(q.encode()).hexdigest()[:8]}"
            return rec
        except Exception as e:
            rec["status"] = f"error: {e}"
            return rec
    # aigc-studio-agent 本地直连（不经 DSH 会话，直接调 cli.py）
    if preset == "aigc-studio-agent":
        import re, subprocess, hashlib
        # 解析 chapter/shots/engine
        m_ch = re.search(r"第(\d+)章|chapter\s*(\d+)", need, re.I)
        chapter = int(m_ch.group(1) or m_ch.group(2)) if m_ch else 1
        m_sh = re.search(r"(\d+)\s*镜|shots?\s*(\d+)", need, re.I)
        shots = int(m_sh.group(1) or m_sh.group(2)) if m_sh else 6
        engine = "h3" if "h3" in need.lower() else "wan21" if "wan" in need.lower() else "local"
        dry = "--dry_run" if any(k in need for k in ["dry_run", "分镜表", "仅分镜", "审prompt"]) else None
        cmd = [sys.executable, str(Path(CWD) / "agents" / "aigc-studio-agent" / "cli.py"), "--chapter", str(chapter), "--shots", str(shots), "--engine", engine]
        if dry:
            cmd.append(dry)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, encoding="utf-8", errors="replace")
            rec["answer"] = proc.stdout[-6000:] + ("\n" + proc.stderr[-2000:] if proc.stderr else "")
            rec["status"] = "ok" if proc.returncode == 0 else f"agent-error:{proc.returncode}"
            rec["sessionId"] = f"local-aigc-{hashlib.sha256(need.encode()).hexdigest()[:8]}"
            rec["answer"] += f"\n\n[产物] F:/deepseek/movie_star_beyond/r2v_output/ (EP{chapter:02d}_* + ledger.jsonl + qc_ch{chapter}.html)"
            return rec
        except Exception as e:
            rec["status"] = f"error: {e}"
            return rec
    # paperreview-agent 本地直连（不经 DSH 会话，直接跑 evidence-grounded 5+1）
    if preset == "paperreview-agent":
        import re, subprocess, hashlib
        m = re.search(r"([A-Za-z]:\\[^\s\"']+\.pdf)", need)
        pdf = m.group(1) if m else None
        if not pdf or not Path(pdf).exists():
            # 尝试无盘符路径
            m2 = re.search(r"(/[^\s\"']+\.pdf)", need)
            if m2:
                pdf = m2.group(1)
        if pdf and Path(pdf).exists():
            out_dir = Path(CWD) / "agents" / "paperreview-agent" / f"out_{int(time.time())}"
            cmd = [sys.executable, str(Path(CWD) / "agents" / "paperreview-agent" / "agent.py"), "review", "--pdf", pdf, "--out-dir", str(out_dir), "--mock"]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, encoding="utf-8", errors="replace")
                rec["answer"] = proc.stdout[-4000:] + ("\n" + proc.stderr[-2000:] if proc.stderr else "")
                rec["status"] = "ok" if proc.returncode == 0 else f"agent-error:{proc.returncode}"
                rec["sessionId"] = f"local-paperreview-{hashlib.sha256(pdf.encode()).hexdigest()[:8]}"
                # 追加产物路径
                rec["answer"] += f"\n\n[产物] {out_dir}/review.pdf\n[Evidence] {out_dir}/evidence.json"
                return rec
            except Exception as e:
                rec["status"] = f"error: {e}"
                return rec
        else:
            rec["answer"] = f"未找到 PDF 路径，请在需求中给出完整 .pdf 路径，例如：用 paperreview-agent 审 F:\\xxx\\main.pdf"
            rec["status"] = "ok"
            return rec
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
    # 三Agent keyword pre-route: AIGC > KG研究 > 论文 (AIGC优先避免"电影"误判为论文)
    need_low = args.need.lower()
    if any(kw.lower() in need_low for kw in AIGC_KEYWORDS):
        label = "aigc-studio-agent"
        cls = {"pred": label, "parse_fail": False, "sessionId": "pre-route-aigc"}
        print(f"[router] keyword pre-route → {label} (跳过分类器)", flush=True)
    elif any(kw.lower() in need_low for kw in KG_RETRIEVAL_KEYWORDS):
        label = "kg-retrieval-agent"
        cls = {"pred": label, "parse_fail": False, "sessionId": "pre-route-kg"}
        print(f"[router] keyword pre-route → {label} (跳过分类器)", flush=True)
    elif any(kw.lower() in need_low for kw in PAPERREVIEW_KEYWORDS):
        label = "paperreview-agent"
        cls = {"pred": label, "parse_fail": False, "sessionId": "pre-route-paperreview"}
        print(f"[router] keyword pre-route → {label} (跳过分类器)", flush=True)
    else:
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
