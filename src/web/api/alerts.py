"""智能告警引擎 API"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from src.storage.database import DatabaseManager
from src.web.api.alert_engine import AlertEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── 数据库与引擎实例 ──────────────────────────────────────

_db: DatabaseManager | None = None
_engine: AlertEngine | None = None


def _get_db() -> DatabaseManager:
    """获取数据库管理器实例"""
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db


def _get_engine() -> AlertEngine:
    """获取告警引擎实例"""
    global _engine
    if _engine is None:
        _engine = AlertEngine(_get_db())
    return _engine


# ── 告警规则管理 ──────────────────────────────────────────


@router.get("/rules")
async def list_rules():
    """获取所有告警规则"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    cursor = await conn.execute(
        "SELECT * FROM alert_rules ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    rules = []
    for row in rows:
        item = dict(row)
        # 解析 channels JSON
        try:
            item["channels"] = json.loads(item.get("channels", "[]"))
        except (json.JSONDecodeError, TypeError):
            item["channels"] = []
        rules.append(item)

    return {"items": rules, "total": len(rules)}


@router.post("/rules")
async def create_rule(
    name: str = Body(..., description="规则名称"),
    description: str = Body("", description="规则描述"),
    rule_type: str = Body("threshold", description="规则类型: threshold/trend/pattern/anomaly"),
    metric: str = Body("error_count", description="监控指标"),
    condition: str = Body("gt", description="比较运算符: gt/gte/lt/lte/eq/ne/increase_rate"),
    threshold: float = Body(..., description="阈值"),
    window: int = Body(5, description="时间窗口（分钟）"),
    level: str = Body("warning", description="告警级别: critical/warning/info"),
    channels: list[int] = Body([], description="通知渠道 ID 列表"),
    cooldown: int = Body(300, description="冷却时间（秒）"),
    enabled: bool = Body(True, description="是否启用"),
):
    """创建告警规则"""
    # 参数校验
    valid_rule_types = {"threshold", "trend", "pattern", "anomaly"}
    if rule_type not in valid_rule_types:
        raise HTTPException(status_code=400, detail=f"无效的规则类型，可选: {valid_rule_types}")

    valid_conditions = {"gt", "gte", "lt", "lte", "eq", "ne", "increase_rate"}
    if condition not in valid_conditions:
        raise HTTPException(status_code=400, detail=f"无效的条件运算符，可选: {valid_conditions}")

    valid_levels = {"critical", "warning", "info"}
    if level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"无效的告警级别，可选: {valid_levels}")

    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()
    now = datetime.now().isoformat()

    await conn.execute(
        """INSERT INTO alert_rules
           (name, description, enabled, rule_type, metric, condition,
            threshold, window, level, channels, cooldown, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            description,
            int(enabled),
            rule_type,
            metric,
            condition,
            threshold,
            window,
            level,
            json.dumps(channels),
            cooldown,
            now,
            now,
        ),
    )
    await conn.commit()

    # 获取新创建的规则
    cursor = await conn.execute(
        "SELECT * FROM alert_rules WHERE id = last_insert_rowid()"
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="创建规则失败")

    item = dict(row)
    try:
        item["channels"] = json.loads(item.get("channels", "[]"))
    except (json.JSONDecodeError, TypeError):
        item["channels"] = []

    return {"message": "规则创建成功", "rule": item}


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    name: Optional[str] = Body(None, description="规则名称"),
    description: Optional[str] = Body(None, description="规则描述"),
    rule_type: Optional[str] = Body(None, description="规则类型"),
    metric: Optional[str] = Body(None, description="监控指标"),
    condition: Optional[str] = Body(None, description="比较运算符"),
    threshold: Optional[float] = Body(None, description="阈值"),
    window: Optional[int] = Body(None, description="时间窗口（分钟）"),
    level: Optional[str] = Body(None, description="告警级别"),
    channels: Optional[list[int]] = Body(None, description="通知渠道 ID 列表"),
    cooldown: Optional[int] = Body(None, description="冷却时间（秒）"),
    enabled: Optional[bool] = Body(None, description="是否启用"),
):
    """更新告警规则"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    # 检查规则是否存在
    cursor = await conn.execute(
        "SELECT * FROM alert_rules WHERE id = ?", (rule_id,)
    )
    existing = await cursor.fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="规则不存在")

    # 构建更新字段
    updates = []
    params = []

    field_map = {
        "name": name,
        "description": description,
        "rule_type": rule_type,
        "metric": metric,
        "condition": condition,
        "threshold": threshold,
        "window": window,
        "level": level,
        "cooldown": cooldown,
    }

    for field, value in field_map.items():
        if value is not None:
            updates.append(f"{field} = ?")
            params.append(value)

    if channels is not None:
        updates.append("channels = ?")
        params.append(json.dumps(channels))

    if enabled is not None:
        updates.append("enabled = ?")
        params.append(int(enabled))

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供更新字段")

    now = datetime.now().isoformat()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(rule_id)

    await conn.execute(
        f"UPDATE alert_rules SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await conn.commit()

    # 返回更新后的规则
    cursor = await conn.execute(
        "SELECT * FROM alert_rules WHERE id = ?", (rule_id,)
    )
    row = await cursor.fetchone()
    item = dict(row)
    try:
        item["channels"] = json.loads(item.get("channels", "[]"))
    except (json.JSONDecodeError, TypeError):
        item["channels"] = []

    return {"message": "规则更新成功", "rule": item}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    """删除告警规则"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    cursor = await conn.execute(
        "SELECT id FROM alert_rules WHERE id = ?", (rule_id,)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="规则不存在")

    await conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    await conn.commit()

    return {"message": "规则删除成功"}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: int):
    """启用/禁用告警规则"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    cursor = await conn.execute(
        "SELECT enabled FROM alert_rules WHERE id = ?", (rule_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="规则不存在")

    new_enabled = 0 if row["enabled"] else 1
    now = datetime.now().isoformat()

    await conn.execute(
        "UPDATE alert_rules SET enabled = ?, updated_at = ? WHERE id = ?",
        (new_enabled, now, rule_id),
    )
    await conn.commit()

    status_label = "启用" if new_enabled else "禁用"
    return {"message": f"规则已{status_label}", "enabled": bool(new_enabled)}


# ── 告警历史 ──────────────────────────────────────────────


@router.get("/history")
async def list_history(
    level: Optional[str] = Query(None, description="按级别过滤: critical/warning/info"),
    status: Optional[str] = Query(None, description="按状态过滤: firing/acknowledged/resolved"),
    rule_id: Optional[int] = Query(None, description="按规则 ID 过滤"),
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    limit: int = Query(50, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取告警历史记录"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    conditions = []
    params = []

    if level is not None:
        conditions.append("level = ?")
        params.append(level)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if rule_id is not None:
        conditions.append("rule_id = ?")
        params.append(rule_id)
    if start_time is not None:
        conditions.append("triggered_at >= ?")
        params.append(start_time)
    if end_time is not None:
        conditions.append("triggered_at <= ?")
        params.append(end_time)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # 查询总数
    cursor = await conn.execute(
        f"SELECT COUNT(*) as cnt FROM alert_history WHERE {where_clause}",
        params,
    )
    total_row = await cursor.fetchone()
    total = total_row["cnt"] if total_row else 0

    # 查询数据
    query_params = params + [limit, offset]
    cursor = await conn.execute(
        f"""SELECT * FROM alert_history
            WHERE {where_clause}
            ORDER BY triggered_at DESC
            LIMIT ? OFFSET ?""",
        query_params,
    )
    rows = await cursor.fetchall()

    items = []
    for row in rows:
        item = dict(row)
        # 解析 JSON 字段
        try:
            item["detail"] = json.loads(item.get("detail", "{}"))
        except (json.JSONDecodeError, TypeError):
            item["detail"] = {}
        try:
            item["channel_results"] = json.loads(item.get("channel_results", "{}"))
        except (json.JSONDecodeError, TypeError):
            item["channel_results"] = {}
        items.append(item)

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.put("/history/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """确认告警"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    cursor = await conn.execute(
        "SELECT status FROM alert_history WHERE id = ?", (alert_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="告警记录不存在")

    if row["status"] == "acknowledged":
        return {"message": "告警已确认，无需重复操作"}

    now = datetime.now().isoformat()
    await conn.execute(
        "UPDATE alert_history SET status = ?, acknowledged_at = ? WHERE id = ?",
        ("acknowledged", now, alert_id),
    )
    await conn.commit()

    return {"message": "告警已确认"}


# ── 通知渠道管理 ──────────────────────────────────────────


@router.get("/channels")
async def list_channels():
    """获取所有通知渠道"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    cursor = await conn.execute(
        "SELECT * FROM notification_channels ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()

    items = []
    for row in rows:
        item = dict(row)
        try:
            item["config"] = json.loads(item.get("config", "{}"))
        except (json.JSONDecodeError, TypeError):
            item["config"] = {}
        items.append(item)

    return {"items": items, "total": len(items)}


@router.post("/channels")
async def create_channel(
    name: str = Body(..., description="渠道名称"),
    type: str = Body(..., description="渠道类型: webhook/email/dingtalk/feishu/slack"),
    config: dict = Body({}, description="渠道配置（JSON）"),
    enabled: bool = Body(True, description="是否启用"),
):
    """创建通知渠道"""
    valid_types = {"webhook", "email", "dingtalk", "feishu", "slack"}
    if type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的渠道类型，可选: {valid_types}")

    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()
    now = datetime.now().isoformat()

    await conn.execute(
        """INSERT INTO notification_channels
           (name, type, enabled, config, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            name,
            type,
            int(enabled),
            json.dumps(config, ensure_ascii=False),
            now,
            now,
        ),
    )
    await conn.commit()

    cursor = await conn.execute(
        "SELECT * FROM notification_channels WHERE id = last_insert_rowid()"
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="创建渠道失败")

    item = dict(row)
    try:
        item["config"] = json.loads(item.get("config", "{}"))
    except (json.JSONDecodeError, TypeError):
        item["config"] = {}

    return {"message": "渠道创建成功", "channel": item}


@router.put("/channels/{channel_id}")
async def update_channel(
    channel_id: int,
    name: Optional[str] = Body(None, description="渠道名称"),
    type: Optional[str] = Body(None, description="渠道类型"),
    config: Optional[dict] = Body(None, description="渠道配置"),
    enabled: Optional[bool] = Body(None, description="是否启用"),
):
    """更新通知渠道"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    cursor = await conn.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="渠道不存在")

    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if type is not None:
        valid_types = {"webhook", "email", "dingtalk", "feishu", "slack"}
        if type not in valid_types:
            raise HTTPException(status_code=400, detail=f"无效的渠道类型，可选: {valid_types}")
        updates.append("type = ?")
        params.append(type)
    if config is not None:
        updates.append("config = ?")
        params.append(json.dumps(config, ensure_ascii=False))
    if enabled is not None:
        updates.append("enabled = ?")
        params.append(int(enabled))

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供更新字段")

    now = datetime.now().isoformat()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(channel_id)

    await conn.execute(
        f"UPDATE notification_channels SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await conn.commit()

    cursor = await conn.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    )
    row = await cursor.fetchone()
    item = dict(row)
    try:
        item["config"] = json.loads(item.get("config", "{}"))
    except (json.JSONDecodeError, TypeError):
        item["config"] = {}

    return {"message": "渠道更新成功", "channel": item}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: int):
    """删除通知渠道"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    cursor = await conn.execute(
        "SELECT id FROM notification_channels WHERE id = ?", (channel_id,)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="渠道不存在")

    await conn.execute(
        "DELETE FROM notification_channels WHERE id = ?", (channel_id,)
    )
    await conn.commit()

    return {"message": "渠道删除成功"}


@router.post("/channels/{channel_id}/test")
async def test_channel(channel_id: int):
    """测试通知渠道连通性"""
    engine = _get_engine()
    result = await engine.test_channel(channel_id)
    return result


# ── 告警统计 ──────────────────────────────────────────────


@router.get("/stats")
async def alert_stats():
    """获取告警统计信息"""
    engine = _get_engine()
    await engine.ensure_tables()
    conn = await _get_db()._get_conn()

    # 按级别统计
    cursor = await conn.execute(
        """SELECT level, COUNT(*) as count
           FROM alert_history
           GROUP BY level"""
    )
    by_level = [dict(row) for row in await cursor.fetchall()]

    # 按状态统计
    cursor = await conn.execute(
        """SELECT status, COUNT(*) as count
           FROM alert_history
           GROUP BY status"""
    )
    by_status = [dict(row) for row in await cursor.fetchall()]

    # 最近 24 小时趋势（按小时）
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor = await conn.execute(
        """SELECT strftime('%Y-%m-%d %H:00', triggered_at) AS hour,
                  COUNT(*) as count
           FROM alert_history
           WHERE triggered_at >= ?
           GROUP BY hour
           ORDER BY hour""",
        (cutoff,),
    )
    recent_trend = [dict(row) for row in await cursor.fetchall()]

    # 总数
    cursor = await conn.execute("SELECT COUNT(*) as cnt FROM alert_history")
    total_row = await cursor.fetchone()
    total = total_row["cnt"] if total_row else 0

    # 活跃告警数（firing 状态）
    cursor = await conn.execute(
        "SELECT COUNT(*) as cnt FROM alert_history WHERE status = 'firing'"
    )
    firing_row = await cursor.fetchone()
    firing_count = firing_row["cnt"] if firing_row else 0

    return {
        "total": total,
        "firing_count": firing_count,
        "by_level": by_level,
        "by_status": by_status,
        "recent_trend": recent_trend,
    }


# ── 手动触发告警检查 ──────────────────────────────────────


@router.post("/check")
async def check_alerts():
    """手动触发告警检查，评估所有启用的规则"""
    engine = _get_engine()

    try:
        fired = await engine.evaluate_rules()
        return {
            "message": f"告警检查完成，共触发 {len(fired)} 条告警",
            "fired_count": len(fired),
            "fired_alerts": fired,
        }
    except Exception as e:
        logger.error("告警检查失败: %s", e)
        raise HTTPException(status_code=500, detail=f"告警检查失败: {str(e)[:200]}")
