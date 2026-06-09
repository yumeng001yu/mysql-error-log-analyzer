"""MySQL 错误日志文件读取模块"""

import asyncio
import logging
import os
from collections import deque
from pathlib import Path
from typing import AsyncIterator

import aiofiles

from src.config import Config

logger = logging.getLogger(__name__)

# 换行符字节
_NEWLINE = b"\n"


class LogReader:
    """日志文件读取器，支持流式读取和断点续读"""

    def __init__(self, instance_info: dict):
        """初始化

        Args:
            instance_info: 实例信息字典，需包含 log_path 键
        """
        self._log_path = instance_info["log_path"]
        self._instance_name = instance_info.get("name", "unknown")
        self._config = Config()
        self._position: int = 0  # 当前读取位置

    @property
    def log_path(self) -> str:
        return self._log_path

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int):
        self._position = value

    def _chunk_size(self) -> int:
        """获取流式读取的 chunk 大小（字节）"""
        mb = self._config.get("collector", "stream_chunk_size_mb", default=10)
        return mb * 1024 * 1024

    async def read_from_beginning(self) -> AsyncIterator[str]:
        """从头读取日志（流式，按 chunk 返回）

        Yields:
            每次返回一个 chunk 的文本内容
        """
        chunk_size = self._chunk_size()
        try:
            async with aiofiles.open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                self._position = 0
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    self._position = await f.tell()
                    yield chunk
        except FileNotFoundError:
            logger.error("日志文件不存在: %s", self._log_path)
        except PermissionError:
            logger.error("权限不足，无法读取日志文件: %s", self._log_path)
        except Exception as e:
            logger.error("读取日志文件 %s 时出错: %s", self._log_path, e)

    async def read_from_position(self, position: int) -> AsyncIterator[str]:
        """从指定位置读取日志（流式，按 chunk 返回）

        Args:
            position: 起始字节偏移量

        Yields:
            每次返回一个 chunk 的文本内容
        """
        chunk_size = self._chunk_size()
        try:
            async with aiofiles.open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                await f.seek(position)
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    self._position = await f.tell()
                    yield chunk
        except FileNotFoundError:
            logger.error("日志文件不存在: %s", self._log_path)
        except PermissionError:
            logger.error("权限不足，无法读取日志文件: %s", self._log_path)
        except Exception as e:
            logger.error("从位置 %d 读取日志文件 %s 时出错: %s", position, self._log_path, e)

    async def read_recent_lines(self, n: int) -> list[str]:
        """读取最近 N 行（使用逆序读取优化，避免全量加载）

        Args:
            n: 要读取的行数

        Returns:
            最近 N 行文本列表（按原始顺序）
        """
        if n <= 0:
            return []

        try:
            file_size = await self.get_file_size()
            if file_size == 0:
                return []

            lines = await self._read_last_n_lines_binary(n, file_size)
            return lines

        except FileNotFoundError:
            logger.error("日志文件不存在: %s", self._log_path)
            return []
        except PermissionError:
            logger.error("权限不足，无法读取日志文件: %s", self._log_path)
            return []
        except Exception as e:
            logger.error("读取日志文件 %s 最近 %d 行时出错: %s", self._log_path, n, e)
            return []

    async def _read_last_n_lines_binary(self, n: int, file_size: int) -> list[str]:
        """使用二进制逆序读取获取最后 N 行

        从文件末尾向前读取，找到 N 个换行符后停止，
        避免将整个文件加载到内存。
        """
        # 每次读取的块大小
        read_chunk = min(self._chunk_size(), 1024 * 1024)  # 最大 1MB 每次逆序读取
        lines_found: deque[bytes] = deque()
        position = file_size
        leftover = b""

        async with aiofiles.open(self._log_path, "rb") as f:
            while position > 0 and len(lines_found) < n:
                read_size = min(read_chunk, position)
                position -= read_size
                await f.seek(position)
                data = await f.read(read_size)

                # 将 leftover 拼到末尾
                data += leftover
                leftover = b""

                # 从右向左扫描换行符
                parts = data.split(_NEWLINE)

                # parts[-1] 是最右边的部分（可能不完整）
                if position > 0:
                    leftover = parts[0]
                    scan_parts = parts[1:]
                else:
                    scan_parts = parts

                # 逆序添加行
                for part in reversed(scan_parts):
                    if part or (len(lines_found) < n):
                        lines_found.appendleft(part)
                    if len(lines_found) >= n:
                        break

            # 处理 leftover
            if leftover and len(lines_found) < n:
                lines_found.appendleft(leftover)

        # 解码并过滤空行
        result = []
        for line in lines_found:
            decoded = line.decode("utf-8", errors="ignore").rstrip("\r")
            if decoded:
                result.append(decoded)

        return result

    async def get_file_size(self) -> int:
        """获取文件大小

        Returns:
            文件大小（字节），文件不存在返回 0
        """
        try:
            return os.path.getsize(self._log_path)
        except OSError:
            return 0

    async def get_line_count(self) -> int:
        """估算文件行数（不精确，不读取全文件）

        通过读取文件首尾 chunk，结合文件大小和平均行长度来估算。

        Returns:
            估算的行数
        """
        try:
            file_size = await self.get_file_size()
            if file_size == 0:
                return 0

            # 读取文件开头一小部分来估算平均行长度
            sample_size = min(64 * 1024, file_size)  # 最多读 64KB
            async with aiofiles.open(self._log_path, "rb") as f:
                sample = await f.read(sample_size)

            sample_text = sample.decode("utf-8", errors="ignore")
            sample_lines = [l for l in sample_text.split("\n") if l.strip()]

            if not sample_lines:
                return 0

            # 计算平均行长度（含换行符）
            avg_line_len = len(sample_text) / max(len(sample_lines), 1)
            if avg_line_len == 0:
                return 0

            estimated = int(file_size / avg_line_len)
            return max(estimated, 1)

        except Exception as e:
            logger.warning("估算文件 %s 行数时出错: %s", self._log_path, e)
            return 0
