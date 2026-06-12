"""FastAPI 应用入口 — 挂载路由、静态文件、生命周期事件。"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from tortoise import Tortoise
from tortoise.contrib.fastapi import RegisterTortoise

from app.config import settings

# 注册路由
from app.routes import config, events, tasks


# 静态文件目录必须在启动前存在
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if not os.path.isdir(STATIC_DIR):
    raise RuntimeError(f"Static directory not found: {STATIC_DIR}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库和下载目录。"""
    # 确保下载目录存在
    os.makedirs(settings.download_dir, exist_ok=True)

    # 初始化 Tortoise ORM（包含 WAL 设置和自动建表）
    async with RegisterTortoise(
        app,
        db_url="sqlite://data.db",
        modules={"models": ["app.database"]},
        generate_schemas=True,
    ):
        # WAL 模式 + busy timeout

        conn = Tortoise.get_connection("default")
        await conn.execute_query("PRAGMA journal_mode=WAL")
        await conn.execute_query("PRAGMA busy_timeout=5000")
        yield


app = FastAPI(title="Model Downloader", lifespan=lifespan)


app.include_router(tasks.router)
app.include_router(events.router)
app.include_router(config.router)

# 静态文件挂载（必须在路由之后，避免 /api/* 被静态文件拦截）
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
