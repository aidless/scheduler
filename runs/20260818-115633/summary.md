# 调度汇总 t1787025394

- 需求: 把 F:\deepseek\agent-群架构 目录下的 .md 文件列一个清单，按文件名排序。
- 分类: daily-assistant（classify-judge v1-classify）
- 决定: routed:daily-assistant status=ok

## 执行结果

- preset: daily-assistant
- 会话: session-c28fb14e-3152-45ae-8eed-607a30b8d1f2
- 转录: transcript_t1787025394.md

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
- `SCHEDULER_DESIGN.

## 主张边界

- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；
  分类歧义/失败一律升级用户，不猜。
- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。