"""Redis 实时监控 API

端点:
- GET /api/redis/status     — 实时指标概览
- GET /api/redis/clients    — 客户端连接列表
- GET /api/redis/replication — 复制状态
- GET /api/redis/persistence — 持久化状态
- GET /api/redis/config     — 配置信息
- GET /api/redis/latency    — 延迟事件
- POST /api/redis/test-connection — 测试连接
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from src.collector.redis_connector import RedisConnector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/redis", tags=["Redis 监控"])


def _get_connector(instance_id: Optional[int] = None) -> Optional[RedisConnector]:
    """根据 instance_id 获取 Redis 连接器"""
    if instance_id is not None:
        connector = RedisConnector.get_instance_connection(instance_id)
        if connector:
            return connector

    # 默认：尝试从数据库找第一个 Redis 实例
    try:
        import sqlite3
        import json as _json
        from src.config import Config
        config = Config()
        db_path = config.get("storage", "db_path", default="./data/logs.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, host, port, credentials FROM instances WHERE db_type = 'redis' AND credentials IS NOT NULL ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            password, username, ssl = None, None, False
            try:
                creds = _json.loads(row['credentials'])
                password = creds.get('password')
                username = creds.get('username')
                ssl = creds.get('ssl', False)
            except (_json.JSONDecodeError, TypeError):
                pass
            return RedisConnector(
                host=row['host'] or 'localhost',
                port=row['port'] or 6379,
                password=password,
                username=username,
                ssl=ssl,
            )
    except Exception:
        pass

    # 最终兜底
    return RedisConnector()


@router.get("/status")
async def get_redis_status(instance_id: Optional[int] = Query(None)):
    """获取 Redis 实时状态指标"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        metrics = await connector.get_metrics()
        if not metrics:
            return {"connected": False, "error": "无法获取 Redis 指标"}

        # 添加连接状态
        metrics["connected"] = True

        # 计算内存使用率
        memory = metrics.get("memory", {})
        used = memory.get("used_memory", 0)
        maxmem = memory.get("maxmemory", 0)
        if maxmem > 0:
            memory["usage_percent"] = round(used / maxmem * 100, 2)
        else:
            memory["usage_percent"] = None  # 未设置 maxmemory

        # 连接使用率
        clients = metrics.get("clients", {})
        maxc = clients.get("maxclients", 0)
        if maxc > 0:
            clients["usage_percent"] = round(clients.get("connected", 0) / maxc * 100, 2)

        return metrics
    except Exception as e:
        return {"connected": False, "error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/clients")
async def get_redis_clients(instance_id: Optional[int] = Query(None)):
    """获取客户端连接列表"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        clients = await connector.get_client_list()
        info = await connector.get_clients_info()
        return {
            "total": len(clients),
            "connected_clients": info.get("connected_clients", 0),
            "blocked_clients": info.get("blocked_clients", 0),
            "maxclients": info.get("maxclients", 0),
            "clients": clients[:100],  # 限制返回数量
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/replication")
async def get_redis_replication(instance_id: Optional[int] = Query(None)):
    """获取复制状态"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        repl = await connector.get_replication_detail()
        role = repl.get('role', 'unknown')
        result = {
            "role": role,
            "is_master": role == 'master',
            "is_slave": role == 'slave',
            "connected_slaves": repl.get('connected_slaves', 0),
        }

        if role == 'slave':
            result.update({
                "master_host": repl.get('master_host', ''),
                "master_port": repl.get('master_port', 0),
                "master_link_status": repl.get('master_link_status', ''),
                "master_sync_in_progress": repl.get('master_sync_in_progress', 0),
                "slave_read_only": repl.get('slave_read_only', 0),
                "slave_repl_offset": repl.get('slave_repl_offset', 0),
            })
        elif role == 'master':
            # 解析从节点详情
            slaves = []
            for i in range(result['connected_slaves']):
                key = f'slave{i}'
                slave_info = repl.get(key, '')
                if slave_info:
                    slaves.append({"id": i, "info": slave_info})
            result['slaves'] = slaves

        return result
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/persistence")
async def get_redis_persistence(instance_id: Optional[int] = Query(None)):
    """获取持久化状态"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        info = await connector.get_persistence_info()
        return {
            "rdb": {
                "last_save_time": info.get('rdb_last_save_time', 0),
                "changes_since_last_save": info.get('rdb_changes_since_last_save', 0),
                "bgsave_in_progress": info.get('rdb_bgsave_in_progress', 0),
                "last_bgsave_status": info.get('rdb_last_bgsave_status', ''),
                "last_bgsave_time_sec": info.get('rdb_last_bgsave_time_sec', 0),
                "current_cow_size": info.get('rdb_last_cow_size', 0),
            },
            "aof": {
                "enabled": info.get('aof_enabled', 0),
                "rewrite_in_progress": info.get('aof_rewrite_in_progress', 0),
                "last_rewrite_status": info.get('aof_last_write_status', ''),
                "current_size": info.get('aof_current_size', 0),
                "base_size": info.get('aof_base_size', 0),
                "rewrite_scheduled": info.get('aof_rewrite_scheduled', 0),
            },
            "loading": info.get('loading', 0),
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/config")
async def get_redis_config(
    instance_id: Optional[int] = Query(None),
    pattern: str = Query("*"),
):
    """获取 Redis 配置"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        config = await connector.get_config(pattern)
        return {"config": config}
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.get("/latency")
async def get_redis_latency(instance_id: Optional[int] = Query(None)):
    """获取延迟事件"""
    connector = _get_connector(instance_id)
    if not connector:
        return {"error": "无法创建 Redis 连接器"}

    try:
        latest = await connector.get_latency_latest()
        events = await connector.get_latency_events()
        return {
            "latest": latest,
            "event_names": events,
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        await connector.close()


@router.post("/test-connection")
async def test_redis_connection(
    host: str = Query("localhost"),
    port: int = Query(6379),
    password: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    ssl: bool = Query(False),
):
    """测试 Redis 连接"""
    connector = RedisConnector(
        host=host,
        port=port,
        password=password,
        username=username,
        ssl=ssl,
    )
    try:
        result = await connector.test_connection()
        return result
    finally:
        await connector.close()
