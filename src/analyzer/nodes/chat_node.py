"""对话节点 - 基于分析结果上下文回答用户问题"""

import json
import logging

from src.analyzer.llm import LLMManager

logger = logging.getLogger(__name__)


def _build_context_text(context: dict) -> str:
    """将分析结果上下文构建为文本"""
    parts = []

    if context.get("summary"):
        parts.append(f"分析摘要：{context['summary']}")

    if context.get("suggestions"):
        suggestions_text = "\n".join(
            f"- [{s.get('priority', 'low')}] {s.get('category', '')}: {s.get('suggestion', '')}"
            for s in context["suggestions"]
        )
        parts.append(f"修复建议：\n{suggestions_text}")

    if context.get("correlations"):
        correlations = context["correlations"]

        time_patterns = correlations.get("time_patterns", [])
        if time_patterns:
            patterns_text = "\n".join(
                f"- {p.get('description', '')}" for p in time_patterns
            )
            parts.append(f"时间分布模式：\n{patterns_text}")

        cross_category = correlations.get("cross_category", [])
        if cross_category:
            cross_text = "\n".join(
                f"- {c.get('description', '')}" for c in cross_category
            )
            parts.append(f"跨类别关联：\n{cross_text}")

        anomalies = correlations.get("anomalies", [])
        if anomalies:
            anomalies_text = "\n".join(
                f"- {a.get('description', '')}" for a in anomalies
            )
            parts.append(f"异常频率：\n{anomalies_text}")

    if context.get("classified_logs"):
        # 只展示统计信息
        category_counts = {}
        for log in context["classified_logs"]:
            cat = log.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        counts_text = ", ".join(f"{k}: {v}" for k, v in sorted(category_counts.items()))
        parts.append(f"错误分类统计：{counts_text}")

    return "\n\n".join(parts)


class ChatNode:
    """对话节点：基于分析结果上下文回答用户问题"""

    def __init__(self, llm_manager: LLMManager | None = None):
        self._llm_manager = llm_manager

    async def __call__(self, state: dict) -> dict:
        """执行对话

        输入状态：
            - messages: list[dict] 对话历史
            - context: dict 可选的分析结果上下文

        输出状态：
            - 增加 response 字段
        """
        messages = state.get("messages", [])
        context = state.get("context")

        logger.info("对话节点: 处理对话，消息数=%d", len(messages))

        if not messages:
            return {"response": "请输入您的问题。"}

        if not self._llm_manager:
            return {"response": "LLM 未配置，无法进行对话分析。"}

        # 构建系统提示
        system_content = (
            "你是一个 MySQL 数据库错误日志分析专家。"
            "请根据提供的分析结果上下文，回答用户关于 MySQL 错误日志的问题。"
            "回答应该专业、准确、有针对性。如果上下文中没有相关信息，请如实说明。"
        )

        if context:
            context_text = _build_context_text(context)
            system_content += f"\n\n当前分析结果上下文：\n{context_text}"

        # 构建 LLM 消息
        llm_messages = [{"role": "system", "content": system_content}]

        # 添加对话历史（最多保留最近 10 轮）
        recent_messages = messages[-20:]
        for msg in recent_messages:
            llm_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        try:
            response = await self._llm_manager.ainvoke(llm_messages)
            logger.info("对话节点: LLM 响应完成")
            return {"response": response}
        except Exception as e:
            logger.error("对话节点: LLM 调用失败: %s", e)
            return {"response": f"抱歉，对话分析出现错误：{e}"}
