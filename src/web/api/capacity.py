"""容量规划 API

端点:
- GET /api/capacity/forecast        — 容量预测（基于历史数据线性回归）
- GET /api/capacity/summary         — 容量概览（关键资源使用情况）
- GET /api/capacity/threshold-check — 阈值检查（当前指标是否接近阈值）
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from src.collector.redis_connector import RedisConnector
from src.web.api.deps import get_db as _get_db
from src.web.api.deps import get_mysql_connector as _get_mysql_connector
from src.web.api.deps import get_redis_connector as _get_redis_connector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/capacity", tags=["容量规划"])


# ── 辅助函数 ────────────────────────────────────────────────

def _status_from_percent(percent: Optional[float]) -> str:
    """根据使用率返回状态: normal/warning/critical"""
    if percent is None:
        return "normal"
    if percent >= 90:
        return "critical"
    if percent >= 80:
        return "warning"
    return "normal"


def _frag_status(ratio: float) -> str:
    """根据碎片率返回状态"""
    if ratio > 2.0:
        return "critical"
    if ratio > 1.5:
        return "warning"
    return "normal"


def _linear_regression(x: list[float], y: list[float]) -> tuple[float, float]:
    """简单线性回归（最小二乘法），返回 (slope, intercept)

    y = slope * x + intercept
    """
    n = len(x)
    if n < 2:
        return 0.0, float(y[0]) if y else 0.0

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        # 所有 x 相同，无法拟合斜率
        return 0.0, float(sum_y / n)

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    return float(slope), float(intercept)


# ── 容量预测 ────────────────────────────────────────────────

@router.get("/forecast")
async def capacity_forecast(
    db_type: str = Query("redis", description="数据库类型: mysql/redis"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    metric_name: str = Query("memory_usage_percent", description="指标名称"),
    days: int = Query(30, ge=1, le=365, description="预测未来 N 天"),
):
    """容量预测：基于历史监控数据使用线性回归预测未来增长趋势

    1. 从 monitor_metrics 表查询历史数据（最近 N 天）
    2. 使用线性回归预测未来增长趋势
    3. 计算预计达到阈值的时间点
    4. 返回：当前值、增长率（每天）、预计达到阈值的天数、预测数据点列表
    """
    db = _get_db()
    instance_id_val = instance_id or 0
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    try:
        rows = await db.query_monitor_metrics(
            instance_id_val,
            metric_name,
            start_time.isoformat(),
            end_time.isoformat(),
            limit=10000,
        )
    except Exception as e:
        logger.warning("查询监控指标历史失败: %s", e)
        rows = []

    threshold = 80.0

    # 历史数据不足
    if not rows or len(rows) < 2:
        current_value = None
        if rows:
            try:
                current_value = round(float(rows[-1].get("metric_value", 0)), 4)
            except (ValueError, TypeError):
                current_value = None
        return {
            "metric_name": metric_name,
            "db_type": db_type,
            "instance_id": instance_id_val,
            "current_value": current_value,
            "growth_rate_per_day": 0.0,
            "threshold": threshold,
            "days_to_threshold": None,
            "forecast_points": [],
            "history_points": len(rows),
            "message": "历史数据不足，无法预测",
        }

    # 解析时间序列
    points: list[tuple[datetime, float]] = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(row["collected_at"])
            val = float(row["metric_value"])
            points.append((ts, val))
        except (ValueError, TypeError):
            continue

    if len(points) < 2:
        return {
            "metric_name": metric_name,
            "db_type": db_type,
            "instance_id": instance_id_val,
            "current_value": round(points[-1][1], 4) if points else None,
            "growth_rate_per_day": 0.0,
            "threshold": threshold,
            "days_to_threshold": None,
            "forecast_points": [],
            "history_points": len(points),
            "message": "历史数据不足，无法预测",
        }

    # 以第一个时间点为基准，转换为天数
    base_time = points[0][0]
    x = [(p[0] - base_time).total_seconds() / 86400.0 for p in points]
    y = [p[1] for p in points]

    slope, intercept = _linear_regression(x, y)
    current_value = y[-1]
    growth_rate = slope  # 每天增长量

    # 计算预计达到阈值的天数
    days_to_threshold = None
    if growth_rate > 0:
        remaining = (threshold - current_value) / growth_rate
        days_to_threshold = round(max(0.0, remaining), 1)

    # 生成预测数据点（未来 N 天，每天一个点）
    forecast_points = []
    last_x = x[-1]
    for i in range(1, days + 1):
        future_x = last_x + i
        predicted = intercept + slope * future_x
        forecast_points.append({
            "day_offset": i,
            "predicted_value": round(predicted, 4),
        })

    return {
        "metric_name": metric_name,
        "db_type": db_type,
        "instance_id": instance_id_val,
        "current_value": round(current_value, 4),
        "growth_rate_per_day": round(growth_rate, 6),
        "threshold": threshold,
        "days_to_threshold": days_to_threshold,
        "forecast_points": forecast_points,
        "history_points": len(points),
    }


# ── 容量概览 ────────────────────────────────────────────────

@router.get("/summary")
async def capacity_summary(
    db_type: str = Query("redis", description="数据库类型: mysql/redis"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """容量概览：返回关键资源使用情况

    每项包含: current, max, usage_percent, status(normal/warning/critical)
    """
    if db_type == "redis":
        return await _redis_capacity_summary(instance_id)
    return await _mysql_capacity_summary(instance_id)


async def _redis_capacity_summary(instance_id: Optional[int]) -> dict:
    """Redis 容量概览：内存使用量/使用率、连接数/使用率、Key 总数、碎片率"""
    connector = _get_redis_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        metrics = await connector.get_metrics()
        if not metrics:
            return {"connected": False, "error": "无法获取 Redis 指标"}

        memory = metrics.get("memory", {})
        clients = metrics.get("clients", {})

        used_memory = memory.get("used_memory", 0)
        maxmemory = memory.get("maxmemory", 0)
        mem_usage_percent = round(used_memory / maxmemory * 100, 2) if maxmemory > 0 else None

        connected = clients.get("connected", 0)
        maxclients = clients.get("maxclients", 0)
        conn_usage_percent = round(connected / maxclients * 100, 2) if maxclients > 0 else None

        frag_ratio = memory.get("fragmentation_ratio", 0) or 0

        # Key 总数
        try:
            total_keys = await connector.get_dbsize()
        except Exception:
            total_keys = 0

        return {
            "connected": True,
            "db_type": "redis",
            "memory": {
                "current": used_memory,
                "max": maxmemory,
                "usage_percent": mem_usage_percent,
                "status": _status_from_percent(mem_usage_percent),
            },
            "connections": {
                "current": connected,
                "max": maxclients,
                "usage_percent": conn_usage_percent,
                "status": _status_from_percent(conn_usage_percent),
            },
            "keys": {
                "current": total_keys,
                "max": None,
                "usage_percent": None,
                "status": "normal",
            },
            "fragmentation": {
                "current": round(frag_ratio, 2),
                "max": None,
                "usage_percent": None,
                "status": _frag_status(frag_ratio),
            },
        }
    except Exception as e:
        return {"connected": False, "error": str(e)[:200]}
    finally:
        await connector.close()


async def _mysql_capacity_summary(instance_id: Optional[int]) -> dict:
    """MySQL 容量概览：磁盘使用、连接数、表数量、数据量"""
    connector = _get_mysql_connector(instance_id)
    if not connector:
        return {"error": "无法创建 MySQL 连接器"}

    try:
        status = await connector.get_global_status()
        if not status:
            return {"connected": False, "error": "无法获取 MySQL 状态"}

        # 连接数
        threads_connected = status.get("Threads_connected", 0)
        max_allowed = 0
        try:
            variables = await connector.get_variables(like_pattern="max_connections")
            max_allowed = int(variables.get("max_connections", 0))
        except Exception:
            pass

        conn_usage_percent = (
            round(threads_connected / max_allowed * 100, 2) if max_allowed > 0 else None
        )

        # 表数量与数据量（近似磁盘使用）
        table_count = 0
        data_size = 0
        try:
            rows = await connector._execute_query(
                "SELECT COUNT(*) AS cnt, COALESCE(SUM(DATA_LENGTH), 0) AS data_size "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA NOT IN "
                "('information_schema','mysql','performance_schema','sys')"
            )
            if rows:
                table_count = int(rows[0].get("cnt", 0))
                data_size = int(rows[0].get("data_size", 0))
        except Exception as e:
            logger.warning("查询 MySQL 表统计失败: %s", e)

        return {
            "connected": True,
            "db_type": "mysql",
            "disk": {
                "current": data_size,
                "max": None,
                "usage_percent": None,
                "status": "normal",
            },
            "connections": {
                "current": threads_connected,
                "max": max_allowed,
                "usage_percent": conn_usage_percent,
                "status": _status_from_percent(conn_usage_percent),
            },
            "tables": {
                "current": table_count,
                "max": None,
                "usage_percent": None,
                "status": "normal",
            },
            "data_size": {
                "current": data_size,
                "max": None,
                "usage_percent": None,
                "status": "normal",
            },
        }
    except Exception as e:
        return {"connected": False, "error": str(e)[:200]}
    finally:
        await connector.close()


# ── 阈值检查 ────────────────────────────────────────────────

@router.get("/threshold-check")
async def threshold_check(
    db_type: str = Query("redis", description="数据库类型: mysql/redis"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """阈值检查：检查当前指标是否接近阈值

    1. 检查内存使用率（>80% warning, >90% critical）
    2. 检查连接使用率（>80% warning, >90% critical）
    3. 检查碎片率（>1.5 warning, >2.0 critical）
    """
    summary = await capacity_summary(db_type=db_type, instance_id=instance_id)
    if "error" in summary or not summary.get("connected"):
        return {
            "db_type": db_type,
            "instance_id": instance_id,
            "overall_status": "unknown",
            "checks": [],
            "error": summary.get("error"),
        }

    checks: list[dict] = []

    # 内存使用率检查（Redis 有明确内存上限）
    if db_type == "redis":
        memory = summary.get("memory", {})
        mem_percent = memory.get("usage_percent")
        checks.append({
            "name": "memory_usage",
            "current": mem_percent,
            "threshold_warning": 80,
            "threshold_critical": 90,
            "status": _status_from_percent(mem_percent),
            "message": _threshold_message("内存使用率", mem_percent, 80, 90, unit="%"),
        })

        # 碎片率检查（仅 Redis）
        frag = summary.get("fragmentation", {})
        frag_ratio = frag.get("current", 0) or 0
        checks.append({
            "name": "fragmentation_ratio",
            "current": frag_ratio,
            "threshold_warning": 1.5,
            "threshold_critical": 2.0,
            "status": _frag_status(frag_ratio),
            "message": _threshold_message("碎片率", frag_ratio, 1.5, 2.0, unit=""),
        })

    # 连接使用率检查（MySQL 和 Redis 都有）
    connections = summary.get("connections", {})
    conn_percent = connections.get("usage_percent")
    checks.append({
        "name": "connection_usage",
        "current": conn_percent,
        "threshold_warning": 80,
        "threshold_critical": 90,
        "status": _status_from_percent(conn_percent),
        "message": _threshold_message("连接使用率", conn_percent, 80, 90, unit="%"),
    })

    # 汇总状态
    statuses = [c["status"] for c in checks]
    if "critical" in statuses:
        overall = "critical"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "normal"

    return {
        "db_type": db_type,
        "instance_id": instance_id,
        "overall_status": overall,
        "checks": checks,
    }


def _threshold_message(name: str, value, warn, crit, unit: str = "") -> str:
    """生成阈值检查消息"""
    if value is None:
        return f"{name}: 无法计算"
    if value >= crit:
        return f"{name} {value}{unit} 超过临界阈值 {crit}{unit}，需要立即处理"
    if value >= warn:
        return f"{name} {value}{unit} 超过警告阈值 {warn}{unit}，建议关注"
    return f"{name} {value}{unit} 正常"
