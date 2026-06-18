"""实时监控 API"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.collector.mysql_connector import MySQLConnector
from src.web.api.deps import get_db as _get_db
from src.web.api.deps import get_mysql_connector as _get_connector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["监控"])


# ── Pydantic 模型 ───────────────────────────────────────────

class TestConnectionRequest(BaseModel):
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""


def _parse_innodb_status(status_text: str) -> dict:
    """解析 InnoDB Status 文本为结构化数据"""
    parsed = {
        'buffer_pool': {},
        'lock_waits': [],
        'transactions': [],
        'log': {},
    }

    if not status_text:
        return parsed

    # 解析 Buffer Pool 部分
    bp_match = re.search(
        r'BUFFER POOL AND MEMORY\s*-{5,}\n(.*?)(?=\n-{5,}|\Z)',
        status_text, re.DOTALL
    )
    if bp_match:
        bp_text = bp_match.group(1)
        for line in bp_text.split('\n'):
            line = line.strip()
            if 'Total memory allocated' in line:
                parsed['buffer_pool']['total_memory'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Buffer pool size' in line and 'Database pages' not in line:
                parsed['buffer_pool']['pool_size'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Database pages' in line:
                parsed['buffer_pool']['database_pages'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Free buffers' in line:
                parsed['buffer_pool']['free_buffers'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Modified db pages' in line:
                parsed['buffer_pool']['modified_pages'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Read views' in line:
                parsed['buffer_pool']['read_views'] = line.split(':')[1].strip() if ':' in line else line

    # 解析锁等待部分
    lock_match = re.search(
        r'TRANSACTIONS\s*-{5,}\n(.*?)(?=\n-{5,}|\Z)',
        status_text, re.DOTALL
    )
    if lock_match:
        lock_text = lock_match.group(1)
        # 提取活跃事务
        tx_pattern = re.compile(
            r'TRANSACTION\s+(\d+),\s+.*?(?=TRANSACTION\s+\d+|\Z)',
            re.DOTALL
        )
        for tx_match in tx_pattern.finditer(lock_text):
            tx_id = tx_match.group(1)
            tx_text = tx_match.group(0)
            tx_info = {'id': tx_id}
            state_match = re.search(r'state:\s*(.+)', tx_text)
            if state_match:
                tx_info['state'] = state_match.group(1).strip()
            tables_match = re.search(r'tables in use\s+(\d+).*?locked\s+(\d+)', tx_text)
            if tables_match:
                tx_info['tables_in_use'] = int(tables_match.group(1))
                tx_info['tables_locked'] = int(tables_match.group(2))
            lock_wait_match = re.search(r'\*\*\*.*?waiting for lock', tx_text, re.IGNORECASE)
            if lock_wait_match:
                tx_info['waiting_for_lock'] = True
            parsed['transactions'].append(tx_info)

    # 解析 Log 部分
    log_match = re.search(
        r'LOG\s*-{5,}\n(.*?)(?=\n-{5,}|\Z)',
        status_text, re.DOTALL
    )
    if log_match:
        log_text = log_match.group(1)
        for line in log_text.split('\n'):
            line = line.strip()
            if 'Log sequence number' in line:
                parsed['log']['lsn'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Log flushed up to' in line:
                parsed['log']['flushed_lsn'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Pages flushed up to' in line:
                parsed['log']['pages_flushed_lsn'] = line.split(':')[1].strip() if ':' in line else line
            elif 'Last checkpoint at' in line:
                parsed['log']['last_checkpoint'] = line.split(':')[1].strip() if ':' in line else line

    return parsed


# ── API 端点 ────────────────────────────────────────────────

@router.get("/monitor/status")
async def get_monitor_status(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """获取 MySQL 实时状态指标"""
    connector = _get_connector(instance_id)

    try:
        status = await connector.get_global_status()
    except Exception as e:
        logger.warning("获取 MySQL 状态失败: %s", e)
        status = {}

    if not status:
        return {'connected': False}

    # 获取 max_connections 变量
    try:
        variables = await connector.get_variables(like_pattern='max_connections')
        max_allowed = int(variables.get('max_connections', 0))
    except Exception:
        max_allowed = 0

    # 保存指标到历史
    db = _get_db()
    now = datetime.now().isoformat()
    instance_id_val = instance_id or 0
    try:
        await db.insert_monitor_metric(instance_id_val, 'connections', status.get('Threads_connected', 0), now)
        await db.insert_monitor_metric(instance_id_val, 'qps', status.get('QPS', 0), now)
        await db.insert_monitor_metric(instance_id_val, 'tps', status.get('TPS', 0), now)
        await db.insert_monitor_metric(instance_id_val, 'buffer_pool_hitrate', status.get('Buffer_pool_hit_rate', 0), now)
    except Exception as e:
        logger.warning("保存监控指标失败: %s", e)

    return {
        'connected': True,
        'version': '',  # 不额外查询，由 test-connection 获取
        'uptime': status.get('Uptime', 0),
        'connections': {
            'current': status.get('Threads_connected', 0),
            'max_used': status.get('Max_used_connections', 0),
            'max_allowed': max_allowed,
        },
        'qps': status.get('QPS', 0),
        'tps': status.get('TPS', 0),
        'buffer_pool': {
            'hit_rate': status.get('Buffer_pool_hit_rate', 0),
            'total_pages': status.get('Innodb_buffer_pool_pages_total', 0),
            'free_pages': status.get('Innodb_buffer_pool_pages_free', 0),
            'read_requests': status.get('Innodb_buffer_pool_read_requests', 0),
            'reads': status.get('Innodb_buffer_pool_reads', 0),
        },
        'innodb_locks': {
            'row_lock_waits': status.get('Innodb_row_lock_waits', 0),
            'row_lock_time_avg_ms': status.get('Innodb_row_lock_time_avg_ms', 0),
            'row_lock_time_total_ms': status.get('Innodb_row_lock_time_total_ms', 0),
        },
        'traffic': {
            'bytes_received_per_sec': status.get('Bytes_received_per_sec', 0),
            'bytes_sent_per_sec': status.get('Bytes_sent_per_sec', 0),
        },
        'slow_queries': status.get('Slow_queries', 0),
        'threads': {
            'running': status.get('Threads_running', 0),
            'cached': status.get('Threads_cached', 0),
            'connected': status.get('Threads_connected', 0),
        },
        'tables': {
            'open': status.get('Open_tables', 0),
            'opened': status.get('Opened_tables', 0),
            'cache_size': status.get('Table_open_cache', 0),
        },
        'full_scans': {
            'select_full_join': status.get('Select_full_join', 0),
            'select_scan': status.get('Select_scan', 0),
        },
    }


@router.get("/monitor/processlist")
async def get_processlist(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """获取当前进程列表"""
    connector = _get_connector(instance_id)

    try:
        items = await connector.get_processlist()
    except Exception as e:
        logger.warning("获取 PROCESSLIST 失败: %s", e)
        items = []

    active_count = sum(1 for p in items if p.get('command', '') != 'Sleep')
    sleep_count = sum(1 for p in items if p.get('command', '') == 'Sleep')

    return {
        'items': items,
        'total': len(items),
        'active_count': active_count,
        'sleep_count': sleep_count,
    }


@router.get("/monitor/replication")
async def get_replication_status(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """获取主从复制状态"""
    connector = _get_connector(instance_id)

    master_status = None
    slave_status = None

    try:
        master_status = await connector.get_master_status()
    except Exception as e:
        logger.warning("获取 MASTER STATUS 失败: %s", e)

    try:
        slave_status = await connector.get_slave_status()
    except Exception as e:
        logger.warning("获取 SLAVE STATUS 失败: %s", e)

    result = {
        'is_master': master_status is not None,
        'is_slave': slave_status is not None,
        'master': None,
        'slave': None,
    }

    if master_status:
        result['master'] = {
            'file': master_status.get('File', ''),
            'position': master_status.get('Position', 0),
            'binlog_do_db': master_status.get('Binlog_Do_DB', ''),
            'binlog_ignore_db': master_status.get('Binlog_Ignore_DB', ''),
        }

    if slave_status:
        result['slave'] = {
            'master_host': slave_status.get('Master_Host', ''),
            'master_port': slave_status.get('Master_Port', 3306),
            'io_running': slave_status.get('Slave_IO_Running', 'No') == 'Yes',
            'sql_running': slave_status.get('Slave_SQL_Running', 'No') == 'Yes',
            'seconds_behind': slave_status.get('Seconds_Behind_Master'),
            'last_io_error': slave_status.get('Last_IO_Error', ''),
            'last_sql_error': slave_status.get('Last_SQL_Error', ''),
            'exec_master_log_pos': slave_status.get('Exec_Master_Log_Pos', 0),
            'read_master_log_pos': slave_status.get('Read_Master_Log_Pos', 0),
            'relay_master_log_file': slave_status.get('Relay_Master_Log_File', ''),
            'master_log_file': slave_status.get('Master_Log_File', ''),
            'auto_position': slave_status.get('Auto_Position', 0),
            'replicate_do_db': slave_status.get('Replicate_Do_DB', ''),
            'slave_sql_running_state': slave_status.get('Slave_SQL_Running_State', ''),
        }

    return result


@router.get("/monitor/innodb")
async def get_innodb_status(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
):
    """获取 InnoDB 引擎状态"""
    connector = _get_connector(instance_id)

    try:
        status_text = await connector.get_innodb_status()
    except Exception as e:
        logger.warning("获取 INNODB STATUS 失败: %s", e)
        status_text = ''

    parsed = _parse_innodb_status(status_text)

    return {
        'status_text': status_text,
        'parsed': parsed,
    }


@router.get("/monitor/history")
async def get_monitor_history(
    instance_id: Optional[int] = Query(None, description="实例 ID"),
    metric: str = Query("connections", description="指标名称: connections/qps/tps/buffer_pool_hitrate"),
    minutes: int = Query(60, ge=1, le=1440, description="查询最近 N 分钟"),
):
    """获取历史监控数据（最近 N 个数据点）"""
    db = _get_db()
    instance_id_val = instance_id or 0
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=minutes)

    try:
        rows = await db.query_monitor_metrics(
            instance_id_val,
            metric,
            start_time.isoformat(),
            end_time.isoformat(),
            limit=1000,
        )
    except Exception as e:
        logger.warning("查询监控历史失败: %s", e)
        rows = []

    data = []
    for row in rows:
        data.append({
            'time': row.get('collected_at', ''),
            'value': row.get('metric_value', 0),
        })

    return {'data': data}


@router.post("/monitor/test-connection")
async def test_connection(body: TestConnectionRequest):
    """测试 MySQL 连接"""
    connector = MySQLConnector(
        host=body.host,
        port=body.port,
        user=body.user,
        password=body.password,
    )

    try:
        result = await connector.test_connection()
    except Exception as e:
        result = {
            'success': False,
            'message': f'连接失败: {str(e)[:200]}',
            'version': '',
        }
    finally:
        await connector.close()

    return result
