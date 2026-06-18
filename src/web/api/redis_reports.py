"""Redis 运维报表 API

复用现有 ReportGenerator 架构（OperationsReport / ReportSection / 持久化能力），
数据来源改为 Redis 实时数据（INFO memory, INFO stats, SLOWLOG, CONFIG GET）。

端点:
- POST   /api/redis/reports/generate    — 生成报表（daily/weekly/monthly）
- GET    /api/redis/reports             — 列出已生成的报表
- GET    /api/redis/reports/{report_id} — 获取报表详情
- DELETE /api/redis/reports/{report_id} — 删除报表
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.analyzer.report_generator import (
    OperationsReport,
    ReportGenerator,
    ReportSection,
)
from src.collector.redis_connector import RedisConnector
from src.web.api.common import report_to_dict as _report_to_dict
from src.web.api.deps import get_db
from src.web.api.deps import get_redis_connector
from src.web.api.redis_monitor import _get_connector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/redis", tags=["Redis 运维报表"])

# ── 数据库与生成器实例 ──────────────────────────────────

_generator: ReportGenerator | None = None


def get_generator() -> ReportGenerator:
    """获取报表生成器实例（复用其持久化能力）"""
    global _generator
    if _generator is None:
        _generator = ReportGenerator()
    return _generator


# ── Redis 报表生成器 ────────────────────────────────────


class RedisReportGenerator:
    """Redis 运维报表生成器

    复用 ReportGenerator 的数据库持久化能力（save/get/list/delete），
    报表内容基于 Redis 实时数据生成，report_type 加 "redis_" 前缀。
    """

    def __init__(self):
        self._rg = ReportGenerator()

    # ── 数据采集 ────────────────────────────────────────

    async def _collect_redis_data(self, connector: RedisConnector) -> dict:
        """采集 Redis 实时数据：INFO memory / stats / clients / persistence + SLOWLOG + CONFIG GET"""
        data: dict = {}

        # INFO memory
        try:
            data["memory"] = await connector.get_memory_info()
        except Exception as e:
            logger.warning("INFO memory 失败: %s", e)
            data["memory"] = {}

        # INFO stats
        try:
            data["stats"] = await connector.get_stats_info()
        except Exception as e:
            logger.warning("INFO stats 失败: %s", e)
            data["stats"] = {}

        # INFO clients（连接数）
        try:
            data["clients"] = await connector.get_clients_info()
        except Exception as e:
            logger.warning("INFO clients 失败: %s", e)
            data["clients"] = {}

        # INFO persistence
        try:
            data["persistence"] = await connector.get_persistence_info()
        except Exception as e:
            logger.warning("INFO persistence 失败: %s", e)
            data["persistence"] = {}

        # SLOWLOG（Top 10）
        try:
            data["slowlog"] = await connector.get_slowlog(10)
        except Exception as e:
            logger.warning("SLOWLOG 失败: %s", e)
            data["slowlog"] = []

        # SLOWLOG LEN（慢查询总数）
        try:
            data["slowlog_len"] = await connector.get_slowlog_len()
        except Exception as e:
            logger.warning("SLOWLOG LEN 失败: %s", e)
            data["slowlog_len"] = 0

        # CONFIG GET
        try:
            data["config"] = await connector.get_config("*")
        except Exception as e:
            logger.warning("CONFIG GET 失败: %s", e)
            data["config"] = {}

        return data

    # ── 健康评分 ────────────────────────────────────────

    def _calculate_health_score(self, data: dict) -> tuple[float, list[str]]:
        """计算健康评分（100 分制）

        规则:
        - 碎片率 > 2.0: -10
        - 碎片率 > 1.5: -5
        - 淘汰策略为 noeviction 且内存使用率 > 80%: -10
        - 慢查询数 > 50: -10
        - 慢查询数 > 20: -5
        - AOF 未启用: -5
        - 连接数 > maxclients*80%: -10
        - 最低 0 分
        """
        score = 100.0
        breakdown: list[str] = []

        memory = data.get("memory", {})
        clients = data.get("clients", {})
        persistence = data.get("persistence", {})
        slowlog_len = data.get("slowlog_len", 0)

        # 碎片率
        frag_ratio = self._to_float(memory.get("mem_fragmentation_ratio"), 0.0)
        if frag_ratio > 2.0:
            score -= 10
            breakdown.append(f"碎片率 {frag_ratio:.2f} > 2.0: -10")
        elif frag_ratio > 1.5:
            score -= 5
            breakdown.append(f"碎片率 {frag_ratio:.2f} > 1.5: -5")

        # 淘汰策略 + 内存使用率
        maxmemory_policy = memory.get("maxmemory_policy", "noeviction")
        used_memory = self._to_int(memory.get("used_memory"), 0)
        maxmemory = self._to_int(memory.get("maxmemory"), 0)
        usage_percent = (used_memory / maxmemory * 100) if maxmemory > 0 else 0.0
        if maxmemory_policy == "noeviction" and usage_percent > 80:
            score -= 10
            breakdown.append(
                f"淘汰策略 noeviction 且内存使用率 {usage_percent:.2f}% > 80%: -10"
            )

        # 慢查询数
        if slowlog_len > 50:
            score -= 10
            breakdown.append(f"慢查询数 {slowlog_len} > 50: -10")
        elif slowlog_len > 20:
            score -= 5
            breakdown.append(f"慢查询数 {slowlog_len} > 20: -5")

        # AOF 未启用
        aof_enabled = self._to_int(persistence.get("aof_enabled"), 0)
        if not aof_enabled:
            score -= 5
            breakdown.append("AOF 未启用: -5")

        # 连接数 > maxclients*80%
        connected = self._to_int(clients.get("connected_clients"), 0)
        maxclients = self._to_int(clients.get("maxclients"), 0)
        if maxclients > 0 and connected > maxclients * 0.8:
            score -= 10
            breakdown.append(
                f"连接数 {connected} > maxclients*80% ({maxclients}): -10"
            )

        return max(score, 0.0), breakdown

    # ── 优化建议 ────────────────────────────────────────

    def _build_optimization_suggestions(self, data: dict) -> list[str]:
        """基于实际数据生成优化建议"""
        suggestions: list[str] = []

        memory = data.get("memory", {})
        clients = data.get("clients", {})
        persistence = data.get("persistence", {})
        stats = data.get("stats", {})
        config = data.get("config", {})
        slowlog_len = data.get("slowlog_len", 0)

        # 碎片率高 -> 开启 activedefrag
        frag_ratio = self._to_float(memory.get("mem_fragmentation_ratio"), 0.0)
        if frag_ratio > 1.5:
            activedefrag = config.get("activedefrag", "no")
            if activedefrag in ("no", "0", 0):
                suggestions.append(
                    f"内存碎片率 {frag_ratio:.2f} 偏高，建议开启 activedefrag 自动碎片整理"
                )
            else:
                suggestions.append(
                    f"内存碎片率 {frag_ratio:.2f} 偏高，activedefrag 已开启，建议关注碎片整理效果"
                )

        # AOF 未启用 -> 建议启用
        aof_enabled = self._to_int(persistence.get("aof_enabled"), 0)
        if not aof_enabled:
            suggestions.append("AOF 持久化未启用，建议开启 appendonly yes 以提升数据安全性")

        # noeviction + 高内存 -> 建议调整淘汰策略
        maxmemory_policy = memory.get("maxmemory_policy", "noeviction")
        used_memory = self._to_int(memory.get("used_memory"), 0)
        maxmemory = self._to_int(memory.get("maxmemory"), 0)
        usage_percent = (used_memory / maxmemory * 100) if maxmemory > 0 else 0.0
        if maxmemory_policy == "noeviction" and usage_percent > 80:
            suggestions.append(
                "淘汰策略为 noeviction 且内存使用率较高，建议调整为 allkeys-lru 等策略避免写入失败"
            )

        # 未设置 maxmemory
        if maxmemory == 0:
            suggestions.append("未设置 maxmemory，建议根据物理内存合理设置上限以防止 OOM")

        # 连接数高
        connected = self._to_int(clients.get("connected_clients"), 0)
        maxclients = self._to_int(clients.get("maxclients"), 0)
        if maxclients > 0 and connected > maxclients * 0.8:
            suggestions.append(
                f"连接数 {connected} 已达 maxclients 的 80% 以上，建议排查连接泄漏或调大 maxclients"
            )

        # 慢查询多
        if slowlog_len > 20:
            slower_than = config.get("slowlog-log-slower-than", "-1")
            suggestions.append(
                f"慢查询数 {slowlog_len} 较多，建议优化耗时命令或调整 slowlog-log-slower-than（当前 {slower_than}）"
            )

        # 命中率低
        keyspace_hits = self._to_int(stats.get("keyspace_hits"), 0)
        keyspace_misses = self._to_int(stats.get("keyspace_misses"), 0)
        total_access = keyspace_hits + keyspace_misses
        if total_access > 0:
            hit_rate = keyspace_hits / total_access * 100
            if hit_rate < 90:
                suggestions.append(
                    f"键命中率 {hit_rate:.2f}% 偏低，建议检查缓存预热与失效策略"
                )

        # 淘汰键多
        evicted_keys = self._to_int(stats.get("evicted_keys"), 0)
        if evicted_keys > 0 and maxmemory > 0:
            suggestions.append(
                f"已淘汰 {evicted_keys} 个键，建议评估容量是否需要扩容"
            )

        if not suggestions:
            suggestions.append("当前 Redis 实例运行状况良好，无特别优化建议")

        return suggestions

    # ── 章节构建 ────────────────────────────────────────

    def _build_overview_section(self, data: dict) -> ReportSection:
        """概览：内存使用/连接数/QPS/慢查询数"""
        memory = data.get("memory", {})
        clients = data.get("clients", {})
        stats = data.get("stats", {})

        used_memory = self._to_int(memory.get("used_memory"), 0)
        maxmemory = self._to_int(memory.get("maxmemory"), 0)
        usage_percent = round(used_memory / maxmemory * 100, 2) if maxmemory > 0 else None

        return ReportSection(
            title="概览",
            content_type="metric_cards",
            data={
                "used_memory": used_memory,
                "used_memory_human": memory.get("used_memory_human", "0B"),
                "maxmemory": maxmemory,
                "maxmemory_human": memory.get("maxmemory_human", "0B"),
                "memory_usage_percent": usage_percent,
                "connected_clients": self._to_int(clients.get("connected_clients"), 0),
                "maxclients": self._to_int(clients.get("maxclients"), 0),
                "qps": self._to_int(stats.get("instantaneous_ops_per_sec"), 0),
                "slowlog_count": data.get("slowlog_len", 0),
            },
        )

    def _build_memory_analysis_section(self, data: dict) -> ReportSection:
        """内存分析：碎片率/淘汰策略/峰值"""
        memory = data.get("memory", {})

        frag_ratio = self._to_float(memory.get("mem_fragmentation_ratio"), 0.0)
        if frag_ratio > 2.0:
            frag_status = "critical"
        elif frag_ratio > 1.5:
            frag_status = "warning"
        elif frag_ratio < 1.0 and frag_ratio > 0:
            frag_status = "low"
        else:
            frag_status = "healthy"

        used_memory = self._to_int(memory.get("used_memory"), 0)
        used_memory_peak = self._to_int(memory.get("used_memory_peak"), 0)
        maxmemory = self._to_int(memory.get("maxmemory"), 0)
        peak_usage_percent = (
            round(used_memory_peak / maxmemory * 100, 2) if maxmemory > 0 else None
        )

        rows = [
            {
                "metric": "内存碎片率",
                "value": f"{frag_ratio:.2f}",
                "status": frag_status,
                "fragmentation_bytes": self._to_int(
                    memory.get("mem_fragmentation_bytes"), 0
                ),
            },
            {
                "metric": "淘汰策略",
                "value": memory.get("maxmemory_policy", "noeviction"),
                "status": "info",
            },
            {
                "metric": "内存峰值",
                "value": memory.get("used_memory_peak_human", "0B"),
                "raw_bytes": used_memory_peak,
                "peak_usage_percent": peak_usage_percent,
                "status": "info",
            },
            {
                "metric": "当前内存使用",
                "value": memory.get("used_memory_human", "0B"),
                "raw_bytes": used_memory,
                "status": "info",
            },
        ]

        return ReportSection(
            title="内存分析",
            content_type="table",
            data=rows,
        )

    def _build_slowlog_top10_section(self, data: dict) -> ReportSection:
        """慢查询 Top 10"""
        slowlog = data.get("slowlog", []) or []
        rows = []
        for idx, entry in enumerate(slowlog[:10], 1):
            duration_us = self._to_int(entry.get("duration_us"), 0)
            rows.append({
                "rank": idx,
                "id": entry.get("id", ""),
                "duration_ms": round(duration_us / 1000, 2),
                "duration_us": duration_us,
                "command": entry.get("command", "")[:200],
                "client_ip": entry.get("client_ip", ""),
                "client_name": entry.get("client_name", ""),
                "start_time": entry.get("start_time", ""),
            })

        if not rows:
            rows = [{"rank": "-", "command": "暂无慢查询", "duration_ms": 0}]

        return ReportSection(
            title="慢查询 Top 10",
            content_type="table",
            data=rows,
        )

    def _build_persistence_section(self, data: dict) -> ReportSection:
        """持久化状态"""
        persistence = data.get("persistence", {})

        rows = [
            {
                "type": "RDB",
                "enabled": True,
                "last_save_time": self._to_int(
                    persistence.get("rdb_last_save_time"), 0
                ),
                "changes_since_last_save": self._to_int(
                    persistence.get("rdb_changes_since_last_save"), 0
                ),
                "bgsave_in_progress": self._to_int(
                    persistence.get("rdb_bgsave_in_progress"), 0
                ),
                "last_bgsave_status": persistence.get(
                    "rdb_last_bgsave_status", ""
                ),
            },
            {
                "type": "AOF",
                "enabled": bool(self._to_int(persistence.get("aof_enabled"), 0)),
                "rewrite_in_progress": self._to_int(
                    persistence.get("aof_rewrite_in_progress"), 0
                ),
                "current_size": self._to_int(
                    persistence.get("aof_current_size"), 0
                ),
                "base_size": self._to_int(persistence.get("aof_base_size"), 0),
                "rewrite_scheduled": self._to_int(
                    persistence.get("aof_rewrite_scheduled"), 0
                ),
            },
        ]

        return ReportSection(
            title="持久化状态",
            content_type="table",
            data=rows,
        )

    def _build_health_score_section(
        self, health_score: float, breakdown: list[str]
    ) -> ReportSection:
        """健康评分"""
        text = f"综合健康评分: {health_score:.1f}/100"
        if breakdown:
            text += "\n" + "\n".join(f"  - {line}" for line in breakdown)
        else:
            text += "\n  - 各项指标正常，无扣分项"

        return ReportSection(
            title="健康评分",
            content_type="text",
            data=text,
        )

    def _build_suggestions_section(self, suggestions: list[str]) -> ReportSection:
        """优化建议"""
        return ReportSection(
            title="优化建议",
            content_type="list",
            data=suggestions or ["暂无数据"],
        )

    # ── 历史趋势（周报/月报） ──────────────────────────

    async def _get_historical_reports(
        self,
        db: DatabaseManager,
        report_type: str,
        instance_id: Optional[int],
        limit: int,
    ) -> list[OperationsReport]:
        """获取历史报表（用于趋势对比）"""
        reports: list[OperationsReport] = []
        try:
            summaries = await self._rg.list_reports(
                db, report_type=report_type, instance_id=instance_id, limit=limit
            )
            for item in summaries:
                rid = item.get("id")
                if not rid:
                    continue
                rep = await self._rg.get_report(db, rid)
                if rep is not None:
                    reports.append(rep)
        except Exception as e:
            logger.warning("获取历史报表失败: %s", e)
        return reports

    def _extract_overview_metrics(self, report: OperationsReport) -> dict:
        """从已保存报表中提取概览指标"""
        for s in report.sections:
            if s.title == "概览" and isinstance(s.data, dict):
                return s.data
        return {}

    async def _build_daily_trend_section(
        self, db: DatabaseManager, instance_id: Optional[int]
    ) -> ReportSection:
        """每日指标趋势对比（基于历史 redis_daily 报表）"""
        reports = await self._get_historical_reports(
            db, "redis_daily", instance_id, limit=7
        )
        # 按生成时间升序
        reports.sort(key=lambda r: r.generated_at)

        rows = []
        for rep in reports:
            overview = self._extract_overview_metrics(rep)
            rows.append({
                "date": rep.period_start,
                "generated_at": rep.generated_at,
                "used_memory": overview.get("used_memory", 0),
                "connected_clients": overview.get("connected_clients", 0),
                "qps": overview.get("qps", 0),
                "slowlog_count": overview.get("slowlog_count", 0),
                "health_score": rep.health_score,
            })

        if not rows:
            rows = [{"date": "暂无历史数据", "used_memory": 0, "qps": 0}]

        return ReportSection(
            title="每日指标趋势对比",
            content_type="table",
            data=rows,
        )

    async def _build_capacity_trend_section(
        self, db: DatabaseManager, instance_id: Optional[int]
    ) -> ReportSection:
        """容量趋势（基于历史 redis_weekly/daily 报表）"""
        reports = await self._get_historical_reports(
            db, "redis_weekly", instance_id, limit=8
        )
        # 周报不足时补充日报
        if len(reports) < 2:
            daily_reports = await self._get_historical_reports(
                db, "redis_daily", instance_id, limit=30
            )
            reports.extend(daily_reports)

        reports.sort(key=lambda r: r.generated_at)

        rows = []
        for rep in reports:
            overview = self._extract_overview_metrics(rep)
            used_memory = overview.get("used_memory", 0)
            maxmemory = overview.get("maxmemory", 0)
            usage_percent = (
                round(used_memory / maxmemory * 100, 2) if maxmemory else None
            )
            rows.append({
                "period": f"{rep.period_start} ~ {rep.period_end}",
                "used_memory": used_memory,
                "maxmemory": maxmemory,
                "memory_usage_percent": usage_percent,
                "connected_clients": overview.get("connected_clients", 0),
                "health_score": rep.health_score,
            })

        if not rows:
            rows = [{"period": "暂无历史数据", "used_memory": 0}]

        return ReportSection(
            title="容量趋势",
            content_type="table",
            data=rows,
        )

    # ── 报表生成入口 ────────────────────────────────────

    async def generate_daily_report(
        self,
        db: DatabaseManager,
        connector: RedisConnector,
        instance_id: Optional[int] = None,
    ) -> OperationsReport:
        """生成 Redis 日报"""
        data = await self._collect_redis_data(connector)

        today = datetime.now()
        period_start = today.strftime("%Y-%m-%d")
        period_end = period_start

        sections: list[ReportSection] = []
        sections.append(self._build_overview_section(data))
        sections.append(self._build_memory_analysis_section(data))
        sections.append(self._build_slowlog_top10_section(data))
        sections.append(self._build_persistence_section(data))

        health_score, breakdown = self._calculate_health_score(data)
        sections.append(self._build_health_score_section(health_score, breakdown))

        suggestions = self._build_optimization_suggestions(data)
        sections.append(self._build_suggestions_section(suggestions))

        summary = self._generate_summary("日", data, health_score)

        return OperationsReport(
            id=str(uuid.uuid4()),
            report_type="redis_daily",
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now().isoformat(),
            instance_id=instance_id,
            instance_name=await self._resolve_instance_name(db, instance_id),
            sections=sections,
            summary=summary,
            health_score=health_score,
        )

    async def generate_weekly_report(
        self,
        db: DatabaseManager,
        connector: RedisConnector,
        instance_id: Optional[int] = None,
    ) -> OperationsReport:
        """生成 Redis 周报（日报内容 + 每日指标趋势对比）"""
        data = await self._collect_redis_data(connector)

        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        period_start = monday.strftime("%Y-%m-%d")
        period_end = sunday.strftime("%Y-%m-%d")

        sections: list[ReportSection] = []
        # 日报内容
        sections.append(self._build_overview_section(data))
        sections.append(self._build_memory_analysis_section(data))
        sections.append(self._build_slowlog_top10_section(data))
        sections.append(self._build_persistence_section(data))

        health_score, breakdown = self._calculate_health_score(data)
        sections.append(self._build_health_score_section(health_score, breakdown))

        suggestions = self._build_optimization_suggestions(data)
        sections.append(self._build_suggestions_section(suggestions))

        # 周报追加：每日指标趋势对比
        sections.append(await self._build_daily_trend_section(db, instance_id))

        summary = self._generate_summary("本周", data, health_score)

        return OperationsReport(
            id=str(uuid.uuid4()),
            report_type="redis_weekly",
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now().isoformat(),
            instance_id=instance_id,
            instance_name=await self._resolve_instance_name(db, instance_id),
            sections=sections,
            summary=summary,
            health_score=health_score,
        )

    async def generate_monthly_report(
        self,
        db: DatabaseManager,
        connector: RedisConnector,
        instance_id: Optional[int] = None,
    ) -> OperationsReport:
        """生成 Redis 月报（周报内容 + 容量趋势 + 优化建议）"""
        data = await self._collect_redis_data(connector)

        today = datetime.now()
        first_day = today.replace(day=1)
        # 该月最后一天
        next_month = first_day.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        period_start = first_day.strftime("%Y-%m-%d")
        period_end = last_day.strftime("%Y-%m-%d")

        sections: list[ReportSection] = []
        # 周报内容（含日报内容）
        sections.append(self._build_overview_section(data))
        sections.append(self._build_memory_analysis_section(data))
        sections.append(self._build_slowlog_top10_section(data))
        sections.append(self._build_persistence_section(data))

        health_score, breakdown = self._calculate_health_score(data)
        sections.append(self._build_health_score_section(health_score, breakdown))

        suggestions = self._build_optimization_suggestions(data)
        sections.append(self._build_suggestions_section(suggestions))

        sections.append(await self._build_daily_trend_section(db, instance_id))

        # 月报追加：容量趋势
        sections.append(await self._build_capacity_trend_section(db, instance_id))

        # 月报追加：基于趋势的优化建议
        monthly_suggestions = self._build_monthly_suggestions(data)
        sections.append(self._build_monthly_suggestions_section(monthly_suggestions))

        summary = self._generate_summary("本月", data, health_score)

        return OperationsReport(
            id=str(uuid.uuid4()),
            report_type="redis_monthly",
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now().isoformat(),
            instance_id=instance_id,
            instance_name=await self._resolve_instance_name(db, instance_id),
            sections=sections,
            summary=summary,
            health_score=health_score,
        )

    # ── 辅助 ────────────────────────────────────────────

    def _build_monthly_suggestions(self, data: dict) -> list[str]:
        """基于月度视角的优化建议"""
        suggestions: list[str] = []
        memory = data.get("memory", {})
        stats = data.get("stats", {})

        used_memory_peak = self._to_int(memory.get("used_memory_peak"), 0)
        maxmemory = self._to_int(memory.get("maxmemory"), 0)

        # 容量规划建议
        if maxmemory > 0 and used_memory_peak > 0:
            peak_usage = used_memory_peak / maxmemory * 100
            if peak_usage > 70:
                suggestions.append(
                    f"内存峰值使用率达 {peak_usage:.2f}%，建议提前规划容量扩容或清理冷数据"
                )

        # 同步建议
        sync_full = self._to_int(stats.get("sync_full"), 0)
        if sync_full > 0:
            suggestions.append(
                f"存在 {sync_full} 次全量同步，建议排查主从网络抖动与复制缓冲区配置"
            )

        evicted_keys = self._to_int(stats.get("evicted_keys"), 0)
        if evicted_keys > 1000:
            suggestions.append(
                f"本月累计淘汰 {evicted_keys} 个键，建议评估内存容量与业务缓存策略"
            )

        if not suggestions:
            suggestions.append("本月容量与同步指标平稳，无特别优化建议")

        return suggestions

    def _build_monthly_suggestions_section(
        self, suggestions: list[str]
    ) -> ReportSection:
        return ReportSection(
            title="月度优化建议",
            content_type="list",
            data=suggestions or ["暂无数据"],
        )

    async def _resolve_instance_name(
        self, db: DatabaseManager, instance_id: Optional[int]
    ) -> Optional[str]:
        """从 instances 表查询实例名称"""
        if instance_id is None:
            return None
        try:
            return await self._rg._get_instance_name(db, instance_id)
        except Exception:
            return None

    def _generate_summary(
        self, period_label: str, data: dict, health_score: float
    ) -> str:
        """生成报表摘要"""
        memory = data.get("memory", {})
        clients = data.get("clients", {})
        stats = data.get("stats", {})

        parts = [
            f"{period_label}内存使用 {memory.get('used_memory_human', '0B')}",
            f"连接数 {self._to_int(clients.get('connected_clients'), 0)}",
            f"QPS {self._to_int(stats.get('instantaneous_ops_per_sec'), 0)}",
            f"慢查询 {data.get('slowlog_len', 0)} 条",
            f"健康评分 {health_score:.1f}",
        ]

        if health_score >= 90:
            parts.append("Redis 运行良好")
        elif health_score >= 70:
            parts.append("Redis 存在少量问题，建议关注")
        elif health_score >= 50:
            parts.append("Redis 存在较多问题，需要排查")
        else:
            parts.append("Redis 健康状况较差，需要立即处理")

        return "，".join(parts)

    @staticmethod
    def _to_int(val, default: int = 0) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _to_float(val, default: float = 0.0) -> float:
        try:
            return float(val)
        except (ValueError, TypeError):
            return default


# ── 模块级生成器实例 ────────────────────────────────────

_redis_generator: RedisReportGenerator | None = None


def _get_redis_generator() -> RedisReportGenerator:
    global _redis_generator
    if _redis_generator is None:
        _redis_generator = RedisReportGenerator()
    return _redis_generator


# ── API 端点 ────────────────────────────────────────────


@router.post("/reports/generate")
async def generate_redis_report(
    report_type: str = Query(..., description="报表类型: daily/weekly/monthly"),
    instance_id: Optional[int] = Query(None, description="Redis 实例 ID，为空时使用默认实例"),
):
    """生成 Redis 运维报表"""
    valid_types = {"daily", "weekly", "monthly"}
    if report_type not in valid_types:
        raise HTTPException(
            status_code=400, detail=f"无效的报表类型，可选: {valid_types}"
        )

    connector = get_redis_connector(instance_id)
    if not connector:
        raise HTTPException(status_code=400, detail="无法创建 Redis 连接器")

    db = get_db()
    generator = _get_redis_generator()

    try:
        if report_type == "daily":
            report = await generator.generate_daily_report(
                db, connector, instance_id=instance_id
            )
        elif report_type == "weekly":
            report = await generator.generate_weekly_report(
                db, connector, instance_id=instance_id
            )
        else:  # monthly
            report = await generator.generate_monthly_report(
                db, connector, instance_id=instance_id
            )

        # 保存报表到 operations_reports 表（复用现有表，report_type 带 redis_ 前缀）
        await get_generator().save_report(db, report)

        return _report_to_dict(report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("生成 Redis 报表失败: %s", e)
        raise HTTPException(
            status_code=500, detail=f"生成报表失败: {str(e)[:200]}"
        )
    finally:
        await connector.close()


@router.get("/reports")
async def list_redis_reports(
    report_type: Optional[str] = Query(
        None, description="报表类型过滤: daily/weekly/monthly（自动加 redis_ 前缀）"
    ),
    instance_id: Optional[int] = Query(None, description="实例 ID 过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
):
    """列出已生成的 Redis 报表（仅摘要信息）"""
    db = get_db()
    rg = get_generator()

    # 自动加 redis_ 前缀
    prefixed_type = f"redis_{report_type}" if report_type else None

    try:
        reports = await rg.list_reports(
            db, report_type=prefixed_type, instance_id=instance_id, limit=limit
        )
        return {"items": reports, "total": len(reports)}
    except Exception as e:
        logger.error("查询 Redis 报表列表失败: %s", e)
        raise HTTPException(
            status_code=500, detail=f"查询报表列表失败: {str(e)[:200]}"
        )


@router.get("/reports/{report_id}")
async def get_redis_report(report_id: str):
    """获取指定 ID 的 Redis 报表详情"""
    db = get_db()
    rg = get_generator()

    try:
        report = await rg.get_report(db, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="报表不存在")

        return _report_to_dict(report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询 Redis 报表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"查询报表失败: {str(e)[:200]}")


@router.delete("/reports/{report_id}")
async def delete_redis_report(report_id: str):
    """删除指定 ID 的 Redis 报表"""
    db = get_db()
    rg = get_generator()

    try:
        success = await rg.delete_report(db, report_id)
        if not success:
            raise HTTPException(status_code=404, detail="报表不存在")

        return {"message": "报表删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除 Redis 报表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"删除报表失败: {str(e)[:200]}")
