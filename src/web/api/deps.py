"""FastAPI 依赖注入模块 - 统一数据库/连接器获取

将各 API 模块中重复的 `_get_db()` 单例获取逻辑和连接器获取逻辑集中到此模块。
- Phase 3: 统一 DatabaseManager 单例
- Phase 4: 统一 MySQL/Redis 连接器获取
"""
import json as _json
import sqlite3
from typing import Optional

from src.collector.mysql_connector import MySQLConnector
from src.collector.redis_connector import RedisConnector
from src.config import Config
from src.storage.database import DatabaseManager

# 模块级单例：整个应用共享同一个 DatabaseManager
_db_instance: DatabaseManager | None = None


def get_db() -> DatabaseManager:
    """获取 DatabaseManager 单例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance


# ── 连接器获取 ──────────────────────────────────────────────


def _query_default_instance(db_type: str) -> Optional[dict]:
    """从数据库查询指定类型的默认实例凭据

    Args:
        db_type: "redis" / "mysql"；mysql 同时匹配 db_type IS NULL（兼容旧数据）

    Returns: {"host", "port", "credentials"} 或 None
    """
    try:
        config = Config()
        db_path = config.get("storage", "db_path", default="./data/logs.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        if db_type == "mysql":
            cursor = conn.execute(
                "SELECT id, host, port, credentials FROM instances "
                "WHERE (db_type = 'mysql' OR db_type IS NULL) AND credentials IS NOT NULL "
                "ORDER BY id DESC LIMIT 1"
            )
        else:
            cursor = conn.execute(
                "SELECT id, host, port, credentials FROM instances "
                "WHERE db_type = 'redis' AND credentials IS NOT NULL "
                "ORDER BY id DESC LIMIT 1"
            )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def get_redis_connector(instance_id: Optional[int] = None) -> Optional[RedisConnector]:
    """获取 Redis 连接器

    优先级：
    1. 指定 instance_id 时，通过 RedisConnector.get_instance_connection 获取
    2. 从数据库查找最近的 Redis 实例凭据创建连接
    3. 兜底：返回默认 RedisConnector()（localhost:6379）
    """
    if instance_id is not None:
        connector = RedisConnector.get_instance_connection(instance_id)
        if connector:
            return connector

    row = _query_default_instance("redis")
    if row:
        password, username, ssl = None, None, False
        try:
            creds = _json.loads(row["credentials"])
            password = creds.get("password")
            username = creds.get("username")
            ssl = creds.get("ssl", False)
        except (_json.JSONDecodeError, TypeError):
            pass
        return RedisConnector(
            host=row["host"] or "localhost",
            port=row["port"] or 6379,
            password=password,
            username=username,
            ssl=ssl,
        )

    return RedisConnector()


def get_mysql_connector(instance_id: Optional[int] = None) -> Optional[MySQLConnector]:
    """获取 MySQL 连接器

    优先级：
    1. 指定 instance_id 时，通过 MySQLConnector.get_instance_connection 获取
    2. 从数据库查找最近的 MySQL 实例凭据创建连接
    3. 兜底：返回默认 MySQLConnector()（localhost:3306, root）
    """
    if instance_id is not None:
        connector = MySQLConnector.get_instance_connection(instance_id)
        if connector:
            return connector

    row = _query_default_instance("mysql")
    if row:
        user, password = "root", ""
        try:
            creds = _json.loads(row["credentials"])
            user = creds.get("user", "root")
            password = creds.get("password", "")
        except (_json.JSONDecodeError, TypeError):
            pass
        return MySQLConnector(
            host=row["host"] or "localhost",
            port=row["port"] or 3306,
            user=user,
            password=password,
        )

    return MySQLConnector()
