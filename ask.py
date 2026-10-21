"""scheduler P4: 群统一入口 ask —— "用户提出需求 → 自动拆分/匹配/执行/汇总"。

一个稳定命令名承接任意需求（云计算类比的"单一入口"）：
    python ask.py "<任意需求>"            # 自动：分类→路由（+模型映射）→执行→汇总
    python ask.py "<需求>" --plan-only    # 只看计划与预算，不执行
    python ask.py --resume <state.json>   # 断点续跑
    python ask.py "<需求>" --no-model-map # 关闭模型映射
    python ask.py --list-routes           # 人类可读：列出所有 routable preset + 关键词路由表
    python ask.py --list-routes --format=json  # 机器可读 JSON
    python ask.py --list-routes --format=md    # Markdown 表格
    python ask.py --check-routes          # 验证调度器分类真值源一致性（CI 防漂移）

行为：
  - 产物自动落 runs/<时间戳>/（state.json / summary.md / transcript_*）
  - 升级语义透传：decision 以 escalate 开头 = 调度器请你补充信息或裁决，不猜
  - 退出码：0=完成（含 escalate，因升级本身是正确行为）；1=执行错误
入口融合用法（编排会话内）：research-collab 收到非本域需求时直接跑本入口，
把 summary.md 的结果转达用户——用户全程不需要知道 preset 的存在。

范式来源: Omarchy bin/omarchy --json/--markdown/--check (E269/E272)
真值源: dispatcher.ROUTABLE + 三个 *_KEYWORDS 常量（反射读取，不建第二份）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
DISPATCHER = HERE / "dispatcher.py"


def _load_routes() -> dict:
    """反射读取 dispatcher 的路由真值源。返回 dict 或抛异常。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("dispatcher_routes", str(DISPATCHER))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 dispatcher: {DISPATCHER}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return {
        "routable": list(getattr(mod, "ROUTABLE", [])),
        "paperreview_keywords": list(getattr(mod, "PAPERREVIEW_KEYWORDS", [])),
        "kg_retrieval_keywords": list(getattr(mod, "KG_RETRIEVAL_KEYWORDS", [])),
        "aigc_keywords": list(getattr(mod, "AIGC_KEYWORDS", [])),
    }


def _do_list_routes(fmt: str) -> int:
    try:
        routes = _load_routes()
    except Exception as e:
        print(f"[ask --list-routes] 加载 dispatcher 真值源失败: {e}", file=sys.stderr)
        return 1

    routable = routes["routable"]
    kw = {
        "paperreview-agent": routes["paperreview_keywords"],
        "kg-retrieval-agent": routes["kg_retrieval_keywords"],
        "aigc-studio-agent": routes["aigc_keywords"],
    }

    if fmt == "json":
        out = {
            "routable": routable,
            "keyword_routes": kw,
            "route_count": len(routable),
            "keyword_counts": {k: len(v) for k, v in kw.items()},
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if fmt == "md":
        print("| Preset | Keywords | Count |")
        print("| --- | --- | --- |")
        for preset in routable:
            kws = kw.get(preset, [])
            kw_str = ", ".join(f"`{k}`" for k in kws[:6])
            if len(kws) > 6:
                kw_str += f" +{len(kws)-6} more"
            if not kws:
                kw_str = "_(no keyword pre-route)_"
            print(f"| `{preset}` | {kw_str} | {len(kws)} |")
        # 额外：关键词表总览
        print("")
        print(f"总计 {len(routable)} 个 routable preset，关键词总数 {sum(len(v) for v in kw.values())}")
        return 0

    # human
    print(f"Routable presets ({len(routable)}):")
    for p in routable:
        print(f"  - {p}")
    print("")
    print("Keyword pre-routes:")
    for preset, kws in kw.items():
        print(f"  {preset} ({len(kws)} keywords):")
        for k in kws:
            # 转义不可见字符
            disp = k.replace("\n", "\\n")[:60]
            print(f"    - {disp!r}")
    print("")
    print(f"总计 {len(routable)} 个 preset，关键词 {sum(len(v) for v in kw.values())} 条")
    return 0


def _do_check_routes() -> int:
    """验证 dispatcher 真值源一致性。0=通过，非0=失败（CI 防漂移）。"""
    try:
        routes = _load_routes()
    except Exception as e:
        print(f"[ask --check-routes] 加载失败: {e}", file=sys.stderr)
        return 1

    failures: list[str] = []
    routable = routes["routable"]
    kw_map = {
        "paperreview-agent": routes["paperreview_keywords"],
        "kg-retrieval-agent": routes["kg_retrieval_keywords"],
        "aigc-studio-agent": routes["aigc_keywords"],
    }

    # 1. ROUTABLE 非空、无空串、无重复
    if not routable:
        failures.append("ROUTABLE 为空")
    else:
        seen: set[str] = set()
        for r in routable:
            if not isinstance(r, str) or not r.strip():
                failures.append(f"ROUTABLE 含空/非字符串: {r!r}")
            if r in seen:
                failures.append(f"ROUTABLE 重复: {r!r}")
            seen.add(r)

    # 2. 各关键词表：元素为非空字符串
    for preset, kws in kw_map.items():
        if not isinstance(kws, list):
            failures.append(f"{preset} 关键词表不是 list")
            continue
        for k in kws:
            if not isinstance(k, str) or not k.strip():
                failures.append(f"{preset} 含空关键词: {k!r}")

    # 3. 三表之间无二义性：同一 token 不应在两表出现（大小写+strip 归一后）
    # 归一：lower + strip；同一 preset 内的大小写变体不算跨 preset 冲突
    norm_to_presets: dict[str, set[str]] = {}
    for preset, kws in kw_map.items():
        for k in kws:
            norm = k.strip().lower()
            if not norm:
                continue
            norm_to_presets.setdefault(norm, set()).add(preset)
    for norm, presets in norm_to_presets.items():
        if len(presets) > 1:
            failures.append(f"关键词二义性: {norm!r} 同时在 {sorted(presets)}")

    # 4. 关键字段齐全：ROUTABLE 应包含 4 个基础 preset
    for must in ["research-collab", "qa-gate", "daily-assistant", "standard"]:
        if must not in routable:
            failures.append(f"ROUTABLE 缺基础 preset: {must!r}")

    if failures:
        print("[ask --check-routes] FAIL — 发现以下问题:", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        print(f"\n共 {len(failures)} 个问题", file=sys.stderr)
        return 1

    print(f"[ask --check-routes] PASS — {len(routable)} presets, "
          f"{sum(len(v) for v in kw_map.values())} keywords, 无二义性")
    return 0


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
    # Omarchy 范式：机器可读三模式（E269/E272）
    ap.add_argument("--list-routes", action="store_true",
                    help="列出所有 routable preset + 关键词路由表（反射读 dispatcher 真值源）")
    ap.add_argument("--check-routes", action="store_true",
                    help="验证调度器分类真值源一致性（CI 防漂移，失败退出非零）")
    ap.add_argument("--format", choices=["human", "json", "md"], default="human",
                    help="配合 --list-routes：输出格式（默认 human）")
    # 兼容别名：--json / --md 直接等同 --list-routes --format=json|md
    ap.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--md", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    # 别名归一
    if args.json:
        args.list_routes = True
        args.format = "json"
    if args.md:
        args.list_routes = True
        args.format = "md"

    # 机器可读三模式优先（不需要 need/resume）
    if args.list_routes:
        return _do_list_routes(args.format)
    if args.check_routes:
        return _do_check_routes()

    if not args.need and args.resume is None:
        ap.error("need 必填（或用 --resume，或用 --list-routes/--check-routes）")
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
