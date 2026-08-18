# 调度汇总 t1787022676

- 需求: 如果我要校准一个 LLM judge，FNR 和 FPR 的验收阈值应该是多少？
- 分类: qa-gate（classify-judge v1-classify）
- 决定: routed:qa-gate status=ok

## 执行结果

- preset: qa-gate
- 会话: session-5858f7c1-ccf1-41a8-bbb1-c0872d8bf069
- 转录: transcript_t1787022676.md

按本环境 `research-kit` 的 judge 校准 kit（提炼自 **ARS v3.11** 标准，见 `F:\deepseek\research-kit\judge-calibration\judge_calibration_kit.md` 第二节），LLM judge 的验收门限是：

## 验收阈值（ARS v3.11 标准）

> **FNR < 0.15 且 FPR < 0.10**，才可启用该 judge + 提示词组合。

- **FNR**（假阴性率）= 假阴性 /（真阳性 + 假阴性）→ judge 漏报的违规
- **FPR**（假阳性率）= 假阳性 /（真阴性 + 假阳性）→ judge 误报的合规
- 两个条件**必须同时满足**，缺一不启用。

## 为什么是这两个数

两类错误的代价不对称：

- **FNR 高** → 漏报违规，会**系统性高估**模型的安全性/鲁棒性（最危险的方向，门限更严苛的直觉是它对应"放行坏东西"）；
- **FPR 高** → 误报合规，会**低估**模型。

用混淆矩阵而不是准确率，是因为准确率会被多数类掩盖（比如 90% 合规样本里，一个"全判通过"的 judge 准确率也有 90%，但 FPR/FNR 立刻暴露它是废的）。

## 达标前置条件（缺一不算数）

1. **gold set ≥ 20 条**（对应 ARS 的 20-tuple 校准集），覆盖明显违规、边界案例、提及未背书、拒绝回答、跨子类型违规（测 Scope）。gold 越多越好。
2. **judge 温度 0**（provider 残余随机性要在报告里声明）。
3. **拒绝计入通过**：输出为空 / 命中拒绝前缀 → 直接判 1，不调 judge；否则 pass_rate 虚高。
4. **错误计入分母**：调用失败/超时记 0 分进分母，不得静默剔除。
5. 把 gold set、提示词版本、混淆矩阵写进评估契约 `run.json`。

## 不达标怎么办

迭代提示词（加反例、改 Scope、补 few-shot 校准块）→ **重测**，不能降低门限凑合。

## 可选进阶层（论文场景建议加）

如果 judge 分数会作为论文证据，kit 第五节还有 **human-gold 一致性层**（MLR-Bench 模式）：

- 分类：Cohen's κ ≥ 0.6 或一致率 ≥ 80%（FNR/FPR 仍须满足上面门限）；
- 连续：|mean offset| ≤ 0.5（10 分制）、Spearman ρ ≥ 0.6。

报告时写"judge 与人工评审一致性 κ=0.72"远比只写"FPR=0.04"有说服力。

---

一句话记忆：**gold ≥ 20 条，温度 0，FNR < 0.15 且 FPR < 0.10，双条件同时达标才启用；不达标只许迭代提示词，不许放宽门限。**

需要的话，我可以帮你把某个 judge 的预测结果做成混淆矩阵，跑一遍逐项核对是否过线。

## 主张边界

- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；
  分类歧义/失败一律升级用户，不猜。
- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。