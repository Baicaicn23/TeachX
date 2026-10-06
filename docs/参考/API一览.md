# API 一览

> 本文是 TeachX 后端 HTTP 接口的速查表。想知道每个接口的代码实现在哪,
> 看 `backend/src/teachx/api/routes/` 下对应的路由文件——那才是永远最新的权威来源。
> 本文更新于 2026-10-02,之后新增的接口以路由文件为准。

所有接口前缀均为 `/api`。WebSocket 聊天走独立入口 `/ws`,不在本表内。

## 认证与引导

```text
GET    /api/auth/status                 当前登录状态
GET    /api/auth/is_first_user          是否还没有任何用户(用于注册第一个管理员)
POST   /api/auth/register               注册(第一个注册用户自动成为管理员)
POST   /api/auth/login                  登录
POST   /api/auth/logout                 退出登录
GET    /api/auth/onboarding             首次引导状态
POST   /api/auth/onboarding/complete    标记首次引导完成
```

## 资料与个性化

```text
GET    /api/auth/profile                       读取个人资料
PUT    /api/auth/profile                       更新个人资料
GET    /api/auth/personalization               个性化状态摘要(聊天页状态条使用)
GET    /api/auth/profile/learner-profile       读取学习档案
PUT    /api/auth/profile/learner-profile       更新学习档案(目标、进度、风格)
PUT    /api/auth/profile/avatar                上传图片头像
DELETE /api/auth/profile/avatar                删除图片头像
GET    /api/auth/avatar/{user_id}              读取头像
GET    /api/auth/memories                      列出当前用户的跨会话长期记忆
DELETE /api/auth/memories/{memory_id}          删除一条长期记忆(仅自己的)
```

## 学习记录

```text
GET    /api/learning/feedback?session_id={id}   某会话的回答反馈
GET    /api/learning/records                    反馈与误区记录列表(支持筛选)
PUT    /api/learning/feedback/{message_id}      对某条回答提交/更新反馈
DELETE /api/learning/records/{feedback_id}      删除一条记录
```

## 练习与复习

```text
GET    /api/practice/summary                              练习摘要(题数、掌握度、复习时间)
GET    /api/practice/knowledge-bases                      可出题的知识库列表
GET    /api/practice/queue                                练习队列(新题 + 到期题)
POST   /api/practice/generate                             从知识库生成练习题
POST   /api/practice/questions/{id}/answer                提交作答和自评
DELETE /api/practice/questions/{id}                       删除题目
```

## 模型连接

```text
GET    /api/model-connections                          当前用户的连接列表
POST   /api/model-connections                          新建连接(Key 加密存储)
POST   /api/model-connections/test                     测试连接并读取模型列表
POST   /api/model-connections/default/activate         切回平台默认模型
POST   /api/model-connections/{id}/activate            激活某个个人连接
DELETE /api/model-connections/{id}                     删除连接
```

## WebSocket 聊天

```text
ws://127.0.0.1:8010/ws
→ 发送 start_turn 命令(内容、能力模式、工具开关、知识库选择)
→ 收到 session / stage_start / content / tool_call / tool_result /
   sources / result / done 等事件流
```

`tool_result` 事件会携带尝试次数、重试信息、耗时和幂等去重标记,
字段说明见[工具执行教程](../tutorials/19-工具执行政策与重试.md)。

意图路由开启时(默认),`tool_call` 事件的 metadata 带 `intent` 与 `agent`
字段;`result` / `done` 事件与助手消息的 metadata 带 `intent`、
`intent_confidence`、`intent_detector`(`rule` / `llm` / `fallback`)和
`agent` 字段,字段含义见[意图路由教程](../tutorials/25-意图识别与多Agent路由.md)。
