"""MySQL 慢查询日志解析器"""

import re
import hashlib
import logging
from datetime import datetime
from typing import Optional, Generator

logger = logging.getLogger(__name__)

# 旧格式慢查询日志行正则
# # Time: 2024-01-15T10:30:45.123456+08:00  或  # Time: 240115 10:30:45
_TIME_RE = re.compile(
    r"^#\s*Time:\s*(.+)$"
)

# # User@Host: root[root] @ localhost [127.0.0.1]  Id:  123
_USER_HOST_RE = re.compile(
    r"^#\s*User@Host:\s*(\S+)\s*.*@\s*(\S+)"
)

# # Query_time: 10.500000  Lock_time: 0.000100 Rows_sent: 1  Rows_examined: 100000
_QUERY_STATS_RE = re.compile(
    r"^#\s*Query_time:\s*([\d.]+)\s+Lock_time:\s*([\d.]+)\s+Rows_sent:\s*(\d+)\s+Rows_examined:\s*(\d+)"
)

# SET timestamp=1705289445;
_SET_TIMESTAMP_RE = re.compile(
    r"^SET\s+timestamp=(\d+);",
    re.IGNORECASE,
)

# SQL 类型关键词
_SQL_TYPE_PATTERNS = [
    ("SELECT", re.compile(r"^\s*SELECT\b", re.IGNORECASE)),
    ("INSERT", re.compile(r"^\s*INSERT\b", re.IGNORECASE)),
    ("UPDATE", re.compile(r"^\s*UPDATE\b", re.IGNORECASE)),
    ("DELETE", re.compile(r"^\s*DELETE\b", re.IGNORECASE)),
    ("ALTER", re.compile(r"^\s*ALTER\b", re.IGNORECASE)),
    ("CREATE", re.compile(r"^\s*CREATE\b", re.IGNORECASE)),
    ("DROP", re.compile(r"^\s*DROP\b", re.IGNORECASE)),
]


class SlowQueryParser:
    """MySQL 慢查询日志解析器

    支持旧格式和新格式（MySQL 5.6+）的慢查询日志。
    旧格式: # Time: ..., # User@Host: ..., # Query_time: ... Lock_time: ... Rows_sent: ... Rows_examined: ...
    新格式: # Time: ..., # User@Host: ..., SET timestamp=...;, 然后 SQL
    """

    def parse_file(self, filepath: str) -> list[dict]:
        """解析整个慢查询日志文件

        Args:
            filepath: 慢查询日志文件路径

        Returns:
            解析后的慢查询记录列表
        """
        results = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for entry in self._parse_lines(f):
                    results.append(entry)
        except FileNotFoundError:
            logger.warning("慢查询日志文件不存在: %s", filepath)
        except Exception as e:
            logger.error("解析慢查询日志失败: %s", e)
        return results

    def parse_stream(self, filepath: str) -> Generator[dict, None, None]:
        """流式解析慢查询日志，适用于大文件

        Args:
            filepath: 慢查询日志文件路径

        Yields:
            逐条解析后的慢查询记录
        """
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                yield from self._parse_lines(f)
        except FileNotFoundError:
            logger.warning("慢查询日志文件不存在: %s", filepath)
        except Exception as e:
            logger.error("流式解析慢查询日志失败: %s", e)

    def _parse_lines(self, lines) -> Generator[dict, None, None]:
        """逐行解析，处理多行 SQL 语句

        Args:
            lines: 可迭代的行文本（文件对象或列表）

        Yields:
            解析后的慢查询记录字典
        """
        current: Optional[dict] = None
        sql_lines: list[str] = []

        for raw_line in lines:
            line = raw_line.rstrip("\n\r")
            if not line:
                continue

            # # Time: 行 - 可能是新的查询记录开始
            time_match = _TIME_RE.match(line)
            if time_match:
                # 如果已有正在构建的记录，先输出
                if current is not None:
                    self._finalize_entry(current, sql_lines)
                    yield current
                    sql_lines = []

                current = {}

                time_str = time_match.group(1).strip()
                current["timestamp"] = self._parse_timestamp(time_str)
                continue

            # # User@Host: 行
            user_match = _USER_HOST_RE.match(line)
            if user_match:
                if current is None:
                    current = {}
                current["user"] = user_match.group(1)
                current["host"] = user_match.group(2)
                continue

            # # Query_time: ... 行（旧格式）
            stats_match = _QUERY_STATS_RE.match(line)
            if stats_match:
                if current is None:
                    current = {}
                current["query_time"] = float(stats_match.group(1))
                current["lock_time"] = float(stats_match.group(2))
                current["rows_sent"] = int(stats_match.group(3))
                current["rows_examined"] = int(stats_match.group(4))
                continue

            # SET timestamp=...; 行（新格式）
            ts_match = _SET_TIMESTAMP_RE.match(line)
            if ts_match:
                if current is None:
                    current = {}
                ts_epoch = int(ts_match.group(1))
                # 如果已有 Time 行的 timestamp，保留；否则用 SET timestamp
                if "timestamp" not in current or not current["timestamp"]:
                    current["timestamp"] = datetime.fromtimestamp(ts_epoch).isoformat()
                continue

            # 其他 # 开头的注释行（如 # Schema: ... 等），跳过
            if line.startswith("#"):
                continue

            # SQL 文本行
            sql_lines.append(line)

        # 处理最后一条记录
        if current is not None:
            self._finalize_entry(current, sql_lines)
            yield current

    def _finalize_entry(self, entry: dict, sql_lines: list[str]):
        """完成一条慢查询记录的构建，填充计算字段"""
        sql_text = " ".join(sql_lines).strip()
        entry["sql_text"] = sql_text
        entry["sql_type"] = self._classify_sql(sql_text)
        entry["sql_hash"] = self._compute_sql_hash(sql_text)
        entry["sql_template"] = self._compute_sql_template(sql_text)
        entry["slow_score"] = self._calculate_score(
            entry.get("query_time", 0),
            entry.get("lock_time", 0),
            entry.get("rows_examined", 0),
        )

        # 填充默认值
        entry.setdefault("timestamp", "")
        entry.setdefault("user", "")
        entry.setdefault("host", "")
        entry.setdefault("query_time", 0.0)
        entry.setdefault("lock_time", 0.0)
        entry.setdefault("rows_sent", 0)
        entry.setdefault("rows_examined", 0)

    @staticmethod
    def _parse_timestamp(time_str: str) -> str:
        """解析时间戳字符串为 ISO 格式

        支持的格式:
        - 2024-01-15T10:30:45.123456+08:00
        - 240115 10:30:45
        - 2024-01-15 10:30:45
        """
        # 尝试 ISO 格式
        try:
            dt = datetime.fromisoformat(time_str)
            return dt.isoformat()
        except (ValueError, TypeError):
            pass

        # 尝试 YYMMDD HH:MM:SS 格式
        m = re.match(r"^(\d{6})\s+(\d{1,2}:\d{2}:\d{2})$", time_str)
        if m:
            try:
                dt = datetime.strptime(time_str, "%y%m%d %H:%M:%S")
                return dt.isoformat()
            except ValueError:
                pass

        # 尝试 YYYY-MM-DD HH:MM:SS 格式
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}:\d{2})$", time_str)
        if m:
            try:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                return dt.isoformat()
            except ValueError:
                pass

        # 无法解析则原样返回
        return time_str

    @staticmethod
    def _classify_sql(sql: str) -> str:
        """分类 SQL 语句类型

        Args:
            sql: SQL 文本

        Returns:
            SQL 类型: SELECT, INSERT, UPDATE, DELETE, ALTER, CREATE, DROP, OTHER
        """
        if not sql:
            return "OTHER"
        for sql_type, pattern in _SQL_TYPE_PATTERNS:
            if pattern.match(sql):
                return sql_type
        return "OTHER"

    @staticmethod
    def _calculate_score(query_time: float, lock_time: float, rows_examined: int) -> float:
        """计算慢查询评分

        公式: slow_score = query_time * 0.5 + lock_time * 2 + rows_examined * 0.001

        Args:
            query_time: 查询耗时（秒）
            lock_time: 锁等待时间（秒）
            rows_examined: 扫描行数

        Returns:
            慢查询评分
        """
        return round(query_time * 0.5 + lock_time * 2 + rows_examined * 0.001, 4)

    @staticmethod
    def _compute_sql_hash(sql: str) -> str:
        """计算 SQL 的 MD5 哈希值

        对标准化后的 SQL（小写、空白折叠）计算哈希

        Args:
            sql: SQL 文本

        Returns:
            MD5 哈希字符串
        """
        normalized = re.sub(r"\s+", " ", sql.strip().lower())
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _compute_sql_template(sql: str) -> str:
        """将 SQL 中的字面值替换为 ? 生成模板

        例如: SELECT * FROM users WHERE id = 123 AND name = 'test'
        变为: SELECT * FROM users WHERE id = ? AND name = ?

        Args:
            sql: SQL 文本

        Returns:
            模板化的 SQL
        """
        if not sql:
            return ""

        # 替换字符串字面值（单引号）
        result = re.sub(r"'[^']*'", "?", sql)
        # 替换字符串字面值（双引号）
        result = re.sub(r'"[^"]*"', "?", result)
        # 替换数字字面值（独立数字，非标识符的一部分）
        result = re.sub(r"\b\d+\.?\d*\b", "?", result)

        return result
