"""性能基线与异常检测 API"""
from fastapi import APIRouter, Query
from typing import Optional

from src.analyzer.baseline import BaselineManager
from src.web.api.deps import get_db as _get_db

router = APIRouter(prefix="/api/baseline", tags=["baseline"])


# ── 数据库与引擎实例 ──────────────────────────────────────

_manager: BaselineManager | None = None


def _get_manager() -> BaselineManager:
    """获取基线管理器实例"""
    global _manager
    if _manager is None:
        _manager = BaselineManager()
    return _manager


# ── API 端点 ────────────────────────────────────────────────


@router.post("/build")
async def build_baselines(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    days: int = Query(30, ge=1, le=365, description="回溯天数"),
):
    """从历史数据构建/重建基线"""
    db = _get_db()
    manager = _get_manager()

    try:
        baselines = await manager.build_baselines(db, instance_id=instance_id, days=days)
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
        return {"message": f"基线构建失败: {str(e)[:200]}", "count": 0, "baselines": []}


@router.get("/anomalies")
async def detect_anomalies(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    sensitivity: float = Query(2.0, ge=0.5, le=10.0, description="灵敏度阈值（标准差倍数）"),
):
    """检测当前指标异常"""
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
        return {"count": 0, "anomalies": [], "message": f"异常检测失败: {str(e)[:200]}"}


@router.get("/list")
async def list_baselines(
    metric_name: Optional[str] = Query(None, description="指标名称过滤"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """获取已存储的基线列表"""
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
        return {"count": 0, "baselines": [], "message": f"获取基线失败: {str(e)[:200]}"}


@router.get("/forecast/{metric_name}")
async def get_metric_forecast(
    metric_name: str,
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    hours: int = Query(24, ge=1, le=168, description="预测小时数"),
):
    """获取指标预测数据"""
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


@router.get("/overview")
async def get_baseline_overview(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """获取基线概览仪表盘数据"""
    db = _get_db()
    manager = _get_manager()

    try:
        # 获取所有基线
        baselines = await manager.get_baselines(db, instance_id=instance_id)

        # 获取当前异常
        anomalies = await manager.detect_anomalies(db, instance_id=instance_id)

        # 提取已监控的指标名称列表（去重）
        metrics_monitored = sorted(set(b.metric_name for b in baselines))

        # 最近 5 条异常
        recent_anomalies = [
            {
                "id": a.id,
                "metric_name": a.metric_name,
                "current_value": a.current_value,
                "baseline_mean": a.baseline_mean,
                "deviation": a.deviation,
                "severity": a.severity,
                "detected_at": a.detected_at,
                "description": a.description,
            }
            for a in anomalies[:5]
        ]

        # 构建各指标状态摘要
        # 将异常按 metric_name 索引，取最严重的
        anomaly_by_metric: dict[str, dict] = {}
        for a in anomalies:
            if a.metric_name not in anomaly_by_metric:
                anomaly_by_metric[a.metric_name] = {
                    "deviation": a.deviation,
                    "severity": a.severity,
                    "current_value": a.current_value,
                    "baseline_mean": a.baseline_mean,
                }
            else:
                # 保留更严重的
                severity_order = {"critical": 3, "high": 2, "medium": 1}
                existing = anomaly_by_metric[a.metric_name]
                if severity_order.get(a.severity, 0) > severity_order.get(
                    existing["severity"], 0
                ):
                    anomaly_by_metric[a.metric_name] = {
                        "deviation": a.deviation,
                        "severity": a.severity,
                        "current_value": a.current_value,
                        "baseline_mean": a.baseline_mean,
                    }

        # 获取每个指标的当前值
        conn = await db._get_conn()
        current_values: dict[str, float] = {}

        conditions = []
        params: list = []
        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"""SELECT metric_name, metric_value
                FROM monitor_metrics
                WHERE {where_clause}
                ORDER BY collected_at DESC""",
            params,
        )
        all_metric_rows = await cursor.fetchall()

        for row in all_metric_rows:
            mname = row["metric_name"]
            if mname not in current_values:
                current_values[mname] = row["metric_value"]

        # 获取每个指标的基线均值（优先 hourly 当前小时）
        from datetime import datetime

        now = datetime.now()
        current_hour_key = f"hour:{now.hour}"

        baseline_means: dict[str, float] = {}
        for b in baselines:
            if b.metric_name not in baseline_means:
                # 优先使用当前小时的 hourly 基线
                if b.period == "hourly" and b.period_key == current_hour_key:
                    baseline_means[b.metric_name] = b.mean

        # 对没有 hourly 基线的指标，使用任意周期的均值
        for b in baselines:
            if b.metric_name not in baseline_means:
                baseline_means[b.metric_name] = b.mean

        # 构建指标状态列表
        metric_status = []
        for metric_name in metrics_monitored:
            current = current_values.get(metric_name)
            baseline_mean = baseline_means.get(metric_name)

            if metric_name in anomaly_by_metric:
                anomaly_info = anomaly_by_metric[metric_name]
                severity = anomaly_info["severity"]
                status = "critical" if severity == "critical" else "warning"
                deviation = anomaly_info["deviation"]
            else:
                status = "normal"
                # 计算偏离度
                if current is not None and baseline_mean is not None and baseline_mean != 0:
                    # 查找对应基线的 std
                    baseline_std = None
                    for b in baselines:
                        if b.metric_name == metric_name and b.period == "hourly" and b.period_key == current_hour_key:
                            baseline_std = b.std
                            break
                    if baseline_std is None:
                        for b in baselines:
                            if b.metric_name == metric_name:
                                baseline_std = b.std
                                break
                    if baseline_std and baseline_std > 0:
                        deviation = (current - baseline_mean) / baseline_std
                    else:
                        deviation = 0.0
                else:
                    deviation = 0.0

            metric_status.append({
                "metric_name": metric_name,
                "current": current,
                "baseline_mean": baseline_mean,
                "deviation": round(deviation, 4) if deviation is not None else None,
                "status": status,
            })

        return {
            "baselines_count": len(baselines),
            "anomalies_count": len(anomalies),
            "metrics_monitored": metrics_monitored,
            "recent_anomalies": recent_anomalies,
            "metric_status": metric_status,
        }
    except Exception as e:
        return {
            "baselines_count": 0,
            "anomalies_count": 0,
            "metrics_monitored": [],
            "recent_anomalies": [],
            "metric_status": [],
            "message": f"获取概览失败: {str(e)[:200]}",
        }
