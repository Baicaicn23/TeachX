<p align="center">
  <img src="./frontend/public/teachx-banner.svg" alt="TeachX" width="720">
</p>

<p align="center">
  一个把大模型做成可靠学习助手的多用户 Web 平台：自研 Agent Harness、
  混合检索、幂等安全的工具调用、可观测的 token 成本。
</p>

<p align="center">
  <img alt="当前状态" src="https://img.shields.io/badge/status-%E5%BC%80%E5%8F%91%E4%B8%AD-brightgreen">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-blue">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.142-009688">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-16-black">
  <img alt="许可证" src="https://img.shields.io/badge/license-Apache--2.0-blue">
  <img alt="CI" src="https://github.com/Baicaicn23/TeachX/actions/workflows/ci.yml/badge.svg">
</p>

TeachX 是一个受 [DeepTutor](https://github.com/HKUDS/DeepTutor) 启发的独立项目：
后端完全重写，前端基于 Apache-2.0 复用。它不是"调一次模型 API"的封装，而是围绕
2026 年 AI 应用岗位真正看重的工程能力构建的完整产品——把模型做成可靠、可控、
可继续扩展的系统。技术选型依据见
[2026 AI 岗位技术栈调研](docs/规划/2026-AI岗位技术栈调研.md)。

## 为什么这个项目不一样

多数课程项目停留在"能调模型、能流式输出"。TeachX 把力气花在模型之外的系统层：

- **自研 Agent Harness**：不依赖 LangChain 等框架，手写流式 Agent Loop（多轮
  推理 → 工具调用 → 继续推理），每一层都能讲清为什么这样设计。
- **工具调用可靠性**：错误分为临时/永久/超时三类，临时错误按指数退避有限重试；
  幂等保护保证同一业务请求只产生一次副作用，重复请求直接重放第一次的结果。
- **混合检索 RAG**：SQLite FTS5 全文检索 + 向量相似度，RRF 融合排序；回答带
  来源引用；检索自动继承当前用户的数据权限。
- **上下文与成本工程**：用户学习档案注入系统提示词；历史消息、工具结果和输出
  token 都有预算上限；每次模型调用记录 token 用量，支持每日预算与超限阻止。
- **多模型接入**：统一 Provider 接口对接 OpenAI 兼容协议；用户可自带
  DeepSeek/OpenAI 的 API Key（服务端加密存储），也可回退平台默认模型。
  DeepSeek Flash 的流式输出和工具调用已真实验证。
- **真实多用户产品**：注册认证、数据按用户隔离、个性化提示词、错题记录、
  练习与间隔复习——是一个可日常使用的学习工具，不是一次性演示。

## 现在能做什么

| 能力 | 说明 |
| --- | --- |
| 流式聊天与 Agent 回合 | WebSocket 流式输出，多轮工具调用，会话与事件持久化 |
| 工具执行可靠性 | 错误分类、单次超时、有限退避重试、幂等去重（`tool_result` 事件可观察尝试次数与去重标记） |
| 知识库与检索 | TXT / Markdown / PDF 上传，全文 + 向量混合检索，来源引用 |
| 多用户与安全 | JWT Cookie 认证，会话/知识库/练习按用户隔离，用户 API Key 加密存储 |
| 个性化 | 学习档案（年级、目标、讲解风格）注入提示词，可随时开关 |
| 学习闭环 | 回答反馈、错题记录、从知识库生成练习、间隔复习、学习目标进度 |
| 成本控制 | token 用量记录与展示、每日预算、输出/历史/工具结果上限、超限阻止或回退 Mock |

**当前边界**（诚实说明，也是下一步方向）：还没有固定评测数据集、离线回放和
RAG 指标；还没有结构化 trace 与告警；Embedding 仍主要使用 Mock；还没有
MCP、工具权限审批和沙箱执行；Docker 配置保留但未实机验证。

## 快速开始

需要 Python 3.12+ 和 Node.js 20+。

```bash
./scripts/dev.sh
```

启动后访问 [http://localhost:3000](http://localhost:3000)（前端），
后端在 [http://127.0.0.1:8010](http://127.0.0.1:8010)。发送"计算 7 * 9"，
应该看到模型调用计算器工具并流式回答 63。

只想体验界面、不消耗 API 额度时，用 Mock 模型启动：

```bash
TEACHX_LLM_PROVIDER=mock \
TEACHX_EMBEDDING_PROVIDER=mock \
TEACHX_DATABASE_PATH=/tmp/teachx-mock.db \
TEACHX_KNOWLEDGE_ROOT=/tmp/teachx-mock-knowledge \
./scripts/dev.sh
```

### 接入真实模型

复制 `backend/.env` 配置（不提交到 Git）：

```bash
TEACHX_LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com/v1   # 任何 OpenAI 兼容平台
TEACHX_MODEL=deepseek-flash
OPENAI_API_KEY=你的密钥
```

也可以在网页"模型连接"页填入自己的 Key，保存后聊天即使用你自己的模型；
Key 由服务端加密，接口不回传明文。

## 项目结构

```text
TeachX/
├── backend/                 FastAPI 服务
│   └── src/teachx/
│       ├── runtime/         Agent Loop、工具注册、执行政策与幂等记录
│       ├── providers/       Mock 与 OpenAI 兼容模型适配器
│       ├── knowledge/       文档提取、切块、索引与混合检索
│       ├── auth/            用户、密码和 JWT
│       ├── usage/           token 用量与日预算
│       └── storage/         SQLite 持久化与迁移
├── frontend/                Next.js 界面（基于 Apache-2.0 复用）
├── docs/                    架构、路线图、教程与调研
└── scripts/                 dev.sh 一键启动、check.sh 一键检查
```

## 质量检查

```bash
./scripts/check.sh
```

预期看到 `All checks passed!` 和 `55 passed`（后端自动测试，全部使用 Mock，
不消耗 API 额度），以及前端 TypeScript 检查通过。前端生产构建单独验证：
在 `frontend/` 下运行 `npm run build`，预期 47 条路由构建成功。

## 文档与教程

项目为每个核心功能写了中文教程，解释为什么这样设计、代码如何工作，并配有
面试问答，从零基础也能读懂：

- [教程目录](docs/tutorials/README.md)
- [如何阅读这个项目](docs/tutorials/00-如何阅读这个项目.md)
- [一次提问的完整旅程](docs/tutorials/01-一次提问的完整旅程.md)
- [工具执行政策、重试与幂等保护](docs/tutorials/19-工具执行政策与重试.md)（最新参考标准）

其他：[全部文档导航](docs/README.md)、
[架构说明](docs/参考/架构与数据流.md)、
[开发路线图](docs/规划/开发路线图.md)、
[文档写作指南](docs/规范/文档写作指南.md)。

## 开发路线

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 基础能力 | Web 垂直切片、流式 Agent 回合、知识库与混合检索 | 已完成 |
| 产品闭环 | 认证与用户隔离、个性化、错题、练习复习、学习目标 | 已完成 |
| 模型接入 | 用户模型连接、费用控制、Provider 错误处理 | 已完成 |
| Agent 可靠性（一） | 工具执行政策、超时、有限重试、幂等保护 | 已完成 |
| Agent 可靠性（二） | 敏感参数脱敏、多工具执行策略、整回合超时与断线提示 | 进行中 |
| 评测与可观测 | 固定评测集、RAG 指标、结构化 trace、回归告警 | 计划中 |
| 上下文与记忆 | 对话摘要、长期学习记忆、上下文压缩 | 计划中 |
| 检索升级 | 真实 Embedding、Reranker、检索质量评测 | 计划中 |
| 生态与部署 | MCP、工具权限审批、沙箱、在线演示 | 计划中 |

## 维护者入口

接手开发或恢复上下文时，按顺序阅读：[AGENTS.md](AGENTS.md)、
[开发交接文档](docs/交接文档.md)、[开发路线图](docs/规划/开发路线图.md)、
[文档写作指南](docs/规范/文档写作指南.md)。

## 上游关系与许可

TeachX 不是 DeepTutor 的官方仓库。前端按照 Apache-2.0 许可证复用，后端和运行时
围绕更小的产品边界重新实现，来源与归属见 [UPSTREAM.md](UPSTREAM.md)。

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE)；上游完整许可文本保留在
[third_party/DeepTutor-LICENSE](third_party/DeepTutor-LICENSE)。
