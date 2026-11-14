# --- acceptance_backfill (EVAL_ACCEPTANCE_STANDARD.md P4) ---
# 证据来源: probe_models.py
# 本机预期红（B 类）：probe_models.py 要连活体 agent host http://127.0.0.1:3080/api
# 并 session.create，没有 host 凭据时服务端直接回 "unauthorized"，本机离线跑不出 0。
# 因此原命令保留为 ci-eval:，eval: 跑仓内离线可复算的两套：eval/run_cases.py（20 条
# 验收题库，必须 20/20）+ test_plan_executor.py（13 项纯逻辑测试，ALL PASS）。
.PHONY: eval ci-eval

eval:
	python3 eval/run_cases.py
	python3 test_plan_executor.py

ci-eval:
	python3 probe_models.py
