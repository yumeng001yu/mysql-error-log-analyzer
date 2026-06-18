"""Redis 性能基线 API

复用 BaselineManager 架构，数据来源为 Redis 实时指标（存入 monitor_metrics 表）。

端点:
- POST /api/redis/baseline/build     — 从历史指标构建基线
- GET  /api/redis/baseline/list      — 列出基线（支持 instance_id / metric_name 过滤）
- GET  /api/redis/baseline/anomalies — 检测异常（对比当前指标与基线）
- GET  /api/redis/baseline/forecast  — 预测未来指标
- POST /api/redis/baseline/collect   — 采集当前 Redis 指标并存入 monitor_metrics
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from src.analyzer.baseline import BaselineManager
from src.collector.redis_connector import RedisConnector
from src.web.api.deps import get_db as _get_db
from src.web.api.redis_monitor import _get_connector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/redis", tags=["Redis 性能基线"])


# ── 数据库与引擎实例 ──────────────────────────────────────

_manager: BaselineManager | None = None


def _get_manager() -> BaselineManager:
    """获取基线管理器实例"""
    global _manager
    if _manager is None:
        _manager = BaselineManager()
    return _manager


# ── 辅助函数 ────────────────────────────────────────────────


async def _resolve_redis_instance_id(
    db: DatabaseManager, instance_id: Optional[int] = None
) -> Optional[int]:
    """解析 Redis 实例 ID，未提供时从数据库查找最新的 Redis 实例"""
    if instance_id is not None:
        return instance_id
    try:
        conn = await db._get_conn()
        cursor = await conn.execute(
            "SELECT id FROM instances WHERE db_type = 'redis' ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return row["id"] if row else None
    except Exception as e:
        logger.warning("查找 Redis 实例 ID 失败: %s", e)
        return None


def _extract_redis_metrics(info: dict) -> dict:
    """从 Redis INFO 字典中提取基线监控所需的指标

    Args:
        info: RedisConnector.get_info() 返回的原始 INFO 字典

    Returns:
        指标名 -> 指标值 的字典
    """

    def _int(key, default=0):
        try:
            return int(info.get(key, default))
        except (ValueError, TypeError):
            return default

    def _float(key, default=0.0):
        try:
            return float(info.get(key, default))
        except (ValueError, TypeError):
            return default

    # 缓存命中率: keyspace_hits / (keyspace_hits + keyspace_misses) * 100
    keyspace_hits = _int("keyspace_hits")
    keyspace_misses = _int("keyspace_misses")
    total_accesses = keyspace_hits + keyspace_misses
    hit_rate = (
        round(keyspace_hits / total_accesses * 100, 2) if total_accesses > 0 else 100.0
    )

    return {
        "used_memory": float(_int("used_memory")),
        "connected_clients": float(_int("connected_clients")),
        "qps": float(_int("instantaneous_ops_per_sec")),
        "hit_rate": hit_rate,
        "fragmentation_ratio": _float("mem_fragmentation_ratio"),
        "evicted_keys": float(_int("evicted_keys")),
        "expired_keys": float(_int("expired_keys")),
    }


# ── API 端点 ────────────────────────────────────────────────


@router.post("/baseline/build")
async def build_redis_baselines(
    instance_id: Optional[int] = Query(None, description="Redis 实例 ID"),
    days: int = Query(30, ge=1, le=365, description="回溯天数"),
):
    """从 monitor_metrics 表中的 Redis 历史指标构建基线"""
    db = _get_db()
    manager = _get_manager()

    try:
        baselines = await manager.build_baselines(
            db, instance_id=instance_id, days=days
        )
        return {
            "message": f"基线构建完成，共生成 {len(baselines)} 条基线",
            "count": len(baselines),
            "baselines": [
                {
                    "metric_name": b.metric_name,
                    "period": b.period,
                    "period_key": b.period_key,
                    "mean": b.mean,
                    "std": b.std,
                    "min_val": b.min_val,
                    "max_val": b.max_val,
                    "p50": b.p50,
                    "p95": b.p95,
                    "p99": b.p99,
                    "sample_count": b.sample_count,
                    "last_updated": b.last_updated,
                }
                for b in baselines
            ],
        }
    except Exception as e:
        return {
            "message": f"基线构建失败: {str(e)[:200]}",
            "count": 0,
            "baselines": [],
        }


@router.get("/baseline/list")
async def list_redis_baselines(
    instance_id: Optional[int] = Query(None, description="实例 ID 过滤"),
    metric_name: Optional[str] = Query(None, description="指标名称过滤"),
):
    """获取已存储的 Redis 基线列表"""
    db = _get_db()
    manager = _get_manager()

    try:
        baselines = await manager.get_baselines(
            db, metric_name=metric_name, instance_id=instance_id
        )
        return {
            "count": len(baselines),
            "baselines": [
                {
                    "metric_name": b.metric_name,
                    "period": b.period,
                    "period_key": b.period_key,
                    "mean": b.mean,
                    "std": b.std,
                    "min_val": b.min_val,
                    "max_val": b.max_val,
                    "p50": b.p50,
                    "p95": b.p95,
                    "p99": b.p99,
                    "sample_count": b.sample_count,
                    "last_updated": b.last_updated,
                }
                for b in baselines
            ],
        }
    except Exception as e:
        return {
            "count": 0,
            "baselines": [],
            "message": f"获取基线失败: {str(e)[:200]}",
        }


@router.get("/baseline/anomalies")
async def detect_redis_anomalies(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    sensitivity: float = Query(
        2.0, ge=0.5, le=10.0, description="灵敏度阈值（标准差倍数）"
    ),
):
    """对比当前 Redis 指标与基线，检测异常"""
    db = _get_db()
    manager = _get_manager()

    try:
        anomalies = await manager.detect_anomalies(
            db, instance_id=instance_id, sensitivity=sensitivity
        )
        return {
            "count": len(anomalies),
            "anomalies": [
                {
                    "id": a.id,
                    "metric_name": a.metric_name,
                    "current_value": a.current_value,
                    "baseline_mean": a.baseline_mean,
                    "baseline_std": a.baseline_std,
                    "deviation": a.deviation,
                    "direction": a.direction,
                    "severity": a.severity,
                    "detected_at": a.detected_at,
                    "description": a.description,
                }
                for a in anomalies
            ],
        }
    except Exception as e:
        return {
            "count": 0,
            "anomalies": [],
            "message": f"异常检测失败: {str(e)[:200]}",
        }


@router.get("/baseline/forecast")
async def forecast_redis_metric(
    metric_name: str = Query(..., description="指标名称"),
    hours: int = Query(24, ge=1, le=168, description="预测小时数"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """基于历史基线预测未来 N 小时的 Redis 指标值"""
    db = _get_db()
    manager = _get_manager()

    try:
        forecast = await manager.get_metric_forecast(
            db, metric_name=metric_name, instance_id=instance_id, hours=hours
        )
        return {
            "metric_name": metric_name,
            "hours": hours,
            "forecast": forecast,
        }
    except Exception as e:
        return {
            "metric_name": metric_name,
            "hours": hours,
            "forecast": [],
            "message": f"预测失败: {str(e)[:200]}",
        }


@router.post("/baseline/collect")
async def collect_redis_metrics(
    instance_id: Optional[int] = Query(
        None, description="Redis 实例 ID，未提供时使用最新的 Redis 实例"
    ),
):
    """采集当前 Redis 指标并存入 monitor_metrics 表（供基线构建使用）"""
    db = _get_db()

    # 解析实例 ID
    resolved_id = await _resolve_redis_instance_id(db, instance_id)
    if resolved_id is None:
        return {
            "error": "无法确定 Redis 实例 ID，请提供 instance_id 参数或先添加 Redis 实例"
        }

    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        info = await connector.get_info()
        if not info:
            return {"error": "无法获取 Redis INFO 数据"}

        # 提取指标
        metrics = _extract_redis_metrics(info)

        # 存入 monitor_metrics 表
        now = datetime.now().isoformat()
        for metric_name, metric_value in metrics.items():
            await db.insert_monitor_metric(
                resolved_id, metric_name, metric_value, now
            )

        return {
            "message": f"采集完成，共 {len(metrics)} 个指标",
            "instance_id": resolved_id,
            "collected_at": now,
            "metrics": metrics,
        }
    except Exception as e:
        return {"error": f"采集失败: {str(e)[:200]}"}
    finally:
        await connector.close()
