# 调度汇总 t1787021930

- 需求: 写论文时如何在结果部分报告效应量？给我一个 APA 格式的示例。
- 分类: research-collab（classify-judge v1-classify）
- 决定: routed:research-collab status=ok

## 执行结果

- preset: research-collab
- 会话: session-43fa3c12-ebf0-4095-b89d-adb7598e5a13
- 转录: transcript_t1787021930.md

效应量报告是 Results 部分最常被忽视又最关键的一环。先说原则，再给匹配表，最后是可直接套用的 APA 7.0 示例。

## 一、为什么必须报告效应量

p 值只回答"效应是否存在"，效应量回答"效应有多大"，二者不可互相替代。大样本下微小差异也会显著，只报 *p* < .05 会让读者误判实际意义。所以核心原则是：

> **效应量 + 置信区间 > 裸 p 值**。报告"显著"是必要的，但不充分；永远同时报告效应大小和精度。

## 二、检验方法 → 效应量匹配表

| 检验场景 | 效应量指标 | 解读基准（Cohen 粗略） |
|---------|-----------|----------------------|
| 独立样本 / 配对 t 检验 | Cohen's *d*（配对用 *d_z*） | 小≈0.20 / 中≈0.50 / 大≈0.80 |
| 单因素 ANOVA | η²（η²_p 重复测量）/ ω² | 小≈0.01 / 中≈0.06 / 大≈0.14 |
| 卡方检验 | Cramér's *V* / φ | 小≈0.10 / 中≈0.30 / 大≈0.50 |
| Pearson / Spearman 相关 | *r*（本身就是效应量） | 小≈.10 / 中≈.30 / 大≈.50 |
| 线性回归 | *R²* / 调整 *R²* / 标准化 β | 按领域经验值解读 |
| 非参数两组 | 秩双列相关 *r*（rank-biserial） | 沿用 *r* 的基准 |

## 三、APA 7.0 报告示例

### 示例 1：独立样本 t 检验（最常用）

> An independent-samples *t*-test revealed that the experimental group (*M* = 12.30, *SD* = 3.20, *n* = 30) scored significantly higher than the control group (*M* = 9.80, *SD* = 3.50, *n* = 30), *t*(58) = 2.89, *p* = .005, *d* = 0.75, 95% CI [0.77, 4.23].

要点拆解：
- **描述性统计先行**：每组都要给 *M*、*SD*（必要时 *n*），让读者能独立重算效应量。
- **统计量三件套**：*t*(df)、*p*、*d*，APA 中 *p* 不写前导零（.005 而非 0.005），统计符号斜体。
- **置信区间**：这里 95% CI 是**均值差的置信区间**；如果工具支持，也可报告 *d* 自己的 CI（如 *d* = 0.75, 95% CI [0.22, 1.28]），二者不冲突，但要在文中说明 CI 指的是哪个量。
- **保留三位小数**：*p* 值小于 .001 时写 *p* < .001。

### 示例 2：单因素 ANOVA + 事后比较

> A one-way ANOVA revealed a significant effect of treatment condition on accuracy, *F*(2, 87) = 5.43, *p* = .006, η² = 0.11, 90% CI [0.02, 0.21]. Post-hoc comparisons using Tukey's HSD indicated that the high-dose group (*M* = 0.82, *SD* = 0.09) outperformed the placebo group (*M* = 0.71, *SD* = 0.11), *p* = .004, *d* = 1.09; no significant difference was found between low-dose and placebo conditions, *p* = .34, *d* = 0.18.

注意：ANOVA 的 η² 置信区间惯例用 **90% CI**（非 95%），因为 η² 本身是非中心 *F* 分布参数，90% CI 与 *F* 检验的 α = .05 对应。

### 示例 3：相关分析

> Pearson correlation indicated a moderate positive association between training epochs and calibration improvement, *r*(48) = .42, *p* = .003, 95% CI [.16, .63].

*r* 本身就是效应量，无需

## 主张边界

- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；
  分类歧义/失败一律升级用户，不猜。
- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。