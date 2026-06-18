"""定期运维报表生成器

自动生成日报/周报/月报，包含 TOP 慢查询、告警统计、容量趋势。
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class ReportSection:
    """报表章节"""
    title: str
    content_type: str  # "text" | "table" | "list" | "metric_cards"
    data: Any = None   # 根据 content_type 不同而不同


@dataclass
class OperationsReport:
    """运维报表"""
    id: str
    report_type: str  # "daily" | "weekly" | "monthly"
    period_start: str
    period_end: str
    generated_at: str
    instance_id: Optional[int] = None
    instance_name: Optional[str] = None
    sections: list[ReportSection] = field(default_factory=list)
    summary: str = ""
    health_score: float = 0.0


class ReportGenerator:
    """定期运维报表生成器"""

    def __init__(self):
        self._tables_ready = False

    async def _ensure_tables(self, db: DatabaseManager):
        """懒加载创建报表相关表"""
        if self._tables_ready:
            return

        conn = await db._get_conn()

        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS operations_reports (
                id TEXT PRIMARY KEY,
                report_type TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                instance_id INTEGER,
                instance_name TEXT,
                health_score REAL NOT NULL DEFAULT 0,
                summary TEXT DEFAULT '',
                sections TEXT DEFAULT '[]',
                generated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_operations_reports_type
                ON operations_reports(report_type);
            CREATE INDEX IF NOT EXISTS idx_operations_reports_instance_id
                ON operations_reports(instance_id);
            CREATE INDEX IF NOT EXISTS idx_operations_reports_generated_at
                ON operations_reports(generated_at);
        """)

        await conn.commit()
        self._tables_ready = True

    async def generate_daily_report(
        self,
        db: DatabaseManager,
        instance_id: Optional[int] = None,
        date: Optional[str] = None,
    ) -> OperationsReport:
        """生成日报

        Args:
            db: 数据库管理器
            instance_id: 实例 ID，为 None 时汇总所有实例
            date: 日期字符串，格式 "2024-01-15"，默认为昨天
        """
        await self._ensure_tables(db)

        # 确定日期范围
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        else:
            target_date = datetime.now() - timedelta(days=1)

        period_start = target_date.strftime("%Y-%m-%d 00:00:00")
        period_end = target_date.strftime("%Y-%m-%d 23:59:59")
        period_start_iso = target_date.strftime("%Y-%m-%d")
        period_end_iso = period_start_iso

        # 前一天的时间范围（用于对比）
        prev_date = target_date - timedelta(days=1)
        prev_start = prev_date.strftime("%Y-%m-%d 00:00:00")
        prev_end = prev_date.strftime("%Y-%m-%d 23:59:59")

        # 获取实例名称
        instance_name = None
        if instance_id is not None:
            instance_name = await self._get_instance_name(db, instance_id)

        # ── 收集数据 ──────────────────────────────────────
        sections: list[ReportSection] = []

        # 1. 概览 - metric_cards
        total_errors = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="ERROR",
        )
        total_warnings = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="WARNING",
        )
        slow_queries = await db.count_slow_queries(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
        )
        alerts_fired = await self._count_alerts(
            db, instance_id=instance_id, start_time=period_start, end_time=period_end,
        )

        sections.append(ReportSection(
            title="概览",
            content_type="metric_cards",
            data={
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "slow_queries": slow_queries,
                "alerts_fired": alerts_fired,
            },
        ))

        # 2. 错误分布 - table
        error_dist = await self._get_error_distribution_with_change(
            db, instance_id, period_start, period_end, prev_start, prev_end,
        )
        sections.append(ReportSection(
            title="错误分布",
            content_type="table",
            data=error_dist or [{"level": "暂无数据", "count": 0, "change_vs_previous_day": 0}],
        ))

        # 3. TOP 10 慢查询 - table
        top_slow = await self._get_top_slow_queries(
            db, instance_id, period_start, period_end, limit=10,
        )
        sections.append(ReportSection(
            title="TOP 10 慢查询",
            content_type="table",
            data=top_slow or [{"rank": "-", "sql_hash": "暂无数据", "avg_time": 0, "count": 0, "template": ""}],
        ))

        # 4. 告警统计 - table
        alert_stats = await self._get_alert_stats(
            db, instance_id, period_start, period_end,
        )
        sections.append(ReportSection(
            title="告警统计",
            content_type="table",
            data=alert_stats or [{"rule_name": "暂无数据", "fired_count": 0, "level": ""}],
        ))

        # 5. 关键指标趋势 - list
        metrics_trend = await self._get_key_metrics_trend(
            db, instance_id, period_start, period_end, prev_start, prev_end,
        )
        sections.append(ReportSection(
            title="关键指标趋势",
            content_type="list",
            data=metrics_trend or [{"metric_name": "暂无数据", "current": 0, "previous": 0, "change_percent": 0}],
        ))

        # 6. 异常事件 - list
        anomaly_events = await self._get_anomaly_events(
            db, instance_id, period_start, period_end,
        )
        sections.append(ReportSection(
            title="异常事件",
            content_type="list",
            data=anomaly_events or [{"timestamp": "", "description": "暂无数据", "severity": ""}],
        ))

        # 7. 健康评分 - text
        health_score = self._calculate_health_score(
            total_errors, total_warnings, alerts_fired, alert_stats, slow_queries,
        )
        health_breakdown = self._get_health_breakdown(
            total_errors, total_warnings, alerts_fired, alert_stats, slow_queries,
        )
        sections.append(ReportSection(
            title="健康评分",
            content_type="text",
            data=f"综合健康评分: {health_score:.1f}/100\n{health_breakdown}",
        ))

        # 生成摘要
        summary = self._generate_daily_summary(
            total_errors, total_warnings, slow_queries, alerts_fired, health_score,
        )

        report = OperationsReport(
            id=str(uuid.uuid4()),
            report_type="daily",
            period_start=period_start_iso,
            period_end=period_end_iso,
            generated_at=datetime.now().isoformat(),
            instance_id=instance_id,
            instance_name=instance_name,
            sections=sections,
            summary=summary,
            health_score=health_score,
        )

        return report

    async def generate_weekly_report(
        self,
        db: DatabaseManager,
        instance_id: Optional[int] = None,
        week_start: Optional[str] = None,
    ) -> OperationsReport:
        """生成周报

        Args:
            db: 数据库管理器
            instance_id: 实例 ID，为 None 时汇总所有实例
            week_start: 周一日期字符串，格式 "2024-01-15"，默认为上周一
        """
        await self._ensure_tables(db)

        # 确定周范围
        if week_start:
            monday = datetime.strptime(week_start, "%Y-%m-%d")
        else:
            today = datetime.now()
            # 上周一
            monday = today - timedelta(days=today.weekday() + 7)

        sunday = monday + timedelta(days=6)

        period_start = monday.strftime("%Y-%m-%d 00:00:00")
        period_end = sunday.strftime("%Y-%m-%d 23:59:59")
        period_start_iso = monday.strftime("%Y-%m-%d")
        period_end_iso = sunday.strftime("%Y-%m-%d")

        # 上一周范围（用于对比）
        prev_monday = monday - timedelta(days=7)
        prev_sunday = prev_monday + timedelta(days=6)
        prev_start = prev_monday.strftime("%Y-%m-%d 00:00:00")
        prev_end = prev_sunday.strftime("%Y-%m-%d 23:59:59")

        # 获取实例名称
        instance_name = None
        if instance_id is not None:
            instance_name = await self._get_instance_name(db, instance_id)

        sections: list[ReportSection] = []

        # 1. 概览
        total_errors = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="ERROR",
        )
        total_warnings = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="WARNING",
        )
        slow_queries = await db.count_slow_queries(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
        )
        alerts_fired = await self._count_alerts(
            db, instance_id=instance_id, start_time=period_start, end_time=period_end,
        )

        sections.append(ReportSection(
            title="概览",
            content_type="metric_cards",
            data={
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "slow_queries": slow_queries,
                "alerts_fired": alerts_fired,
            },
        ))

        # 2. 错误分布
        error_dist = await self._get_error_distribution_with_change(
            db, instance_id, period_start, period_end, prev_start, prev_end,
        )
        sections.append(ReportSection(
            title="错误分布",
            content_type="table",
            data=error_dist or [{"level": "暂无数据", "count": 0, "change_vs_previous_day": 0}],
        ))

        # 3. TOP 10 慢查询
        top_slow = await self._get_top_slow_queries(
            db, instance_id, period_start, period_end, limit=10,
        )
        sections.append(ReportSection(
            title="TOP 10 慢查询",
            content_type="table",
            data=top_slow or [{"rank": "-", "sql_hash": "暂无数据", "avg_time": 0, "count": 0, "template": ""}],
        ))

        # 4. 告警统计
        alert_stats = await self._get_alert_stats(
            db, instance_id, period_start, period_end,
        )
        sections.append(ReportSection(
            title="告警统计",
            content_type="table",
            data=alert_stats or [{"rule_name": "暂无数据", "fired_count": 0, "level": ""}],
        ))

        # 5. 关键指标趋势
        metrics_trend = await self._get_key_metrics_trend(
            db, instance_id, period_start, period_end, prev_start, prev_end,
        )
        sections.append(ReportSection(
            title="关键指标趋势",
            content_type="list",
            data=metrics_trend or [{"metric_name": "暂无数据", "current": 0, "previous": 0, "change_percent": 0}],
        ))

        # 6. 异常事件
        anomaly_events = await self._get_anomaly_events(
            db, instance_id, period_start, period_end,
        )
        sections.append(ReportSection(
            title="异常事件",
            content_type="list",
            data=anomaly_events or [{"timestamp": "", "description": "暂无数据", "severity": ""}],
        ))

        # 7. 周趋势对比 - 每日错误数
        daily_trend = await self._get_daily_error_trend(
            db, instance_id, monday, sunday,
        )
        sections.append(ReportSection(
            title="周趋势对比",
            content_type="table",
            data=daily_trend or [{"date": "暂无数据", "error_count": 0, "warning_count": 0}],
        ))

        # 8. TOP 变化 - 与上周对比变化最大的指标
        top_changes = await self._get_top_changes(
            db, instance_id, period_start, period_end, prev_start, prev_end,
        )
        sections.append(ReportSection(
            title="TOP 变化",
            content_type="list",
            data=top_changes or [{"metric_name": "暂无数据", "current": 0, "previous": 0, "change_percent": 0}],
        ))

        # 9. 健康评分
        health_score = self._calculate_health_score(
            total_errors, total_warnings, alerts_fired, alert_stats, slow_queries,
        )
        health_breakdown = self._get_health_breakdown(
            total_errors, total_warnings, alerts_fired, alert_stats, slow_queries,
        )
        sections.append(ReportSection(
            title="健康评分",
            content_type="text",
            data=f"综合健康评分: {health_score:.1f}/100\n{health_breakdown}",
        ))

        summary = self._generate_weekly_summary(
            total_errors, total_warnings, slow_queries, alerts_fired, health_score,
        )

        report = OperationsReport(
            id=str(uuid.uuid4()),
            report_type="weekly",
            period_start=period_start_iso,
            period_end=period_end_iso,
            generated_at=datetime.now().isoformat(),
            instance_id=instance_id,
            instance_name=instance_name,
            sections=sections,
            summary=summary,
            health_score=health_score,
        )

        return report

    async def generate_monthly_report(
        self,
        db: DatabaseManager,
        instance_id: Optional[int] = None,
        month: Optional[str] = None,
    ) -> OperationsReport:
        """生成月报

        Args:
            db: 数据库管理器
            instance_id: 实例 ID，为 None 时汇总所有实例
            month: 月份字符串，格式 "2024-01"，默认为上月
        """
        await self._ensure_tables(db)

        # 确定月份范围
        if month:
            first_day = datetime.strptime(month, "%Y-%m")
        else:
            today = datetime.now()
            # 上月第一天
            first_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

        # 该月最后一天
        next_month = first_day.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)

        period_start = first_day.strftime("%Y-%m-%d 00:00:00")
        period_end = last_day.strftime("%Y-%m-%d 23:59:59")
        period_start_iso = first_day.strftime("%Y-%m-%d")
        period_end_iso = last_day.strftime("%Y-%m-%d")

        # 上月范围（用于对比）
        prev_first = (first_day - timedelta(days=1)).replace(day=1)
        prev_last = first_day - timedelta(days=1)
        prev_start = prev_first.strftime("%Y-%m-%d 00:00:00")
        prev_end = prev_last.strftime("%Y-%m-%d 23:59:59")

        # 获取实例名称
        instance_name = None
        if instance_id is not None:
            instance_name = await self._get_instance_name(db, instance_id)

        sections: list[ReportSection] = []

        # 1. 月度概览
        total_errors = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="ERROR",
        )
        total_warnings = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="WARNING",
        )
        total_critical = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="CRITICAL",
        )
        slow_queries = await db.count_slow_queries(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
        )
        alerts_fired = await self._count_alerts(
            db, instance_id=instance_id, start_time=period_start, end_time=period_end,
        )

        sections.append(ReportSection(
            title="月度概览",
            content_type="metric_cards",
            data={
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "total_critical": total_critical,
                "slow_queries": slow_queries,
                "alerts_fired": alerts_fired,
            },
        ))

        # 2. 容量趋势 - 磁盘/连接/查询量趋势
        capacity_trend = await self._get_capacity_trend(
            db, instance_id, first_day, last_day,
        )
        sections.append(ReportSection(
            title="容量趋势",
            content_type="table",
            data=capacity_trend or [{"metric": "暂无数据", "current": 0, "peak": 0, "avg": 0}],
        ))

        # 3. TOP 20 慢查询
        top_slow = await self._get_top_slow_queries(
            db, instance_id, period_start, period_end, limit=20,
        )
        sections.append(ReportSection(
            title="TOP 20 慢查询",
            content_type="table",
            data=top_slow or [{"rank": "-", "sql_hash": "暂无数据", "avg_time": 0, "count": 0, "template": ""}],
        ))

        # 4. 告警趋势 - 按周统计告警数
        alert_trend = await self._get_alert_trend_by_week(
            db, instance_id, first_day, last_day,
        )
        sections.append(ReportSection(
            title="告警趋势",
            content_type="table",
            data=alert_trend or [{"week": "暂无数据", "count": 0}],
        ))

        # 5. 优化建议 - 基于观察到的模式
        optimization_suggestions = await self._get_optimization_suggestions(
            db, instance_id, period_start, period_end,
        )
        sections.append(ReportSection(
            title="优化建议",
            content_type="list",
            data=optimization_suggestions or ["暂无数据"],
        ))

        # 6. 健康评分
        alert_stats = await self._get_alert_stats(db, instance_id, period_start, period_end)
        health_score = self._calculate_health_score(
            total_errors, total_warnings, alerts_fired,
            alert_stats,
            slow_queries,
        )
        health_breakdown = self._get_health_breakdown(
            total_errors, total_warnings, alerts_fired,
            alert_stats,
            slow_queries,
        )
        sections.append(ReportSection(
            title="健康评分",
            content_type="text",
            data=f"综合健康评分: {health_score:.1f}/100\n{health_breakdown}",
        ))

        summary = self._generate_monthly_summary(
            total_errors, total_warnings, total_critical,
            slow_queries, alerts_fired, health_score,
        )

        report = OperationsReport(
            id=str(uuid.uuid4()),
            report_type="monthly",
            period_start=period_start_iso,
            period_end=period_end_iso,
            generated_at=datetime.now().isoformat(),
            instance_id=instance_id,
            instance_name=instance_name,
            sections=sections,
            summary=summary,
            health_score=health_score,
        )

        return report

    async def save_report(self, db: DatabaseManager, report: OperationsReport) -> str:
        """保存报表到数据库

        Args:
            db: 数据库管理器
            report: 运维报表对象

        Returns:
            报表 ID
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        # 序列化 sections 为 JSON
        sections_json = json.dumps(
            [{"title": s.title, "content_type": s.content_type, "data": s.data}
             for s in report.sections],
            ensure_ascii=False,
        )

        await conn.execute(
            """INSERT INTO operations_reports
               (id, report_type, period_start, period_end, instance_id,
                instance_name, health_score, summary, sections, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report.id,
                report.report_type,
                report.period_start,
                report.period_end,
                report.instance_id,
                report.instance_name,
                report.health_score,
                report.summary,
                sections_json,
                report.generated_at,
            ),
        )
        await conn.commit()

        return report.id

    async def get_report(self, db: DatabaseManager, report_id: str) -> Optional[OperationsReport]:
        """根据 ID 获取已保存的报表

        Args:
            db: 数据库管理器
            report_id: 报表 ID

        Returns:
            运维报表对象，不存在则返回 None
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        cursor = await conn.execute(
            "SELECT * FROM operations_reports WHERE id = ?",
            (report_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_report(row)

    async def list_reports(
        self,
        db: DatabaseManager,
        report_type: Optional[str] = None,
        instance_id: Optional[int] = None,
        limit: int = 20,
    ) -> list[dict]:
        """列出已保存的报表（仅摘要信息，不含完整内容）

        Args:
            db: 数据库管理器
            report_type: 报表类型过滤 ("daily" | "weekly" | "monthly")
            instance_id: 实例 ID 过滤
            limit: 返回数量限制

        Returns:
            报表摘要列表
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        conditions = []
        params: list[Any] = []

        if report_type is not None:
            conditions.append("report_type = ?")
            params.append(report_type)
        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        cursor = await conn.execute(
            f"""SELECT id, report_type, period_start, period_end,
                       instance_id, instance_name, health_score, summary, generated_at
                FROM operations_reports
                WHERE {where_clause}
                ORDER BY generated_at DESC
                LIMIT ?""",
            params,
        )
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def delete_report(self, db: DatabaseManager, report_id: str) -> bool:
        """删除报表

        Args:
            db: 数据库管理器
            report_id: 报表 ID

        Returns:
            是否删除成功
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        cursor = await conn.execute(
            "SELECT id FROM operations_reports WHERE id = ?",
            (report_id,),
        )
        if await cursor.fetchone() is None:
            return False

        await conn.execute(
            "DELETE FROM operations_reports WHERE id = ?",
            (report_id,),
        )
        await conn.commit()
        return True

    async def get_latest_report(
        self,
        db: DatabaseManager,
        report_type: str,
        instance_id: Optional[int] = None,
    ) -> Optional[OperationsReport]:
        """获取指定类型的最新报表

        Args:
            db: 数据库管理器
            report_type: 报表类型 ("daily" | "weekly" | "monthly")
            instance_id: 实例 ID 过滤

        Returns:
            最新的运维报表对象，不存在则返回 None
        """
        await self._ensure_tables(db)
        conn = await db._get_conn()

        conditions = ["report_type = ?"]
        params: list[Any] = [report_type]

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)

        where_clause = " AND ".join(conditions)
        params.append(1)

        cursor = await conn.execute(
            f"""SELECT * FROM operations_reports
                WHERE {where_clause}
                ORDER BY generated_at DESC
                LIMIT ?""",
            params,
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_report(row)

    # ── 内部辅助方法 ──────────────────────────────────────

    def _row_to_report(self, row) -> OperationsReport:
        """将数据库行转换为 OperationsReport 对象"""
        # 反序列化 sections JSON
        try:
            sections_data = json.loads(row["sections"]) if row["sections"] else []
        except (json.JSONDecodeError, TypeError):
            sections_data = []

        sections = [
            ReportSection(
                title=s.get("title", ""),
                content_type=s.get("content_type", "text"),
                data=s.get("data"),
            )
            for s in sections_data
        ]

        return OperationsReport(
            id=row["id"],
            report_type=row["report_type"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            generated_at=row["generated_at"],
            instance_id=row["instance_id"],
            instance_name=row["instance_name"],
            sections=sections,
            summary=row["summary"] or "",
            health_score=row["health_score"] or 0.0,
        )

    async def _get_instance_name(self, db: DatabaseManager, instance_id: int) -> Optional[str]:
        """获取实例名称"""
        try:
            conn = await db._get_conn()
            cursor = await conn.execute(
                "SELECT name FROM instances WHERE id = ?",
                (instance_id,),
            )
            row = await cursor.fetchone()
            return row["name"] if row else None
        except Exception:
            return None

    async def _count_alerts(
        self,
        db: DatabaseManager,
        instance_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> int:
        """统计告警数量"""
        try:
            conn = await db._get_conn()

            conditions = []
            params: list[Any] = []

            if instance_id is not None:
                conditions.append("instance_id = ?")
                params.append(instance_id)
            if start_time is not None:
                conditions.append("triggered_at >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("triggered_at <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor = await conn.execute(
                f"SELECT COUNT(*) as cnt FROM alert_history WHERE {where_clause}",
                params,
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
        except Exception:
            # alert_history 表可能不存在
            return 0

    async def _get_error_distribution_with_change(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        period_start: str,
        period_end: str,
        prev_start: str,
        prev_end: str,
    ) -> list[dict]:
        """获取错误分布及与前一时段的对比变化"""
        # 当前时段
        current_dist = await db.get_error_distribution(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
        )
        # 前一时段
        prev_dist = await db.get_error_distribution(
            instance_id=instance_id, start_time=prev_start, end_time=prev_end,
        )

        # 构建前一时段的级别计数映射
        prev_level_map = {item["level"]: item["count"] for item in prev_dist.get("by_level", [])}

        result = []
        for item in current_dist.get("by_level", []):
            level = item["level"]
            count = item["count"]
            prev_count = prev_level_map.get(level, 0)
            change = count - prev_count
            result.append({
                "level": level,
                "count": count,
                "change_vs_previous_day": change,
            })

        return result

    async def _get_top_slow_queries(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        start_time: str,
        end_time: str,
        limit: int = 10,
    ) -> list[dict]:
        """获取 TOP N 慢查询"""
        try:
            conn = await db._get_conn()

            conditions = []
            params: list[Any] = []

            if instance_id is not None:
                conditions.append("instance_id = ?")
                params.append(instance_id)
            if start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("timestamp <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)

            cursor = await conn.execute(
                f"""SELECT sql_hash, sql_template,
                           COUNT(*) as count,
                           AVG(query_time) as avg_time,
                           MAX(query_time) as max_time,
                           SUM(query_time) as total_time
                    FROM slow_queries
                    WHERE {where_clause}
                    GROUP BY sql_hash
                    ORDER BY total_time DESC
                    LIMIT ?""",
                params,
            )
            rows = await cursor.fetchall()

            result = []
            for idx, row in enumerate(rows, 1):
                result.append({
                    "rank": idx,
                    "sql_hash": row["sql_hash"] or "",
                    "avg_time": round(row["avg_time"] or 0, 4),
                    "count": row["count"],
                    "template": row["sql_template"] or "",
                })

            return result
        except Exception:
            return []

    async def _get_alert_stats(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        start_time: str,
        end_time: str,
    ) -> list[dict]:
        """获取告警统计（按规则名称分组）"""
        try:
            conn = await db._get_conn()

            conditions = []
            params: list[Any] = []

            if instance_id is not None:
                conditions.append("instance_id = ?")
                params.append(instance_id)
            if start_time is not None:
                conditions.append("triggered_at >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("triggered_at <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor = await conn.execute(
                f"""SELECT rule_name, level, COUNT(*) as fired_count
                    FROM alert_history
                    WHERE {where_clause}
                    GROUP BY rule_name, level
                    ORDER BY fired_count DESC""",
                params,
            )
            rows = await cursor.fetchall()

            return [dict(row) for row in rows]
        except Exception:
            return []

    async def _get_key_metrics_trend(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        period_start: str,
        period_end: str,
        prev_start: str,
        prev_end: str,
    ) -> list[dict]:
        """获取关键指标趋势（当前 vs 前一时段）"""
        metrics = []

        # 错误数对比
        current_errors = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="ERROR",
        )
        prev_errors = await db.count_logs(
            instance_id=instance_id, start_time=prev_start, end_time=prev_end,
            level="ERROR",
        )
        metrics.append(self._build_metric_item("错误数", current_errors, prev_errors))

        # 警告数对比
        current_warnings = await db.count_logs(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
            level="WARNING",
        )
        prev_warnings = await db.count_logs(
            instance_id=instance_id, start_time=prev_start, end_time=prev_end,
            level="WARNING",
        )
        metrics.append(self._build_metric_item("警告数", current_warnings, prev_warnings))

        # 慢查询数对比
        current_slow = await db.count_slow_queries(
            instance_id=instance_id, start_time=period_start, end_time=period_end,
        )
        prev_slow = await db.count_slow_queries(
            instance_id=instance_id, start_time=prev_start, end_time=prev_end,
        )
        metrics.append(self._build_metric_item("慢查询数", current_slow, prev_slow))

        # 告警数对比
        current_alerts = await self._count_alerts(
            db, instance_id=instance_id, start_time=period_start, end_time=period_end,
        )
        prev_alerts = await self._count_alerts(
            db, instance_id=instance_id, start_time=prev_start, end_time=prev_end,
        )
        metrics.append(self._build_metric_item("告警数", current_alerts, prev_alerts))

        return metrics

    def _build_metric_item(self, name: str, current: int, previous: int) -> dict:
        """构建指标项"""
        if previous > 0:
            change_percent = round((current - previous) / previous * 100, 2)
        elif current > 0:
            change_percent = 100.0  # 从 0 增长视为 100%
        else:
            change_percent = 0.0

        return {
            "metric_name": name,
            "current": current,
            "previous": previous,
            "change_percent": change_percent,
        }

    async def _get_anomaly_events(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        start_time: str,
        end_time: str,
    ) -> list[dict]:
        """获取异常事件列表"""
        events = []

        # 从 critical_alerts 获取异常事件
        try:
            conn = await db._get_conn()

            conditions = []
            params: list[Any] = []

            if instance_id is not None:
                conditions.append("instance_id = ?")
                params.append(instance_id)
            if start_time is not None:
                conditions.append("created_at >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("created_at <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(50)  # 最多返回 50 条

            cursor = await conn.execute(
                f"""SELECT created_at as timestamp, alert_type as description, 'critical' as severity
                    FROM critical_alerts
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ?""",
                params,
            )
            rows = await cursor.fetchall()
            events.extend([dict(row) for row in rows])
        except Exception:
            pass

        # 从 alert_history 获取异常事件
        try:
            conn = await db._get_conn()

            conditions = []
            params: list[Any] = []

            if instance_id is not None:
                conditions.append("instance_id = ?")
                params.append(instance_id)
            if start_time is not None:
                conditions.append("triggered_at >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("triggered_at <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(50)

            cursor = await conn.execute(
                f"""SELECT triggered_at as timestamp, message as description, level as severity
                    FROM alert_history
                    WHERE {where_clause}
                    ORDER BY triggered_at DESC
                    LIMIT ?""",
                params,
            )
            rows = await cursor.fetchall()
            events.extend([dict(row) for row in rows])
        except Exception:
            pass

        # 按时间排序，取前 50 条
        events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return events[:50]

    async def _get_daily_error_trend(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        monday: datetime,
        sunday: datetime,
    ) -> list[dict]:
        """获取一周内每日错误数趋势"""
        result = []
        for i in range(7):
            day = monday + timedelta(days=i)
            day_start = day.strftime("%Y-%m-%d 00:00:00")
            day_end = day.strftime("%Y-%m-%d 23:59:59")

            error_count = await db.count_logs(
                instance_id=instance_id, start_time=day_start, end_time=day_end,
                level="ERROR",
            )
            warning_count = await db.count_logs(
                instance_id=instance_id, start_time=day_start, end_time=day_end,
                level="WARNING",
            )

            result.append({
                "date": day.strftime("%Y-%m-%d"),
                "error_count": error_count,
                "warning_count": warning_count,
            })

        return result

    async def _get_top_changes(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        period_start: str,
        period_end: str,
        prev_start: str,
        prev_end: str,
    ) -> list[dict]:
        """获取与上一时段对比变化最大的指标"""
        metrics = await self._get_key_metrics_trend(
            db, instance_id, period_start, period_end, prev_start, prev_end,
        )

        # 按变化幅度绝对值排序
        metrics.sort(key=lambda x: abs(x["change_percent"]), reverse=True)
        return metrics[:5]

    async def _get_capacity_trend(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        first_day: datetime,
        last_day: datetime,
    ) -> list[dict]:
        """获取容量趋势（磁盘/连接/查询量）"""
        result = []

        try:
            conn = await db._get_conn()

            # 查询监控指标中的容量相关数据
            metric_names = ["disk_usage", "connections", "queries_per_second"]
            display_names = ["磁盘使用率(%)", "活跃连接数", "每秒查询数(QPS)"]

            for metric_name, display_name in zip(metric_names, display_names):
                conditions = ["metric_name = ?"]
                params: list[Any] = [metric_name]

                if instance_id is not None:
                    conditions.append("instance_id = ?")
                    params.append(instance_id)

                start_str = first_day.strftime("%Y-%m-%d 00:00:00")
                end_str = last_day.strftime("%Y-%m-%d 23:59:59")
                conditions.append("collected_at >= ?")
                params.append(start_str)
                conditions.append("collected_at <= ?")
                params.append(end_str)

                where_clause = " AND ".join(conditions)

                cursor = await conn.execute(
                    f"""SELECT MAX(metric_value) as peak,
                               AVG(metric_value) as avg_val,
                               MIN(metric_value) as min_val
                        FROM monitor_metrics
                        WHERE {where_clause}""",
                    params,
                )
                row = await cursor.fetchone()

                if row and row["peak"] is not None:
                    result.append({
                        "metric": display_name,
                        "current": round(row["avg_val"] or 0, 2),
                        "peak": round(row["peak"] or 0, 2),
                        "avg": round(row["avg_val"] or 0, 2),
                    })
                else:
                    result.append({
                        "metric": display_name,
                        "current": 0,
                        "peak": 0,
                        "avg": 0,
                    })
        except Exception:
            # 如果查询失败，返回空指标
            result = [
                {"metric": "磁盘使用率(%)", "current": 0, "peak": 0, "avg": 0},
                {"metric": "活跃连接数", "current": 0, "peak": 0, "avg": 0},
                {"metric": "每秒查询数(QPS)", "current": 0, "peak": 0, "avg": 0},
            ]

        return result

    async def _get_alert_trend_by_week(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        first_day: datetime,
        last_day: datetime,
    ) -> list[dict]:
        """按周统计告警趋势"""
        result = []

        try:
            conn = await db._get_conn()

            conditions = []
            params: list[Any] = []

            if instance_id is not None:
                conditions.append("instance_id = ?")
                params.append(instance_id)

            start_str = first_day.strftime("%Y-%m-%d 00:00:00")
            end_str = last_day.strftime("%Y-%m-%d 23:59:59")
            conditions.append("triggered_at >= ?")
            params.append(start_str)
            conditions.append("triggered_at <= ?")
            params.append(end_str)

            where_clause = " AND ".join(conditions)

            cursor = await conn.execute(
                f"""SELECT strftime('%Y-W%W', triggered_at) AS week,
                           COUNT(*) as count
                    FROM alert_history
                    WHERE {where_clause}
                    GROUP BY week
                    ORDER BY week""",
                params,
            )
            rows = await cursor.fetchall()
            result = [dict(row) for row in rows]
        except Exception:
            pass

        return result

    async def _get_optimization_suggestions(
        self,
        db: DatabaseManager,
        instance_id: Optional[int],
        start_time: str,
        end_time: str,
    ) -> list[str]:
        """基于观察到的模式生成优化建议"""
        suggestions = []

        # 检查慢查询情况
        slow_stats = await db.get_slow_query_stats(
            instance_id=instance_id, start_time=start_time, end_time=end_time,
        )
        if slow_stats.get("total_count", 0) > 0:
            avg_time = slow_stats.get("avg_query_time", 0)
            if avg_time > 5:
                suggestions.append(
                    f"平均慢查询时间 {avg_time:.2f}s，建议检查索引优化和查询语句"
                )

            top_slow = slow_stats.get("top_slow", [])
            if top_slow:
                top_hash = top_slow[0].get("sql_hash", "")
                top_count = top_slow[0].get("count", 0)
                if top_count > 10:
                    suggestions.append(
                        f"SQL Hash {top_hash} 出现 {top_count} 次慢查询，建议优先优化该查询"
                    )

        # 检查错误分布
        error_dist = await db.get_error_distribution(
            instance_id=instance_id, start_time=start_time, end_time=end_time,
        )
        by_category = error_dist.get("by_category", [])
        for cat in by_category:
            if cat.get("category") == "connection" and cat.get("count", 0) > 5:
                suggestions.append(
                    f"连接相关错误 {cat['count']} 次，建议检查连接池配置和网络状况"
                )
            if cat.get("category") == "innodb" and cat.get("count", 0) > 3:
                suggestions.append(
                    f"InnoDB 相关错误 {cat['count']} 次，建议检查缓冲池和锁等待情况"
                )

        # 检查告警情况
        alert_stats = await self._get_alert_stats(
            db, instance_id, start_time, end_time,
        )
        critical_alerts = [a for a in alert_stats if a.get("level") == "critical"]
        if critical_alerts:
            total_critical = sum(a.get("fired_count", 0) for a in critical_alerts)
            suggestions.append(
                f"本月共触发 {total_critical} 次严重告警，建议排查根因并制定改进计划"
            )

        if not suggestions:
            suggestions.append("当前系统运行状况良好，无特别优化建议")

        return suggestions

    def _calculate_health_score(
        self,
        total_errors: int,
        total_warnings: int,
        alerts_fired: int,
        alert_stats: list[dict],
        slow_queries: int,
    ) -> float:
        """计算健康评分

        规则:
        - 基础分: 100
        - 每个 critical 错误: -5
        - 每个 warning 错误: -2
        - 每个 critical 告警: -10
        - 每个 warning 告警: -5
        - 每个慢查询: -3（最多扣 30）
        - 最低: 0
        """
        score = 100.0

        # 错误扣分
        score -= total_errors * 5
        score -= total_warnings * 2

        # 告警扣分
        critical_alert_count = 0
        warning_alert_count = 0
        for alert in alert_stats:
            level = alert.get("level", "")
            count = alert.get("fired_count", 0)
            if level == "critical":
                critical_alert_count += count
            elif level == "warning":
                warning_alert_count += count

        score -= critical_alert_count * 10
        score -= warning_alert_count * 5

        # 慢查询扣分（最多扣 30）
        slow_deduction = min(slow_queries * 3, 30)
        score -= slow_deduction

        return max(score, 0.0)

    def _get_health_breakdown(
        self,
        total_errors: int,
        total_warnings: int,
        alerts_fired: int,
        alert_stats: list[dict],
        slow_queries: int,
    ) -> str:
        """获取健康评分明细"""
        lines = []

        lines.append(f"  错误扣分: -{total_errors * 5} ({total_errors} 个错误 × 5)")
        lines.append(f"  警告扣分: -{total_warnings * 2} ({total_warnings} 个警告 × 2)")

        critical_alert_count = 0
        warning_alert_count = 0
        for alert in alert_stats:
            level = alert.get("level", "")
            count = alert.get("fired_count", 0)
            if level == "critical":
                critical_alert_count += count
            elif level == "warning":
                warning_alert_count += count

        lines.append(f"  严重告警扣分: -{critical_alert_count * 10} ({critical_alert_count} 个 × 10)")
        lines.append(f"  警告告警扣分: -{warning_alert_count * 5} ({warning_alert_count} 个 × 5)")

        slow_deduction = min(slow_queries * 3, 30)
        lines.append(f"  慢查询扣分: -{slow_deduction} ({slow_queries} 个 × 3, 上限 30)")

        return "\n".join(lines)

    def _generate_daily_summary(
        self,
        total_errors: int,
        total_warnings: int,
        slow_queries: int,
        alerts_fired: int,
        health_score: float,
    ) -> str:
        """生成日报摘要"""
        parts = []
        parts.append(f"错误 {total_errors} 条，警告 {total_warnings} 条")
        parts.append(f"慢查询 {slow_queries} 条")
        parts.append(f"告警 {alerts_fired} 次")
        parts.append(f"健康评分 {health_score:.1f}")

        if health_score >= 90:
            parts.append("系统运行良好")
        elif health_score >= 70:
            parts.append("系统存在少量问题，建议关注")
        elif health_score >= 50:
            parts.append("系统存在较多问题，需要排查")
        else:
            parts.append("系统健康状况较差，需要立即处理")

        return "，".join(parts)

    def _generate_weekly_summary(
        self,
        total_errors: int,
        total_warnings: int,
        slow_queries: int,
        alerts_fired: int,
        health_score: float,
    ) -> str:
        """生成周报摘要"""
        parts = []
        parts.append(f"本周错误 {total_errors} 条，警告 {total_warnings} 条")
        parts.append(f"慢查询 {slow_queries} 条")
        parts.append(f"告警 {alerts_fired} 次")
        parts.append(f"健康评分 {health_score:.1f}")

        if health_score >= 90:
            parts.append("本周系统整体运行良好")
        elif health_score >= 70:
            parts.append("本周系统存在少量问题，建议持续关注")
        elif health_score >= 50:
            parts.append("本周系统问题较多，需要重点排查")
        else:
            parts.append("本周系统健康状况较差，需要紧急处理")

        return "，".join(parts)

    def _generate_monthly_summary(
        self,
        total_errors: int,
        total_warnings: int,
        total_critical: int,
        slow_queries: int,
        alerts_fired: int,
        health_score: float,
    ) -> str:
        """生成月报摘要"""
        parts = []
        parts.append(f"本月错误 {total_errors} 条，警告 {total_warnings} 条，严重错误 {total_critical} 条")
        parts.append(f"慢查询 {slow_queries} 条")
        parts.append(f"告警 {alerts_fired} 次")
        parts.append(f"健康评分 {health_score:.1f}")

        if health_score >= 90:
            parts.append("本月系统整体运行稳定")
        elif health_score >= 70:
            parts.append("本月系统存在一些问题，建议制定优化计划")
        elif health_score >= 50:
            parts.append("本月系统问题较多，需要系统性排查和优化")
        else:
            parts.append("本月系统健康状况较差，需要紧急制定整改方案")

        return "，".join(parts)
