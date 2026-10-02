# 18：Agent 费用控制与 Provider 稳定性

这一章解决的问题很实际：真实模型可以完成任务，但如果每一轮都无限携带历史消息、
工具长结果和额外标题调用，费用会变得不可预测。本章说明 TeachX 如何记录 token、
限制上下文、设置每日预算，并把供应商错误转换成前端能理解的失败事件。

## 用户场景

一个用户连接了真实 DeepSeek、OpenAI 或其他 OpenAI 兼容模型。

他希望：

1. 回答完成后能看到本轮用了多少 token。
2. 能看到当前会话累计用了多少 token。
3. 出错时知道是超时、限流、服务端错误还是流中断。
4. 设置每日预算后，不会因为忘记关闭页面而无限产生费用。

## 一次真实调用现在发生什么

```text
WebSocket start_turn
→ AgentRuntime 检查今日预算
→ 读取并裁剪历史消息
→ Provider 流式调用模型
→ OpenAI 兼容接口返回 usage
→ UsageService 写入 llm_usage
→ 聚合本回合 usage_summary
→ result / done 事件返回 token 与预算状态
→ 前端 UsageFooter 显示本轮和会话累计
```

整个 Agent Loop 没有被重写。新增逻辑只在每次模型调用结束后记录用量，并在下一轮
调用前检查预算。

## 1. Provider 返回结构化 usage

原来的 `LLMResult` 只有内容和工具调用：

```python
LLMResult(
    content="",
    tool_calls=[],
    finish_reason="stop",
)
```

现在增加可选 `usage`：

```python
LLMUsage(
    prompt_tokens=120,
    completion_tokens=35,
    total_tokens=155,
    estimated=False,
)
```

OpenAI 兼容流式接口会尽量请求 `stream_options.include_usage`。如果某个兼容平台不
支持这个参数，TeachX 会自动去掉该参数重试；供应商仍没有返回 usage 时，会按文本
长度进行明确标记的估算，而不是假装数据是真实值。

关键文件：

- `backend/src/teachx/providers/base.py`
- `backend/src/teachx/providers/openai_compat.py`

## 2. usage 持久化在哪里

每次模型调用都会写入 `llm_usage` 表：

```text
user_id
session_id
turn_id
call_kind
provider
model
prompt_tokens
completion_tokens
total_tokens
estimated
billable
created_at
```

这样即使用户稍后刷新浏览器，助手消息里的 `result` 和 `done` 事件仍然带有
`usage_summary`，前端不需要重新调用模型就能恢复用量展示。

日预算只统计 `billable = 1` 的调用。Mock 和超预算后的 Mock 回退仍会记录估算
usage，但不会占用真实费用预算。

## 3. 输出上限与上下文裁剪

新增配置：

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| `TEACHX_MAX_OUTPUT_TOKENS` | `1024` | 传给 Provider 的 `max_tokens` 上限 |
| `TEACHX_MAX_HISTORY_MESSAGES` | `24` | 最多带入的历史消息数，`0` 表示不按数量限制 |
| `TEACHX_MAX_HISTORY_CHARS` | `16000` | 历史消息总字符预算，`0` 表示不按字符限制 |
| `TEACHX_MAX_TOOL_RESULT_CHARS` | `6000` | 工具结果进入下一轮提示词前的最大字符数 |

历史消息从最近一条开始保留，避免旧对话挤掉当前问题。裁剪后如果第一条是助手消息，
会继续丢弃它，保证上下文从用户问题开始。

工具结果过长时会截断，并在事件 metadata 中记录：

```json
{
  "context_truncated": true
}
```

完整工具结果仍可能出现在工具自身的来源 metadata 中；被限制的是再次发送给模型的
上下文长度。

## 4. 会话标题默认本地生成

新会话第一轮过去会额外调用一次模型生成标题。这个调用虽然短，但也会产生 token。

现在默认：

```text
TEACHX_GENERATE_TITLES=false
```

标题直接使用用户问题截断结果。需要模型生成标题时显式开启：

```text
TEACHX_GENERATE_TITLES=true
```

开启后标题调用也有独立的 `max_tokens=64` 上限，并计入本回合 usage。

## 5. 每日 token 预算

配置示例：

```bash
TEACHX_DAILY_TOKEN_BUDGET=100000
TEACHX_BUDGET_EXCEEDED_ACTION=block
```

`TEACHX_DAILY_TOKEN_BUDGET=0` 表示不限制。

超预算有两种行为：

### block

```text
TEACHX_BUDGET_EXCEEDED_ACTION=block
```

下一轮不调用真实模型，返回：

```text
error_code = daily_budget_exceeded
retryable = false
```

用户会看到明确提示，不能误以为真实模型仍然执行过。

### mock

```text
TEACHX_BUDGET_EXCEEDED_ACTION=mock
```

真实调用被替换为本地 Mock，回答仍可继续，但 `done` 事件会携带：

```text
budget_fallback = true
```

这种方式适合课堂演示，不适合需要严格确认真实模型输出的场景。

## 6. 前端用量面板

助手回答完成后，底部会显示类似：

```text
116 tokens · 缓存命中率 — · 每日 token 预算 0/10万
```

点击后可以选择：

- 本轮对话。
- 当前会话累计。
- 输入 token、输出 token、推理 token。
- 缓存读取与缓存命中率。
- 模型用时、TTFT 和 TPS。
- 每日预算已用、剩余和状态。

当前会话累计是按可见对话分支逐条助手消息累加的，不会把后续回答错误地算进较早
回答里。

## 7. Provider 错误映射

前端不需要理解各家 SDK 的异常类型。Provider 会转换成稳定错误：

| 场景 | `error_code` | 可重试 |
| --- | --- | --- |
| 请求超时 | `provider_timeout` | 是 |
| 429 限流 | `rate_limited` | 是 |
| 5xx 服务端错误 | `provider_server_error` | 是 |
| 其他 HTTP 状态 | `provider_http_error` | 按状态码判断 |
| 连接失败 | `provider_connection_error` | 是 |
| 流提前中断 | `provider_stream_error` | 是 |

错误事件同时包含 `retryable` 和可用的 `provider_status_code`，前端会据此决定是否
展示重试入口。

## 8. 自动测试如何保持免费

`scripts/check.sh` 强制：

```text
TEACHX_LLM_PROVIDER=mock
TEACHX_EMBEDDING_PROVIDER=mock
TEACHX_AUTH_ENABLED=false
```

认证隔离是必要的，因为本地 `backend/.env` 会开启登录，而通用 API 测试必须在
确定、无 Cookie 的环境中运行。

费用控制测试覆盖：

- 真实 usage 的聚合与持久化。
- 默认使用本地标题，不额外调用模型。
- 开启标题生成后，标题调用计入 usage。
- 超预算阻止真实调用。
- 超预算回退 Mock。
- Provider 超时的稳定失败事件。
- 历史消息和工具结果裁剪。

## 9. 浏览器验收记录

使用隔离的 Mock 数据库和 `TEACHX_DAILY_TOKEN_BUDGET=100000` 启动后，实际浏览器
发送一条消息：

```text
最终验证用量面板 ...
→ 116 tokens
→ 每日 token 预算 0/10万
→ 详情：0 / 100,000
→ 剩余预算：100,000
→ 预算状态：可用
```

关闭浏览器后重新打开历史会话，用量面板仍然存在，证明 `result` / `done` 事件已经
持久化，而不是只在当前 WebSocket 连接中可见。

## 当前边界

- usage 依赖供应商返回值；供应商不返回时只能估算，并会标记 `estimated`。
- 日预算按 TeachX 服务所在时区的自然日统计。
- 预算不是供应商账单的精确定价，不包含不同平台的价格和缓存折扣。
- 单个回合可以在最后一次已开始的调用中略微超过预算，下一次调用会被阻止。
- 工具调用重试、多工具并发和断线恢复仍属于后续稳定性工作。

## 自测题

1. 为什么预算只统计 `billable = 1` 的记录？
2. 供应商不支持 `stream_options` 时，TeachX 如何继续获取 usage？
3. 为什么标题生成默认关闭更符合费用控制目标？
4. `TEACHX_MAX_HISTORY_CHARS` 限制的是数据库大小还是发送给模型的上下文？
5. 为什么 `done` 事件也要写入助手消息的 `events`？
