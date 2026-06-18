"""一键诊断 API

整合 MySQL 和 Redis 的所有检查项，生成诊断报告。

端点:
- POST /api/diagnosis/run            — 执行诊断
- GET  /api/diagnosis/history        — 获取诊断历史
- GET  /api/diagnosis/{diagnosis_id} — 获取诊断详情
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from src.collector.redis_connector import RedisConnector
from src.web.api.deps import get_db as _get_db
from src.web.api.deps import get_mysql_connector as _get_mysql_connector
from src.web.api.deps import get_redis_connector as _get_redis_connector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnosis", tags=["一键诊断"])


# ── Pydantic 模型 ───────────────────────────────────────────

class RunDiagnosisRequest(BaseModel):
    """执行诊断请求"""
    db_type: str = "all"  # mysql / redis / all
    instance_id: Optional[int] = None


# ── 数据库实例 ──────────────────────────────────────────────

_tables_ready: bool = False


async def _ensure_tables():
    """懒加载创建诊断报告表"""
    global _tables_ready
    if _tables_ready:
        return

    db = _get_db()
    conn = await db._get_conn()

    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS diagnosis_reports (
            id TEXT PRIMARY KEY,
            db_type TEXT NOT NULL,
            instance_id INTEGER,
            instance_name TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_ms INTEGER DEFAULT 0,
            checks_json TEXT DEFAULT '[]',
            summary_json TEXT DEFAULT '{}',
            health_score INTEGER DEFAULT 0,
            overall_status TEXT DEFAULT 'healthy',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_diagnosis_reports_db_type
            ON diagnosis_reports(db_type);
        CREATE INDEX IF NOT EXISTS idx_diagnosis_reports_instance_id
            ON diagnosis_reports(instance_id);
        CREATE INDEX IF NOT EXISTS idx_diagnosis_reports_created_at
            ON diagnosis_reports(created_at);
    """)

    await conn.commit()
    _tables_ready = True
    logger.info("诊断报告数据表已就绪")


# ── 连接器获取 ──────────────────────────────────────────────
# _get_redis_connector / _get_mysql_connector 由 src.web.api.deps 提供


async def _get_instance_info(instance_id: Optional[int], db_type: str) -> dict:
    """获取实例信息（id, name）"""
    if instance_id is None:
        return {"id": None, "name": f"默认{db_type.upper()}实例"}

    db = _get_db()
    conn = await db._get_conn()
    cursor = await conn.execute(
        "SELECT id, name, db_type FROM instances WHERE id = ?",
        (instance_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return {"id": instance_id, "name": f"实例#{instance_id}"}
    return {"id": row["id"], "name": row.get("name") or f"实例#{instance_id}"}


# ── 检查项辅助函数 ──────────────────────────────────────────

def _make_check(
    name: str,
    status: str,
    message: str,
    detail: Any = None,
    recommendation: str = "",
) -> dict:
    """构造检查项结果"""
    return {
        "name": name,
        "status": status,  # passed / warning / critical / error / skip
        "message": message,
        "detail": detail if detail is not None else {},
        "recommendation": recommendation,
    }


# ── Redis 诊断检查项 ───────────────────────────────────────

async def _check_redis_connection(connector: RedisConnector) -> dict:
    """连接检查：能否连接、连接数是否接近上限"""
    try:
        test_result = await connector.test_connection()
        if not test_result.get("success"):
            return _make_check(
                name="连接检查",
                status="critical",
                message=f"无法连接 Redis: {test_result.get('message', '')}",
                detail=test_result,
                recommendation="检查 Redis 服务是否运行、网络是否通畅、认证信息是否正确",
            )

        clients_info = await connector.get_clients_info()
        connected = int(clients_info.get("connected_clients", 0))
        maxclients = int(clients_info.get("maxclients", 0))

        detail = {
            "connected": connected,
            "maxclients": maxclients,
            "version": test_result.get("version", ""),
            "mode": test_result.get("mode", "standalone"),
        }

        if maxclients > 0:
            usage_percent = round(connected / maxclients * 100, 2)
            detail["usage_percent"] = usage_percent
            if usage_percent >= 90:
                return _make_check(
                    name="连接检查",
                    status="critical",
                    message=f"连接数已接近上限（{connected}/{maxclients}, {usage_percent}%）",
                    detail=detail,
                    recommendation="检查是否存在连接泄漏，或调大 maxclients 配置",
                )
            if usage_percent >= 70:
                return _make_check(
                    name="连接检查",
                    status="warning",
                    message=f"连接数使用率较高（{connected}/{maxclients}, {usage_percent}%）",
                    detail=detail,
                    recommendation="关注连接数增长趋势，排查异常客户端",
                )

        return _make_check(
            name="连接检查",
            status="passed",
            message=f"连接正常，当前连接数 {connected}" + (
                f"/{maxclients}" if maxclients > 0 else ""
            ),
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="连接检查",
            status="error",
            message=f"连接检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接配置",
        )


async def _check_redis_memory(connector: RedisConnector) -> dict:
    """内存检查：内存使用量、碎片率、maxmemory、淘汰策略"""
    try:
        memory = await connector.get_memory_info()
        used = int(memory.get("used_memory", 0))
        maxmemory = int(memory.get("maxmemory", 0))
        frag_ratio = float(memory.get("mem_fragmentation_ratio", 0))
        policy = memory.get("maxmemory_policy", "noeviction")

        detail = {
            "used_memory": used,
            "used_memory_human": memory.get("used_memory_human", ""),
            "maxmemory": maxmemory,
            "maxmemory_human": memory.get("maxmemory_human", ""),
            "fragmentation_ratio": frag_ratio,
            "maxmemory_policy": policy,
        }

        issues = []

        # maxmemory 检查
        if maxmemory == 0:
            issues.append(("warning", "未设置 maxmemory，可能导致内存无限增长"))
        else:
            usage_percent = round(used / maxmemory * 100, 2) if maxmemory > 0 else 0
            detail["usage_percent"] = usage_percent
            if usage_percent >= 90:
                issues.append(("critical", f"内存使用率过高（{usage_percent}%）"))
            elif usage_percent >= 70:
                issues.append(("warning", f"内存使用率较高（{usage_percent}%）"))

        # 碎片率检查
        if frag_ratio > 1.5:
            issues.append(("warning", f"内存碎片率过高（{frag_ratio}），建议重启或执行 MEMORY PURGE"))
        elif frag_ratio < 1.0 and used > 0:
            issues.append(("warning", f"内存碎片率偏低（{frag_ratio}），可能存在 swap"))

        # 淘汰策略检查
        if maxmemory > 0 and policy == "noeviction":
            issues.append(("warning", "已设置 maxmemory 但淘汰策略为 noeviction，写操作可能失败"))

        if any(s == "critical" for s, _ in issues):
            return _make_check(
                name="内存检查",
                status="critical",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="调整 maxmemory 与淘汰策略，监控内存使用趋势",
            )
        if issues:
            return _make_check(
                name="内存检查",
                status="warning",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="建议设置合理的 maxmemory 和淘汰策略（如 allkeys-lru）",
            )

        return _make_check(
            name="内存检查",
            status="passed",
            message=f"内存使用正常（{detail['used_memory_human']}）",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="内存检查",
            status="error",
            message=f"内存检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接与权限",
        )


async def _check_redis_persistence(connector: RedisConnector) -> dict:
    """持久化检查：RDB、AOF、最近一次 save 时间"""
    try:
        info = await connector.get_persistence_info()

        rdb_last_save = int(info.get("rdb_last_save_time", 0))
        rdb_changes = int(info.get("rdb_changes_since_last_save", 0))
        rdb_bgsave = int(info.get("rdb_bgsave_in_progress", 0))
        rdb_last_status = info.get("rdb_last_bgsave_status", "")

        aof_enabled = int(info.get("aof_enabled", 0))
        aof_rewrite = int(info.get("aof_rewrite_in_progress", 0))
        aof_last_status = info.get("aof_last_write_status", "")

        detail = {
            "rdb_last_save_time": rdb_last_save,
            "rdb_changes_since_last_save": rdb_changes,
            "rdb_bgsave_in_progress": rdb_bgsave,
            "rdb_last_bgsave_status": rdb_last_status,
            "aof_enabled": bool(aof_enabled),
            "aof_rewrite_in_progress": bool(aof_rewrite),
            "aof_last_write_status": aof_last_status,
        }

        issues = []

        # RDB 状态检查
        if rdb_last_status and rdb_last_status != "ok":
            issues.append(("critical", f"RDB 最近一次 BGSAVE 失败（{rdb_last_status}）"))

        # AOF 状态检查
        if aof_enabled:
            if aof_last_status and aof_last_status != "ok":
                issues.append(("critical", f"AOF 最近一次写入失败（{aof_last_status}）"))
        else:
            # 未启用 AOF，仅作为提示
            if rdb_last_save == 0:
                issues.append(("warning", "RDB 与 AOF 均未生效，存在数据丢失风险"))

        # 最近一次 save 时间检查
        if rdb_last_save > 0:
            now_ts = int(time.time())
            hours_since_save = (now_ts - rdb_last_save) / 3600
            detail["hours_since_last_save"] = round(hours_since_save, 2)
            if hours_since_save > 24 and rdb_changes > 0:
                issues.append(("warning", f"距上次 RDB save 已 {int(hours_since_save)} 小时，且有 {rdb_changes} 个未保存变更"))

        if any(s == "critical" for s, _ in issues):
            return _make_check(
                name="持久化检查",
                status="critical",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="检查磁盘空间与权限，必要时手动执行 BGSAVE",
            )
        if issues:
            return _make_check(
                name="持久化检查",
                status="warning",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="建议启用 AOF 持久化以提升数据安全性",
            )

        aof_str = "已启用" if aof_enabled else "未启用"
        return _make_check(
            name="持久化检查",
            status="passed",
            message=f"持久化正常（RDB: 正常, AOF: {aof_str}）",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="持久化检查",
            status="error",
            message=f"持久化检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接与权限",
        )


async def _check_redis_slowlog(connector: RedisConnector) -> dict:
    """慢查询检查：慢查询数量、是否有超长慢查询（>1s）"""
    try:
        slowlog_len = await connector.get_slowlog_len()
        slowlog = await connector.get_slowlog(count=100)

        detail = {
            "slowlog_count": slowlog_len,
            "recent_count": len(slowlog),
        }

        # 统计超长慢查询（>1s = 1,000,000 us）
        long_slow = [s for s in slowlog if int(s.get("duration_us", 0)) > 1_000_000]
        detail["long_slow_count"] = len(long_slow)

        if long_slow:
            top = max(long_slow, key=lambda x: int(x.get("duration_us", 0)))
            detail["slowest_duration_ms"] = round(int(top.get("duration_us", 0)) / 1000, 2)
            detail["slowest_command"] = top.get("command", "")[:200]
            return _make_check(
                name="慢查询检查",
                status="critical",
                message=f"发现 {len(long_slow)} 条超过 1s 的慢查询，最长 {detail['slowest_duration_ms']}ms",
                detail=detail,
                recommendation="优化慢查询命令，或调低 slowlog-log-slower-than 阈值以便发现更多慢查询",
            )

        if slowlog_len > 100:
            return _make_check(
                name="慢查询检查",
                status="warning",
                message=f"慢查询数量较多（{slowlog_len}）",
                detail=detail,
                recommendation="关注慢查询增长趋势，排查业务命令",
            )

        return _make_check(
            name="慢查询检查",
            status="passed",
            message=f"慢查询数量正常（{slowlog_len}）",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="慢查询检查",
            status="error",
            message=f"慢查询检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接与权限",
        )


async def _check_redis_replication(connector: RedisConnector) -> dict:
    """复制检查：主从复制是否正常、复制延迟"""
    try:
        repl = await connector.get_replication_detail()
        role = repl.get("role", "unknown")

        detail = {
            "role": role,
            "connected_slaves": int(repl.get("connected_slaves", 0)),
        }

        # 如果是 master，检查从节点状态
        if role == "master":
            slaves_count = int(repl.get("connected_slaves", 0))
            detail["connected_slaves"] = slaves_count
            if slaves_count == 0:
                return _make_check(
                    name="复制检查",
                    status="warning",
                    message="当前为 master 但无连接的从节点",
                    detail=detail,
                    recommendation="如需高可用，建议配置至少一个从节点",
                )
            # 检查每个从节点状态
            offline_slaves = []
            for i in range(slaves_count):
                key = f"slave{i}"
                slave_info = repl.get(key, "")
                if slave_info and "online" not in str(slave_info):
                    offline_slaves.append(f"slave{i}")
            if offline_slaves:
                detail["offline_slaves"] = offline_slaves
                return _make_check(
                    name="复制检查",
                    status="critical",
                    message=f"以下从节点离线: {', '.join(offline_slaves)}",
                    detail=detail,
                    recommendation="检查从节点网络与进程状态",
                )
            return _make_check(
                name="复制检查",
                status="passed",
                message=f"主从复制正常（{slaves_count} 个从节点在线）",
                detail=detail,
                recommendation="",
            )

        # 如果是 slave，检查复制状态
        if role == "slave":
            master_link_status = repl.get("master_link_status", "")
            master_sync = int(repl.get("master_sync_in_progress", 0))
            slave_repl_offset = int(repl.get("slave_repl_offset", 0))
            master_repl_offset = int(repl.get("master_repl_offset", 0))

            detail.update({
                "master_host": repl.get("master_host", ""),
                "master_port": repl.get("master_port", 0),
                "master_link_status": master_link_status,
                "master_sync_in_progress": master_sync,
                "slave_repl_offset": slave_repl_offset,
                "master_repl_offset": master_repl_offset,
            })

            if master_link_status != "up":
                return _make_check(
                    name="复制检查",
                    status="critical",
                    message=f"与主节点连接异常（master_link_status={master_link_status}）",
                    detail=detail,
                    recommendation="检查主节点网络与认证配置",
                )

            # 计算复制延迟
            if master_repl_offset > 0:
                lag = master_repl_offset - slave_repl_offset
                detail["replication_lag_bytes"] = lag
                if lag > 1024 * 1024:  # >1MB
                    return _make_check(
                        name="复制检查",
                        status="warning",
                        message=f"复制延迟较大（{lag} 字节）",
                        detail=detail,
                        recommendation="检查网络带宽与从节点负载",
                    )

            return _make_check(
                name="复制检查",
                status="passed",
                message="从节点复制状态正常",
                detail=detail,
                recommendation="",
            )

        # 既不是 master 也不是 slave
        return _make_check(
            name="复制检查",
            status="passed",
            message=f"当前角色为 {role}，无需检查复制状态",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="复制检查",
            status="error",
            message=f"复制检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接与权限",
        )


async def _check_redis_cluster(connector: RedisConnector) -> dict:
    """集群检查：集群状态是否正常（如果是集群模式）"""
    try:
        server_info = await connector.get_server_info()
        redis_mode = server_info.get("redis_mode", "standalone")

        detail = {"redis_mode": redis_mode, "is_cluster": redis_mode == "cluster"}

        if redis_mode != "cluster":
            return _make_check(
                name="集群检查",
                status="passed",
                message=f"当前为 {redis_mode} 模式，无需集群检查",
                detail=detail,
                recommendation="",
            )

        cluster_info = await connector.get_cluster_info_detail()
        cluster_state = cluster_info.get("cluster_state", "unknown")
        slots_ok = int(cluster_info.get("cluster_slots_ok", 0))
        slots_assigned = int(cluster_info.get("cluster_slots_assigned", 0))
        slots_fail = int(cluster_info.get("cluster_slots_fail", 0))
        known_nodes = int(cluster_info.get("cluster_known_nodes", 0))

        detail.update({
            "cluster_state": cluster_state,
            "cluster_slots_ok": slots_ok,
            "cluster_slots_assigned": slots_assigned,
            "cluster_slots_fail": slots_fail,
            "cluster_known_nodes": known_nodes,
            "cluster_size": int(cluster_info.get("cluster_size", 0)),
        })

        if cluster_state != "ok" or slots_fail > 0:
            return _make_check(
                name="集群检查",
                status="critical",
                message=f"集群状态异常（state={cluster_state}, fail_slots={slots_fail}）",
                detail=detail,
                recommendation="检查集群节点状态，处理 fail 槽位",
            )

        return _make_check(
            name="集群检查",
            status="passed",
            message=f"集群状态正常（{known_nodes} 节点, {slots_ok}/{slots_assigned} 槽位）",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="集群检查",
            status="error",
            message=f"集群检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接与权限",
        )


async def _check_redis_config(connector: RedisConnector) -> dict:
    """配置检查：timeout、maxclients、appendonly 等关键配置项"""
    try:
        config = await connector.get_config("*")

        # 关注的关键配置项
        keys_of_interest = [
            "timeout",
            "maxclients",
            "appendonly",
            "appendfsync",
            "maxmemory",
            "maxmemory-policy",
            "slowlog-log-slower-than",
            "slowlog-max-len",
            "hash-max-ziplist-entries",
            "list-max-ziplist-size",
            "save",
        ]

        detail = {k: config.get(k, "") for k in keys_of_interest}

        issues = []

        # timeout 检查
        timeout = config.get("timeout", "0")
        try:
            timeout_val = int(timeout)
            if timeout_val == 0:
                issues.append(("warning", "timeout=0（不超时），可能导致空闲连接占用资源"))
        except (ValueError, TypeError):
            pass

        # maxclients 检查
        maxclients = config.get("maxclients", "0")
        try:
            mc_val = int(maxclients)
            if mc_val < 1000:
                issues.append(("warning", f"maxclients={mc_val} 偏小，可能在高并发下拒绝连接"))
        except (ValueError, TypeError):
            pass

        # appendonly 检查
        appendonly = config.get("appendonly", "no")
        if appendonly == "no":
            issues.append(("warning", "appendonly=no（未启用 AOF），数据安全性较低"))

        if any(s == "critical" for s, _ in issues):
            return _make_check(
                name="配置检查",
                status="critical",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="调整 Redis 关键配置项",
            )
        if issues:
            return _make_check(
                name="配置检查",
                status="warning",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="根据业务场景调整 timeout、appendonly 等配置",
            )

        return _make_check(
            name="配置检查",
            status="passed",
            message="关键配置项合理",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="配置检查",
            status="error",
            message=f"配置检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接与权限",
        )


async def _check_redis_keys(connector: RedisConnector) -> dict:
    """Key 检查：是否存在大 Key（>10MB）、Key 总数是否过多"""
    try:
        dbsize = await connector.get_dbsize()

        detail = {
            "total_keys": dbsize,
            "big_keys": [],
        }

        issues = []

        # Key 总数检查
        if dbsize > 10_000_000:
            issues.append(("warning", f"Key 总数过多（{dbsize}），可能影响性能"))
        elif dbsize > 1_000_000:
            issues.append(("warning", f"Key 总数较多（{dbsize}），建议关注"))

        # 大 Key 检查（采样扫描，避免阻塞）
        big_keys = []
        scanned_count = 0
        try:
            keys = await connector.scan_keys(pattern="*", count=500)
            # 限制扫描数量，避免阻塞 Redis
            sample_keys = keys[:500]
            scanned_count = len(sample_keys)
            for key in sample_keys:
                try:
                    mem = await connector.get_memory_usage(key)
                    if mem and mem > 10 * 1024 * 1024:  # >10MB
                        big_keys.append({"key": str(key)[:200], "memory_bytes": mem})
                        if len(big_keys) >= 10:
                            break
                except Exception:
                    continue
        except Exception as e:
            logger.debug("扫描大 Key 失败: %s", e)

        detail["big_keys"] = big_keys
        detail["scanned_keys"] = scanned_count

        if big_keys:
            issues.append(("critical", f"发现 {len(big_keys)} 个大 Key（>10MB）"))

        if any(s == "critical" for s, _ in issues):
            return _make_check(
                name="Key 检查",
                status="critical",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="拆分或删除大 Key，避免阻塞主线程",
            )
        if issues:
            return _make_check(
                name="Key 检查",
                status="warning",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="定期清理无用 Key，监控 Key 数量增长",
            )

        return _make_check(
            name="Key 检查",
            status="passed",
            message=f"Key 数量正常（{dbsize}），未发现大 Key",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="Key 检查",
            status="error",
            message=f"Key 检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 Redis 连接与权限",
        )


async def run_redis_diagnosis(connector: RedisConnector) -> list[dict]:
    """执行 Redis 全部诊断检查项"""
    checks = []
    try:
        checks.append(await _check_redis_connection(connector))
        checks.append(await _check_redis_memory(connector))
        checks.append(await _check_redis_persistence(connector))
        checks.append(await _check_redis_slowlog(connector))
        checks.append(await _check_redis_replication(connector))
        checks.append(await _check_redis_cluster(connector))
        checks.append(await _check_redis_config(connector))
        checks.append(await _check_redis_keys(connector))
    finally:
        await connector.close()
    return checks


# ── MySQL 诊断检查项 ───────────────────────────────────────

def _check_mysql_available() -> bool:
    """检查 pymysql 是否可用"""
    try:
        import pymysql  # noqa: F401
        return True
    except ImportError:
        return False


async def _check_mysql_connection(connector) -> dict:
    """连接检查：能否连接、连接数使用率"""
    if not _check_mysql_available():
        return _make_check(
            name="连接检查",
            status="skip",
            message="pymysql 未安装，跳过 MySQL 连接检查",
            detail={},
            recommendation="执行 pip install pymysql 以启用 MySQL 诊断",
        )

    try:
        test_result = await connector.test_connection()
        if not test_result.get("success"):
            return _make_check(
                name="连接检查",
                status="critical",
                message=f"无法连接 MySQL: {test_result.get('message', '')}",
                detail=test_result,
                recommendation="检查 MySQL 服务是否运行、网络是否通畅、认证信息是否正确",
            )

        # 获取连接数信息
        status = await connector.get_global_status()
        threads_connected = int(status.get("Threads_connected", 0))
        max_used = int(status.get("Max_used_connections", 0))

        variables = await connector.get_variables(like_pattern="max_connections")
        max_connections = int(variables.get("max_connections", 0))

        detail = {
            "threads_connected": threads_connected,
            "max_used_connections": max_used,
            "max_connections": max_connections,
            "version": test_result.get("version", ""),
        }

        if max_connections > 0:
            usage_percent = round(threads_connected / max_connections * 100, 2)
            detail["usage_percent"] = usage_percent
            if usage_percent >= 90:
                return _make_check(
                    name="连接检查",
                    status="critical",
                    message=f"连接数已接近上限（{threads_connected}/{max_connections}, {usage_percent}%）",
                    detail=detail,
                    recommendation="调大 max_connections 或优化业务连接池",
                )
            if usage_percent >= 70:
                return _make_check(
                    name="连接检查",
                    status="warning",
                    message=f"连接数使用率较高（{threads_connected}/{max_connections}, {usage_percent}%）",
                    detail=detail,
                    recommendation="关注连接数增长趋势",
                )

        return _make_check(
            name="连接检查",
            status="passed",
            message=f"连接正常，当前连接数 {threads_connected}/{max_connections}",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="连接检查",
            status="error",
            message=f"连接检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 MySQL 连接配置",
        )


async def _check_mysql_error_logs(instance_id: Optional[int]) -> dict:
    """错误日志检查：最近 24 小时错误数、是否有严重错误"""
    try:
        db = _get_db()
        conn = await db._get_conn()
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

        # 最近 24 小时错误数
        if instance_id is not None:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM log_entries "
                "WHERE instance_id = ? AND level IN ('ERROR', 'FATAL') AND timestamp >= ?",
                (instance_id, cutoff),
            )
        else:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM log_entries "
                "WHERE level IN ('ERROR', 'FATAL') AND timestamp >= ?",
                (cutoff,),
            )
        row = await cursor.fetchone()
        error_count = row["cnt"] if row else 0

        # 最近 24 小时 FATAL 数
        if instance_id is not None:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM log_entries "
                "WHERE instance_id = ? AND level = 'FATAL' AND timestamp >= ?",
                (instance_id, cutoff),
            )
        else:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM log_entries "
                "WHERE level = 'FATAL' AND timestamp >= ?",
                (cutoff,),
            )
        row = await cursor.fetchone()
        fatal_count = row["cnt"] if row else 0

        # 最近 5 条错误
        if instance_id is not None:
            cursor = await conn.execute(
                "SELECT timestamp, level, error_code, message FROM log_entries "
                "WHERE instance_id = ? AND level IN ('ERROR', 'FATAL') AND timestamp >= ? "
                "ORDER BY timestamp DESC LIMIT 5",
                (instance_id, cutoff),
            )
        else:
            cursor = await conn.execute(
                "SELECT timestamp, level, error_code, message FROM log_entries "
                "WHERE level IN ('ERROR', 'FATAL') AND timestamp >= ? "
                "ORDER BY timestamp DESC LIMIT 5",
                (cutoff,),
            )
        recent_errors = [dict(r) for r in await cursor.fetchall()]

        detail = {
            "error_count_24h": error_count,
            "fatal_count_24h": fatal_count,
            "recent_errors": recent_errors,
        }

        if fatal_count > 0:
            return _make_check(
                name="错误日志检查",
                status="critical",
                message=f"最近 24 小时发现 {fatal_count} 条 FATAL 错误，{error_count} 条 ERROR",
                detail=detail,
                recommendation="立即排查 FATAL 错误，可能影响服务可用性",
            )
        if error_count > 50:
            return _make_check(
                name="错误日志检查",
                status="warning",
                message=f"最近 24 小时错误数较多（{error_count}）",
                detail=detail,
                recommendation="分析错误模式，排查根因",
            )
        if error_count > 0:
            return _make_check(
                name="错误日志检查",
                status="warning",
                message=f"最近 24 小时发现 {error_count} 条错误",
                detail=detail,
                recommendation="关注错误日志，及时处理",
            )

        return _make_check(
            name="错误日志检查",
            status="passed",
            message="最近 24 小时无错误日志",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="错误日志检查",
            status="error",
            message=f"错误日志检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查数据库表是否已创建",
        )


async def _check_mysql_slow_queries(instance_id: Optional[int]) -> dict:
    """慢查询检查：慢查询数量、平均耗时"""
    try:
        db = _get_db()
        stats = await db.get_slow_query_stats(instance_id=instance_id)

        total = stats.get("total_count", 0)
        avg_time = stats.get("avg_query_time", 0)
        max_time = stats.get("max_query_time", 0)

        detail = {
            "total_count": total,
            "avg_query_time": avg_time,
            "max_query_time": max_time,
        }

        if total == 0:
            return _make_check(
                name="慢查询检查",
                status="passed",
                message="无慢查询记录",
                detail=detail,
                recommendation="",
            )

        if avg_time > 5:
            return _make_check(
                name="慢查询检查",
                status="critical",
                message=f"慢查询平均耗时过长（{avg_time}s，共 {total} 条）",
                detail=detail,
                recommendation="优化慢查询 SQL，添加合适索引",
            )
        if avg_time > 1:
            return _make_check(
                name="慢查询检查",
                status="warning",
                message=f"慢查询平均耗时较高（{avg_time}s，共 {total} 条）",
                detail=detail,
                recommendation="关注慢查询模式，逐步优化",
            )

        return _make_check(
            name="慢查询检查",
            status="passed",
            message=f"慢查询数量 {total}，平均耗时 {avg_time}s",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="慢查询检查",
            status="error",
            message=f"慢查询检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 slow_queries 表是否已创建",
        )


async def _check_mysql_replication(connector) -> dict:
    """复制检查：主从复制状态、延迟"""
    if not _check_mysql_available():
        return _make_check(
            name="复制检查",
            status="skip",
            message="pymysql 未安装，跳过 MySQL 复制检查",
            detail={},
            recommendation="执行 pip install pymysql 以启用 MySQL 诊断",
        )

    try:
        master_status = await connector.get_master_status()
        slave_status = await connector.get_slave_status()

        detail = {
            "is_master": master_status is not None,
            "is_slave": slave_status is not None,
        }

        # 既不是 master 也不是 slave
        if master_status is None and slave_status is None:
            return _make_check(
                name="复制检查",
                status="passed",
                message="单机实例，无需检查复制状态",
                detail=detail,
                recommendation="",
            )

        if slave_status:
            io_running = slave_status.get("Slave_IO_Running", "No") == "Yes"
            sql_running = slave_status.get("Slave_SQL_Running", "No") == "Yes"
            seconds_behind = slave_status.get("Seconds_Behind_Master")

            detail.update({
                "master_host": slave_status.get("Master_Host", ""),
                "io_running": io_running,
                "sql_running": sql_running,
                "seconds_behind_master": seconds_behind,
                "last_io_error": slave_status.get("Last_IO_Error", ""),
                "last_sql_error": slave_status.get("Last_SQL_Error", ""),
            })

            if not io_running or not sql_running:
                return _make_check(
                    name="复制检查",
                    status="critical",
                    message=f"复制线程异常（IO: {io_running}, SQL: {sql_running}）",
                    detail=detail,
                    recommendation="检查复制线程状态与错误信息",
                )

            if seconds_behind is not None and seconds_behind > 3600:
                return _make_check(
                    name="复制检查",
                    status="critical",
                    message=f"复制延迟过大（{seconds_behind}s）",
                    detail=detail,
                    recommendation="检查从节点负载与网络状况",
                )
            if seconds_behind is not None and seconds_behind > 300:
                return _make_check(
                    name="复制检查",
                    status="warning",
                    message=f"复制延迟较大（{seconds_behind}s）",
                    detail=detail,
                    recommendation="关注复制延迟趋势",
                )

            return _make_check(
                name="复制检查",
                status="passed",
                message=f"从节点复制正常，延迟 {seconds_behind}s",
                detail=detail,
                recommendation="",
            )

        # 仅 master
        return _make_check(
            name="复制检查",
            status="passed",
            message="主节点复制状态正常",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="复制检查",
            status="error",
            message=f"复制检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 MySQL 连接与权限",
        )


async def _check_mysql_metrics(connector) -> dict:
    """监控指标检查：QPS、连接数、Buffer Pool 命中率"""
    if not _check_mysql_available():
        return _make_check(
            name="监控指标检查",
            status="skip",
            message="pymysql 未安装，跳过 MySQL 监控指标检查",
            detail={},
            recommendation="执行 pip install pymysql 以启用 MySQL 诊断",
        )

    try:
        status = await connector.get_global_status()
        if not status:
            return _make_check(
                name="监控指标检查",
                status="error",
                message="无法获取 MySQL 状态指标",
                detail={},
                recommendation="检查 MySQL 连接与权限",
            )

        qps = float(status.get("QPS", 0))
        threads_connected = int(status.get("Threads_connected", 0))
        threads_running = int(status.get("Threads_running", 0))
        bp_hit_rate = float(status.get("Buffer_pool_hit_rate", 100))
        slow_queries = int(status.get("Slow_queries", 0))

        detail = {
            "qps": qps,
            "threads_connected": threads_connected,
            "threads_running": threads_running,
            "buffer_pool_hit_rate": bp_hit_rate,
            "slow_queries": slow_queries,
        }

        issues = []

        if bp_hit_rate < 90:
            issues.append(("critical", f"Buffer Pool 命中率过低（{bp_hit_rate}%）"))
        elif bp_hit_rate < 95:
            issues.append(("warning", f"Buffer Pool 命中率偏低（{bp_hit_rate}%）"))

        if threads_running > 100:
            issues.append(("warning", f"运行线程数较多（{threads_running}）"))

        if any(s == "critical" for s, _ in issues):
            return _make_check(
                name="监控指标检查",
                status="critical",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="调大 innodb_buffer_pool_size，优化查询",
            )
        if issues:
            return _make_check(
                name="监控指标检查",
                status="warning",
                message="; ".join(m for _, m in issues),
                detail=detail,
                recommendation="关注监控指标趋势",
            )

        return _make_check(
            name="监控指标检查",
            status="passed",
            message=f"QPS={qps}, 连接数={threads_connected}, BP命中率={bp_hit_rate}%",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="监控指标检查",
            status="error",
            message=f"监控指标检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查 MySQL 连接与权限",
        )


async def _check_mysql_alerts(instance_id: Optional[int]) -> dict:
    """告警检查：是否有未处理的告警"""
    try:
        db = _get_db()
        conn = await db._get_conn()

        # 检查 alert_history 表是否存在
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alert_history'"
        )
        if await cursor.fetchone() is None:
            return _make_check(
                name="告警检查",
                status="passed",
                message="告警系统未启用",
                detail={},
                recommendation="",
            )

        # 查询 firing 状态的告警
        if instance_id is not None:
            # 通过 alert_rules 关联实例（如有 instance_id 字段则用，否则全部）
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM alert_history WHERE status = 'firing'"
            )
        else:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM alert_history WHERE status = 'firing'"
            )
        row = await cursor.fetchone()
        firing_count = row["cnt"] if row else 0

        # 按级别统计
        cursor = await conn.execute(
            "SELECT level, COUNT(*) as count FROM alert_history "
            "WHERE status = 'firing' GROUP BY level"
        )
        by_level = [dict(r) for r in await cursor.fetchall()]

        detail = {
            "firing_count": firing_count,
            "by_level": by_level,
        }

        # 检查 critical 级别
        critical_count = sum(r["count"] for r in by_level if r.get("level") == "critical")

        if critical_count > 0:
            return _make_check(
                name="告警检查",
                status="critical",
                message=f"有 {critical_count} 条 critical 级别未处理告警",
                detail=detail,
                recommendation="立即处理 critical 告警",
            )
        if firing_count > 0:
            return _make_check(
                name="告警检查",
                status="warning",
                message=f"有 {firing_count} 条未处理告警",
                detail=detail,
                recommendation="及时确认并处理告警",
            )

        return _make_check(
            name="告警检查",
            status="passed",
            message="无未处理告警",
            detail=detail,
            recommendation="",
        )
    except Exception as e:
        return _make_check(
            name="告警检查",
            status="error",
            message=f"告警检查异常: {str(e)[:200]}",
            detail={},
            recommendation="检查告警表是否正常",
        )


async def run_mysql_diagnosis(connector, instance_id: Optional[int]) -> list[dict]:
    """执行 MySQL 全部诊断检查项"""
    checks = []
    checks.append(await _check_mysql_connection(connector))
    checks.append(await _check_mysql_error_logs(instance_id))
    checks.append(await _check_mysql_slow_queries(instance_id))
    checks.append(await _check_mysql_replication(connector))
    checks.append(await _check_mysql_metrics(connector))
    checks.append(await _check_mysql_alerts(instance_id))

    # 关闭连接
    try:
        await connector.close()
    except Exception:
        pass

    return checks


# ── 诊断报告生成 ───────────────────────────────────────────

def _compute_summary(checks: list[dict]) -> dict:
    """计算检查项汇总"""
    summary = {"passed": 0, "warning": 0, "critical": 0, "error": 0, "total": 0}
    for c in checks:
        status = c.get("status", "passed")
        if status in summary:
            summary[status] += 1
        summary["total"] += 1
    return summary


def _compute_health_score(summary: dict) -> int:
    """计算健康分（passed=100, 每个 warning -5, 每个 critical -15, 每个 error -20）"""
    score = 100
    score -= summary.get("warning", 0) * 5
    score -= summary.get("critical", 0) * 15
    score -= summary.get("error", 0) * 20
    return max(0, min(100, score))


def _compute_overall_status(summary: dict) -> str:
    """计算总体状态"""
    if summary.get("critical", 0) > 0 or summary.get("error", 0) > 0:
        return "critical"
    if summary.get("warning", 0) > 0:
        return "warning"
    return "healthy"


async def _save_report(report: dict):
    """保存诊断报告到数据库"""
    db = _get_db()
    conn = await db._get_conn()
    now = datetime.now().isoformat()

    await conn.execute(
        """INSERT INTO diagnosis_reports
           (id, db_type, instance_id, instance_name, started_at, completed_at,
            duration_ms, checks_json, summary_json, health_score, overall_status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            report["id"],
            report["db_type"],
            report.get("instance_id"),
            report.get("instance_name"),
            report["started_at"],
            report.get("completed_at"),
            report.get("duration_ms", 0),
            json.dumps(report.get("checks", []), ensure_ascii=False),
            json.dumps(report.get("summary", {}), ensure_ascii=False),
            report.get("health_score", 0),
            report.get("overall_status", "healthy"),
            now,
        ),
    )
    await conn.commit()


async def _load_report(report_id: str) -> Optional[dict]:
    """从数据库加载诊断报告"""
    db = _get_db()
    conn = await db._get_conn()

    cursor = await conn.execute(
        "SELECT * FROM diagnosis_reports WHERE id = ?",
        (report_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    item = dict(row)
    try:
        item["checks"] = json.loads(item.get("checks_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        item["checks"] = []
    try:
        item["summary"] = json.loads(item.get("summary_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        item["summary"] = {}

    # 移除内部字段
    item.pop("checks_json", None)
    item.pop("summary_json", None)
    return item


# ── API 端点 ───────────────────────────────────────────────

@router.post("/run")
async def run_diagnosis(body: RunDiagnosisRequest = Body(...)):
    """执行一键诊断

    参数:
        db_type: mysql / redis / all
        instance_id: 可选，指定实例 ID
    """
    await _ensure_tables()

    db_type = (body.db_type or "all").lower()
    if db_type not in ("mysql", "redis", "all"):
        raise HTTPException(status_code=400, detail="db_type 必须为 mysql / redis / all")

    diagnosis_id = str(uuid.uuid4())
    started_at = datetime.now()
    started_at_iso = started_at.isoformat()
    start_ts = time.time()

    all_checks: list[dict] = []
    instance_name_parts: list[str] = []

    # 执行 Redis 诊断
    if db_type in ("redis", "all"):
        redis_connector = _get_redis_connector(body.instance_id)
        if redis_connector is not None:
            redis_checks = await run_redis_diagnosis(redis_connector)
            # 标注检查项所属的数据库类型
            for c in redis_checks:
                c["db_type"] = "redis"
            all_checks.extend(redis_checks)
            inst_info = await _get_instance_info(body.instance_id, "redis")
            instance_name_parts.append(f"Redis:{inst_info['name']}")
        else:
            all_checks.append(_make_check(
                name="Redis 诊断",
                status="skip",
                message="未找到可用的 Redis 实例",
                detail={},
                recommendation="请先注册 Redis 实例",
            ))

    # 执行 MySQL 诊断
    if db_type in ("mysql", "all"):
        mysql_connector = _get_mysql_connector(body.instance_id)
        if mysql_connector is not None:
            mysql_checks = await run_mysql_diagnosis(mysql_connector, body.instance_id)
            for c in mysql_checks:
                c["db_type"] = "mysql"
            all_checks.extend(mysql_checks)
            inst_info = await _get_instance_info(body.instance_id, "mysql")
            instance_name_parts.append(f"MySQL:{inst_info['name']}")
        else:
            all_checks.append(_make_check(
                name="MySQL 诊断",
                status="skip",
                message="未找到可用的 MySQL 实例",
                detail={},
                recommendation="请先注册 MySQL 实例",
            ))

    completed_at = datetime.now()
    duration_ms = int((time.time() - start_ts) * 1000)

    summary = _compute_summary(all_checks)
    health_score = _compute_health_score(summary)
    overall_status = _compute_overall_status(summary)

    report = {
        "id": diagnosis_id,
        "db_type": db_type,
        "instance_id": body.instance_id,
        "instance_name": " | ".join(instance_name_parts) if instance_name_parts else "默认实例",
        "started_at": started_at_iso,
        "completed_at": completed_at.isoformat(),
        "duration_ms": duration_ms,
        "checks": all_checks,
        "summary": summary,
        "health_score": health_score,
        "overall_status": overall_status,
    }

    # 保存到数据库
    try:
        await _save_report(report)
    except Exception as e:
        logger.warning("保存诊断报告失败: %s", e)

    return report


@router.get("/history")
async def get_diagnosis_history(
    db_type: Optional[str] = Query(None, description="按数据库类型过滤: mysql/redis/all"),
    instance_id: Optional[int] = Query(None, description="按实例 ID 过滤"),
    limit: int = Query(50, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """获取诊断历史记录"""
    await _ensure_tables()

    db = _get_db()
    conn = await db._get_conn()

    conditions = []
    params: list[Any] = []

    if db_type is not None:
        conditions.append("db_type = ?")
        params.append(db_type)
    if instance_id is not None:
        conditions.append("instance_id = ?")
        params.append(instance_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # 查询总数
    cursor = await conn.execute(
        f"SELECT COUNT(*) as cnt FROM diagnosis_reports WHERE {where_clause}",
        params,
    )
    total_row = await cursor.fetchone()
    total = total_row["cnt"] if total_row else 0

    # 查询数据
    query_params = params + [limit, offset]
    cursor = await conn.execute(
        f"""SELECT id, db_type, instance_id, instance_name, started_at, completed_at,
                  duration_ms, health_score, overall_status, created_at
            FROM diagnosis_reports
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?""",
        query_params,
    )
    rows = await cursor.fetchall()
    items = [dict(row) for row in rows]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{diagnosis_id}")
async def get_diagnosis_detail(diagnosis_id: str):
    """获取诊断详情"""
    await _ensure_tables()

    report = await _load_report(diagnosis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="诊断报告不存在")

    return report
