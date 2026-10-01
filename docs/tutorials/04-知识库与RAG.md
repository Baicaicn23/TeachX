# 04：知识库与 RAG

## 先用生活语言理解 RAG

RAG 可以理解成“开卷考试”。

- 普通模型回答，相当于只靠记忆考试。
- RAG 回答，相当于先找到相关资料，再根据资料回答。
- 引用来源相当于把翻到的页码写出来。

英文全称是 Retrieval-Augmented Generation，意思是“检索增强生成”。

## 为什么需要 RAG

模型有三个常见问题：

1. 不知道你私有的课程资料。
2. 可能记错事实。
3. 无法证明答案来自哪里。

RAG 不能解决全部问题，但可以显著改善这三类问题。

## TeachX 的 RAG 流程

```text
上传文件
→ 提取纯文本
→ 切成文本块
→ 写入 SQLite
→ 建立 FTS5 全文索引
→ 用户提问
→ knowledge_search 检索
→ 把片段交给模型
→ 模型回答
→ 前端显示来源
```

## 第一步：提取文本

相关文件：

```text
backend/src/teachx/knowledge/extractors.py
```

上传文件最初是字节：

```python
content: bytes
```

模型无法直接检索 PDF 二进制。因此必须转换：

```python
text = extract_text(filename, content)
```

当前支持：

- `.txt`
- `.md`
- `.markdown`
- `.pdf`

PDF 使用 `pypdf` 逐页提取文本。扫描图片型 PDF 暂时没有 OCR，因此会明确报错。

## 第二步：文本切块

相关文件：

```text
backend/src/teachx/knowledge/chunker.py
```

为什么不把整本书作为一个检索单位？

假设一本书有 20 万字。如果整本书作为一个文本块，搜索“什么是 Agent Loop”时会
返回整本书，模型不知道该看哪里。

因此要把文本切成约 900 字的小块：

```python
chunks = chunker.chunk(text)
```

当前算法先按空行分段，再把相邻段落组合到接近 900 字。相邻块保留 120 字重叠，
避免答案刚好被切断。

## 第三步：存储和索引

数据库新增三张表：

```text
knowledge_bases      知识库
knowledge_documents  原始文档和提取文本
knowledge_chunks     文本块
```

另外建立 FTS5 虚拟表：

```sql
CREATE VIRTUAL TABLE knowledge_chunks_fts
USING fts5(content, chunk_id UNINDEXED, kb_name UNINDEXED);
```

FTS5 是 SQLite 内置的全文搜索模块。它不需要额外服务器，适合个人知识库和课设部署。

## 为什么暂时不用向量数据库

向量检索擅长理解“意思相近但词语不同”的问题，例如：

```text
“怎么让机器人调工具”
与
“Agent 如何执行 function calling”
```

但它需要 Embedding 模型、向量维度和额外存储。

P2 第一阶段先使用 FTS5：

- 部署简单。
- 没有额外 API 成本。
- 容易调试。
- 足以验证完整 RAG 链路。

以后可以在 `KnowledgeService.search()` 后面增加向量检索，而不需要修改 WebSocket、
Agent Loop 或前端聊天协议。这就是保持模块接缝清晰的价值。

## 第四步：模型调用知识检索工具

工具定义：

```text
backend/src/teachx/runtime/tools.py
```

模型看到的工具参数是：

```json
{
  "query": "Agent Loop 如何处理工具结果",
  "knowledge_bases": ["课程资料"],
  "limit": 5
}
```

KnowledgeSearchTool 调用：

```python
hits = await self.service.search(
    query,
    knowledge_bases,
    limit=limit,
)
```

## 第五步：把检索结果送回模型

检索结果不会凭空进入模型。AgentRuntime 把它作为 `tool` 消息追加：

```python
{
    "role": "tool",
    "tool_call_id": "search-1",
    "name": "knowledge_search",
    "content": "命中的资料片段...",
}
```

模型再次调用时，才能根据片段生成回答。

## 第六步：发送引用事件

除了普通 `tool_result`，TeachX 还会发送：

```json
{
  "type": "sources",
  "metadata": {
    "sources": [
      {
        "title": "agent-loop.md",
        "knowledge_base": "TeachX 教程资料",
        "chunk_index": 0,
        "snippet": "Agent Loop 会..."
      }
    ]
  }
}
```

前端可以根据这个事件绘制引用卡片。模型回答负责解释内容，`sources` 负责证明来源。

## 当前模块职责

```text
extractors.py  文件字节 → 纯文本
chunker.py     长文本 → 检索片段
service.py     创建、存储、搜索和删除
tools.py       knowledge_search 工具
engine.py      将检索接入 Agent Loop
```

这套拆分让每一层只做一件事，测试也更容易：

- 提取器测试 PDF/TXT 转换。
- Chunker 测试切块边界。
- Service 测试存储、搜索和删除。
- AgentRuntime 测试是否产生 `sources` 事件。

## 常见误区

### “只要上传文件，模型就会自动知道”

不会。必须检索到相关片段，并把片段放进本次模型调用。

### “FTS5 等于向量数据库”

不等于。FTS5 主要匹配词语，向量检索匹配语义。两者可以组合成混合检索。

### “分块越大越好”

块太大时噪声多，模型上下文成本高；块太小时上下文不足。需要根据资料类型调整。

### “引用只靠模型自己写”

不可靠。引用应该来自后端真实检索结果，而不是让模型编造文件名。

## 小练习

1. 上传一份 Markdown 课程笔记并搜索一个关键词。
2. 把 `TextChunker.max_chars` 改成 400，观察块数量变化。
3. 给 `.txt`、`.md`、`.pdf` 各写一个提取测试。
4. 在搜索结果中加入文档标题和章节标题。
5. 思考如何加入 Embedding 检索，并保持现有 `SearchHit` 接口不变。

## 自测题

1. 为什么不能直接检索 PDF 二进制？
2. 文档为什么要切成多个块？
3. `knowledge_search` 的结果为什么要作为 `tool` 消息送回模型？
4. `sources` 事件和模型回答分别负责什么？
5. 为什么把向量检索放在 `KnowledgeService` 后面，而不是改 WebSocket？
