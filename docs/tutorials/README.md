# TeachX 技术教程

这套教程面向“学过 Python 基础语法，但还没有独立读过工程项目”的读者。
它不会要求你一开始就理解所有代码，而是沿着一次真实请求的路径逐步建立认知。

## 学习目标

学完后，你应该能够：

1. 说清楚用户消息从浏览器到模型，再到数据库的完整路径。
2. 理解 Agent Loop 为什么需要循环，以及工具调用如何参与循环。
3. 理解异步函数、异步迭代器和流式输出。
4. 找到并修改 TeachX 中的提示词、工具和 WebSocket 事件。
5. 为一项新功能补测试，并且知道测试应该验证什么。

## 推荐顺序

| 章节 | 主题 | 对应代码 |
| --- | --- | --- |
| [00](00-如何阅读这个项目.md) | 如何阅读项目、运行项目和定位代码 | 整个仓库 |
| [01](01-一次提问的完整旅程.md) | 一次提问从浏览器到数据库的完整路径 | `frontend/`、`backend/` |
| [02](02-从complete到stream.md) | `async`、`await`、异步生成器和流式输出 | `providers/`、`runtime/engine.py` |
| [03](03-工具调用是怎么工作的.md) | 消息角色、工具 schema、工具调用闭环 | `runtime/tools.py`、`runtime/engine.py` |
| [04](04-知识库与RAG.md) | 上传、提取、切块、FTS5、检索和引用 | `knowledge/`、`runtime/tools.py` |
| [05](05-向量检索与混合排序.md) | Embedding、余弦相似度、RRF 和重建立索引 | `knowledge/embeddings.py`、`knowledge/service.py` |
| [06](06-认证与权限.md) | bcrypt、JWT、Cookie、WebSocket 鉴权和会话隔离 | `auth/`、`api/auth_dependencies.py` |
| [07](07-多用户数据隔离.md) | owner_id、知识库权限、管理员边界和 Agent 工具授权 | `knowledge/service.py`、`runtime/tools.py` |
| [08](08-Docker部署.md) | Image、Container、Volume、Compose 和健康检查 | `Dockerfile`、`compose.yaml` |
| [09](09-CI持续集成.md) | GitHub Actions、测试和构建 | `.github/workflows/ci.yml` |
| [10](10-个人资料与学习档案.md) | 头像、资料校验、学习偏好和用户隐私 | `auth/service.py`、`api/routes/profile.py` |
| [11](11-个性化提示词.md) | 学习档案注入、开启关闭、注入防护和提示词测试 | `runtime/prompts.py`、`runtime/engine.py` |
| [12](12-聊天页个性化状态.md) | 个性化状态条、快速开关、下一回合生效和独立组件设计 | `PersonalizationStatus.tsx`、`profile-api.ts` |
| [13](13-首次使用引导.md) | 首次引导、跳过状态、学习目标、可选资料和旧用户迁移 | `onboarding/page.tsx`、`onboarding-api.ts` |
| [14](14-学习反馈与错题记录.md) | 回答反馈、误区记录、用户隔离、记录管理和聊天草稿回流 | `AnswerFeedbackActions.tsx`、`answer-feedback-api.ts` |
| [15](15-练习与复习模式.md) | 知识库出题、自评、复习间隔、掌握度和练习队列 | `practice/service.py`、`practice-review-api.ts` |
| [16](16-对话中的学习目标.md) | 目标进度、完成状态、提示词注入、重新激活和聊天状态条 | `LearningGoalStatus.tsx`、`runtime/prompts.py` |
| [17](17-用户模型连接与多平台.md) | 平台默认、用户模型连接、Key 加密、模型测试和 Provider 切换 | `model_connections/service.py`、`model-connections/page.tsx` |
| [18](18-Agent费用控制与Provider稳定性.md) | token usage、输出和上下文预算、日预算、错误映射与费用验收 | `providers/`、`runtime/engine.py`、`usage/service.py` |
| [19](19-工具执行政策与重试.md) | 工具政策、临时/永久错误、超时、指数退避、可观测性和面试问答 | `runtime/tools.py`、`runtime/engine.py` |

## 项目路线图

了解每一步开发目标、当前进度和后续计划，请查看：

- [TeachX 完整开发路线](../roadmap.md)
- [TeachX 开发交接文档](../HANDOFF.md)

## 学习方法

编写或修改教程前，请先阅读 [TeachX 文档写作指南](../documentation-guide.md)。
教程需要让基础一般的读者知道“为什么、怎么做、结果是什么、出错怎么办”。

不要只读代码，按照下面的循环学习每一章：

```text
先读人话解释
→ 打开对应源码
→ 只追踪一条路径
→ 回答自测题
→ 修改一个小地方
→ 运行测试
```

看不懂某个类时，不要立刻搜索所有相关文件。先回答三个问题：

1. 谁创建了它？
2. 谁调用了它？
3. 它最终把数据交给了谁？

这三个问题通常比“这个类一共有多少方法”更重要。

## 阅读约定

- “模块”指一个拥有明确输入和输出的代码单元，可以是一个函数、类或文件。
- “接口”不只指函数签名，还包括调用顺序、错误方式和必要配置。
- “适配器”指把外部系统转换成项目内部统一接口的代码。
- 星号 `*` 出现在函数参数前时，表示它后面的参数必须使用关键字传递。
