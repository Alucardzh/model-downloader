"""应用配置模块 — 从 CLI 参数 / .env / 默认值 加载配置，优先级递减。"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    return int(val) if val else default


def _env_bool(key: str) -> bool:
    return bool(os.getenv(key))


@dataclass
class Settings:
    """全局配置，CLI 参数会覆盖 .env 值。"""

    # Token
    hf_token: str = field(default_factory=lambda: _env("HF_TOKEN"))
    ms_token: str = field(default_factory=lambda: _env("MS_TOKEN"))

    # 代理与镜像
    hf_proxy: str = field(default_factory=lambda: _env("HF_PROXY"))
    hf_mirror: str = field(default_factory=lambda: _env("HF_MIRROR"))

    # 下载
    download_dir: str = field(default_factory=lambda: _env("DOWNLOAD_DIR", "./downloads"))
    max_concurrent: int = field(default_factory=lambda: _env_int("MAX_CONCURRENT_DOWNLOADS", 3))

    # 服务
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))

    # 只读属性：前端用来判断开关是否可用
    @property
    def has_hf_token(self) -> bool:
        return bool(self.hf_token)

    @property
    def has_ms_token(self) -> bool:
        return bool(self.ms_token)

    @property
    def has_proxy(self) -> bool:
        return bool(self.hf_proxy)

    @property
    def has_mirror(self) -> bool:
        return bool(self.hf_mirror)

    def apply_cli(
        self,
        host: str | None = None,
        port: int | None = None,
        download_dir: str | None = None,
    ) -> None:
        """CLI 参数覆盖 .env 值。"""
        if host:
            self.host = host
        if port:
            self.port = port
        if download_dir:
            self.download_dir = download_dir


settings = Settings()
