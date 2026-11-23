# Failure modes

This repository is a research prototype aimed at one local agent host. It is not a production scheduler and not a general-purpose library. There is no package metadata. The publish workflow skips the build when no packaging metadata is present, and it does not upload a release.

The figures `make check` locks live in the README numbers block. This file records what those figures do not mean. If a sentence here and the block disagree, fix the sentence or the checker; do not keep both.

## Gold is not human agreement

Gold labels are assigned by construction. `classify_gold_gen.py` reads the workspace path quoted in the README block. Those frozen task files are not in this repository, so the gold sets cannot be rebuilt here. The check joins committed gold files to committed verdicts. It does not show that a person would assign the same labels.

`gold_classify_v2.json` still records its `gold_set` field as the v1 name. The filename and the item count are what the check uses.

The scorer accepts a reply when exactly one known label string occurs. In these committed runs the raw reply is exactly that label. A longer reply that mentions a label in passing would still be scored as that label. Zero or two labels is a parse failure and stays in the denominator. These runs happened to have none.

## Judge identity is incomplete

Verdict rows do not store a provider or a model. Three runs name a judge in `calibration.json`. `calib_l1_baidu` has no `calibration.json`, so its model is not recorded. The directory name is not a measurement.

## The coding comparison is a ceiling

Result rows store arm A or arm B. They do not store a model id. Arm A is a provider and model in `coding_model_ab.py`. Arm B is the unset default in that dict. The names in `analysis_plan_fleet_r4.json` and `fleet_r4_report.md` are the preregistered labels, not fields replayed from the result rows.

Re-executing `ab_work` and `ab_work_r4` shows that the committed solutions still pass the assertions embedded in those files. It does not call a model again. A file edited after the original session is what this check sees.

Zero discordant pairs make `exact_mcnemar_p` return the value that function defines for an empty split. That is not evidence the arms are equivalent. The tasks are not a public benchmark. One seed. Cost and latency were not measured.

`coding_r4_results.json` reuses a summary note written for the six-task round. The note is stale relative to the sixteen-task rows. The rows and the re-execution are the result. `ab_work_regression` is a partial leftover and is not part of the checked comparison.

`model_map.json` keeps every preset mapping null. This comparison does not justify turning a mapping on.

The previous README said committed calibration runs report 0.875–0.97 exact accuracy with 0 parse failures. The high end, 0.97, was rounding of 31/32 (0.96875), and the sentence collapsed four runs into one range. It also described both coding rounds as 16/16 versus 16/16. The earlier round is 6/6 versus 6/6. Those sentences are withdrawn.

## Host and personal paths

Client scripts hardcode the host and the working directory quoted in the README block. `dispatcher.py` can shell out to `agents/aigc-studio-agent/cli.py` under that working directory, and it appends this personal artifact path: `F:/deepseek/movie_star_beyond/r2v_output/`. The paper-review preset looks for a local PDF path. None of that runs under `make check`.

`make ci-eval` runs `probe_models.py`. That call needs the live host. Without the host it fails. `make check` does not invoke it.

## What the acceptance tests do not cover

The acceptance cases and the plan-executor tests stub dispatch. They do not open a session. Directories `runs/` and `smoke/`, and the session ledger, are artifacts from one machine. Committed verdicts include host session ids. A search of the tree for common credential markers found no API keys. That search is not a formal secret audit.

## License

The repository is MIT. No separate third-party license is bundled. The coding tasks are short specs in this repo, not a vendored external suite.

## About text

GitHub About is not stored in git. The proposed replacement is the sentence in the README block. Until that sentence is pasted into the repository description, the GitHub sidebar can still show the older summary.
