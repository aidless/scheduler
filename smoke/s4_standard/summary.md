# 调度汇总 t1787022035

- 需求: Python 里怎么用 dataclass 定义一个带默认值的类？给个简短示例。
- 分类: standard（classify-judge v1-classify）
- 决定: routed:standard status=ok

## 执行结果

- preset: standard
- 会话: session-08e897f2-85c1-467a-9054-b15913249312
- 转录: transcript_t1787022035.md

Python 的 `dataclass` 通过给字段直接赋默认值即可。简短示例：

```python
from dataclasses import dataclass

@dataclass
class User:
    name: str = "匿名"
    age: int = 0
    role: str = "guest"
    active: bool = True

# 不传参 → 全部用默认值
u1 = User()
print(u1)        # User(name='匿名', age=0, role='guest', active=True)

# 传部分参数，其余用默认值
u2 = User(name="Alice", age=30)
print(u2)        # User(name='Alice', age=30, role='guest', active=True)
```

几个要点：

- **默认值按声明顺序**：有默认值的字段后面不能再跟无默认值的字段，否则会报 `TypeError: non-default argument follows default argument`。
- **可变默认值（如 `list`/`dict`）**不能直接写，因为它是类属性、会被所有实例共享。应改用 `field(default_factory=...)`：

```python
from dataclasses import dataclass, field

@dataclass
class User:
    name: str = "匿名"
    tags: list[str] = field(default_factory=list)   # 正确：每次新建空列表

u = User(tags=["vip"])
print(u)   # User(name='匿名', tags=['vip'])
```

- `dataclass` 默认生成 `__init__` / `__repr__` / `__eq__`，所以上面的实例能直接打印和比较，无需手写。

## 主张边界

- 路由由校准过的 classify-judge 给出（构造即真值 gold 校准）；
  分类歧义/失败一律升级用户，不猜。
- 登记会话见 sched_sessions.json（git 追踪，不自动删除）。