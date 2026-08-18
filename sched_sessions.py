"""scheduler P4: 调度器会话账本管理（sched_sessions.json）。

宿主 API 无 session 删除能力（rpc-map 只有 list/search/create/history/models/
selectModel/rename/fork/prompt/attachment/updateQueue/cancel）——本工具管理的是
调度器自己的账本（审计层）：list/stats/retire。retire 只是账本标记（不触碰宿主
会话；宿主会话列表由 GUI 管理），且必须 --confirm 显式确认——默认不删任何东西。

用法:
    python sched_sessions.py list [--purpose dispatch|classify|planner] [--preset X]
    python sched_sessions.py stats
    python sched_sessions.py retire --older-than 72 [--purpose X] --dry-run
    python sched_sessions.py retire --older-than 72 --confirm   # 显式确认才落盘
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent / "sched_sessions.json"


def load() -> list:
    if not REGISTRY.exists():
        return []
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def save(entries: list) -> None:
    REGISTRY.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def age_hours(entry: dict) -> float:
    try:
        ts = datetime.fromisoformat(entry["ts"])
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    except (KeyError, ValueError):
        return float("inf")


def cmd_list(entries: list, purpose: str | None, preset: str | None) -> int:
    rows = [e for e in entries
            if (purpose is None or e.get("purpose") == purpose)
            and (preset is None or e.get("preset") == preset)]
    print(f"共 {len(rows)} 条（总 {len(entries)}）")
    for e in rows:
        retired = " [retired]" if e.get("retired") else ""
        print(f"  {e.get('ts', '?')[:19]}  {e.get('purpose', '?'):<9} "
              f"{e.get('preset', '?'):<17} {e.get('sessionId', '?')[:40]}{retired}")
    return 0


def cmd_stats(entries: list) -> int:
    by_purpose: dict[str, int] = {}
    by_preset: dict[str, int] = {}
    retired = 0
    for e in entries:
        by_purpose[e.get("purpose", "?")] = by_purpose.get(e.get("purpose", "?"), 0) + 1
        by_preset[e.get("preset", "?")] = by_preset.get(e.get("preset", "?"), 0) + 1
        if e.get("retired"):
            retired += 1
    print(f"总条目: {len(entries)}（其中 retired {retired}）")
    print("按用途:", json.dumps(by_purpose, ensure_ascii=False))
    print("按 preset:", json.dumps(by_preset, ensure_ascii=False))
    return 0


def cmd_retire(entries: list, older_than: float, purpose: str | None,
               confirm: bool, dry_run: bool) -> int:
    candidates = [e for e in entries
                  if not e.get("retired")
                  and age_hours(e) >= older_than
                  and (purpose is None or e.get("purpose") == purpose)]
    print(f"候选 {len(candidates)} 条（age ≥ {older_than}h"
          + (f", purpose={purpose}" if purpose else "") + "）")
    for e in candidates[:20]:
        print(f"  {e.get('ts', '?')[:19]}  {e.get('purpose', '?'):<9} "
              f"{e.get('preset', '?'):<17} age={age_hours(e):.1f}h")
    if len(candidates) > 20:
        print(f"  … 其余 {len(candidates) - 20} 条略")
    if dry_run:
        print("[dry-run] 未改动账本")
        return 0
    if not confirm:
        print("未加 --confirm：不落盘（默认不删任何东西）")
        return 0
    ids = {e.get("sessionId") for e in candidates}
    n = 0
    for e in entries:
        if e.get("sessionId") in ids and not e.get("retired"):
            e["retired"] = True
            e["retired_at"] = datetime.now(timezone.utc).isoformat()
            n += 1
    save(entries)
    print(f"[confirm] 已标记 retired {n} 条（账本级；宿主会话列表不受影响）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--purpose", default=None)
    p_list.add_argument("--preset", default=None)
    sub.add_parser("stats")
    p_retire = sub.add_parser("retire")
    p_retire.add_argument("--older-than", type=float, required=True, help="小时")
    p_retire.add_argument("--purpose", default=None)
    p_retire.add_argument("--dry-run", action="store_true")
    p_retire.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    entries = load()
    if args.cmd == "list":
        return cmd_list(entries, args.purpose, args.preset)
    if args.cmd == "stats":
        return cmd_stats(entries)
    if args.cmd == "retire":
        return cmd_retire(entries, args.older_than, args.purpose,
                          args.confirm, args.dry_run)
    return 1


if __name__ == "__main__":
    sys.exit(main())
