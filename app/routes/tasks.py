"""任务 CRUD 路由 — 创建/查询/删除下载任务。"""

from fastapi import APIRouter, HTTPException

import app.database as db
from app.models import BatchDeleteResponse, MessageResponse, TaskCreate, TaskResponse
from app.task_manager import task_manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
async def create_task(body: TaskCreate):
    """创建下载任务。"""
    task_data = body.model_dump()
    result = await task_manager.create_task(task_data)
    return result


@router.get("", response_model=list[TaskResponse])
async def list_tasks(status: str | None = None):
    """获取任务列表，可按状态筛选。"""
    return await db.list_tasks(status)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """获取单个任务详情。"""
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}", response_model=MessageResponse)
async def delete_task(task_id: str):
    """取消或删除任务。进行中的任务会被取消，已结束的会被删除。"""
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 如果任务正在运行或排队中，先取消
    if task["status"] in ("running", "pending"):
        await task_manager.cancel_task(task_id)

    await db.delete_task(task_id)
    return MessageResponse(ok=True, message="Task deleted")


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: str):
    """重试失败的任务。"""
    result = await task_manager.retry_task(task_id)
    if not result:
        raise HTTPException(status_code=400, detail="Task cannot be retried")
    return result


@router.delete("", response_model=BatchDeleteResponse)
async def batch_delete_tasks(status: str):
    """按状态批量清理任务（仅允许清理终态任务）。"""
    # 只允许清理终态，禁止清理 running/pending
    if status not in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="只能清理已完成、失败或已取消的任务")

    deleted = await db.delete_tasks_by_status(status)
    return BatchDeleteResponse(deleted=deleted)
