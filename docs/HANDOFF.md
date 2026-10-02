# TeachX 开发交接文档

> 最后更新：2026-10-02
>
> 接手时使用 `git log -1` 查看当前真实提交；最后一个功能基线：`cfaab58`。
> 用途：新的 Codex Agent、开发者或贡献者恢复项目上下文，并直接继续开发。

## 给下一个 Agent 的第一条指令

可以把下面这段直接发给新的 Codex 对话：

```text
请先完整阅读 AGENTS.md、docs/HANDOFF.md、docs/roadmap.md、
docs/architecture.md、README.md、docs/tutorials/README.md、
docs/documentation-guide.md 和 docs/research/2026-AI岗位技术栈调研.md。

这是一个持续开发中的真实项目，不要从零重做，也不要删除本地数据。
先检查 git status、最近提交和当前验证结果，然后从 HANDOFF 的“下一步优先级”继续。
当前明确下一步是 E3：敏感工具参数脱敏；E1 和 E2 已经完成，不要重做。

开发规则：
- 普通用户体验优先。
- 管理员功能、Docker、PostgreSQL 暂缓。
- 自动测试必须使用 Mock，不能消耗真实 API 额度。
- 完成大型功能后补适合基础读者的中文教程、写清面试问答、更新
  README/roadmap/HANDOFF、做浏览器或 API 验证、commit、push。
- 不要输出、提交或写入文档任何 API Key / Auth Secret。
```

## 交接快照

截至最后一个功能基线 `cfaab58`：

```text
分支：main
工作区：应为 clean，并与 origin/main 同步
后端标准检查：55 passed
前端类型检查：通过
前端生产构建：47 routes
当前功能任务：E2 已完成（工具执行幂等保护）
下一步功能任务：E3 敏感工具参数脱敏
```

接手后不要先改代码。先运行 `git status --short --branch` 和
`./scripts/check.sh`，确认工作区没有被用户或其他 Agent 并行修改。

## 新 Agent 即刻执行顺序

```bash
git status --short --branch
git log --oneline -12
./scripts/check.sh
```

如果 `check.sh` 为 `55 passed` 且前端 typecheck 通过：

1. 阅读 `docs/roadmap.md` 的 E3。
2. 阅读 `backend/src/teachx/runtime/tools.py`、
   `backend/src/teachx/runtime/tool_executions.py` 和
   `backend/tests/test_tool_idempotency.py`。
3. 从“下一步优先级”中的 E3 继续开工。

如果 `check.sh` 失败，先判断失败属于当前代码回归还是“已知无关失败”。
已知无关失败见本文后面的“测试基线与已知失败”，不要在 E3 中顺手重写旧前端页面。

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

截至 `cfaab58`：

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
- 工具执行政策与重试：完成，包含临时/永久错误、超时、有限退避和尝试次数元数据。
- 工具执行幂等保护：完成，包含幂等键、执行记录、重复请求重放、并发保护和 stale 接管。

后端自动测试当前为 `55 passed`。前端生产构建为 `47` 条路由。

当前下一步是 **E3：敏感工具参数脱敏**。

## 最近提交

```text
cfaab58 feat: add tool execution idempotency protection
c64d6aa docs: strengthen agent handoff
7969d7e docs: add tool retry tutorial
502bbcd feat: add tool execution policies and retries
07e5a1a feat: add token usage and daily budget controls
483dddb docs: add model connection tutorial
17c516c feat: add user model connections
5484b10 docs: add learning goal tutorial
a5e12d9 feat: track learning goals in chat
c38dbe1 docs: add practice and review tutorial
f682cc1 feat: add knowledge-base practice and review
143f40a docs: add learning feedback tutorial
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

工具执行默认值：

```text
TEACHX_TOOL_MAX_ATTEMPTS=3
TEACHX_TOOL_TIMEOUT_SECONDS=30
TEACHX_TOOL_RETRY_BASE_DELAY_MS=200
TEACHX_TOOL_RETRY_MAX_DELAY_MS=2000
TEACHX_TOOL_IDEMPOTENCY_ENABLED=true
TEACHX_TOOL_EXECUTION_STALE_SECONDS=300
```

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

这样本地 `.env` 即使用真实付费模型，自动测试也不会消耗 API 额度。不要移除这些覆盖。

`check.sh` 同时强制：

```text
TEACHX_AUTH_ENABLED=false
```

这是必要的。本地真实 `.env` 会开启认证，通用 API 测试必须在无 Cookie 的确定性环境中
运行，不要让测试依赖本机登录状态。

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
55 passed
typecheck passed
47 Next.js routes built
```

## 测试基线与已知失败

这些结果已经在 `cfaab58` 代码基线上确认，方便新 Agent 区分回归与旧问题。

### 必须保持通过

```bash
./scripts/check.sh
# 55 passed + typecheck passed

cd frontend
npm run build
# 47 routes built

npm run test:unit -- --run tests/exploring-auto-fold.spec.tsx
# 1 passed
```

### 已知无关失败

以下失败不是 E1/E2 引入的，除非用户明确要求，否则不要让 E3 被它们拖偏：

1. `npm run check:fast`
   - `test:node` 的 `admin-user-batches.test.js` 尝试读取
     `deeptutor/api/routers/auth.py`，该旧路径在当前项目不存在。
2. `npm run test:unit`
   - 有 4 个旧测试仍期待 DeepTutor 品牌或旧侧边栏配置：
     `attachment-processing-status.spec.tsx`、`chat-streaming-status.spec.tsx`
     （2 个）和 `sidebar-defaults.spec.tsx`。
3. `npm run lint`
   - 当前仍有 2 个旧错误：
     `app/(utility)/model-connections/page.tsx` 的 Hook 调用规则问题；
     `features/chat/messages/AnswerFeedbackActions.tsx` 的 effect 同步 setState。
   - 另有大量 warning，不要在没有范围确认时做全仓清理。

新 Agent 在最终答复中要继续如实报告这些已知失败，不能声称整个前端检查全绿。

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
| `backend/src/teachx/runtime/tools.py` | 工具注册、计算器、知识检索、执行政策与幂等接缝 |
| `backend/src/teachx/runtime/tool_executions.py` | 幂等键计算、tool_executions 执行记录存储与重放 |
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

## E1 已完成：工具执行政策与重试

不要把 E1 当成未完成项重做。当前实现已经进入 `502bbcd`。

### 接口

```python
ToolPolicy(
    read_only=True,
    max_attempts=3,
    timeout_seconds=30.0,
    retry_base_delay_seconds=0.2,
    retry_max_delay_seconds=2.0,
)
```

工具可以只覆盖自己关心的字段，`None` 表示继承 `ToolExecutionDefaults`。

错误分类：

```text
ToolError             永久错误，不重试
ToolTransientError    临时错误，可以重试
ToolTimeoutError      单次执行超时，可以重试
```

### 当前行为

- `CalculatorTool`：`read_only=True`，最多一次，2 秒超时。
- `KnowledgeSearchTool`：`read_only=True`，最多三次，10 秒超时。
- SQLite `locked/busy/timeout/unable to open` 会转换成临时错误并重试。
- 未知异常默认永久失败（幂等保护上线后，这一保守策略继续保留）。
- `ToolRegistry.execute()` 负责超时、退避、错误分类和执行 metadata。
- `tool_result` 事件会携带 `attempt_count`、`retry_count`、`retry_delays_ms`、
  `duration_ms`、`error_code`、`retryable` 和 `timed_out`。

### 配置

```text
TEACHX_TOOL_MAX_ATTEMPTS=3
TEACHX_TOOL_TIMEOUT_SECONDS=30
TEACHX_TOOL_RETRY_BASE_DELAY_MS=200
TEACHX_TOOL_RETRY_MAX_DELAY_MS=2000
```

### 测试

```text
backend/tests/test_tool_reliability.py
```

覆盖临时失败重试、永久错误不重试、重试耗尽、超时、未知工具、Runtime 事件和
SQLite locked 自动重试。

### 教程

`docs/tutorials/19-工具执行政策与重试.md`

教程的 E1 部分包含 15 个面试问答；E2 幂等问答（第 16～23 题）已补充在同一文件。

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
tool_executions
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

## E2 已完成：工具执行幂等保护

不要把 E2 当成未完成项重做。当前实现已经进入 `cfaab58`。

### 接口

```python
ToolContext(session_id=..., user_id=..., is_admin=..., knowledge_bases=..., turn_id=...)
ToolRegistry.execute(name, arguments, context, call_id="...")
ToolExecutionStore(database, stale_seconds=300.0)
```

幂等键（`runtime/tool_executions.py::compute_idempotency_key`）：

```text
sha256(user_id | session_id | turn_id | call_id | tool_name | sha256(canonical_json(arguments)))
```

参数先做 canonical JSON（`sort_keys=True`、`separators=(",", ":")`）再取 SHA-256。
数据库只存参数 hash，不存原始参数。键包含 `user_id`，用户之间不共享执行记录。

### 数据库

```text
tool_executions 表（idempotency_key TEXT PRIMARY KEY）
索引：(user_id, created_at DESC)、(turn_id, call_id)
旧库由 Database.initialize() 的 CREATE TABLE IF NOT EXISTS 自动迁移。
```

### 当前行为

- `turn_id` 为空时（例如测试里直接调用 Registry）不启用幂等，保持 E1 行为。
- 执行前先 `INSERT OR IGNORE` 一条 `running` 记录；插入成功才执行工具。
- 插入冲突：completed 重放原结果；永久失败重放失败终态；可重试失败允许接管重新执行。
- `running` 记录短暂轮询等待（最多 5 秒），等不到返回
  `error_code = tool_execution_in_progress`。
- `running` 超过 `TEACHX_TOOL_EXECUTION_STALE_SECONDS` 视为可接管（崩溃恢复）。
- 重放结果保留原来的 `sources`、`success` 和业务 metadata，只追加去重标记。
- `tool_result` 事件新增 `deduplicated`、`replayed`、`execution_status`、
  `idempotency_key_hash`（前 16 位）。

### 配置

```text
TEACHX_TOOL_IDEMPOTENCY_ENABLED=true
TEACHX_TOOL_EXECUTION_STALE_SECONDS=300
```

### 测试

```text
backend/tests/test_tool_idempotency.py
```

10 个测试覆盖：首次执行并记录、重复调用重放且工具只执行一次、永久失败终态重放、
不同 turn/call 不误去重、跨用户不共享记录、并发重复只有一个执行权、Runtime 事件携带
dedup 元数据、旧库迁移建表、可重试失败接管、无 turn_id 不启用幂等。

### 真实验证

Mock 后端 + 真实 WebSocket 发送“请计算 7 * 9”：`tool_result` 事件携带
`execution_status = completed` 和 16 位 `idempotency_key_hash`；`tool_executions`
表出现 `calculator / completed / attempt_count = 1` 记录，原始参数未落库。

### 教程

教程 19（`docs/tutorials/19-工具执行政策与重试.md`）已扩展幂等章节和第 16～23 题
面试问答，覆盖 exactly-once/at-least-once、canonical JSON、唯一约束、并发、stale
恢复和“工具成功但写终态失败”等追问题。E3 完成后继续在该教程补充参数脱敏问答。

## 下一步优先级

当前顺序以 `docs/roadmap.md` 的“近期执行计划”为权威来源：

| 顺序 | 任务 | 状态 |
| --- | --- | --- |
| E1 | 工具执行政策、超时和有限重试 | 已完成 |
| E2 | 工具执行幂等保护 | 已完成 |
| E3 | 敏感工具参数脱敏 | 下一步 |
| E4 | 多工具执行策略和稳定结果顺序 | 等待 E3 |
| E5 | 整回合超时、最大轮数和断线提示 | 等待 E4 |
| E6 | Evaluation 与 Observability | E1～E5 后优先做 |
| E7 | Context Engineering 与 Memory | 计划中 |
| E8 | 真实 Embedding、Reranker 和检索评测 | 计划中 |
| E9 | MCP、Skills、权限沙箱和 HITL | 计划中 |
| E10 | Model Routing 与 Durable Workflow | 计划中 |
| E11 | 部署、Q3 测试和 Q4 展示 | 计划中 |

不要跳过 E3 直接做 E4 或 E6。E3 的参数脱敏要以 E2 的执行记录为落点：脱敏后的参数
进入事件、数据库和日志，幂等键继续使用原始参数的 hash，避免脱敏规则变化导致去重失效。

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
- 工具有有限重试和幂等执行记录；相同业务请求只产生一次副作用，但“执行成功后写终态
  失败”的窗口在 stale 接管时仍可能重复执行副作用，教程 19 有说明。
- 还没有固定评测数据集、离线回放、Recall@K/MRR、trace 和回归 dashboard。
- 还没有 MCP Client/Server、完整权限审批和沙箱执行。
- 还没有模型复杂度路由和可恢复的 durable workflow。
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

## 文档写作与面试学习要求

用户明确要求：接下来的大型功能采用“边开发、边写技术文档”的方式，文档不仅要能运行，
还要帮助他理解并回答面试问题。

每篇新功能教程至少包含：

1. 用户场景和最终结果。
2. 前置知识和术语解释。
3. 可执行步骤与预期输出。
4. 核心数据流和代码路径。
5. 常见错误与排障。
6. 自动测试和真实验证证据。
7. 当前边界和下一步。
8. 至少 8 个面试问答，解释为什么、怎么做、替代方案、失败模式和 trade-off。
9. 自测题。

详细规则见 `docs/documentation-guide.md`。教程 19 是当前的新标准参考：

```text
docs/tutorials/19-工具执行政策与重试.md
```

教程 19 已包含 E2 的幂等、canonical JSON、唯一约束、并发、stale execution 和
exactly-once/at-least-once 面试问答。E3 完成后要在同一教程继续补充参数脱敏问答，
不能只更新代码不更新教程。

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
cat AGENTS.md
cat docs/HANDOFF.md
cat docs/roadmap.md
cat docs/documentation-guide.md
cat docs/research/2026-AI岗位技术栈调研.md
./scripts/check.sh
```

然后：

1. 如果任务是 Agent 稳定性，从 E3 敏感工具参数脱敏开始。
2. 如果任务是展示材料，从“P3：Q4 展示材料”开始。
3. 如果不确定，先向用户确认优先级，不要默认重做已完成功能。

## 交接完成检查

- [x] 最新功能提交 `cfaab58` 已完成 E2。
- [x] 当前文档提交已更新教程 19、README、roadmap、architecture 和本文件（具体哈希以 `git log` 为准）。
- [x] `main` 已推送并与 `origin/main` 同步。
- [x] `./scripts/check.sh` 当前为 `55 passed`。
- [x] 前端生产构建为 47 routes。
- [x] E2 的幂等键、状态机、并发、stale 接管、测试和教程问答已落地。
- [x] 已知前端无关失败和敏感文件边界已明确记录。
- [x] 用户要求的“教程包含面试问答”已同步到 `AGENTS.md` 和文档指南。

## 新对话推荐开场语

```text
你正在接手 TeachX。请先阅读 AGENTS.md、docs/HANDOFF.md、docs/roadmap.md、
docs/architecture.md、README.md、docs/tutorials/README.md、
docs/documentation-guide.md 和 docs/research/2026-AI岗位技术栈调研.md。

不要从零重做，不要删除本地数据或 Secret，不要让自动测试调用真实模型。
先检查 git status、最近提交和 ./scripts/check.sh。E1、E2 已完成，下一项是 E3：
敏感工具参数脱敏，方向见 docs/roadmap.md 的近期执行计划，不要重做 E1/E2。

每次任务结束前都要做文档判定。新功能必须补适合基础读者的中文教程，教程中至少
包含 8 个面试问答；更新 README/roadmap/HANDOFF，做浏览器或 API 验证，commit、push。
```
