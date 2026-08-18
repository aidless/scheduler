"""scheduler P4: 群统一入口 ask —— "用户提出需求 → 自动拆分/匹配/执行/汇总"。

一个稳定命令名承接任意需求（云计算类比的"单一入口"）：
    python ask.py "<任意需求>"            # 自动：分类→路由（+模型映射）→执行→汇总
    python ask.py "<需求>" --plan-only    # 只看计划与预算，不执行
    python ask.py --resume <state.json>   # 断点续跑
    python ask.py "<需求>" --no-model-map # 关闭模型映射

行为：
  - 产物自动落 runs/<时间戳>/（state.json / summary.md / transcript_*）
  - 升级语义透传：decision 以 escalate 开头 = 调度器请你补充信息或裁决，不猜
  - 退出码：0=完成（含 escalate，因升级本身是正确行为）；1=执行错误
入口融合用法（编排会话内）：research-collab 收到非本域需求时直接跑本入口，
把 summary.md 的结果转达用户——用户全程不需要知道 preset 的存在。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DISPATCHER = HERE / "dispatcher.py"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("need", nargs="?", default=None, help="任意需求文本")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--resume", type=Path, default=None)
    ap.add_argument("--no-model-map", action="store_true",
                    help="关闭模型映射（默认启用 model_map.json）")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", type=Path, default=None,
                    help="产物目录（缺省 runs/<时间戳>/）")
    args = ap.parse_args()

    if not args.need and args.resume is None:
        ap.error("need 必填（或用 --resume）")
    out = args.out or HERE / "runs" / time.strftime("%Y%m%d-%H%M%S")

    cmd = [sys.executable, str(DISPATCHER)]
    if args.resume is not None:
        cmd += ["--resume", str(args.resume)]
    else:
        cmd += [args.need]
        if args.plan_only:
            cmd.append("--plan-only")
    cmd += ["--timeout", str(args.timeout), "--out", str(out)]
    if not args.no_model_map:
        cmd.append("--use-model-map")

    print(f"[ask] 产物目录: {out}", flush=True)
    proc = subprocess.run(cmd)
    summary = out / "summary.md"
    if summary.exists():
        print(f"[ask] 汇总: {summary}")
    state = out / "state.json"
    if state.exists():
        import json
        try:
            decision = json.loads(state.read_text(encoding="utf-8")).get("decision")
            print(f"[ask] 决定: {decision}")
            if decision and decision.startswith("escalate"):
                print("[ask] ⚠ 调度器升级：请按上面的决定补充信息或裁决后重试。")
        except (json.JSONDecodeError, ValueError):
            pass
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
