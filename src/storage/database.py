"""SQLite 异步存储模块"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from src.config import Config


class DatabaseManager:
    """SQLite 数据库管理器"""

    def __init__(self):
        Config.load()
        config = Config()
        self.db_path = config.get("storage", "db_path", default="./data/logs.db")
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """获取数据库连接"""
        if self._conn is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                Path(db_dir).mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    async def close(self):
        """关闭数据库连接"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def initialize(self):
        """创建表和索引"""
        conn = await self._get_conn()

        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                log_path TEXT NOT NULL,
                host TEXT NOT NULL DEFAULT 'localhost',
                port INTEGER NOT NULL DEFAULT 3306,
                user TEXT NOT NULL DEFAULT 'root',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                error_code TEXT,
                thread_id TEXT,
                category TEXT DEFAULT 'other',
                message TEXT,
                raw_line TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instance_id) REFERENCES instances(id)
            );

            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER NOT NULL,
                time_range_start TEXT NOT NULL,
                time_range_end TEXT NOT NULL,
                category TEXT NOT NULL,
                summary TEXT,
                suggestion TEXT,
                severity TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instance_id) REFERENCES instances(id)
            );

            CREATE TABLE IF NOT EXISTS critical_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER NOT NULL,
                log_entry_id INTEGER,
                alert_type TEXT NOT NULL,
                llm_suggestion TEXT,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instance_id) REFERENCES instances(id),
                FOREIGN KEY (log_entry_id) REFERENCES log_entries(id)
            );

            CREATE INDEX IF NOT EXISTS idx_log_entries_instance_id
                ON log_entries(instance_id);
            CREATE INDEX IF NOT EXISTS idx_log_entries_timestamp
                ON log_entries(timestamp);
            CREATE INDEX IF NOT EXISTS idx_log_entries_level
                ON log_entries(level);
            CREATE INDEX IF NOT EXISTS idx_log_entries_instance_timestamp
                ON log_entries(instance_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_log_entries_instance_level
                ON log_entries(instance_id, level);
            CREATE INDEX IF NOT EXISTS idx_log_entries_category
                ON log_entries(category);

            CREATE INDEX IF NOT EXISTS idx_analysis_results_instance_id
                ON analysis_results(instance_id);
            CREATE INDEX IF NOT EXISTS idx_analysis_results_time_range
                ON analysis_results(time_range_start, time_range_end);
            CREATE INDEX IF NOT EXISTS idx_analysis_results_category
                ON analysis_results(category);

            CREATE TABLE IF NOT EXISTS monitor_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                collected_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_critical_alerts_instance_id
                ON critical_alerts(instance_id);
            CREATE INDEX IF NOT EXISTS idx_critical_alerts_is_read
                ON critical_alerts(is_read);
            CREATE INDEX IF NOT EXISTS idx_critical_alerts_created_at
                ON critical_alerts(created_at);

            CREATE INDEX IF NOT EXISTS idx_monitor_metrics_instance_metric
                ON monitor_metrics(instance_id, metric_name);
            CREATE INDEX IF NOT EXISTS idx_monitor_metrics_collected_at
                ON monitor_metrics(collected_at);
        """)

        await conn.commit()

        # 额外表（可能已存在，单独创建以兼容旧数据库）
        try:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS slow_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER,
                timestamp TEXT NOT NULL,
                user TEXT NOT NULL DEFAULT '',
                host TEXT NOT NULL DEFAULT '',
                query_time REAL NOT NULL DEFAULT 0,
                lock_time REAL NOT NULL DEFAULT 0,
                rows_sent INTEGER NOT NULL DEFAULT 0,
                rows_examined INTEGER NOT NULL DEFAULT 0,
                sql_text TEXT,
                sql_hash TEXT,
                sql_type TEXT NOT NULL DEFAULT 'OTHER',
                sql_template TEXT,
                slow_score REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instance_id) REFERENCES instances(id)
            );

            CREATE TABLE IF NOT EXISTS slow_query_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER,
                time_range_start TEXT NOT NULL,
                time_range_end TEXT NOT NULL,
                summary TEXT,
                suggestions_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instance_id) REFERENCES instances(id)
            );

            CREATE INDEX IF NOT EXISTS idx_slow_queries_instance_id
                ON slow_queries(instance_id);
            CREATE INDEX IF NOT EXISTS idx_slow_queries_timestamp
                ON slow_queries(timestamp);
            CREATE INDEX IF NOT EXISTS idx_slow_queries_sql_hash
                ON slow_queries(sql_hash);
            CREATE INDEX IF NOT EXISTS idx_slow_queries_sql_type
                ON slow_queries(sql_type);
            CREATE INDEX IF NOT EXISTS idx_slow_queries_query_time
                ON slow_queries(query_time);
            CREATE INDEX IF NOT EXISTS idx_slow_queries_slow_score
                ON slow_queries(slow_score);
            CREATE INDEX IF NOT EXISTS idx_slow_queries_instance_timestamp
                ON slow_queries(instance_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_slow_query_analysis_instance_id
                ON slow_query_analysis(instance_id);
            CREATE INDEX IF NOT EXISTS idx_slow_query_analysis_time_range
                ON slow_query_analysis(time_range_start, time_range_end);
        """)
        except Exception:
            pass  # 忽略额外表的创建错误

        await conn.commit()

    async def insert_log_entries(self, entries: list[dict]):
        """批量插入日志条目"""
        if not entries:
            return

        conn = await self._get_conn()
        now = datetime.now().isoformat()

        rows = []
        for entry in entries:
            rows.append((
                entry.get("instance_id"),
                entry.get("timestamp", ""),
                entry.get("level", ""),
                entry.get("error_code"),
                entry.get("thread_id"),
                entry.get("category", "other"),
                entry.get("message"),
                entry.get("raw_line"),
                entry.get("created_at", now),
            ))

        await conn.executemany(
            """INSERT INTO log_entries
               (instance_id, timestamp, level, error_code, thread_id, category, message, raw_line, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await conn.commit()

    async def query_logs(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
        level=None,
        keyword=None,
        limit=100,
        offset=0,
    ) -> list[dict]:
        """多条件查询日志"""
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if level is not None:
            conditions.append("level = ?")
            params.append(level)
        if keyword is not None:
            conditions.append("message LIKE ?")
            params.append(f"%{keyword}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        params.extend([limit, offset])

        cursor = await conn.execute(
            f"""SELECT id, instance_id, timestamp, level, error_code,
                       thread_id, message, raw_line, created_at
                FROM log_entries
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?""",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def count_logs(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
        level=None,
        keyword=None,
    ) -> int:
        """统计符合条件的日志总数"""
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if level is not None:
            conditions.append("level = ?")
            params.append(level)
        if keyword is not None:
            conditions.append("message LIKE ?")
            params.append(f"%{keyword}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"SELECT COUNT(*) as cnt FROM log_entries WHERE {where_clause}",
            params,
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def insert_analysis_result(self, result: dict):
        """插入分析结果"""
        conn = await self._get_conn()
        now = datetime.now().isoformat()

        await conn.execute(
            """INSERT INTO analysis_results
               (instance_id, time_range_start, time_range_end, category,
                summary, suggestion, severity, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.get("instance_id"),
                result.get("time_range_start", ""),
                result.get("time_range_end", ""),
                result.get("category", ""),
                result.get("summary"),
                result.get("suggestion"),
                result.get("severity"),
                result.get("created_at", now),
            ),
        )
        await conn.commit()

    async def query_analysis(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
    ) -> list[dict]:
        """查询分析结果"""
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("time_range_start >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("time_range_end <= ?")
            params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"""SELECT id, instance_id, time_range_start, time_range_end,
                       category, summary, suggestion, severity, created_at
                FROM analysis_results
                WHERE {where_clause}
                ORDER BY created_at DESC""",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def insert_critical_alert(self, alert: dict):
        """插入关键告警"""
        conn = await self._get_conn()
        now = datetime.now().isoformat()

        await conn.execute(
            """INSERT INTO critical_alerts
               (instance_id, log_entry_id, alert_type, llm_suggestion, is_read, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                alert.get("instance_id"),
                alert.get("log_entry_id"),
                alert.get("alert_type", ""),
                alert.get("llm_suggestion"),
                int(alert.get("is_read", False)),
                alert.get("created_at", now),
            ),
        )
        await conn.commit()

    async def query_alerts(self, is_read=None, limit=50) -> list[dict]:
        """查询告警"""
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if is_read is not None:
            conditions.append("is_read = ?")
            params.append(int(is_read))

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        cursor = await conn.execute(
            f"""SELECT id, instance_id, log_entry_id, alert_type,
                       llm_suggestion, is_read, created_at
                FROM critical_alerts
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ?""",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def mark_alert_read(self, alert_id):
        """标记告警已读"""
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE critical_alerts SET is_read = 1 WHERE id = ?",
            (alert_id,),
        )
        await conn.commit()

    async def get_stats(self) -> dict:
        """获取统计信息（各实例日志数量、告警数量等）"""
        conn = await self._get_conn()

        # 各实例日志数量
        cursor = await conn.execute(
            """SELECT instance_id, COUNT(*) as log_count
               FROM log_entries
               GROUP BY instance_id"""
        )
        log_counts = {row["instance_id"]: row["log_count"] for row in await cursor.fetchall()}

        # 各实例告警数量
        cursor = await conn.execute(
            """SELECT instance_id, COUNT(*) as alert_count
               FROM critical_alerts
               GROUP BY instance_id"""
        )
        alert_counts = {row["instance_id"]: row["alert_count"] for row in await cursor.fetchall()}

        # 未读告警总数
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM critical_alerts WHERE is_read = 0"
        )
        unread_row = await cursor.fetchone()
        unread_alerts = unread_row["cnt"] if unread_row else 0

        # 分析结果总数
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM analysis_results")
        analysis_row = await cursor.fetchone()
        analysis_count = analysis_row["cnt"] if analysis_row else 0

        # 实例信息
        cursor = await conn.execute("SELECT id, name, host, port FROM instances")
        instances = [dict(row) for row in await cursor.fetchall()]

        # 合并统计
        instance_stats = []
        for inst in instances:
            iid = inst["id"]
            instance_stats.append({
                **inst,
                "log_count": log_counts.get(iid, 0),
                "alert_count": alert_counts.get(iid, 0),
            })

        # 对没有日志但有告警的实例也包含进来
        for iid in alert_counts:
            if iid not in log_counts:
                already = any(s["id"] == iid for s in instance_stats)
                if not already:
                    instance_stats.append({
                        "id": iid,
                        "log_count": log_counts.get(iid, 0),
                        "alert_count": alert_counts.get(iid, 0),
                    })

        return {
            "instances": instance_stats,
            "total_logs": sum(log_counts.values()),
            "total_alerts": sum(alert_counts.values()),
            "unread_alerts": unread_alerts,
            "analysis_count": analysis_count,
        }

    async def get_error_distribution(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
        levels=None,
    ) -> dict:
        """获取错误分布（按类别、按级别）

        Args:
            levels: 可选的级别过滤列表，如 ["ERROR", "WARNING", "FATAL"]
        """
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if levels:
            placeholders = ",".join("?" for _ in levels)
            conditions.append(f"level IN ({placeholders})")
            params.extend(levels)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 按级别分布
        cursor = await conn.execute(
            f"""SELECT level, COUNT(*) as count
                FROM log_entries
                WHERE {where_clause}
                GROUP BY level
                ORDER BY count DESC""",
            params,
        )
        by_level = [dict(row) for row in await cursor.fetchall()]

        # 按错误码分布（error_code 不为空时）
        code_conditions = conditions.copy()
        code_params = params.copy()
        code_conditions.append("error_code IS NOT NULL")
        code_conditions.append("error_code != ''")
        code_where = " AND ".join(code_conditions)

        cursor = await conn.execute(
            f"""SELECT error_code, COUNT(*) as count
                FROM log_entries
                WHERE {code_where}
                GROUP BY error_code
                ORDER BY count DESC
                LIMIT 20""",
            code_params,
        )
        by_error_code = [dict(row) for row in await cursor.fetchall()]

        # 按日志类别分布（从 log_entries 的 category 字段）
        cursor = await conn.execute(
            f"""SELECT category, COUNT(*) as count
                FROM log_entries
                WHERE {where_clause}
                GROUP BY category
                ORDER BY count DESC""",
            params,
        )
        by_category = [dict(row) for row in await cursor.fetchall()]

        return {
            "by_level": by_level,
            "by_error_code": by_error_code,
            "by_category": by_category,
        }

    async def get_error_trend(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
        interval="hour",
        levels=None,
    ) -> list[dict]:
        """获取错误趋势

        Args:
            levels: 可选的级别过滤列表，如 ["ERROR", "WARNING", "FATAL"]
        """
        conn = await self._get_conn()

        # 根据间隔选择 SQLite 时间格式化模板
        if interval == "minute":
            fmt = "%Y-%m-%d %H:%M"
        elif interval == "hour":
            fmt = "%Y-%m-%d %H:00"
        elif interval == "day":
            fmt = "%Y-%m-%d"
        elif interval == "month":
            fmt = "%Y-%m"
        else:
            fmt = "%Y-%m-%d %H:00"

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if levels:
            placeholders = ",".join("?" for _ in levels)
            conditions.append(f"level IN ({placeholders})")
            params.extend(levels)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"""SELECT strftime('{fmt}', timestamp) AS time_bucket,
                       level,
                       COUNT(*) AS count
                FROM log_entries
                WHERE {where_clause}
                GROUP BY time_bucket, level
                ORDER BY time_bucket""",
            params,
        )
        rows = await cursor.fetchall()

        # 组装为按时间段聚合的结构
        trend_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            bucket = row["time_bucket"]
            level = row["level"]
            count = row["count"]
            if bucket not in trend_map:
                trend_map[bucket] = {"time": bucket, "levels": {}, "total": 0}
            trend_map[bucket]["levels"][level] = count
            trend_map[bucket]["total"] += count

        return list(trend_map.values())

    async def cleanup_old_logs(self, days: int):
        """清理过期日志"""
        if days <= 0:
            return

        conn = await self._get_conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # 先删除关联的 critical_alerts（通过 log_entry_id）
        await conn.execute(
            """DELETE FROM critical_alerts
               WHERE log_entry_id IN (
                   SELECT id FROM log_entries WHERE created_at < ?
               )""",
            (cutoff,),
        )

        # 删除过期日志
        await conn.execute(
            "DELETE FROM log_entries WHERE created_at < ?",
            (cutoff,),
        )

        # 删除过期分析结果
        await conn.execute(
            "DELETE FROM analysis_results WHERE created_at < ?",
            (cutoff,),
        )

        # 删除不关联日志条目的孤立告警
        await conn.execute(
            """DELETE FROM critical_alerts
               WHERE created_at < ?
                 AND (log_entry_id IS NULL OR log_entry_id = 0)""",
            (cutoff,),
        )

        await conn.commit()

    async def get_log_file_size_info(self, instance_id: int) -> dict:
        """获取日志文件大小信息"""
        conn = await self._get_conn()

        # 获取实例的 log_path
        cursor = await conn.execute(
            "SELECT name, log_path FROM instances WHERE id = ?",
            (instance_id,),
        )
        instance = await cursor.fetchone()

        if instance is None:
            return {"instance_id": instance_id, "found": False}

        log_path = instance["log_path"]
        name = instance["name"]

        result: dict[str, Any] = {
            "instance_id": instance_id,
            "name": name,
            "log_path": log_path,
            "found": False,
        }

        path = Path(log_path)
        if path.exists():
            file_size = path.stat().st_size
            result["found"] = True
            result["file_size_bytes"] = file_size
            result["file_size_mb"] = round(file_size / (1024 * 1024), 2)

        # 获取数据库中该实例的日志条目数
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM log_entries WHERE instance_id = ?",
            (instance_id,),
        )
        row = await cursor.fetchone()
        result["db_entry_count"] = row["cnt"] if row else 0

        return result

    # ── 慢查询相关方法 ────────────────────────────────────────

    async def insert_slow_queries(self, entries: list[dict]):
        """批量插入慢查询记录

        Args:
            entries: 慢查询记录列表，每条记录包含:
                instance_id, timestamp, user, host, query_time, lock_time,
                rows_sent, rows_examined, sql_text, sql_hash, sql_type,
                sql_template, slow_score
        """
        if not entries:
            return

        conn = await self._get_conn()
        now = datetime.now().isoformat()

        rows = []
        for entry in entries:
            rows.append((
                entry.get("instance_id"),
                entry.get("timestamp", ""),
                entry.get("user", ""),
                entry.get("host", ""),
                entry.get("query_time", 0.0),
                entry.get("lock_time", 0.0),
                entry.get("rows_sent", 0),
                entry.get("rows_examined", 0),
                entry.get("sql_text", ""),
                entry.get("sql_hash", ""),
                entry.get("sql_type", "OTHER"),
                entry.get("sql_template", ""),
                entry.get("slow_score", 0.0),
                entry.get("created_at", now),
            ))

        await conn.executemany(
            """INSERT INTO slow_queries
               (instance_id, timestamp, user, host, query_time, lock_time,
                rows_sent, rows_examined, sql_text, sql_hash, sql_type,
                sql_template, slow_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await conn.commit()

    async def query_slow_queries(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
        min_query_time=None,
        sql_type=None,
        sort_by=None,
        limit=100,
        offset=0,
    ) -> list[dict]:
        """多条件查询慢查询记录

        Args:
            instance_id: 实例 ID
            start_time: 开始时间
            end_time: 结束时间
            min_query_time: 最小查询时间过滤
            sql_type: SQL 类型过滤
            sort_by: 排序字段 (query_time/lock_time/rows_examined/slow_score)
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            慢查询记录列表
        """
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if min_query_time is not None:
            conditions.append("query_time >= ?")
            params.append(min_query_time)
        if sql_type is not None:
            conditions.append("sql_type = ?")
            params.append(sql_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 排序
        order_map = {
            "query_time": "query_time DESC",
            "lock_time": "lock_time DESC",
            "rows_examined": "rows_examined DESC",
            "slow_score": "slow_score DESC",
        }
        order_clause = order_map.get(sort_by, "query_time DESC")

        params.extend([limit, offset])

        cursor = await conn.execute(
            f"""SELECT id, instance_id, timestamp, user, host, query_time,
                       lock_time, rows_sent, rows_examined, sql_text,
                       sql_hash, sql_type, sql_template, slow_score, created_at
                FROM slow_queries
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?""",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def count_slow_queries(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
        min_query_time=None,
        sql_type=None,
    ) -> int:
        """统计符合条件的慢查询总数"""
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if min_query_time is not None:
            conditions.append("query_time >= ?")
            params.append(min_query_time)
        if sql_type is not None:
            conditions.append("sql_type = ?")
            params.append(sql_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"SELECT COUNT(*) as cnt FROM slow_queries WHERE {where_clause}",
            params,
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def get_slow_query_stats(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
    ) -> dict:
        """获取慢查询统计信息

        Returns:
            包含 total_count, avg_query_time, max_query_time, avg_lock_time,
            avg_rows_examined, top_slow 等统计数据的字典
        """
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 基础统计
        cursor = await conn.execute(
            f"""SELECT COUNT(*) as total_count,
                       AVG(query_time) as avg_query_time,
                       MAX(query_time) as max_query_time,
                       AVG(lock_time) as avg_lock_time,
                       AVG(rows_examined) as avg_rows_examined
                FROM slow_queries
                WHERE {where_clause}""",
            params,
        )
        row = await cursor.fetchone()

        if row is None or row["total_count"] == 0:
            return {
                "total_count": 0,
                "avg_query_time": 0,
                "max_query_time": 0,
                "avg_lock_time": 0,
                "avg_rows_examined": 0,
                "top_slow": [],
            }

        # 按 sql_hash 分组统计 Top 慢查询
        cursor = await conn.execute(
            f"""SELECT sql_hash, sql_template,
                       COUNT(*) as count,
                       AVG(query_time) as avg_query_time,
                       MAX(query_time) as max_query_time,
                       SUM(query_time) as total_query_time,
                       MIN(timestamp) as first_seen,
                       MAX(timestamp) as last_seen
                FROM slow_queries
                WHERE {where_clause}
                GROUP BY sql_hash
                ORDER BY total_query_time DESC
                LIMIT 20""",
            params,
        )
        top_slow = [dict(row) for row in await cursor.fetchall()]

        return {
            "total_count": row["total_count"],
            "avg_query_time": round(row["avg_query_time"] or 0, 4),
            "max_query_time": round(row["max_query_time"] or 0, 4),
            "avg_lock_time": round(row["avg_lock_time"] or 0, 4),
            "avg_rows_examined": round(row["avg_rows_examined"] or 0, 2),
            "top_slow": top_slow,
        }

    async def get_slow_query_distribution(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
    ) -> dict:
        """获取慢查询分布

        Returns:
            包含 by_type, by_time_range, trend 的字典
        """
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 按 SQL 类型分布
        cursor = await conn.execute(
            f"""SELECT sql_type, COUNT(*) as count
                FROM slow_queries
                WHERE {where_clause}
                GROUP BY sql_type
                ORDER BY count DESC""",
            params.copy(),
        )
        by_type = [dict(row) for row in await cursor.fetchall()]

        # 按查询时间范围分布
        cursor = await conn.execute(
            f"""SELECT
                    CASE
                        WHEN query_time < 1 THEN '<1s'
                        WHEN query_time < 5 THEN '1-5s'
                        WHEN query_time < 10 THEN '5-10s'
                        WHEN query_time < 30 THEN '10-30s'
                        WHEN query_time < 60 THEN '30-60s'
                        ELSE '>60s'
                    END as range,
                    COUNT(*) as count
                FROM slow_queries
                WHERE {where_clause}
                GROUP BY range
                ORDER BY MIN(query_time)""",
            params.copy(),
        )
        by_time_range = [dict(row) for row in await cursor.fetchall()]

        # 时间趋势（按小时）
        cursor = await conn.execute(
            f"""SELECT strftime('%Y-%m-%d %H:00', timestamp) AS time,
                       COUNT(*) as count,
                       AVG(query_time) as avg_query_time
                FROM slow_queries
                WHERE {where_clause}
                GROUP BY time
                ORDER BY time""",
            params.copy(),
        )
        trend = []
        for row in await cursor.fetchall():
            trend.append({
                "time": row["time"],
                "count": row["count"],
                "avg_query_time": round(row["avg_query_time"] or 0, 4),
            })

        return {
            "by_type": by_type,
            "by_time_range": by_time_range,
            "trend": trend,
        }

    async def insert_slow_query_analysis(self, result: dict):
        """插入慢查询分析结果

        Args:
            result: 包含 instance_id, time_range_start, time_range_end,
                    summary, suggestions_json 的字典
        """
        conn = await self._get_conn()
        now = datetime.now().isoformat()

        suggestions = result.get("suggestions", [])
        suggestions_json = json.dumps(suggestions, ensure_ascii=False) if suggestions else "[]"

        await conn.execute(
            """INSERT INTO slow_query_analysis
               (instance_id, time_range_start, time_range_end, summary,
                suggestions_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                result.get("instance_id"),
                result.get("time_range_start", ""),
                result.get("time_range_end", ""),
                result.get("summary", ""),
                suggestions_json,
                result.get("created_at", now),
            ),
        )
        await conn.commit()

    async def query_slow_query_analysis(
        self,
        instance_id=None,
        start_time=None,
        end_time=None,
    ) -> list[dict]:
        """查询慢查询分析结果

        Args:
            instance_id: 实例 ID
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            分析结果列表
        """
        conn = await self._get_conn()

        conditions = []
        params: list[Any] = []

        if instance_id is not None:
            conditions.append("instance_id = ?")
            params.append(instance_id)
        if start_time is not None:
            conditions.append("time_range_start >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("time_range_end <= ?")
            params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = await conn.execute(
            f"""SELECT id, instance_id, time_range_start, time_range_end,
                       summary, suggestions_json, created_at
                FROM slow_query_analysis
                WHERE {where_clause}
                ORDER BY created_at DESC""",
            params,
        )
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            item = dict(row)
            # 解析 suggestions_json
            try:
                item["suggestions"] = json.loads(item.get("suggestions_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                item["suggestions"] = []
            results.append(item)

        return results

    # ── 监控指标相关方法 ──────────────────────────────────────

    async def insert_monitor_metric(
        self, instance_id: int, metric_name: str, metric_value: float, collected_at: str
    ):
        """插入监控指标数据"""
        conn = await self._get_conn()

        await conn.execute(
            """INSERT INTO monitor_metrics
               (instance_id, metric_name, metric_value, collected_at)
               VALUES (?, ?, ?, ?)""",
            (instance_id, metric_name, metric_value, collected_at),
        )
        await conn.commit()

    async def query_monitor_metrics(
        self,
        instance_id: int,
        metric_name: str,
        start_time: str,
        end_time: str,
        limit: int = 1000,
    ) -> list[dict]:
        """查询监控指标历史数据"""
        conn = await self._get_conn()

        cursor = await conn.execute(
            """SELECT id, instance_id, metric_name, metric_value, collected_at
               FROM monitor_metrics
               WHERE instance_id = ?
                 AND metric_name = ?
                 AND collected_at >= ?
                 AND collected_at <= ?
               ORDER BY collected_at ASC
               LIMIT ?""",
            (instance_id, metric_name, start_time, end_time, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def cleanup_old_metrics(self, days: int = 7):
        """清理过期的监控指标数据，默认保留最近 7 天"""
        if days <= 0:
            return

        conn = await self._get_conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        await conn.execute(
            "DELETE FROM monitor_metrics WHERE collected_at < ?",
            (cutoff,),
        )
        await conn.commit()
