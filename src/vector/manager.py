"""向量搜索管理器（门面模式），统一管理 Embedding 和 Index"""

import logging
from datetime import datetime

from src.config import Config
from src.vector.embedding import EmbeddingManager
from src.vector.index import VectorIndex

logger = logging.getLogger(__name__)


class VectorSearchManager:
    """向量搜索管理器，统一管理 EmbeddingManager 和 VectorIndex"""

    def __init__(self, config: Config | None = None):
        self._config = config or Config()
        self._embedding = EmbeddingManager(self._config)
        self._index = VectorIndex(self._config)

    @property
    def embedding(self) -> EmbeddingManager:
        return self._embedding

    @property
    def index(self) -> VectorIndex:
        return self._index

    def is_available(self) -> bool:
        """Embedding 和 Index 都可用时返回 True"""
        return self._embedding.is_available() and self._index.is_available()

    async def initialize(self):
        """初始化

        如果 embedding 可用，初始化 index（dim 从 embedding.dim 获取）；
        否则跳过。
        """
        if not self._embedding.is_available():
            logger.info("Embedding 未启用，向量搜索功能不可用")
            return

        try:
            await self._index.initialize(dim=self._embedding.dim)
            if self._index.is_available():
                logger.info("向量搜索功能已初始化")
            else:
                logger.warning("向量索引初始化失败，向量搜索功能不可用")
        except Exception:
            logger.exception("初始化向量搜索管理器失败")

    async def index_logs(self, log_entries: list[dict]):
        """将日志条目索引到向量库

        对每条日志的 message 字段生成 embedding，
        使用数据库 id 作为向量 id，
        批量处理（batch_size 从配置获取）。
        不可用时静默跳过。
        """
        if not self._embedding.is_available() or not self._index.is_available():
            return

        if not log_entries:
            return

        try:
            batch_size = self._embedding.batch_size
            for i in range(0, len(log_entries), batch_size):
                batch = log_entries[i : i + batch_size]
                texts = [entry.get("message", "") for entry in batch]
                ids = [entry.get("id", i + j) for j, entry in enumerate(batch)]

                # 过滤掉空文本
                valid_items = [
                    (id_, text) for id_, text in zip(ids, texts) if text.strip()
                ]
                if not valid_items:
                    continue

                valid_ids, valid_texts = zip(*valid_items)
                vectors = await self._embedding.embed_batch(list(valid_texts))
                if vectors:
                    await self._index.add_vectors(list(valid_ids), vectors)

            logger.info("索引了 %d 条日志", len(log_entries))
        except Exception:
            logger.exception("索引日志失败")

    async def search_similar(
        self,
        query: str,
        k: int = 10,
        time_range: dict | None = None,
    ) -> list[dict]:
        """语义搜索

        query → embedding → turbovec.search → 返回相似日志。
        如果提供了 time_range，搜索后按时间过滤。
        不可用时返回空列表。
        """
        if not self.is_available():
            return []

        try:
            query_vector = await self._embedding.embed(query)
            if not query_vector:
                return []

            results = await self._index.search(query_vector, k=k)

            # 时间范围过滤
            if time_range and results:
                results = self._filter_by_time_range(results, time_range)

            return results
        except Exception:
            logger.exception("语义搜索失败")
            return []

    async def search_by_vector(
        self,
        query_vector: list[float],
        k: int = 10,
    ) -> list[dict]:
        """直接用向量搜索"""
        if not self._index.is_available():
            return []

        try:
            return await self._index.search(query_vector, k=k)
        except Exception:
            logger.exception("向量搜索失败")
            return []

    def _filter_by_time_range(
        self, results: list[dict], time_range: dict
    ) -> list[dict]:
        """按时间范围过滤搜索结果

        time_range 格式: {"start": "2024-01-01", "end": "2024-12-31"}
        注意：由于向量索引不存储时间信息，此过滤依赖外部数据，
        需要调用方根据返回的 id 查询数据库进行二次过滤。
        这里仅做标记，实际过滤在调用方完成。
        """
        # 向量索引中没有时间字段，无法直接过滤
        # 返回原始结果，由调用方根据 id 查询数据库进行时间过滤
        logger.debug(
            "时间范围过滤需要在调用方完成，time_range: %s", time_range
        )
        return results

    async def close(self):
        """关闭索引和 embedding 客户端"""
        try:
            await self._index.close()
        except Exception:
            logger.exception("关闭向量索引失败")

        try:
            await self._embedding.close()
        except Exception:
            logger.exception("关闭 Embedding 客户端失败")
