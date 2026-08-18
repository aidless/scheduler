"""scheduler P2: plan_executor 纯逻辑测试（无模型调用，stub dispatch）。

覆盖（SCHEDULER_DESIGN §8.3 故障演练最小集）：
  1. verify_plan：合法/preset 非法/环/保护层关键词强制标记
  2. topo_levels：分层序 + 环检测
  3. execute_plan 语义：链式 ok（上游注入）/ 上游 fail→下游 skip /
     protection→awaiting-user 且不投递
  4. extract_plan_json：文本内嵌 JSON 提取
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_executor import (execute_plan, extract_plan_json,  # noqa: E402
                           topo_levels, verify_plan)

FAILURES = []


def check(name: str, cond: bool):
    print(f"{'PASS' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


def make_state(subs_meta):
    return {
        "task_id": "test", "need": "test",
        "plan": {"subtasks": subs_meta},
        "subtasks": {s["id"]: {"status": "pending", "answer": "", "sessionId": ""}
                     for s in subs_meta},
    }


def ok_dispatch(prompt, preset, timeout):
    ok_dispatch.calls.append((prompt, preset))
    return {"status": "ok", "answer": f"ANSWER({preset})", "sessionId": "stub-sid"}


ok_dispatch.calls = []


def fail_dispatch(prompt, preset, timeout):
    fail_dispatch.calls.append((prompt, preset))
    return {"status": "turn-error: stub", "answer": "", "sessionId": "stub-sid"}


fail_dispatch.calls = []


def main() -> int:
    # 1. verify_plan
    errs, cleaned = verify_plan({"subtasks": [
        {"id": "s1", "text": "写一个排序函数", "preset": "standard", "depends_on": []},
        {"id": "s2", "text": "整理会议纪要", "preset": "daily-assistant",
         "depends_on": ["s1"]}]})
    check("verify 合法计划无错误", errs == [] and len(cleaned["subtasks"]) == 2)

    errs, _ = verify_plan({"subtasks": [
        {"id": "s1", "text": "x", "preset": "unknown-agent", "depends_on": []}]})
    check("verify preset 非法被拒", any("preset 非法" in e for e in errs))

    errs, _ = verify_plan({"subtasks": [
        {"id": "s1", "text": "x", "preset": "standard", "depends_on": ["s2"]},
        {"id": "s2", "text": "y", "preset": "standard", "depends_on": ["s1"]}]})
    check("verify 环被拒", any("环" in e for e in errs))

    errs, cleaned = verify_plan({"subtasks": [
        {"id": "s1", "text": "删除临时目录里的旧文件", "preset": "daily-assistant",
         "depends_on": []}]})
    check("verify 保护层关键词强制标记",
          errs == [] and cleaned["subtasks"][0]["protection"] is True)

    errs, _ = verify_plan({"subtasks": [
        {"id": "s1", "text": "x", "preset": "standard", "depends_on": ["ghost"]}]})
    check("verify 依赖引用不存在被拒", any("引用不存在" in e for e in errs))

    # 2. topo_levels
    levels, err = topo_levels([
        {"id": "s1", "depends_on": []}, {"id": "s2", "depends_on": ["s1"]},
        {"id": "s3", "depends_on": ["s1"]}, {"id": "s4", "depends_on": ["s2", "s3"]}])
    check("topo 分层正确", err == "" and levels == [["s1"], ["s2", "s3"], ["s4"]])

    # 3. execute_plan 语义
    ok_dispatch.calls = []
    st = make_state([
        {"id": "s1", "text": "写代码", "preset": "standard",
         "depends_on": [], "protection": False},
        {"id": "s2", "text": "用上游结果继续", "preset": "standard",
         "depends_on": ["s1"], "protection": False}])
    execute_plan(st, ok_dispatch)
    check("链式执行两子任务都 ok",
          st["subtasks"]["s1"]["status"] == "ok" and st["subtasks"]["s2"]["status"] == "ok")
    check("上游答案注入下游提示",
          "ANSWER(standard)" in ok_dispatch.calls[1][0]
          and "写代码" in ok_dispatch.calls[0][0]
          and "ANSWER(standard)" not in ok_dispatch.calls[0][0])

    fail_dispatch.calls = []
    st = make_state([
        {"id": "s1", "text": "会失败的任务", "preset": "standard",
         "depends_on": [], "protection": False},
        {"id": "s2", "text": "依赖 s1", "preset": "standard",
         "depends_on": ["s1"], "protection": False}])
    execute_plan(st, fail_dispatch)
    check("上游 fail → 下游 skip 且不投递",
          st["subtasks"]["s1"]["status"] == "fail"
          and st["subtasks"]["s2"]["status"] == "skip"
          and len(fail_dispatch.calls) == 1)

    ok_dispatch.calls = []
    st = make_state([
        {"id": "s1", "text": "删除某目录全部文件", "preset": "daily-assistant",
         "depends_on": [], "protection": True},
        {"id": "s2", "text": "依赖 s1", "preset": "standard",
         "depends_on": ["s1"], "protection": False}])
    execute_plan(st, ok_dispatch)
    check("protection → awaiting-user 且零投递、下游 skip",
          st["subtasks"]["s1"]["status"] == "awaiting-user"
          and st["subtasks"]["s2"]["status"] == "skip"
          and len(ok_dispatch.calls) == 0)

    st = make_state([
        {"id": "s1", "text": "t", "preset": "standard",
         "depends_on": [], "protection": False}])
    st["subtasks"]["s1"]["status"] = "ok"
    st["subtasks"]["s1"]["answer"] = "已有结果"
    ok_dispatch.calls = []
    execute_plan(st, ok_dispatch)
    check("resume 语义：ok 子任务不重跑", len(ok_dispatch.calls) == 0)

    # 4. extract_plan_json
    txt = '好的，拆分如下：{"subtasks": [{"id": "s1", "text": "a", "preset": "standard", "depends_on": []}]} 完毕。'
    plan = extract_plan_json(txt)
    check("JSON 从包裹文本中提取", plan is not None and len(plan["subtasks"]) == 1)
    check("无 JSON 文本返回 None", extract_plan_json("没有任何 json") is None)

    print(f"\n{'ALL PASS' if not FAILURES else 'FAILURES: ' + str(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
