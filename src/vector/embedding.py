"""Embedding 管理器，支持 Ollama / OpenAI / Custom 提供商"""

import logging

import httpx

from src.config import Config

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """Embedding 管理器，根据配置初始化不同的 Embedding 提供商"""

    def __init__(self, config: Config | None = None):
        self._config = config or Config()
        self._enabled: bool = self._config.get("embedding", "enabled", default=False)
        self._provider: str = self._config.get("embedding", "provider", default="ollama")
        self._model: str = self._config.get("embedding", "model", default="nomic-embed-text")
        self._api_base: str = self._config.get("embedding", "api_base", default="")
        self._api_key: str | None = self._config.get("embedding", "api_key", default=None)
        self._dim: int = self._config.get("embedding", "dim", default=768)
        self._batch_size: int = self._config.get("embedding", "batch_size", default=32)

        # 设置默认 api_base
        if not self._api_base:
            if self._provider == "ollama":
                self._api_base = "http://localhost:11434"
            elif self._provider == "openai":
                self._api_base = "https://api.openai.com/v1"
            else:
                self._api_base = "http://localhost:8000/v1"

        self._client: httpx.AsyncClient | None = None

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def is_available(self) -> bool:
        """Embedding 是否可用"""
        return bool(self._enabled)

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 httpx 异步客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def embed(self, text: str) -> list[float]:
        """嵌入单条文本，不可用时返回空列表"""
        if not self.is_available():
            return []
        try:
            results = await self.embed_batch([text])
            return results[0] if results else []
        except Exception:
            logger.exception("Embedding 单条文本失败")
            return []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本，不可用时返回空列表"""
        if not self.is_available():
            return []
        if not texts:
            return []

        try:
            if self._provider == "ollama":
                return await self._embed_ollama(texts)
            elif self._provider in ("openai", "custom"):
                return await self._embed_openai_compatible(texts)
            else:
                logger.warning("未知的 embedding provider: %s", self._provider)
                return []
        except Exception:
            logger.exception("批量 Embedding 失败")
            return []

    async def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """调用 Ollama Embedding API"""
        client = await self._get_client()
        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            embeddings = []
            for text in batch:
                resp = await client.post(
                    f"{self._api_base}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings.append(data.get("embedding", []))
            results.extend(embeddings)
        return results

    async def _embed_openai_compatible(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI 兼容 Embedding API（OpenAI / Custom）"""
        client = await self._get_client()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            resp = await client.post(
                f"{self._api_base}/embeddings",
                headers=headers,
                json={"model": self._model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = [item["embedding"] for item in data.get("data", [])]
            results.extend(embeddings)
        return results

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
