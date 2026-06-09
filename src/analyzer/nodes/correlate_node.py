"""关联分析节点 - 分析错误之间的关联和异常模式"""

import logging
from collections import Counter, defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


def _parse_timestamp(ts_str: str | None) -> datetime | None:
    """尝试解析时间戳字符串"""
    if not ts_str:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%y%m%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _analyze_time_distribution(logs: list[dict]) -> list[dict]:
    """分析各类错误的时间分布模式

    Returns:
        时间分布模式列表，每项包含 category, pattern, description
    """
    category_timestamps = defaultdict(list)
    for log in logs:
        category = log.get("category", "other")
        ts = _parse_timestamp(log.get("timestamp"))
        if ts:
            category_timestamps[category].append(ts)

    patterns = []
    for category, timestamps in category_timestamps.items():
        if len(timestamps) < 2:
            continue

        timestamps.sort()
        intervals = []
        for i in range(1, len(timestamps)):
            interval = (timestamps[i] - timestamps[i - 1]).total_seconds()
            intervals.append(interval)

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)
        min_interval = min(intervals)
        max_interval = max(intervals)

        # 检测突发模式（短时间内大量错误）
        burst_threshold = avg_interval * 0.1 if avg_interval > 0 else 0
        burst_count = sum(1 for iv in intervals if iv <= burst_threshold) if burst_threshold > 0 else 0

        pattern_type = "periodic"
        description = f"{category} 类错误平均间隔 {avg_interval:.1f} 秒"

        if burst_count > len(intervals) * 0.3:
            pattern_type = "burst"
            description = f"{category} 类错误存在突发模式，共 {burst_count} 次密集出现"
        elif max_interval > avg_interval * 5:
            pattern_type = "irregular"
            description = f"{category} 类错误分布不均匀，最长间隔 {max_interval:.1f} 秒"

        patterns.append({
            "category": category,
            "pattern": pattern_type,
            "count": len(timestamps),
            "avg_interval_seconds": round(avg_interval, 2),
            "description": description,
        })

    return patterns


def _analyze_cross_category_correlations(logs: list[dict]) -> list[dict]:
    """发现不同类别错误之间的关联

    例如：连接错误激增后出现 InnoDB 错误

    Returns:
        关联列表，每项包含 source_category, target_category, correlation_type, description
    """
    category_timestamps = defaultdict(list)
    for log in logs:
        category = log.get("category", "other")
        ts = _parse_timestamp(log.get("timestamp"))
        if ts:
            category_timestamps[category].append(ts)

    correlations = []
    categories = list(category_timestamps.keys())

    for i, source_cat in enumerate(categories):
        for target_cat in categories[i + 1:]:
            source_ts = sorted(category_timestamps[source_cat])
            target_ts = sorted(category_timestamps[target_cat])

            if not source_ts or not target_ts:
                continue

            # 检测时序关联：source 类错误是否在 target 类错误之前出现
            follow_count = 0
            follow_window = 300  # 5 分钟窗口
            for s_ts in source_ts:
                for t_ts in target_ts:
                    delta = (t_ts - s_ts).total_seconds()
                    if 0 < delta <= follow_window:
                        follow_count += 1
                        break

            source_total = len(source_ts)
            if source_total > 0 and follow_count / source_total > 0.3:
                correlations.append({
                    "source_category": source_cat,
                    "target_category": target_cat,
                    "correlation_type": "temporal_follow",
                    "follow_ratio": round(follow_count / source_total, 2),
                    "description": (
                        f"{source_cat} 错误出现后，{target_cat} 错误在 5 分钟内跟随出现的比例为 "
                        f"{follow_count / source_total:.0%}"
                    ),
                })

    return correlations


def _detect_anomaly_frequency(logs: list[dict]) -> list[dict]:
    """识别异常频率（某类错误突然增多）

    Returns:
        异常频率列表
    """
    category_timestamps = defaultdict(list)
    for log in logs:
        category = log.get("category", "other")
        ts = _parse_timestamp(log.get("timestamp"))
        if ts:
            category_timestamps[category].append(ts)

    anomalies = []

    for category, timestamps in category_timestamps.items():
        if len(timestamps) < 5:
            continue

        timestamps.sort()

        # 按小时分组统计
        hourly_counts = Counter()
        for ts in timestamps:
            hour_key = ts.strftime("%Y-%m-%d %H:00")
            hourly_counts[hour_key] += 1

        if len(hourly_counts) < 2:
            continue

        counts = list(hourly_counts.values())
        avg_count = sum(counts) / len(counts)

        # 检测超过平均值 3 倍的小时
        for hour_key, count in hourly_counts.items():
            if count > avg_count * 3 and count > 3:
                anomalies.append({
                    "category": category,
                    "anomaly_type": "frequency_spike",
                    "hour": hour_key,
                    "count": count,
                    "average": round(avg_count, 2),
                    "ratio": round(count / avg_count, 2),
                    "description": (
                        f"{category} 类错误在 {hour_key} 出现 {count} 次，"
                        f"是平均 {avg_count:.1f} 次的 {count / avg_count:.1f} 倍"
                    ),
                })

    return anomalies


class CorrelateNode:
    """关联分析节点：分析错误之间的关联和异常模式"""

    async def __call__(self, state: dict) -> dict:
        """执行关联分析

        输入状态：
            - classified_logs: list[dict]

        输出状态：
            - 增加 correlations 字段
        """
        classified_logs = state.get("classified_logs", [])
        logger.info("关联分析节点: 开始处理 %d 条分类日志", len(classified_logs))

        if not classified_logs:
            return {"correlations": []}

        # 分析时间分布模式
        time_patterns = _analyze_time_distribution(classified_logs)

        # 分析跨类别关联
        cross_correlations = _analyze_cross_category_correlations(classified_logs)

        # 检测异常频率
        anomalies = _detect_anomaly_frequency(classified_logs)

        correlations = {
            "time_patterns": time_patterns,
            "cross_category": cross_correlations,
            "anomalies": anomalies,
        }

        logger.info(
            "关联分析节点: 完成，发现 %d 个时间模式, %d 个跨类别关联, %d 个异常频率",
            len(time_patterns),
            len(cross_correlations),
            len(anomalies),
        )
        return {"correlations": correlations}
