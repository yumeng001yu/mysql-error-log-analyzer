"""MySQL 错误日志解析模块"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# MySQL 8.0+ 新格式:
# 2024-01-15T10:30:45.123456Z 123 [Note] [MY-010914] Aborted connection 45 to db: 'test'
_NEW_FORMAT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+"
    r"(\d+)\s+"
    r"\[(Note|Warning|Error|System|Fatal)\]\s+"
    r"\[(MY-\d+)\]\s+"
    r"(.*)"
)

# MySQL 5.7 及更早格式:
# 2024-01-15 10:30:45 123 [Note] Aborted connection 45 to db: 'test'
# 2024-01-15 10:30:45 mysqld_safe Starting mysqld daemon
_OLD_FORMAT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"((?:\d+|[\w]+)\s+)?"
    r"\[(Note|Warning|Error|System|Fatal)\]\s+"
    r"(.*)"
)

# 旧格式无级别（如 mysqld_safe 行）
_OLD_PLAIN_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.*)"
)

# 错误分类关键词映射
_CLASSIFICATION_RULES: list[tuple[str, list[str], list[str]]] = [
    # (category, message_keywords, error_code_prefixes)
    ("connection", [
        "aborted connection", "access denied", "host", "too many connections",
        "connection refused", "lost connection", "connect failed",
    ], ["MY-010914", "MY-010915", "MY-013123", "MY-010056"]),
    ("permission", [
        "access denied", "permission denied", "authentication",
        "password", "privilege",
    ], ["MY-010055", "MY-010056", "MY-013124"]),
    ("innodb", [
        "innodb", "ibdata", "tablespace", "undo log", "redo log",
        "corruption", "page checksum",
    ], ["MY-012", "MY-013"]),
    ("replication", [
        "replication", "slave", "master", "binlog", "relay log",
        "gtid", "slave_io_running", "slave_sql_running",
        "replicate", "semi-sync",
    ], ["MY-010577", "MY-014", "MY-015"]),
    ("crash", [
        "crash", "shutdown", "abort", "segfault", "signal",
        "killed", "terminated", "fatal error",
    ], ["MY-013081", "MY-013082"]),
    ("deadlock", [
        "deadlock",
    ], ["MY-012345"]),
    ("memory", [
        "out of memory", "memory", "cannot allocate", "malloc",
        "mmap", "virtual memory",
    ], ["MY-011090"]),
]


class LogParser:
    """MySQL 错误日志解析器"""

    def parse_line(self, line: str) -> dict | None:
        """解析单行日志

        Args:
            line: 日志行文本

        Returns:
            解析结果字典，包含 timestamp, level, error_code, thread_id, message；
            如果不是有效的日志行则返回 None
        """
        line = line.rstrip("\n\r")
        if not line:
            return None

        # 尝试新格式 (MySQL 8.0+)
        match = _NEW_FORMAT_RE.match(line)
        if match:
            return {
                "timestamp": match.group(1),
                "thread_id": int(match.group(2)),
                "level": match.group(3).upper(),
                "error_code": match.group(4),
                "message": match.group(5),
            }

        # 尝试旧格式（带级别）
        match = _OLD_FORMAT_RE.match(line)
        if match:
            thread_part = match.group(2)
            thread_id = 0
            if thread_part:
                thread_str = thread_part.strip()
                if thread_str.isdigit():
                    thread_id = int(thread_str)
            return {
                "timestamp": match.group(1),
                "thread_id": thread_id,
                "level": match.group(3).upper(),
                "error_code": None,
                "message": match.group(4),
            }

        # 尝试旧格式（无级别，如 mysqld_safe 行）
        match = _OLD_PLAIN_RE.match(line)
        if match:
            return {
                "timestamp": match.group(1),
                "thread_id": 0,
                "level": "SYSTEM",
                "error_code": None,
                "message": match.group(2),
            }

        return None

    def parse_batch(self, lines: list[str]) -> list[dict]:
        """批量解析日志行，处理多行日志（续行以空格开头）

        Args:
            lines: 日志行列表

        Returns:
            解析结果列表
        """
        results: list[dict] = []
        current: dict | None = None

        for line in lines:
            stripped = line.rstrip("\n\r")

            # 空行跳过
            if not stripped:
                continue

            # 续行：以空格或制表符开头，且不是新日志行
            if stripped[0] in (" ", "\t") and current is not None:
                current["message"] += "\n" + stripped.strip()
                continue

            # 解析新行
            parsed = self.parse_line(stripped)
            if parsed is not None:
                if current is not None:
                    results.append(current)
                current = parsed
            else:
                # 无法解析的行，作为续行追加到当前记录
                if current is not None:
                    current["message"] += "\n" + stripped

        if current is not None:
            results.append(current)

        return results

    def classify_error(self, message: str, error_code: str | None = None) -> str:
        """对错误进行分类

        Args:
            message: 错误消息
            error_code: MySQL 错误代码 (如 MY-010914)

        Returns:
            错误分类: connection, permission, innodb, replication,
                      crash, deadlock, memory, other
        """
        message_lower = message.lower()
        code_upper = (error_code or "").upper()

        for category, keywords, code_prefixes in _CLASSIFICATION_RULES:
            # 先检查错误代码前缀
            if error_code:
                for prefix in code_prefixes:
                    if code_upper.startswith(prefix):
                        return category

            # 再检查消息关键词
            for keyword in keywords:
                if keyword in message_lower:
                    return category

        return "other"
