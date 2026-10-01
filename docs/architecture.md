# TeachX 系统架构

## 产品边界

TeachX 明确采用 Web 优先设计，浏览器是第一版唯一支持的客户端。
第一阶段围绕四个产品方向建设：

1. 带流式 Agent 输出的聊天。
2. 解题、出题等可复用能力模式。
3. 基于知识库的检索和回答。
4. 模型与学习偏好设置。

## 运行时路径

```text
Next.js Web 界面
  -> /ws 统一回合协议
  -> AgentRuntime
  -> Provider Adapter
  -> Tool Registry
  -> Session Repository
```

## 后端模块

- `api`：HTTP 与 WebSocket 适配层。
- `runtime`：Agent Loop、能力模式和工具系统。
- `providers`：Mock 与 OpenAI 兼容模型适配器。
- `storage`：会话、消息和回合事件的持久化。

## Agent Loop

一次回合不是简单地调用一次模型，而是：

1. 组装系统提示词和历史消息。
2. 调用模型。
3. 如果模型请求工具，执行工具并追加 `tool` 消息。
4. 继续调用模型，直到得到最终回答或达到最大轮数。
5. 保存用户消息、助手消息和完整事件。

## Provider 接口

所有 Provider 提供两个入口：

- `complete()`：一次性返回完整结果，适合标题生成等短任务。
- `stream()`：逐段产生内容，适合用户可见的正常回答。

OpenAI 兼容 Provider 会累计流式工具参数。因为真实模型可能把
`{"expression": "2 + 3"}` 拆成多个片段发送，不能假设参数一次到齐。

## 设计规则

- WebSocket 协议是前端与后端之间的稳定产品接缝。
- 工具只声明一次，通过 Tool Registry 统一执行。
- 持久化层负责消息历史和回放，不把 SQL 写进 Agent Loop。
- 能力提示词独立于传输层和存储层，并带有版本号。
- 更换模型、数据库或部署方式时，应替换适配器，而不是修改全部业务代码。
