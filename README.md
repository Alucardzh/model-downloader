# Model Downloader — 大模型下载网页工具

通过浏览器界面下载 HuggingFace / ModelScope 上的大模型文件，适合部署在 NAS 上个人使用。

## 功能

- 支持 **ModelScope**（默认主源）和 **HuggingFace** 双平台下载
- **实时进度**：整体进度条 + 下载速度 + 单文件进度（可展开查看）
- **多任务并行下载**，可配置最大并发数
- **任务管理**：取消、重试、删除、批量清理
- **HuggingFace 网络选项**：镜像（默认）/ 代理 / 直连，三选一
- **缓存续传**：已下载的完整文件自动跳过，中断后重试只需下载剩余文件
- Token 通过 `.env` 安全配置，不暴露在页面

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | 纯 HTML / CSS / JS，无框架 |
| 后端 | FastAPI + uvicorn |
| 数据库 | SQLite (Tortoise ORM) |
| 实时通信 | SSE (Server-Sent Events) |
| 下载引擎 | modelscope SDK + huggingface_hub SDK |
| 环境管理 | uv + pyproject.toml |

## 快速开始

### 1. 安装依赖

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
cd hfdownload
uv sync
```

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env` 填入你的配置：

```env
# Token（按需填写，不需要的可留空）
HF_TOKEN=hf_xxxxx
MS_TOKEN=

# HF 代理（留空则不使用）
HF_PROXY=http://127.0.0.1:7890

# HF 国内镜像（推荐 hf-mirror.com）
HF_MIRROR=https://hf-mirror.com

# 下载目录
DOWNLOAD_DIR=./downloads

# 最大并发下载数
MAX_CONCURRENT_DOWNLOADS=3

# 服务配置
HOST=0.0.0.0
PORT=8000
```

### 3. 启动

```bash
uv run model-download
```

自定义参数：

```bash
uv run model-download --host 0.0.0.0 --port 9000 --download-dir /data/models
```

开发模式（自动重载）：

```bash
uv run model-download --reload
```

### 4. 使用

浏览器打开 `http://localhost:8000`，在页面中：

1. 输入仓库地址（如 `ZhipuAI/glm-4`）
2. 可选填具体文件名（留空则下载整个仓库）
3. 选择下载平台（ModelScope 默认 / HuggingFace）
4. HuggingFace 平台可选网络方式：镜像（默认）、代理、直连
5. 点击「开始下载」

## 项目结构

```
hfdownload/
├── .env.example              # 配置模板
├── pyproject.toml            # 项目配置 + CLI 入口
├── app/
│   ├── cli.py                # CLI 入口点
│   ├── main.py               # FastAPI 应用 + 静态文件托管
│   ├── config.py             # 配置加载 (CLI > .env > 默认值)
│   ├── database.py           # Tortoise ORM 模型 + CRUD
│   ├── models.py             # Pydantic 数据模型 + 输入校验
│   ├── task_manager.py       # 任务队列 + 并发控制 + 线程安全取消
│   ├── downloaders/
│   │   ├── base.py           # 下载器抽象基类
│   │   ├── modelscope.py     # ModelScope SDK 下载器
│   │   └── huggingface.py    # HuggingFace SDK 下载器
│   └── routes/
│       ├── tasks.py          # 任务 CRUD API
│       ├── events.py         # SSE 实时事件流
│       └── config.py         # 前端配置查询
├── static/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
└── downloads/                # 下载目录（自动创建）
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks` | 创建下载任务 |
| `GET` | `/api/tasks` | 获取任务列表（`?status=running`） |
| `GET` | `/api/tasks/{id}` | 获取任务详情 |
| `DELETE` | `/api/tasks/{id}` | 取消/删除任务 |
| `POST` | `/api/tasks/{id}/retry` | 重试失败任务 |
| `DELETE` | `/api/tasks?status=completed` | 批量清理任务 |
| `GET` | `/api/tasks/{id}/progress` | 单任务进度 SSE 流 |
| `GET` | `/api/events` | 全局事件 SSE 流 |
| `GET` | `/api/config` | 前端可用配置状态 |

## 配置优先级

CLI 参数 > `.env` 文件 > 默认值

## 开发

```bash
# 代码检查
uv run ruff check app/

# 自动修复 + 格式化
uv run ruff check app/ --fix && uv run ruff format app/

# 开发模式启动
uv run model-download --reload
```

## License

MIT
