"""LLM 接口模块，支持 OpenAI / Ollama / Custom 提供商"""

import logging
import os

from src.config import Config

logger = logging.getLogger(__name__)


class LLMManager:
    """LLM 管理器，根据配置初始化不同的 Chat Model"""

    def __init__(self, config: Config | None = None):
        self._config = config or Config()
        self._chat_model = self._init_chat_model()

    def _init_chat_model(self):
        """根据配置初始化 Chat Model 实例"""
        provider = (
            os.environ.get("MYSQL_ANALYZER_LLM_PROVIDER")
            or self._config.get("llm", "provider")
            or "openai"
        )
        model = (
            os.environ.get("MYSQL_ANALYZER_LLM_MODEL")
            or self._config.get("llm", "model")
            or "gpt-4"
        )
        api_base = (
            os.environ.get("MYSQL_ANALYZER_LLM_API_BASE")
            or self._config.get("llm", "api_base")
            or ""
        )
        api_key = (
            os.environ.get("MYSQL_ANALYZER_LLM_API_KEY")
            or self._config.get("llm", "api_key")
            or ""
        )
        timeout = self._config.get("llm", "timeout") or 60
        temperature = self._config.get("llm", "temperature") or 0.3

        provider = provider.lower().strip()

        if provider == "ollama":
            from langchain_community.chat_models import ChatOllama

            kwargs = {
                "model": model,
                "temperature": temperature,
            }
            if api_base:
                kwargs["base_url"] = api_base
            chat_model = ChatOllama(**kwargs)
            logger.info("LLM 初始化: provider=ollama, model=%s", model)

        elif provider == "custom":
            from langchain_openai import ChatOpenAI

            chat_model = ChatOpenAI(
                model=model,
                api_key=api_key or "not-needed",
                base_url=api_base,
                timeout=timeout,
                temperature=temperature,
            )
            logger.info("LLM 初始化: provider=custom, model=%s, api_base=%s", model, api_base)

        else:  # openai
            from langchain_openai import ChatOpenAI

            kwargs = {
                "model": model,
                "api_key": api_key or "not-needed",
                "timeout": timeout,
                "temperature": temperature,
            }
            if api_base:
                kwargs["base_url"] = api_base
            chat_model = ChatOpenAI(**kwargs)
            logger.info("LLM 初始化: provider=openai, model=%s", model)

        return chat_model

    def get_chat_model(self):
        """返回 ChatModel 实例"""
        return self._chat_model

    async def ainvoke(self, messages: list) -> str:
        """异步调用 LLM

        Args:
            messages: 消息列表，格式为 [{"role": "...", "content": "..."}]

        Returns:
            LLM 响应文本
        """
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        try:
            response = await self._chat_model.ainvoke(lc_messages)
            return response.content
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            raise
