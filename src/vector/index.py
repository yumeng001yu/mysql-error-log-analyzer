"""turbovec 索引管理器"""

import logging
from pathlib import Path

import numpy as np

from src.config import Config

logger = logging.getLogger(__name__)


class VectorIndex:
    """turbovec 索引管理器，封装向量索引的创建、加载、添加和搜索"""

    def __init__(self, config: Config | None = None):
        self._config = config or Config()
        self._index_path: str = self._config.get(
            "vector", "index_path", default="./data/vector_index.tq"
        )
        self._bit_width: int = self._config.get("vector", "bit_width", default=4)
        self._index = None
        self._dim: int | None = None

    def is_available(self) -> bool:
        """索引是否可用"""
        return self._index is not None

    async def initialize(self, dim: int):
        """创建或加载索引

        如果 index_path 文件存在则加载，否则创建新索引。
        """
        self._dim = dim
        index_path = Path(self._index_path)

        try:
            import turbovec
        except ImportError:
            logger.warning("turbovec 未安装，向量索引功能不可用")
            return

        try:
            if index_path.exists():
                logger.info("加载已有向量索引: %s", self._index_path)
                self._index = turbovec.TurboQuantIndex.load(str(index_path))
            else:
                logger.info("创建新向量索引 (dim=%d, bit_width=%d)", dim, self._bit_width)
                self._index = turbovec.TurboQuantIndex(dim=dim, bit_width=self._bit_width)
        except Exception:
            logger.exception("初始化向量索引失败")
            self._index = None

    async def add_vectors(self, ids: list[int], vectors: list[list[float]]):
        """添加向量到索引

        调用 turbovec.TurboQuantIndex.add()，并自动保存索引。
        """
        if not self.is_available():
            return
        if not vectors:
            return

        try:
            np_vectors = np.array(vectors, dtype=np.float32)
            self._index.add(np_vectors)
            await self.save()
            logger.debug("添加 %d 条向量到索引", len(vectors))
        except Exception:
            logger.exception("添加向量失败")

    async def search(
        self,
        query_vector: list[float],
        k: int = 10,
        allowed_ids: list[int] | None = None,
    ) -> list[dict]:
        """搜索相似向量

        调用 turbovec.TurboQuantIndex.search()。
        如果提供 allowed_ids，在搜索后手动过滤。
        返回 [{"id": int, "score": float}, ...]
        """
        if not self.is_available():
            return []

        try:
            query = np.array(query_vector, dtype=np.float32)
            # 扩大搜索范围以应对 allowed_ids 过滤
            search_k = k * 4 if allowed_ids is not None else k
            scores, indices = self._index.search(query, k=search_k)

            results: list[dict] = []
            for score, idx in zip(scores, indices):
                int_idx = int(idx)
                if allowed_ids is not None and int_idx not in allowed_ids:
                    continue
                results.append({"id": int_idx, "score": float(score)})
                if len(results) >= k:
                    break

            return results
        except Exception:
            logger.exception("向量搜索失败")
            return []

    async def save(self):
        """保存索引到文件"""
        if not self.is_available():
            return

        try:
            index_path = Path(self._index_path)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            self._index.write(str(index_path))
            logger.debug("向量索引已保存: %s", self._index_path)
        except Exception:
            logger.exception("保存向量索引失败")

    async def close(self):
        """关闭索引"""
        if self.is_available():
            try:
                await self.save()
            except Exception:
                logger.exception("关闭索引时保存失败")
            self._index = None
