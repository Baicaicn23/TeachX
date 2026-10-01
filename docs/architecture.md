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
- `auth`：用户、密码哈希和 JWT 服务。
- `runtime`：Agent Loop、能力模式和工具系统。
- `providers`：Mock 与 OpenAI 兼容模型适配器。
- `knowledge`：文档提取、切块、索引和检索。
- `storage`：会话、消息和回合事件的持久化。

## Agent Loop

一次回合不是简单地调用一次模型，而是：

1. 组装系统提示词和历史消息。
2. 调用模型。
3. 如果模型请求工具，执行工具并追加 `tool` 消息。
4. 继续调用模型，直到得到最终回答或达到最大轮数。
5. 保存用户消息、助手消息和完整事件。

## 知识库链路

```text
上传文件
→ extractors 提取纯文本
→ chunker 切分片段
→ KnowledgeService 写入 SQLite
→ FTS5 建立全文索引
→ Embedding 建立向量索引
→ FTS 与向量使用 RRF 混合排序
→ knowledge_search 执行检索
→ sources 事件返回引用
```

知识库原文保存在 `data/knowledge/`，不进入 Git。数据库保存文档元数据、提取文本、可搜索文本块和向量。
Mock Embedding 用于本地开发，真实环境可切换 OpenAI 兼容 Embeddings API。

## Provider 接口

所有 Provider 提供两个入口：

- `complete()`：一次性返回完整结果，适合标题生成等短任务。
- `stream()`：逐段产生内容，适合用户可见的正常回答。

OpenAI 兼容 Provider 会累计流式工具参数。因为真实模型可能把
`{"expression": "2 + 3"}` 拆成多个片段发送，不能假设参数一次到齐。

## 认证边界

```text
注册/登录
→ bcrypt 验证密码
→ 签发 JWT
→ 写入 HttpOnly Cookie
→ HTTP 依赖与 WebSocket 握手验证
→ 会话按 user_id 隔离
```

认证关闭时返回本地开发用户，保持单用户模式。认证开启时，受保护接口和
WebSocket 都必须在后端验证 Cookie，不能依赖前端路由隐藏。

会话使用 `user_id` 隔离；知识库使用 `owner_id` 隔离。普通用户只能访问自己的
数据，管理员可以访问全部资源。HTTP 路由、文件下载和 Agent 工具调用必须使用
相同的所有权规则。

## 容器部署

```text
Browser
→ web 容器（Next.js standalone）
→ api 容器（FastAPI）
→ teachx-data Volume
```

Compose 通过服务名 `api` 提供容器网络发现。SQLite 数据库和知识库原文保存在
`/app/data`，通过命名 Volume 持久化。

## 设计规则

- WebSocket 协议是前端与后端之间的稳定产品接缝。
- 工具只声明一次，通过 Tool Registry 统一执行。
- 持久化层负责消息历史和回放，不把 SQL 写进 Agent Loop。
- 能力提示词独立于传输层和存储层，并带有版本号。
- 更换模型、数据库或部署方式时，应替换适配器，而不是修改全部业务代码。
