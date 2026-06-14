"""设置接口模块 - LLM 和 Embedding 配置管理"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.config import Config
from src.web.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["设置"])


# ── Pydantic 模型 ───────────────────────────────────────────

class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4"
    api_base: str = ""
    api_key: str = ""
    temperature: float = 0.3
    timeout: int = 60


class EmbeddingConfig(BaseModel):
    enabled: bool = False
    provider: str = "ollama"
    model: str = "nomic-embed-text"
    api_base: str = ""
    api_key: str = ""
    dim: int = 768
    batch_size: int = 32


class SettingsResponse(BaseModel):
    llm: LLMConfig
    embedding: EmbeddingConfig


class SettingsUpdateRequest(BaseModel):
    llm: Optional[LLMConfig] = None
    embedding: Optional[EmbeddingConfig] = None


class TestResultResponse(BaseModel):
    success: bool
    message: str


# ── 配置文件路径 ──────────────────────────────────────────

def _get_config_path() -> str:
    """获取配置文件路径"""
    from pathlib import Path
    search_paths = [
        Path.cwd() / "config.yaml",
        Path.cwd() / "config" / "config.yaml",
    ]
    for p in search_paths:
        if p.exists():
            return str(p)
    # 默认路径
    return str(Path.cwd() / "config.yaml")


def _save_config_to_yaml(config_data: dict):
    """保存配置到 YAML 文件"""
    import yaml
    from pathlib import Path

    config_path = _get_config_path()
    path = Path(config_path)

    # 读取现有配置
    existing = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}

    # 深度合并
    def deep_merge(base, override):
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    merged = deep_merge(existing, config_data)

    # 确保目录存在
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(merged, f, default_flow_style=False, allow_unicode=True)

    # 重新加载 Config 单例
    Config._instance = None
    Config.load(config_path)


# ── API 端点 ────────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(user: Optional[str] = Depends(get_current_user)):
    """获取当前配置"""
    config = Config()

    llm_cfg = LLMConfig(
        provider=config.get("llm", "provider", default="openai"),
        model=config.get("llm", "model", default="gpt-4"),
        api_base=config.get("llm", "api_base", default=""),
        api_key=config.get("llm", "api_key", default=""),
        temperature=config.get("llm", "temperature", default=0.3),
        timeout=config.get("llm", "timeout", default=60),
    )

    embedding_cfg = EmbeddingConfig(
        enabled=config.get("embedding", "enabled", default=False),
        provider=config.get("embedding", "provider", default="ollama"),
        model=config.get("embedding", "model", default="nomic-embed-text"),
        api_base=config.get("embedding", "api_base", default=""),
        api_key=config.get("embedding", "api_key", default=""),
        dim=config.get("embedding", "dim", default=768),
        batch_size=config.get("embedding", "batch_size", default=32),
    )

    return SettingsResponse(llm=llm_cfg, embedding=embedding_cfg)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateRequest,
    user: Optional[str] = Depends(get_current_user),
):
    """更新配置"""
    config_data = {}

    if body.llm:
        config_data["llm"] = body.llm.model_dump()

    if body.embedding:
        config_data["embedding"] = body.embedding.model_dump()

    if not config_data:
        raise HTTPException(status_code=400, detail="没有提供配置数据")

    try:
        _save_config_to_yaml(config_data)
        logger.info("配置已更新")
    except Exception as e:
        logger.error("保存配置失败: %s", e)
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")

    # 重新读取配置返回
    config = Config()
    llm_cfg = LLMConfig(
        provider=config.get("llm", "provider", default="openai"),
        model=config.get("llm", "model", default="gpt-4"),
        api_base=config.get("llm", "api_base", default=""),
        api_key=config.get("llm", "api_key", default=""),
        temperature=config.get("llm", "temperature", default=0.3),
        timeout=config.get("llm", "timeout", default=60),
    )

    embedding_cfg = EmbeddingConfig(
        enabled=config.get("embedding", "enabled", default=False),
        provider=config.get("embedding", "provider", default="ollama"),
        model=config.get("embedding", "model", default="nomic-embed-text"),
        api_base=config.get("embedding", "api_base", default=""),
        api_key=config.get("embedding", "api_key", default=""),
        dim=config.get("embedding", "dim", default=768),
        batch_size=config.get("embedding", "batch_size", default=32),
    )

    return SettingsResponse(llm=llm_cfg, embedding=embedding_cfg)


@router.post("/settings/test-llm", response_model=TestResultResponse)
async def test_llm(
    body: LLMConfig,
    user: Optional[str] = Depends(get_current_user),
):
    """测试 LLM 连接"""
    try:
        from langchain_core.messages import HumanMessage

        if body.provider == "ollama":
            from langchain_community.chat_models import ChatOllama
            kwargs = {"model": body.model, "temperature": body.temperature}
            if body.api_base:
                kwargs["base_url"] = body.api_base
            chat_model = ChatOllama(**kwargs)
        else:
            from langchain_openai import ChatOpenAI
            kwargs = {
                "model": body.model,
                "api_key": body.api_key or "not-needed",
                "timeout": 15,
                "temperature": body.temperature,
            }
            if body.api_base:
                kwargs["base_url"] = body.api_base
            chat_model = ChatOpenAI(**kwargs)

        # 发送测试消息
        import asyncio
        response = await asyncio.wait_for(
            chat_model.ainvoke([HumanMessage(content="Hello, respond with 'OK' only.")]),
            timeout=20,
        )

        return TestResultResponse(success=True, message=f"连接成功: {response.content[:50]}")

    except asyncio.TimeoutError:
        return TestResultResponse(success=False, message="连接超时，请检查 API 地址和网络")
    except Exception as e:
        error_msg = str(e)[:200]
        logger.warning("LLM 测试失败: %s", error_msg)
        return TestResultResponse(success=False, message=f"连接失败: {error_msg}")


@router.post("/settings/test-embedding", response_model=TestResultResponse)
async def test_embedding(
    body: EmbeddingConfig,
    user: Optional[str] = Depends(get_current_user),
):
    """测试 Embedding 连接"""
    if not body.enabled:
        return TestResultResponse(success=False, message="Embedding 未启用")

    try:
        import httpx

        api_base = body.api_base
        if not api_base:
            if body.provider == "ollama":
                api_base = "http://localhost:11434"
            elif body.provider == "openai":
                api_base = "https://api.openai.com/v1"
            else:
                api_base = "http://localhost:8000/v1"

        async with httpx.AsyncClient(timeout=15.0) as client:
            if body.provider == "ollama":
                resp = await client.post(
                    f"{api_base}/api/embeddings",
                    json={"model": body.model, "prompt": "test"},
                )
            else:
                headers = {"Content-Type": "application/json"}
                if body.api_key:
                    headers["Authorization"] = f"Bearer {body.api_key}"
                resp = await client.post(
                    f"{api_base}/embeddings",
                    headers=headers,
                    json={"model": body.model, "input": ["test"]},
                )

            resp.raise_for_status()
            data = resp.json()

            if body.provider == "ollama":
                dim = len(data.get("embedding", []))
            else:
                items = data.get("data", [])
                dim = len(items[0].get("embedding", [])) if items else 0

            return TestResultResponse(
                success=True,
                message=f"连接成功，向量维度: {dim}"
            )

    except Exception as e:
        error_msg = str(e)[:200]
        logger.warning("Embedding 测试失败: %s", error_msg)
        return TestResultResponse(success=False, message=f"连接失败: {error_msg}")
