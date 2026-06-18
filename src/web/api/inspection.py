"""定时巡检 API

端点:
- POST /api/inspection/run                      — 执行巡检
- GET /api/inspection/history                   — 获取巡检历史
- POST /api/inspection/schedule                 — 创建定时巡检任务
- GET /api/inspection/schedules                 — 列出定时巡检任务
- DELETE /api/inspection/schedule/{schedule_id} — 删除定时巡检任务
- GET /api/inspection/{inspection_id}           — 获取巡检详情

巡检是一键诊断的轻量版，只执行关键检查项（连接、内存/磁盘、慢查询、告警）。
巡检结果保存到 inspection_reports 表。
定时巡检任务保存到 inspection_schedules 表（仅实现 CRUD，实际调度需后台调度器）。
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from src.collector.redis_connector import RedisConnector
from src.web.api.deps import get_db as _get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/inspection", tags=["定时巡检"])


async def _ensure_tables():
    """确保巡检相关表存在"""
    db = _get_db()
    conn = await db._get_conn()
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS inspection_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            db_type TEXT NOT NULL,
            instance_id INTEGER,
            executed_at TEXT NOT NULL,
            checks_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT,
            health_score REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'unknown'
        );

        CREATE TABLE IF NOT EXISTS inspection_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cron_expression TEXT NOT NULL,
            db_type TEXT NOT NULL,
            instance_id INTEGER,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_run_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_inspection_reports_executed_at
            ON inspection_reports(executed_at);
        CREATE INDEX IF NOT EXISTS idx_inspection_schedules_enabled
            ON inspection_schedules(enabled);
    """)
    await conn.commit()


# ── Pydantic 模型 ───────────────────────────────────────────

class ScheduleRequest(BaseModel):
    """创建定时巡检任务请求"""
    cron_expression: str
    db_type: str = "all"
    instance_id: Optional[int] = None


# ── 巡检执行 ────────────────────────────────────────────────

@router.post("/run")
async def run_inspection(
    db_type: str = Query("all", description="数据库类型: mysql/redis/all"),
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """执行一次巡检（一键诊断的轻量版）

    巡检只执行关键检查项：连接、内存/磁盘、慢查询、告警。
    """
    await _ensure_tables()

    if db_type == "all":
        # 对所有实例巡检
        results = []
        instances = await _list_instances()
        for inst in instances:
            itype = inst.get("db_type", "mysql")
            iid = inst.get("id")
            report = await _inspect_instance(itype, iid)
            results.append(report)
        return {"reports": results, "total": len(results)}

    # 单类型巡检
    report = await _inspect_instance(db_type, instance_id)
    return report


async def _list_instances() -> list[dict]:
    """列出所有已注册实例"""
    db = _get_db()
    conn = await db._get_conn()
    try:
        cursor = await conn.execute(
            "SELECT id, name, host, port, db_type FROM instances ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


async def _inspect_instance(db_type: str, instance_id: Optional[int]) -> dict:
    """对单个实例执行巡检，生成报告并保存"""
    if db_type == "redis":
        checks = await _inspect_redis(instance_id)
    else:
        checks = await _inspect_mysql(instance_id)

    # 计算健康分（0-100）
    score_map = {"pass": 100, "warning": 60, "fail": 0, "critical": 0}
    total = len(checks)
    if total == 0:
        health_score = 0.0
    else:
        health_score = round(
            sum(score_map.get(c.get("status"), 0) for c in checks) / total, 1
        )

    # 汇总状态
    statuses = [c.get("status") for c in checks]
    if "critical" in statuses or "fail" in statuses:
        status = "critical"
    elif "warning" in statuses:
        status = "warning"
    else:
        status = "healthy"

    summary = _build_summary(db_type, instance_id, checks, status)

    # 保存到数据库
    executed_at = datetime.now().isoformat()
    report_id = await _save_report(
        db_type, instance_id, executed_at, checks, summary, health_score, status
    )

    return {
        "id": report_id,
        "db_type": db_type,
        "instance_id": instance_id,
        "executed_at": executed_at,
        "checks": checks,
        "summary": summary,
        "health_score": health_score,
        "status": status,
    }


async def _inspect_redis(instance_id: Optional[int]) -> list[dict]:
    """Redis 巡检：连接、内存、碎片率、慢查询、告警"""
    checks: list[dict] = []

    connector = (
        RedisConnector.get_instance_connection(instance_id)
        if instance_id is not None
        else RedisConnector()
    )
    if not connector:
        checks.append({
            "name": "connection",
            "status": "fail",
            "message": "无法创建 Redis 连接器",
            "detail": {},
        })
        return checks

    try:
        metrics = await connector.get_metrics()
        if not metrics:
            checks.append({
                "name": "connection",
                "status": "fail",
                "message": "无法获取 Redis 指标",
                "detail": {},
            })
            return checks

        # 连接检查
        checks.append({
            "name": "connection",
            "status": "pass",
            "message": "连接正常",
            "detail": {"connected": True},
        })

        # 内存检查
        memory = metrics.get("memory", {})
        used = memory.get("used_memory", 0)
        maxmem = memory.get("maxmemory", 0)
        if maxmem > 0:
            usage = used / maxmem * 100
            detail = {
                "used": used,
                "max": maxmem,
                "usage_percent": round(usage, 2),
            }
            if usage >= 90:
                checks.append({"name": "memory", "status": "critical",
                               "message": f"内存使用率 {usage:.1f}% 超过 90%", "detail": detail})
            elif usage >= 80:
                checks.append({"name": "memory", "status": "warning",
                               "message": f"内存使用率 {usage:.1f}% 超过 80%", "detail": detail})
            else:
                checks.append({"name": "memory", "status": "pass",
                               "message": f"内存使用率 {usage:.1f}% 正常", "detail": detail})
        else:
            checks.append({
                "name": "memory", "status": "pass",
                "message": "未设置 maxmemory",
                "detail": {"used": used, "max": maxmem},
            })

        # 碎片率检查
        frag = memory.get("fragmentation_ratio", 0) or 0
        if frag > 2.0:
            checks.append({"name": "fragmentation", "status": "critical",
                           "message": f"碎片率 {frag} 超过 2.0", "detail": {"ratio": frag}})
        elif frag > 1.5:
            checks.append({"name": "fragmentation", "status": "warning",
                           "message": f"碎片率 {frag} 超过 1.5", "detail": {"ratio": frag}})
        else:
            checks.append({"name": "fragmentation", "status": "pass",
                           "message": f"碎片率 {frag} 正常", "detail": {"ratio": frag}})

        # 慢查询检查
        try:
            slowlog_len = await connector.get_slowlog_len()
            if slowlog_len > 100:
                checks.append({"name": "slowlog", "status": "warning",
                               "message": f"慢查询日志数量 {slowlog_len} 较多",
                               "detail": {"count": slowlog_len}})
            else:
                checks.append({"name": "slowlog", "status": "pass",
                               "message": f"慢查询日志数量 {slowlog_len}",
                               "detail": {"count": slowlog_len}})
        except Exception as e:
            checks.append({"name": "slowlog", "status": "warning",
                           "message": f"获取慢查询失败: {str(e)[:100]}", "detail": {}})

    except Exception as e:
        checks.append({
            "name": "connection",
            "status": "fail",
            "message": f"巡检异常: {str(e)[:150]}",
            "detail": {},
        })
    finally:
        await connector.close()

    # 告警检查（从数据库）
    checks.append(await _check_recent_alerts(instance_id))

    return checks


async def _inspect_mysql(instance_id: Optional[int]) -> list[dict]:
    """MySQL 巡检：连接、磁盘/数据量、慢查询、告警"""
    from src.collector.mysql_connector import MySQLConnector

    checks: list[dict] = []

    connector = (
        MySQLConnector.get_instance_connection(instance_id)
        if instance_id is not None
        else MySQLConnector()
    )
    if not connector:
        checks.append({
            "name": "connection",
            "status": "fail",
            "message": "无法创建 MySQL 连接器",
            "detail": {},
        })
        return checks

    try:
        status = await connector.get_global_status()
        if not status:
            checks.append({
                "name": "connection",
                "status": "fail",
                "message": "无法获取 MySQL 状态",
                "detail": {},
            })
            return checks

        # 连接检查
        checks.append({
            "name": "connection",
            "status": "pass",
            "message": "连接正常",
            "detail": {"connected": True},
        })

        # 连接数检查
        threads_connected = status.get("Threads_connected", 0)
        max_allowed = 0
        try:
            variables = await connector.get_variables(like_pattern="max_connections")
            max_allowed = int(variables.get("max_connections", 0))
        except Exception:
            pass

        if max_allowed > 0:
            usage = threads_connected / max_allowed * 100
            detail = {
                "current": threads_connected,
                "max": max_allowed,
                "usage_percent": round(usage, 2),
            }
            if usage >= 90:
                checks.append({"name": "connections", "status": "critical",
                               "message": f"连接使用率 {usage:.1f}% 超过 90%", "detail": detail})
            elif usage >= 80:
                checks.append({"name": "connections", "status": "warning",
                               "message": f"连接使用率 {usage:.1f}% 超过 80%", "detail": detail})
            else:
                checks.append({"name": "connections", "status": "pass",
                               "message": f"连接使用率 {usage:.1f}% 正常", "detail": detail})
        else:
            checks.append({
                "name": "connections", "status": "pass",
                "message": f"当前连接数 {threads_connected}",
                "detail": {"current": threads_connected, "max": max_allowed},
            })

        # 慢查询检查
        slow_queries = status.get("Slow_queries", 0)
        if slow_queries > 100:
            checks.append({"name": "slow_queries", "status": "warning",
                           "message": f"慢查询数 {slow_queries} 较多",
                           "detail": {"count": slow_queries}})
        else:
            checks.append({"name": "slow_queries", "status": "pass",
                           "message": f"慢查询数 {slow_queries}",
                           "detail": {"count": slow_queries}})

        # 磁盘/数据量检查
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
                checks.append({
                    "name": "disk", "status": "pass",
                    "message": f"表数量 {table_count}，数据量 {data_size} 字节",
                    "detail": {"table_count": table_count, "data_size": data_size},
                })
        except Exception as e:
            checks.append({
                "name": "disk", "status": "warning",
                "message": f"获取磁盘信息失败: {str(e)[:100]}",
                "detail": {},
            })

    except Exception as e:
        checks.append({
            "name": "connection",
            "status": "fail",
            "message": f"巡检异常: {str(e)[:150]}",
            "detail": {},
        })
    finally:
        await connector.close()

    # 告警检查
    checks.append(await _check_recent_alerts(instance_id))

    return checks


async def _check_recent_alerts(instance_id: Optional[int]) -> dict:
    """检查最近未读告警"""
    db = _get_db()
    try:
        alerts = await db.query_alerts(is_read=0, limit=10)
        count = len(alerts)
        if count > 0:
            return {
                "name": "alerts",
                "status": "warning",
                "message": f"有 {count} 条未读告警",
                "detail": {"unread_count": count},
            }
        return {
            "name": "alerts",
            "status": "pass",
            "message": "无未读告警",
            "detail": {"unread_count": 0},
        }
    except Exception as e:
        return {
            "name": "alerts",
            "status": "warning",
            "message": f"获取告警失败: {str(e)[:100]}",
            "detail": {},
        }


def _build_summary(db_type: str, instance_id: Optional[int],
                   checks: list[dict], status: str) -> str:
    """生成巡检摘要文本"""
    pass_count = sum(1 for c in checks if c.get("status") == "pass")
    warn_count = sum(1 for c in checks if c.get("status") == "warning")
    fail_count = sum(1 for c in checks if c.get("status") in ("fail", "critical"))
    return (
        f"{db_type} 实例 {instance_id or '默认'} 巡检完成："
        f"通过 {pass_count}，警告 {warn_count}，异常 {fail_count}，整体状态 {status}"
    )


async def _save_report(
    db_type: str,
    instance_id: Optional[int],
    executed_at: str,
    checks: list[dict],
    summary: str,
    health_score: float,
    status: str,
) -> int:
    """保存巡检报告到数据库，返回报告 ID"""
    db = _get_db()
    conn = await db._get_conn()
    checks_json = json.dumps(checks, ensure_ascii=False)
    cursor = await conn.execute(
        """INSERT INTO inspection_reports
           (db_type, instance_id, executed_at, checks_json, summary, health_score, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (db_type, instance_id, executed_at, checks_json, summary, health_score, status),
    )
    await conn.commit()
    return cursor.lastrowid


# ── 巡检历史 ────────────────────────────────────────────────

@router.get("/history")
async def get_inspection_history(
    limit: int = Query(20, ge=1, le=200, description="返回数量"),
):
    """获取巡检历史列表"""
    await _ensure_tables()
    db = _get_db()
    conn = await db._get_conn()
    cursor = await conn.execute(
        """SELECT id, db_type, instance_id, executed_at, summary, health_score, status
           FROM inspection_reports
           ORDER BY executed_at DESC
           LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── 定时巡检任务 CRUD ───────────────────────────────────────

@router.post("/schedule")
async def create_schedule(body: ScheduleRequest = Body(...)):
    """创建定时巡检任务

    注意：实际定时执行需要后台调度器，这里只实现 CRUD。
    """
    await _ensure_tables()
    db = _get_db()
    conn = await db._get_conn()
    now = datetime.now().isoformat()

    cursor = await conn.execute(
        """INSERT INTO inspection_schedules
           (cron_expression, db_type, instance_id, enabled, created_at, last_run_at)
           VALUES (?, ?, ?, 1, ?, NULL)""",
        (body.cron_expression, body.db_type, body.instance_id, now),
    )
    await conn.commit()

    schedule_id = cursor.lastrowid
    return {
        "id": schedule_id,
        "cron_expression": body.cron_expression,
        "db_type": body.db_type,
        "instance_id": body.instance_id,
        "enabled": True,
        "created_at": now,
        "last_run_at": None,
    }


@router.get("/schedules")
async def list_schedules():
    """列出所有定时巡检任务"""
    await _ensure_tables()
    db = _get_db()
    conn = await db._get_conn()
    cursor = await conn.execute(
        "SELECT * FROM inspection_schedules ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    schedules = []
    for r in rows:
        item = dict(r)
        item["enabled"] = bool(item.get("enabled", 1))
        schedules.append(item)
    return schedules


@router.delete("/schedule/{schedule_id}")
async def delete_schedule(schedule_id: int):
    """删除定时巡检任务"""
    await _ensure_tables()
    db = _get_db()
    conn = await db._get_conn()

    cursor = await conn.execute(
        "SELECT id FROM inspection_schedules WHERE id = ?", (schedule_id,)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="定时巡检任务不存在")

    await conn.execute(
        "DELETE FROM inspection_schedules WHERE id = ?", (schedule_id,)
    )
    await conn.commit()
    return {"message": "定时巡检任务已删除", "id": schedule_id}


# ── 巡检详情（放在最后，避免路径参数遮蔽 /history、/schedules 等）──

@router.get("/{inspection_id}")
async def get_inspection_detail(inspection_id: int):
    """获取巡检详情"""
    await _ensure_tables()
    db = _get_db()
    conn = await db._get_conn()
    cursor = await conn.execute(
        "SELECT * FROM inspection_reports WHERE id = ?",
        (inspection_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="巡检报告不存在")

    item = dict(row)
    try:
        item["checks"] = json.loads(item.get("checks_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        item["checks"] = []
    item.pop("checks_json", None)
    return item
