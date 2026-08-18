# 调度汇总 t1787022056

- 需求: 先给我写一个冒泡排序函数，再帮我整理一份会议纪要模板。
- 分类: composite（classify-judge v1-classify）
- 决定: escalate: composite——需求含多领域子任务，拆分/并行/汇总为 P2 能力，P1 不执行；请拆分后分别提交或等 P2

## 主张边界

- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；
  分类歧义/失败一律升级用户，不猜。
- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。