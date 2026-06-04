# 智能体管理路由
import asyncio
import os
import time
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query

from ontology_intelligence.config import settings
from ontology_intelligence.web.models import AgentInitRequest
from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.web.audit import audit_event

router = APIRouter(tags=["agent"])
logger = logging.getLogger("web-platform")


def _extract_tool_detail(tool) -> dict:
    detail = {"name": getattr(tool, "name", "unknown"), "description": getattr(tool, "description", ""), "parameters": []}
    schema = getattr(tool, "args_schema", None)
    if schema:
        try:
            json_schema = schema.schema() if hasattr(schema, 'schema') else {}
            props = json_schema.get("properties", {})
            required = json_schema.get("required", [])
            for pname, pinfo in props.items():
                detail["parameters"].append({
                    "name": pname, "type": pinfo.get("type", "string"),
                    "description": pinfo.get("description", ""), "required": pname in required,
                })
        except Exception:
            pass
    return detail


def _empty_agent_state():
    return {
        "graph": None, "agent": None, "config": None,
        "initialized": False, "initializing": False, "error": None,
        "tools": [], "tools_detail": [], "diagnostics": {}, "last_init_time": None,
    }


def _get_agent_state(scene_id: str = None):
    from ontology_intelligence.web.app import agent_state, scene_agent_states
    if not scene_id:
        return agent_state
    return scene_agent_states.setdefault(scene_id, _empty_agent_state())


def _init_agent(scene_id: str = None):
    state = _get_agent_state(scene_id)
    if state["initialized"]:
        return
    if state["initializing"]:
        for _ in range(60):
            time.sleep(1)
            if state["initialized"]:
                return
        raise RuntimeError("初始化超时")

    state["initializing"] = True
    try:
        logger.info(f"[Agent] 开始初始化... scene_id={scene_id or 'global'}")
        settings.reload()

        from ontology_intelligence.agent.core import (
            connect_neo4j, get_dynamic_ontology_semantics, get_relationship_semantics,
            get_data_property_semantics, build_scene_mapping_semantics,
            build_scene_ontology_contract, build_scene_ontology_contract_semantics,
            build_cypher_prompt, build_graph_query_tool, get_scene_display_maps,
            load_plugins, build_agent,
        )
        from ontology_intelligence.agent.llm_factory import create_llm

        graph = connect_neo4j(scene_id=scene_id)
        ontology_sem = get_dynamic_ontology_semantics(graph, scene_id=scene_id)
        rel_sem = get_relationship_semantics(graph, scene_id=scene_id)
        data_prop_sem = get_data_property_semantics(graph, scene_id=scene_id)
        mapping_sem = build_scene_mapping_semantics(scene_id)
        ontology_contract = build_scene_ontology_contract(scene_id)
        ontology_contract_sem = build_scene_ontology_contract_semantics(scene_id)

        # 场景智能体使用工具调用和长业务 prompt；部分 OpenAI 兼容服务在这种组合下
        # 会返回空流并触发 "No generations found in stream"，因此这里禁用底层流式。
        llm = create_llm(streaming=False)
        cypher_prompt = build_cypher_prompt(
            ontology_sem,
            rel_sem,
            scene_id=scene_id,
            data_property_semantics=data_prop_sem,
            mapping_semantics=mapping_sem,
            ontology_contract_semantics=ontology_contract_sem,
        )
        display_maps = get_scene_display_maps(scene_id=scene_id, graph=graph)
        graph_tool = build_graph_query_tool(
            graph,
            cypher_prompt,
            llm,
            display_maps=display_maps,
            scene_id=scene_id,
            query_routing=ontology_contract.get("query_routing", []),
        )
        all_tools = [graph_tool]
        all_tools.extend(load_plugins(scene_id=scene_id))

        db_path = None
        if scene_id:
            db_path = str(settings.project_root / "data" / f"chat_sessions_{scene_id}.db")
        agent = build_agent(all_tools, llm, db_path=db_path)

        state["graph"] = graph
        state["agent"] = agent
        state["config"] = {"scene_id": scene_id}
        state["tools"] = [t.name for t in all_tools]
        state["tools_detail"] = [_extract_tool_detail(t) for t in all_tools]
        
        # We can dynamically get the count now from core module if needed, or just remove it
        try:
            from ontology_intelligence.agent.core import get_scene_few_shots_cache
            cached_shots = get_scene_few_shots_cache(scene_id)
            fs_count = len(cached_shots) if cached_shots else 0
        except Exception:
            fs_count = 0

        state["diagnostics"] = {
            "scene_id": scene_id,
            "linked_ontology_id": ontology_contract.get("linked_ontology_id"),
            "mapping_count": ontology_contract.get("mapping_count", 0),
            "candidate_path_count": len(ontology_contract.get("paths", [])),
            "vector_fields": ontology_contract.get("vector_fields", []),
            "query_routing": ontology_contract.get("query_routing", []),
            "few_shot_count": fs_count,
            "tool_names": [t.name for t in all_tools],
        }
        state["initialized"] = True
        state["error"] = None
        state["last_init_time"] = datetime.now().isoformat()
        logger.info(f"[Agent] 初始化成功！{len(all_tools)} 个工具，诊断信息: {state['diagnostics']}")
    except Exception as e:
        state["error"] = str(e)
        logger.error(f"[Agent] 初始化失败: {e}")
        raise
    finally:
        state["initializing"] = False


@router.post("/agent/init")
async def init_agent_endpoint(req: AgentInitRequest = None, username: str = Depends(require_admin)):
    from ontology_intelligence.web.app import executor
    scene_id = req.scene_id if req else None
    state = _get_agent_state(scene_id)
    if state["initialized"]:
        return {"status": "already_initialized", "scene_id": scene_id, "tools": state["tools"], "tools_detail": state["tools_detail"], "diagnostics": state.get("diagnostics", {})}
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, lambda: _init_agent(scene_id))
        audit_event(username, "agent.init", scene_id=scene_id, tools=state["tools"])
        return {"status": "success", "scene_id": scene_id, "tools": state["tools"], "tools_detail": state["tools_detail"], "diagnostics": state.get("diagnostics", {})}
    except Exception as e:
        audit_event(username, "agent.init", "failed", scene_id=scene_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"初始化失败: {e}")


@router.get("/agent/status")
async def agent_status(scene_id: str = Query(None), username: str = Depends(verify_token)):
    agent_state = _get_agent_state(scene_id)
    return {
        "scene_id": scene_id,
        "initialized": agent_state["initialized"],
        "initializing": agent_state["initializing"],
        "error": agent_state["error"],
        "tools": agent_state["tools"],
        "tools_detail": agent_state["tools_detail"],
        "diagnostics": agent_state.get("diagnostics", {}),
        "last_init_time": agent_state["last_init_time"],
    }


@router.post("/agent/reset")
async def reset_agent(scene_id: str = Query(None), username: str = Depends(require_admin)):
    agent_state = _get_agent_state(scene_id)
    agent_state.update({"initialized": False, "agent": None, "graph": None,
                        "tools": [], "tools_detail": [], "diagnostics": {}, "error": None})
    audit_event(username, "agent.reset", scene_id=scene_id)
    return {"status": "success", "message": "已重置"}
