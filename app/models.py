"""Pydantic 数据模型 — 请求/响应/内部数据结构。"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class Platform(StrEnum):
    """下载平台。"""

    modelscope = "modelscope"
    huggingface = "huggingface"


class TaskStatus(StrEnum):
    """任务状态生命周期。"""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# ---------- 请求模型 ----------


class TaskCreate(BaseModel):
    """创建下载任务请求。"""

    repo_id: str
    filename: str | None = None
    platform: Platform = Platform.modelscope
    use_proxy: bool = False
    use_mirror: bool = False

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, v: str) -> str:
        """校验仓库地址格式，防止路径注入。"""
        v = v.strip()
        if not v or not all(c.isalnum() or c in "_./-@" for c in v):
            raise ValueError("仓库地址包含非法字符")
        if ".." in v:
            raise ValueError("仓库地址不能包含路径穿越")
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str | None) -> str | None:
        """校验文件名格式，防止路径注入。"""
        if v is None:
            return v
        v = v.strip()
        if not v or not all(c.isalnum() or c in "_./- " for c in v):
            raise ValueError("文件名包含非法字符")
        if ".." in v or v.startswith("/"):
            raise ValueError("文件名不能包含路径穿越")
        return v


# ---------- 响应模型 ----------


class TaskResponse(BaseModel):
    """任务详情响应。"""

    id: str
    repo_id: str
    filename: str | None = None
    platform: str
    status: str
    progress: float = 0.0
    speed: str | None = None
    downloaded: int = 0
    total: int = 0
    save_path: str | None = None
    error_msg: str | None = None
    current_file: str | None = None
    files_total: int = 0
    files_done: int = 0
    files_json: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ConfigResponse(BaseModel):
    """前端可用配置。"""

    has_hf_token: bool
    has_ms_token: bool
    has_proxy: bool
    has_mirror: bool
    max_concurrent: int


class MessageResponse(BaseModel):
    """通用消息响应。"""

    ok: bool = True
    message: str = ""


class BatchDeleteResponse(BaseModel):
    """批量删除响应。"""

    deleted: int


# ---------- 内部模型 ----------


class DownloadTask(BaseModel):
    """内部下载任务，用于 TaskManager。"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    repo_id: str
    filename: str | None = None
    platform: Platform = Platform.modelscope
    status: TaskStatus = TaskStatus.pending
    progress: float = 0.0
    speed: str | None = None
    downloaded: int = 0
    total: int = 0
    save_path: str | None = None
    error_msg: str | None = None
    use_proxy: bool = False
    use_mirror: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
