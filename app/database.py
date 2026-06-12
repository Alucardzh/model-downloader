"""数据库模块 — 使用 Tortoise ORM 管理 SQLite。

提供任务 CRUD 操作，接口返回 dict，对上层透明。
"""

from tortoise import Tortoise, fields
from tortoise.models import Model


class Task(Model):
    """下载任务 ORM 模型。"""

    id = fields.CharField(max_length=32, primary_key=True)
    repo_id = fields.CharField(max_length=255)
    filename = fields.CharField(max_length=512, null=True)
    platform = fields.CharField(max_length=32, default="modelscope")
    status = fields.CharField(max_length=32, default="pending")
    progress = fields.FloatField(default=0)
    speed = fields.CharField(max_length=64, null=True)
    downloaded = fields.IntField(default=0)
    total = fields.IntField(default=0)
    save_path = fields.CharField(max_length=1024, null=True)
    error_msg = fields.TextField(null=True)
    current_file = fields.CharField(max_length=512, null=True)
    files_total = fields.IntField(default=0)
    files_done = fields.IntField(default=0)
    use_proxy = fields.BooleanField(default=False)
    use_mirror = fields.BooleanField(default=False)
    files_json = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tasks"


# 允许通过 update_task 更新的字段白名单，防止注入
VALID_UPDATE_FIELDS = {
    "status",
    "progress",
    "speed",
    "downloaded",
    "total",
    "save_path",
    "error_msg",
    "current_file",
    "files_total",
    "files_done",
    "files_json",
}


async def init_db() -> None:
    """初始化 Tortoise ORM，启用 WAL 模式。"""
    await Tortoise.init(
        db_url="sqlite://data.db",
        modules={"models": ["app.database"]},
    )
    # 启用 WAL 模式，允许并发读写
    conn = Tortoise.get_connection("default")
    await conn.execute_query("PRAGMA journal_mode=WAL")
    await conn.execute_query("PRAGMA busy_timeout=5000")
    # 自动建表
    await Tortoise.generate_schemas()


async def close_db() -> None:
    """关闭所有数据库连接。"""
    await Tortoise.close_connections()


def _task_to_dict(task: Task) -> dict:
    """将 ORM 实例转为字典。"""
    return {
        "id": task.id,
        "repo_id": task.repo_id,
        "filename": task.filename,
        "platform": task.platform,
        "status": task.status,
        "progress": task.progress,
        "speed": task.speed,
        "downloaded": task.downloaded,
        "total": task.total,
        "save_path": task.save_path,
        "error_msg": task.error_msg,
        "current_file": task.current_file,
        "files_total": task.files_total,
        "files_done": task.files_done,
        "files_json": task.files_json,
        "use_proxy": task.use_proxy,
        "use_mirror": task.use_mirror,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


async def insert_task(task: dict) -> None:
    """插入一条下载任务记录。"""
    await Task.create(
        id=task["id"],
        repo_id=task["repo_id"],
        filename=task.get("filename"),
        platform=task.get("platform", "modelscope"),
        status=task.get("status", "pending"),
        progress=task.get("progress", 0),
        speed=task.get("speed"),
        downloaded=task.get("downloaded", 0),
        total=task.get("total", 0),
        save_path=task.get("save_path"),
        error_msg=task.get("error_msg"),
        use_proxy=task.get("use_proxy", False),
        use_mirror=task.get("use_mirror", False),
    )


async def update_task(task_id: str, **fields) -> None:
    """更新任务的指定字段（白名单过滤）。"""
    safe = {k: v for k, v in fields.items() if k in VALID_UPDATE_FIELDS}
    if not safe:
        return
    await Task.filter(id=task_id).update(**safe)


async def get_task(task_id: str) -> dict | None:
    """获取单条任务记录。"""
    task = await Task.get_or_none(id=task_id)
    return _task_to_dict(task) if task else None


async def list_tasks(status: str | None = None) -> list[dict]:
    """获取任务列表，可按状态筛选。"""
    if status and status != "all":
        qs = Task.filter(status=status).order_by("created_at")
    else:
        qs = Task.all().order_by("created_at")
    tasks = await qs
    return [_task_to_dict(t) for t in tasks]


async def delete_task(task_id: str) -> bool:
    """删除单条任务记录，返回是否成功。"""
    count = await Task.filter(id=task_id).delete()
    return count > 0


async def delete_tasks_by_status(status: str) -> int:
    """按状态批量删除任务，返回删除数量。"""
    count = await Task.filter(status=status).delete()
    return count
