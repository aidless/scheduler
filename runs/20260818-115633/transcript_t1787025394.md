# 调度结果 t1787025394

- 需求: 把 F:\deepseek\agent-群架构 目录下的 .md 文件列一个清单，按文件名排序。
- 路由: daily-assistant
- 会话: session-c28fb14e-3152-45ae-8eed-607a30b8d1f2

## 回答

已在 `F:\deepseek\agent-群架构` 下找到 **48 个 .md 文件**。下面按**文件名（basename）**排序，同名文件归到一组、组内再按路径排序。路径均相对于 `F:\deepseek\agent-群架构\`。

### 1. `ARCHITECTURE.md`（1）
- `ARCHITECTURE.md`

### 2. `daily-assistant-probe.md`（1）
- `probes\daily-assistant-probe.md`

### 3. `group_health.md`（15）
- `.verify\final_sweep\health\group_health.md`
- `.verify\final_sweep\v2_combo\group_health\group_health.md`
- `.verify\health_p2\group_health.md`
- `.verify\health_p3\group_health.md`
- `.verify\health_p5\group_health.md`
- `.verify\health_post_fleet\group_health.md`
- `.verify\health_promote\group_health.md`
- `.verify\health_real\group_health.md`
- `.verify\health_sched\group_health.md`
- `.verify\health_v2\group_health.md`
- `.verify\qa_smoke_ext\group_health\group_health.md`
- `.verify\regression_r2\health\group_health.md`
- `.verify\regression_r2\health2\group_health.md`
- `.verify\regression_r2\health3\group_health.md`
- `.verify\regression_r2\qa\group_health\group_health.md`

### 4. `judge_calibration_gate.md`（4）
- `.verify\e2e_calib\judge_calibration_gate.md`
- `.verify\final_sweep\v2_combo\judge_calibration_gate.md`
- `.verify\v2_smoke\jc_fail\judge_calibration_gate.md`
- `.verify\v2_smoke\jc_pass\judge_calibration_gate.md`

### 5. `qa-gate-probe.md`（1）
- `probes\qa-gate-probe.md`

### 6. `README.md`（1）
- `probes\README.md`

### 7. `report.md`（16）
- `.verify\e2e_calib\report.md`
- `.verify\final_sweep\compat\report.md`
- `.verify\final_sweep\v2_combo\report.md`
- `.verify\probe_qa\report.md`
- `.verify\probe_qa_session\report.md`
- `.verify\qa_smoke\report.md`
- `.verify\qa_smoke_compat\report.md`
- `.verify\qa_smoke_ext\report.md`
- `.verify\regression_r2\qa\report.md`
- `.verify\v2_smoke\compat\report.md`
- `.verify\v2_smoke\contract\report.md`
- `.verify\v2_smoke\jc_fail\report.md`
- `.verify\v2_smoke\jc_pass\report.md`
- `.verify\v2_smoke\jp_fail\report.md`
- `.verify\v2_smoke\jp_pass\report.md`
- `.verify\v2_smoke\tmlr\report.md`

### 8. `SCHEDULER_DESIGN.md`（1）
- `SCHEDULER_DESIGN.md`

### 9. `tmlr_compliance.md`（2）
- `.verify\final_sweep\v2_combo\tmlr_compliance.md`
- `.verify\v2_smoke\tmlr\tmlr_compliance.md`

### 10. `transcript_daily-assistant_A1.md`（1）
- `.verify\p1_probe_sessions\transcript_daily-assistant_A1.md`

### 11. `transcript_daily-assistant_A2.md`（1）
- `.verify\p1_probe_sessions\transcript_daily-assistant_A2.md`

### 12. `transcript_daily-assistant_A3.md`（1）
- `.verify\p1_probe_sessions\transcript_daily-assistant_A3.md`

### 13. `transcript_qa-gate_B1.md`（1）
- `.verify\p1_probe_sessions\transcript_qa-gate_B1.md`

### 14. `transcript_qa-gate_B2.md`（1）
- `.verify\p1_probe_sessions\transcript_qa-gate_B2.md`

### 15. `transcript_qa-gate_B3.md`（1）
- `.verify\p1_probe_sessions\transcript_qa-gate_B3.md`

---

几点观察：
- 顶层实际只有 **3 个**「正经」文档：`ARCHITECTURE.md`、`SCHEDULER_DESIGN.md`、`probes\README.md`，外加两个 probe 文件。
- 其余 **43 个**全在 `.verify\` 下，是各类校验/冒烟/回归运行的产物，且高度重复（`report.md` 出现 16 次、`group_health.md` 15 次）。

如果你想要的是一份不含 `.verify\` 校验产物的「文档清单」，告诉我，我可以只列顶层与 `probes\` 下的。
