"""MySQL Error Log Analyzer - 主入口模块

启动即 Web 模式，自动输出访问链接。
"""

import asyncio
import logging
import os
import signal
import socket
import sys

from src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def print_banner(host: str, port: int):
    """打印启动横幅"""
    local_ip = get_local_ip()
    is_localhost = host in ("127.0.0.1", "localhost", "0.0.0.0")

    banner = f"""
╔══════════════════════════════════════════════════════════╗
║        MySQL Error Log Analyzer  v1.0                   ║
║        MySQL 错误日志自动分析工具                         ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🌐 Web 界面已就绪，请在浏览器中访问：                     ║
║                                                          ║"""

    if is_localhost or host == "0.0.0.0":
        banner += f"""
║    ➜  本机访问:  http://127.0.0.1:{port}                  ║
║    ➜  局域网访问: http://{local_ip}:{port}"""
        # 补齐空格
        line_len = len(f"║    ➜  局域网访问: http://{local_ip}:{port}")
        padding = max(0, 58 - line_len)
        banner += " " * padding + "║\n"

    banner += f"""║                                                          ║
║  📋 功能说明:                                            ║
║    • 首页选择 MySQL → 进入分析界面                        ║
║    • 仪表盘 / 实时监控 / 慢查询 / 复制状态                ║
║    • 设置页面配置 LLM 和 Embedding                        ║
║                                                          ║
║  ⌨️  按 Ctrl+C 停止服务                                  ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)


def parse_args():
    """解析命令行参数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="MySQL Error Log Analyzer - MySQL错误日志自动分析工具"
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
        help="Web 服务端口（覆盖配置文件，默认 8080）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Web 服务监听地址（覆盖配置文件，默认 0.0.0.0）",
    )
    return parser.parse_args()


async def run_web(config: Config, host: str, port: int):
    """启动 Web 服务"""
    import uvicorn
    from src.web.app import create_app

    app = create_app()

    # 打印启动横幅
    print_banner(host, port)

    config_server = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",  # 只显示警告及以上，避免刷屏
        access_log=False,
    )
    server = uvicorn.Server(config_server)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(server.shutdown()))

    await server.serve()


def main():
    args = parse_args()

    # 加载配置
    config = Config.load(args.config)

    # 默认监听 0.0.0.0（允许局域网访问）
    host = args.host or config.get("web", "host", default="0.0.0.0")
    port = args.port or config.get("web", "port", default=8080)

    logger.info("MySQL Error Log Analyzer 启动中...")

    try:
        asyncio.run(run_web(config, host, port))
    except KeyboardInterrupt:
        print("\n服务已停止")
    except Exception as e:
        logger.error("程序异常退出: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
