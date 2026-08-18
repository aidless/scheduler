"""scheduler P2: 复合需求规划器 + DAG 执行器 + 汇总器。

设计依据 SCHEDULER_DESIGN.md §6-§7：
  - 规划器：单次 LLM 调用产出子任务 DAG（JSON），提示词冻结于 PLANNER_PROMPT
  - 校验器：确定性——preset 必须在群成员内、id 唯一、DAG 无环、
    保护层关键词强制 protection=true（不依赖 LLM 自觉）
  - 执行：拓扑层序；默认并行度 1（token plan RPM 硬限制，L102）；
    上游 ok 才投递下游；上游 fail/skip/awaiting-user → 下游 skip（显式披露）；
    上游答案注入下游提示（数据链路最小实现）
  - 保护层：protection=true 的子任务一律不自动执行 → awaiting-user
  - 检查点：每子任务完成即写 state.json；--resume 跳过 ok，重跑 pending/fail

用法（模块级）：被 dispatcher.py 调用；测试见 test_plan_executor.py（纯逻辑 stub）。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROUTABLE = ["research-collab", "qa-gate", "daily-assistant", "standard"]
PROTECTION_KEYWORDS = ("删除", "移除", "覆盖", "清空", "发布", "转账", "付款",
                       "购买", "权限", "提交到外部", "公开发布", "格式化")

PLANNER_PROMPT = """你是任务规划器。用户需求是复合需求（含多个领域的原子任务）。
请把它拆成子任务并输出严格 JSON，不要解释，不要调用任何工具。

可用处理者（preset 字段只能取这四者之一）:
- research-collab: 写论文/实验设计/统计/投稿
- qa-gate: 验证引用/judge 校准/评估契约/TMLR 自查/A/B 消融
- daily-assistant: 整理文件/抓网页/自动化脚本/批量转换/文档模板
- standard: 纯代码编写/重构/调试/运行脚本

输出格式（严格 JSON，不要包在代码块外框里）:
{"subtasks": [{"id": "s1", "text": "子任务需求文本（完整、可独立执行）", "preset": "处理者", "depends_on": []}]}

拆分规则:
1. 每个子任务是单一领域的原子任务；text 保留原意，不扩大范围，不加用户没提的要求。
2. 子任务 B 需要 A 的产物才能执行时，把 A 的 id 放进 B 的 depends_on；独立任务留空。
3. 子任务涉及删除/覆盖/发布/转账/购买/权限等不可逆操作时，text 必须保留这些操作的原话。
4. 子任务数量应与需求中原子任务数量一致，不过度拆分。

需求: {need}
输出: """


def extract_plan_json(text: str) -> dict | None:
    """从回答里提取含 subtasks 的 JSON 对象（L104：多候选解析，不取首个花括号）。"""
    candidates = re.findall(r"\{.*\}", text, flags=re.DOTALL)
    for cand in sorted(candidates, key=len):
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("subtasks"), list):
            return obj
    return None


def verify_plan(plan: dict) -> tuple[list[str], dict]:
    """确定性校验；返回 (errors, cleaned_plan)。protection 由关键词强制标记。"""
    errors: list[str] = []
    subs = plan.get("subtasks")
    if not isinstance(subs, list) or not subs:
        return ["subtasks 缺失或为空"], {}
    ids = [s.get("id") for s in subs]
    if any(i is None for i in ids):
        errors.append("存在无 id 的子任务")
    if len(set(ids)) != len(ids):
        errors.append(f"子任务 id 重复: {ids}")
    cleaned = []
    for s in subs:
        if not isinstance(s, dict):
            errors.append("子任务不是对象")
            continue
        text = str(s.get("text") or "").strip()
        preset = str(s.get("preset") or "").strip()
        if not text:
            errors.append(f"{s.get('id')}: text 为空")
        if preset not in ROUTABLE:
            errors.append(f"{s.get('id')}: preset 非法: {preset!r}（必须 ∈ {ROUTABLE}）")
        deps = s.get("depends_on") or []
        if not isinstance(deps, list):
            errors.append(f"{s.get('id')}: depends_on 非列表")
            deps = []
        protection = any(k in text for k in PROTECTION_KEYWORDS)
        cleaned.append({"id": s.get("id"), "text": text, "preset": preset,
                        "depends_on": [str(d) for d in deps],
                        "protection": protection})
    idset = {c["id"] for c in cleaned}
    for c in cleaned:
        for d in c["depends_on"]:
            if d not in idset:
                errors.append(f"{c['id']}: depends_on 引用不存在的 {d}")
            if d == c["id"]:
                errors.append(f"{c['id']}: 自依赖")
    if errors:
        return errors, {}
    # 环检测（Kahn）
    levels, err = topo_levels(cleaned)
    if err:
        return [err], {}
    return [], {"subtasks": cleaned}


def topo_levels(subs: list[dict]) -> tuple[list[list[str]], str]:
    """Kahn 分层拓扑序；返回 (levels, error)。"""
    indeg = {s["id"]: 0 for s in subs}
    down: dict[str, list[str]] = {s["id"]: [] for s in subs}
    for s in subs:
        for d in s["depends_on"]:
            if d in indeg and s["id"] in indeg:
                indeg[s["id"]] += 1
                down[d].append(s["id"])
    levels = []
    frontier = sorted([i for i, d in indeg.items() if d == 0])
    seen = 0
    while frontier:
        levels.append(frontier)
        seen += len(frontier)
        nxt = []
        for i in frontier:
            for j in down[i]:
                indeg[j] -= 1
                if indeg[j] == 0:
                    nxt.append(j)
        frontier = sorted(nxt)
    if seen != len(subs):
        return [], "DAG 存在环（拓扑序覆盖不全）"
    return levels, ""


def upstream_context(subs_state: dict, sub: dict, max_chars: int = 2000) -> str:
    """注入已 ok 的上游答案（数据链路最小实现）。"""
    parts = []
    for d in sub["depends_on"]:
        up = subs_state.get(d)
        if up and up.get("status") == "ok" and up.get("answer"):
            parts.append(f"[上游 {d} 的结果]\n{up['answer'][:max_chars]}")
    return "\n\n".join(parts)


def execute_plan(state: dict, dispatch_fn, timeout_s: int = 600,
                 out: Path | None = None) -> dict:
    """按拓扑层序执行子任务；dispatch_fn(text, preset, timeout) -> rec。

    dispatch_fn 可注入（测试用 stub）；生产为 dispatcher.dispatch_single。
    每子任务完成后写检查点（state_path 存在时）。
    """
    state_path = Path(state["state_path"]) if state.get("state_path") else None
    subs_state = state["subtasks"]
    meta = {s["id"]: s for s in state["plan"]["subtasks"]}
    levels, err = topo_levels(state["plan"]["subtasks"])
    if err:
        state["status"] = f"plan-invalid: {err}"
        return state
    for level in levels:
        for sid in level:
            meta_s = meta[sid]
            rec_s = subs_state[sid]
            if rec_s["status"] in ("ok", "awaiting-user", "skip"):
                continue
            up_states = [subs_state[d]["status"] for d in meta_s["depends_on"]]
            if any(u != "ok" for u in up_states):
                rec_s["status"] = "skip"
                rec_s["skip_reason"] = ("上游未全部 ok: "
                                        + ", ".join(f"{d}={subs_state[d]['status']}"
                                                    for d in meta_s["depends_on"]))
            elif meta_s["protection"]:
                rec_s["status"] = "awaiting-user"
                rec_s["skip_reason"] = ("保护层：含不可逆操作（"
                                        + "/".join(k for k in PROTECTION_KEYWORDS
                                                   if k in meta_s["text"])
                                        + "），需用户裁决后手动执行")
            else:
                ctx = upstream_context(subs_state, meta_s)
                prompt = (f"{ctx}\n\n[当前子任务]\n{meta_s['text']}"
                          if ctx else meta_s["text"])
                d = dispatch_fn(prompt, meta_s["preset"], timeout_s)
                rec_s.update({"status": "ok" if d["status"] == "ok" else "fail",
                              "answer": d.get("answer", ""),
                              "sessionId": d.get("sessionId", ""),
                              "dispatch_status": d["status"]})
            if state_path:
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    state["status"] = "done"
    return state


def aggregate(state: dict, out: Path) -> Path:
    """确定性组装汇总（非 LLM 自由发挥）；失败与待确认显式列出。"""
    out.mkdir(parents=True, exist_ok=True)
    subs_state = state["subtasks"]
    meta = {s["id"]: s for s in state["plan"]["subtasks"]}
    awaiting = [i for i, s in subs_state.items() if s["status"] == "awaiting-user"]
    failed = [i for i, s in subs_state.items() if s["status"] == "fail"]
    skipped = [i for i, s in subs_state.items() if s["status"] == "skip"]
    lines = [f"# 复合需求调度汇总 {state.get('task_id', '')}", "",
             f"- 需求: {state.get('need', '')}",
             f"- 子任务: {len(subs_state)}（ok={sum(1 for s in subs_state.values() if s['status'] == 'ok')}"
             f" / fail={len(failed)} / awaiting-user={len(awaiting)} / skip={len(skipped)}）",
             ""]
    if awaiting:
        lines += ["## ⚠ 待用户确认（保护层，未自动执行）", ""]
        for i in awaiting:
            lines.append(f"- {i}: {meta[i]['text']}")
            lines.append(f"  原因: {subs_state[i].get('skip_reason', '')}")
        lines.append("")
    lines += ["## 子任务明细", "",
              "| id | preset | 状态 | 依赖 | 会话 |",
              "| --- | --- | --- | --- | --- |"]
    for i, s in subs_state.items():
        deps = ",".join(meta[i]["depends_on"]) or "-"
        lines.append(f"| {i} | {meta[i]['preset']} | {s['status']} | {deps} "
                     f"| {s.get('sessionId', '-')} |")
    lines.append("")
    for i, s in subs_state.items():
        if s["status"] == "ok":
            lines += [f"## {i} 结果（{meta[i]['preset']}）", "",
                      s.get("answer", "")[:4000], ""]
    if failed or skipped:
        lines += ["## 失败与跳过（显式披露，不静默）", ""]
        for i in failed:
            lines.append(f"- {i} FAIL: {subs_state[i].get('dispatch_status', '')}")
        for i in skipped:
            lines.append(f"- {i} SKIP: {subs_state[i].get('skip_reason', '')}")
        lines.append("")
    lines += ["## 主张边界", "",
              "- 拆分由 planner 单次调用产出，经确定性校验器（preset/环/保护层关键词）；",
              "- 保护层子任务未自动执行；汇总为确定性组装，无 LLM 二次总结。"]
    p = out / "summary.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
