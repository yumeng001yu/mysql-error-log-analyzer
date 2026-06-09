"""摘要节点 - 使用 LLM 生成分析摘要和建议"""

import json
import logging

from src.analyzer.llm import LLMManager

logger = logging.getLogger(__name__)


def _build_summary_prompt(classified_logs: list[dict], correlations: dict) -> str:
    """构建摘要生成提示词"""
    # 统计各类别数量
    category_counts = {}
    for log in classified_logs:
        cat = log.get("category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # 收集各类别的代表性日志（最多 3 条）
    category_samples = {}
    for log in classified_logs:
        cat = log.get("category", "other")
        if cat not in category_samples:
            category_samples[cat] = []
        if len(category_samples[cat]) < 3:
            category_samples[cat].append(log.get("message", "")[:150])

    # 构建日志摘要
    log_summary_lines = []
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        samples = category_samples.get(cat, [])
        samples_text = "; ".join(samples)
        log_summary_lines.append(f"- {cat}: {count} 条, 示例: {samples_text}")

    log_summary = "\n".join(log_summary_lines)

    # 构建关联信息
    correlation_text = ""
    if correlations:
        time_patterns = correlations.get("time_patterns", [])
        cross_category = correlations.get("cross_category", [])
        anomalies = correlations.get("anomalies", [])

        if time_patterns:
            correlation_text += "\n时间分布模式:\n"
            for p in time_patterns:
                correlation_text += f"- {p.get('description', '')}\n"

        if cross_category:
            correlation_text += "\n跨类别关联:\n"
            for c in cross_category:
                correlation_text += f"- {c.get('description', '')}\n"

        if anomalies:
            correlation_text += "\n异常频率:\n"
            for a in anomalies:
                correlation_text += f"- {a.get('description', '')}\n"

    prompt = f"""你是一个 MySQL 数据库专家，请根据以下 MySQL 错误日志分析结果，生成：

1. 整体摘要：简要概括日志中反映的主要问题
2. 各类错误的修复建议：针对每个错误类别给出具体的修复建议
3. 关键错误优先级排序：按严重程度对错误类别排序

日志统计：
{log_summary}

{correlation_text}

请返回 JSON 格式结果，格式如下：
{{
    "summary": "整体摘要文本",
    "suggestions": [
        {{"category": "connection", "suggestion": "修复建议", "priority": "high"}},
        ...
    ]
}}

priority 可选值: high, medium, low

请只返回 JSON，不要包含其他文字。"""

    return prompt


class SummarizeNode:
    """摘要节点：使用 LLM 生成整体摘要、修复建议和优先级排序"""

    def __init__(self, llm_manager: LLMManager | None = None):
        self._llm_manager = llm_manager

    async def __call__(self, state: dict) -> dict:
        """执行摘要生成

        输入状态：
            - classified_logs: list[dict]
            - correlations: dict

        输出状态：
            - 增加 summary 和 suggestions 字段
        """
        classified_logs = state.get("classified_logs", [])
        correlations = state.get("correlations", {})

        logger.info("摘要节点: 开始处理 %d 条分类日志", len(classified_logs))

        if not classified_logs:
            return {
                "summary": "没有发现错误日志。",
                "suggestions": [],
            }

        # 尝试使用 LLM 生成摘要
        if self._llm_manager:
            result = await self._llm_summarize(classified_logs, correlations)
            if result:
                return result

        # 回退到基于规则的摘要
        return self._rule_based_summarize(classified_logs, correlations)

    async def _llm_summarize(
        self, classified_logs: list[dict], correlations: dict
    ) -> dict | None:
        """使用 LLM 生成摘要"""
        prompt = _build_summary_prompt(classified_logs, correlations)
        messages = [
            {"role": "system", "content": "你是一个 MySQL 数据库专家，只返回 JSON 格式的分析结果。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self._llm_manager.ainvoke(messages)
            result = json.loads(response.strip())

            summary = result.get("summary", "")
            suggestions = result.get("suggestions", [])

            logger.info("摘要节点: LLM 生成摘要完成")
            return {"summary": summary, "suggestions": suggestions}

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("LLM 摘要结果解析失败: %s，回退到规则摘要", e)
            return None
        except Exception as e:
            logger.error("LLM 摘要调用失败: %s，回退到规则摘要", e)
            return None

    def _rule_based_summarize(
        self, classified_logs: list[dict], correlations: dict
    ) -> dict:
        """基于规则的摘要生成（LLM 不可用时的回退方案）"""
        # 统计各类别数量
        category_counts = {}
        for log in classified_logs:
            cat = log.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # 生成摘要
        total = len(classified_logs)
        top_categories = sorted(category_counts.items(), key=lambda x: -x[1])[:3]
        top_desc = "、".join(f"{cat}({count}条)" for cat, count in top_categories)

        summary = f"共发现 {total} 条错误日志，主要类别为：{top_desc}。"

        # 添加关联信息到摘要
        anomalies = correlations.get("anomalies", [])
        if anomalies:
            summary += f" 发现 {len(anomalies)} 个异常频率。"
        cross_category = correlations.get("cross_category", [])
        if cross_category:
            summary += f" 发现 {len(cross_category)} 个跨类别关联。"

        # 生成建议
        priority_map = {
            "crash": "high",
            "deadlock": "high",
            "innodb": "high",
            "replication": "high",
            "memory": "high",
            "connection": "medium",
            "permission": "medium",
            "performance": "medium",
            "configuration": "low",
            "other": "low",
        }

        suggestion_map = {
            "crash": "检查 MySQL 崩溃原因，查看错误日志和系统日志，确认是否有硬件故障或内存问题。",
            "deadlock": "分析死锁日志，优化事务逻辑，减少锁竞争，考虑调整锁获取顺序。",
            "innodb": "检查 InnoDB 状态，确认表空间和缓冲池配置是否合理，排查数据损坏问题。",
            "replication": "检查主从复制状态，确认网络连接和权限配置，排查复制延迟原因。",
            "memory": "检查 MySQL 内存配置，调整 buffer pool 大小，排查内存泄漏。",
            "connection": "检查 max_connections 配置，排查连接泄漏，考虑使用连接池。",
            "permission": "检查用户权限配置，确认认证信息正确，审查访问控制策略。",
            "performance": "分析慢查询日志，优化 SQL 语句和索引，调整相关参数。",
            "configuration": "检查 MySQL 配置文件，确认参数设置正确，移除废弃选项。",
            "other": "进一步分析日志内容，确定具体问题类型。",
        }

        suggestions = []
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            suggestions.append({
                "category": cat,
                "suggestion": suggestion_map.get(cat, suggestion_map["other"]),
                "priority": priority_map.get(cat, "low"),
            })

        logger.info("摘要节点: 规则摘要生成完成")
        return {"summary": summary, "suggestions": suggestions}
