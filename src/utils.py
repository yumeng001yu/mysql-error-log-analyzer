"""工具函数模块"""

import re
from datetime import datetime, timedelta, timezone


def parse_time_range(time_range: str) -> tuple[str, str]:
    """将 time_range 字符串转换为 (start_time, end_time) ISO 格式

    支持的格式：
    - 预定义: "all", "1h", "24h", "7d"
    - 自定义小时: "3h", "5h", "12h" 等
    - 自定义天: "3d", "5d" 等

    Returns:
        (start_time_iso, end_time_iso)
    """
    now = datetime.now(timezone.utc)
    end = now.isoformat()

    if time_range == "all":
        return "", end

    # 匹配 Nh 或 Nd 格式
    match = re.match(r'^(\d+)(h|d)$', time_range.lower())
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "h":
            start = (now - timedelta(hours=value)).isoformat()
        else:  # d
            start = (now - timedelta(days=value)).isoformat()
        return start, end

    # 默认 7d
    start = (now - timedelta(days=7)).isoformat()
    return start, end


def parse_time_range_datetime(time_range: str) -> dict:
    """将 time_range 字符串转换为 {start: datetime, end: datetime} 字典

    用于 CLI 等需要 datetime 对象的场景
    """
    now = datetime.now()

    if time_range == "all":
        return {"start": datetime(2000, 1, 1), "end": now}

    match = re.match(r'^(\d+)(h|d)$', time_range.lower())
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "h":
            start = now - timedelta(hours=value)
        else:  # d
            start = now - timedelta(days=value)
        return {"start": start, "end": now}

    return {"start": now - timedelta(days=7), "end": now}


def get_auto_read_interval_hours(time_range: str) -> float:
    """根据时间段计算自动读取间隔（小时）

    规则：
    - 时间段 <= 24h: 间隔 = 时间段本身
    - 时间段 > 24h: 间隔 = 24h
    - all: 间隔 = 24h
    """
    if time_range == "all":
        return 24.0

    match = re.match(r'^(\d+)(h|d)$', time_range.lower())
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "h":
            hours = float(value)
        else:  # d
            hours = float(value) * 24

        return min(hours, 24.0)

    return 24.0


def is_valid_time_range(time_range: str) -> bool:
    """验证时间范围字符串是否有效"""
    if time_range == "all":
        return True
    match = re.match(r'^(\d+)(h|d)$', time_range.lower())
    if match:
        value = int(match.group(1))
        return value > 0
    return False


def format_time_range_display(time_range: str) -> str:
    """将时间范围字符串转为可读显示文本"""
    if time_range == "all":
        return "全部"

    match = re.match(r'^(\d+)(h|d)$', time_range.lower())
    if match:
        value = match.group(1)
        unit = match.group(2)
        if unit == "h":
            return f"{value}小时"
        else:
            return f"{value}天"

    return time_range
