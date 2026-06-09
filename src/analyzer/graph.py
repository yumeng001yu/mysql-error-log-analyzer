"""LangGraph 工作流 - 分析引擎核心"""

import logging
from typing import TypedDict

from langgraph.graph import END, StateGraph

from src.analyzer.llm import LLMManager
from src.analyzer.nodes.chat_node import ChatNode
from src.analyzer.nodes.classify_node import ClassifyNode
from src.analyzer.nodes.correlate_node import CorrelateNode
from src.analyzer.nodes.parse_node import ParseNode
from src.analyzer.nodes.summarize_node import SummarizeNode
from src.config import Config

logger = logging.getLogger(__name__)


class AnalysisState(TypedDict):
    """分析工作流状态定义"""
    instance_id: str
    time_range: dict  # {"start": datetime, "end": datetime}
    raw_logs: list[dict]
    parsed_logs: list[dict]
    classified_logs: list[dict]
    correlations: list[dict]
    summary: str
    suggestions: list[dict]
    messages: list[dict]
    response: str


class ChatState(TypedDict):
    """对话工作流状态定义"""
    messages: list[dict]
    context: dict | None
    response: str


class AnalysisGraph:
    """分析引擎工作流管理器"""

    def __init__(self, config: Config | None = None):
        self._config = config or Config()
        self._llm_manager = LLMManager(self._config)

        # 初始化节点
        self._parse_node = ParseNode()
        self._classify_node = ClassifyNode(self._llm_manager)
        self._correlate_node = CorrelateNode()
        self._summarize_node = SummarizeNode(self._llm_manager)
        self._chat_node = ChatNode(self._llm_manager)

        # 构建分析工作流图
        self._analysis_graph = self._build_analysis_graph()

        # 构建对话工作流图
        self._chat_graph = self._build_chat_graph()

    def _build_analysis_graph(self) -> StateGraph:
        """构建分析工作流图: parse → classify → correlate → summarize"""
        graph = StateGraph(AnalysisState)

        # 添加节点
        graph.add_node("parse", self._parse_node)
        graph.add_node("classify", self._classify_node)
        graph.add_node("correlate", self._correlate_node)
        graph.add_node("summarize", self._summarize_node)

        # 设置入口
        graph.set_entry_point("parse")

        # 添加边
        graph.add_edge("parse", "classify")
        graph.add_edge("classify", "correlate")
        graph.add_edge("correlate", "summarize")
        graph.add_edge("summarize", END)

        return graph.compile()

    def _build_chat_graph(self) -> StateGraph:
        """构建对话工作流图: chat_node"""
        graph = StateGraph(ChatState)

        graph.add_node("chat", self._chat_node)
        graph.set_entry_point("chat")
        graph.add_edge("chat", END)

        return graph.compile()

    async def run_analysis(self, instance_id: str, time_range: dict) -> dict:
        """运行完整分析流程

        Args:
            instance_id: MySQL 实例 ID
            time_range: 时间范围 {"start": datetime, "end": datetime}

        Returns:
            分析结果字典
        """
        logger.info("开始分析流程: instance_id=%s, time_range=%s", instance_id, time_range)

        initial_state = {
            "instance_id": instance_id,
            "time_range": time_range,
            "raw_logs": [],
            "parsed_logs": [],
            "classified_logs": [],
            "correlations": [],
            "summary": "",
            "suggestions": [],
            "messages": [],
            "response": "",
        }

        # 如果 raw_logs 为空，尝试从存储加载
        if not initial_state["raw_logs"]:
            initial_state["raw_logs"] = await self._load_logs(instance_id, time_range)

        result = await self._analysis_graph.ainvoke(initial_state)

        logger.info("分析流程完成: instance_id=%s", instance_id)
        return result

    async def run_chat(self, messages: list[dict], context: dict = None) -> str:
        """运行对话

        Args:
            messages: 对话历史 [{"role": "user/assistant", "content": "..."}]
            context: 可选的分析结果上下文

        Returns:
            LLM 响应文本
        """
        logger.info("开始对话: 消息数=%d", len(messages))

        initial_state = {
            "messages": messages,
            "context": context,
            "response": "",
        }

        result = await self._chat_graph.ainvoke(initial_state)

        logger.info("对话完成")
        return result.get("response", "")

    async def check_critical_errors(self, logs: list[dict]) -> list[dict]:
        """检查关键错误并生成建议

        Args:
            logs: 原始日志列表

        Returns:
            关键错误列表，每项包含日志信息和修复建议
        """
        logger.info("检查关键错误: %d 条日志", len(logs))

        critical_levels = self._config.get("analyzer", "critical_levels") or ["CRITICAL", "ERROR"]
        critical_keywords = self._config.get("analyzer", "critical_keywords") or [
            "crash", "shutdown", "abort",
            "InnoDB: corruption", "replication",
            "slave_io_running", "deadlock",
        ]

        critical_errors = []

        for log in logs:
            level = (log.get("level") or "").upper()
            message = log.get("message", "")

            is_critical = False

            # 检查错误级别
            for cl in critical_levels:
                if cl.upper() in level:
                    is_critical = True
                    break

            # 检查关键词
            if not is_critical:
                for keyword in critical_keywords:
                    if keyword.lower() in message.lower():
                        is_critical = True
                        break

            if is_critical:
                error_entry = dict(log)
                error_entry["is_critical"] = True
                error_entry["suggestion"] = self._generate_critical_suggestion(log)
                critical_errors.append(error_entry)

        logger.info("发现 %d 个关键错误", len(critical_errors))
        return critical_errors

    def _generate_critical_suggestion(self, log: dict) -> str:
        """为关键错误生成快速建议"""
        message = log.get("message", "").lower()

        if "crash" in message or "shutdown" in message or "abort" in message:
            return "MySQL 可能发生崩溃，请立即检查错误日志和系统日志，确认崩溃原因。"
        if "innodb" in message and "corruption" in message:
            return "检测到 InnoDB 数据损坏，请立即备份数据并运行 innodb_force_recovery 模式检查。"
        if "replication" in message or "slave" in message:
            return "复制出现异常，请检查主从连接状态、网络和权限配置。"
        if "deadlock" in message:
            return "检测到死锁，请分析死锁日志并优化事务逻辑。"
        if "memory" in message or "out of memory" in message:
            return "内存不足，请检查 buffer pool 配置和系统内存使用情况。"

        return "检测到关键错误，请尽快排查。"

    async def _load_logs(self, instance_id: str, time_range: dict) -> list[dict]:
        """从存储加载日志（预留接口）"""
        # TODO: 对接 storage 模块加载日志
        logger.warning("日志加载功能尚未实现，请通过 raw_logs 参数传入日志")
        return []
