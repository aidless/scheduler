#!/usr/bin/env python3
"""Recompute the README numbers block from committed files.

Offline: no network, no API keys, no agent host. Exact match is a recount of
committed verdicts joined to committed gold files. Wilson intervals use the
fixed z below (score interval, endpoints clamped to [0, 1], four decimals).
Coding arms are re-executed from the committed solution files; models are not
called. The integer lock is check/frozen_results.json, written before this
checker. This file recomputes those integers and fails if they, the README
block, or the side files drift.
"""
from __future__ import annotations

import ast
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classify_run import ESCALATION, LABELS, PROMPT_VERSION, parse_label  # noqa: E402
from coding_model_ab import ARMS, exact_mcnemar_p  # noqa: E402

Z_TEXT = "1.959963984540054"
Z = float(Z_TEXT)
BEGIN = "<!-- NUMBERS:BEGIN -->"
END = "<!-- NUMBERS:END -->"
RATE_TOL = 5.1e-4  # stored rates are rounded to 4 decimals

CLASSIFY_SPEC = [
    ("calib_classify_v1", "gold_classify_v1.json"),
    ("calib_classify_v2gold", "gold_classify_v2.json"),
    ("calib_classify_china", "gold_classify_v2.json"),
    ("calib_l1_baidu", "gold_classify_v2.json"),
]
FLEET_SPEC = [
    ("fleet-r3", "coding_ab_results.json", "coding_ab_tasks.json", "ab_work"),
    ("fleet-r4", "coding_r4_results.json", "coding_r4_tasks.json", "ab_work_r4"),
]
DISPATCHER_PATH_NEEDLE = "F:/deepseek/movie_star_beyond/r2v_output/"


def wilson(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("wilson n must be positive")
    z = Z
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / den
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson_fmt(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{lo:.4f} to {hi:.4f}"


def human_join(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assign_literal(name: str, text: str) -> str | None:
    """Return the string literal assigned to a top-level NAME = \"...\" or r\"...\"."""
    m = re.search(rf'^{re.escape(name)} = (r)?"([^"]*)"', text, re.M)
    return m.group(2) if m else None


def escalation_counts(verdicts: list[dict]) -> dict[str, int]:
    tp = fn = fp = tn = 0
    for v in verdicts:
        human = v["gold"] in ESCALATION
        if v["pred"] is None:
            judge = not human
        else:
            judge = v["pred"] in ESCALATION
        if human and judge:
            tp += 1
        elif human and not judge:
            fn += 1
        elif (not human) and judge:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn}


def binary_rates(counts: dict[str, int]) -> dict[str, float]:
    tp, fn, fp, tn = counts["tp"], counts["fn"], counts["fp"], counts["tn"]
    n = tp + fn + fp + tn
    agree = (tp + tn) / n
    p_yes_h = (tp + fn) / n
    p_yes_j = (tp + fp) / n
    p_no_h = (fp + tn) / n
    p_no_j = (tn + fn) / n
    pe = p_yes_h * p_yes_j + p_no_h * p_no_j
    kappa = (agree - pe) / (1.0 - pe) if pe != 1.0 else 1.0
    return {
        "agreement": agree,
        "kappa": kappa,
        "fnr": fn / (tp + fn) if tp + fn else 0.0,
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
    }


def near(stored, actual: float) -> bool:
    return abs(float(stored) - actual) <= RATE_TOL


class Audit:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def base_constants(audit: Audit) -> tuple[str, str, list[str]]:
    files = []
    base_url = None
    cwd = None
    for path in sorted(ROOT.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        base = assign_literal("BASE", text)
        cwd_i = assign_literal("CWD", text)
        if base is None and cwd_i is None:
            continue
        if base is None or cwd_i is None:
            audit.fail(f"{path.name} defines only one of BASE and CWD")
            continue
        files.append(path.name)
        base_url = base if base_url is None else base_url
        cwd = cwd_i if cwd is None else cwd
        if base != base_url or cwd_i != cwd:
            audit.fail(f"{path.name} BASE/CWD differs from the other client scripts")
    if not files or base_url is None or cwd is None:
        audit.fail("no BASE/CWD assignments found")
        return "", "", []
    return base_url, cwd, files


def mission_path(audit: Audit) -> str:
    text = (ROOT / "classify_gold_gen.py").read_text(encoding="utf-8")
    m = re.search(r'^MISSION = Path\(r"([^"]+)"\)', text, re.M)
    if not m:
        audit.fail("classify_gold_gen.py has no MISSION literal")
        return ""
    mission = m.group(1)
    if (ROOT / "tasks.json").exists() or (ROOT / "tasks_r3.json").exists():
        audit.fail("frozen task files are present; gold regeneration is a different check")
    if Path(mission).exists():
        audit.fail(f"MISSION path exists in this environment: {mission}")
    return mission


def config_literals(audit: Audit) -> tuple[str, str]:
    text = (ROOT / "config.json").read_text(encoding="utf-8")
    ver = re.search(r'"version"\s*:\s*"([^"]+)"', text)
    thr = re.search(r'"routing_threshold"\s*:\s*([0-9.]+)', text)
    if not ver or not thr:
        audit.fail("config.json is missing version or routing_threshold")
        return "", ""
    return ver.group(1), thr.group(1)


def check_pairs(run: str, verdicts: list[dict], audit: Audit) -> None:
    path = ROOT / run / "pairs_escalation.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "sample_id,human_label,judge_label":
        audit.fail(f"{run} pairs header drifted")
        return
    body = lines[1:]
    if len(body) != len(verdicts):
        audit.fail(f"{run} pairs has {len(body)} rows, verdicts {len(verdicts)}")
        return
    for line, v in zip(body, verdicts):
        sid, human, judge = line.split(",")
        expect_h = "1" if v["gold"] in ESCALATION else "0"
        if v["pred"] is None:
            expect_j = "0" if expect_h == "1" else "1"
        else:
            expect_j = "1" if v["pred"] in ESCALATION else "0"
        if sid != v["sample_id"] or human != expect_h or judge != expect_j:
            audit.fail(f"{run} pairs row drifted for {v['sample_id']}")
            return


def check_stats(run: str, verdicts: list[dict], audit: Audit) -> None:
    stats = read_json(ROOT / run / "stats.json")
    n = len(verdicts)
    exact = sum(1 for v in verdicts if v["pred"] == v["gold"])
    parse_fails = sum(1 for v in verdicts if v["parse_fail"])
    if stats.get("n") != n or stats.get("exact_match") != exact or stats.get("parse_fails") != parse_fails:
        audit.fail(f"{run} stats.json counts disagree with verdicts")
    elif n and abs(float(stats["exact_accuracy"]) - exact / n) > 1e-12:
        audit.fail(f"{run} stats.json exact_accuracy disagrees with exact/n")
    if stats.get("prompt_version") != PROMPT_VERSION:
        audit.fail(f"{run} stats.json prompt_version is not {PROMPT_VERSION}")
    per = stats.get("per_class_recall") or {}
    for lab in LABELS:
        tot = [v for v in verdicts if v["gold"] == lab]
        hit = sum(1 for v in tot if v["pred"] == lab)
        rec = per.get(lab)
        if not rec or rec.get("n") != len(tot):
            audit.fail(f"{run} stats.json recall n drifted for {lab}")
            continue
        if tot and abs(float(rec["recall"]) - hit / len(tot)) > 1e-12:
            audit.fail(f"{run} stats.json recall drifted for {lab}")


def check_side_rates(run: str, verdicts: list[dict], audit: Audit) -> None:
    counts = escalation_counts(verdicts)
    rates = binary_rates(counts)
    cal_path = ROOT / run / "calibration.json"
    if cal_path.exists():
        cal = read_json(cal_path)
        if cal.get("n_gold") != len(verdicts):
            audit.fail(f"{run} calibration.json n_gold disagrees")
        if not near(cal.get("fnr"), rates["fnr"]) or not near(cal.get("fpr"), rates["fpr"]):
            audit.fail(f"{run} calibration.json fnr/fpr disagrees with verdicts")
        if cal.get("prompt_version") != PROMPT_VERSION:
            audit.fail(f"{run} calibration.json prompt_version drifted")
    cons_path = ROOT / run / "consistency.json"
    if cons_path.exists():
        cons = read_json(cons_path)
        if cons.get("n") != len(verdicts):
            audit.fail(f"{run} consistency.json n disagrees")
        got = cons.get("confusion") or {}
        if any(got.get(k) != counts[k] for k in ("tp", "fn", "fp", "tn")):
            audit.fail(f"{run} consistency.json confusion disagrees: {got} vs {counts}")
        for key in ("agreement", "kappa", "judge_fnr_vs_human", "judge_fpr_vs_human"):
            actual_key = {"judge_fnr_vs_human": "fnr", "judge_fpr_vs_human": "fpr"}.get(key, key)
            if key not in cons or not near(cons[key], rates[actual_key]):
                audit.fail(f"{run} consistency.json {key} disagrees")
        should_pass = rates["kappa"] >= 0.6 or rates["agreement"] >= 0.8
        if (cons.get("gate") == "PASS") != should_pass:
            audit.fail(f"{run} consistency.json gate does not follow its stated rule")


def classify_facts(audit: Audit) -> list[dict]:
    gold_cache: dict[str, dict] = {}
    rows = []
    bare = True
    for run, gold_name in CLASSIFY_SPEC:
        if gold_name not in gold_cache:
            gold = read_json(ROOT / gold_name)
            items = gold["items"]
            if gold.get("n") != len(items) or sum(gold.get("counts", {}).values()) != len(items):
                audit.fail(f"{gold_name} n/counts/items disagree")
            if not str(gold.get("truth_source", "")).startswith("construction"):
                audit.fail(f"{gold_name} truth_source does not start with construction")
            gold_cache[gold_name] = {it["sample_id"]: it for it in items}
        by_id = gold_cache[gold_name]
        blob = read_json(ROOT / run / "judge_verdicts.json")
        verdicts = blob["verdicts"]
        ids = [v["sample_id"] for v in verdicts]
        if len(ids) != len(set(ids)):
            audit.fail(f"{run} has duplicate sample ids")
        if set(ids) != set(by_id):
            audit.fail(f"{run} sample ids do not match {gold_name}")
        for v in verdicts:
            reparsed = parse_label(v.get("raw") or "")
            if reparsed != v.get("pred"):
                audit.fail(f"{run} {v['sample_id']} pred does not match reparse of raw")
            if bool(v.get("parse_fail")) != (v.get("pred") is None):
                audit.fail(f"{run} {v['sample_id']} parse_fail flag disagrees with pred")
            item = by_id.get(v["sample_id"])
            if item is not None and item["gold"] != v["gold"]:
                audit.fail(f"{run} {v['sample_id']} gold disagrees with {gold_name}")
            if v.get("status") != "ok" or v.get("retries") != 0:
                audit.fail(f"{run} {v['sample_id']} is not status ok with retries 0")
            if v.get("pred") is None or str(v.get("raw", "")).strip() != v["pred"]:
                bare = False
        if blob.get("prompt_version") != PROMPT_VERSION:
            audit.fail(f"{run} prompt_version is not {PROMPT_VERSION}")
        check_stats(run, verdicts, audit)
        check_pairs(run, verdicts, audit)
        check_side_rates(run, verdicts, audit)
        cal = ROOT / run / "calibration.json"
        judge = read_json(cal)["judge"] if cal.exists() else "not recorded"
        rows.append({
            "exact": sum(1 for v in verdicts if v["pred"] == v["gold"]),
            "gold_file": gold_name,
            "judge": judge,
            "misses": [v["sample_id"] for v in verdicts if v["pred"] != v["gold"]],
            "n": len(verdicts),
            "parse_fails": sum(1 for v in verdicts if v["parse_fail"]),
            "prompt_version": blob.get("prompt_version"),
            "run": run,
        })
    if not bare:
        audit.fail("at least one raw reply is not exactly the predicted label")
    return rows


def reexec(path: Path) -> bool:
    proc = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True, text=True, timeout=30, encoding="utf-8",
    )
    return proc.returncode == 0 and "TESTS_OK" in proc.stdout


def fleet_facts(audit: Audit) -> list[dict]:
    rows = []
    for rnd, results_file, tasks_file, work in FLEET_SPEC:
        blob = read_json(ROOT / results_file)
        spec = read_json(ROOT / tasks_file)
        results = blob["results"]
        by: dict[str, dict] = {}
        for rec in results:
            by.setdefault(rec["task_id"], {})[rec["arm"]] = rec
        if spec.get("n") != len(spec.get("tasks", [])) or len(by) != len(spec["tasks"]):
            audit.fail(f"{rnd} task-file n does not match result rows")
        if set(by) != {t["id"] for t in spec["tasks"]}:
            audit.fail(f"{rnd} task ids do not match {tasks_file}")
        b = c = 0
        reexec_pass = 0
        for tid, arms in by.items():
            if set(arms) != {"A", "B"}:
                audit.fail(f"{rnd} {tid} does not have both arms")
                continue
            if arms["A"]["pass"] == 1 and arms["B"]["pass"] == 0:
                b += 1
            elif arms["A"]["pass"] == 0 and arms["B"]["pass"] == 1:
                c += 1
            for arm, rec in arms.items():
                path = ROOT / work / f"{tid}_{arm}.py"
                if not path.is_file():
                    audit.fail(f"missing {path.relative_to(ROOT)}")
                    continue
                ok = reexec(path)
                if ok != (rec["pass"] == 1):
                    audit.fail(f"re-exec of {path.name} does not match recorded pass={rec['pass']}")
                if ok:
                    reexec_pass += 1
                if rec.get("status") != "ok" or rec.get("retries") != 0 or rec.get("extracted") is not True:
                    audit.fail(f"{results_file} {tid} {arm} is not status ok, retries 0, extracted")
        summary = blob["summary"]
        p = exact_mcnemar_p(b, c)
        n_tasks = len(by)
        pass_a = sum(1 for r in results if r["arm"] == "A" and r["pass"] == 1)
        pass_b = sum(1 for r in results if r["arm"] == "B" and r["pass"] == 1)
        if summary.get("n_tasks") != n_tasks or summary.get("b_Awin") != b or summary.get("c_Bwin") != c:
            audit.fail(f"{results_file} summary counts disagree with rows")
        if n_tasks and (
            abs(float(summary["acc_A_mapped"]) - pass_a / n_tasks) > 1e-12
            or abs(float(summary["acc_B_default"]) - pass_b / n_tasks) > 1e-12
            or abs(float(summary["p_exact"]) - p) > 1e-12
        ):
            audit.fail(f"{results_file} summary rates disagree with rows")
        if p < 0.05 and b > c:
            decision = "promote_mapping"
        elif p < 0.05 and c > b:
            decision = "rollback_mapping"
        else:
            decision = "keep_with_disclosure"
        if summary.get("decision") != decision:
            audit.fail(f"{results_file} decision {summary.get('decision')!r} != {decision}")
        rows.append({
            "b_A_only": b,
            "c_B_only": c,
            "pass_A": pass_a,
            "pass_B": pass_b,
            "reexec_pass": reexec_pass,
            "results_file": results_file,
            "results_plan_id": blob.get("plan_id"),
            "round": rnd,
            "summary_note": summary.get("note"),
            "tasks": n_tasks,
            "tasks_file": tasks_file,
            "tasks_plan_id": spec.get("plan_id"),
            "work_dir": work,
        })
    return rows


def acceptance_count(audit: Audit) -> int:
    path = ROOT / "eval" / "cases.jsonl"
    n = sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "run_cases.py")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    m = re.search(r"(\d+)/(\d+) cases passed", proc.stdout)
    if proc.returncode != 0 or not m or m.group(1) != m.group(2) or int(m.group(1)) != n:
        audit.fail(f"acceptance cases failed or did not pass {n}/{n}")
    proc_red = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "run_cases.py"), "--selftest"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    red = re.search(r"(\d+)/(\d+) cases passed", proc_red.stdout)
    if proc_red.returncode != 0 or not red or int(red.group(1)) >= int(red.group(2)):
        audit.fail("acceptance --selftest did not go red")
    return n


def plan_checks(audit: Audit) -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "test_plan_executor.py")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    n = sum(1 for ln in proc.stdout.splitlines() if ln.startswith("PASS "))
    fails = sum(1 for ln in proc.stdout.splitlines() if ln.startswith("FAIL "))
    if proc.returncode != 0 or fails or "ALL PASS" not in proc.stdout:
        audit.fail("test_plan_executor.py did not pass")
    return n


def import_audit(audit: Audit) -> bool:
    local = {p.stem for p in ROOT.glob("*.py")}
    stdlib = sys.stdlib_module_names
    ok = True
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            audit.fail(f"syntax error in {path.relative_to(ROOT)}: {exc}")
            ok = False
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    continue
                names = [node.module.split(".")[0]]
            for name in names:
                if name in stdlib or name in local or name == "__future__":
                    continue
                audit.fail(f"{path.relative_to(ROOT)} imports third-party module {name}")
                ok = False
    return ok


def check_model_map(fleet: list[dict], audit: Audit) -> None:
    mm = read_json(ROOT / "model_map.json")
    mapping = mm.get("mapping") or {}
    if any(v is not None for v in mapping.values()):
        audit.fail("model_map.json mapping is no longer all null")
    hist = mm.get("validation_history") or {}
    expect = {
        "fleet_r3_p3": next(r for r in fleet if r["round"] == "fleet-r3"),
        "fleet_r4": next(r for r in fleet if r["round"] == "fleet-r4"),
    }
    for key, row in expect.items():
        got = hist.get(key) or {}
        p = exact_mcnemar_p(row["b_A_only"], row["c_B_only"])
        if got.get("tasks") != row["tasks"] or got.get("b") != row["b_A_only"] or got.get("c") != row["c_B_only"]:
            audit.fail(f"model_map.json {key} counts disagree with recomputation")
        if row["tasks"] and (
            abs(float(got.get("acc_A", -1)) - row["pass_A"] / row["tasks"]) > 1e-12
            or abs(float(got.get("acc_B", -1)) - row["pass_B"] / row["tasks"]) > 1e-12
            or abs(float(got.get("p", -1)) - p) > 1e-12
        ):
            audit.fail(f"model_map.json {key} rates disagree with recomputation")
    report = (ROOT / "fleet_r4_report.md").read_text(encoding="utf-8")
    r4 = expect["fleet_r4"]
    rows = r4["tasks"] * 2
    p_text = f"{exact_mcnemar_p(r4['b_A_only'], r4['c_B_only']):.4f}"
    needles = [
        f"{r4['pass_A']}/{r4['tasks']}",
        f"{r4['pass_B']}/{r4['tasks']}",
        f"p={p_text}",
        f"b={r4['b_A_only']}",
        f"c={r4['c_B_only']}",
        f"{rows}/{rows}",
    ]
    for needle in needles:
        if needle not in report:
            audit.fail(f"fleet_r4_report.md is missing recomputed token {needle}")
    dispatcher = (ROOT / "dispatcher.py").read_text(encoding="utf-8")
    modes = (ROOT / "FAILURE_MODES.md").read_text(encoding="utf-8")
    if DISPATCHER_PATH_NEEDLE not in dispatcher or DISPATCHER_PATH_NEEDLE not in modes:
        audit.fail("dispatcher personal output path is not quoted in both dispatcher.py and FAILURE_MODES.md")


def build_facts(audit: Audit) -> dict:
    base_url, cwd, base_files = base_constants(audit)
    version, threshold = config_literals(audit)
    gold_v2 = read_json(ROOT / "gold_classify_v2.json")
    return {
        "acceptance_cases": acceptance_count(audit),
        "base_files": base_files,
        "base_url": base_url,
        "classify": classify_facts(audit),
        "config_version": version,
        "cwd": cwd,
        "fleet": fleet_facts(audit),
        "gold_v2_gold_set_field": gold_v2.get("gold_set"),
        "labels": list(LABELS),
        "mission_path": mission_path(audit),
        "plan_executor_checks": plan_checks(audit),
        "routing_threshold_literal": threshold,
    }


def render(facts: dict) -> str:
    runs = facts["classify"]
    fracs = human_join([f"{r['exact']}/{r['n']}" for r in runs])
    intervals = human_join([wilson_fmt(r["exact"], r["n"]) for r in runs])
    if all(r["parse_fails"] == 0 for r in runs):
        pf = "with 0 parse failures in each run"
        pf_about = "0 parse failures"
    else:
        detail = ", ".join(f"{r['run']} {r['parse_fails']}" for r in runs)
        pf = f"with parse failures [{detail}]"
        pf_about = pf
    r3 = next(r for r in facts["fleet"] if r["round"] == "fleet-r3")
    r4 = next(r for r in facts["fleet"] if r["round"] == "fleet-r4")
    p4 = exact_mcnemar_p(r4["b_A_only"], r4["c_B_only"])
    p_empty = f"{exact_mcnemar_p(0, 0):.4f}"
    w4a, w4b = wilson_fmt(r4["pass_A"], r4["tasks"]), wilson_fmt(r4["pass_B"], r4["tasks"])
    if w4a == w4b:
        w4 = f"Each arm's Wilson 95% interval is {w4a}."
    else:
        w4 = f"Wilson 95% intervals are {w4a} for arm A and {w4b} for arm B."
    plan = read_json(ROOT / "analysis_plan_fleet_r4.json")
    arm_a = ARMS["A"]
    lines = [
        f"**Result.** On the {len(runs)} committed classify-judge runs, in the table order below, exact label match is {fracs}, {pf}. "
        f"Wilson 95% intervals (z={Z_TEXT}) are {intervals}. "
        f"Gold labels are true by construction, not human agreement, and this check did not call the host at {facts['base_url']}.",
        "",
        f"The separate fleet-r4 coding comparison is a ceiling: both arms {r4['pass_A']}/{r4['tasks']} and {r4['pass_B']}/{r4['tasks']}, "
        f"{r4['b_A_only']} discordant pairs where only arm A passed and {r4['c_B_only']} where only arm B passed, "
        f"so exact_mcnemar_p returns {p4:.4f}. {w4} "
        f"The earlier round was {r3['pass_A']}/{r3['tasks']} versus {r3['pass_B']}/{r3['tasks']} "
        f"(Wilson 95% {wilson_fmt(r3['pass_A'], r3['tasks'])}), not another {r4['tasks']}/{r4['tasks']}.",
        "",
        "### Classify judge",
        "",
        "Exact match counts a stored pred only when it equals classify_run.parse_label of the raw reply and equals the gold-file label for that sample_id. "
        "Parse failures stay in the denominator. Every raw reply in these runs is exactly the predicted label. "
        "stats.json and pairs_escalation.csv match that recount. "
        "Where calibration.json and consistency.json exist, their escalation contingency matches the recount. "
        "Every verdict row has status ok and retries 0. "
        f"Prompt on every verdict file is {runs[0]['prompt_version']}. "
        f"Labels are {', '.join(facts['labels'])}. "
        f"gold_classify_v2.json field gold_set is still \"{facts['gold_v2_gold_set_field']}\". "
        "Both gold files set truth_source to a string that starts with \"construction\". "
        "Verdict rows do not record a provider or model. The judge column is calibration.json when that file exists, and \"not recorded\" when it does not.",
        "",
        "| run | gold file | judge in calibration.json | n | exact | parse_fails | Wilson 95% | misses |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in runs:
        misses = ", ".join(r["misses"]) if r["misses"] else "none"
        lines.append(
            f"| {r['run']} | {r['gold_file']} | {r['judge']} | {r['n']} | {r['exact']} | {r['parse_fails']} | {wilson_fmt(r['exact'], r['n'])} | {misses} |"
        )
    lines += [
        "",
        "### Coding A/B",
        "",
        f"Recomputed from the results rows and by executing each committed solution file. A pass is exit code 0 and stdout containing TESTS_OK. No model call. "
        f"exact_mcnemar_p is the function in coding_model_ab.py; with no discordant pairs it returns {p_empty} by that function's definition. "
        "A ceiling is not evidence the arms are equivalent. "
        f"In coding_model_ab.py, arm A is provider {arm_a['provider']} model {arm_a['model']}, and arm B is {ARMS['B']!r}. "
        "Result rows do not store a model id. "
        f"Preregistered arm text in analysis_plan_fleet_r4.json: A is {plan['arms']['A_mapped']}; B is {plan['arms']['B_default']}.",
        "",
        "| round | results file | tasks | arm A | arm B | A-only | B-only | McNemar p | Wilson 95% A | Wilson 95% B | re-exec |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in facts["fleet"]:
        p = exact_mcnemar_p(row["b_A_only"], row["c_B_only"])
        denom = row["tasks"] * 2
        lines.append(
            f"| {row['round']} | {row['results_file']} | {row['tasks']} | {row['pass_A']}/{row['tasks']} | {row['pass_B']}/{row['tasks']} | "
            f"{row['b_A_only']} | {row['c_B_only']} | {p:.4f} | {wilson_fmt(row['pass_A'], row['tasks'])} | "
            f"{wilson_fmt(row['pass_B'], row['tasks'])} | {row['reexec_pass']}/{denom} |"
        )
    if "n=6" in r4["summary_note"] and r4["tasks"] != 6:
        lines += [
            "",
            f"{r4['results_file']} summary.note still contains \"n=6\" while the results rows cover {r4['tasks']} tasks. "
            f"results plan_id is {r4['results_plan_id']}; the task file plan_id is {r4['tasks_plan_id']}. "
            "The counts above come from the rows and from re-execution, not from that note.",
        ]
    mapping = read_json(ROOT / "model_map.json")["mapping"]
    n_null = sum(1 for v in mapping.values() if v is None)
    lines += [
        "",
        f"model_map.json keeps {n_null} of {len(mapping)} preset mappings null.",
        "",
        "### Offline gate",
        "",
        f"eval/cases.jsonl has {facts['acceptance_cases']} cases and test_plan_executor.py reports {facts['plan_executor_checks']} passing checks. "
        f"BASE is {facts['base_url']} in {len(facts['base_files'])} scripts: {', '.join(facts['base_files'])}. "
        f"CWD is {facts['cwd']}. "
        f"classify_gold_gen.py MISSION is {facts['mission_path']}, which is not in this repo. "
        f"config.json version is {facts['config_version']} and routing_threshold literal is {facts['routing_threshold_literal']}. "
        "Every Python import in this repo resolves to the standard library or to a top-level module in this repository.",
        "",
        "Proposed GitHub About text: "
        f"Research prototype that classifies requests for one local agent host ({facts['base_url']}). "
        f"Committed judge runs: exact match {fracs}, with {pf_about}. "
        "Gold is by construction, not human agreement. Not a general-purpose scheduler.",
    ]
    return "\n".join(lines)


def extract_block(text: str, audit: Audit) -> str:
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        audit.fail("README must contain exactly one numbers block")
        return ""
    i = text.index(BEGIN)
    j = text.index(END)
    if j < i:
        audit.fail("README numbers block markers are out of order")
        return ""
    inner = text[i + len(BEGIN):j]
    if inner.startswith("\n"):
        inner = inner[1:]
    if inner.endswith("\n"):
        inner = inner[:-1]
    return inner


def check_readme(text: str, block: str, audit: Audit) -> None:
    lines = text.splitlines()
    if not lines or lines[0] != "# scheduler":
        audit.fail("README must open with the title")
    if "actions/workflows/static-checks.yml" not in text:
        audit.fail("README CI badge must point at static-checks.yml")
    if "Those sentences are withdrawn." not in text:
        audit.fail("README is missing the withdrawal sentence")
    try:
        b = lines.index(BEGIN)
    except ValueError:
        return
    if b < 5 or lines[b - 1] != "" or lines[b - 5] != "":
        audit.fail("README problem statement must be three lines directly above the numbers block")
        return
    problem = lines[b - 4:b - 1]
    if len(problem) != 3 or any(not ln.strip() for ln in problem):
        audit.fail("README problem statement is not exactly three non-empty lines")
    if any(re.search(r"\d", ln) for ln in problem):
        audit.fail("README problem statement contains a digit")
    got = extract_block(text, audit)
    if got != block:
        diff = "\n".join(
            __import__("difflib").unified_diff(
                block.splitlines(), got.splitlines(),
                fromfile="recomputed", tofile="README", lineterm="",
            )
        )
        audit.fail("README numbers block drifted from recomputation:\n" + diff)
    outside = text[:text.index(BEGIN)] + text[text.index(END) + len(END):]
    nums = re.findall(r"\d+(?:\.\d+)?", outside)
    if nums:
        audit.fail(f"README has numbers outside the checked block: {nums}")


def comparator_selftest(block: str, audit: Audit) -> None:
    """The README comparison is string equality. A one-count edit must fail it."""
    tampered = block.replace("23/24", "22/24", 1)
    if tampered == block:
        audit.fail("checker self-test could not tamper 23/24")


def main(argv: list[str]) -> int:
    audit = Audit()
    facts = build_facts(audit)
    frozen_path = ROOT / "check" / "frozen_results.json"
    if not frozen_path.is_file():
        audit.fail("check/frozen_results.json is missing")
    else:
        frozen = read_json(frozen_path)
        if facts != frozen:
            got = json.dumps(facts, ensure_ascii=False, indent=2, sort_keys=True)
            exp = json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True)
            diff = "\n".join(
                __import__("difflib").unified_diff(
                    exp.splitlines(), got.splitlines(),
                    fromfile="frozen_results.json", tofile="recomputed", lineterm="",
                )
            )
            audit.fail("recomputed integers differ from frozen_results.json:\n" + diff)
    import_audit(audit)
    if facts.get("fleet"):
        check_model_map(facts["fleet"], audit)
    block = render(facts) if facts.get("classify") and facts.get("fleet") else ""
    if "--print-block" in argv:
        print(block)
        if audit.errors:
            print("\n".join(audit.errors), file=sys.stderr)
            return 1
        return 0
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if block:
        check_readme(readme, block, audit)
        comparator_selftest(block, audit)
    about = ""
    for line in block.splitlines():
        if line.startswith("Proposed GitHub About text: "):
            about = line.split(": ", 1)[1]
    if about and len(about) > 350:
        audit.fail(f"proposed About text is {len(about)} characters; GitHub allows 350")
    if audit.errors:
        print(f"{len(audit.errors)} check failure(s):", file=sys.stderr)
        for err in audit.errors:
            print(err, file=sys.stderr)
        return 1
    print("CHECK OK")
    print(block.splitlines()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
