"""分类节点 - 使用 LLM 对日志进行智能分类"""

import json
import logging

from src.analyzer.llm import LLMManager

logger = logging.getLogger(__name__)

# 分类体系
CATEGORIES = [
    "connection",
    "permission",
    "innodb",
    "replication",
    "crash",
    "deadlock",
    "memory",
    "configuration",
    "performance",
    "other",
]

# 基于规则的关键词分类（作为 LLM 分类的补充和快速路径）
_RULE_KEYWORDS = {
    "connection": [
        "access denied", "connection", "host", "too many connections",
        "connect", "client", "handshake", "authentication",
        "Can't connect", "Lost connection",
    ],
    "permission": [
        "access denied", "permission", "privilege", "grant",
        "denied for user",
    ],
    "innodb": [
        "InnoDB", "innodb", "ibdata", "ib_logfile", "tablespace",
        "buffer pool", "flushing", "dirty page",
    ],
    "replication": [
        "replication", "slave", "master", "relay log", "binlog",
        "gtid", "io thread", "sql thread", "replica",
        "Slave_IO_Running", "Slave_SQL_Running",
    ],
    "crash": [
        "crash", "shutdown", "abort", "segfault", "signal",
        "core dump", "terminated", "killed",
    ],
    "deadlock": [
        "deadlock", "lock wait timeout", "lock deadlock",
        "Deadlock found",
    ],
    "memory": [
        "out of memory", "memory", "malloc", "alloc",
        "OOM", "cannot allocate",
    ],
    "configuration": [
        "option", "config", "setting", "unknown variable",
        "deprecated", "startup option",
    ],
    "performance": [
        "slow query", "timeout", "long running", "performance",
        "waiting for", "lock wait",
    ],
}


def _rule_based_classify(message: str) -> str | None:
    """基于规则的快速分类"""
    message_lower = message.lower()
    for category, keywords in _RULE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in message_lower:
                return category
    return None


def _build_classify_prompt(logs: list[dict]) -> str:
    """构建分类提示词"""
    log_summaries = []
    for i, log in enumerate(logs):
        msg = log.get("message", "")[:200]
        level = log.get("level", "")
        subsystem = log.get("subsystem", "")
        log_summaries.append(f"[{i}] level={level}, subsystem={subsystem}: {msg}")

    logs_text = "\n".join(log_summaries)

    prompt = f"""你是一个 MySQL 错误日志分类专家。请对以下 MySQL 错误日志进行分类。

分类体系：
{", ".join(CATEGORIES)}

分类说明：
- connection: 连接相关错误（连接拒绝、认证失败、连接数过多等）
- permission: 权限相关错误（访问被拒绝、权限不足等）
- innodb: InnoDB 存储引擎相关错误
- replication: 主从复制相关错误
- crash: 崩溃相关错误（崩溃、异常终止等）
- deadlock: 死锁相关错误
- memory: 内存相关错误（内存不足等）
- configuration: 配置相关错误（参数错误、配置项无效等）
- performance: 性能相关错误（慢查询、超时等）
- other: 无法归入以上类别的错误

请对每条日志进行分类，返回 JSON 格式结果，格式如下：
{{"classifications": [{{"index": 0, "category": "connection"}}, ...]}}

日志内容：
{logs_text}

请只返回 JSON，不要包含其他文字。"""

    return prompt


class ClassifyNode:
    """分类节点：使用 LLM 对日志进行智能分类"""

    def __init__(self, llm_manager: LLMManager | None = None):
        self._llm_manager = llm_manager

    async def __call__(self, state: dict) -> dict:
        """执行分类

        输入状态：
            - parsed_logs: list[dict]

        输出状态：
            - 增加 classified_logs 字段，每条日志带 category
        """
        parsed_logs = state.get("parsed_logs", [])
        logger.info("分类节点: 开始处理 %d 条日志", len(parsed_logs))

        if not parsed_logs:
            return {"classified_logs": []}

        # 先进行规则分类
        classified_logs = []
        unclassified_indices = []

        for i, log in enumerate(parsed_logs):
            log_copy = dict(log)
            rule_category = _rule_based_classify(log.get("message", ""))
            if rule_category:
                log_copy["category"] = rule_category
            else:
                unclassified_indices.append(i)
            classified_logs.append(log_copy)

        # 对规则无法分类的日志使用 LLM
        if unclassified_indices and self._llm_manager:
            await self._llm_classify(classified_logs, unclassified_indices)

        # 确保所有日志都有 category
        for log in classified_logs:
            log.setdefault("category", "other")

        logger.info(
            "分类节点: 完成，分类结果: %s",
            {cat: sum(1 for l in classified_logs if l.get("category") == cat) for cat in CATEGORIES},
        )
        return {"classified_logs": classified_logs}

    async def _llm_classify(self, logs: list[dict], indices: list[int]) -> None:
        """使用 LLM 对指定索引的日志进行分类"""
        unclassified_logs = [logs[i] for i in indices]

        # 分批处理，每批最多 20 条
        batch_size = 20
        for batch_start in range(0, len(unclassified_logs), batch_size):
            batch = unclassified_logs[batch_start:batch_start + batch_size]
            batch_indices = indices[batch_start:batch_start + batch_size]

            prompt = _build_classify_prompt(batch)
            messages = [
                {"role": "system", "content": "你是一个 MySQL 错误日志分类专家，只返回 JSON 格式的分类结果。"},
                {"role": "user", "content": prompt},
            ]

            try:
                response = await self._llm_manager.ainvoke(messages)
                result = json.loads(response.strip())

                classifications = result.get("classifications", [])
                for item in classifications:
                    idx = item.get("index", -1)
                    category = item.get("category", "other")
                    if 0 <= idx < len(batch) and category in CATEGORIES:
                        logs[batch_indices[idx]]["category"] = category

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("LLM 分类结果解析失败: %s，回退到 other", e)
            except Exception as e:
                logger.error("LLM 分类调用失败: %s", e)
