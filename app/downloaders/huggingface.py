"""HuggingFace 下载器 — 封装 huggingface_hub SDK 的下载逻辑，支持实时进度和子文件追踪。"""

import asyncio
import json
import os
import time
from collections.abc import Callable
from typing import Any

from huggingface_hub import HfApi, hf_hub_download
from tqdm.std import tqdm as base_tqdm

from app.config import settings
from app.downloaders.base import BaseDownloader
from app.models import DownloadTask


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


class _FileProgressTracker:
    """跟踪多文件下载的整体进度和各文件状态。"""

    def __init__(self, on_progress: Callable):
        self._on_progress = on_progress
        self._files_done = 0
        self._completed_bytes = 0
        # {name: {size, downloaded, status}}
        self._files: dict[str, dict] = {}
        self._last_time = time.monotonic()
        self._last_overall_bytes = 0
        # 调用方在 hf_hub_download 前设置的完整文件名（绕过 SDK 截断）
        self.pending_file: str | None = None

    def register_file(self, filename: str, file_size: int) -> None:
        """注册新文件到追踪列表。"""
        if filename not in self._files:
            self._files[filename] = {"size": file_size, "downloaded": 0, "status": "downloading"}

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
            files_total=len(self._files),
            files_done=self._files_done,
            files_json=files_json,
        )


def _make_tqdm_wrapper(tracker: _FileProgressTracker) -> type:
    """创建 tqdm 兼容的包装类（组合模式，避免继承 MRO 冲突）。"""

    class _ProgressWrapper:
        """代理真实 tqdm 实例，拦截 update/close 上报进度。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._bar = base_tqdm(*args, **kwargs)
            self._is_file_bar = (
                kwargs.get("unit") == "B" and self._bar.total and self._bar.total > 0
            )
            if self._is_file_bar:
                # 优先使用 tracker.pending_file（完整名），绕过 SDK 40 字符截断
                real_name = tracker.pending_file or (
                    str(self._bar.desc).strip() if self._bar.desc else None
                )
                if real_name:
                    tracker.register_file(real_name, self._bar.total)
                    self._real_name = real_name

        def update(self, n: float | None = 1) -> bool | None:
            """更新进度"""
            result = self._bar.update(n)
            if self._is_file_bar and hasattr(self, "_real_name"):
                tracker.report(
                    self._real_name,
                    int(self._bar.n),
                    self._bar.total or 0,
                )
            return result

        def close(self) -> None:
            """关闭进度条"""
            if (
                self._is_file_bar
                and hasattr(self, "_real_name")
                and self._bar.total
                and self._bar.n >= self._bar.total
            ):
                tracker.on_file_done(self._real_name)
            self._bar.close()

        def __enter__(self):  # type: ignore[self-type]
            return self

        def __exit__(self, *args: Any) -> None:
            self.close()

        def __getattr__(self, name: str) -> Any:
            """转发未定义的属性到真实 tqdm 实例（如 total、n、desc）。"""
            if name.startswith("_"):
                raise AttributeError(name)
            return getattr(self._bar, name)

    return _ProgressWrapper


class HuggingFaceDownloader(BaseDownloader):
    """HuggingFace 平台下载器，使用 huggingface_hub SDK。"""

    async def download(
        self,
        task: DownloadTask,
        on_progress: Callable,
    ) -> str:
        """下载 HuggingFace 模型，支持整仓或单文件下载。"""
        kwargs = self._build_kwargs()
        save_dir = os.path.join(settings.download_dir, task.repo_id.replace("/", "_"))

        # 创建文件进度追踪器
        tracker = _FileProgressTracker(on_progress)
        kwargs["tqdm_class"] = _make_tqdm_wrapper(tracker)

        if task.use_mirror and settings.hf_mirror:
            kwargs["endpoint"] = settings.hf_mirror

        # 代理通过环境变量设置（hf_hub_download 不接受 proxies 参数）
        old_env = self._set_proxy_env(task)

        try:
            if task.filename:
                # 单文件下载：设置 pending_file 避免截断
                tracker.pending_file = task.filename
                result = await asyncio.to_thread(
                    hf_hub_download,
                    repo_id=task.repo_id,
                    filename=task.filename,
                    local_dir=save_dir,
                    **kwargs,
                )
                tracker.pending_file = None
            else:
                # 不用 snapshot_download（它会吞掉单文件进度），
                # 改为手动列出文件后逐个下载
                result = await asyncio.to_thread(
                    self._download_all_files,
                    task.repo_id,
                    save_dir,
                    kwargs,
                    tracker,
                )

            on_progress(1.0, "", 0, 0)
            return str(result)

        except Exception as e:
            raise RuntimeError(f"HuggingFace 下载失败: {e}") from e

        finally:
            self._restore_proxy_env(old_env)

    @staticmethod
    def _download_all_files(
        repo_id: str, save_dir: str, download_kwargs: dict, tracker: _FileProgressTracker
    ) -> str:
        """获取文件列表后逐个下载，确保每个文件都有独立的进度上报。"""
        api_kwargs = {}
        for key in ("token", "endpoint"):
            if key in download_kwargs:
                api_kwargs[key] = download_kwargs[key]

        api = HfApi(**api_kwargs)
        info = api.model_info(repo_id, files_metadata=True)
        files = [f for f in (info.siblings or []) if not f.rfilename.startswith(".")]

        for f in files:
            # 设置完整文件名，绕过 SDK 内部的 40 字符截断
            tracker.pending_file = f.rfilename
            hf_hub_download(
                repo_id=repo_id,
                filename=f.rfilename,
                local_dir=save_dir,
                **download_kwargs,
            )
        tracker.pending_file = None

        return save_dir

    @staticmethod
    def _set_proxy_env(task: DownloadTask) -> dict[str, str | None]:
        """设置代理环境变量，返回旧值用于恢复。"""
        old: dict[str, str | None] = {}
        if not (task.use_proxy and settings.hf_proxy):
            return old
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            old[key] = os.environ.get(key)
        os.environ["http_proxy"] = settings.hf_proxy
        os.environ["https_proxy"] = settings.hf_proxy
        return old

    @staticmethod
    def _restore_proxy_env(old: dict[str, str | None]) -> None:
        """恢复代理环境变量。"""
        for key, val in old.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def _build_kwargs(self) -> dict:
        """构建 SDK 调用参数，处理 Token。"""
        kwargs: dict = {}
        if settings.hf_token:
            kwargs["token"] = settings.hf_token
        return kwargs
