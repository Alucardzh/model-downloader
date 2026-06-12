# 大模型下载网页工具 — 设计文档

## 概述

一个轻量级 Web 工具，通过浏览器界面下载 HuggingFace / ModelScope 上的大模型文件，部署在 NAS 上供个人使用。

## 技术决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 架构 | 单进程 + asyncio | 部署简单，资源占用低，适合 NAS |
| 后端框架 | FastAPI + uvicorn | 原生 async，SSE 支持好 |
| 下载方式 | Python SDK | modelscope / huggingface_hub SDK 回调获取进度 |
| 实时通信 | SSE (Server-Sent Events) | 单向推送，实现简单 |
| 前端 | 纯 HTML/CSS/JS | Nginx-free，FastAPI 直接托管静态文件 |
| 数据存储 | SQLite (aiosqlite) | 轻量，无需额外服务 |
| 环境管理 | uv + pyproject.toml | 一行启动，CLI 入口 |
| Token 管理 | .env 文件 | 不在页面暴露 |
| Proxy/Mirror | .env 配置值，前端仅开关 | 部署时配置，使用时切换 |

## 下载源策略

- **ModelScope 为默认主源**
- **HuggingFace 为备选源**，用户也可手动选择
- 顺序：用户选平台 → 指定平台下载；不指定 → ModelScope 优先

## 数据模型

```sql
CREATE TABLE tasks (
    id          TEXT PRIMARY KEY,
    repo_id     TEXT NOT NULL,
    filename    TEXT,
    platform    TEXT NOT NULL DEFAULT 'modelscope',
    status      TEXT NOT NULL DEFAULT 'pending',
    progress    REAL DEFAULT 0,
    speed       TEXT,
    downloaded  INTEGER DEFAULT 0,
    total       INTEGER DEFAULT 0,
    save_path   TEXT,
    error_msg   TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

status 生命周期: `pending → running → completed | failed | cancelled`

## API 设计

### REST API

```
POST   /api/tasks                  创建下载任务
       Body: { repo_id, filename?, platform, use_proxy?, use_mirror? }

GET    /api/tasks                  任务列表
       Query: ?status=running|completed|failed|all

GET    /api/tasks/{id}             任务详情

DELETE /api/tasks/{id}             取消/删除单个任务

DELETE /api/tasks                  批量清理
       Query: ?status=completed|failed

GET    /api/config                 前端可用配置
       Response: { has_hf_token, has_ms_token, has_proxy, has_mirror, max_concurrent }
```

### SSE

```
GET    /api/tasks/{id}/progress    单任务进度流
       Event: { progress, speed, downloaded, total }

GET    /api/events                 全局事件流
       Event: { type, task_id, ... }
```

## .env 配置

```env
HF_TOKEN=hf_xxxxx
MS_TOKEN=xxxxx
HF_PROXY=http://127.0.0.1:7890
HF_MIRROR=https://hf-mirror.com
DOWNLOAD_DIR=./downloads
MAX_CONCURRENT_DOWNLOADS=3
HOST=0.0.0.0
PORT=8000
```

配置优先级: **CLI 参数 > .env > 默认值**

## 前端 UI

单页面，两大区域：

**新建任务表单：**
- 仓库地址（必填）+ 文件名（选填）
- 平台下拉选择（ModelScope 默认 / HuggingFace）
- 代理开关 + 镜像开关（.env 未配置则置灰）
- 开始下载按钮

**任务列表：**
- 状态筛选 Tab（全部 / 下载中 / 已完成 / 失败）
- 清理记录按钮（按状态批量删除）
- 任务卡片：仓库名、平台、状态标签、进度条、速度、大小
  - 下载中：进度条 + 取消按钮
  - 已完成：保存路径 + 删除按钮
  - 失败：错误信息 + 重试/删除按钮

顶栏显示配置可用状态（Token/Proxy/Mirror 是否已配置）。

## 项目结构

```
hfdownload/
├── .env.example
├── .gitignore
├── .python-version
├── pyproject.toml
├── readme.md
│
├── app/
│   ├── __init__.py
│   ├── cli.py                 # CLI 入口 (argparse)
│   ├── main.py                # FastAPI app + StaticFiles 挂载
│   ├── config.py              # 配置加载 (CLI > .env > 默认值)
│   ├── database.py            # SQLite 初始化 + CRUD
│   ├── models.py              # Pydantic 数据模型
│   ├── task_manager.py        # 任务管理器 (队列/并发/进度/SSE)
│   ├── downloaders/
│   │   ├── __init__.py
│   │   ├── base.py            # 下载器基类
│   │   ├── modelscope.py      # ModelScope SDK 下载器
│   │   └── huggingface.py     # HuggingFace SDK 下载器
│   └── routes/
│       ├── __init__.py
│       ├── tasks.py           # 任务 CRUD API
│       ├── events.py          # SSE 事件流
│       └── config.py          # 配置查询 API
│
├── static/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
│
└── downloads/
```

## CLI

```bash
uv run model-download --host 0.0.0.0 --port 8000 --download-dir ./downloads
```

pyproject.toml 中定义:
```toml
[project.scripts]
model-download = "app.cli:main"
```

## 多任务并发

- TaskManager 维护 asyncio 任务队列
- 最大并发数由 MAX_CONCURRENT_DOWNLOADS 控制（默认 3）
- 超出并发的任务保持 pending 状态排队等待
- 前端通过 SSE 实时感知任务状态变化

## 部署流程

```bash
git clone <repo> && cd hfdownload
cp .env.example .env           # 编辑填入 Token/Proxy/Mirror
uv run model-download          # 启动服务
# 浏览器打开 http://nas-ip:8000
```

## 依赖

```
fastapi
uvicorn[standard]
aiosqlite
modelscope
huggingface_hub
python-dotenv
```
