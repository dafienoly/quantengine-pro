"""
QuantEngine Pro - Web Application Entry Point
===============================================
Launches the FastAPI backend + Plotly Dash dashboard.

Usage:
    python -m quantengine.web.app
    python -m quantengine.web.app --port 8050 --host 0.0.0.0
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger


def main():
    """Launch the QuantEngine Pro web application."""
    parser = argparse.ArgumentParser(
        description="QuantEngine Pro - Web Dashboard"
    )
    parser.add_argument("--port", type=int, default=8050, help="Dashboard port")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--api-port", type=int, default=8000, help="API server port")
    parser.add_argument("--debug", action="store_true", help="Debug mode")

    args = parser.parse_args()

    logger.info(
        f"Starting QuantEngine Pro Web Application...\n"
        f"  Dashboard: http://{args.host}:{args.port}\n"
        f"  API:       http://{args.host}:{args.api_port}\n"
        f"  API Docs:  http://{args.host}:{args.api_port}/docs"
    )

    try:
        from quantengine.web.dashboard import create_dashboard
        from quantengine.web.api import create_app

        import uvicorn
        import threading

        # Start FastAPI in background thread
        api_app = create_app()

        def run_api():
            uvicorn.run(
                api_app,
                host=args.host,
                port=args.api_port,
                log_level="info" if args.debug else "warning",
            )

        api_thread = threading.Thread(target=run_api, daemon=True)
        api_thread.start()
        logger.info(f"API server started on port {args.api_port}")

        # Start Dash dashboard (main thread)
        dashboard = create_dashboard()
        dashboard.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
        )

    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error(
            "Install with: pip install fastapi uvicorn dash plotly"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Failed to start web app: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
