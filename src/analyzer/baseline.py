"""性能基线与异常检测引擎

自动建立 QPS/TPS/延迟等指标基线，偏离基线自动告警。
使用统计学方法（均值+标准差/百分位数）建立基线。
"""
import math
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict


@dataclass
class MetricBaseline:
    """指标基线数据结构"""

    metric_name: str
    period: str  # "hourly" | "daily" | "weekly"
    period_key: str  # 如 "hour:14" 表示下午2点, "day:Monday", "week:1"
    mean: float
    std: float
    min_val: float
    max_val: float
    p50: float  # 中位数
    p95: float
    p99: float
    sample_count: int
    last_updated: str


@dataclass
class AnomalyEvent:
    """异常事件数据结构"""

    id: str
    metric_name: str
    current_value: float
    baseline_mean: float
    baseline_std: float
    deviation: float  # 偏离均值多少个标准差
    direction: str  # "above" | "below"
    severity: str  # "low" | "medium" | "high" | "critical"
    detected_at: str
    description: str


class BaselineManager:
    """性能基线管理器，负责基线构建、异常检测和预测"""

    def __init__(self):
        self._tables_ready = False

    async def _ensure_tables(self, db):
        """懒加载创建 baseline_metrics 表"""
        if self._tables_ready:
            return

        conn = await db._get_conn()

        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS baseline_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER,
                metric_name TEXT NOT NULL,
                period TEXT NOT NULL,
                period_key TEXT NOT NULL,
                mean REAL NOT NULL,
                std REAL NOT NULL,
                min_val REAL NOT NULL,
                max_val REAL NOT NULL,
                p50 REAL NOT NULL,
                p95 REAL NOT NULL,
                p99 REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                last_updated TEXT NOT NULL,
                UNIQUE(instance_id, metric_name, period, period_key)
            );

            CREATE INDEX IF NOT EXISTS idx_baseline_metrics_instance_metric
                ON baseline_metrics(instance_id, metric_name);
            CREATE INDEX IF NOT EXISTS idx_baseline_metrics_period
                ON baseline_metrics(period, period_key);
        """)

        await conn.commit()
        self._tables_ready = True

    async def build_baselines(
        self, db, instance_id=None, days: int = 30
    ) -> list[MetricBaseline]:
        """从历史 monitor_metrics 数据构建基线

        步骤:
        1. 查询最近 N 天的 monitor_metrics 数据
        2. 按 (metric_name, period_type, period_key) 分组
           - hourly: 按小时 (0-23)
           - daily: 按星期 (0-6)
           - weekly: 按周数
        3. 对每个分组计算均值、标准差、最小值、最大值、百分位数
        4. 存储或更新 baseline_metrics 表

        Args:
            db: DatabaseManager 实例
            instance_id: 可选的实例 ID 过滤
            days: 回溯天数，默认 30 天

        Returns:
            构建的 MetricBaseline 列表
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        # 查询历史数据
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        conditions = ["collected_at >= ?"]
        params = [cutoff]

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)

        where_clause = " AND ".join(conditions)

        cursor = await conn.execute(
            f"""SELECT instance_id, metric_name, metric_value, collected_at
                FROM monitor_metrics
                WHERE {where_clause}
                ORDER BY collected_at ASC""",
            params,
        )
        rows = await cursor.fetchall()

        if not rows:
            return []

        # 按 (instance_id, metric_name) 分组
        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for row in rows:
            key = (row["instance_id"], row["metric_name"])
            grouped[key].append(dict(row))

        baselines: list[MetricBaseline] = []
        now = datetime.now().isoformat()

        for (inst_id, metric_name), metric_rows in grouped.items():
            # 按三种周期分别构建基线
            for period_type in ("hourly", "daily", "weekly"):
                period_groups: dict[str, list[float]] = defaultdict(list)

                for r in metric_rows:
                    try:
                        collected_dt = datetime.fromisoformat(r["collected_at"])
                    except (ValueError, TypeError):
                        continue

                    if period_type == "hourly":
                        period_key = f"hour:{collected_dt.hour}"
                    elif period_type == "daily":
                        # 0=Monday, 6=Sunday
                        day_names = [
                            "Monday", "Tuesday", "Wednesday",
                            "Thursday", "Friday", "Saturday", "Sunday",
                        ]
                        period_key = f"day:{day_names[collected_dt.weekday()]}"
                    else:  # weekly
                        iso_calendar = collected_dt.isocalendar()
                        period_key = f"week:{iso_calendar[1]}"

                    period_groups[period_key].append(r["metric_value"])

                # 对每个周期分组计算统计量并存储
                for period_key, values in period_groups.items():
                    stats = self._compute_stats(values)
                    if stats is None:
                        continue

                    baseline = MetricBaseline(
                        metric_name=metric_name,
                        period=period_type,
                        period_key=period_key,
                        mean=stats["mean"],
                        std=stats["std"],
                        min_val=stats["min"],
                        max_val=stats["max"],
                        p50=stats["p50"],
                        p95=stats["p95"],
                        p99=stats["p99"],
                        sample_count=stats["count"],
                        last_updated=now,
                    )
                    baselines.append(baseline)

                    # 存储或更新到数据库
                    await conn.execute(
                        """INSERT INTO baseline_metrics
                           (instance_id, metric_name, period, period_key,
                            mean, std, min_val, max_val, p50, p95, p99,
                            sample_count, last_updated)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(instance_id, metric_name, period, period_key)
                           DO UPDATE SET
                            mean=excluded.mean, std=excluded.std,
                            min_val=excluded.min_val, max_val=excluded.max_val,
                            p50=excluded.p50, p95=excluded.p95, p99=excluded.p99,
                            sample_count=excluded.sample_count,
                            last_updated=excluded.last_updated""",
                        (
                            inst_id,
                            metric_name,
                            period_type,
                            period_key,
                            stats["mean"],
                            stats["std"],
                            stats["min"],
                            stats["max"],
                            stats["p50"],
                            stats["p95"],
                            stats["p99"],
                            stats["count"],
                            now,
                        ),
                    )

        await conn.commit()
        return baselines

    async def detect_anomalies(
        self, db, instance_id=None, sensitivity: float = 2.0
    ) -> list[AnomalyEvent]:
        """将当前指标与基线对比，检测异常

        步骤:
        1. 获取当前最新指标值（从 monitor_metrics）
        2. 获取对应时间周期的基线
        3. 计算偏离度: (current - mean) / std
        4. 如果 |偏离度| > sensitivity 阈值，则判定为异常
        5. 根据偏离度确定严重程度:
           - > 3σ: critical
           - > 2.5σ: high
           - > 2σ: medium
           - 其余: 不算异常

        Args:
            db: DatabaseManager 实例
            instance_id: 可选的实例 ID 过滤
            sensitivity: 灵敏度阈值（标准差倍数），默认 2.0

        Returns:
            AnomalyEvent 列表
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        # 获取每个指标的最新值
        conditions = []
        params: list = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"""SELECT instance_id, metric_name, metric_value, collected_at
                FROM monitor_metrics
                WHERE {where_clause}
                ORDER BY collected_at DESC""",
            params,
        )
        all_rows = await cursor.fetchall()

        if not all_rows:
            return []

        # 取每个 (instance_id, metric_name) 的最新值
        latest_metrics: dict[tuple, dict] = {}
        for row in all_rows:
            key = (row["instance_id"], row["metric_name"])
            if key not in latest_metrics:
                latest_metrics[key] = dict(row)

        # 获取当前时间对应的周期键
        now = datetime.now()
        current_hour_key = f"hour:{now.hour}"
        day_names = [
            "Monday", "Tuesday", "Wednesday",
            "Thursday", "Friday", "Saturday", "Sunday",
        ]
        current_day_key = f"day:{day_names[now.weekday()]}"
        current_week_key = f"week:{now.isocalendar()[1]}"

        anomalies: list[AnomalyEvent] = []
        anomaly_counter = 0

        for (inst_id, metric_name), metric_data in latest_metrics.items():
            current_value = metric_data["metric_value"]

            # 查找对应的 hourly 基线（优先使用 hourly，更精确）
            cursor = await conn.execute(
                """SELECT mean, std, sample_count
                   FROM baseline_metrics
                   WHERE instance_id = ?
                     AND metric_name = ?
                     AND period = 'hourly'
                     AND period_key = ?""",
                (inst_id, metric_name, current_hour_key),
            )
            baseline_row = await cursor.fetchone()

            # 如果没有 hourly 基线，尝试 daily
            if baseline_row is None:
                cursor = await conn.execute(
                    """SELECT mean, std, sample_count
                       FROM baseline_metrics
                       WHERE instance_id = ?
                         AND metric_name = ?
                         AND period = 'daily'
                         AND period_key = ?""",
                    (inst_id, metric_name, current_day_key),
                )
                baseline_row = await cursor.fetchone()

            # 如果没有 daily 基线，尝试 weekly
            if baseline_row is None:
                cursor = await conn.execute(
                    """SELECT mean, std, sample_count
                       FROM baseline_metrics
                       WHERE instance_id = ?
                         AND metric_name = ?
                         AND period = 'weekly'
                         AND period_key = ?""",
                    (inst_id, metric_name, current_week_key),
                )
                baseline_row = await cursor.fetchone()

            # 没有找到任何基线，跳过
            if baseline_row is None:
                continue

            baseline_mean = baseline_row["mean"]
            baseline_std = baseline_row["std"]
            sample_count = baseline_row["sample_count"]

            # 样本数不足，跳过
            if sample_count < 3:
                continue

            # 标准差为 0（指标值完全不变），无法计算偏离度
            if baseline_std == 0:
                # 如果当前值与均值不同，视为异常
                if current_value != baseline_mean:
                    deviation = float("inf")
                else:
                    continue
            else:
                deviation = (current_value - baseline_mean) / baseline_std

            abs_deviation = abs(deviation)

            # 未超过灵敏度阈值，不算异常
            if abs_deviation <= sensitivity:
                continue

            # 确定方向
            direction = "above" if deviation > 0 else "below"

            # 确定严重程度
            if abs_deviation > 3.0:
                severity = "critical"
            elif abs_deviation > 2.5:
                severity = "high"
            else:
                severity = "medium"

            # 构建描述
            direction_label = "高于" if direction == "above" else "低于"
            severity_label = {
                "critical": "严重",
                "high": "高",
                "medium": "中等",
            }.get(severity, severity)

            description = (
                f"指标 {metric_name} 当前值 {current_value:.2f} "
                f"{direction_label}基线均值 {baseline_mean:.2f}，"
                f"偏离 {abs_deviation:.2f} 个标准差（基线标准差 {baseline_std:.2f}），"
                f"严重程度: {severity_label}"
            )

            anomaly_counter += 1
            anomaly = AnomalyEvent(
                id=f"anomaly_{now.strftime('%Y%m%d%H%M%S')}_{anomaly_counter}",
                metric_name=metric_name,
                current_value=current_value,
                baseline_mean=baseline_mean,
                baseline_std=baseline_std,
                deviation=round(deviation, 4),
                direction=direction,
                severity=severity,
                detected_at=now.isoformat(),
                description=description,
            )
            anomalies.append(anomaly)

        # 按严重程度排序: critical > high > medium
        severity_order = {"critical": 0, "high": 1, "medium": 2}
        anomalies.sort(key=lambda a: severity_order.get(a.severity, 3))

        return anomalies

    async def get_metric_forecast(
        self, db, metric_name: str, instance_id=None, hours: int = 24
    ) -> list[dict]:
        """基于小时基线预测未来 N 小时的指标值

        Args:
            db: DatabaseManager 实例
            metric_name: 指标名称
            instance_id: 可选的实例 ID
            hours: 预测小时数，默认 24

        Returns:
            预测数据列表，每项包含 hour, predicted, lower_bound, upper_bound
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        # 查询该指标的所有 hourly 基线
        conditions = ["metric_name = ?", "period = 'hourly'"]
        params: list = [metric_name]

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)

        where_clause = " AND ".join(conditions)

        cursor = await conn.execute(
            f"""SELECT period_key, mean, std, sample_count
                FROM baseline_metrics
                WHERE {where_clause}""",
            params,
        )
        rows = await cursor.fetchall()

        if not rows:
            return []

        # 构建小时基线映射: hour_index -> {mean, std}
        hourly_baselines: dict[int, dict] = {}
        for row in rows:
            # period_key 格式: "hour:14"
            try:
                hour = int(row["period_key"].split(":")[1])
                hourly_baselines[hour] = {
                    "mean": row["mean"],
                    "std": row["std"],
                    "sample_count": row["sample_count"],
                }
            except (IndexError, ValueError):
                continue

        if not hourly_baselines:
            return []

        # 从当前时间开始，预测未来 N 小时
        now = datetime.now()
        forecast: list[dict] = []

        for i in range(1, hours + 1):
            future_time = now + timedelta(hours=i)
            hour = future_time.hour

            baseline = hourly_baselines.get(hour)
            if baseline is None:
                # 没有该小时的基线，使用最近的可用基线的均值
                closest_hour = self._find_closest_hour(hour, hourly_baselines)
                if closest_hour is None:
                    continue
                baseline = hourly_baselines[closest_hour]

            predicted = baseline["mean"]
            std = baseline["std"]

            # 95% 置信区间: 均值 ± 1.96 * 标准差
            lower_bound = predicted - 1.96 * std
            upper_bound = predicted + 1.96 * std

            # 确保下界不为负（大多数指标非负）
            lower_bound = max(0.0, lower_bound)

            forecast.append({
                "hour": future_time.strftime("%Y-%m-%d %H:%M"),
                "predicted": round(predicted, 4),
                "lower_bound": round(lower_bound, 4),
                "upper_bound": round(upper_bound, 4),
            })

        return forecast

    async def get_baselines(
        self, db, metric_name: str = None, instance_id=None
    ) -> list[MetricBaseline]:
        """获取已存储的基线数据

        Args:
            db: DatabaseManager 实例
            metric_name: 可选的指标名称过滤
            instance_id: 可选的实例 ID 过滤

        Returns:
            MetricBaseline 列表
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        conditions = []
        params: list = []

        if metric_name is not None:
            conditions.append("metric_name = ?")
            params.append(metric_name)

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"""SELECT metric_name, period, period_key, mean, std,
                       min_val, max_val, p50, p95, p99,
                       sample_count, last_updated
                FROM baseline_metrics
                WHERE {where_clause}
                ORDER BY metric_name, period, period_key""",
            params,
        )
        rows = await cursor.fetchall()

        baselines = []
        for row in rows:
            baseline = MetricBaseline(
                metric_name=row["metric_name"],
                period=row["period"],
                period_key=row["period_key"],
                mean=row["mean"],
                std=row["std"],
                min_val=row["min_val"],
                max_val=row["max_val"],
                p50=row["p50"],
                p95=row["p95"],
                p99=row["p99"],
                sample_count=row["sample_count"],
                last_updated=row["last_updated"],
            )
            baselines.append(baseline)

        return baselines

    def _compute_stats(self, values: list[float]) -> Optional[dict]:
        """计算统计量：均值、标准差、最小值、最大值、百分位数

        Args:
            values: 数值列表

        Returns:
            包含统计量的字典，数据不足时返回 None
        """
        if not values:
            return None

        n = len(values)

        # 单个值无法计算有意义的标准差
        if n < 2:
            val = values[0]
            return {
                "mean": val,
                "std": 0.0,
                "min": val,
                "max": val,
                "p50": val,
                "p95": val,
                "p99": val,
                "count": n,
            }

        # 均值
        mean = sum(values) / n

        # 标准差（总体标准差）
        variance = sum((v - mean) ** 2 for v in values) / n
        std = math.sqrt(variance)

        # 排序用于百分位数计算
        sorted_vals = sorted(values)

        # 最小值和最大值
        min_val = sorted_vals[0]
        max_val = sorted_vals[-1]

        # 百分位数计算（线性插值法）
        def percentile(data: list[float], p: float) -> float:
            """计算百分位数"""
            if not data:
                return 0.0
            k = (len(data) - 1) * p / 100.0
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return data[int(k)]
            # 线性插值
            return data[int(f)] * (c - k) + data[int(c)] * (k - f)

        p50 = percentile(sorted_vals, 50)
        p95 = percentile(sorted_vals, 95)
        p99 = percentile(sorted_vals, 99)

        return {
            "mean": round(mean, 6),
            "std": round(std, 6),
            "min": round(min_val, 6),
            "max": round(max_val, 6),
            "p50": round(p50, 6),
            "p95": round(p95, 6),
            "p99": round(p99, 6),
            "count": n,
        }

    def _find_closest_hour(
        self, target_hour: int, available: dict[int, dict]
    ) -> Optional[int]:
        """找到与目标小时最接近的可用基线小时

        Args:
            target_hour: 目标小时 (0-23)
            available: 可用的小时基线映射

        Returns:
            最接近的小时索引，无可用数据时返回 None
        """
        if not available:
            return None

        min_distance = float("inf")
        closest = None

        for hour in available:
            # 考虑环形距离（23点和0点只差1小时）
            distance = min(abs(hour - target_hour), 24 - abs(hour - target_hour))
            if distance < min_distance:
                min_distance = distance
                closest = hour

        return closest
