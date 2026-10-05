# 24:上下文摘要压缩与 MCP 工具接入

> 本章覆盖两个"下一步必备"能力,都保持学习版实现:
> **E7**——对话历史太长时,旧消息自动压缩成"前情提要";
> **E9 前半**——用自写的最小 MCP 客户端,把外部 server 的工具接进 Agent。
> 读完后你应该能回答:上下文长了怎么办、MCP 是什么、为什么要自己写协议客户端。

## 一、E7:上下文摘要压缩

### 1.1 问题:历史越长,越贵越差

每次回合都会把历史消息塞进模型上下文。对话越长:token 费用线性上涨、模型注意力
被稀释、还可能撞上下文窗口上限。旧的 `_trim_history` 处理方式是"超出窗口的直接
丢弃"——旧对话的关键信息(比如用户 earlier 说过目标)就永远消失了。

### 1.2 学习版方案:前情提要

不调模型(零消耗、确定性、可测试),用**本地启发式**压缩:

```text
历史 24 条,窗口保留 4 条时:
【前情提要】更早的 20 条对话已压缩为要点:     ← system 消息,紧跟系统提示词
- 用户:很旧的问题0,包含关键概念超导0…
- 助手:…
- …(每条截断到 50 字)
message-19                                     ← 最近 4 条保留原文
message-20
message-21
message-22
```

设计取舍:

- **摘要是本地拼接,不是模型总结**。学习版优先确定性:同样的历史永远产出同样
  的提要,测试可以直接断言内容。模型总结是后续可选升级。
- **提要永不丢**:字符预算裁剪只作用于最近消息,提要始终保留在最前。
- **关掉即回退**:`TEACHX_HISTORY_SUMMARY_ENABLED=false` 恢复旧行为。

配置:

```bash
TEACHX_HISTORY_SUMMARY_ENABLED=true   # 默认开
TEACHX_SUMMARY_SNIPPET_CHARS=50       # 提要里每条消息截断长度
```

### 1.3 测试与验证

`backend/tests/test_history_summary.py`(6 个):未超窗口不动、超窗压缩且保留
最近原文、截断生效、可关闭、字符预算共存、`_build_messages` 端到端组装。
原费用控制测试同步更新为新契约(前情提要置顶)。

## 二、E9 前半:MCP 工具接入

### 2.1 MCP 是什么,为什么值得接

MCP(Model Context Protocol)是连接 AI 应用与外部工具/数据源的开放标准——
写一个符合协议的 server,任何 MCP 客户端(AI 应用)都能发现并调用你的工具。
对简历的含义:这是 2026 年 Agent 岗位的高频词,而且"接入外部工具生态"是
Agent 从玩具走向平台的分水岭。

### 2.2 学习版实现:自写协议客户端,不引 SDK

`backend/src/teachx/runtime/mcp_client.py` 约 200 行,零新依赖:

```text
McpStdioClient(子进程管理 + JSON-RPC 2.0 帧收发)
  start()       拉起 server 子进程(stdin/stdout 管道),幂等
  initialize()  协议握手:initialize 请求 → notifications/initialized 通知
  list_tools()  发现远端工具(name/description/inputSchema)
  call_tool()   执行远端工具,抽取 text 内容,isError 转异常
McpTool(BaseTool)  把远端工具包装成本地工具
  注册名加前缀 mcp_<server>_ 防冲突;schema 原样透传给模型
  保守政策:read_only=False、不重试——外部工具不可信默认
McpBridge  连接 server → 发现 → 注册进 ToolRegistry
```

为什么自己写而不引官方 SDK:协议核心只有三个方法(initialize / tools/list /
tools/call),手写一遍才能在面试里讲清"MCP 到底是什么"——它是换行分隔的
JSON-RPC 2.0,stdio 上跑子进程。真要上生产,再换官方 SDK,接口不用变。

### 2.3 接入方式

配置环境变量(默认为空 = 不启用,生产行为不变):

```bash
export TEACHX_MCP_SERVERS='[{"name":"demo","command":"python","args":["-u","server.py"]}]'
```

应用启动时逐个连接注册,**单个 server 挂了只告警不阻塞启动**:

```text
[mcp] server=demo 注册工具: ['mcp_demo_fake_echo']
```

MCP 工具在聊天中自动可用(mcp_ 前缀工具默认追加到启用列表),用户显式指定
tools 列表时仍以列表为准。

### 2.4 测试与验证

- `tests/fixtures/fake_mcp_server.py`:约 60 行的测试夹具 server,按协议响应
  initialize / tools/list / tools/call。
- `tests/test_mcp_client.py`(4 个):握手与发现、包装工具经 ToolRegistry
  真实执行(含 schema 透传、保守政策断言)、远端 isError 转失败结果、幂等 start。
- **真实验证**:带 `TEACHX_MCP_SERVERS` 启动完整应用,启动日志出现
  `[mcp] server=demo 注册工具: ['mcp_demo_fake_echo']`——配置→子进程→协议
  握手→发现→注册全链路打通。
- 全量检查:102 passed。

## 三、当前边界

- 摘要是本地拼接,不做模型总结;不会跨会话持久记忆(长期记忆仍是 E7 远期)。
- MCP 客户端只实现了 stdio 传输与 tools 能力,没有 resources/prompts/采样;
  单 server 顺序请求,无并发流水线。
- MCP 工具的参数脱敏未声明(E3 的 sensitive_arguments 对动态工具留空),
  接入可信 server 后再按需补充。

## 四、面试问答

### 1. 上下文太长你们怎么处理?

两层:先用三层硬上限(历史条数/字符、工具结果、输出 token)兜底;E7 之后,
超出窗口的旧消息不再直接丢弃,而是压缩成"前情提要"作为 system 消息置顶——
关键概念不丢,token 可控。学习版摘要是本地拼接(确定性、可测试),模型总结
是可选升级。

### 2. 为什么摘要用本地拼接而不是让模型总结?

总结要额外调一次模型:有成本、有延迟、不确定(同一段历史两次总结不同),
测试只能断言"变短了"。本地拼接零消耗、确定性、可精确断言内容。当历史复杂到
拼接式提要不够用时,升级成模型总结只需替换一个函数,接口不变。

### 3. 前情提要会不会被字符预算裁掉?

不会。裁剪只作用于"最近消息"区,提要固定置顶保留——它本身就是压缩产物,
比它保护的原文短得多。

### 4. MCP 是什么?你的实现做了什么?

MCP 是连接 AI 应用与外部工具的开放协议,传输层是换行分隔的 JSON-RPC 2.0。
我的客户端管理一个 server 子进程,完成 initialize 握手、tools/list 发现、
tools/call 执行三步,把发现的工具包装成本地 BaseTool 注册进 ToolRegistry——
Agent Loop 完全无感,它看到的仍是统一的 execute 接口。

### 5. 为什么不用官方 MCP SDK?

协议核心只有三个方法,手写一遍才能真正讲清协议(而不是"我会调 SDK")。
同时零新依赖,符合学习版约束。生产化时换官方 SDK,桥接接口不变——这是
"先吃透协议,再拥抱生态"的顺序。

### 6. 外部工具默认给什么执行政策?为什么?

read_only=False、不重试。外部工具的能力和副作用未知,保守默认最安全:
串行执行避免并发交错,不重试避免重复副作用(它没接幂等记录)。确认某个
server 工具只读后,再显式放宽。

### 7. 远端工具名和本地工具撞名怎么办?

注册名强制加 `mcp_<server>_` 前缀,不同 server 之间、与内置工具之间都不会
冲突;调用远端时再去掉前缀还原原始名。

### 8. MCP server 挂了会怎样?

启动时:单个 server 连接失败只打告警,应用照常起(工具生态是增强,不是依赖)。
运行时:请求超时或连接断开会转成 McpError,经 ToolRegistry 包装成 success=False
的 ToolResult 返回给模型——错误是数据,不是中断(与教程 20 的批次设计一致)。

## 自测题

1. 前情提要为什么放在 system 消息、且置于最近消息之前?
2. `TEACHX_SUMMARY_SNIPPET_CHARS` 调成 200 会带来什么 trade-off?
3. MCP 的 initialize 握手之后为什么要发 notifications/initialized?
4. 动态 MCP 工具的 inputSchema 从哪来?它对模型起什么作用?
5. 如果两个 MCP server 都提供名为 `search` 的工具,注册后分别叫什么?
6. 为什么 MCP 工具的注册名要加前缀,而调用远端时要去掉?
