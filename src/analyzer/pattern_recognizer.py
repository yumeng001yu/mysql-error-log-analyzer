"""日志模式识别引擎

自动聚类相似日志条目，发现异常模式（如突发 ERROR 暴增）。
使用基于消息模板的聚类算法，将相似日志归为同一模式。
"""
import re
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional


class LogPattern:
    """日志模式，表示一组相似日志的聚合"""

    def __init__(
        self,
        pattern_id: str,
        template: str,
        sample_message: str,
        level: str,
        category: str,
        count: int,
        first_seen: str,
        last_seen: str,
        error_codes: list[str],
        is_anomaly: bool = False,
        anomaly_score: float = 0.0,
        trend: str = "stable",
    ):
        self.pattern_id = pattern_id
        self.template = template
        self.sample_message = sample_message
        self.level = level
        self.category = category
        self.count = count
        self.first_seen = first_seen
        self.last_seen = last_seen
        self.error_codes = error_codes
        self.is_anomaly = is_anomaly
        self.anomaly_score = anomaly_score
        self.trend = trend

    def to_dict(self) -> dict:
        """转换为字典，用于 API 响应"""
        return {
            "pattern_id": self.pattern_id,
            "template": self.template,
            "sample_message": self.sample_message,
            "level": self.level,
            "category": self.category,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "error_codes": self.error_codes,
            "is_anomaly": self.is_anomaly,
            "anomaly_score": self.anomaly_score,
            "trend": self.trend,
        }


class PatternRecognizer:
    """日志模式识别器

    通过提取消息模板将相似日志聚类，并检测异常模式。
    """

    def __init__(self):
        # 预编译正则表达式，提升模板提取性能
        # UUID
        self._re_uuid = re.compile(
            r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
        )
        # IP 地址
        self._re_ip = re.compile(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        )
        # 十六进制值
        self._re_hex = re.compile(
            r'\b0x[0-9a-fA-F]+\b'
        )
        # 文件路径（Unix 风格）
        self._re_filepath = re.compile(
            r'(?:/[\w\-\.]+)+'
        )
        # 方括号中的线程 ID
        self._re_thread_id = re.compile(
            r'\[\d+\]'
        )
        # 独立数字
        self._re_number = re.compile(
            r'\b\d+\.?\d*\b'
        )
        # 时间戳（多种格式）
        self._re_timestamp = re.compile(
            r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?\b'
            r'|\b\d{2}:\d{2}:\d{2}\b'
            r'|\b\d{4}\d{2}\d{2}\s\d{2}\d{2}\d{2}\b'
        )
        # 长引号字符串（长度 >= 8）
        self._re_long_quoted = re.compile(
            r'"[^"]{8,}"'
            r"|'[^']{8,}'"
        )
        # TABLE/DATABASE 关键字后跟名称
        self._re_table_db_name = re.compile(
            r'\b(TABLE|DATABASE|SCHEMA|INDEX)\s+`?(\w+)`?',
            re.IGNORECASE,
        )

    def extract_template(self, message: str) -> str:
        """将日志消息中的变量部分替换为 *，生成通用模板

        替换规则（按优先级从高到低）：
        1. 时间戳 → *
        2. UUID → *
        3. IP 地址 → *
        4. 十六进制值 → *
        5. 文件路径 → *
        6. TABLE/DATABASE 等关键字后的名称 → 关键字 *
        7. 方括号中的线程 ID → [*]
        8. 长引号字符串 → "*"
        9. 独立数字 → *

        Args:
            message: 原始日志消息

        Returns:
            通用化后的模板字符串
        """
        if not message:
            return ""

        template = message

        # 1. 替换时间戳
        template = self._re_timestamp.sub('*', template)

        # 2. 替换 UUID
        template = self._re_uuid.sub('*', template)

        # 3. 替换 IP 地址
        template = self._re_ip.sub('*', template)

        # 4. 替换十六进制值
        template = self._re_hex.sub('*', template)

        # 5. 替换文件路径（仅当路径包含 / 且长度 >= 5 时）
        def _replace_filepath(m):
            matched = m.group(0)
            if len(matched) >= 5:
                return '*'
            return matched
        template = self._re_filepath.sub(_replace_filepath, template)

        # 6. 替换 TABLE/DATABASE 等关键字后的名称
        template = self._re_table_db_name.sub(r'\1 *', template)

        # 7. 替换方括号中的线程 ID
        template = self._re_thread_id.sub('[*]', template)

        # 8. 替换长引号字符串
        template = self._re_long_quoted.sub('"*"', template)

        # 9. 替换独立数字
        template = self._re_number.sub('*', template)

        # 清理多余空格
        template = re.sub(r'\s+', ' ', template).strip()

        return template

    async def recognize_patterns(
        self,
        db,
        instance_id=None,
        start_time=None,
        end_time=None,
        min_count=2,
    ) -> list[LogPattern]:
        """主方法：识别日志模式

        步骤：
        1. 查询日志数据
        2. 提取每条日志的模板
        3. 按 (模板, 级别, 类别) 分组
        4. 为每组创建 LogPattern
        5. 检测异常模式

        Args:
            db: DatabaseManager 实例
            instance_id: 可选的实例 ID 过滤
            start_time: 可选的开始时间
            end_time: 可选的结束时间
            min_count: 最小出现次数，低于此值的模式被过滤

        Returns:
            按出现次数降序排列的 LogPattern 列表
        """
        # 查询全部日志（分批获取）
        all_logs = []
        offset = 0
        batch_size = 1000
        while True:
            logs = await db.query_logs(
                instance_id=instance_id,
                start_time=start_time,
                end_time=end_time,
                limit=batch_size,
                offset=offset,
            )
            if not logs:
                break
            all_logs.extend(logs)
            if len(logs) < batch_size:
                break
            offset += batch_size

        if not all_logs:
            return []

        # 按 (模板, 级别, 类别) 分组
        groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for log in all_logs:
            message = log.get("message", "") or ""
            template = self.extract_template(message)
            level = log.get("level", "unknown")
            category = log.get("category", "other")
            key = (template, level, category)
            groups[key].append(log)

        # 为每组创建 LogPattern
        patterns: list[LogPattern] = []
        for (template, level, category), logs_in_group in groups.items():
            if len(logs_in_group) < min_count:
                continue

            # 计算 pattern_id（模板的哈希）
            pattern_id = hashlib.md5(template.encode()).hexdigest()[:12]

            # 收集统计信息
            timestamps = []
            error_codes_set: set[str] = set()
            sample_message = ""

            for log in logs_in_group:
                ts = log.get("timestamp", "")
                if ts:
                    timestamps.append(ts)
                ec = log.get("error_code")
                if ec:
                    error_codes_set.add(ec)
                # 取第一条作为样本消息
                if not sample_message and log.get("message"):
                    sample_message = log["message"]

            # 排序时间戳以获取 first_seen / last_seen
            timestamps.sort()
            first_seen = timestamps[0] if timestamps else ""
            last_seen = timestamps[-1] if timestamps else ""

            pattern = LogPattern(
                pattern_id=pattern_id,
                template=template,
                sample_message=sample_message,
                level=level,
                category=category,
                count=len(logs_in_group),
                first_seen=first_seen,
                last_seen=last_seen,
                error_codes=sorted(error_codes_set),
            )
            patterns.append(pattern)

        # 检测异常模式
        # 获取最近一小时的日志以构建 recent_patterns
        now = datetime.now()
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        recent_logs = []
        offset = 0
        while True:
            logs = await db.query_logs(
                instance_id=instance_id,
                start_time=one_hour_ago,
                limit=batch_size,
                offset=offset,
            )
            if not logs:
                break
            recent_logs.extend(logs)
            if len(logs) < batch_size:
                break
            offset += batch_size

        # 构建 recent_patterns
        recent_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for log in recent_logs:
            message = log.get("message", "") or ""
            template = self.extract_template(message)
            level = log.get("level", "unknown")
            category = log.get("category", "other")
            key = (template, level, category)
            recent_groups[key].append(log)

        recent_patterns: list[LogPattern] = []
        for (template, level, category), logs_in_group in recent_groups.items():
            pattern_id = hashlib.md5(template.encode()).hexdigest()[:12]
            timestamps = []
            error_codes_set: set[str] = set()
            sample_message = ""
            for log in logs_in_group:
                ts = log.get("timestamp", "")
                if ts:
                    timestamps.append(ts)
                ec = log.get("error_code")
                if ec:
                    error_codes_set.add(ec)
                if not sample_message and log.get("message"):
                    sample_message = log["message"]
            timestamps.sort()
            recent_patterns.append(LogPattern(
                pattern_id=pattern_id,
                template=template,
                sample_message=sample_message,
                level=level,
                category=category,
                count=len(logs_in_group),
                first_seen=timestamps[0] if timestamps else "",
                last_seen=timestamps[-1] if timestamps else "",
                error_codes=sorted(error_codes_set),
            ))

        # 执行异常检测
        patterns = self.detect_anomalies(patterns, recent_patterns)

        # 按出现次数降序排列
        patterns.sort(key=lambda p: p.count, reverse=True)

        return patterns

    def detect_anomalies(
        self,
        patterns: list[LogPattern],
        recent_patterns: list[LogPattern],
    ) -> list[LogPattern]:
        """对比近期模式与整体模式，检测异常

        异常判定标准：
        - 突增（Spike）：近期计数 > 3 倍平均每窗口计数 → anomaly_score = min(近期/平均/3, 1.0)
        - 新模式：近期出现但整体未出现过 → anomaly_score = 0.8
        - 递增趋势：最近 3 个窗口计数持续递增 → anomaly_score = 0.6

        Args:
            patterns: 整体模式列表
            recent_patterns: 近期模式列表

        Returns:
            更新了异常标记的模式列表
        """
        # 构建整体模式的快速查找表
        overall_map: dict[str, LogPattern] = {}
        for p in patterns:
            overall_map[p.pattern_id] = p

        # 构建近期模式的快速查找表
        recent_map: dict[str, LogPattern] = {}
        for p in recent_patterns:
            recent_map[p.pattern_id] = p

        # 检测突增和递增趋势
        for pattern in patterns:
            pid = pattern.pattern_id
            recent_p = recent_map.get(pid)

            if recent_p is not None:
                # 计算平均每窗口计数（将整体时间跨度划分为 1 小时窗口）
                try:
                    first = datetime.fromisoformat(pattern.first_seen)
                    last = datetime.fromisoformat(pattern.last_seen)
                    total_hours = max((last - first).total_seconds() / 3600, 1)
                except (ValueError, TypeError):
                    total_hours = 1

                avg_per_window = pattern.count / total_hours if total_hours > 0 else 0

                # 突增检测：近期 1 小时计数 > 3 倍平均每窗口计数
                if avg_per_window > 0 and recent_p.count > 3 * avg_per_window:
                    pattern.is_anomaly = True
                    pattern.anomaly_score = min(recent_p.count / avg_per_window / 3, 1.0)
                    pattern.trend = "spike"
                elif recent_p.count > pattern.count * 0.5:
                    # 近期计数占比较大，标记为递增
                    pattern.trend = "increasing"
                    pattern.anomaly_score = 0.6
                    pattern.is_anomaly = True
                elif recent_p.count == 0:
                    pattern.trend = "decreasing"
                else:
                    pattern.trend = "stable"
            else:
                # 近期未出现该模式
                pattern.trend = "decreasing"

        # 检测新模式（近期出现但整体未出现过）
        for recent_p in recent_patterns:
            if recent_p.pattern_id not in overall_map:
                # 新模式，添加到结果列表
                recent_p.is_anomaly = True
                recent_p.anomaly_score = 0.8
                recent_p.trend = "spike"
                patterns.append(recent_p)

        return patterns

    async def get_pattern_trend(
        self,
        db,
        pattern_id: str,
        instance_id=None,
        hours: int = 24,
    ) -> list[dict]:
        """获取指定模式的小时级趋势数据

        Args:
            db: DatabaseManager 实例
            pattern_id: 模式 ID
            instance_id: 可选的实例 ID 过滤
            hours: 回溯小时数，默认 24

        Returns:
            按小时聚合的计数列表，格式为 [{"hour": "2024-01-01 10:00", "count": 5}, ...]
        """
        now = datetime.now()
        start_time = (now - timedelta(hours=hours)).isoformat()

        # 查询时间范围内的日志
        all_logs = []
        offset = 0
        batch_size = 1000
        while True:
            logs = await db.query_logs(
                instance_id=instance_id,
                start_time=start_time,
                limit=batch_size,
                offset=offset,
            )
            if not logs:
                break
            all_logs.extend(logs)
            if len(logs) < batch_size:
                break
            offset += batch_size

        # 筛选属于该 pattern_id 的日志
        hourly_counts: dict[str, int] = defaultdict(int)

        for log in all_logs:
            message = log.get("message", "") or ""
            template = self.extract_template(message)
            pid = hashlib.md5(template.encode()).hexdigest()[:12]
            if pid != pattern_id:
                continue

            # 提取小时键
            ts = log.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts)
                hour_key = dt.strftime("%Y-%m-%d %H:00")
            except (ValueError, TypeError):
                continue

            hourly_counts[hour_key] += 1

        # 填充缺失的小时段（确保连续）
        result = []
        for i in range(hours):
            hour_dt = now - timedelta(hours=hours - 1 - i)
            hour_key = hour_dt.strftime("%Y-%m-%d %H:00")
            result.append({
                "hour": hour_key,
                "count": hourly_counts.get(hour_key, 0),
            })

        return result
