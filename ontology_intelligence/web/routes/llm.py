# LLM 配置和测试路由
import asyncio
from fastapi import APIRouter, Depends
try:
    from dotenv import set_key
except ImportError:
    def set_key(dotenv_path, key_to_set, value_to_set):
        lines = []
        found = False
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            pass
        for idx, line in enumerate(lines):
            if line.strip().startswith(f"{key_to_set}="):
                lines[idx] = f"{key_to_set}={value_to_set}"
                found = True
                break
        if not found:
            lines.append(f"{key_to_set}={value_to_set}")
        with open(dotenv_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True, key_to_set, value_to_set

from ontology_intelligence.config import settings
from ontology_intelligence.web.models import LLMConfigRequest, LLMTestRequest, EmbeddingTestRequest
from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.agent.llm_factory import (
    test_llm_connection, test_embedding_connection, PROVIDER_ENDPOINTS,
)

router = APIRouter(tags=["llm"])


@router.get("/llm/config")
async def get_llm_config(username: str = Depends(verify_token)):
    return {
        "provider": settings.llm_provider,
        "base_url": settings.llm_base_url or "",
        "api_key": ("*" * 8 + settings.llm_api_key[-4:]) if len(settings.llm_api_key) > 4 else "未配置",
        "model": settings.llm_model,
        "embedding_model": settings.llm_embedding_model,
        "embedding_dimensions": settings.llm_embedding_dimensions,
        "available_providers": list(PROVIDER_ENDPOINTS.keys()),
    }


@router.put("/llm/config")
async def update_llm_config(req: LLMConfigRequest, username: str = Depends(require_admin)):
    env_path = str(settings.project_root / ".env")
    if req.provider is not None:
        set_key(env_path, "LLM_PROVIDER", req.provider)
    if req.base_url is not None:
        set_key(env_path, "LLM_BASE_URL", req.base_url)
    if req.api_key is not None:
        set_key(env_path, "LLM_API_KEY", req.api_key)
    if req.model is not None:
        set_key(env_path, "LLM_MODEL", req.model)
    if req.embedding_model is not None:
        set_key(env_path, "LLM_EMBEDDING_MODEL", req.embedding_model)
    if req.embedding_dimensions is not None:
        set_key(env_path, "LLM_EMBEDDING_DIMENSIONS", str(req.embedding_dimensions))
    settings.reload()
    return {"status": "success", "message": "LLM 配置已更新"}


@router.post("/llm/test")
async def test_llm(req: LLMTestRequest, username: str = Depends(verify_token)):
    from ontology_intelligence.web.app import executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        lambda: test_llm_connection(req.provider, req.base_url, req.api_key, req.model),
    )
    return result


@router.post("/llm/test-embedding")
async def test_embedding(req: EmbeddingTestRequest, username: str = Depends(verify_token)):
    from ontology_intelligence.web.app import executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        lambda: test_embedding_connection(req.provider, req.base_url, req.api_key, req.model, req.dimensions),
    )
    return result
