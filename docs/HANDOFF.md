# TeachX 开发交接文档

> 最后更新：2026-10-02
>
> 功能基线：`07e5a1a`；接手时使用 `git log -1` 查看最新提交。
> 用途：新的 Codex Agent、开发者或贡献者恢复项目上下文，并直接继续开发。

## 给下一个 Agent 的第一条指令

可以把下面这段直接发给新的 Codex 对话：

```text
请先完整阅读 docs/HANDOFF.md、docs/roadmap.md、docs/architecture.md、
README.md、docs/tutorials/README.md 和 docs/documentation-guide.md。

这是一个持续开发中的真实项目，不要从零重做，也不要删除本地数据。
先检查 git status、最近提交和当前验证结果，然后从 HANDOFF 的“下一步优先级”继续。

开发规则：
- 普通用户体验优先。
- 管理员功能、Docker、PostgreSQL 暂缓。
- 自动测试必须使用 Mock，不能消耗真实 API 额度。
- 完成大型功能后补中文教程、更新 README/roadmap、浏览器验证、commit、push。
- 不要输出、提交或写入文档任何 API Key / Auth Secret。
```

## 项目目标

TeachX 是一个 Web 优先的 AI 学习平台：

- 浏览器聊天与流式回答。
- Agent Loop 和工具调用。
- 用户知识库、RAG 和来源引用。
- 学习档案、个性化提示词和目标进度。
- 回答反馈、错题、练习与复习。
- 用户可连接 DeepSeek、OpenAI 或其他 OpenAI 兼容平台。

项目定位是真实可演示、可解释、可继续扩展的作品集和课程项目，不是一次性 API 封装。

当前明确暂缓：

- 管理员用户管理。
- Docker 实机构建。
- PostgreSQL 迁移。
- 复杂插件市场。

## 当前完成度

截至 `07e5a1a`：

- P0 Web 垂直切片：完成。
- P1 流式 Agent Runtime：核心完成，DeepSeek Flash 已真实验证。
- P2 知识库、FTS5、Embedding 接口和 RRF：代码完成，Embedding 仍主要使用 Mock。
- P3 认证、用户隔离、个人资料：完成基础阶段。
- U1 学习档案注入提示词：完成。
- U2 聊天页个性化状态：完成。
- U3 首次使用引导：完成。
- U4 学习反馈与错题记录：完成。
- U5 练习与复习模式：完成。
- U6 对话中的学习目标：完成。
- 用户级模型连接：完成。
- DeepSeek Flash：真实 `/models`、流式文本、工具调用、浏览器聊天已验证。
- Agent 费用控制：完成，包含真实/估算 usage、输出与上下文上限、日预算和错误事件。

后端自动测试当前为 `38 passed`。前端生产构建为 `47` 条路由。

当前下一步是 **Q2：工具调用重试、幂等和多工具策略**。

## 最近提交

```text
07e5a1a feat: add token usage and daily budget controls
483dddb docs: add model connection tutorial
17c516c feat: add user model connections
5484b10 docs: add learning goal tutorial
a5e12d9 feat: track learning goals in chat
c38dbe1 docs: add practice and review tutorial
f682cc1 feat: add knowledge-base practice and review
143f40a docs: add learning feedback tutorial
2c1f302 feat: add learning feedback and mistake records
163da1b docs: add first-run onboarding guide
abed83c feat: add first-run onboarding
```

## 本地环境与敏感文件

### `backend/.env`

该文件被 Git 忽略，本地目前包含真实配置：

```text
TEACHX_LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com/v1
TEACHX_MODEL=deepseek-flash
TEACHX_EMBEDDING_PROVIDER=mock
TEACHX_AUTH_ENABLED=true
TEACHX_AUTH_COOKIE_SECURE=false
```

本地费用控制当前使用默认值；`TEACHX_DAILY_TOKEN_BUDGET=0` 表示关闭日预算，
`TEACHX_GENERATE_TITLES=false` 表示不额外调用模型生成标题。

同时包含：

- DeepSeek API Key。
- 本地认证 Secret。

不要把任何值打印到终端、聊天、README、HANDOFF 或提交中。修改 `TEACHX_AUTH_SECRET`
会导致已保存的用户模型连接无法解密，用户必须重新填写 Key。

### 本地演示账号

演示账号存放在被 Git 忽略的文件：

```text
data/DEMO_ACCESS.txt
```

不要再把账号密码写进已跟踪文档。当前本地数据库包含：

- 6 个演示会话。
- 2 个知识库。
- 5 份知识库文档。
- 3 条反馈/误区记录。
- 5 道练习题。
- 3 次练习作答和掌握度。
- 1 个已激活的 DeepSeek Flash 用户连接。

重置前旧数据备份在：

```text
/tmp/teachx-reset-20261002-010800
```

`data/*` 已被 Git 忽略。不要在没有用户确认时删除 `data/teachx.db` 或知识库原文。

## 一键启动

正常本地运行：

```bash
./scripts/dev.sh
```

访问：

```text
前端：http://localhost:3000
后端：http://127.0.0.1:8010
```

当前本地 `.env` 会启用认证并使用 DeepSeek Flash。若只需要开发和界面测试，优先使用
Mock，避免产生费用：

```bash
TEACHX_LLM_PROVIDER=mock \
TEACHX_EMBEDDING_PROVIDER=mock \
TEACHX_DATABASE_PATH=/tmp/teachx-mock.db \
TEACHX_KNOWLEDGE_ROOT=/tmp/teachx-mock-knowledge \
./scripts/dev.sh
```

也可以分别启动：

```bash
cd backend
uv sync
uv run uvicorn teachx.main:app --app-dir src --reload --port 8010
```

```bash
cd frontend
npm ci
npm run dev
```

## 验证命令

项目标准检查：

```bash
./scripts/check.sh
```

它会执行：

- Ruff。
- 后端 pytest。
- 前端 TypeScript 检查。

`check.sh` 强制：

```text
TEACHX_LLM_PROVIDER=mock
TEACHX_EMBEDDING_PROVIDER=mock
```

这样本地 `.env` 即使用真实付费模型，自动测试也不会消耗 API 额度。不要移除这两个覆盖。

完整验证：

```bash
cd frontend
npm run architecture:check
npm run i18n:parity
npm run i18n:audit
npm run build
```

当前预期：

```text
38 passed
typecheck passed
47 Next.js routes built
```

## 核心架构链路

### 聊天

```text
Next.js Chat UI
→ /ws
→ FastAPI WebSocket
→ 选择当前用户激活的模型连接
→ OpenAICompatibleProvider 或平台默认 Provider
→ AgentRuntime
→ UsageService 记录 token 和检查日预算
→ ToolRegistry
→ SessionRepository
```

### 个性化

```text
用户学习档案
→ AgentRuntime 每回合读取
→ active 学习目标、进度、讲解风格进入系统提示词
→ 已完成目标不注入
→ done.personalization_applied
```

### 知识库

```text
上传
→ 提取
→ 切块
→ FTS5 + Embedding
→ RRF 混合排序
→ knowledge_search
→ sources 事件
```

### 练习

```text
知识库文本片段
→ practice_questions
→ 用户开放题作答
→ Again / Hard / Good / Easy
→ practice_attempts + practice_progress
→ 1 / 2 / 4 / 7 天后复习
```

### 模型连接

```text
用户 Base URL + API Key + 默认模型
→ Fernet 加密
→ model_connections
→ WebSocket 每回合读取 active 连接
→ 临时创建 OpenAICompatibleProvider
→ 传入 AgentRuntime.run_turn(provider=...)
```

没有个人 active 连接时，回退到 `.env` 平台默认 Provider。

## 关键代码文件

### 后端

| 文件 | 职责 |
| --- | --- |
| `backend/src/teachx/main.py` | 应用装配、数据库、Auth、Knowledge、Practice、ModelConnection、Runtime |
| `backend/src/teachx/runtime/engine.py` | Agent Loop、工具循环、Provider 覆盖、个性化、标题 |
| `backend/src/teachx/runtime/prompts.py` | 系统提示词、学习档案和目标注入 |
| `backend/src/teachx/runtime/tools.py` | 工具注册、计算器、知识检索 |
| `backend/src/teachx/providers/openai_compat.py` | OpenAI 兼容流式和工具参数拼接 |
| `backend/src/teachx/usage/service.py` | token 用量持久化、按日预算统计和本地用户映射 |
| `backend/src/teachx/storage/database.py` | SQLite schema 与迁移 |
| `backend/src/teachx/storage/repository.py` | 会话、消息、反馈和事件持久化 |
| `backend/src/teachx/auth/service.py` | 用户、JWT、学习档案 |
| `backend/src/teachx/knowledge/service.py` | 知识库提取、索引、权限和混合检索 |
| `backend/src/teachx/practice/service.py` | 出题、复习队列、掌握度 |
| `backend/src/teachx/model_connections/service.py` | 用户连接、Key 加密、Provider 创建 |

### 路由

```text
backend/src/teachx/api/routes/auth.py
backend/src/teachx/api/routes/profile.py
backend/src/teachx/api/routes/ws.py
backend/src/teachx/api/routes/sessions.py
backend/src/teachx/api/routes/knowledge.py
backend/src/teachx/api/routes/learning.py
backend/src/teachx/api/routes/practice.py
backend/src/teachx/api/routes/model_connections.py
```

### 前端

| 文件 | 职责 |
| --- | --- |
| `frontend/features/chat/components/ChatWorkspace.tsx` | 聊天主装配和状态条 |
| `frontend/features/chat/messages/ChatMessageList.tsx` | 消息、反馈操作和动作区 |
| `frontend/features/chat/ChatStateAdapter.tsx` | WebSocket 状态机 |
| `frontend/app/(auth)/onboarding/page.tsx` | 首次引导 |
| `frontend/app/(utility)/profile/page.tsx` | 资料、目标、进度和个性化 |
| `frontend/app/(utility)/learning-records/page.tsx` | 反馈与误区记录 |
| `frontend/app/(workspace)/practice/page.tsx` | 练习与复习 |
| `frontend/app/(utility)/model-connections/page.tsx` | 用户模型连接 |
| `frontend/components/sidebar/nav-entries.ts` | 导航入口 |

## 当前 API 概览

### 认证与引导

```text
GET    /api/auth/status
GET    /api/auth/is_first_user
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/onboarding
POST   /api/auth/onboarding/complete
```

### 资料与个性化

```text
GET    /api/auth/profile
PUT    /api/auth/profile
GET    /api/auth/personalization
GET    /api/auth/profile/learner-profile
PUT    /api/auth/profile/learner-profile
PUT    /api/auth/profile/avatar
DELETE /api/auth/profile/avatar
GET    /api/auth/avatar/{user_id}
```

### 学习记录

```text
GET    /api/learning/feedback?session_id={session_id}
GET    /api/learning/records
PUT    /api/learning/feedback/{message_id}
DELETE /api/learning/records/{feedback_id}
```

### 练习

```text
GET    /api/practice/summary
GET    /api/practice/knowledge-bases
GET    /api/practice/queue
POST   /api/practice/generate
POST   /api/practice/questions/{question_id}/answer
DELETE /api/practice/questions/{question_id}
```

### 模型连接

```text
GET    /api/model-connections
POST   /api/model-connections
POST   /api/model-connections/test
POST   /api/model-connections/default/activate
POST   /api/model-connections/{connection_id}/activate
DELETE /api/model-connections/{connection_id}
```

## 数据库所有权

```text
sessions.user_id
knowledge_bases.owner_id
answer_feedback.user_id
practice_questions.user_id
practice_attempts.user_id
practice_progress.user_id
model_connections.user_id
```

用户数据必须始终遵守这些边界。管理员跨用户能力目前只应用于已存在的资源查询路径，
新增接口不要默认给普通用户开放全量数据。

## 当前主要表

```text
users
sessions
messages
knowledge_bases
knowledge_documents
knowledge_chunks
knowledge_chunks_fts
knowledge_chunk_vectors
answer_feedback
practice_questions
practice_attempts
practice_progress
model_connections
llm_usage
```

用户档案关键字段：

```text
users.avatar
users.learner_profile
users.personalization_enabled
users.onboarding_completed
users.learner_profile.learning_goal
users.learner_profile.learning_goal_progress
users.learner_profile.learning_goal_status
```

## 已完成功能的使用路径

### 新用户

```text
/register
→ 自动登录
→ /onboarding
→ 学习阶段、目标、讲解偏好、可选资料
→ /chat
```

### 个性化与目标

```text
/chat
→ 顶部显示个性化状态
→ 显示当前学习目标、进度
→ 可完成目标
→ /profile 调整目标、进度和状态
```

### 反馈与误区

```text
/chat 回答下方
→ 有帮助 / 不清楚 / 记录我的误区
→ /learning-records 查看、筛选、删除
→ 再弄懂一次，将误区写入 /chat 草稿
```

### 练习

```text
/practice
→ 选择知识库
→ 生成开放题
→ 作答
→ Again / Hard / Good / Easy
→ 更新掌握度和下次复习
```

### 模型连接

```text
/model-connections
→ DeepSeek / OpenAI / 自定义 OpenAI 兼容平台
→ 测试连接和模型列表
→ 保存并激活
→ 后续 WebSocket 回合使用该用户模型
```

## 已完成的真实联调

DeepSeek 控制台返回：

```text
deepseek-flash
deepseek-v4-pro
```

已验证：

- `/models` 正常。
- DeepSeek Flash 流式文本正常。
- calculator 工具调用正常，参数为 `{"expression": "19 * 23"}`。
- 浏览器保存并激活个人连接后，真实聊天成功。
- API 响应不返回用户明文或密文 Key。

当前仍没有验证：

- 真实 Embedding 供应商和混合检索。
- 不同 OpenAI 兼容平台的所有错误格式。
- 网络断开、超时、限流和部分流中断。

## 下一步优先级

### P0：Agent 稳定性剩余项

费用控制已完成，当前下一步是：

1. 为工具调用增加重试和幂等保护。
2. 设计多工具并行执行和结果顺序。
3. 对敏感工具参数做脱敏后再进入事件和日志。
4. 为最大回合数、超时和断线恢复提供更明确的用户提示。

按 E1～E5 顺序推进，详细交付、验收和依赖见
`docs/roadmap.md` 的“近期执行计划”。

验收要求：

- 不重复执行有副作用的工具。
- 多工具结果顺序可解释。
- 敏感参数不会出现在前端事件或持久化日志。
- 自动测试继续强制 Mock。

### P1：真实 Embedding

- 使用支持 Embeddings 的平台进行真实联调。
- 验证维度、失败回退和模型升级后的 reindex。
- 保持 DeepSeek Chat 与 Embedding 配置相互独立。

### P2：Q3 测试

- 前端关键页面测试。
- API 合同测试。
- 覆盖率报告。
- 真实边界场景的确定性 Mock 测试。

### P3：Q4 展示材料

- 截图和演示视频。
- 在线演示。
- 架构图、时序图。
- 简历项目描述和面试问答。

## 已知限制与坑

- 新用户首次注册自动登录，第一用户是管理员。
- 旧用户 `onboarding_completed` 迁移默认已完成；新用户明确写为未完成。
- 学习目标修改文字时自动 active，完成状态不会被旧值覆盖。
- 已完成学习目标不进入提示词，但其他档案字段继续存在。
- 知识库名称目前全局唯一，不同用户不能创建同名知识库。
- 原 DeepTutor 前端仍有大量非当前主线的页面，只保证 HANDOFF 中列出的路径完成验证。
- 旧的 `/learning/practice` 页面保留兼容；新的普通用户练习入口是 `/practice`。
- 模型连接只用于聊天 Provider，不用于 Embedding。
- `TEACHX_AUTH_SECRET` 变化会使已有用户模型 Key 无法解密。
- 日预算默认关闭；真实模型测试仍应少打、短问，优先使用 Mock。
- usage 依赖供应商返回值；缺失时 TeachX 会估算并标记 `estimated`。
- Docker、PostgreSQL 和管理员用户管理不是当前阻塞项。

## 开发规则

每个大型功能必须完成：

```text
明确用户场景
→ 代码
→ 自动测试
→ 浏览器或 API 验证
→ 中文教程
→ 更新 README（影响用户时）
→ 更新 docs/roadmap.md
→ commit
→ push
```

每次任务结束前都要做文档判定。新功能必须补中文教程，小修复至少检查现有文档
是否失真。面向基础一般的读者写作，术语要解释，命令要有预期结果；详细规则见
`docs/documentation-guide.md`。

不要：

- 在没有验证的情况下声称真实模型或线上环境完成。
- 在自动测试中读取本地真实 API Key。
- 输出或提交任何 Secret。
- 重写已经稳定的 Agent Loop。
- 删除用户本地数据库或知识库原文。
- 继续投入 Docker 或管理员功能，除非用户明确恢复。

## Git 和提交规范

每个大型功能至少分两类提交：

```text
feat: 功能代码、测试、迁移
docs: 教程、README、交接和路线图
```

推送前至少执行：

```bash
./scripts/check.sh
git diff --check
git status --short
```

前端路由或依赖发生变化时再执行：

```bash
cd frontend
npm run architecture:check
npm run i18n:parity
npm run i18n:audit
npm run build
```

## 最新上手动作

新 Agent 接手后的最短路径：

```bash
git status --short --branch
git log --oneline -12
cat docs/HANDOFF.md
cat docs/roadmap.md
./scripts/check.sh
```

然后：

1. 如果任务是 Agent 稳定性，从“P0：Agent 稳定性剩余项”开始。
2. 如果任务是展示材料，从“P3：Q4 展示材料”开始。
3. 如果不确定，先向用户确认优先级，不要默认重做已完成功能。

## 新对话推荐开场语

```text
你正在接手 TeachX。请先阅读 docs/HANDOFF.md、docs/roadmap.md、
docs/architecture.md、README.md、docs/tutorials/README.md 和
docs/documentation-guide.md。

不要从零重做，不要删除本地数据或 Secret，不要让自动测试调用真实模型。
先检查 git status、最近提交和 ./scripts/check.sh，然后从当前最高优先级继续。

每次任务结束前都要做文档判定。新功能必须补适合基础读者的中文教程、更新
README/roadmap、浏览器验证、commit、push。
```
