"""scheduler: 分类版 judge 的 gold set 生成器（构造即真值，无人工标注）。

类别六选一: research-collab / qa-gate / daily-assistant / standard / composite / clarify
构造规则（真值 by construction）：
  - single（12）: 从冻结题集 tasks.json/tasks_r3.json 每类取 3 条（gold handler 即真值），
    与 routing-judge 判定版 gold 所用条目不重叠
  - composite（6）: 取两条不同领域的冻结需求，用"先…再…"连接——含两个不同领域
    原子任务即 composite（构造规则即真值）
  - clarify（6）: 冻结歧义需求 X1-X4 + 2 条构造模糊指代/缺上下文需求
升级检测视图（ARS 二值门）: positive = {composite, clarify}（需升级/规划），
negative = 单一领域；12/12 平衡。
确定性：无随机源，重跑逐字节一致。

用法: python classify_gold_gen.py [--out gold_classify_v1.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MISSION = Path(r"F:\deepseek\.agent-memory\agent-fleet-iter-2026")

SINGLE_PICKS = {
    "research-collab": ["R7", "R9", "R10"],
    "qa-gate": ["E2", "E4", "E5"],
    "daily-assistant": ["D2", "D4", "D5"],
    "standard": ["C2", "C3", "C5"],
}
COMPOSITE_PAIRS = [("R1", "D1"), ("E1", "C1"), ("D2", "R3"),
                   ("C2", "E2"), ("R4", "D3"), ("E3", "C3")]
EXTRA_CLARIFY = [
    ("帮我弄一下那个。", "模糊指代（那个，无上下文）"),
    ("上次说的事情办得怎么样了？", "缺上下文（上次/事情均无指代）"),
]
# v2 扩容：咨询型问题（问方法/标准/用法）→ 归该领域处理者（smoke s2 误路由修复）
ADVISORY = [
    ("写论文的 related work 部分有什么技巧？", "research-collab", "advisory:research"),
    ("效应量和置信区间应该怎么报告才规范？", "research-collab", "advisory:research"),
    ("引用验证一般要核查哪几项内容？", "qa-gate", "advisory:qa"),
    ("怎么判断一个 A/B 实验的预算是否等价？", "qa-gate", "advisory:qa"),
    ("批量重命名文件有什么省事的办法？", "daily-assistant", "advisory:daily"),
    ("把一堆 PDF 合并成一个有什么好工具？", "daily-assistant", "advisory:daily"),
    ("Python 的装饰器一般用在什么场景？", "standard", "advisory:standard"),
    ("单元测试的覆盖率多少算合适？", "standard", "advisory:standard"),
]


def load_tasks() -> dict[str, dict]:
    tasks = {}
    for f in ("tasks.json", "tasks_r3.json"):
        for t in json.loads((MISSION / f).read_text(encoding="utf-8"))["tasks"]:
            tasks[t["id"]] = t
    return tasks


def build(include_advisory: bool = False) -> list[dict]:
    tasks = load_tasks()
    items: list[dict] = []
    n = 0
    for gold, tids in SINGLE_PICKS.items():
        for tid in tids:
            n += 1
            items.append({"sample_id": f"c{n:02d}", "source": tid,
                          "need": tasks[tid]["text"], "gold": gold,
                          "gold_rule": "frozen-task-gold"})
    for a, b in COMPOSITE_PAIRS:
        n += 1
        ta, tb = tasks[a]["text"].rstrip("。"), tasks[b]["text"].rstrip("。")
        items.append({"sample_id": f"c{n:02d}", "source": f"{a}+{b}",
                      "need": f"先{ta}，再{tb}。", "gold": "composite",
                      "gold_rule": "construction:two-domain-conjunction"})
    for tid in ("X1", "X2", "X3", "X4"):
        n += 1
        items.append({"sample_id": f"c{n:02d}", "source": tid,
                      "need": tasks[tid]["text"], "gold": "clarify",
                      "gold_rule": "frozen-ambiguous"})
    for text, why in EXTRA_CLARIFY:
        n += 1
        items.append({"sample_id": f"c{n:02d}", "source": "constructed",
                      "need": text, "gold": "clarify",
                      "gold_rule": f"construction:{why}"})
    if include_advisory:
        for text, gold, rule in ADVISORY:
            n += 1
            items.append({"sample_id": f"c{n:02d}", "source": "constructed",
                          "need": text, "gold": gold,
                          "gold_rule": f"construction:{rule}"})
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "gold_classify_v1.json")
    ap.add_argument("--advisory", action="store_true",
                    help="v2：包含咨询型问题条目（8 条）")
    args = ap.parse_args()
    items = build(include_advisory=args.advisory)
    counts: dict[str, int] = {}
    for i in items:
        counts[i["gold"]] = counts.get(i["gold"], 0) + 1
    esc_pos = sum(1 for i in items if i["gold"] in ("composite", "clarify"))
    payload = {
        "gold_set": "classify-judge v1",
        "task": "需求六分类（四个单一处理者 + composite + clarify）",
        "truth_source": "construction（冻结题集真值 + 确定性连接/模糊构造规则，无人工标注）",
        "escalation_view": "positive={composite,clarify} negative=单一领域（ARS 二值门用）",
        "n": len(items),
        "counts": counts,
        "escalation_pos": esc_pos,
        "escalation_neg": len(items) - esc_pos,
        "items": items,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"gold: {len(items)} items {json.dumps(counts, ensure_ascii=False)} "
          f"escalation {esc_pos}/{len(items) - esc_pos} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
