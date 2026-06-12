"""CLI 入口 — 解析命令行参数并启动服务。"""

import argparse
import logging

import uvicorn

from app.config import settings


def main() -> None:
    """model-download CLI 入口点。"""
    parser = argparse.ArgumentParser(description="Model Download Server — 大模型下载网页工具")
    parser.add_argument("--host", default=None, help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="监听端口 (默认: 8000)")
    parser.add_argument("--download-dir", default=None, help="下载目录 (默认: ./downloads)")
    parser.add_argument("--reload", action="store_true", help="开发模式，自动重载")
    args = parser.parse_args()

    # CLI 参数覆盖 .env
    settings.apply_cli(host=args.host, port=args.port, download_dir=args.download_dir)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
