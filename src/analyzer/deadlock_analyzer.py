"""InnoDB 死锁深度分析引擎

解析死锁日志，构建锁等待链图，给出索引优化建议。
"""
import re
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime


@dataclass
class LockInfo:
    """锁信息"""
    lock_type: str          # RECORD LOCK, TABLE LOCK 等
    lock_mode: str          # X, S, IX, IS, X,GAP 等
    database: str           # 数据库名
    table: str              # 表名
    index: str              # 索引名
    lock_data: str          # 具体记录/行信息


@dataclass
class DeadlockTransaction:
    """死锁中的事务信息"""
    transaction_id: str
    thread_id: str
    query: str              # 导致死锁的 SQL
    tables: list[str]       # 涉及的表
    locks_held: list[LockInfo]      # 持有的锁
    locks_requested: list[LockInfo] # 请求的锁
    wait_for: Optional[str]         # 等待的事务 ID
    rollback_weight: float          # 回滚代价权重 0-1，越高回滚代价越大


@dataclass
class DeadlockChain:
    """锁等待链"""
    chain: list[tuple[str, str, str]]  # (from_tx_id, to_tx_id, resource)
    cycle_detected: bool
    victim: Optional[str]              # 被回滚的事务 ID


@dataclass
class DeadlockAnalysis:
    """死锁分析结果"""
    id: str
    timestamp: str
    raw_text: str
    transactions: list[DeadlockTransaction]
    lock_chain: DeadlockChain
    root_cause: str
    suggestions: list[str]
    severity: str                       # low/medium/high/critical
    affected_tables: list[str]
    index_suggestions: list[dict]       # {table, suggested_index, reason}


class DeadlockAnalyzer:
    """InnoDB 死锁分析器

    解析 MySQL 错误日志中的 InnoDB 死锁信息，
    构建锁等待链图，分析根因并给出优化建议。
    """

    def __init__(self):
        # 预编译正则表达式，提升解析性能
        # 匹配事务头: TRANSACTION 12345, ACTIVE 2 sec ...
        self._re_transaction = re.compile(
            r'TRANSACTION\s+(\d+),\s+ACTIVE\s+(\d+)\s+sec\b(.*)',
            re.IGNORECASE,
        )
        # 匹配线程 ID: MySQL thread id 10, ...
        self._re_thread_id = re.compile(
            r'MySQL\s+thread\s+id\s+(\d+)',
            re.IGNORECASE,
        )
        # 匹配 SQL 查询行（通常在事务块最后一行）
        self._re_query = re.compile(
            r'^(UPDATE|DELETE|INSERT|REPLACE|SELECT|ALTER|CREATE|DROP|CALL)\b',
            re.IGNORECASE,
        )
        # 匹配 RECORD LOCKS 行
        self._re_record_lock = re.compile(
            r'RECORD\s+LOCKS\s+space\s+id\s+(\d+)\s+page\s+no\s+(\d+)\s+'
            r'n\s+bits\s+(\d+)\s+index\s+(\S+)\s+of\s+table\s+`?(\w+)`?\.`?(\w+)`?',
            re.IGNORECASE,
        )
        # 匹配 TABLE LOCK 行
        self._re_table_lock = re.compile(
            r'TABLE\s+LOCK\s+table\s+`?(\w+)`?\.`?(\w+)`?\s+trx\s+id\s+(\d+)\s+lock\s+mode\s+(\S+)',
            re.IGNORECASE,
        )
        # 匹配 lock_mode
        self._re_lock_mode = re.compile(
            r'lock_mode\s+(\S+)',
            re.IGNORECASE,
        )
        # 匹配 Record lock 行（具体记录信息）
        self._re_record_data = re.compile(
            r'Record\s+lock,\s+heap\s+no\s+(\d+)(.*)',
            re.IGNORECASE,
        )
        # 匹配 "WE ROLL BACK TRANSACTION" 行
        self._re_rollback = re.compile(
            r'WE\s+ROLL\s+BACK\s+TRANSACTION\s+\((\d+)\)',
            re.IGNORECASE,
        )
        # 匹配 "mysql tables in use" 行
        self._re_tables_in_use = re.compile(
            r'mysql\s+tables\s+in\s+use\s+(\d+),\s+locked\s+(\d+)',
            re.IGNORECASE,
        )
        # 匹配 "LOCK WAIT" 行
        self._re_lock_wait = re.compile(
            r'LOCK\s+WAIT',
            re.IGNORECASE,
        )
        # 匹配时间戳（MySQL 错误日志格式，不要求行首）
        self._re_timestamp = re.compile(
            r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)',
        )

    def parse_deadlock_log(self, log_text: str) -> Optional[DeadlockAnalysis]:
        """解析完整的 InnoDB 死锁日志条目

        Args:
            log_text: 死锁日志原文

        Returns:
            DeadlockAnalysis 对象，解析失败返回 None
        """
        if not log_text or 'DEADLOCK' not in log_text.upper():
            return None

        # 提取时间戳
        timestamp = ""
        ts_match = self._re_timestamp.search(log_text)
        if ts_match:
            timestamp = ts_match.group(1)

        # 生成唯一 ID
        analysis_id = hashlib.md5(log_text.encode()).hexdigest()[:16]

        # 提取被回滚的事务编号
        victim_tx_num = None
        rollback_match = self._re_rollback.search(log_text)
        if rollback_match:
            victim_tx_num = rollback_match.group(1)

        # 按事务块分割日志
        # 事务块以 *** (N) TRANSACTION: 开始
        tx_blocks = re.split(
            r'\*\*\*\s*\((\d+)\)\s*TRANSACTION:',
            log_text,
        )

        transactions: list[DeadlockTransaction] = []

        # tx_blocks[0] 是头部，之后每3个元素为一组：(编号, 事务内容, ...)
        idx = 1
        while idx + 1 < len(tx_blocks):
            tx_num = tx_blocks[idx].strip()
            tx_body = tx_blocks[idx + 1]
            idx += 2

            tx = self._parse_transaction_block(tx_num, tx_body, log_text)
            if tx:
                transactions.append(tx)

        # 构建锁等待链
        lock_chain = self.build_lock_chain(transactions)

        # 设置 victim
        if victim_tx_num:
            # 找到对应的事务 ID
            for tx in transactions:
                # victim_tx_num 是日志中的序号 (1), (2) 等
                # 需要映射到 transaction_id
                pass
            # 直接从 raw_text 中提取被回滚事务的 transaction_id
            victim_tx_id = self._find_victim_tx_id(log_text, victim_tx_num, transactions)
            lock_chain.victim = victim_tx_id

        # 创建分析对象（先不填 root_cause 和 suggestions）
        affected_tables = []
        for tx in transactions:
            for t in tx.tables:
                if t not in affected_tables:
                    affected_tables.append(t)

        analysis = DeadlockAnalysis(
            id=analysis_id,
            timestamp=timestamp,
            raw_text=log_text,
            transactions=transactions,
            lock_chain=lock_chain,
            root_cause="",
            suggestions=[],
            severity="medium",
            affected_tables=affected_tables,
            index_suggestions=[],
        )

        # 分析根因
        analysis.root_cause = self.analyze_root_cause(analysis)

        # 生成建议
        analysis.suggestions = self.generate_suggestions(analysis)

        # 生成索引建议
        analysis.index_suggestions = self.generate_index_suggestions(analysis)

        # 评估严重程度
        analysis.severity = self._assess_severity(analysis)

        return analysis

    def _parse_transaction_block(
        self,
        tx_num: str,
        tx_body: str,
        full_log: str,
    ) -> Optional[DeadlockTransaction]:
        """解析单个事务块

        Args:
            tx_num: 事务序号 (1, 2, ...)
            tx_body: 事务块内容
            full_log: 完整日志（用于查找 HOLDS/WAITING 段）

        Returns:
            DeadlockTransaction 对象
        """
        # 提取事务 ID
        transaction_id = ""
        tx_match = self._re_transaction.search(tx_body)
        if tx_match:
            transaction_id = tx_match.group(1)

        # 提取线程 ID
        thread_id = ""
        tid_match = self._re_thread_id.search(tx_body)
        if tid_match:
            thread_id = tid_match.group(1)

        # 提取 SQL 查询
        query = ""
        lines = tx_body.strip().split('\n')
        for line in lines:
            stripped = line.strip()
            if self._re_query.match(stripped):
                query = stripped
                break

        # 提取涉及的表名
        tables = self._extract_tables(tx_body)

        # 解析持有的锁和请求的锁
        # 需要在完整日志中查找对应事务的 HOLDS 和 WAITING 段
        locks_held, locks_requested = self._parse_locks_for_tx(tx_num, full_log)

        # 确定 wait_for（请求的锁被谁持有）
        wait_for = None
        if locks_requested:
            # 请求的锁说明在等待，需要从锁等待链推断
            # 简单处理：在后续 build_lock_chain 中确定
            pass

        # 计算回滚代价权重
        rollback_weight = self._calc_rollback_weight(tx_body, transaction_id)

        return DeadlockTransaction(
            transaction_id=transaction_id,
            thread_id=thread_id,
            query=query,
            tables=tables,
            locks_held=locks_held,
            locks_requested=locks_requested,
            wait_for=wait_for,
            rollback_weight=rollback_weight,
        )

    def _extract_tables(self, text: str) -> list[str]:
        """从文本中提取涉及的表名"""
        tables: list[str] = []
        seen: set[str] = set()

        def _add_table(name: str, bare_name: str = ""):
            """添加表名，去重

            优先使用完全限定名（db.table），避免同时出现 db.table 和 table
            """
            # 检查是否已有该表的完全限定名
            if bare_name:
                for existing in tables:
                    if existing.endswith(f'`.`{bare_name}`') or existing == bare_name:
                        # 已存在，如果新名称更完整则替换
                        if '.' in name and '.' not in existing:
                            idx = tables.index(existing)
                            tables[idx] = name
                            seen.discard(existing)
                            seen.add(name)
                        return
            if name not in seen:
                seen.add(name)
                tables.append(name)

        # 从 RECORD LOCKS / TABLE LOCK 行提取
        for match in self._re_record_lock.finditer(text):
            db_name = match.group(5)
            tb_name = match.group(6)
            full_name = f"`{db_name}`.`{tb_name}`"
            _add_table(full_name, tb_name)
        for match in self._re_table_lock.finditer(text):
            db_name = match.group(1)
            tb_name = match.group(2)
            full_name = f"`{db_name}`.`{tb_name}`"
            _add_table(full_name, tb_name)
        # 从 SQL 中提取（简单匹配 FROM/UPDATE/INSERT INTO 后的表名）
        sql_table_re = re.compile(
            r'(?:FROM|UPDATE|INSERT\s+INTO|DELETE\s+FROM|JOIN)\s+`?(\w+)`?',
            re.IGNORECASE,
        )
        for match in sql_table_re.finditer(text):
            tb_name = match.group(1)
            if tb_name.upper() not in ('SELECT', 'SET', 'WHERE', 'AND', 'OR'):
                _add_table(tb_name, tb_name)
        return tables

    def _parse_locks_for_tx(
        self,
        tx_num: str,
        full_log: str,
    ) -> tuple[list[LockInfo], list[LockInfo]]:
        """解析指定事务持有的锁和请求的锁

        Args:
            tx_num: 事务序号
            full_log: 完整日志

        Returns:
            (locks_held, locks_requested) 元组
        """
        locks_held: list[LockInfo] = []
        locks_requested: list[LockInfo] = []

        # 查找 HOLDS THE LOCK(S) 段
        holds_pattern = re.compile(
            r'\*\*\*\s*\(' + re.escape(tx_num) + r'\)\s*HOLDS\s+THE\s+LOCK\(S\):(.*?)(?=\*\*\*|\Z)',
            re.IGNORECASE | re.DOTALL,
        )
        holds_match = holds_pattern.search(full_log)
        if holds_match:
            holds_text = holds_match.group(1)
            locks_held = self._parse_lock_section(holds_text)

        # 查找 WAITING FOR THIS LOCK 段
        waiting_pattern = re.compile(
            r'\*\*\*\s*\(' + re.escape(tx_num) + r'\)\s*WAITING\s+FOR\s+THIS\s+LOCK\s+TO\s+BE\s+GRANTED:(.*?)(?=\*\*\*|\Z)',
            re.IGNORECASE | re.DOTALL,
        )
        waiting_match = waiting_pattern.search(full_log)
        if waiting_match:
            waiting_text = waiting_match.group(1)
            locks_requested = self._parse_lock_section(waiting_text)

        # 如果没有明确的 HOLDS 段，从事务块本身提取锁信息
        # 某些 MySQL 版本的格式不同
        if not locks_held and not locks_requested:
            # 尝试从事务块中直接提取
            tx_pattern = re.compile(
                r'\*\*\*\s*\(' + re.escape(tx_num) + r'\)\s*TRANSACTION:(.*?)(?=\*\*\*\s*\(\d+\)|\Z)',
                re.IGNORECASE | re.DOTALL,
            )
            tx_match = tx_pattern.search(full_log)
            if tx_match:
                tx_text = tx_match.group(1)
                # 如果有 LOCK WAIT 标记，则锁信息在 WAITING 段
                if self._re_lock_wait.search(tx_text):
                    locks_requested = self._parse_lock_section(tx_text)
                else:
                    locks_held = self._parse_lock_section(tx_text)

        return locks_held, locks_requested

    def _parse_lock_section(self, text: str) -> list[LockInfo]:
        """解析锁信息段落

        Args:
            text: 包含锁信息的文本

        Returns:
            LockInfo 列表
        """
        locks: list[LockInfo] = []

        # 解析 RECORD LOCKS
        for match in self._re_record_lock.finditer(text):
            index_name = match.group(4)
            db_name = match.group(5)
            tb_name = match.group(6)

            # 提取 lock_mode
            lock_mode = ""
            remaining = text[match.end():]
            mode_match = self._re_lock_mode.search(remaining[:200])
            if mode_match:
                lock_mode = mode_match.group(1)

            # 提取 Record lock 具体数据
            lock_data = ""
            rec_match = self._re_record_data.search(remaining[:500])
            if rec_match:
                lock_data = rec_match.group(0).strip()

            locks.append(LockInfo(
                lock_type="RECORD LOCK",
                lock_mode=lock_mode,
                database=db_name,
                table=tb_name,
                index=index_name,
                lock_data=lock_data,
            ))

        # 解析 TABLE LOCK
        for match in self._re_table_lock.finditer(text):
            db_name = match.group(1)
            tb_name = match.group(2)
            lock_mode = match.group(4)

            locks.append(LockInfo(
                lock_type="TABLE LOCK",
                lock_mode=lock_mode,
                database=db_name,
                table=tb_name,
                index="",
                lock_data="",
            ))

        return locks

    def _calc_rollback_weight(self, tx_body: str, transaction_id: str) -> float:
        """计算事务回滚代价权重

        基于：
        - 持有锁的数量
        - 活跃时间
        - 锁定行数

        Args:
            tx_body: 事务块文本
            transaction_id: 事务 ID

        Returns:
            0-1 之间的权重值
        """
        weight = 0.0

        # 活跃时间
        tx_match = self._re_transaction.search(tx_body)
        if tx_match:
            try:
                active_sec = int(tx_match.group(2))
                # 活跃时间越长，回滚代价越高
                weight += min(active_sec / 60.0, 0.4)
            except (ValueError, IndexError):
                pass

        # 锁定行数
        row_lock_match = re.search(r'(\d+)\s+row\s+lock\(s\)', tx_body, re.IGNORECASE)
        if row_lock_match:
            try:
                row_locks = int(row_lock_match.group(1))
                # 锁定行数越多，回滚代价越高
                weight += min(row_locks / 100.0, 0.3)
            except (ValueError, IndexError):
                pass

        # 锁结构数
        lock_struct_match = re.search(r'(\d+)\s+lock\s+struct\(s\)', tx_body, re.IGNORECASE)
        if lock_struct_match:
            try:
                lock_structs = int(lock_struct_match.group(1))
                weight += min(lock_structs / 10.0, 0.3)
            except (ValueError, IndexError):
                pass

        return min(weight, 1.0)

    def _find_victim_tx_id(
        self,
        full_log: str,
        victim_num: str,
        transactions: list[DeadlockTransaction],
    ) -> Optional[str]:
        """从日志中找到被回滚事务的 transaction_id

        Args:
            full_log: 完整日志
            victim_num: 日志中的事务序号 (1, 2, ...)
            transactions: 已解析的事务列表

        Returns:
            被回滚事务的 transaction_id
        """
        # 事务按日志中出现的顺序排列
        idx = int(victim_num) - 1
        if 0 <= idx < len(transactions):
            return transactions[idx].transaction_id
        return None

    def build_lock_chain(self, transactions: list[DeadlockTransaction]) -> DeadlockChain:
        """构建锁等待链图

        从事务列表中提取等待关系，构建有向图并检测环。

        Args:
            transactions: 事务列表

        Returns:
            DeadlockChain 对象
        """
        chain: list[tuple[str, str, str]] = []
        cycle_detected = False

        # 构建事务 ID 到事务的映射
        tx_map: dict[str, DeadlockTransaction] = {}
        for tx in transactions:
            if tx.transaction_id:
                tx_map[tx.transaction_id] = tx

        # 分析等待关系：事务 A 请求的锁被事务 B 持有 → A 等待 B
        for tx_a in transactions:
            if not tx_a.transaction_id or not tx_a.locks_requested:
                continue

            for req_lock in tx_a.locks_requested:
                resource = f"{req_lock.database}.{req_lock.table}.{req_lock.index}"
                # 查找持有该资源锁的事务
                for tx_b in transactions:
                    if tx_b.transaction_id == tx_a.transaction_id:
                        continue
                    for held_lock in tx_b.locks_held:
                        held_resource = f"{held_lock.database}.{held_lock.table}.{held_lock.index}"
                        if resource == held_resource:
                            chain.append((
                                tx_a.transaction_id,
                                tx_b.transaction_id,
                                resource,
                            ))
                            tx_a.wait_for = tx_b.transaction_id

        # 检测环：如果存在 A→B→A 的链，则检测到死锁环
        if len(chain) >= 2:
            # 使用 DFS 检测环
            adj: dict[str, list[str]] = {}
            for from_tx, to_tx, _ in chain:
                if from_tx not in adj:
                    adj[from_tx] = []
                adj[from_tx].append(to_tx)

            for start_node in adj:
                if self._dfs_cycle(start_node, adj, set(), start_node):
                    cycle_detected = True
                    break

        # 如果只有两个事务且互相等待（双向边），也构成环
        if not cycle_detected and len(transactions) == 2 and len(chain) >= 2:
            edge_set = {(f, t) for f, t, _ in chain}
            for f, t in edge_set:
                if (t, f) in edge_set:
                    cycle_detected = True
                    break

        # InnoDB 检测到死锁必然存在环，如果事务数 >= 2 且有等待关系，标记为检测到环
        if not cycle_detected and len(transactions) >= 2 and len(chain) >= 1:
            cycle_detected = True

        return DeadlockChain(
            chain=chain,
            cycle_detected=cycle_detected,
            victim=None,
        )

    def _dfs_cycle(
        self,
        current: str,
        adj: dict[str, list[str]],
        visited: set[str],
        start: str,
    ) -> bool:
        """深度优先搜索检测环

        Args:
            current: 当前节点
            adj: 邻接表
            visited: 已访问节点集合
            start: 起始节点

        Returns:
            是否检测到环
        """
        if current in visited:
            return current == start

        visited.add(current)
        for neighbor in adj.get(current, []):
            if neighbor == start:
                return True
            if neighbor not in visited:
                if self._dfs_cycle(neighbor, adj, visited, start):
                    return True
        return False

    def analyze_root_cause(self, analysis: DeadlockAnalysis) -> str:
        """分析死锁根因

        判定规则：
        - 同表不同索引 → 索引设计问题
        - 同表同索引 → 行级竞争
        - 不同表 → 跨表依赖
        - GAP 锁 → 间隙锁竞争

        Args:
            analysis: 死锁分析对象

        Returns:
            根因描述字符串
        """
        transactions = analysis.transactions
        if not transactions:
            return "无法确定根因：未解析到事务信息"

        # 收集所有锁信息
        all_locks_held: list[LockInfo] = []
        all_locks_requested: list[LockInfo] = []
        for tx in transactions:
            all_locks_held.extend(tx.locks_held)
            all_locks_requested.extend(tx.locks_requested)

        # 检查是否有 GAP 锁
        has_gap_lock = False
        for lock in all_locks_held + all_locks_requested:
            if 'GAP' in lock.lock_mode.upper():
                has_gap_lock = True
                break

        if has_gap_lock:
            return "间隙锁（GAP Lock）竞争：事务使用了范围查询或 Next-Key Lock，导致间隙锁冲突。建议使用 READ COMMITTED 隔离级别或缩短事务。"

        # 检查是否涉及不同表
        all_tables = set()
        for lock in all_locks_held + all_locks_requested:
            if lock.table:
                all_tables.add(f"{lock.database}.{lock.table}")

        if len(all_tables) > 1:
            return "跨表依赖死锁：多个事务以不同顺序访问不同表，形成循环等待。建议统一表的访问顺序或减小事务范围。"

        # 同表情况：检查索引
        if len(all_tables) == 1:
            indexes_held = set()
            indexes_requested = set()
            for lock in all_locks_held:
                if lock.index:
                    indexes_held.add(lock.index)
            for lock in all_locks_requested:
                if lock.index:
                    indexes_requested.add(lock.index)

            # 同表不同索引
            if indexes_held and indexes_requested and indexes_held != indexes_requested:
                return (
                    "索引设计问题：同一表上使用了不同索引，导致锁定的行范围不同，"
                    "形成死锁。建议统一查询使用的索引或添加合适的复合索引。"
                )

            # 同表同索引
            return "行级竞争死锁：多个事务在同一索引上竞争相同或相邻行的锁。建议优化事务逻辑，减少锁持有时间。"

        return "死锁原因待进一步分析。"

    def generate_suggestions(self, analysis: DeadlockAnalysis) -> list[str]:
        """生成优化建议

        规则：
        - WHERE 子句无索引 → 建议添加索引
        - GAP 锁 → 建议使用 READ COMMITTED 或缩短事务
        - 同表高竞争 → 建议乐观锁或队列
        - 跨表 → 建议减小事务范围
        - 长事务 → 建议拆分为小事务

        Args:
            analysis: 死锁分析对象

        Returns:
            建议列表
        """
        suggestions: list[str] = []

        # 检查 GAP 锁
        has_gap_lock = False
        for tx in analysis.transactions:
            for lock in tx.locks_held + tx.locks_requested:
                if 'GAP' in lock.lock_mode.upper():
                    has_gap_lock = True
                    break
            if has_gap_lock:
                break

        if has_gap_lock:
            suggestions.append(
                "检测到 GAP 锁冲突，建议将隔离级别调整为 READ COMMITTED 以减少间隙锁，"
                "或缩短事务执行时间。"
            )

        # 检查跨表依赖
        all_tables = set()
        for tx in analysis.transactions:
            for lock in tx.locks_held + tx.locks_requested:
                if lock.table:
                    all_tables.add(f"{lock.database}.{lock.table}")

        if len(all_tables) > 1:
            suggestions.append(
                "检测到跨表依赖，建议统一表的访问顺序，或拆分大事务以减小锁定范围。"
            )

        # 检查同表高竞争
        if len(all_tables) == 1 and len(analysis.transactions) >= 2:
            suggestions.append(
                "同表高竞争场景，建议使用乐观锁（版本号机制）或通过消息队列串行化访问。"
            )

        # 检查长事务
        for tx in analysis.transactions:
            if tx.rollback_weight > 0.5:
                suggestions.append(
                    f"事务 {tx.transaction_id} 回滚代价较高（权重 {tx.rollback_weight:.2f}），"
                    "建议将长事务拆分为多个小事务，减少锁持有时间。"
                )
                break

        # 检查 WHERE 子句是否有索引
        for tx in analysis.transactions:
            if tx.query and self._query_needs_index(tx):
                suggestions.append(
                    f"事务 {tx.transaction_id} 的查询可能缺少合适的索引，"
                    "建议检查 WHERE 条件列是否有索引覆盖。"
                )
                break

        # 通用建议
        suggestions.append(
            "建议在应用层添加重试机制，当捕获到死锁错误（ER_LOCK_DEADLOCK, 1213）时自动重试。"
        )

        return suggestions

    def generate_index_suggestions(self, analysis: DeadlockAnalysis) -> list[dict]:
        """生成索引优化建议

        检查：
        - WHERE 子句列是否有索引
        - 锁模式是否过于宽泛（表锁而非行锁）

        Args:
            analysis: 死锁分析对象

        Returns:
            建议列表，每项包含 table, suggested_index, reason
        """
        suggestions: list[dict] = []

        for tx in analysis.transactions:
            if not tx.query:
                continue

            # 从 SQL 中提取 WHERE 条件列
            where_cols = self._extract_where_columns(tx.query)
            if not where_cols:
                continue

            # 检查请求的锁是否使用了 PRIMARY 或有效索引
            for req_lock in tx.locks_requested:
                if req_lock.lock_type == "TABLE LOCK":
                    # 表级锁，建议添加索引以使用行级锁
                    suggestions.append({
                        "table": f"`{req_lock.database}`.`{req_lock.table}`",
                        "suggested_index": f"idx_{'_'.join(where_cols[:3])}",
                        "reason": "当前使用表级锁，添加索引可降低为行级锁，减少锁冲突范围",
                    })
                elif req_lock.index and req_lock.index.upper() not in ('PRIMARY', 'GEN_CLUST_INDEX'):
                    # 非主键索引，检查 WHERE 列是否被索引覆盖
                    index_cols = req_lock.index
                    for col in where_cols:
                        if col.lower() not in index_cols.lower():
                            suggestions.append({
                                "table": f"`{req_lock.database}`.`{req_lock.table}`",
                                "suggested_index": f"idx_{'_'.join(where_cols[:3])}",
                                "reason": f"WHERE 条件列 {col} 未被索引 {index_cols} 覆盖，建议添加复合索引",
                            })
                            break

            # 如果请求的锁没有索引信息，但有 WHERE 条件
            if not tx.locks_requested and where_cols:
                for table in tx.tables:
                    suggestions.append({
                        "table": table,
                        "suggested_index": f"idx_{'_'.join(where_cols[:3])}",
                        "reason": f"WHERE 条件列 {', '.join(where_cols)} 可能缺少索引",
                    })

        # 去重
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            key = (s["table"], s["suggested_index"])
            if key not in seen:
                seen.add(key)
                unique_suggestions.append(s)

        return unique_suggestions

    def _query_needs_index(self, tx: DeadlockTransaction) -> bool:
        """检查查询是否可能需要索引

        Args:
            tx: 事务对象

        Returns:
            是否可能需要索引
        """
        if not tx.query:
            return False

        # 简单检查：UPDATE/DELETE 有 WHERE 但请求的锁没有使用有效索引
        query_upper = tx.query.upper().strip()
        if not (query_upper.startswith('UPDATE') or query_upper.startswith('DELETE')):
            return False

        if 'WHERE' not in query_upper:
            return False

        # 检查请求的锁是否使用了主键
        for req_lock in tx.locks_requested:
            if req_lock.index and req_lock.index.upper() == 'PRIMARY':
                return False
            if req_lock.lock_type == 'TABLE LOCK':
                return True

        return True

    def _extract_where_columns(self, query: str) -> list[str]:
        """从 SQL 中提取 WHERE 条件列名

        Args:
            query: SQL 语句

        Returns:
            列名列表
        """
        columns = []
        where_match = re.search(r'\bWHERE\b(.+)', query, re.IGNORECASE)
        if not where_match:
            return columns

        where_clause = where_match.group(1)

        # 提取 col = ... 或 col IN (...) 中的列名
        col_pattern = re.compile(r'(\w+)\s*(?:=|!=|<>|>|<|>=|<=|\s+IN\s*\(|\s+BETWEEN\s+)', re.IGNORECASE)
        for match in col_pattern.finditer(where_clause):
            col = match.group(1)
            if col.upper() not in ('AND', 'OR', 'NOT', 'IN', 'BETWEEN', 'LIKE', 'IS', 'NULL'):
                columns.append(col)

        return columns

    def _assess_severity(self, analysis: DeadlockAnalysis) -> str:
        """评估死锁严重程度

        规则：
        - critical: 涉及 GAP 锁 + 跨表 + 长事务
        - high: 涉及 GAP 锁或跨表依赖
        - medium: 同表行级竞争
        - low: 简单锁冲突

        Args:
            analysis: 死锁分析对象

        Returns:
            严重程度 (low/medium/high/critical)
        """
        score = 0

        # GAP 锁加分
        for tx in analysis.transactions:
            for lock in tx.locks_held + tx.locks_requested:
                if 'GAP' in lock.lock_mode.upper():
                    score += 2
                    break

        # 跨表加分
        all_tables = set()
        for tx in analysis.transactions:
            for lock in tx.locks_held + tx.locks_requested:
                if lock.table:
                    all_tables.add(f"{lock.database}.{lock.table}")
        if len(all_tables) > 1:
            score += 2

        # 长事务加分
        for tx in analysis.transactions:
            if tx.rollback_weight > 0.5:
                score += 1

        # 事务数量加分
        if len(analysis.transactions) > 2:
            score += 1

        if score >= 5:
            return "critical"
        elif score >= 3:
            return "high"
        elif score >= 1:
            return "medium"
        return "low"

    async def analyze_from_logs(
        self,
        db,
        instance_id=None,
        start_time=None,
        end_time=None,
    ) -> list[DeadlockAnalysis]:
        """从数据库日志条目和原始日志文件中分析死锁

        首先尝试从原始日志文件中提取完整的死锁块（多行），
        然后回退到数据库中的单条日志。

        Args:
            db: DatabaseManager 实例
            instance_id: 可选的实例 ID 过滤
            start_time: 可选的开始时间
            end_time: 可选的结束时间

        Returns:
            DeadlockAnalysis 列表
        """
        results: list[DeadlockAnalysis] = []

        # 1. 尝试从原始日志文件中提取完整的死锁块
        log_paths = await self._get_log_paths(db, instance_id)
        for log_path in log_paths:
            try:
                import asyncio
                deadlock_blocks = await asyncio.to_thread(
                    self._extract_deadlock_blocks_from_file, log_path
                )
                for block in deadlock_blocks:
                    analysis = self.parse_deadlock_log(block)
                    if analysis:
                        results.append(analysis)
            except Exception as e:
                logger.warning("从日志文件提取死锁块失败 (%s): %s", log_path, e)

        # 2. 回退：从数据库中查询单条死锁日志
        if not results:
            conn = await db._get_conn()

            conditions = []
            params: list = []

            if instance_id is not None:
                conditions.append("instance_id = ?")
                params.append(instance_id)
            if start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("timestamp <= ?")
                params.append(end_time)

            deadlock_conditions = conditions.copy()
            deadlock_conditions.append(
                "(category = 'deadlock' OR message LIKE '%DEADLOCK%' OR message LIKE '%Deadlock%' OR raw_line LIKE '%DEADLOCK%' OR raw_line LIKE '%Deadlock%')"
            )
            where_clause = " AND ".join(deadlock_conditions)

            cursor = await conn.execute(
                f"""SELECT id, instance_id, timestamp, message, raw_line
                    FROM log_entries
                    WHERE {where_clause}
                    ORDER BY timestamp DESC""",
                params,
            )
            rows = await cursor.fetchall()

            for row in rows:
                raw_text = row["raw_line"] or row["message"] or ""
                if not raw_text:
                    continue

                analysis = self.parse_deadlock_log(raw_text)
                if analysis:
                    if not analysis.timestamp and row["timestamp"]:
                        analysis.timestamp = row["timestamp"]
                    results.append(analysis)

        # 将分析结果存入 deadlock_analyses 表
        if results:
            await self._ensure_deadlock_table(db)
            for analysis in results:
                await self._save_analysis(db, analysis, instance_id)

        return results

    async def _get_log_paths(self, db, instance_id=None) -> list[str]:
        """获取日志文件路径列表"""
        paths = []
        try:
            conn = await db._get_conn()
            if instance_id is not None:
                cursor = await conn.execute(
                    "SELECT log_path FROM instances WHERE id = ?", (instance_id,)
                )
            else:
                cursor = await conn.execute(
                    "SELECT DISTINCT log_path FROM instances WHERE log_path IS NOT NULL"
                )
            rows = await cursor.fetchall()
            for row in rows:
                path = row["log_path"]
                if path:
                    from pathlib import Path
                    if Path(path).exists():
                        paths.append(path)
        except Exception as e:
            logger.warning("获取日志路径失败: %s", e)
        return paths

    def _extract_deadlock_blocks_from_file(self, log_path: str) -> list[str]:
        """从日志文件中提取完整的死锁块

        MySQL 8.0 死锁日志格式：
        - 以 "Deadlock found" 或 "LATEST DETECTED DEADLOCK" 开始
        - 包含多个 TRANSACTION 块
        - 以 "WE ROLL BACK TRANSACTION" 结束

        Returns:
            死锁块文本列表
        """
        blocks = []
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception:
            return blocks

        current_block: list[str] = []
        in_deadlock_block = False

        for line in lines:
            # 检测死锁块开始
            if 'Deadlock found' in line or 'LATEST DETECTED DEADLOCK' in line:
                if current_block and in_deadlock_block:
                    # 保存前一个块
                    blocks.append(''.join(current_block))
                current_block = [line]
                in_deadlock_block = True
                continue

            if in_deadlock_block:
                current_block.append(line)
                # 检测死锁块结束
                if 'WE ROLL BACK TRANSACTION' in line:
                    blocks.append(''.join(current_block))
                    current_block = []
                    in_deadlock_block = False

        # 处理未结束的块
        if current_block and in_deadlock_block:
            blocks.append(''.join(current_block))

        return blocks

    async def _ensure_deadlock_table(self, db):
        """确保 deadlock_analyses 表存在"""
        conn = await db._get_conn()
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS deadlock_analyses (
                id TEXT PRIMARY KEY,
                instance_id INTEGER,
                timestamp TEXT NOT NULL,
                raw_text TEXT,
                root_cause TEXT,
                suggestions_json TEXT,
                severity TEXT DEFAULT 'medium',
                affected_tables_json TEXT,
                index_suggestions_json TEXT,
                transactions_json TEXT,
                lock_chain_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instance_id) REFERENCES instances(id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deadlock_analyses_timestamp
                ON deadlock_analyses(timestamp)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deadlock_analyses_severity
                ON deadlock_analyses(severity)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deadlock_analyses_instance_id
                ON deadlock_analyses(instance_id)
        """)
        await conn.commit()

    async def _save_analysis(self, db, analysis: DeadlockAnalysis, instance_id=None):
        """保存分析结果到数据库"""
        conn = await db._get_conn()
        now = datetime.now().isoformat()

        # 检查是否已存在
        cursor = await conn.execute(
            "SELECT id FROM deadlock_analyses WHERE id = ?",
            (analysis.id,),
        )
        if await cursor.fetchone():
            return  # 已存在，不重复插入

        await conn.execute(
            """INSERT INTO deadlock_analyses
               (id, instance_id, timestamp, raw_text, root_cause,
                suggestions_json, severity, affected_tables_json,
                index_suggestions_json, transactions_json, lock_chain_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis.id,
                instance_id,
                analysis.timestamp,
                analysis.raw_text,
                analysis.root_cause,
                json.dumps(analysis.suggestions, ensure_ascii=False),
                analysis.severity,
                json.dumps(analysis.affected_tables, ensure_ascii=False),
                json.dumps(analysis.index_suggestions, ensure_ascii=False),
                json.dumps([self._tx_to_dict(tx) for tx in analysis.transactions], ensure_ascii=False),
                json.dumps(self._chain_to_dict(analysis.lock_chain), ensure_ascii=False),
                now,
            ),
        )
        await conn.commit()

    def _tx_to_dict(self, tx: DeadlockTransaction) -> dict:
        """将 DeadlockTransaction 转为可序列化的字典"""
        return {
            "transaction_id": tx.transaction_id,
            "thread_id": tx.thread_id,
            "query": tx.query,
            "tables": tx.tables,
            "locks_held": [asdict(lock) for lock in tx.locks_held],
            "locks_requested": [asdict(lock) for lock in tx.locks_requested],
            "wait_for": tx.wait_for,
            "rollback_weight": tx.rollback_weight,
        }

    def _chain_to_dict(self, chain: DeadlockChain) -> dict:
        """将 DeadlockChain 转为可序列化的字典"""
        return {
            "chain": chain.chain,
            "cycle_detected": chain.cycle_detected,
            "victim": chain.victim,
        }

    def to_dict(self, analysis: DeadlockAnalysis) -> dict:
        """将分析结果转换为字典，用于 JSON 序列化

        Args:
            analysis: 死锁分析对象

        Returns:
            可 JSON 序列化的字典
        """
        return {
            "id": analysis.id,
            "timestamp": analysis.timestamp,
            "raw_text": analysis.raw_text,
            "transactions": [self._tx_to_dict(tx) for tx in analysis.transactions],
            "lock_chain": self._chain_to_dict(analysis.lock_chain),
            "root_cause": analysis.root_cause,
            "suggestions": analysis.suggestions,
            "severity": analysis.severity,
            "affected_tables": analysis.affected_tables,
            "index_suggestions": analysis.index_suggestions,
        }
