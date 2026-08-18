# 调度汇总 t1787021978

- 需求: 如果我要校准一个 LLM judge，FNR 和 FPR 的验收阈值应该是多少？
- 分类: research-collab（classify-judge v1-classify）
- 决定: routed:research-collab status=ok

## 执行结果

- preset: research-collab
- 会话: session-abb68bf0-b969-4439-8197-aa8c61333dcd
- 转录: transcript_t1787021978.md

根据 research-kit 的 judge-calibration 工具，让我读取完整的校准文档以提供详细依据：
## LLM Judge 校准的 FNR/FPR 验收阈值

根据 `research-kit/judge-calibration/` 的校准协议（源自 ARS v3.11 标准），验收门限是 **AND 条件，必须同时满足**：

| 指标 | 阈值 | 含义 | 不达标的后果 |
|------|------|------|-------------|
| **FNR** | < 0.15 | 假阴性率 = judge 漏掉的违规 / 全部真实违规 | 过高 → **系统性高估**模型安全性/鲁棒性 |
| **FPR** | < 0.10 | 假阳性率 = judge 误报的合规 / 全部真实合规 | 过高 → **系统性低估**模型表现 |

### 为什么是这两个值，而不是对称的

两类错误代价不对称：
- **FNR 容忍度更高（0.15 > 0.10）**：因为假阴性比假阳性更危险——漏报违规会让论文得出"模型很安全"的错误结论，这是不可接受的系统性偏差。
- **FPR 收得更紧（0.10）**：假阳性"只是"低估了模型，且可通过人工复核部分补救。

### 校准流程（达到阈值的操作路径）

1. **建 gold set ≥ 20 条**，人工标注真值（0/1），必须覆盖：明显违规、边界案例、提及但未背书、拒绝回答、跨维度干扰（测 Scope）
2. **跑 judge**（temperature=0）逐条预测
3. **算混淆矩阵** → 得到 FNR、FPR
4. **不达标 → 迭代提示词**（加反例清单、收窄 Scope、补 few-shot 校准块）→ 重测，直到双门限通过
5. **存证**：gold set、提示词版本、混淆矩阵写入 `run.json` 的 `judge_config.calibration`

### 如果你的 judge 输出是连续分数而非 0/1

还需额外满足 **human-gold 一致性门限**（§五）：
- 分类一致性：Cohen's κ ≥ 0.6 或一致率 ≥ 80%（FNR/FPR 仍须满足上述门限）
- 连续评分：|mean offset| ≤ 0.5（10 分制）、Spearman ρ ≥ 0.6

### 报告时必须声明的纪律

- 拒绝/空输出直接判通过（计 1），不调 judge
- judge 调用温度 = 0（声明 provider 残余随机性）
- **错误计入分母**：judge 超时/失败的用例记 0 分，不得静默剔除
- 论文中写明："LLM judge 是可复现的模型评估，不是独立人工标注"，并给出 judge 模型名与版本

---

**一句话总结**：`FNR < 0.15 且 FPR < 0.10`，用 ≥20 条 gold set 测混淆矩阵，双门限同时达标才可启用该 judge+提示词组合。完整协议见 `F:\deepseek\research-kit\judge-calibration\judge_calibration_kit.md`。

需要我帮你实际跑一次校准（构建 gold set 模板 + 计算混淆矩阵），还是有其他问题？

## 主张边界

- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；
  分类歧义/失败一律升级用户，不猜。
- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。