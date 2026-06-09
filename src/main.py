"""MySQL Error Log Analyzer - 主入口模块"""

import argparse
import asyncio
import logging
import signal
import sys

from src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="MySQL Error Log Analyzer - MySQL错误日志自动分析工具"
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Web 可视化界面（默认仅 CLI 模式）",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="启动 CLI 交互界面（默认启用）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="配置文件路径（默认自动查找 config.yaml）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Web 服务端口（覆盖配置文件）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Web 服务监听地址（覆盖配置文件）",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="以守护进程模式运行（仅 Web，无 CLI）",
    )
    return parser.parse_args()


async def run_cli_only(config: Config):
    """仅运行 CLI 模式"""
    from src.cli.interface import CLIInterface

    cli = CLIInterface(config)
    try:
        await cli.start()
    except KeyboardInterrupt:
        await cli.stop()


async def run_web_only(config: Config, host: str, port: int):
    """仅运行 Web 模式"""
    import uvicorn
    from src.web.app import create_app

    app = create_app(config)
    logger.info(f"Web 服务启动: http://{host}:{port}")
    config_server = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config_server)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(server.shutdown()))

    await server.serve()


async def run_both(config: Config, host: str, port: int):
    """同时运行 CLI 和 Web"""
    import uvicorn
    from src.cli.interface import CLIInterface
    from src.web.app import create_app

    app = create_app(config)
    config_server = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config_server)

    # 启动 Web 服务（后台运行）
    web_task = asyncio.create_task(server.serve())
    logger.info(f"Web 服务启动: http://{host}:{port}")

    # 启动 CLI（前台运行）
    cli = CLIInterface(config)
    try:
        await cli.start()
    except KeyboardInterrupt:
        pass
    finally:
        await cli.stop()
        server.should_exit = True
        await web_task


def main():
    args = parse_args()

    # 加载配置
    config = Config.load(args.config)

    # 命令行参数覆盖配置
    host = args.host or config.get("web", "host", default="127.0.0.1")
    port = args.port or config.get("web", "port", default=8080)

    # 守护进程模式：仅 Web
    if args.daemon:
        args.web = True
        args.cli = False

    # 默认：仅 CLI
    if not args.web and not args.cli:
        args.cli = True

    logger.info("MySQL Error Log Analyzer 启动中...")
    logger.info(f"模式: {'Web' if args.web else ''}{'CLI' if args.cli else ''}{' + ' if args.web and args.cli else ''}")

    try:
        if args.web and args.cli:
            asyncio.run(run_both(config, host, port))
        elif args.web:
            asyncio.run(run_web_only(config, host, port))
        else:
            asyncio.run(run_cli_only(config))
    except KeyboardInterrupt:
        logger.info("程序已停止")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
