# 08：Docker 部署

## 为什么需要 Docker

开发环境里需要安装：

- Python 3.12
- Node.js 22
- uv
- npm
- 系统编译工具

部署到另一台机器时，版本和系统差异会导致“在我电脑上能运行”的问题。

Docker 会把应用和运行环境一起打包：

```text
代码 + 依赖 + 启动命令 + 系统环境
→ Docker Image
→ Docker Container
```

## 三个核心概念

### Image 镜像

镜像是只读模板，例如：

```text
teachx-api
teachx-web
```

镜像中可以包含 Python、Node.js、系统库和项目代码。

### Container 容器

容器是镜像的运行实例。可以启动、停止、删除，也可以同时运行多个。

### Volume 数据卷

容器删除后，容器内部文件会丢失。  
Volume 用来持久化数据库和知识库原文。

TeachX 使用：

```text
teachx-data:/app/data
```

因此重新构建镜像不会丢失聊天记录和知识库。

## 后端 Dockerfile

文件：

```text
backend/Dockerfile
```

核心步骤：

```dockerfile
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev
COPY src ./src
```

含义：

1. 先复制依赖声明。
2. 安装锁定版本依赖。
3. 再复制源代码。

为什么先复制依赖文件？

Docker 会缓存每一层。如果只修改源代码，而依赖没有变化，就不需要重新安装全部包。

## 前端 Dockerfile

文件：

```text
frontend/Dockerfile
```

它使用多阶段构建：

```text
dependencies
→ 安装 npm 依赖

builder
→ 执行 Next.js 生产构建

runner
→ 只复制 standalone 运行产物
```

最终的 runner 不需要完整开发依赖，镜像更小，启动也更快。

## Docker Compose

文件：

```text
compose.yaml
```

它同时启动两个服务：

```text
api  → FastAPI，端口 8010
web  → Next.js，端口 3000
```

浏览器只访问 Web。Next.js 在容器网络中通过：

```text
http://api:8010
```

请求 FastAPI。

这里的 `api` 是 Compose 自动创建的 DNS 名称，不是公网域名。

## 启动方式

复制配置：

```bash
cp .env.docker.example .env
```

构建并启动：

```bash
docker compose up --build -d
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

停止容器：

```bash
docker compose down
```

删除容器时保留数据卷。

如果明确要删除全部数据：

```bash
docker compose down -v
```

这个命令会删除聊天记录和知识库数据，必须谨慎使用。

## 健康检查

后端健康接口：

```text
GET /health
```

Dockerfile 使用 Python 标准库检查：

```dockerfile
HEALTHCHECK ... urllib.request.urlopen(...)
```

前端容器会等待 API 健康后才启动：

```yaml
depends_on:
  api:
    condition: service_healthy
```

这样可以减少前端先启动、后端还没准备好的竞态。

## 环境变量

普通配置放在 `.env` 中，例如：

```bash
TEACHX_AUTH_ENABLED=true
TEACHX_AUTH_SECRET=至少32字节随机值
TEACHX_LLM_PROVIDER=openai
OPENAI_API_KEY=...
```

注意：

- `.env` 不应该提交到 Git。
- API Key 不能写进 Dockerfile。
- 正式 HTTPS 部署必须设置 `TEACHX_AUTH_COOKIE_SECURE=true`。
- Secret 应该使用随机值，而不是示例值。

## 当前验证边界

仓库已经提供：

- 后端 Dockerfile。
- 前端 Dockerfile。
- Compose 服务定义。
- 数据卷。
- 环境变量模板。
- 健康检查。

当前开发机器没有安装 Docker，因此 Compose YAML 已完成结构验证，但镜像还没有在这台机器上实机构建。  
在安装 Docker Desktop 后，应运行：

```bash
docker compose build
docker compose up -d
```

并通过真实健康检查确认。

这说明文档必须区分：

```text
配置已经写入仓库
≠
镜像已经在所有平台完成验证
```

## 常见问题

### 前端无法访问后端

检查：

```yaml
DEEPTUTOR_API_BASE_URL: http://api:8010
```

容器内部不能使用 `localhost:8010` 访问另一个容器。

### 重启后数据消失

检查 Volume 是否仍然存在：

```bash
docker volume ls
```

不要随意执行 `docker compose down -v`。

### 密码或 JWT 配置不安全

不要使用示例 Secret。生产环境必须通过部署平台注入随机 Secret。

### 构建很慢

第一次构建需要下载：

- Python 依赖
- Node 依赖
- Next.js 构建产物

后续修改源代码通常会复用缓存层。

## 为什么暂时还是 SQLite

当前容器中的数据库仍然是 SQLite，因为 PostgreSQL 迁移会涉及：

- 替换 `aiosqlite`
- 替换 FTS5
- 重写向量存储
- 增加迁移工具
- 兼容现有数据
- 重写测试数据库夹具

这是一次独立的存储层重构，不应和 Docker 打包混在同一个提交里。

下一阶段会增加 PostgreSQL，但不会直接删除 SQLite 开发模式。最佳方案是让 Repository 支持两种数据库适配器，并保留 SQLite 用于本地测试。

## 小练习

1. 执行 `docker compose config` 查看展开后的配置。
2. 创建一个已有名称的数据卷并验证数据持久化。
3. 修改服务端口，通过 `.env` 覆盖默认值。
4. 增加一个只读数据库备份服务。
5. 思考 PostgreSQL 迁移时应先改 Repository、KnowledgeService，还是同时改。

## 自测题

1. Image、Container 和 Volume 有什么区别？
2. 为什么后端 Dockerfile 先复制依赖文件？
3. 为什么容器之间不能使用 `localhost` 互相访问？
4. 前端为什么要等待后端健康？
5. `.env` 为什么不能直接提交？
