"""ModelScope 下载器 — 封装 modelscope SDK 的下载逻辑，支持实时进度和子文件追踪。"""

import asyncio
import json
import os
import time
from collections.abc import Callable

from modelscope.hub.callback import ProgressCallback
from modelscope.hub.file_download import model_file_download
from modelscope.hub.snapshot_download import snapshot_download

from app.config import settings
from app.downloaders.base import BaseDownloader
from app.models import DownloadTask


class _FileProgressTracker:
    """跟踪多文件下载的整体进度和各文件状态。"""

    def __init__(self, on_progress: Callable, files_total: int = 0):
        self._on_progress = on_progress
        self._files_total = files_total
        self._files_done = 0
        self._completed_bytes = 0
        # {name: {size, downloaded, status}}
        self._files: dict[str, dict] = {}
        self._last_time = time.monotonic()
        self._last_overall_bytes = 0

    def register_file(self, filename: str, file_size: int) -> None:
        """注册新文件到追踪列表。"""
        self._files[filename] = {"size": file_size, "downloaded": 0, "status": "downloading"}
        self._files_total = len(self._files)

    def on_file_done(self, filename: str) -> None:
        """标记文件下载完成。"""
        if filename in self._files:
            info = self._files[filename]
            info["status"] = "done"
            info["downloaded"] = info["size"]
            self._completed_bytes += info["size"]
        self._files_done += 1

    def report(self, current_file: str, file_downloaded: int, file_total: int) -> None:
        """上报当前文件进度。"""
        now = time.monotonic()
        elapsed = now - self._last_time

        # 节流：每 0.5 秒上报一次（文件完成时立即上报）
        if elapsed < 0.5 and file_downloaded < file_total:
            return

        # 更新当前文件信息
        if current_file in self._files:
            self._files[current_file]["downloaded"] = file_downloaded
            self._files[current_file]["size"] = file_total

        # 整体字节 = 已完成文件字节 + 当前文件已下载字节
        overall_downloaded = self._completed_bytes + file_downloaded
        overall_total = self._completed_bytes + file_total

        speed = 0.0
        if elapsed > 0:
            speed = (overall_downloaded - self._last_overall_bytes) / elapsed

        self._last_time = now
        self._last_overall_bytes = overall_downloaded

        progress = min(overall_downloaded / overall_total, 1.0) if overall_total > 0 else 0
        speed_str = _format_speed(speed)

        # 序列化文件列表用于前端展开查看
        files_json = json.dumps([{"name": name, **info} for name, info in self._files.items()])

        self._on_progress(
            progress=progress,
            speed=speed_str,
            downloaded=overall_downloaded,
            total=overall_total,
            current_file=current_file,
            files_total=self._files_total,
            files_done=self._files_done,
            files_json=files_json,
        )


def _make_callback_class(tracker: _FileProgressTracker) -> type[ProgressCallback]:
    """创建一个 ProgressCallback 子类，闭包捕获文件追踪器。"""

    class _Callback(ProgressCallback):
        def __init__(self, filename: str, file_size: int):
            super().__init__(filename, file_size)
            self._downloaded = 0
            tracker.register_file(filename, file_size)

        def update(self, size: int) -> None:
            self._downloaded += size
            tracker.report(self.filename, self._downloaded, self.file_size)

        def end(self) -> None:
            tracker.on_file_done(self.filename)

    return _Callback


def _format_speed(speed: float) -> str:
    """将字节/秒转为可读速度字符串。"""
    if speed <= 0:
        return ""
    if speed < 1024:
        return f"{speed:.1f} B/s"
    if speed < 1024 * 1024:
        return f"{speed / 1024:.1f} KB/s"
    if speed < 1024 * 1024 * 1024:
        return f"{speed / 1024 / 1024:.1f} MB/s"
    return f"{speed / 1024 / 1024 / 1024:.2f} GB/s"


class ModelScopeDownloader(BaseDownloader):
    """ModelScope 平台下载器，使用 modelscope SDK。"""

    async def download(
        self,
        task: DownloadTask,
        on_progress: Callable,
    ) -> str:
        """下载 ModelScope 模型，支持整仓或单文件下载。"""
        kwargs = self._build_kwargs()
        save_dir = os.path.join(settings.download_dir, task.repo_id.replace("/", "_"))
        kwargs["cache_dir"] = save_dir

        try:
            if task.filename:
                # 单文件下载
                result = await asyncio.to_thread(
                    model_file_download,
                    model_id=task.repo_id,
                    file_path=task.filename,
                    **kwargs,
                )
            else:
                # 整仓快照下载，传入进度回调
                tracker = _FileProgressTracker(on_progress, files_total=0)
                kwargs["progress_callbacks"] = [_make_callback_class(tracker)]
                result = await asyncio.to_thread(
                    snapshot_download,
                    model_id=task.repo_id,
                    **kwargs,
                )

            on_progress(1.0, "", 0, 0)
            return str(result)

        except Exception as e:
            raise RuntimeError(f"ModelScope 下载失败: {e}") from e

    def _build_kwargs(self) -> dict:
        """构建 SDK 调用参数。"""
        kwargs: dict = {}
        if settings.ms_token:
            kwargs["token"] = settings.ms_token
        return kwargs
