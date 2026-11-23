# Offline gate. `make check` recomputes the README numbers block from committed
# files and reruns the acceptance cases plus the plan-executor tests.
# No model calls and no agent host. `make ci-eval` probes the live host and is
# not part of `make check`.
.PHONY: eval ci-eval check

check:
	python3 check/recompute.py

eval:
	python3 eval/run_cases.py
	python3 test_plan_executor.py

ci-eval:
	python3 probe_models.py
