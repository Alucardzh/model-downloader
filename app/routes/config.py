"""配置查询路由 — 前端用来获取可用配置状态。"""

from fastapi import APIRouter

from app.config import settings
from app.models import ConfigResponse

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
async def get_config():
    """返回前端可用的配置状态（Token/Proxy/Mirror 是否已配置）。"""
    return ConfigResponse(
        has_hf_token=settings.has_hf_token,
        has_ms_token=settings.has_ms_token,
        has_proxy=settings.has_proxy,
        has_mirror=settings.has_mirror,
        max_concurrent=settings.max_concurrent,
    )
