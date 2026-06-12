"""下载器基类 — 定义统一接口，子类实现具体平台下载逻辑。"""

import abc
from collections.abc import Callable

from app.models import DownloadTask


class BaseDownloader(abc.ABC):
    """下载器抽象基类，所有平台下载器必须实现 download 方法。"""

    @abc.abstractmethod
    async def download(
        self,
        task: DownloadTask,
        on_progress: Callable,  # (progress, speed, downloaded, total, **file_info)
    ) -> str:
        """执行下载。

        Args:
            task: 下载任务信息。
            on_progress: 进度回调函数，参数为 (progress, speed, downloaded, total)。

        Returns:
            本地保存路径。

        Raises:
            Exception: 下载失败时抛出异常。
        """
