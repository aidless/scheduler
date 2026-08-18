# 调度结果 t1787024853

- 需求: 写一个函数，把驼峰命名转成下划线命名。
- 路由: standard
- 模型: baidu/qianfan-code-latest
- 会话: session-d3aff1e9-bc8d-46bb-8bb9-82c24ec2095b

## 回答

我来写一个把驼峰命名转成下划线命名的函数。考虑到没指定语言，我用 Python 实现，并覆盖常见边界情况（连续大写如 `getHTTPResponse`、PascalCase 首字母大写等）。
文件已创建，我来运行验证一下结果是否正确。
已完成，所有用例验证通过。函数写在 `F:\deepseek\camel_to_snake.py`。

核心函数：

```python
import re

def camel_to_snake(name: str) -> str:
    if not name:
        return name
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)   # HTTPResponse -> HTTP_Response
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)     # getHTTP      -> get_HTTP
    return s2.strip("_").lower()
```

**两步正则的思路**：
1. `(.)([A-Z][a-z]+)` —— 把“任意字符 + 大写字母开头的小写串”拆开，处理缩写后面跟小写的边界，例如 `HTTPResponse → HTTP_Response`、`XMLParser → XML_Parser`。
2. `([a-z0-9])([A-Z])` —— 在“小写/数字”与“大写”之间补下划线，处理普通驼峰边界，例如 `getHTTP → get_HTTP`、`camelCase → camel_Case`。

最后去掉首尾多余下划线并转小写。

**覆盖的边界情况**（均已跑通）：
| 输入 | 输出 |
|---|---|
| `camelCase` | `camel_case` |
| `PascalCase` | `pascal_case` |
| `getHTTPResponse` | `get_http_response` |
| `XMLParser` | `xml_parser` |
| `parseXMLElement` | `parse_xml_element` |
| `already_snake` | `already_snake`（已下划线，保持不变） |
| `userID123` | `user_id123`（数字边界） |
| `""` | `""`（空串安全） |

如果你需要的是别的语言版本（JavaScript/TypeScript、Go、Java 等），或希望用纯字符遍历而不是正则的实现，告诉我即可。
