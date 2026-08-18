# fleet-r4 模型映射 A/B 分析报告（补齐统计尾巴）

> 预注册：analysis_plan_fleet_r4.json（2026-08-18，frozen）
> 前情：fleet-r3/P3 用 6 个简单编码任务，两臂 12/12 全过 → ceiling effect，无法定论。
> 本轮：换 16 个难度梯度任务（medium~hard），重跑 A/B 定论。

## 设计

- **A（映射）**：baidu/qianfan-code-latest（代码专精）
- **B（默认）**：china/Qwen3.8-Max（旗舰通用）
- 均在 standard preset 会话，仅 selectModel 不同（单因素=模型）
- **判分**：提取模型输出 python 代码块 → 拼接确定性断言 → 运行 → 退出码 0=pass
  （无 LLM judge，双臂同一套断言；提取失败=0 计入分母）
- **任务集**：coding_r4_tasks.json，16 题，参考实现先自校验
  （validate_coding_r4_tests.py → ALL_TESTS_VALID 才进 A/B）

## 任务难度梯度（16 题）

| 难度 | 任务 |
| --- | --- |
| medium | 最长无重复子串 / 有效括号 / 合并区间 / 字母异位词分组 / 前 K 高频 / 逆波兰求值 / 最大子数组 |
| medium-hard | 三数之和 / 最长回文子串 / 课程表（拓扑判环） |
| hard | 编辑距离 / 接雨水 / 零钱兑换 / 岛屿数量 / LRU 缓存（类）/ 前缀树 Trie（类） |

## 结果

| 臂 | 通过数 | 通过率 |
| --- | --- | --- |
| A（qianfan-code-latest） | 16/16 | 1.000 |
| B（Qwen3.8-Max） | 16/16 | 1.000 |

- 分裂对：b=0（A 过 B 挂），c=0（A 挂 B 过）
- exact McNemar：p=1.0000（无分裂对）
- 32/32 全部 status=ok、retries=0

## 决定：**keep_with_disclosure**（按预注册 decision_rule）

p≥0.05 且无分裂对 → 映射保留（opt-in）但标注"无显著差异证据"。

## 诚实解读

1. **两次尝试（6 简单题 + 16 难度梯度题）均触顶**：两臂全对。这不是题集偶然太易——
   hard 档（编辑距离/接雨水/LRU/Trie/岛屿/课程表）也全解出，说明这两个模型在
   算法编码上确实都很强，**难度梯度内无法区分**。
2. **结论**：编码任务上，代码专精模型 vs 旗舰通用模型**无可检出差异**（不优也不劣）。
   默认 Qwen3.8-Max 已足够胜任编码，切换到 qianfan-code-latest **无实证收益**。
3. **主张边界**：这是"无法定论/无优势证据"，不是"证明了两者完全等同"；未测
   竞赛级（Codeforces/ICPC）更难题、未测成本/延迟、未测真实项目级代码。
4. **建议**：model_map 的 standard→qianfan-code-latest 映射保持 **opt-in**
   （无害但不必要）。若要真找差异，需上竞赛级题或真实工程任务——但两轮触顶提示
   收益可能仍为零，优先级应放低。

## 产物

- coding_r4_tasks.json（16 题+断言）
- validate_coding_r4_tests.py（参考实现自校验，ALL_TESTS_VALID）
- coding_r4_results.json（32 run 明细）
- ab_work_r4/（被测代码+断言留档）
- coding_model_ab.py 增 --tasks/--work 参数（向后兼容）
