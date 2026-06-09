"""CLI 交互界面模块"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from src.analyzer.graph import AnalysisGraph
from src.collector.discover import MySQLLogDiscover
from src.collector.parser import LogParser
from src.collector.reader import LogReader
from src.collector.watcher import LogWatcher
from src.config import Config
from src.notifier.alert import AlertNotifier
from src.status import StatusTracker
from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

# 支持的命令列表
_COMMANDS = [
    "analyze", "recent", "search", "status",
    "instances", "alerts", "help", "quit", "exit",
]

# analyze 子命令的 time_range 选项
_TIME_RANGES = ["all", "7d", "24h", "1h"]


def _format_uptime(seconds: float) -> str:
    """将秒数格式化为可读的运行时长"""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _parse_time_range(time_range: str) -> dict:
    """将 time_range 字符串转换为 {start, end} 字典"""
    now = datetime.now()
    if time_range == "1h":
        start = now - timedelta(hours=1)
    elif time_range == "24h":
        start = now - timedelta(hours=24)
    elif time_range == "7d":
        start = now - timedelta(days=7)
    else:  # all
        start = datetime(2000, 1, 1)

    return {"start": start, "end": now}


class CLIInterface:
    """CLI 交互界面，提供命令行交互和对话功能"""

    def __init__(self):
        self._config: Config | None = None
        self._db: DatabaseManager | None = None
        self._analyzer: AnalysisGraph | None = None
        self._discoverer: MySQLLogDiscover | None = None
        self._watcher: LogWatcher | None = None
        self._parser: LogParser | None = None
        self._notifier: AlertNotifier | None = None
        self._status: StatusTracker | None = None

        self._instances: list[dict] = []
        self._chat_messages: list[dict] = []
        self._running: bool = False

        self._console = Console()
        self._prompt_session: PromptSession | None = None

        # 自动分析任务
        self._auto_analyze_task: asyncio.Task | None = None

    # ── 生命周期 ──────────────────────────────────────────────

    async def start(self):
        """启动 CLI 交互界面：初始化组件 → 启动监控 → 进入交互循环"""
        try:
            # 1. 加载配置
            self._console.print("[bold cyan]正在加载配置...[/bold cyan]")
            self._config = Config.load()

            # 2. 初始化数据库
            self._console.print("[bold cyan]正在初始化数据库...[/bold cyan]")
            self._db = DatabaseManager()
            await self._db.initialize()

            # 3. 初始化分析引擎
            self._analyzer = AnalysisGraph(self._config)

            # 4. 初始化日志解析器
            self._parser = LogParser()

            # 5. 初始化通知器并设置 CLI 回调
            self._notifier = AlertNotifier()
            self._notifier.set_cli_callback(self._on_alert)

            # 6. 初始化状态追踪器
            self._status = StatusTracker()
            self._status.start()

            # 7. 发现 MySQL 实例
            self._console.print("[bold cyan]正在发现 MySQL 实例...[/bold cyan]")
            self._discoverer = MySQLLogDiscover()
            self._instances = await self._discoverer.discover()

            if self._instances:
                self._console.print(
                    f"[bold green]发现 {len(self._instances)} 个 MySQL 实例[/bold green]"
                )
                # 将实例信息注册到状态追踪器
                for inst in self._instances:
                    self._status.update_instance(
                        inst.get("name", "unknown"),
                        {
                            "log_path": inst.get("log_path", ""),
                            "host": inst.get("host", "localhost"),
                            "port": inst.get("port", 3306),
                        },
                    )
            else:
                self._console.print(
                    "[bold yellow]未发现 MySQL 实例，可手动配置后重启[/bold yellow]"
                )

            # 8. 启动日志监控
            if self._instances:
                self._console.print("[bold cyan]正在启动日志监控...[/bold cyan]")
                self._watcher = LogWatcher(self._instances, self._on_log_change)
                await self._watcher.start()
                self._console.print("[bold green]日志监控已启动[/bold green]")

            # 9. 启动自动分析（如果配置开启）
            if self._config.get("analyzer", "auto_analyze", default=False):
                interval = self._config.get("analyzer", "auto_analyze_interval", default=60)
                self._auto_analyze_task = asyncio.create_task(
                    self._auto_analyze_loop(interval)
                )
                self._console.print(
                    f"[bold green]自动分析已启动，间隔 {interval}s[/bold green]"
                )

            # 10. 初始化 prompt_toolkit 会话
            history_file = self._config.get(
                "cli", "history_file", default=".cli_history"
            )
            # 确保历史文件路径有效
            history_path = Path(history_file)
            if not history_path.is_absolute():
                history_path = Path.cwd() / history_path

            command_completer = WordCompleter(
                _COMMANDS + _TIME_RANGES, ignore_case=True
            )
            self._prompt_session = PromptSession(
                history=FileHistory(str(history_path)),
                auto_suggest=AutoSuggestFromHistory(),
                completer=command_completer,
            )

            self._running = True

            # 显示欢迎信息
            self._print_welcome()

            # 11. 进入交互循环
            await self._interactive_loop()

        except KeyboardInterrupt:
            self._console.print("\n[yellow]收到中断信号，正在退出...[/yellow]")
        except Exception as e:
            self._console.print(f"[bold red]启动失败: {e}[/bold red]")
            logger.error("CLI 启动失败: %s", e, exc_info=True)
        finally:
            await self.stop()

    async def stop(self):
        """优雅退出"""
        self._running = False

        # 停止自动分析
        if self._auto_analyze_task and not self._auto_analyze_task.done():
            self._auto_analyze_task.cancel()
            try:
                await self._auto_analyze_task
            except asyncio.CancelledError:
                pass

        # 停止日志监控
        if self._watcher:
            await self._watcher.stop()

        # 停止状态追踪
        if self._status:
            self._status.stop()

        # 关闭数据库
        if self._db:
            await self._db.close()

        self._console.print("[bold green]已安全退出，再见！[/bold green]")

    # ── 欢迎信息 ──────────────────────────────────────────────

    def _print_welcome(self):
        """显示欢迎信息"""
        welcome = Panel(
            "[bold cyan]MySQL 错误日志自动分析工具[/bold cyan]\n\n"
            "输入 [bold]help[/bold] 查看可用命令\n"
            "输入其他内容将进入对话模式\n"
            "输入 [bold]quit[/bold] 或 [bold]exit[/bold] 退出程序",
            title="欢迎使用",
            border_style="cyan",
        )
        self._console.print(welcome)

    # ── 交互循环 ──────────────────────────────────────────────

    async def _interactive_loop(self):
        """主交互循环"""
        prompt_str = self._config.get("cli", "prompt", default="mysql-analyzer> ")

        while self._running:
            try:
                user_input = await asyncio.to_thread(
                    self._prompt_session.prompt, prompt_str
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                # 解析命令
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                # 命令分发
                if command in ("quit", "exit"):
                    self._running = False
                    break
                elif command == "help":
                    self._cmd_help()
                elif command == "analyze":
                    await self._cmd_analyze(args.strip())
                elif command == "recent":
                    await self._cmd_recent(args.strip())
                elif command == "search":
                    await self._cmd_search(args.strip())
                elif command == "status":
                    self._cmd_status()
                elif command == "instances":
                    self._cmd_instances()
                elif command == "alerts":
                    await self._cmd_alerts()
                else:
                    # 非命令输入，进入对话模式
                    await self._cmd_chat(user_input)

            except KeyboardInterrupt:
                self._console.print("\n[yellow]按 Ctrl+D 或输入 quit 退出[/yellow]")
            except EOFError:
                self._running = False
                break
            except Exception as e:
                self._console.print(f"[red]命令执行出错: {e}[/red]")
                logger.error("命令执行出错: %s", e, exc_info=True)

    # ── 命令实现 ──────────────────────────────────────────────

    def _cmd_help(self):
        """显示帮助信息"""
        table = Table(
            title="可用命令",
            show_header=True,
            header_style="bold cyan",
            border_style="blue",
        )
        table.add_column("命令", style="bold", width=20)
        table.add_column("说明", width=60)

        commands_info = [
            ("analyze [time_range]", "运行分析 (all/7d/24h/1h，默认 all)"),
            ("recent [n]", "查看最近 N 条错误日志 (默认 20)"),
            ("search <keyword>", "搜索关键词相关日志"),
            ("status", "查看程序运行状态"),
            ("instances", "查看监控的 MySQL 实例列表"),
            ("alerts", "查看未读关键错误告警"),
            ("help", "显示帮助信息"),
            ("quit / exit", "退出程序"),
        ]

        for cmd, desc in commands_info:
            table.add_row(cmd, desc)

        self._console.print(table)
        self._console.print(
            "\n[dim]其他输入将作为自然语言对话，由 AI 进行分析和回答[/dim]"
        )

    async def _cmd_analyze(self, time_range: str = "all"):
        """运行分析"""
        if time_range and time_range not in _TIME_RANGES:
            self._console.print(
                f"[red]无效的时间范围: {time_range}，可选值: {', '.join(_TIME_RANGES)}[/red]"
            )
            return

        if not time_range:
            time_range = "all"

        # 全量分析时检查日志大小
        if time_range == "all" and self._instances:
            warning_mb = self._config.get(
                "collector", "full_analysis_warning_mb", default=500
            )
            total_size_mb = 0.0
            for inst in self._instances:
                try:
                    reader = LogReader(inst)
                    size = await reader.get_file_size()
                    total_size_mb += size / (1024 * 1024)
                except Exception:
                    pass

            if total_size_mb > warning_mb:
                self._console.print(
                    Panel(
                        f"日志总大小 [bold red]{total_size_mb:.1f} MB[/bold red] "
                        f"超过阈值 [bold]{warning_mb} MB[/bold]\n"
                        "全量分析可能耗时较长，是否继续？",
                        title="[bold yellow]⚠ 日志大小警告[/bold yellow]",
                        border_style="yellow",
                    )
                )
                try:
                    confirm = await asyncio.to_thread(
                        self._prompt_session.prompt, "确认继续? (y/N): "
                    )
                    if confirm.strip().lower() != "y":
                        self._console.print("[dim]已取消分析[/dim]")
                        return
                except (EOFError, KeyboardInterrupt):
                    self._console.print("\n[dim]已取消分析[/dim]")
                    return

        # 执行分析
        time_range_dict = _parse_time_range(time_range)

        if not self._instances:
            self._console.print("[yellow]没有可分析的 MySQL 实例[/yellow]")
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self._console,
        ) as progress:
            for inst in self._instances:
                instance_id = inst.get("name", "unknown")
                task = progress.add_task(
                    f"正在分析实例 {instance_id}...", total=None
                )

                try:
                    result = await self._analyzer.run_analysis(
                        instance_id=instance_id,
                        time_range=time_range_dict,
                    )

                    progress.remove_task(task)

                    # 显示分析结果
                    summary = result.get("summary", "")
                    suggestions = result.get("suggestions", [])

                    if summary:
                        self._console.print(
                            Panel(
                                Markdown(summary),
                                title=f"[bold green]分析结果 - {instance_id}[/bold green]",
                                border_style="green",
                            )
                        )

                    if suggestions:
                        sug_table = Table(
                            title=f"建议 - {instance_id}",
                            show_header=True,
                            header_style="bold yellow",
                        )
                        sug_table.add_column("类别", width=15)
                        sug_table.add_column("建议", width=60)
                        for sug in suggestions:
                            sug_table.add_row(
                                str(sug.get("category", "")),
                                str(sug.get("suggestion", "")),
                            )
                        self._console.print(sug_table)

                    # 更新状态
                    if self._status:
                        self._status.update_analysis_time(instance_id)

                except Exception as e:
                    progress.remove_task(task)
                    self._console.print(
                        f"[red]分析实例 {instance_id} 失败: {e}[/red]"
                    )
                    logger.error("分析实例 %s 失败: %s", instance_id, e)

    async def _cmd_recent(self, args: str = ""):
        """查看最近 N 条错误日志"""
        n = 20
        if args:
            try:
                n = int(args)
                if n <= 0:
                    raise ValueError
            except ValueError:
                self._console.print("[red]参数无效，请输入正整数[/red]")
                return

        if not self._db:
            self._console.print("[red]数据库未初始化[/red]")
            return

        try:
            logs = await self._db.query_logs(limit=n)

            if not logs:
                self._console.print("[dim]暂无日志记录[/dim]")
                return

            table = Table(
                title=f"最近 {len(logs)} 条错误日志",
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("时间", width=22)
            table.add_column("级别", width=10)
            table.add_column("错误码", width=12)
            table.add_column("消息", width=50)

            for log in logs:
                level = log.get("level", "")
                level_style = self._level_style(level)
                table.add_row(
                    str(log.get("timestamp", "")),
                    f"[{level_style}]{level}[/{level_style}]",
                    str(log.get("error_code", "") or ""),
                    str(log.get("message", "") or "")[:80],
                )

            self._console.print(table)

        except Exception as e:
            self._console.print(f"[red]查询日志失败: {e}[/red]")
            logger.error("查询日志失败: %s", e)

    async def _cmd_search(self, keyword: str):
        """搜索关键词相关日志"""
        if not keyword:
            self._console.print("[red]请输入搜索关键词: search <keyword>[/red]")
            return

        if not self._db:
            self._console.print("[red]数据库未初始化[/red]")
            return

        try:
            logs = await self._db.query_logs(keyword=keyword, limit=50)

            if not logs:
                self._console.print(f"[dim]未找到与 '{keyword}' 相关的日志[/dim]")
                return

            table = Table(
                title=f"搜索结果: '{keyword}' ({len(logs)} 条)",
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("时间", width=22)
            table.add_column("级别", width=10)
            table.add_column("错误码", width=12)
            table.add_column("消息", width=50)

            for log in logs:
                level = log.get("level", "")
                level_style = self._level_style(level)
                message = str(log.get("message", "") or "")
                # 高亮关键词
                message_display = message[:80].replace(
                    keyword, f"[bold yellow]{keyword}[/bold yellow]"
                )
                table.add_row(
                    str(log.get("timestamp", "")),
                    f"[{level_style}]{level}[/{level_style}]",
                    str(log.get("error_code", "") or ""),
                    message_display,
                )

            self._console.print(table)

        except Exception as e:
            self._console.print(f"[red]搜索失败: {e}[/red]")
            logger.error("搜索失败: %s", e)

    def _cmd_status(self):
        """查看程序运行状态"""
        if not self._status:
            self._console.print("[red]状态追踪器未初始化[/red]")
            return

        status = self._status.get_status()
        summary = self._status.get_summary()

        self._console.print(
            Panel(
                summary,
                title="[bold]程序状态[/bold]",
                border_style="cyan",
            )
        )

        # 额外显示详细信息
        detail_table = Table(show_header=True, header_style="bold cyan")
        detail_table.add_column("指标", width=20)
        detail_table.add_column("值", width=40)

        detail_table.add_row(
            "启动时间",
            str(status.get("start_time", "N/A")),
        )
        detail_table.add_row(
            "运行时长",
            _format_uptime(status.get("uptime_seconds", 0)),
        )
        detail_table.add_row(
            "监控实例数",
            str(len(status.get("monitored_instances", []))),
        )
        detail_table.add_row(
            "已处理日志",
            str(status.get("total_logs_processed", 0)),
        )
        detail_table.add_row(
            "告警总数",
            str(status.get("total_alerts", 0)),
        )
        detail_table.add_row(
            "CPU 使用率",
            f"{status.get('cpu_percent', 0):.1f}%",
        )
        detail_table.add_row(
            "内存使用",
            f"{status.get('memory_mb', 0):.1f} MB",
        )

        self._console.print(detail_table)

    def _cmd_instances(self):
        """查看监控的 MySQL 实例列表"""
        if not self._instances:
            self._console.print("[yellow]暂无监控的 MySQL 实例[/yellow]")
            return

        table = Table(
            title="MySQL 实例列表",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("名称", width=20)
        table.add_column("日志路径", width=45)
        table.add_column("主机", width=15)
        table.add_column("端口", width=8)

        for inst in self._instances:
            table.add_row(
                str(inst.get("name", "")),
                str(inst.get("log_path", "")),
                str(inst.get("host", "localhost")),
                str(inst.get("port", 3306)),
            )

        self._console.print(table)

    async def _cmd_alerts(self):
        """查看未读关键错误告警"""
        if not self._db:
            self._console.print("[red]数据库未初始化[/red]")
            return

        try:
            alerts = await self._db.query_alerts(is_read=False, limit=50)

            if not alerts:
                self._console.print("[dim]暂无未读告警[/dim]")
                return

            table = Table(
                title=f"未读告警 ({len(alerts)} 条)",
                show_header=True,
                header_style="bold red",
            )
            table.add_column("ID", width=6)
            table.add_column("实例", width=15)
            table.add_column("类型", width=10)
            table.add_column("LLM 建议", width=50)
            table.add_column("时间", width=22)

            for alert in alerts:
                suggestion = str(alert.get("llm_suggestion", "") or "无")
                table.add_row(
                    str(alert.get("id", "")),
                    str(alert.get("instance_id", "")),
                    str(alert.get("alert_type", "")),
                    suggestion[:80],
                    str(alert.get("created_at", "")),
                )

            self._console.print(table)

            # 询问是否标记已读
            self._console.print(
                "\n[dim]输入 'alerts read' 标记所有告警为已读[/dim]"
            )

        except Exception as e:
            self._console.print(f"[red]查询告警失败: {e}[/red]")
            logger.error("查询告警失败: %s", e)

    async def _cmd_chat(self, user_input: str):
        """对话模式：将用户输入作为自然语言对话"""
        if not self._analyzer:
            self._console.print("[red]分析引擎未初始化[/red]")
            return

        # 添加用户消息到历史
        self._chat_messages.append({"role": "user", "content": user_input})

        with self._console.status("[bold cyan]AI 正在思考...[/bold cyan]"):
            try:
                response = await self._analyzer.run_chat(self._chat_messages)

                # 添加助手回复到历史
                self._chat_messages.append({"role": "assistant", "content": response})

                # 使用 rich Markdown 渲染对话结果
                self._console.print(
                    Panel(
                        Markdown(response),
                        title="[bold green]AI 回复[/bold green]",
                        border_style="green",
                    )
                )

            except Exception as e:
                self._console.print(f"[red]对话失败: {e}[/red]")
                logger.error("对话失败: %s", e)

    # ── 回调处理 ──────────────────────────────────────────────

    async def _on_alert(self, alert: dict):
        """关键错误告警 CLI 回调"""
        alert_type = alert.get("alert_type", "")
        level = alert.get("level", "")
        message = alert.get("message", "")
        instance_id = alert.get("instance_id", "")
        llm_suggestion = alert.get("llm_suggestion", "")

        content = Text()
        content.append(f"实例: {instance_id}\n", style="bold")
        content.append(f"级别: {level}\n", style="bold")
        content.append(f"类型: {alert_type}\n")
        content.append(f"消息: {message}\n")
        if llm_suggestion:
            content.append(f"\n💡 LLM 建议: {llm_suggestion}", style="bold yellow")

        self._console.print(
            Panel(
                content,
                title="[bold red]🚨 关键错误告警[/bold red]",
                border_style="red",
            )
        )

        # 更新状态追踪器
        if self._status:
            self._status.increment_alerts()

    async def _on_log_change(self, instance_id: str, new_lines: list[str]):
        """日志变化回调：解析新日志行并检查关键错误"""
        if not self._parser:
            return

        parsed = self._parser.parse_batch(new_lines)

        # 存储到数据库
        if self._db and parsed:
            entries = []
            for p in parsed:
                entries.append({
                    "instance_id": instance_id,
                    **p,
                })
            try:
                await self._db.insert_log_entries(entries)
            except Exception as e:
                logger.error("存储日志条目失败: %s", e)

            # 更新状态
            if self._status:
                self._status.increment_logs(len(entries))

        # 检查关键错误并通知
        if self._notifier and parsed:
            for log_entry in parsed:
                try:
                    await self._notifier.check_and_notify(log_entry, instance_id)
                except Exception as e:
                    logger.error("告警检测失败: %s", e)

    # ── 自动分析循环 ──────────────────────────────────────────

    async def _auto_analyze_loop(self, interval: int):
        """自动分析循环"""
        try:
            while self._running:
                await asyncio.sleep(interval)
                if not self._running or not self._instances:
                    continue

                try:
                    time_range = _parse_time_range("1h")
                    for inst in self._instances:
                        instance_id = inst.get("name", "unknown")
                        result = await self._analyzer.run_analysis(
                            instance_id=instance_id,
                            time_range=time_range,
                        )
                        if self._status:
                            self._status.update_analysis_time(instance_id)

                        # 检查关键错误
                        raw_logs = result.get("raw_logs", [])
                        if raw_logs:
                            await self._analyzer.check_critical_errors(raw_logs)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("自动分析出错: %s", e)

        except asyncio.CancelledError:
            pass

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _level_style(level: str) -> str:
        """根据日志级别返回 rich 样式"""
        level_upper = (level or "").upper()
        if level_upper in ("CRITICAL", "FATAL"):
            return "bold red"
        if level_upper == "ERROR":
            return "red"
        if level_upper == "WARNING":
            return "yellow"
        if level_upper == "NOTE":
            return "dim"
        return "white"
