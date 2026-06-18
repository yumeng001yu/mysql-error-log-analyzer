"""跨 API 模块共享的辅助函数

将各 API 模块中完全重复的工具函数集中到此模块。
Phase 2-D 逐步将各模块的本地实现替换为从此处导入。
"""
from typing import Optional, Tuple

from src.utils import parse_time_range_datetime


def resolve_time_range(
    period: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """将 period 参数解析为 start_time/end_time 字符串

    替代 logs.py 和 slow_query.py 中完全重复的 `_resolve_time_range()`。

    Args:
        period: 时间段字符串 (1h/24h/7d/all/Nh/Nd)
        start_time: 显式开始时间（优先于 period）
        end_time: 显式结束时间（优先于 period）

    Returns:
        (start_iso, end_iso) 元组，无范围时为 (None, None)
    """
    if start_time and end_time:
        return start_time, end_time
    if period and period != "all":
        result = parse_time_range_datetime(period)
        st = result.get("start")
        et = result.get("end")
        return st.isoformat() if st else None, et.isoformat() if et else None
    return None, None


def report_to_dict(report) -> dict:
    """将 OperationsReport 对象转换为可序列化的字典

    替代 reports.py 和 redis_reports.py 中完全重复的 `_report_to_dict()`。
    """
    return {
        "id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "generated_at": report.generated_at,
        "instance_id": report.instance_id,
        "instance_name": report.instance_name,
        "sections": [
            {
                "title": s.title,
                "content_type": s.content_type,
                "data": s.data,
            }
            for s in report.sections
        ],
        "summary": report.summary,
        "health_score": report.health_score,
    }
