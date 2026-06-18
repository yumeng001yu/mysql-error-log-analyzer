"""多实例统一管理 API"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from src.web.api.deps import get_db as _get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances", tags=["instances"])

# ── Pydantic 模型 ───────────────────────────────────────────

class CredentialsModel(BaseModel):
    """实例连接凭据"""
    user: str = "root"
    password: str = ""


class CreateInstanceRequest(BaseModel):
    """创建实例请求"""
    name: str
    host: str = "localhost"
    port: int = 3306
    log_path: str = ""
    group_name: Optional[str] = None
    db_type: str = "mysql"  # mysql / redis
    credentials: Optional[CredentialsModel] = None


class UpdateInstanceRequest(BaseModel):
    """更新实例请求（部分更新）"""
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    log_path: Optional[str] = None
    group_name: Optional[str] = None
    db_type: Optional[str] = None
    credentials: Optional[CredentialsModel] = None


class UpdateGroupRequest(BaseModel):
    """更新分组设置请求"""
    alert_enabled: Optional[bool] = None
    notification_channels: Optional[list[str]] = None


# ── 数据库实例 ──────────────────────────────────────────────

# 标记是否已完成列迁移
_migrated: bool = False


async def _ensure_columns():
    """确保 instances 表包含新增列（懒迁移）"""
    global _migrated
    if _migrated:
        return

    db = _get_db()
    conn = await db._get_conn()

    # 需要新增的列定义
    new_columns = [
        ("group_name", "TEXT DEFAULT NULL"),
        ("status", "TEXT DEFAULT 'unknown'"),
        ("last_collected_at", "TEXT DEFAULT NULL"),
        ("credentials", "TEXT DEFAULT NULL"),
        ("db_type", "TEXT DEFAULT 'mysql'"),
    ]

    for col_name, col_type in new_columns:
        try:
            await conn.execute(f"ALTER TABLE instances ADD COLUMN {col_name} {col_type}")
            logger.info("已添加列: instances.%s", col_name)
        except Exception:
            # 列已存在时忽略错误
            pass

    await conn.commit()
    _migrated = True


async def _ensure_group_tables():
    """确保实例分组相关表存在"""
    db = _get_db()
    conn = await db._get_conn()

    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS instance_groups (
            name TEXT PRIMARY KEY,
            alert_enabled INTEGER NOT NULL DEFAULT 1,
            notification_channels TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    await conn.commit()


def _mask_credentials(creds_json: Optional[str]) -> Optional[dict]:
    """解析凭据 JSON 并脱敏密码"""
    if not creds_json:
        return None
    try:
        creds = json.loads(creds_json)
        if "password" in creds and creds["password"]:
            creds["password"] = "******"
        return creds
    except (json.JSONDecodeError, TypeError):
        return None


def _format_instance(row: dict) -> dict:
    """格式化实例信息，包含统计字段"""
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "host": row.get("host", "localhost"),
        "port": row.get("port", 3306),
        "log_path": row.get("log_path"),
        "group_name": row.get("group_name"),
        "status": row.get("status", "unknown"),
        "last_collected_at": row.get("last_collected_at"),
        "db_type": row.get("db_type", "mysql"),
        "credentials": _mask_credentials(row.get("credentials")),
        "created_at": row.get("created_at"),
    }


# ── API 端点 ────────────────────────────────────────────────

@router.get("/")
async def list_instances(
    group: Optional[str] = Query(None, description="按分组名称过滤"),
):
    """列出所有已注册的实例"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    # 一次查询获取实例及其错误/警告计数，避免 N+1 查询
    if group:
        cursor = await conn.execute(
            """
            SELECT i.*,
                (SELECT COUNT(*) FROM log_entries
                 WHERE instance_id = i.id AND level IN ('ERROR', 'FATAL')) AS error_count,
                (SELECT COUNT(*) FROM log_entries
                 WHERE instance_id = i.id AND level = 'WARNING') AS warning_count
            FROM instances i
            WHERE i.group_name = ?
            ORDER BY i.created_at DESC
            """,
            (group,),
        )
    else:
        cursor = await conn.execute(
            """
            SELECT i.*,
                (SELECT COUNT(*) FROM log_entries
                 WHERE instance_id = i.id AND level IN ('ERROR', 'FATAL')) AS error_count,
                (SELECT COUNT(*) FROM log_entries
                 WHERE instance_id = i.id AND level = 'WARNING') AS warning_count
            FROM instances i
            ORDER BY i.created_at DESC
            """
        )
    rows = await cursor.fetchall()

    instances = [_format_instance(dict(row)) for row in rows]

    return instances


@router.post("/")
async def create_instance(body: CreateInstanceRequest = Body(...)):
    """注册新的数据库实例（MySQL/Redis）"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    now = datetime.now().isoformat()

    # 序列化凭据为 JSON
    creds_json = None
    if body.credentials:
        creds_data = {"user": body.credentials.user, "password": body.credentials.password}
        if body.db_type == "redis":
            creds_data = {"username": body.credentials.user, "password": body.credentials.password}
        creds_json = json.dumps(creds_data, ensure_ascii=False)

    # 检查同名实例是否已存在
    cursor = await conn.execute(
        "SELECT id FROM instances WHERE name = ?", (body.name,)
    )
    if await cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"实例名称 '{body.name}' 已存在")

    await conn.execute(
        """INSERT INTO instances (name, host, port, log_path, group_name, status, credentials, db_type, created_at)
           VALUES (?, ?, ?, ?, ?, 'online', ?, ?, ?)""",
        (body.name, body.host, body.port, body.log_path, body.group_name, creds_json, body.db_type, now),
    )
    await conn.commit()

    # 获取新创建的实例
    cursor = await conn.execute(
        "SELECT * FROM instances WHERE id = last_insert_rowid()"
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="创建实例失败")

    return _format_instance(dict(row))


@router.put("/{instance_id}")
async def update_instance(
    instance_id: int,
    body: UpdateInstanceRequest = Body(...),
):
    """更新实例配置（部分更新）"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    # 检查实例是否存在
    cursor = await conn.execute(
        "SELECT * FROM instances WHERE id = ?", (instance_id,)
    )
    existing = await cursor.fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="实例不存在")

    # 构建更新字段
    updates = []
    params = []

    field_map = {
        "name": body.name,
        "host": body.host,
        "port": body.port,
        "log_path": body.log_path,
        "group_name": body.group_name,
    }

    for field, value in field_map.items():
        if value is not None:
            updates.append(f"{field} = ?")
            params.append(value)

    # 凭据单独处理（需要序列化为 JSON）
    if body.credentials is not None:
        creds_json = json.dumps(
            {"user": body.credentials.user, "password": body.credentials.password},
            ensure_ascii=False,
        )
        updates.append("credentials = ?")
        params.append(creds_json)

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供更新字段")

    params.append(instance_id)

    await conn.execute(
        f"UPDATE instances SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await conn.commit()

    # 返回更新后的实例
    cursor = await conn.execute(
        "SELECT * FROM instances WHERE id = ?", (instance_id,)
    )
    row = await cursor.fetchone()
    return _format_instance(dict(row))


@router.delete("/{instance_id}")
async def delete_instance(instance_id: int):
    """移除实例"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    # 检查实例是否存在
    cursor = await conn.execute(
        "SELECT id FROM instances WHERE id = ?", (instance_id,)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="实例不存在")

    # 删除关联的日志条目
    await conn.execute(
        "DELETE FROM log_entries WHERE instance_id = ?", (instance_id,)
    )
    # 删除关联的告警
    await conn.execute(
        "DELETE FROM critical_alerts WHERE instance_id = ?", (instance_id,)
    )
    # 删除关联的分析结果
    await conn.execute(
        "DELETE FROM analysis_results WHERE instance_id = ?", (instance_id,)
    )
    # 删除关联的监控指标
    await conn.execute(
        "DELETE FROM monitor_metrics WHERE instance_id = ?", (instance_id,)
    )
    # 删除实例
    await conn.execute(
        "DELETE FROM instances WHERE id = ?", (instance_id,)
    )
    await conn.commit()

    return {"message": "实例删除成功"}


@router.post("/{instance_id}/test")
async def test_instance_connection(instance_id: int):
    """测试实例连接（支持 MySQL 和 Redis）"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    # 获取实例信息
    cursor = await conn.execute(
        "SELECT * FROM instances WHERE id = ?", (instance_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="实例不存在")

    instance = dict(row)
    host = instance.get("host", "localhost")
    port = instance.get("port", 3306)
    db_type = instance.get("db_type", "mysql")

    # 解析凭据
    user = "root"
    password = ""
    creds_raw = instance.get("credentials")
    if creds_raw:
        try:
            creds = json.loads(creds_raw)
            user = creds.get("user", creds.get("username", "root"))
            password = creds.get("password", "")
        except (json.JSONDecodeError, TypeError):
            pass

    if db_type == "redis":
        # Redis 连接测试
        try:
            from src.collector.redis_connector import RedisConnector
        except ImportError:
            return {"connected": False, "version": "", "error": "redis 未安装，请执行 pip install redis"}

        connector = RedisConnector(host=host, port=port, password=password or None, username=user if user != "root" else None)
        try:
            result = await connector.test_connection()
            status = "online" if result["success"] else "error"
            await conn.execute(
                "UPDATE instances SET status = ? WHERE id = ?",
                (status, instance_id),
            )
            await conn.commit()
            return result
        finally:
            await connector.close()
    else:
        # MySQL 连接测试
        try:
            import pymysql
        except ImportError:
            return {"connected": False, "version": "", "error": "pymysql 未安装，请执行 pip install pymysql"}

        def _do_connect():
            """同步执行连接测试"""
            c = pymysql.connect(
                host=host, port=port, user=user, password=password,
                connect_timeout=5,
            )
            version = c.server_version
            c.close()
            return version

        try:
            version = await asyncio.to_thread(_do_connect)
            # 连接成功，更新实例状态
            await conn.execute(
                "UPDATE instances SET status = 'online' WHERE id = ?",
                (instance_id,),
            )
            await conn.commit()
            return {"connected": True, "version": str(version), "error": ""}
        except pymysql.err.OperationalError as e:
            error_code = e.args[0] if e.args else 0
            error_msg = str(e)[:200]

            # 根据错误码判断状态
            if error_code in (1045, 28000):
                # 认证失败
                status = "auth_failed"
            elif error_code in (2003, 2006):
                # 连接拒绝/超时
                status = "unreachable"
            else:
                status = "error"

            await conn.execute(
                "UPDATE instances SET status = ? WHERE id = ?",
                (status, instance_id),
            )
            await conn.commit()

            return {"connected": False, "version": "", "error": error_msg}
        except Exception as e:
            error_msg = str(e)[:200]
            await conn.execute(
                "UPDATE instances SET status = 'error' WHERE id = ?",
                (instance_id,),
            )
            await conn.commit()
            return {"connected": False, "version": "", "error": error_msg}


@router.get("/{instance_id}/status")
async def get_instance_status(instance_id: int):
    """获取实例状态摘要"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    # 获取实例信息
    cursor = await conn.execute(
        "SELECT * FROM instances WHERE id = ?", (instance_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="实例不存在")

    instance = _format_instance(dict(row))

    # 日志统计
    cursor = await conn.execute(
        "SELECT COUNT(*) as total FROM log_entries WHERE instance_id = ?",
        (instance_id,),
    )
    total_row = await cursor.fetchone()
    total = total_row["cnt"] if total_row else 0

    # 按级别统计
    cursor = await conn.execute(
        """SELECT level, COUNT(*) as count
           FROM log_entries
           WHERE instance_id = ?
           GROUP BY level
           ORDER BY count DESC""",
        (instance_id,),
    )
    by_level = [dict(r) for r in await cursor.fetchall()]

    # 最近 5 条错误
    cursor = await conn.execute(
        """SELECT id, timestamp, level, error_code, message
           FROM log_entries
           WHERE instance_id = ? AND level IN ('ERROR', 'FATAL')
           ORDER BY timestamp DESC
           LIMIT 5""",
        (instance_id,),
    )
    latest_errors = [dict(r) for r in await cursor.fetchall()]

    # 尝试获取 uptime（如果可连接）
    uptime = None
    host = dict(row).get("host", "localhost")
    port = dict(row).get("port", 3306)
    user = "root"
    password = ""
    creds_raw = dict(row).get("credentials")
    if creds_raw:
        try:
            creds = json.loads(creds_raw)
            user = creds.get("user", "root")
            password = creds.get("password", "")
        except (json.JSONDecodeError, TypeError):
            pass

    try:
        import pymysql

        def _get_uptime():
            c = pymysql.connect(
                host=host, port=port, user=user, password=password,
                connect_timeout=5,
            )
            with c.cursor() as cur:
                cur.execute("SHOW GLOBAL STATUS LIKE 'Uptime'")
                result = cur.fetchone()
            c.close()
            return int(result[1]) if result else None

        uptime = await asyncio.to_thread(_get_uptime)
    except Exception:
        pass

    return {
        "instance": instance,
        "log_stats": {
            "total": total,
            "by_level": by_level,
        },
        "latest_errors": latest_errors,
        "uptime": uptime,
    }


@router.get("/groups")
async def list_groups():
    """列出所有实例分组"""
    await _ensure_columns()
    await _ensure_group_tables()

    db = _get_db()
    conn = await db._get_conn()

    # 获取所有分组及其实例统计
    cursor = await conn.execute(
        """SELECT group_name, COUNT(*) as instance_count
           FROM instances
           WHERE group_name IS NOT NULL
           GROUP BY group_name""",
    )
    group_rows = await cursor.fetchall()

    groups = []
    for g in group_rows:
        gname = g["group_name"]
        instance_count = g["instance_count"]

        # 获取该分组下所有实例 ID
        cursor_ids = await conn.execute(
            "SELECT id FROM instances WHERE group_name = ?", (gname,)
        )
        ids = [r["id"] for r in await cursor_ids.fetchall()]

        # 统计该分组的错误和警告总数
        total_errors = 0
        total_warnings = 0
        if ids:
            placeholders = ",".join("?" for _ in ids)
            cursor_err = await conn.execute(
                f"SELECT COUNT(*) as cnt FROM log_entries WHERE instance_id IN ({placeholders}) AND level IN ('ERROR', 'FATAL')",
                ids,
            )
            err_row = await cursor_err.fetchone()
            total_errors = err_row["cnt"] if err_row else 0

            cursor_warn = await conn.execute(
                f"SELECT COUNT(*) as cnt FROM log_entries WHERE instance_id IN ({placeholders}) AND level = 'WARNING'",
                ids,
            )
            warn_row = await cursor_warn.fetchone()
            total_warnings = warn_row["cnt"] if warn_row else 0

        # 获取分组配置
        cursor_grp = await conn.execute(
            "SELECT alert_enabled, notification_channels FROM instance_groups WHERE name = ?",
            (gname,),
        )
        grp_row = await cursor_grp.fetchone()
        alert_enabled = bool(grp_row["alert_enabled"]) if grp_row else True
        notification_channels = []
        if grp_row and grp_row["notification_channels"]:
            try:
                notification_channels = json.loads(grp_row["notification_channels"])
            except (json.JSONDecodeError, TypeError):
                notification_channels = []

        groups.append({
            "name": gname,
            "instance_count": instance_count,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "alert_enabled": alert_enabled,
            "notification_channels": notification_channels,
        })

    # 也包含未分组的实例
    cursor_ungrouped = await conn.execute(
        "SELECT COUNT(*) as cnt FROM instances WHERE group_name IS NULL"
    )
    ungrouped_row = await cursor_ungrouped.fetchone()
    ungrouped_count = ungrouped_row["cnt"] if ungrouped_row else 0
    if ungrouped_count > 0:
        groups.append({
            "name": None,
            "instance_count": ungrouped_count,
            "total_errors": 0,
            "total_warnings": 0,
            "alert_enabled": True,
            "notification_channels": [],
        })

    return groups


@router.put("/groups/{group_name}")
async def update_group(
    group_name: str,
    body: UpdateGroupRequest = Body(...),
):
    """更新分组设置"""
    await _ensure_columns()
    await _ensure_group_tables()

    db = _get_db()
    conn = await db._get_conn()

    # 检查分组是否有实例
    cursor = await conn.execute(
        "SELECT COUNT(*) as cnt FROM instances WHERE group_name = ?",
        (group_name,),
    )
    count_row = await cursor.fetchone()
    if count_row["cnt"] == 0:
        raise HTTPException(status_code=404, detail=f"分组 '{group_name}' 不存在或没有关联实例")

    now = datetime.now().isoformat()

    # 检查分组配置是否已存在
    cursor_grp = await conn.execute(
        "SELECT name FROM instance_groups WHERE name = ?", (group_name,)
    )
    grp_exists = await cursor_grp.fetchone() is not None

    if grp_exists:
        # 更新
        updates = []
        params = []
        if body.alert_enabled is not None:
            updates.append("alert_enabled = ?")
            params.append(int(body.alert_enabled))
        if body.notification_channels is not None:
            updates.append("notification_channels = ?")
            params.append(json.dumps(body.notification_channels, ensure_ascii=False))

        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(group_name)
            await conn.execute(
                f"UPDATE instance_groups SET {', '.join(updates)} WHERE name = ?",
                params,
            )
            await conn.commit()
    else:
        # 创建
        alert_enabled = body.alert_enabled if body.alert_enabled is not None else True
        channels = json.dumps(
            body.notification_channels if body.notification_channels is not None else [],
            ensure_ascii=False,
        )
        await conn.execute(
            """INSERT INTO instance_groups (name, alert_enabled, notification_channels, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (group_name, int(alert_enabled), channels, now, now),
        )
        await conn.commit()

    # 返回更新后的分组信息
    cursor_grp = await conn.execute(
        "SELECT * FROM instance_groups WHERE name = ?", (group_name,)
    )
    grp_row = await cursor_grp.fetchone()
    result = dict(grp_row) if grp_row else {}
    result["alert_enabled"] = bool(result.get("alert_enabled", 1))
    try:
        result["notification_channels"] = json.loads(result.get("notification_channels", "[]"))
    except (json.JSONDecodeError, TypeError):
        result["notification_channels"] = []

    return result


@router.get("/overview")
async def get_overview():
    """获取所有实例的统一概览"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    # 获取所有实例
    cursor = await conn.execute("SELECT * FROM instances ORDER BY created_at DESC")
    rows = await cursor.fetchall()

    now = datetime.now()
    cutoff_24h = (now - timedelta(hours=24)).isoformat()

    instances = []
    healthy_count = 0
    unhealthy_count = 0

    for row in rows:
        item = dict(row)
        iid = item["id"]

        # 24 小时内错误和警告计数
        cursor_err = await conn.execute(
            """SELECT COUNT(*) as cnt FROM log_entries
               WHERE instance_id = ? AND level IN ('ERROR', 'FATAL') AND timestamp >= ?""",
            (iid, cutoff_24h),
        )
        err_row = await cursor_err.fetchone()
        error_count_24h = err_row["cnt"] if err_row else 0

        cursor_warn = await conn.execute(
            """SELECT COUNT(*) as cnt FROM log_entries
               WHERE instance_id = ? AND level = 'WARNING' AND timestamp >= ?""",
            (iid, cutoff_24h),
        )
        warn_row = await cursor_warn.fetchone()
        warning_count_24h = warn_row["cnt"] if warn_row else 0

        status = item.get("status", "unknown")
        if status == "online":
            healthy_count += 1
        else:
            unhealthy_count += 1

        instances.append({
            "id": iid,
            "name": item.get("name"),
            "host": item.get("host", "localhost"),
            "status": status,
            "error_count_24h": error_count_24h,
            "warning_count_24h": warning_count_24h,
            "group_name": item.get("group_name"),
        })

    # 分组概览
    cursor_groups = await conn.execute(
        """SELECT group_name, COUNT(*) as instance_count
           FROM instances
           WHERE group_name IS NOT NULL
           GROUP BY group_name""",
    )
    group_rows = await cursor_groups.fetchall()

    groups = []
    for g in group_rows:
        gname = g["group_name"]
        g_instance_count = g["instance_count"]

        # 获取分组下实例的状态摘要
        cursor_status = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM instances WHERE group_name = ? GROUP BY status",
            (gname,),
        )
        status_rows = await cursor_status.fetchall()
        status_summary = {r["status"] or "unknown": r["cnt"] for r in status_rows}

        groups.append({
            "name": gname,
            "instance_count": g_instance_count,
            "status_summary": status_summary,
        })

    return {
        "total_instances": len(rows),
        "healthy_count": healthy_count,
        "unhealthy_count": unhealthy_count,
        "instances": instances,
        "groups": groups,
    }


@router.post("/{instance_id}/collect")
async def collect_instance_logs(instance_id: int):
    """手动触发实例的日志采集"""
    await _ensure_columns()

    db = _get_db()
    conn = await db._get_conn()

    # 获取实例信息
    cursor = await conn.execute(
        "SELECT * FROM instances WHERE id = ?", (instance_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="实例不存在")

    instance = dict(row)
    log_path = instance.get("log_path", "")

    # 检查日志文件是否存在
    path = Path(log_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"日志文件不存在: {log_path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"路径不是文件: {log_path}")

    # 读取并解析日志文件
    from src.collector.parser import LogParser

    parser = LogParser()

    def _read_and_parse():
        """同步读取日志文件并解析"""
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except PermissionError:
            return None, "权限不足，无法读取日志文件"
        except Exception as e:
            return None, f"读取日志文件失败: {str(e)[:200]}"

        return lines, None

    lines, read_error = await asyncio.to_thread(_read_and_parse)
    if read_error:
        raise HTTPException(status_code=500, detail=read_error)

    # 批量解析
    parsed_entries = parser.parse_batch(lines)

    # 查询数据库中已有的日志条目，避免重复插入
    # 使用 raw_line 去重：获取该实例已有的最新日志时间戳
    cursor_latest = await conn.execute(
        "SELECT MAX(timestamp) as latest FROM log_entries WHERE instance_id = ?",
        (instance_id,),
    )
    latest_row = await cursor_latest.fetchone()
    latest_ts = latest_row["latest"] if latest_row and latest_row["latest"] else ""

    # 只插入比已有最新时间戳更新的条目
    now = datetime.now().isoformat()
    new_entries = []
    for entry in parsed_entries:
        ts = entry.get("timestamp", "")
        if ts > latest_ts:
            entry["instance_id"] = instance_id
            entry["category"] = parser.classify_error(
                entry.get("message", ""), entry.get("error_code")
            )
            entry["created_at"] = now
            new_entries.append(entry)

    # 批量插入
    if new_entries:
        await db.insert_log_entries(new_entries)

    # 更新实例的最后采集时间和状态
    await conn.execute(
        "UPDATE instances SET last_collected_at = ?, status = 'online' WHERE id = ?",
        (now, instance_id),
    )
    await conn.commit()

    return {"collected_entries": len(new_entries)}
