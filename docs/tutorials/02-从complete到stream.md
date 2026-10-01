# 02：从 `complete` 到 `stream`

## 这篇讲什么

P1 阶段最重要的代码变化，是模型调用从“等完整答案”升级为“边生成边发送”。

改造前后对比：

```text
改造前：请求 → 等待很久 → 一次性得到完整答案
改造后：请求 → 收到片段 → 收到片段 → 收到片段 → 结束
```

## 先认识同步、异步和阻塞

普通函数：

```python
def hello():
    return "hello"
```

调用后立即返回结果。

异步函数：

```python
async def hello():
    return "hello"
```

调用异步函数会得到一个协程对象。必须使用 `await` 才能真正执行：

```python
result = await hello()
```

模型请求需要等待网络，属于典型 I/O 操作。异步可以让服务器在等待模型时继续处理
其他请求。

## 为什么流式输出还需要“迭代器”

一个回答不是一次产生，而是很多片段：

```text
"你" + "好" + "，我" + "来" + "解释"
```

异步迭代器允许我们用 `async for` 逐个读取：

```python
async for event in provider.stream(messages, tools):
    ...
```

同步列表使用 `for`，异步数据流使用 `async for`。

## 两种流事件

在：

```text
backend/src/teachx/providers/base.py
```

定义了两个事件对象：

```python
@dataclass
class ContentDelta:
    content: str

@dataclass
class StreamFinished:
    result: LLMResult
```

- `ContentDelta`：模型刚生成了一小段文字。
- `StreamFinished`：流结束，并携带完整文本和工具调用。

用“快递”类比：`ContentDelta` 是不断送来的包裹，`StreamFinished` 是本次
配送的签收单。

## Provider 接口的职责

所有模型适配器都继承 `BaseProvider`，必须实现：

```python
async def complete(messages, tools) -> LLMResult:
    ...
```

同时可以覆盖：

```python
async def stream(messages, tools):
    ...
```

`complete()` 用于不需要流式的短任务，例如生成会话标题。
`stream()` 用于正常聊天回合。

## MockProvider 如何模拟流

MockProvider 先在 `complete()` 中计算完整回答，然后把它切成小块：

```python
result = await self.complete(messages, tools)

for chunk in self._chunks(result.content):
    yield ContentDelta(chunk)

yield StreamFinished(result)
```

这里的 `yield` 会让函数变成异步生成器。它不是一次返回列表，而是每次产生一个值，
等待消费者读取下一个值。

## OpenAI 真实流式实现

OpenAI 兼容接口返回的片段不是完整答案，而可能是：

```text
第 1 个 chunk：content = "我先"
第 2 个 chunk：tool_call.arguments = '{"expression":'
第 3 个 chunk：content = "计算。"
第 4 个 chunk：tool_call.arguments = '"2 + 3"}'
```

工具参数可能被拆成多段，因此 Provider 内部维护缓冲区：

```python
tool_buffers = {}

for tool_delta in delta.tool_calls:
    buffer = tool_buffers.setdefault(index, {...})
    buffer["arguments"] += tool_delta.arguments
```

流结束后再把 JSON 字符串解析成 Python 字典。

## AgentRuntime 如何消费流

在 `runtime/engine.py` 中：

```python
async for item in self.provider.stream(messages, tool_schemas):
    if isinstance(item, ContentDelta):
        发送 content 事件

    elif isinstance(item, StreamFinished):
        result = item.result
```

`isinstance()` 用来判断当前对象属于哪种类型。不同类型走不同处理逻辑。

## 为什么不能只使用真实流、不保留 complete

标题生成、分类和简单判断这类任务不需要把结果逐字展示给用户。
如果也强制使用流，会增加复杂度。因此两个接口同时保留：

- `complete()`：适合短任务。
- `stream()`：适合面向用户的回答。

## 常见误区

### “`yield` 等于 `return`”

`return` 结束函数并返回一个值。
`yield` 暂停函数，产生一个值，等待下一次读取后再继续。

### “`async` 会自动让代码变快”

异步不会让单个计算变快。它的价值是等待网络时减少资源浪费。

### “工具参数一定一次到齐”

真实模型的参数可能分段到达，必须累计后再解析。

## 小练习

1. 把 MockProvider 的分片大小从 12 改成 3，观察前端效果。
2. 在 `ContentDelta` 中加入 `index` 字段，并在 Provider 中递增。
3. 写一个测试，断言所有 `ContentDelta` 拼接后等于最终文本。

## 自测题

1. `async def` 和普通 `def` 的调用方式有什么不同？
2. `ContentDelta` 与 `StreamFinished` 分别表示什么？
3. 为什么工具参数需要缓冲区？
4. `complete()` 为什么仍然需要保留？
