"""解析节点 - 对原始日志进行结构化确认和补充解析"""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# MySQL 错误日志常见时间格式
_TIMESTAMP_PATTERNS = [
    re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)"),
    re.compile(r"(\d{6}\s+\d{2}:\d{2}:\d{2})"),
]

# MySQL 错误级别
_LOG_LEVELS = {"System", "Warning", "Note", "Error", "CRITICAL", "ERROR", "WARNING", "NOTE"}

# 常见 MySQL 子系统标签
_SUBSYSTEM_PATTERNS = {
    "innodb": re.compile(r"\[?InnoDB\]?", re.IGNORECASE),
    "replication": re.compile(r"\[?(?:Replication|Slave|Master|IO|SQL)\s*(?:thread|running)?\]?", re.IGNORECASE),
    "myisam": re.compile(r"\[?MyISAM\]?", re.IGNORECASE),
    "server": re.compile(r"\[?Server\]?", re.IGNORECASE),
    "plugin": re.compile(r"\[?Plugin\]?", re.IGNORECASE),
    "ddl": re.compile(r"\[?DDL\]?", re.IGNORECASE),
}


def _extract_timestamp(text: str) -> str | None:
    """从日志行中提取时间戳"""
    for pattern in _TIMESTAMP_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _extract_level(text: str) -> str | None:
    """从日志行中提取错误级别"""
    for level in _LOG_LEVELS:
        if level in text:
            return level
    return None


def _extract_subsystem(text: str) -> str | None:
    """从日志行中提取子系统标签"""
    for name, pattern in _SUBSYSTEM_PATTERNS.items():
        if pattern.search(text):
            return name
    return None


def _parse_log_entry(raw: dict) -> dict:
    """对单条原始日志进行结构化确认和补充解析

    Args:
        raw: 原始日志字典，至少包含 "message" 字段

    Returns:
        解析后的日志字典
    """
    parsed = dict(raw)

    message = raw.get("message", "")
    if not message:
        parsed.setdefault("message", "")

    # 补充时间戳
    if not parsed.get("timestamp"):
        ts = _extract_timestamp(message)
        if ts:
            parsed["timestamp"] = ts

    # 补充错误级别
    if not parsed.get("level"):
        level = _extract_level(message)
        if level:
            parsed["level"] = level

    # 补充子系统
    if not parsed.get("subsystem"):
        subsystem = _extract_subsystem(message)
        if subsystem:
            parsed["subsystem"] = subsystem

    # 确保必要字段存在
    parsed.setdefault("timestamp", None)
    parsed.setdefault("level", None)
    parsed.setdefault("subsystem", None)
    parsed.setdefault("message", "")
    parsed.setdefault("raw_message", raw.get("raw_message", message))

    return parsed


class ParseNode:
    """解析节点：对原始日志进行结构化确认和补充解析"""

    async def __call__(self, state: dict) -> dict:
        """执行解析

        输入状态：
            - instance_id: str
            - time_range: dict
            - raw_logs: list[dict]

        输出状态：
            - 增加 parsed_logs 字段
        """
        raw_logs = state.get("raw_logs", [])
        logger.info("解析节点: 开始处理 %d 条原始日志", len(raw_logs))

        parsed_logs = []
        for raw in raw_logs:
            try:
                parsed = _parse_log_entry(raw)
                parsed_logs.append(parsed)
            except Exception as e:
                logger.warning("解析日志条目失败: %s, 原始数据: %s", e, raw)
                parsed_logs.append(dict(raw))

        logger.info("解析节点: 完成，解析出 %d 条结构化日志", len(parsed_logs))
        return {"parsed_logs": parsed_logs}
