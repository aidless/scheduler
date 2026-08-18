"""scheduler: 分类版 judge 校准执行器（构造即真值 gold，无人工）。

对 gold_classify_v1.json 逐条开真实会话跑分类 judge，解析六选一标签 →
输出 verdicts + 升级检测视图 pairs CSV（positive={composite,clarify}）
供 human_gold_consistency.py / check_judge_calibration.py 判门。
纪律：解析失败（0 个或多个标签）= 错误，计入分母（升级视图按反值记，透明标注）。

用法:
    python classify_run.py --gold gold_classify_v1.json --out calib_classify_v1
                           [--preset minimal] [--tag cls-calib] [--timeout 300] [--pace 5]
产物（<out>/）：judge_verdicts.json、pairs_escalation.csv、stats.json、
               classify_prompt.md（版本冻结留档）
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
PROMPT_VERSION = "v1-classify"
LABELS = ["research-collab", "qa-gate", "daily-assistant", "standard",
          "composite", "clarify"]
ESCALATION = {"composite", "clarify"}

CLASSIFY_PROMPT = """你是需求分类器。对给定需求输出且仅输出一个类别名，不要解释，不要调用任何工具。

类别（六选一，必须用原文形式输出）:
- research-collab: 写论文/实验设计/统计/投稿类单一科研任务
- qa-gate: 验证引用/judge 校准/评估契约/TMLR 自查/A/B 消融类单一验证任务
- daily-assistant: 整理文件/抓网页/自动化脚本/批量转换类单一日常任务
- standard: 纯代码编写/重构/调试类单一编码任务
- composite: 需求包含两个及以上不同领域的原子任务（需要拆分执行）
- clarify: 需求信息不足或指代不明（无法判断归属，应请求澄清）

判定规则:
1. 单一领域需求 → 输出对应处理者类别。
2. 含多个不同领域子任务（"先…再…"/"并且"等连接）→ composite。
3. 模糊指代（那个/这个/上次 + 缺上下文）或对象/标准不明确 → clarify。

示例:
需求: 给论文的讨论部分补一段局限性分析。
输出: research-collab
需求: 核查这份交付物的证据清单有没有漏项。
输出: qa-gate
需求: 把这批发票扫描件按月份归档。
输出: daily-assistant
需求: 给这个函数补上类型注解。
输出: standard
需求: 先修掉登录页的报错，再把会议纪要整理成文档。
输出: composite
需求: 帮我把那天那个发出去。
输出: clarify

需求: {need}
输出: """

BACKOFFS = [30, 60, 120, 240, 480]
QUOTA_MARKERS = ("429", "rate limit", "rate_limit", "quota", "token_plan")


def rpc(method: str, payload: dict) -> dict:
    body = json.dumps({"type": "client-request", "rpcId": f"cl-{time.time_ns()}",
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


def parse_label(text: str) -> str | None:
    found = [l for l in LABELS if l in text.lower()]
    return found[0] if len(found) == 1 else None


def classify_one(item: dict, preset: str, timeout_s: int, tag: str) -> dict:
    rec = {"sample_id": item["sample_id"], "gold": item["gold"],
           "pred": None, "raw": "", "parse_fail": False,
           "status": "ok", "retries": 0, "sessionId": ""}
    text = CLASSIFY_PROMPT.replace("{need}", item["need"])
    try:
        sid = rpc("session.create", {"agentPreset": preset, "cwd": CWD})["sessionId"]
        rec["sessionId"] = sid
        try:
            rpc("session.rename", {"sessionId": sid,
                                   "title": f"{tag} {item['sample_id']}"})
        except Exception:  # noqa: BLE001
            pass
        for attempt in range(len(BACKOFFS) + 1):
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
                rec["status"] = "timeout"
                break
            reason = ((turn_end.get("data") or {}).get("reason") or {})
            if reason.get("kind") == "error":
                msg = str((reason.get("error") or {}).get("message", ""))
                if any(m in msg.lower() for m in QUOTA_MARKERS) and attempt < len(BACKOFFS):
                    rec["retries"] += 1
                    print(f"  [retry {rec['retries']}] quota 429，退避 {BACKOFFS[attempt]}s",
                          flush=True)
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
            rec["raw"] = "\n".join(texts)
            rec["pred"] = parse_label(rec["raw"])
            rec["parse_fail"] = rec["pred"] is None
            return rec
    except Exception as e:  # noqa: BLE001
        rec["status"] = f"error: {e}"
    if rec["pred"] is None:
        rec["parse_fail"] = True
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--preset", default="minimal")
    ap.add_argument("--tag", default="cls-calib")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--pace", type=float, default=5.0)
    args = ap.parse_args()

    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    items = gold["items"]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "classify_prompt.md").write_text(
        f"# classify prompt 冻结留档（prompt_version={PROMPT_VERSION}）\n\n"
        + CLASSIFY_PROMPT, encoding="utf-8")

    verdicts = []
    for i, item in enumerate(items):
        print(f"[classify {i + 1}/{len(items)}] {item['sample_id']} "
              f"(gold={item['gold']})", flush=True)
        rec = classify_one(item, args.preset, args.timeout, args.tag)
        verdicts.append(rec)
        print(f"  -> pred={rec['pred']} parse_fail={rec['parse_fail']} "
              f"status={rec['status']}", flush=True)
        (args.out / "judge_verdicts.json").write_text(
            json.dumps({"prompt_version": PROMPT_VERSION, "verdicts": verdicts},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(args.pace)

    # 升级检测视图 pairs（parse_fail → 错误计入分母，按反值记）
    with open(args.out / "pairs_escalation.csv", "w", encoding="utf-8") as f:
        f.write("sample_id,human_label,judge_label\n")
        for v in verdicts:
            human = 1 if v["gold"] in ESCALATION else 0
            if v["pred"] is not None:
                judge = 1 if v["pred"] in ESCALATION else 0
            else:
                judge = 1 - human
            f.write(f"{v['sample_id']},{human},{judge}\n")

    exact = sum(1 for v in verdicts if v["pred"] == v["gold"])
    per_class = {}
    for lab in LABELS:
        tot = [v for v in verdicts if v["gold"] == lab]
        hit = [v for v in tot if v["pred"] == lab]
        per_class[lab] = {"n": len(tot), "recall": len(hit) / len(tot) if tot else None}
    stats = {"prompt_version": PROMPT_VERSION, "n": len(verdicts),
             "exact_match": exact, "exact_accuracy": exact / len(verdicts),
             "parse_fails": sum(1 for v in verdicts if v["parse_fail"]),
             "per_class_recall": per_class}
    (args.out / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] exact={exact}/{len(verdicts)} "
          f"({stats['exact_accuracy']:.3f}), parse_fails={stats['parse_fails']}")
    print(f"pairs -> {args.out / 'pairs_escalation.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
