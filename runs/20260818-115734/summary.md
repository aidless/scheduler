# 调度汇总 t1787025454

- 需求: 帮我把那个东西弄一下。
- 分类: clarify（classify-judge v1-classify）
- 决定: escalate: clarify——需求信息不足或指代不明，请补充：对象是哪个？要做什么？标准是什么？（路由表纪律：不猜）

## 主张边界

- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；
  分类歧义/失败一律升级用户，不猜。
- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。