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

调用还会返回可选的 `LLMUsage`，包含 prompt、completion、total token 和耗时信息；
Provider 自身负责把超时、429、5xx、连接失败和流中断转换成稳定的 `ProviderError`。
`max_output_tokens` 由 Provider 适配层映射到对应请求参数，不进入 Agent Loop 的业务逻辑。

OpenAI 兼容 Provider 会累计流式工具参数。因为真实模型可能把
`{"expression": "2 + 3"}` 拆成多个片段发送，不能假设参数一次到齐。

## 费用与上下文预算

```text
AgentRuntime
→ 检查用户今日 billable token
→ 裁剪历史消息和工具结果
→ Provider 调用
→ UsageService 写入 llm_usage
→ usage_summary 写入助手消息事件
→ 前端显示本轮、会话累计和每日预算
```

每日预算按服务所在时区的自然日统计，只计算真实 Provider 调用。超限默认阻止后续
真实调用，也可以配置为回退 Mock；回退会在 `done` 事件中明确标记。自动测试始终
强制 Mock，不能读取本地真实 Key。

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

## 容器部署（暂缓）

```text
Browser
→ web 容器（Next.js standalone）
→ api 容器（FastAPI）
→ teachx-data Volume
```

Compose 通过服务名 `api` 提供容器网络发现。SQLite 数据库和知识库原文保存在
`/app/data`，通过命名 Volume 持久化。

## 持续集成

```text
Push / Pull Request
→ Backend lint + tests
→ Frontend typecheck + production build
→ Docker Compose build + smoke test
```

GitHub Actions 使用干净的 Ubuntu Runner，避免依赖开发者本机状态。

## 用户资料

账户资料保存用户名、角色、头像标记和创建时间。图片头像存放在
`data/avatars/`，数据库只保存版本标记。

学习档案使用 JSON 保存年龄、年级、课程体系、语言、阅读水平和讲解风格。
这些字段用于个性化提示词，不与其他普通用户共享。AgentRuntime 每回合读取最新档案，
压缩字段长度，并把档案标记为数据而非系统指令。关闭个性化后不注入档案。聊天页通过独立 PersonalizationStatus 组件展示状态，
但最终是否启用仍由后端每回合读取数据库决定。

首次使用引导使用独立的 `users.onboarding_completed` 状态，而不是用档案是否为空
推断。已有账号迁移时默认标记为完成，新注册账号明确标记为未完成；完成后引导状态
持久化。引导中的学习阶段、学习目标和讲解偏好仍写入同一份学习档案，可选资料写入
用户拥有的知识库，因此聊天、个性化提示词和知识检索继续复用原有数据边界。

回答反馈和误区保存在独立的 `answer_feedback` 表中，通过 `user_id`、`session_id`
和 `message_id` 关联用户、会话与导师回答。查询时从原消息读取问题和回答，不复制
聊天正文；更新使用用户和消息唯一约束，删除聊天时通过外键级联清理。学习记录页只
查询当前用户的数据，后续追问通过 workspace draft 回填聊天输入框，由用户确认后发送。

练习与复习由独立的 `PracticeService` 负责。`practice_questions` 保存从知识库文本
片段生成的开放题，`practice_attempts` 保存每次回答、自评、复习间隔和掌握度快照，
`practice_progress` 汇总用户在每个知识库上的掌握度。调度当前使用可解释的
Again / Hard / Good / Easy 固定间隔，后续可以在不改变用户、知识库和题目权限边界
的前提下替换为更复杂的复习算法。

学习目标继续保存在 `users.learner_profile` 中，额外使用 `learning_goal_progress`
和 `learning_goal_status` 表示进度与 active/completed 状态。AgentRuntime 每回合
读取最新档案：未完成目标会连同进度进入个性化提示词；已完成目标不再注入，但不会关闭
其他个性化字段。目标文字发生变化时，更新服务自动把目标恢复为 active，避免新目标
继承旧目标的完成状态。

用户级模型连接保存在 `model_connections` 中。每项连接包含 Base URL、默认模型和
Fernet 加密后的 API Key；HTTP 接口只返回是否存在凭据。WebSocket 在每回合开始时读取
当前用户激活的连接，创建 `OpenAICompatibleProvider` 并传入 AgentRuntime；没有个人
连接时回退到环境和 `.env` 配置的平台默认 Provider。Agent Loop、工具协议和会话存储
不感知供应商差异。

## 设计规则

- WebSocket 协议是前端与后端之间的稳定产品接缝。
- 工具只声明一次，通过 Tool Registry 统一执行。
- 持久化层负责消息历史和回放，不把 SQL 写进 Agent Loop。
- 能力提示词独立于传输层和存储层，并带有版本号。
- 更换模型、数据库或部署方式时，应替换适配器，而不是修改全部业务代码。
