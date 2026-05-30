"""
QuantEngine Pro - Web Application Entry Point
===============================================
Launches FastAPI backend + Plotly Dash dashboard.

Usage:
    python -m quantengine.web.app --port 8050 --host 0.0.0.0
"""

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger


def main():
    """Launch QuantEngine Pro web application."""
    parser = argparse.ArgumentParser(description="量化引擎专业版 - Web 看板")
    parser.add_argument("--port", type=int, default=8050, help="看板端口")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--api-port", type=int, default=8000, help="API 服务端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    logger.info(
        f"正在启动量化引擎专业版...\n"
        f"  看板: http://{args.host}:{args.port}\n"
        f"  API:  http://{args.host}:{args.api_port}\n"
        f"  API 文档: http://{args.host}:{args.api_port}/docs"
    )

    try:
        from quantengine.web.dashboard import create_dashboard
        from quantengine.web.api import create_app
        import uvicorn

        # Start FastAPI in background thread
        api_app = create_app()

        def run_api():
            uvicorn.run(api_app, host=args.host, port=args.api_port,
                       log_level="info" if args.debug else "warning")

        api_thread = threading.Thread(target=run_api, daemon=True)
        api_thread.start()
        logger.info(f"API 服务已启动，端口: {args.api_port}")

        # Start Dash (main thread)
        dashboard = create_dashboard()
        dashboard.run(host=args.host, port=args.port, debug=args.debug)

    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        logger.error("请安装依赖: pip install fastapi uvicorn dash plotly")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("正在关闭...")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
