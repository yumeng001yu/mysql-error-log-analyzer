"""MySQL 错误日志文件监控模块"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Awaitable, Callable

from watchdog.events import FileModifiedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.config import Config
from src.collector.reader import LogReader

logger = logging.getLogger(__name__)

# 回调函数类型
Callback = Callable[[str, list[str]], Awaitable[None]]


class _LogEventHandler(FileSystemEventHandler):
    """watchdog 文件系统事件处理器"""

    def __init__(
        self,
        instance_id: str,
        log_path: str,
        reader: LogReader,
        callback: Callback,
        loop: asyncio.AbstractEventLoop,
    ):
        super().__init__()
        self.instance_id = instance_id
        self.log_path = log_path
        self.reader = reader
        self.callback = callback
        self.loop = loop
        self._last_size: int = 0

    def on_modified(self, event):
        if event.src_path != self.log_path:
            return
        self._handle_change()

    def on_moved(self, event):
        """处理日志轮转：文件被重命名（如 error.log -> error.log.1）"""
        if event.src_path != self.log_path:
            return
        logger.info("检测到日志轮转（重命名）: %s", event.src_path)
        # 重置读取位置，等待新文件出现
        self.reader.position = 0
        self._last_size = 0

    def _handle_change(self):
        """文件变化时读取新增内容并回调"""
        try:
            current_size = os.path.getsize(self.log_path)
        except OSError:
            return

        # 文件被截断（日志轮转的另一种方式）
        if current_size < self._last_size:
            logger.info("检测到日志轮转（截断）: %s", self.log_path)
            self.reader.position = 0
            self._last_size = 0
            current_size = 0

        if current_size <= self._last_size:
            return

        # 读取新增部分
        position = self.reader.position
        if position > current_size:
            # 位置超出文件大小，重置
            position = 0

        asyncio.run_coroutine_threadsafe(
            self._read_and_callback(position, current_size),
            self.loop,
        )

    async def _read_and_callback(self, position: int, current_size: int):
        """读取新增内容并调用回调"""
        new_lines: list[str] = []
        try:
            async for chunk in self.reader.read_from_position(position):
                lines = chunk.splitlines()
                new_lines.extend(lines)

            if new_lines:
                await self.callback(self.instance_id, new_lines)

            self._last_size = current_size
        except Exception as e:
            logger.error("读取日志增量内容时出错 (%s): %s", self.log_path, e)


class LogWatcher:
    """文件监控器，使用 watchdog 监控 MySQL 错误日志变化"""

    def __init__(self, instances: list[dict], callback: Callback):
        """初始化

        Args:
            instances: 实例信息列表，每项需包含 name 和 log_path
            callback: 文件变化时的回调函数，签名为
                      async callback(instance_id: str, new_lines: list[str])
        """
        self._instances = instances
        self._callback = callback
        self._config = Config()
        self._observer: Observer | None = None
        self._readers: dict[str, LogReader] = {}
        self._handlers: dict[str, _LogEventHandler] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self):
        """启动文件监控"""
        self._loop = asyncio.get_running_loop()
        self._observer = Observer()

        for instance in self._instances:
            instance_id = instance.get("name", "unknown")
            log_path = instance.get("log_path", "")

            if not log_path or not Path(log_path).exists():
                logger.warning("实例 %s 的日志路径无效: %s", instance_id, log_path)
                continue

            # 创建 LogReader 并初始化位置为文件末尾
            reader = LogReader(instance)
            file_size = await reader.get_file_size()
            reader.position = file_size
            self._readers[instance_id] = reader

            # 创建事件处理器
            handler = _LogEventHandler(
                instance_id=instance_id,
                log_path=log_path,
                reader=reader,
                callback=self._callback,
                loop=self._loop,
            )
            handler._last_size = file_size
            self._handlers[instance_id] = handler

            # 监控日志文件所在目录（watchdog 监控目录才能检测到重命名等事件）
            log_dir = str(Path(log_path).parent)
            self._observer.schedule(handler, log_dir, recursive=False)
            logger.info("开始监控实例 %s 的日志: %s", instance_id, log_path)

        if self._observer.emitters:
            self._observer.start()
            logger.info("日志监控已启动，共监控 %d 个实例", len(self._handlers))
        else:
            logger.warning("没有有效的日志文件可监控")

    async def stop(self):
        """停止监控"""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=10)
            self._observer = None
            logger.info("日志监控已停止")

        self._readers.clear()
        self._handlers.clear()
