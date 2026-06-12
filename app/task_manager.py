"""任务管理器 — 管理下载队列、并发控制、进度更新、SSE 推送。"""

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable

import app.database as db
from app.config import settings
from app.downloaders.huggingface import HuggingFaceDownloader
from app.downloaders.modelscope import ModelScopeDownloader
from app.models import DownloadTask, Platform, TaskStatus

logger = logging.getLogger(__name__)


class _DownloadCancelled(Exception):
    """下载被取消时在进度回调中抛出，用于中止下载线程。"""


# 数据库 tasks 表允许更新的列名白名单，防止 SQL 注入
VALID_COLUMNS = {
    "status",
    "progress",
    "speed",
    "downloaded",
    "total",
    "save_path",
    "error_msg",
    "updated_at",
}


class TaskManager:
    """管理所有下载任务的生命周期。

    职责:
    - 创建/取消/重试任务
    - 控制最大并发下载数
    - 调用对应平台的下载器执行下载
    - 通过 SSE 回调推送进度和状态变更
    """

    def __init__(self) -> None:
        self._running_count = 0
        self._tasks: dict[str, asyncio.Task] = {}  # task_id -> asyncio.Task
        self._cancel_events: dict[str, threading.Event] = {}  # task_id -> 取消信号
        self._on_event: list[Callable] = []  # SSE 事件回调列表

        # 下载器实例
        self._downloaders = {
            Platform.modelscope: ModelScopeDownloader(),
            Platform.huggingface: HuggingFaceDownloader(),
        }

    def add_event_callback(self, callback: Callable) -> None:
        """注册 SSE 事件回调，用于推送进度和状态变更。"""
        self._on_event.append(callback)

    def remove_event_callback(self, callback: Callable) -> None:
        """移除 SSE 事件回调。"""
        with contextlib.suppress(ValueError):
            self._on_event.remove(callback)

    async def _emit(self, event_type: str, task_id: str, **extra) -> None:
        """触发事件，通知所有 SSE 回调。"""
        data = {"type": event_type, "task_id": task_id, **extra}
        # 复制列表，防止迭代中修改
        for callback in list(self._on_event):
            try:
                callback(data)
            except Exception:
                logger.exception("SSE callback error")

    async def create_task(self, task_data: dict) -> dict:
        """创建下载任务并加入队列。"""
        task = DownloadTask(**task_data)
        task_dict = task.model_dump()

        # 持久化到数据库
        await db.insert_task(task_dict)

        # 通知前端新任务已创建
        await self._emit("task_created", task.id, status=task.status)

        # 尝试启动任务
        self._try_start(task.id)
        return task_dict

    async def cancel_task(self, task_id: str) -> bool:
        """取消正在运行的任务。"""
        task_record = await db.get_task(task_id)
        if not task_record:
            return False

        # 通知下载线程中止（在进度回调中检查）
        if task_id in self._cancel_events:
            self._cancel_events[task_id].set()

        # 取消 asyncio 任务（仅取消引用，_running_count 在 finally 中递减）
        if task_id in self._tasks:
            self._tasks[task_id].cancel()
            del self._tasks[task_id]

        await db.update_task(task_id, status=TaskStatus.cancelled)
        await self._emit("task_cancelled", task_id)
        return True

    async def retry_task(self, task_id: str) -> dict | None:
        """重试失败的任务。"""
        task_record = await db.get_task(task_id)
        if not task_record:
            return None
        allowed = (TaskStatus.failed, TaskStatus.cancelled)
        if task_record["status"] not in allowed:
            return None

        await db.update_task(task_id, status=TaskStatus.pending, progress=0, error_msg=None)
        self._try_start(task_id)
        await self._emit("task_retry", task_id)

        return await db.get_task(task_id)

    def _try_start(self, task_id: str) -> None:
        """如果当前并发数未达上限，启动任务；否则排队等待。"""
        if self._running_count >= settings.max_concurrent:
            return
        # 立即递增计数，关闭竞态窗口
        self._running_count += 1
        asyncio_task = asyncio.create_task(self._run_download(task_id))
        self._tasks[task_id] = asyncio_task

    def _schedule_next(self) -> None:
        """当有任务完成时，尝试启动排队的任务。"""
        asyncio.create_task(self._start_next_pending())

    async def _start_next_pending(self) -> None:
        """查找并启动下一个排队中的任务。"""
        if self._running_count >= settings.max_concurrent:
            return

        # ASC 排序，第一个即为最早的 pending 任务
        tasks = await db.list_tasks(status=TaskStatus.pending)
        if tasks:
            next_task = tasks[0]
            self._try_start(next_task["id"])

    async def _run_download(self, task_id: str) -> None:
        """执行单个下载任务（在 asyncio.Task 中运行）。"""
        cancel_event = threading.Event()
        self._cancel_events[task_id] = cancel_event

        task_record = await db.get_task(task_id)
        if not task_record:
            # 任务已被删除，回退计数
            self._running_count -= 1
            self._tasks.pop(task_id, None)
            self._cancel_events.pop(task_id, None)
            return

        platform = Platform(task_record["platform"])
        downloader = self._downloaders[platform]
        task = DownloadTask(**task_record)

        # 状态更新为 running
        await db.update_task(task_id, status=TaskStatus.running)
        await self._emit("task_started", task_id)

        # 进度回调
        async def on_progress(
            progress: float,
            speed: str,
            downloaded: int,
            total: int,
            current_file: str | None = None,
            files_total: int = 0,
            files_done: int = 0,
            files_json: str | None = None,
        ) -> None:
            fields = {
                "progress": progress,
                "speed": speed,
                "downloaded": downloaded,
                "total": total,
            }
            if current_file is not None:
                fields["current_file"] = current_file
            if files_total > 0:
                fields["files_total"] = files_total
            if files_done > 0:
                fields["files_done"] = files_done
            if files_json is not None:
                fields["files_json"] = files_json
            await db.update_task(task_id, **fields)
            await self._emit("task_progress", task_id, **fields)

        try:
            # 保存主线程的事件循环引用，供线程池中的同步回调使用
            loop = asyncio.get_running_loop()

            def sync_on_progress(
                progress: float,
                speed: str,
                downloaded: int,
                total: int,
                current_file: str | None = None,
                files_total: int = 0,
                files_done: int = 0,
                files_json: str | None = None,
            ) -> None:
                """线程安全的进度回调，从下载线程调度到主事件循环。"""
                # 检查取消信号，中止下载线程
                if cancel_event.is_set():
                    raise _DownloadCancelled("任务已取消")
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(
                        on_progress(
                            progress,
                            speed,
                            downloaded,
                            total,
                            current_file,
                            files_total,
                            files_done,
                            files_json,
                        ),
                        loop=loop,
                    )
                )

            save_path = await downloader.download(task, sync_on_progress)
            await db.update_task(
                task_id, status=TaskStatus.completed, progress=1.0, save_path=save_path
            )
            await self._emit("task_completed", task_id)

        except (asyncio.CancelledError, _DownloadCancelled):
            await db.update_task(task_id, status=TaskStatus.cancelled)
            await self._emit("task_cancelled", task_id)

        except Exception as e:
            logger.exception("Download failed for task %s", task_id)
            await db.update_task(task_id, status=TaskStatus.failed, error_msg=str(e))
            await self._emit("task_failed", task_id, error=str(e))

        finally:
            self._running_count -= 1
            self._tasks.pop(task_id, None)
            self._cancel_events.pop(task_id, None)
            self._schedule_next()


# 全局单例
task_manager = TaskManager()
