"""SSE 事件流路由 — 实时推送任务进度和状态变更。"""

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.task_manager import task_manager

router = APIRouter(tags=["events"])


@router.get("/api/tasks/{task_id}/progress")
async def task_progress(task_id: str, request: Request):
    """单任务进度 SSE 流。"""

    async def event_generator():
        queue = asyncio.Queue()

        def callback(data: dict):
            if data.get("task_id") == task_id:
                queue.put_nowait(data)

        task_manager.add_event_callback(callback)

        try:
            while True:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"data": json.dumps(data)}
                    # 任务终态时结束流
                    if data.get("type") in ("task_completed", "task_failed", "task_cancelled"):
                        break
                except TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            task_manager.remove_event_callback(callback)

    return EventSourceResponse(event_generator())


@router.get("/api/events")
async def global_events(request: Request):
    """全局事件 SSE 流，推送所有任务的状态变更。"""

    async def event_generator():
        queue = asyncio.Queue()

        def callback(data: dict):
            queue.put_nowait(data)

        task_manager.add_event_callback(callback)

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"data": json.dumps(data)}
                except TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            task_manager.remove_event_callback(callback)

    return EventSourceResponse(event_generator())
