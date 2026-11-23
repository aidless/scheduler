# scheduler

[![CI](https://github.com/aidless/scheduler/actions/workflows/static-checks.yml/badge.svg)](https://github.com/aidless/scheduler/actions/workflows/static-checks.yml)

A local multi-agent workspace still needs a person to choose which specialist session handles each request.
This repository is a research prototype of one front door: classify the request, route a single-domain request, or plan a composite one.
It speaks JSON-RPC to one hardcoded local agent host and is not a general-purpose or production scheduler.

<!-- NUMBERS:BEGIN -->
**Result.** On the 4 committed classify-judge runs, in the table order below, exact label match is 23/24, 29/32, 31/32, and 28/32, with 0 parse failures in each run. Wilson 95% intervals (z=1.959963984540054) are 0.7976 to 0.9926, 0.7578 to 0.9676, 0.8426 to 0.9945, and 0.7193 to 0.9503. Gold labels are true by construction, not human agreement, and this check did not call the host at http://127.0.0.1:3080/api.

The separate fleet-r4 coding comparison is a ceiling: both arms 16/16 and 16/16, 0 discordant pairs where only arm A passed and 0 where only arm B passed, so exact_mcnemar_p returns 1.0000. Each arm's Wilson 95% interval is 0.8064 to 1.0000. The earlier round was 6/6 versus 6/6 (Wilson 95% 0.6097 to 1.0000), not another 16/16.

### Classify judge

Exact match counts a stored pred only when it equals classify_run.parse_label of the raw reply and equals the gold-file label for that sample_id. Parse failures stay in the denominator. Every raw reply in these runs is exactly the predicted label. stats.json and pairs_escalation.csv match that recount. Where calibration.json and consistency.json exist, their escalation contingency matches the recount. Every verdict row has status ok and retries 0. Prompt on every verdict file is v1-classify. Labels are research-collab, qa-gate, daily-assistant, standard, composite, clarify. gold_classify_v2.json field gold_set is still "classify-judge v1". Both gold files set truth_source to a string that starts with "construction". Verdict rows do not record a provider or model. The judge column is calibration.json when that file exists, and "not recorded" when it does not.

| run | gold file | judge in calibration.json | n | exact | parse_fails | Wilson 95% | misses |
| --- | --- | --- | --- | --- | --- | --- | --- |
| calib_classify_v1 | gold_classify_v1.json | baidu/qianfan-code-latest | 24 | 23 | 0 | 0.7976 to 0.9926 | c20 |
| calib_classify_v2gold | gold_classify_v2.json | baidu/qianfan-code-latest | 32 | 29 | 0 | 0.7578 to 0.9676 | c04, c20, c32 |
| calib_classify_china | gold_classify_v2.json | china/Qwen3.8-Max | 32 | 31 | 0 | 0.8426 to 0.9945 | c01 |
| calib_l1_baidu | gold_classify_v2.json | not recorded | 32 | 28 | 0 | 0.7193 to 0.9503 | c20, c27, c31, c32 |

### Coding A/B

Recomputed from the results rows and by executing each committed solution file. A pass is exit code 0 and stdout containing TESTS_OK. No model call. exact_mcnemar_p is the function in coding_model_ab.py; with no discordant pairs it returns 1.0000 by that function's definition. A ceiling is not evidence the arms are equivalent. In coding_model_ab.py, arm A is provider baidu model qianfan-code-latest, and arm B is None. Result rows do not store a model id. Preregistered arm text in analysis_plan_fleet_r4.json: A is baidu/qianfan-code-latest（代码专精，model_map v1 的映射目标）; B is china/Qwen3.8-Max（旗舰通用，standard preset 默认）.

| round | results file | tasks | arm A | arm B | A-only | B-only | McNemar p | Wilson 95% A | Wilson 95% B | re-exec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fleet-r3 | coding_ab_results.json | 6 | 6/6 | 6/6 | 0 | 0 | 1.0000 | 0.6097 to 1.0000 | 0.6097 to 1.0000 | 12/12 |
| fleet-r4 | coding_r4_results.json | 16 | 16/16 | 16/16 | 0 | 0 | 1.0000 | 0.8064 to 1.0000 | 0.8064 to 1.0000 | 32/32 |

coding_r4_results.json summary.note still contains "n=6" while the results rows cover 16 tasks. results plan_id is model-map-v1; the task file plan_id is fleet-r4. The counts above come from the rows and from re-execution, not from that note.

model_map.json keeps 4 of 4 preset mappings null.

### Offline gate

eval/cases.jsonl has 20 cases and test_plan_executor.py reports 13 passing checks. BASE is http://127.0.0.1:3080/api in 7 scripts: classify_run.py, coding_model_ab.py, demo_tool_dispatch.py, probe_models.py, probe_preset_defaults.py, verify_select_model.py, verify_tool_plugin.py. CWD is F:\deepseek. classify_gold_gen.py MISSION is F:\deepseek\.agent-memory\agent-fleet-iter-2026, which is not in this repo. config.json version is G084-single05-20260821 and routing_threshold literal is 0.5. Every Python import in this repo resolves to the standard library or to a top-level module in this repository.

Proposed GitHub About text: Research prototype that classifies requests for one local agent host (http://127.0.0.1:3080/api). Committed judge runs: exact match 23/24, 29/32, 31/32, and 28/32, with 0 parse failures. Gold is by construction, not human agreement. Not a general-purpose scheduler.
<!-- NUMBERS:END -->

## What the code does

`ask.py` is the front door. Classification, routing, and composite planning live in `dispatcher.py` and `plan_executor.py`. Presets that are not a single safe domain escalate instead of being guessed. Plan validation is deterministic: a preset whitelist, unique ids, an acyclic graph, and protection keywords. Protected steps stay unexecuted.

Scripts that talk to models need the host named in the checked block. Edit the constants at the top of those scripts before pointing them at a different machine. Pure logic tests do not need the host.

## Reproduce

`make check` recomputes the block above from committed files, reruns the offline acceptance cases (including the self-test that must go red), and reruns the plan-executor logic tests. It does not call a model, does not read API keys, and does not contact the agent host. `make eval` is the acceptance subset. `make ci-eval` is the live host probe and fails when that host is absent.

## Limits

Gold labels are true by construction, not human agreement. The gold generator's workspace path is outside this repository, so the gold files cannot be rebuilt here. Verdict rows do not name a provider or model. Live routing was not re-run. A coding ceiling is a null result, not evidence the two arms are the same. Details are in [FAILURE_MODES.md](FAILURE_MODES.md).

## Withdrawn

The previous README compressed the classify runs into one rounded accuracy range and described both coding rounds as the longer ceiling. Those sentences are withdrawn. The checked block is the claim.

## License

MIT. See [LICENSE](LICENSE).
