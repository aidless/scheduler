# scheduler

A single-entry dispatcher for a fleet of local AI agent sessions: it takes an arbitrary natural-language request, classifies it with a calibrated judge, routes it to the right specialist agent preset (or plans it as a subtask DAG), executes, and returns one aggregated report.

> **Research prototype.** This was extracted from a personal research workspace and drives a specific local agent host (JSON-RPC over HTTP at `http://127.0.0.1:3080/api`) — it is not a general-purpose library. See [Quick start](#quick-start) for what must be configured before reusing it.

## What it is

`scheduler` implements the "single front door" pattern for a multi-agent workspace: instead of choosing which agent session to open, the user issues one request to `ask.py` and the scheduler handles classification, routing, execution, and reporting.

The pipeline:

1. **Classify** — a prompt-frozen LLM judge labels the request as one of six classes: `research-collab`, `qa-gate`, `daily-assistant`, `standard` (single-domain), `composite` (multiple domains), or `clarify` (ambiguous). The judge is calibrated against gold sets that are true *by construction* (no human labeling); committed calibration runs report 0.875–0.97 exact accuracy with 0 parse failures (`calib_classify_*/stats.json`).
2. **Route** — single-domain requests are dispatched to the matching agent preset session on the host (`research-collab`, `qa-gate`, `daily-assistant`, `standard`, plus keyword pre-routes for `paperreview-agent`, `kg-retrieval-agent`, `aigc-studio-agent`). Optional per-preset model mapping (`model_map.json`) is applied via the host's `selectModel`.
3. **Plan and execute** — composite requests go through an LLM planner that proposes a subtask DAG (`plan_executor.py`). The plan is validated deterministically: presets must be whitelisted, ids unique, the graph acyclic, and protection keywords (delete/publish/pay/…) force `protection=true`. Protected subtasks are never auto-executed — they return `awaiting-user`. Execution is topological with checkpointing: each finished subtask updates `state.json`, upstream results are injected into downstream prompts, and `--resume` skips completed work.
4. **Escalate, don't guess** — `clarify` labels, unparseable plans, and failed classifications escalate to the user instead of being routed somewhere plausible. Escalation is reported as exit code 0 with an explicit decision.
5. **Summarize** — every run writes `state.json`, `summary.md`, and per-task `transcript_*.md` under `runs/<timestamp>/`.

Design discipline visible in the code:

- **Deterministic guardrails over LLM output** — plan validation and protection keywords do not rely on the model's compliance.
- **Errors count in the denominator** — parse failures are scored as errors, not silently retried; 429/quota responses use a fixed backoff ladder (30/60/120/240/480 s).
- **No silent deletion** — the session ledger `sched_sessions.json` is git-tracked under a no-auto-delete policy; `sched_sessions.py retire` requires `--confirm` and only marks the ledger (it never touches host sessions).
- **Preregistered experiments** — calibration and A/B studies use frozen analysis plans (`analysis_plan_fleet_r4.json`, `model_map.json`), deterministic scoring (assert-and-run, no LLM judge), and exact McNemar tests. The committed `fleet_r4_report.md` documents a null result honestly: two coding A/B rounds both hit the ceiling (16/16 vs 16/16), so the model mapping stays opt-in with "no detectable difference" disclosed rather than claimed.

## Quick start

**Requirements:** Python 3.10+. Standard library only — the scripts import nothing outside `argparse`, `json`, `urllib`, `subprocess`, `re`, `time`, `pathlib`, etc. There is no `pip install` step.

**Prerequisite (for anything that talks to models):** a local agent host exposing JSON-RPC over HTTP at `http://127.0.0.1:3080/api`, with agent presets named `research-collab`, `qa-gate`, `daily-assistant`, `standard`, and `minimal`. The endpoint and working directory are hardcoded constants at the top of each script (`BASE = "http://127.0.0.1:3080/api"`, `CWD = ...`) — edit them to point at your own host. Scripts that only run pure logic or self-validation need no host at all.

Offline (no host, no model calls):

```bash
python test_plan_executor.py        # plan-executor logic tests (stubbed dispatch) → ALL PASS
python ask.py --check-routes        # routing source-of-truth consistency check
python ask.py --list-routes         # presets + keyword routes (also --format json|md)
python validate_coding_tests.py     # self-validate coding A/B assertions (reference impls)
python validate_coding_r4_tests.py  # same, for the 16-task fleet-r4 set
python sched_sessions.py stats      # inspect the session ledger
```

Full pipeline (requires the agent host):

```bash
python ask.py "Fix the login page error, then turn the meeting notes into a document"
python ask.py "<request>" --plan-only           # show the plan and budget, don't execute
python ask.py --resume runs/<ts>/state.json     # resume a run from its checkpoint
python ask.py "<request>" --no-model-map        # disable per-preset model mapping
```

Artifacts land in `runs/<timestamp>/` (`state.json`, `summary.md`, `transcript_*.md`).

Calibration and experiments (requires the agent host; gold sets and task files are committed):

```bash
python classify_run.py --gold gold_classify_v1.json --out calib_classify_v1   # classify-judge calibration
python classify_run.py --gold gold_classify_v2.json --out calib_classify_v2gold
python coding_model_ab.py --tasks coding_r4_tasks.json --work ab_work_r4     # preregistered coding A/B
python probe_models.py --out probe_models.json                               # dump host model catalog
python probe_preset_defaults.py                                              # per-preset default models
python verify_select_model.py --preset standard --provider <p> --model <m>   # prove selectModel takes effect
```

## Repository structure

```
ask.py                    Unified entry point: classify → route → execute → summarize;
                          --list-routes / --check-routes introspection
dispatcher.py             Core P1 dispatch loop (classify, single-domain routing, escalation)
plan_executor.py          P2 composite planner: DAG proposal, deterministic validation,
                          topological execution, checkpoint/resume, aggregation
classify_run.py           Calibrated classify-judge runner (gold set → verdicts + stats)
classify_gold_gen.py      Gold set generator (truth by construction; needs the original
                          workspace's frozen task files, which are not in this repo)
sched_sessions.py         Session ledger management: list / stats / retire (--confirm)
coding_model_ab.py        Preregistered A/B of model mapping on coding tasks
                          (deterministic assert-and-run scoring, exact McNemar)
probe_models.py           Probe the host's model catalog (session.models)
probe_preset_defaults.py  Probe each preset's default model
verify_select_model.py    Three-step evidence that selectModel actually reroutes
verify_tool_plugin.py     E2E check that the scheduler tool is visible to agent sessions
demo_tool_dispatch.py     Demo: an agent session dispatching through the scheduler tool
test_plan_executor.py     Pure-logic tests for plan_executor (no model calls)
validate_coding_tests.py  Self-validate A/B task assertions with reference implementations
validate_coding_r4_tests.py  Same, for the 16-task fleet-r4 set

config.json               Routing threshold and prompt version stamp
model_map.json            Frozen (preregistered) per-preset model mapping — currently
                          all null: keep provider defaults, mapping is opt-in
gold_classify_v1.json     Committed gold sets for the classify judge
gold_classify_v2.json
coding_ab_tasks.json      Coding A/B task sets with deterministic assertions
coding_r4_tasks.json
analysis_plan_fleet_r4.json  Frozen analysis plan for fleet-r4
fleet_r4_report.md        A/B results report (null result, disclosed as such)
sched_sessions.json       Git-tracked session ledger (no-auto-delete policy)

calib_classify_v1/        Committed calibration runs: verdicts, escalation pairs, stats
calib_classify_v2gold/
calib_classify_china/
calib_l1_baidu/
ab_work/                  A/B artifacts: generated code + assertions per task/arm
ab_work_r4/
ab_work_regression/
runs/                     Committed example run outputs (state.json + summary.md)
smoke/                    Committed smoke-test runs (one per class + composite/clarify)
smoke_p2/                 Smoke tests for planner/DAG execution paths
smoke_p3/                 Smoke test for model mapping
```

## License

MIT — see [LICENSE](LICENSE).
