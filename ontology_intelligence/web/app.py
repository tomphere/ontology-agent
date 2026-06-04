# =============================================================================
# FastAPI 应用主入口（从 web-platform/backend/main.py 重构拆分）
# =============================================================================

import os
import logging
import warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ontology_intelligence.config import settings

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=DeprecationWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("web-platform")

# 线程池
executor = ThreadPoolExecutor(max_workers=50)
sync_executor = ThreadPoolExecutor(max_workers=10)

# 全局 Agent 状态
agent_state = {
    "graph": None, "agent": None, "config": None,
    "initialized": False, "initializing": False, "error": None,
    "tools": [], "tools_detail": [], "last_init_time": None,
}
scene_agent_states = {}

sync_state = {
    "ontology_syncing": False, "database_syncing": False,
    "last_ontology_sync": None, "last_database_sync": None,
    "ontology_started_at": None, "database_started_at": None,
    "ontology_result": None, "database_result": None,
}

# 会话数据目录
SESSIONS_DIR = settings.project_root / "data" / "chat_sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# FastAPI 应用
app = FastAPI(title="本体智能体 Web 可视化平台", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/healthz", include_in_schema=False)
@app.get("/api/healthz", include_in_schema=False)
async def healthz():
    """Lightweight liveness check that does not require authentication."""
    return {
        "status": "ok",
        "service": "ontology-intelligence",
        "time": datetime.now(timezone.utc).isoformat(),
    }

# ==== 注册路由 ====
from ontology_intelligence.web.routes.auth import router as auth_router
from ontology_intelligence.web.routes.config import router as config_router
from ontology_intelligence.web.routes.sync import router as sync_router
from ontology_intelligence.web.routes.system import router as system_router
from ontology_intelligence.web.routes.graph import router as graph_router
from ontology_intelligence.web.routes.agent import router as agent_router
from ontology_intelligence.web.routes.chat import router as chat_router
from ontology_intelligence.web.routes.llm import router as llm_router
from ontology_intelligence.web.routes.ontology import router as ontology_router
from ontology_intelligence.web.routes.datasource import router as datasource_router
from ontology_intelligence.web.routes.validation import router as validation_router
from ontology_intelligence.web.routes.scene import router as scene_router
from ontology_intelligence.web.routes.mapping_builder import router as mapping_builder_router
from ontology_intelligence.web.routes.admin import router as admin_router
from ontology_intelligence.web.routes.ontology_management import router as ontology_management_router
from ontology_intelligence.web.routes.ontology_studio import router as ontology_studio_router
from ontology_intelligence.web.routes.dl_query import router as dl_query_router
from ontology_intelligence.web.routes.sparql_query import router as sparql_query_router
from ontology_intelligence.web.routes.swrl_rules import router as swrl_rules_router

app.include_router(auth_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(ontology_router, prefix="/api")
app.include_router(datasource_router, prefix="/api")
app.include_router(validation_router, prefix="/api")
app.include_router(scene_router, prefix="/api")
app.include_router(mapping_builder_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(ontology_management_router, prefix="/api")
app.include_router(ontology_studio_router, prefix="/api")
app.include_router(dl_query_router, prefix="/api")
app.include_router(sparql_query_router, prefix="/api")
app.include_router(swrl_rules_router, prefix="/api")

@app.on_event("startup")
async def startup_event():
    settings.validate_runtime_security()
    logger.info("[启动] 正在后台自动初始化图谱大模型 Agent...")
    from ontology_intelligence.web.routes.agent import _init_agent

    def _record_agent_init_result(future):
        try:
            future.result()
        except Exception as e:
            agent_state["error"] = str(e)
            logger.warning(f"[启动] Agent 后台初始化失败，Web 服务继续运行: {e}")

    future = executor.submit(_init_agent)
    future.add_done_callback(_record_agent_init_result)

if __name__ == "__main__":
    import uvicorn
    settings.validate_runtime_security()
    logger.info(f"[启动] 项目路径: {settings.project_root}")
    logger.info(f"[启动] 会话路径: {SESSIONS_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
