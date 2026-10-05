<div align="center">

<img src="./frontend/public/teachx-banner.svg" alt="TeachX" width="600">

**把大模型做成可靠、可评测的学习助手**

自研 Agent Harness · 混合检索 RAG · 工具可靠性工程 · 多用户学习闭环

[![状态](https://img.shields.io/badge/status-%E5%BC%80%E5%8F%91%E4%B8%AD-brightgreen)](#-开发路线)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](backend/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.142-009688)](backend/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black)](frontend/)
[![CI](https://github.com/Baicaicn23/TeachX/actions/workflows/ci.yml/badge.svg)](https://github.com/Baicaicn23/TeachX/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](#-维护者入口)

[快速开始](#-快速开始) · [技术亮点](#-技术亮点) · [教程](#-文档与教程) · [开发路线](#-开发路线)

</div>

---

TeachX 是一个受 [DeepTutor](https://github.com/HKUDS/DeepTutor) 启发的独立项目：
后端完全重写，前端基于 Apache-2.0 复用。它不做"调一次模型 API"的封装，而是围绕
2026 年 AI 应用岗位真正看重的工程能力构建——把模型做成**可靠、可控、可评测**的系统。
技术选型依据见 [2026 AI 岗位技术栈调研](docs/规划/2026-AI岗位技术栈调研.md)。

## ✨ 技术亮点

| | 能力 | 一句话说明 |
| --- | --- | --- |
| 🧭 | **意图识别 + 多 Agent 路由** | 每回合先判意图（六类教学场景），按路由表交给专属提示词 + 工具策略的子 agent；工具最小权限在 schema 与执行层双重生效 |
| 🧩 | **自研 Agent Harness** | 不依赖 Agent 框架，手写流式多轮工具调用循环，每层设计都能讲清为什么 |
| 🛡️ | **工具可靠性工程** | 错误分类 · 有限退避重试 · 幂等去重 · 敏感参数脱敏 · 有界并发 · 双层超时 |
| 🔎 | **混合检索 RAG** | SQLite FTS5 + 向量 + RRF 融合排序，来源引用，检索继承用户数据权限 |
| 📊 | **评测与可观测** | 固定评测集 + Hit@K/Recall@K/MRR 基线门禁；回合 trace 五层责任定位 |
| 🧠 | **上下文与工具生态** | 超长历史自动压缩为前情提要；MCP 协议客户端（自写，零依赖）接入外部工具 |
| 📉 | **成本与上下文工程** | token 全量记录与展示 · 每日预算 · 输出/历史/工具结果上限 · 超限阻止或回退 |
| 🔌 | **多模型接入** | 统一 Provider 接口，用户自带 DeepSeek/OpenAI Key（加密存储），已真实联调 |
| 🎓 | **真实学习闭环** | 个性化提示词 · 首次引导 · 错题记录 · 练习复习 · 学习目标，多用户数据隔离 |

## 🖼 核心功能一览（真实运行界面）

### 🔎 混合检索 RAG——每个回答都有出处

上传资料后提问，回答基于检索到的片段生成，并附**知识库来源引用**（哪个文件、哪个片段），
同时展示本轮 token 消耗。检索走 FTS5 + 向量 + RRF 融合，并自动继承用户数据权限。

<img src="docs/screenshots/rag-sources.png" width="820" alt="RAG 检索与来源引用">

### 🧩 Agent Loop——模型与工具的多轮协作

模型决定何时调用工具：下例中知识检索工具先执行，结果回填后模型继续推理，
回合状态条显示"已完成 · 0s · 1 次工具调用"；整条链路
`WebSocket → Agent Runtime → Tool Registry → Session Storage` 在回答中一目了然。

<img src="docs/screenshots/agent-loop-tool.png" width="820" alt="Agent Loop 工具调用">

### 🧠 上下文记忆——它记得你是谁

学习档案（阶段、目标、进度、讲解风格）注入系统提示词，聊天页实时显示个性化状态与
目标进度条；对话变长后旧消息自动压缩为"前情提要"，关键信息不丢、token 可控。

<img src="docs/screenshots/memory-context.png" width="820" alt="个性化状态与学习目标">

### 🔌 MCP 工具接入——即插即用的外部工具生态

自写的最小 MCP stdio 客户端（JSON-RPC 2.0，零依赖）在应用启动时连接外部 server，
发现并注册远端工具，Agent 无感使用：

```text
[mcp] server=demo 注册工具: ['mcp_demo_fake_echo']   ← 真实启动日志
```

配置即接入：`TEACHX_MCP_SERVERS='[{"name":"demo","command":"python","args":["server.py"]}]'`

<details>
<summary><b>当前边界（诚实说明，也是下一步方向）</b></summary>

- 运行时 Embedding 默认 Mock；真实向量模型（智谱 embedding-3）已联调并有评测对比，日常使用可一键切换
- 回答忠实度与引用质量评测未做（需要真实模型 + LLM-as-a-Judge）
- 工具权限审批、沙箱执行、MCP Server 端生态未做（MCP Client 已接入）
- Docker 配置保留但未实机验证，未做公网部署
- 项目定位是**简历作品集**（Agent 开发实习方向），不追求生产上线

</details>

## 🚀 快速开始

需要 Python 3.12+ 和 Node.js 20+。

```bash
./scripts/dev.sh
```

打开 [http://localhost:3000](http://localhost:3000)，发送"计算 7 * 9"，
应该看到模型调用计算器工具并流式回答 63。

不想消耗 API 额度？用 Mock 模型启动：

```bash
TEACHX_LLM_PROVIDER=mock \
TEACHX_EMBEDDING_PROVIDER=mock \
TEACHX_DATABASE_PATH=/tmp/teachx-mock.db \
TEACHX_KNOWLEDGE_ROOT=/tmp/teachx-mock-knowledge \
./scripts/dev.sh
```

<details>
<summary><b>接入真实模型（DeepSeek / OpenAI / 任何 OpenAI 兼容平台）</b></summary>

配置 `backend/.env`（该文件被 Git 忽略）：

```bash
TEACHX_LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com/v1
TEACHX_MODEL=deepseek-flash
OPENAI_API_KEY=你的密钥
```

也可以在网页"模型连接"页填入自己的 Key——服务端加密存储，接口不回传明文，
保存后聊天即使用你自己的模型。

</details>

## 📊 质量与验证

```bash
./scripts/check.sh     # 预期 All checks passed（后端测试全绿,全程 Mock 零 API 消耗）
```

- 检索质量可复现:固定评测集(关键词卷 + 语义改写卷)双基线;真实 Embedding
  (智谱 embedding-3)接入后语义卷 MRR 0.639 → 0.667,关键词卷无退化,
  退化自动拦截:`cd backend && uv run python -m teachx.evals.run_rag_eval`
- 意图路由质量可复现:38 条标注意图考卷,规则分类器准确率门槛 0.90 +
  基线回归门禁:`cd backend && uv run python -m teachx.evals.run_intent_eval`
- 失败定位：`uv run python -m teachx.runtime.turn_trace --session <会话id>`
  （把失败定位到模型 / 检索 / 工具 / 编排 / 费用五层之一）
- 前端生产构建：47 条路由（`cd frontend && npm run build`）

## 📁 项目结构

```text
TeachX/
├── backend/                 FastAPI 服务
│   └── src/teachx/
│       ├── runtime/         Agent Loop、工具政策、幂等、trace
│       ├── providers/       Mock 与 OpenAI 兼容模型适配器
│       ├── knowledge/       文档提取、切块、索引与混合检索
│       ├── evals/           检索评测指标与跑分命令
│       ├── auth/            用户、密码和 JWT
│       ├── usage/           token 用量与日预算
│       └── storage/         SQLite 持久化与迁移
├── frontend/                Next.js 界面（基于 Apache-2.0 复用）
├── docs/                    导航、参考、规划、规范、26 篇教程
└── scripts/                 dev.sh 一键启动 · check.sh 一键检查
```

## 📚 文档与教程

每个核心功能都有中文教程，解释为什么这样设计，并配**面试问答**——项目即面试准备材料。

- [全部文档导航](docs/README.md) · [教程目录](docs/tutorials/README.md)
- 入门：[如何阅读这个项目](docs/tutorials/00-如何阅读这个项目.md) · [一次提问的完整旅程](docs/tutorials/01-一次提问的完整旅程.md)
- Agent 稳定性：[工具政策/重试/幂等/脱敏](docs/tutorials/19-工具执行政策与重试.md) · [多工具执行](docs/tutorials/20-多工具执行策略.md) · [超时与恢复](docs/tutorials/21-整回合超时与断线恢复.md)
- 评测可观测：[RAG 检索评测](docs/tutorials/22-RAG检索评测.md) · [回合 trace 诊断](docs/tutorials/23-回合trace诊断.md) · [意图识别与多 Agent 路由](docs/tutorials/25-意图识别与多Agent路由.md)
- 参考：[架构与数据流](docs/参考/架构与数据流.md) · [API 一览](docs/参考/API一览.md) · [配置说明](docs/参考/配置说明.md) · [数据库表结构](docs/参考/数据库表结构.md)

## 🗺️ 开发路线

| 状态 | 阶段 | 内容 |
| :---: | --- | --- |
| ✅ | 基础平台 | Web 垂直切片 · 流式回合 · 知识库混合检索 · 认证与隔离 |
| ✅ | 学习闭环 | 个性化 · 首次引导 · 错题 · 练习复习 · 学习目标 |
| ✅ | 模型与费用 | 用户模型连接 · token 预算 · Provider 错误处理 |
| ✅ | Agent 稳定性 | 重试 · 幂等 · 脱敏 · 并发 · 双层超时（E1~E5） |
| ✅ | 评测与可观测 | 检索指标与基线门禁 · 回合 trace 五层诊断（E6） |
| ✅ | 真实 Embedding | 智谱 embedding-3 零代码接入，语义卷 MRR 0.639 → 0.667（E8） |
| ✅ | 上下文与工具生态 | 历史前情提要 · 自写 MCP 客户端接入外部工具（E7/E9a） |
| ✅ | 意图与多 Agent 路由 | 意图六分类 · 规则 + LLM 两层识别 · 六个子 agent · 工具最小权限 · 意图评测门禁（P0） |
| 🔄 | 作品集收尾 | 演示视频三支 · 简历项目描述 · 面试问答稿 |
| ⬜ | 端到端深度（下一步） | 端到端 Agent 评测（P1）· 检索召回优化（P2）· 长期记忆与在线监控（P3） |

> 项目定位：**简历作品集**（目标 Agent 开发实习），生产部署硬化不在计划内。
> 详细进度见 [可视化进度地图](docs/规划/项目进度地图.html) 和 [开发路线图](docs/规划/开发路线图.md)。

## 🔧 维护者入口

接手开发或恢复上下文：[AGENTS.md](AGENTS.md) → [开发交接文档](docs/交接文档.md) →
[开发路线图](docs/规划/开发路线图.md) → [文档写作指南](docs/规范/文档写作指南.md)

<details>
<summary><b>上游关系与许可</b></summary>

TeachX 不是 DeepTutor 的官方仓库。前端按照 Apache-2.0 许可证复用，后端和运行时
围绕更小的产品边界重新实现，来源与归属见 [UPSTREAM.md](UPSTREAM.md)。

本项目使用 Apache License 2.0，详见 [LICENSE](LICENSE)；上游完整许可文本保留在
[third_party/DeepTutor-LICENSE](third_party/DeepTutor-LICENSE)。

</details>
