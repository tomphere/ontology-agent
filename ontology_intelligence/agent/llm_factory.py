# =============================================================================
# LLM 工厂 - 统一的大语言模型创建接口
# =============================================================================
# 兼容所有 OpenAI 格式 API：
#   - OpenAI 原生 (api.openai.com)
#   - OpenRouter (openrouter.ai/api/v1)
#   - Qwen/通义千问 (dashscope.aliyuncs.com/compatible-mode/v1)
#   - Ollama 本地 (localhost:11434/v1)
#   - LLM OpenAI 兼容端点 (generativelanguage.googleapis.com/v1beta/openai)
#   - 任何 OpenAI 兼容的自定义端点
# =============================================================================

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 预置的 Provider 端点映射
PROVIDER_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
    "LLM": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def _resolve_base_url(provider: str, custom_base_url: Optional[str] = None) -> Optional[str]:
    """根据 provider 名称解析 base_url"""
    if custom_base_url:
        return custom_base_url.rstrip("/")
    return PROVIDER_ENDPOINTS.get(provider.lower())


def create_llm(
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0,
    max_tokens: int = 2048,
    **kwargs,
):
    """
    创建 LangChain ChatModel 实例（统一使用 OpenAI 兼容接口）。

    Args:
        provider: 服务商名称（openai/openrouter/qwen/ollama/LLM 等）
        base_url: 自定义 API 端点（覆盖 provider 默认值）
        api_key: API Key
        model: 模型名称
        temperature: 生成温度
        max_tokens: 最大输出 token 数
        **kwargs: 其他传递给 ChatOpenAI 的参数

    Returns:
        ChatOpenAI 实例
    """
    from ontology_intelligence.config import settings

    provider = provider or settings.llm_provider
    api_key = api_key or settings.llm_api_key
    model = model or settings.llm_model
    resolved_base_url = _resolve_base_url(provider, base_url or settings.llm_base_url)

    if not api_key and provider not in ("ollama",):
        raise ValueError(
            f"LLM_API_KEY 未配置。请在 .env 中设置 LLM_API_KEY 或 LLM_API_KEY。"
        )

    # Ollama 不需要 api_key，但 ChatOpenAI 要求非空
    if not api_key:
        api_key = "ollama"

    from langchain_openai import ChatOpenAI
    
    # 为满足 OpenRouter 规范增加请求头
    extra_headers = {
        "HTTP-Referer": "https://github.com/ontology-intelligence", # 可选
        "X-Title": "Ontology Intelligence Platform",
    }
    streaming = kwargs.pop("streaming", True)
    disable_streaming = kwargs.pop("disable_streaming", "tool_calling")

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=resolved_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60, # 延长至 60 秒
        default_headers=extra_headers,
        streaming=streaming,
        disable_streaming=disable_streaming,
        **kwargs,
    )

    logger.info(
        f"[LLM] 创建成功: provider={provider}, model={model}, "
        f"base_url={resolved_base_url or '(default)'}"
    )
    return llm


# 支持 dimensions 参数的模型白名单（OpenAI text-embedding-3 系列等）
_MODELS_SUPPORTING_DIMENSIONS = {
    "text-embedding-3-small", "text-embedding-3-large",
    "text-embedding-ada-002",
}


def create_embeddings(
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
    **kwargs,
):
    """
    创建 LangChain Embeddings 实例（统一 OpenAI 兼容接口）。

    注意：dimensions 参数仅对支持 Matryoshka Representation 的模型生效
    （如 OpenAI text-embedding-3-*）。对于 bge-m3 等不支持该特性的模型，
    不会将 dimensions 传递给 API，避免触发 400 错误。

    Returns:
        OpenAIEmbeddings 实例
    """
    from ontology_intelligence.config import settings

    provider = provider or settings.llm_provider
    api_key = api_key or settings.llm_embedding_api_key
    model = model or settings.llm_embedding_model
    dimensions = dimensions or settings.llm_embedding_dimensions
    
    # 优先解析专用的 Embedding Base URL
    resolved_base_url = _resolve_base_url(provider, base_url or settings.llm_embedding_base_url)

    if not api_key and provider not in ("ollama",):
        raise ValueError("LLM_EMBEDDING_API_KEY 或 LLM_API_KEY 未配置。")

    if not api_key:
        api_key = "ollama"

    from langchain_openai import OpenAIEmbeddings

    # 仅对支持 dimensions 参数的模型传递该参数
    # bge-m3 等模型不支持 matryoshka representation，传 dimensions 会导致 400 错误
    emb_kwargs = {
        "model": model,
        "api_key": api_key,
        "base_url": resolved_base_url,
        "timeout": 15,       # 单次请求超时 15 秒
        "max_retries": 2,    # 最多重试 2 次（减少 502 时的长时间阻塞）
    }
    if model and model.lower() in _MODELS_SUPPORTING_DIMENSIONS:
        emb_kwargs["dimensions"] = dimensions

    emb_kwargs.update(kwargs)
    embeddings = OpenAIEmbeddings(**emb_kwargs)

    logger.info(
        f"[Embedding] 创建成功: model={model}, expected_dimensions={dimensions}, "
        f"base_url={resolved_base_url or '(default)'}"
    )
    return embeddings


# 缓存的 Embeddings 实例，避免在批量同步时每条记录都重建连接
_cached_embeddings = None
_cached_embeddings_key = None


def get_embedding_vector(text: str, **kwargs) -> Optional[list]:
    """
    便捷函数：将单段文本转为向量。
    供 sync engine 等模块直接调用。
    使用缓存的 Embeddings 实例，避免每条记录都重新创建连接。

    Args:
        text: 待向量化的文本

    Returns:
        list[float] 或 None
    """
    global _cached_embeddings, _cached_embeddings_key
    if not text:
        return None
    try:
        # 根据配置参数生成缓存键，配置变化时重建实例
        from ontology_intelligence.config import settings
        cache_key = (
            kwargs.get('model', settings.llm_embedding_model),
            kwargs.get('base_url', settings.llm_embedding_base_url),
        )
        if _cached_embeddings is None or _cached_embeddings_key != cache_key:
            _cached_embeddings = create_embeddings(**kwargs)
            _cached_embeddings_key = cache_key
            logger.info("[Embedding] 已创建/更新缓存的 Embeddings 实例")

        return _cached_embeddings.embed_query(text)
    except Exception as e:
        logger.error(f"[Embedding] 向量生成失败: {e}")
        # 清除缓存，下次调用时重建
        _cached_embeddings = None
        _cached_embeddings_key = None
        return None


def test_llm_connection(
    provider: str,
    base_url: Optional[str],
    api_key: str,
    model: str,
) -> dict:
    """
    测试 LLM 连接可用性。

    Returns:
        {"success": bool, "message": str, "response": str|None}
    """
    try:
        llm = create_llm(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=0,
            max_tokens=50,
        )
        response = llm.invoke("Say 'hello' in one word.")
        content = response.content if hasattr(response, "content") else str(response)
        return {
            "success": True,
            "message": f"模型 {model} 连接成功",
            "response": content[:200],
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接失败: {str(e)[:300]}",
            "response": None,
        }


def test_embedding_connection(
    provider: str,
    base_url: Optional[str],
    api_key: str,
    model: str,
    dimensions: Optional[int] = None,
) -> dict:
    """
    测试 Embedding 连接可用性。

    Returns:
        {"success": bool, "message": str, "dimensions": int|None}
    """
    try:
        from ontology_intelligence.config import settings
        emb = create_embeddings(
            provider=provider,
            base_url=base_url or settings.llm_embedding_base_url,
            api_key=api_key or settings.llm_embedding_api_key,
            model=model,
            dimensions=dimensions or settings.llm_embedding_dimensions,
        )
        vector = emb.embed_query("test")
        return {
            "success": True,
            "message": f"Embedding 模型 {model} 连接成功",
            "dimensions": len(vector),
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接失败: {str(e)[:300]}",
            "dimensions": None,
        }
