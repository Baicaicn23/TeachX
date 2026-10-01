# TeachX 开发交接文档

> 最后更新：2026-10-02  
> 用途：新开 Codex 对话或更换开发者时，先读本文件恢复项目上下文。

## 新对话第一条指令

可以把下面这段直接发给新对话：

```text
请先阅读 docs/HANDOFF.md、docs/roadmap.md、docs/architecture.md 和 README.md。
这是一个已经持续开发中的真实项目，不要从零重做。
先检查 git status 和最近提交，再从 roadmap 的当前焦点继续开发。
大型功能完成后必须补中文教程、更新 README/roadmap，并提交推送。
```

## 项目目标

TeachX 是一个 Web 优先的 AI 学习平台。

核心目标：

- 复用 DeepTutor 的 Next.js 前端。
- 重写一个更小、更清晰、可解释的 Python 后端。
- 保留 Agent Loop、工具调用、流式输出、知识库和个性化学习。
- 作为课设、作品集和简历项目持续开发。
- 每个大型功能都有代码、测试、教程、Git 提交和路线图记录。

项目暂时不做：

- 管理员用户管理。
- Docker 实机部署。
- PostgreSQL 迁移。
- 复杂多用户后台。

Docker 配置文件保留备用，但当前不投入时间。

## 当前技术栈

```text
前端：Next.js 16 + React 19 + TypeScript + Tailwind
后端：Python 3.12 + FastAPI + Pydantic
模型：Mock / OpenAI 兼容 Chat Completions
数据库：SQLite
检索：FTS5 + Embedding + RRF 混合排序
认证：bcrypt + JWT + HttpOnly Cookie
实时通信：WebSocket
CI：GitHub Actions，后端检查和前端构建
```

## 当前状态

截至最后更新：

- P0 Web 垂直切片完成。
- P1 流式 Agent Runtime 核心完成。
- P2 知识库和混合检索完成。
- P3 认证、用户隔离和个人资料完成基础阶段。
- U1 学习档案注入提示词完成。
- U2 聊天页个性化状态完成。
- U3 首次使用引导是当前下一步。
- 后端测试 `22 passed`。
- Git 工作区应保持干净。

最近功能提交：

```text
560cee9 docs: add chat personalization status tutorial
f51bf41 feat: show personalization status in chat
c9a109a docs: add personalization prompt tutorial
7310470 feat: personalize tutor prompts from learner profiles
```

## 仓库结构

```text
TeachX/
├── backend/
│   ├── src/teachx/
│   │   ├── api/          HTTP、WebSocket、认证和兼容路由
│   │   ├── auth/         用户、bcrypt、JWT、学习档案
│   │   ├── knowledge/    文档提取、切块、FTS、Embedding、混合检索
│   │   ├── providers/    Mock 和 OpenAI 兼容模型适配器
│   │   ├── runtime/      Agent Loop、提示词、工具
│   │   └── storage/      SQLite 和 Repository
│   └── tests/
├── frontend/             Next.js Web 前端
├── docs/
│   ├── HANDOFF.md        当前文件
│   ├── roadmap.md        完整开发路线和迭代日志
│   ├── architecture.md   稳定架构说明
│   └── tutorials/        面向基础薄弱读者的中文教程
├── scripts/
│   ├── dev.sh            同时启动前后端
│   └── check.sh          后端测试 + 前端类型检查
└── compose.yaml          Docker 配置，当前暂缓
```

## 本地启动

默认认证关闭，使用 Mock 模型：

```bash
./scripts/dev.sh
```

浏览器访问：

```text
http://localhost:3000
```

后端端口：

```text
http://127.0.0.1:8010
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

## 启用认证后的测试环境

```bash
NEXT_PUBLIC_AUTH_ENABLED=true \
TEACHX_AUTH_ENABLED=true \
TEACHX_AUTH_SECRET='至少32字节的测试Secret' \
./scripts/dev.sh
```

注意：

- 不要把真实 Secret 写进 Git。
- 正式 HTTPS 部署时设置 `TEACHX_AUTH_COOKIE_SECURE=true`。
- 本地测试账户保存在被 Git 忽略的 `data/teachx.db`。
- 要获得全新用户环境，可以停止服务后删除本地 `data/teachx.db`。这会删除本地会话、用户和知识库元数据。

## 验证命令

必须优先使用：

```bash
./scripts/check.sh
```

它执行：

- 后端 Ruff。
- 后端 pytest。
- 前端 TypeScript 检查。

完整前端构建：

```bash
cd frontend
npm run build
```

当前预期：

```text
22 passed
typecheck passed
43 Next.js routes built
```

## 核心运行链路

```text
Next.js Chat UI
→ /ws 统一回合协议
→ FastAPI WebSocket
→ AgentRuntime
→ Provider Adapter
→ ToolRegistry
→ SessionRepository
```

知识检索：

```text
文档上传
→ extractors 提取文本
→ chunker 切块
→ SQLite FTS5
→ Embedding 向量
→ RRF 混合排序
→ knowledge_search
→ sources 事件
```

个性化：

```text
用户学习档案
→ AgentRuntime 每回合读取
→ 注入系统提示词
→ 模型调整回答风格
→ done.personalization_applied
```

## 关键代码文件

### 后端

| 文件 | 职责 |
| --- | --- |
| `backend/src/teachx/main.py` | 应用装配和生命周期 |
| `backend/src/teachx/runtime/engine.py` | Agent Loop、工具循环、个性化和标题 |
| `backend/src/teachx/runtime/prompts.py` | 系统提示词与个性化注入 |
| `backend/src/teachx/runtime/tools.py` | 工具接口、计算器、知识检索 |
| `backend/src/teachx/providers/base.py` | Provider 接口 |
| `backend/src/teachx/providers/openai_compat.py` | OpenAI 流式和工具调用 |
| `backend/src/teachx/knowledge/service.py` | 知识库权限、存储和混合检索 |
| `backend/src/teachx/knowledge/embeddings.py` | Mock/OpenAI Embedding |
| `backend/src/teachx/auth/service.py` | 用户、密码、JWT、学习档案 |
| `backend/src/teachx/api/routes/ws.py` | WebSocket 回合协议 |
| `backend/src/teachx/api/routes/profile.py` | 用户资料、头像和学习档案 API |

### 前端

| 文件 | 职责 |
| --- | --- |
| `frontend/features/chat/components/ChatWorkspace.tsx` | 主聊天页面装配 |
| `frontend/components/chat/home/ChatComposer.tsx` | 聊天输入框 |
| `frontend/components/chat/home/PersonalizationStatus.tsx` | 聊天页个性化状态条 |
| `frontend/app/(utility)/profile/page.tsx` | 个人主页、头像和学习档案 |
| `frontend/features/chat/ChatStateAdapter.tsx` | WebSocket 状态机和消息展示 |

## 当前用户可用功能

- 注册、登录、退出。
- 用户会话隔离。
- 知识库所有权隔离。
- 图标头像和图片头像。
- 学习档案。
- 个性化开关。
- 聊天页个性化状态条。
- 流式聊天。
- 计算器工具调用。
- 知识库上传。
- FTS5、向量和 RRF 混合检索。
- 来源引用事件。

## 当前 API 概览

### 认证

```text
GET    /api/auth/status
GET    /api/auth/is_first_user
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout
```

### 个人资料

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

### 会话

```text
GET    /api/sessions
GET    /api/sessions/search
GET    /api/sessions/{session_id}
PATCH  /api/sessions/{session_id}
DELETE /api/sessions/{session_id}
GET    /api/sessions/{session_id}/messages/{message_id}/events
```

### 知识库

```text
GET    /api/knowledge-bases
POST   /api/knowledge-bases
GET    /api/knowledge-bases/{kb_name}
GET    /api/knowledge-bases/{kb_name}/files
POST   /api/knowledge-bases/{kb_name}/upload
GET    /api/knowledge-bases/{kb_name}/search
POST   /api/knowledge-bases/{kb_name}/reindex
```

## 数据库表

```text
users
sessions
messages
knowledge_bases
knowledge_documents
knowledge_chunks
knowledge_chunks_fts
knowledge_chunk_vectors
```

用户数据：

```text
users.avatar
users.learner_profile
users.personalization_enabled
```

会话所有权：

```text
sessions.user_id
```

知识库所有权：

```text
knowledge_bases.owner_id
```

## 当前路线图和下一步

完整内容在：

- `docs/roadmap.md`
- `docs/tutorials/README.md`

当前焦点是 U3：首次使用引导。

### U3 目标

新用户注册后，在 3 分钟内完成基础学习档案。

### U3 建议实现

1. 注册成功后进入 onboarding 页面或弹层。
2. 选择学习阶段。
3. 选择主要学习目标。
4. 选择讲解偏好。
5. 可选上传第一份资料。
6. 允许“稍后设置”并跳过。
7. 保存后进入聊天页。
8. 写测试和教程。
9. 更新 README 和 roadmap。

### U3 验收标准

- 新用户不填写任何内容也能跳过。
- 填写后数据写入现有学习档案接口。
- 完成后聊天页状态条立即显示摘要。
- 刷新后不回退到 onboarding。
- 旧用户不应被强制再次引导。
- 浏览器实际验证。
- 后端和前端测试通过。
- 教程、README、roadmap 和 Git 提交同步。

## 当前已知限制

- 真实 OpenAI/Embedding API 尚未使用用户 API Key 完成线上联调。
- Docker 配置未实机构建。
- PostgreSQL 未迁移。
- 管理员用户管理暂缓。
- 知识库名称目前全局唯一，不同用户不能使用同名知识库。
- 原前端仍包含大量尚未接通的页面，当前只保证已实现路径可用。
- 学习档案设置页主要入口已放到 `/profile`，不要依赖隐藏的 learner-only Settings 页面。
- 个性化和知识检索都可关闭，但权限最终由后端判断。

## 开发规则

每次大型功能必须完成：

```text
功能代码
→ 自动测试
→ 浏览器或 API 验证
→ 中文教程
→ 更新 README（如影响用户）
→ 更新 docs/roadmap.md
→ commit
→ push
```

Git 提交建议：

```text
feat: 功能实现
docs: 教程和路线图
```

不要：

- 每个小改动都更新 README。
- 把 Secret 提交到 Git。
- 在没有验证时写“已经完成生产验证”。
- 跳过浏览器验证。
- 重写已经稳定工作的 Agent Loop。

## 当前 Git

远端：

```text
git@github.com:Baicaicn23/TeachX.git
```

查看状态：

```bash
git status --short --branch
git log --oneline -10
```

推送：

```bash
git push
```

## 新对话推荐工作顺序

1. 阅读本文件。
2. 阅读 `docs/roadmap.md`。
3. 执行 `git status` 和 `git log -5`。
4. 执行 `./scripts/check.sh`。
5. 从 U3 开始，不要重做已验证功能。
6. 先在浏览器验证现状，再开始修改。
