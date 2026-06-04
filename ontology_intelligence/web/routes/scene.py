# =============================================================================
# Scene Management Routes
# =============================================================================

import os
import yaml
import logging
import time
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from pydantic import BaseModel
from typing import Optional, List

from ontology_intelligence.config import settings
from ontology_intelligence.security import validate_mapping_identifiers
from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.web.audit import audit_event
from ontology_intelligence.web import scene_store

router = APIRouter(tags=["scene"])
logger = logging.getLogger("web-platform")
MAX_SCENE_SYNC_LOGS = 5


# ---- Request Models ----

class SceneCreateRequest(BaseModel):
    name: str
    description: str = ''
    data_mode: str = 'import'  # "import" or "virtual"

class SceneUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    data_mode: Optional[str] = None
    linked_ontology_id: Optional[str] = None

class SceneMappingUpdateRequest(BaseModel):
    content: str

class SceneFewShotsUpdateRequest(BaseModel):
    content: str

class SceneRulesUpdateRequest(BaseModel):
    content: str

class SceneAliasesUpdateRequest(BaseModel):
    content: str

class SceneRoutingUpdateRequest(BaseModel):
    content: str

class SceneDatasourceRequest(BaseModel):
    datasource_ids: List[str]

class SceneSyncRequest(BaseModel):
    clear_existing: bool = False


def _rotate_scene_sync_logs(scene_dir: str):
    log_file = os.path.join(scene_dir, "sync.log")
    if os.path.exists(log_file):
        archive = os.path.join(scene_dir, f"sync-{time.strftime('%Y%m%d-%H%M%S')}.log")
        os.replace(log_file, archive)
    archives = sorted(
        [name for name in os.listdir(scene_dir) if name.startswith("sync-") and name.endswith(".log")],
        reverse=True,
    )
    for old_name in archives[MAX_SCENE_SYNC_LOGS:]:
        try:
            os.remove(os.path.join(scene_dir, old_name))
        except OSError:
            pass


# ---- Scene CRUD ----

@router.get("/scene/list")
async def list_scenes(username: str = Depends(verify_token)):
    """List all scenes."""
    return {"scenes": scene_store.list_scenes()}


@router.post("/scene/create")
async def create_scene(req: SceneCreateRequest, username: str = Depends(require_admin)):
    """Create a new scene."""
    if req.data_mode not in ('import', 'virtual'):
        raise HTTPException(status_code=400, detail="data_mode must be 'import' or 'virtual'")
    scene = scene_store.create_scene(req.name, req.description, req.data_mode)
    audit_event(username, "scene.create", scene_id=scene["id"], name=req.name, data_mode=req.data_mode)
    return {"status": "success", "scene": scene}


@router.get("/scene/{scene_id}")
async def get_scene(scene_id: str, username: str = Depends(verify_token)):
    """Get scene details."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.put("/scene/{scene_id}")
async def update_scene(scene_id: str, req: SceneUpdateRequest, username: str = Depends(require_admin)):
    """Update scene metadata."""
    updates = req.dict(exclude_unset=True)
    if 'data_mode' in updates and updates['data_mode'] not in ('import', 'virtual'):
        raise HTTPException(status_code=400, detail="data_mode must be 'import' or 'virtual'")
    if 'linked_ontology_id' in updates and updates['linked_ontology_id']:
        ontology_id = updates['linked_ontology_id']
        ontology_paths = [
            os.path.join(str(settings.project_root), 'data', 'ontology_studio', f"{ontology_id}.json"),
            os.path.join(str(settings.project_root), 'data', 'ontologies', f"{ontology_id}.json"),
        ]
        if not any(os.path.isfile(path) for path in ontology_paths):
            raise HTTPException(status_code=404, detail="Linked ontology not found")
    scene = scene_store.update_scene(scene_id, **updates)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    audit_event(username, "scene.update", scene_id=scene_id, updates=updates)
    return {"status": "success", "scene": scene}


@router.delete("/scene/{scene_id}")
async def delete_scene(scene_id: str, username: str = Depends(require_admin)):
    """Delete a scene."""
    if not scene_store.get_scene(scene_id):
        raise HTTPException(status_code=404, detail="Scene not found")
    graph_cleanup = None
    try:
        from ontology_intelligence.sync.engine import purge_scene_graph
        graph_cleanup = purge_scene_graph(scene_id)
    except Exception as e:
        logger.warning(f"[Scene Delete] Graph cleanup skipped/failed for {scene_id}: {e}")
    scene_store.delete_scene(scene_id)
    audit_event(username, "scene.delete", scene_id=scene_id, graph_cleanup=graph_cleanup)
    return {"status": "success", "message": "Scene deleted", "graph_cleanup": graph_cleanup}


# ---- Ontology File ----

ALLOWED_EXTENSIONS = {'.owl', '.rdf', '.ttl', '.n3', '.nt', '.jsonld', '.owx'}


@router.post("/scene/{scene_id}/ontology/upload")
async def upload_scene_ontology(
    scene_id: str,
    file: UploadFile = File(...),
    username: str = Depends(require_admin),
):
    """Upload/replace a scene's ontology file (only 1 allowed per scene)."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    scene_dir = scene_store._scene_dir(scene_id)

    # Delete old ontology file if exists
    old_file = scene.get('ontology_file')
    if old_file:
        old_path = os.path.join(scene_dir, old_file)
        if os.path.isfile(old_path):
            os.remove(old_path)

    # Save new file
    save_path = os.path.join(scene_dir, file.filename)
    content = await file.read()
    with open(save_path, 'wb') as f:
        f.write(content)

    # Update scene metadata
    scene_store.update_scene(scene_id, ontology_file=file.filename, linked_ontology_id='')
    audit_event(username, "scene.ontology.upload", scene_id=scene_id, filename=file.filename, size=len(content))

    return {
        "status": "success",
        "message": f"Ontology file {file.filename} uploaded",
        "filename": file.filename,
        "size": len(content),
    }


@router.get("/scene/{scene_id}/ontology/parse")
async def parse_scene_ontology(scene_id: str, username: str = Depends(verify_token)):
    """Parse the scene's ontology file and return structured data."""
    path = scene_store.get_scene_ontology_path(scene_id)
    linked_model = scene_store.get_linked_ontology_model(scene_id)
    if not path and not linked_model:
        raise HTTPException(status_code=404, detail="No ontology file or linked ontology in this scene")
    if linked_model:
        return scene_store.normalize_ontology_model(linked_model)
    try:
        from ontology_intelligence.ontology.parser import parse_ontology
        return parse_ontology(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")

@router.delete("/scene/{scene_id}/ontology")
async def delete_scene_ontology(scene_id: str, username: str = Depends(require_admin)):
    """Delete the scene's ontology file."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    old_file = scene.get('ontology_file')
    if old_file:
        old_path = os.path.join(scene_store._scene_dir(scene_id), old_file)
        if os.path.isfile(old_path):
            os.remove(old_path)
    scene_store.update_scene(scene_id, ontology_file='')
    audit_event(username, "scene.ontology.delete", scene_id=scene_id, filename=old_file)
    return {"status": "success", "message": "Ontology file deleted"}


# ---- Mapping Config ----

@router.get("/scene/{scene_id}/mapping")
async def get_scene_mapping(scene_id: str, username: str = Depends(verify_token)):
    """Get scene's mapping configuration."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    mapping_path = scene_store.get_scene_mapping_path(scene_id)
    if not os.path.isfile(mapping_path):
        return {"raw": "", "parsed": None}
    content = open(mapping_path, 'r', encoding='utf-8').read()
    try:
        parsed = yaml.safe_load(content)
    except Exception:
        parsed = None
    return {"raw": content, "parsed": parsed}


@router.put("/scene/{scene_id}/mapping")
async def update_scene_mapping(scene_id: str, req: SceneMappingUpdateRequest, username: str = Depends(require_admin)):
    """Update scene's mapping configuration."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    try:
        parsed = yaml.safe_load(req.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
    if parsed is not None and not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Mapping config must be a YAML object")
    mappings = parsed.get("mappings", []) if parsed else []
    identifier_errors = validate_mapping_identifiers(mappings)
    if identifier_errors:
        raise HTTPException(status_code=400, detail="; ".join(identifier_errors))
    mapping_path = scene_store.get_scene_mapping_path(scene_id)
    with open(mapping_path, 'w', encoding='utf-8') as f:
        f.write(req.content)
    scene_store.update_scene(scene_id)  # touch updated_at
    audit_event(username, "scene.mapping.update", scene_id=scene_id)
    return {"status": "success", "message": "Mapping config updated"}

# ---- Few Shots Config ----

@router.get("/scene/{scene_id}/few-shots")
async def get_scene_few_shots(scene_id: str, username: str = Depends(verify_token)):
    """Get scene's few-shots prompt examples."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "few_shots.txt")
    if not os.path.isfile(fs_path):
        return {"raw": ""}
    content = open(fs_path, 'r', encoding='utf-8').read()
    return {"raw": content}

@router.put("/scene/{scene_id}/few-shots")
async def update_scene_few_shots(scene_id: str, req: SceneFewShotsUpdateRequest, username: str = Depends(require_admin)):
    """Update scene's few-shots prompt examples."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "few_shots.txt")
    with open(fs_path, 'w', encoding='utf-8') as f:
        f.write(req.content)
    scene_store.update_scene(scene_id)
    try:
        from ontology_intelligence.web.routes.agent import _get_agent_state
        agent_state = _get_agent_state(scene_id)
        agent_state.update({"initialized": False, "agent": None, "graph": None,
                            "tools": [], "tools_detail": [], "error": None})
    except Exception as e:
        logger.warning(f"[Scene Few-Shots] Agent reset skipped for {scene_id}: {e}")
    return {"status": "success", "message": "Few-shots config updated"}


# ---- Rules Config ----

@router.get("/scene/{scene_id}/rules")
async def get_scene_rules(scene_id: str, username: str = Depends(verify_token)):
    """Get scene's rules.yaml."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "rules.yaml")
    if not os.path.isfile(fs_path):
        return {"raw": ""}
    content = open(fs_path, 'r', encoding='utf-8').read()
    return {"raw": content}

@router.put("/scene/{scene_id}/rules")
async def update_scene_rules(scene_id: str, req: SceneRulesUpdateRequest, username: str = Depends(require_admin)):
    """Update scene's rules.yaml."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "rules.yaml")
    with open(fs_path, 'w', encoding='utf-8') as f:
        f.write(req.content)
    scene_store.update_scene(scene_id)
    return {"status": "success", "message": "Rules config updated"}


# ---- Aliases Config ----

@router.get("/scene/{scene_id}/aliases")
async def get_scene_aliases(scene_id: str, username: str = Depends(verify_token)):
    """Get scene's aliases.yaml."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "aliases.yaml")
    if not os.path.isfile(fs_path):
        return {"raw": ""}
    content = open(fs_path, 'r', encoding='utf-8').read()
    return {"raw": content}

@router.put("/scene/{scene_id}/aliases")
async def update_scene_aliases(scene_id: str, req: SceneAliasesUpdateRequest, username: str = Depends(require_admin)):
    """Update scene's aliases.yaml."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "aliases.yaml")
    with open(fs_path, 'w', encoding='utf-8') as f:
        f.write(req.content)
    scene_store.update_scene(scene_id)
    return {"status": "success", "message": "Aliases config updated"}


# ---- Routing Config ----

@router.get("/scene/{scene_id}/routing")
async def get_scene_routing(scene_id: str, username: str = Depends(verify_token)):
    """Get scene's routing.yaml."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "routing.yaml")
    if not os.path.isfile(fs_path):
        return {"raw": ""}
    content = open(fs_path, 'r', encoding='utf-8').read()
    return {"raw": content}

@router.put("/scene/{scene_id}/routing")
async def update_scene_routing(scene_id: str, req: SceneRoutingUpdateRequest, username: str = Depends(require_admin)):
    """Update scene's routing.yaml."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    fs_path = os.path.join(scene_store._scene_dir(scene_id), "routing.yaml")
    with open(fs_path, 'w', encoding='utf-8') as f:
        f.write(req.content)
    scene_store.update_scene(scene_id)
    return {"status": "success", "message": "Routing config updated"}


# ---- Data Sources ----

@router.put("/scene/{scene_id}/datasources")
async def update_scene_datasources(scene_id: str, req: SceneDatasourceRequest, username: str = Depends(require_admin)):
    """Associate data sources with a scene."""
    scene = scene_store.update_scene(scene_id, datasource_ids=req.datasource_ids)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    audit_event(username, "scene.datasources.update", scene_id=scene_id, datasource_ids=req.datasource_ids)
    return {"status": "success", "scene": scene}


# ---- Sync ----

@router.post("/scene/{scene_id}/sync")
async def sync_scene(
    scene_id: str,
    req: Optional[SceneSyncRequest] = None,
    username: str = Depends(require_admin),
):
    """Execute data sync for a scene (import mode only)."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    if scene.get('data_mode') == 'virtual':
        return {"status": "skipped", "message": "Virtual mode scenes do not require sync"}

    # Setup file handler for this scene
    scene_dir = scene_store._scene_dir(scene_id)
    _rotate_scene_sync_logs(scene_dir)
    log_file = os.path.join(scene_dir, "sync.log")
    fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    
    # Capture engine logs
    sync_logger = logging.getLogger("ontology_intelligence.sync.engine")
    sync_logger.setLevel(logging.INFO) # Ensure INFO level propagates to file
    sync_logger.addHandler(fh)

    sync_errors = []
    try:
        graph_cleanup = None
        if req and req.clear_existing:
            try:
                from ontology_intelligence.sync.engine import purge_scene_graph
                graph_cleanup = purge_scene_graph(scene_id)
                sync_logger.info(f"Cleared existing scene graph data: {graph_cleanup}")
            except Exception as e:
                logger.error(f"[Scene Sync] Graph cleanup failed: {e}")
                sync_logger.error(f"Graph cleanup failed: {e}")
                sync_errors.append(f"Graph cleanup failed: {e}")

        # Sync ontology file
        ontology_path = scene_store.get_scene_ontology_path(scene_id)
        if ontology_path:
            try:
                from ontology_intelligence.sync.engine import sync_single_ontology_file, init_neo4j_environment
                init_neo4j_environment() # 确保 Neosemantics 配置已初始化
                sync_single_ontology_file(ontology_path)
            except Exception as e:
                logger.error(f"[Scene Sync] Ontology sync failed: {e}")
                sync_logger.error(f"Ontology sync failed: {e}")
                sync_errors.append(f"Ontology sync failed: {e}")
        elif scene.get("linked_ontology_id"):
            try:
                from ontology_intelligence.sync.engine import sync_ontology_model_to_neo4j, init_neo4j_environment
                init_neo4j_environment()
                linked_model = scene_store.get_linked_ontology_model(scene_id)
                if linked_model:
                    sync_ontology_model_to_neo4j(scene_store.normalize_ontology_model(linked_model))
                else:
                    sync_errors.append("Linked ontology model not found")
            except Exception as e:
                logger.error(f"[Scene Sync] Linked ontology sync failed: {e}")
                sync_logger.error(f"Linked ontology sync failed: {e}")
                sync_errors.append(f"Linked ontology sync failed: {e}")
        else:
            sync_logger.warning("No ontology file or linked ontology configured for this scene; skipped ontology sync")

        # Sync data via mapping
        mapping_path = scene_store.get_scene_mapping_path(scene_id)
        if os.path.isfile(mapping_path):
            try:
                from ontology_intelligence.sync.engine import sync_mysql_to_neo4j
                from ontology_intelligence.web.routes.datasource import _load_datasources
                
                mysql_cfg = None
                scene_ds = None
                ds_ids = scene.get('datasource_ids', [])
                if ds_ids:
                    all_ds = _load_datasources()
                    scene_ds = next((d for d in all_ds if d['id'] in ds_ids and d['type'].lower() == 'mysql'), None)
                    if scene_ds and scene_ds['type'].lower() == 'mysql':
                        mysql_cfg = {
                            "host": scene_ds.get("host"),
                            "port": int(scene_ds.get("port", 3306)),
                            "user": scene_ds.get("user"),
                            "password": scene_ds.get("password"),
                            "database": scene_ds.get("database"),
                            "charset": "utf8mb4"
                        }
                    else:
                        sync_errors.append("No MySQL datasource is associated with this scene; import sync currently supports MySQL only")
                
                if not (ds_ids and scene_ds is None):
                    sync_logger.info(f"Starting data mapping sync using dataset config: {scene_ds.get('label') if scene_ds else 'system defaults'}")
                    sync_result = sync_mysql_to_neo4j(mysql_config=mysql_cfg, mapping_file=mapping_path, scene_id=scene_id)
                    if isinstance(sync_result, dict) and sync_result.get("errors"):
                        sync_errors.extend(sync_result["errors"])
            except Exception as e:
                logger.error(f"[Scene Sync] Data sync failed: {e}")
                sync_logger.error(f"Data sync failed: {e}")
                import traceback
                sync_logger.error(traceback.format_exc())
                sync_errors.append(f"Data sync failed: {e}")
        else:
            sync_errors.append("No mapping config found for this scene")

    finally:
        sync_logger.removeHandler(fh)
        fh.close()

    if sync_errors:
        audit_event(username, "scene.sync", "failed", scene_id=scene_id, errors=sync_errors)
        raise HTTPException(status_code=500, detail="; ".join(sync_errors))

    audit_event(username, "scene.sync", scene_id=scene_id)
    return {"status": "success", "message": "Scene sync completed", "graph_cleanup": graph_cleanup}


@router.delete("/scene/{scene_id}/graph")
async def clear_scene_graph(scene_id: str, username: str = Depends(require_admin)):
    """Clear graph data associated with a scene without deleting scene files."""
    if not scene_store.get_scene(scene_id):
        raise HTTPException(status_code=404, detail="Scene not found")
    try:
        from ontology_intelligence.sync.engine import purge_scene_graph
        result = purge_scene_graph(scene_id)
        audit_event(username, "scene.graph.clear", **result)
        return {"status": "success", **result}
    except Exception as e:
        audit_event(username, "scene.graph.clear", "failed", scene_id=scene_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Graph cleanup failed: {e}")

@router.get("/scene/{scene_id}/sync-log")
async def get_scene_sync_log(scene_id: str, username: str = Depends(verify_token)):
    """Retrieve the sync execution log for a scene."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    scene_dir = scene_store._scene_dir(scene_id)
    log_file = os.path.join(scene_dir, "sync.log")
    if not os.path.exists(log_file):
        return {"log": "No sync log found. Please run sync first."}
        
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"log": content}
    except Exception as e:
        return {"log": f"Failed to read log file: {e}"}


@router.get("/scene/{scene_id}/qa-health")
async def get_scene_qa_health(scene_id: str, username: str = Depends(verify_token)):
    """Check whether a scene is ready for ontology-driven Agent QA."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    checks = []
    mapping_path = scene_store.get_scene_mapping_path(scene_id)
    mappings = []
    vector_fields = []
    if os.path.isfile(mapping_path):
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping_config = yaml.safe_load(f) or {}
            mappings = mapping_config.get("mappings") or []
            for mapping in mappings:
                for vf in mapping.get("vectorize_fields", []):
                    vector_fields.append({"table": mapping.get("table_name"), "field": vf})
        except Exception as e:
            checks.append({"name": "映射配置", "status": "error", "message": f"mapping.yaml 解析失败: {e}"})

    linked_model = scene_store.get_linked_ontology_model(scene_id)
    ontology_ok = bool(linked_model or scene_store.get_scene_ontology_path(scene_id))
    checks.append({
        "name": "权威本体",
        "status": "ok" if ontology_ok else "warning",
        "message": f"已绑定本体 {scene.get('linked_ontology_id')}" if scene.get("linked_ontology_id") else ("已上传本体文件" if ontology_ok else "未绑定本体"),
    })
    checks.append({
        "name": "场景映射",
        "status": "ok" if mappings else "warning",
        "message": f"已加载 {len(mappings)} 条映射规则" if mappings else "mapping.yaml 为空或不存在",
    })
    checks.append({
        "name": "向量字段",
        "status": "ok" if vector_fields else "warning",
        "message": "、".join(f"{item['table']}.{item['field']}" for item in vector_fields) if vector_fields else "未配置文本向量字段",
        "details": vector_fields,
    })

    plugin_path = settings.project_root / "ontology_intelligence" / "plugins" / "semantic_incident_search.py"
    checks.append({
        "name": "事件语义检索工具",
        "status": "ok" if plugin_path.exists() else "warning",
        "message": "Semantic_Incident_Search 可被插件加载器发现" if plugin_path.exists() else "缺少 semantic_incident_search.py",
    })

    graph_info = {"nodes": None, "relationships": None, "indexes": []}
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        with driver.session() as session:
            graph_info["nodes"] = session.run(
                "MATCH (n {scene_id: $scene_id}) RETURN count(n) AS count",
                scene_id=scene_id,
            ).single()["count"]
            graph_info["relationships"] = session.run(
                "MATCH ()-[r]->() WHERE r.scene_id = $scene_id RETURN count(r) AS count",
                scene_id=scene_id,
            ).single()["count"]
            try:
                graph_info["indexes"] = [
                    record.get("name")
                    for record in session.run("SHOW INDEXES YIELD name RETURN name")
                    if record.get("name")
                ]
            except Exception:
                graph_info["indexes"] = []
        driver.close()
        checks.append({
            "name": "场景图谱数据",
            "status": "ok" if graph_info["nodes"] else "warning",
            "message": f"{graph_info['nodes']} 个节点，{graph_info['relationships']} 条关系" if graph_info["nodes"] else "未发现当前场景图谱节点，请先同步",
        })
        checks.append({
            "name": "案事件向量索引",
            "status": "ok" if "incident_vector_index" in graph_info["indexes"] else "warning",
            "message": "incident_vector_index 已存在" if "incident_vector_index" in graph_info["indexes"] else "未发现 incident_vector_index",
        })
    except Exception as e:
        checks.append({"name": "Neo4j 连通性", "status": "warning", "message": f"无法连接或查询 Neo4j: {e}"})

    errors = len([item for item in checks if item["status"] == "error"])
    warnings = len([item for item in checks if item["status"] == "warning"])
    return {
        "scene_id": scene_id,
        "summary": "ready" if not errors and not warnings else ("error" if errors else "warning"),
        "checks": checks,
        "graph": graph_info,
    }


# ---- Validation ----

@router.post("/scene/{scene_id}/validate")
async def validate_scene(scene_id: str, username: str = Depends(verify_token)):
    """Run consistency validation for a specific scene."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    import glob
    from ontology_intelligence.web.routes.validation import (
        _parse_ontology_classes,
        _parse_ontology_details,
        _run_shacl_validation,
        _get_db_tables_and_columns,
        _class_matches,
    )

    errors = []
    warnings = []
    passed = []

    # 1. Check mapping
    mapping_path = scene_store.get_scene_mapping_path(scene_id)
    if not os.path.isfile(mapping_path):
        errors.append({"category": "Mapping", "message": "No mapping config found"})
        return {"errors": errors, "warnings": warnings, "passed": passed, "summary": "Validation stopped"}

    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping_config = yaml.safe_load(f)
    mappings = mapping_config.get("mappings", []) if mapping_config else []
    if mappings:
        passed.append({"category": "Mapping", "message": f"Loaded {len(mappings)} mapping rules"})
    else:
        warnings.append({"category": "Mapping", "message": "Mapping config is empty"})
    for error in validate_mapping_identifiers(mappings):
        errors.append({"category": "Mapping", "message": error})

    # 2. Check ontology
    ontology_info = {"classes": set(), "object_properties": set(), "data_properties": set()}
    ontology_details = {"class_parents": {}, "object_properties": {}, "data_properties": {}}
    ontology_path = scene_store.get_scene_ontology_path(scene_id)
    if ontology_path:
        info = _parse_ontology_classes(ontology_path)
        details = _parse_ontology_details(ontology_path)
        ontology_info["classes"].update(info["classes"])
        ontology_info["object_properties"].update(info["object_properties"])
        ontology_info["data_properties"].update(info["data_properties"])
        ontology_details["class_parents"].update(details["class_parents"])
        ontology_details["object_properties"].update(details["object_properties"])
        ontology_details["data_properties"].update(details["data_properties"])
        shacl_result = _run_shacl_validation(ontology_path)
        if shacl_result["status"] == "passed":
            passed.append({"category": "SHACL", "message": shacl_result["message"]})
        elif shacl_result["status"] == "error":
            errors.append({"category": "SHACL", "message": shacl_result["message"]})
        elif shacl_result["status"] == "warning":
            warnings.append({"category": "SHACL", "message": shacl_result["message"]})
        if ontology_info["classes"]:
            passed.append({"category": "Ontology", "message": f"Found {len(ontology_info['classes'])} classes"})
        else:
            warnings.append({"category": "Ontology", "message": "No classes found in ontology file"})
    elif scene.get("linked_ontology_id"):
        linked_model = scene_store.get_linked_ontology_model(scene_id)
        if linked_model:
            parsed_model = scene_store.normalize_ontology_model(linked_model)
            for cls in parsed_model.get("classes", []):
                name = cls.get("name")
                if not name:
                    continue
                ontology_info["classes"].add(name)
                ontology_details["class_parents"][name] = set(cls.get("parents") or [])
            for prop in parsed_model.get("object_properties", []):
                name = prop.get("name")
                if not name:
                    continue
                ontology_info["object_properties"].add(name)
                ontology_details["object_properties"][name] = {
                    "domain": prop.get("domain") or "",
                    "range": prop.get("range") or "",
                }
            for prop in parsed_model.get("data_properties", []):
                name = prop.get("name")
                if not name:
                    continue
                ontology_info["data_properties"].add(name)
                ontology_details["data_properties"][name] = {
                    "domains": set(prop.get("domains") or []),
                    "range": prop.get("range") or "",
                }
            passed.append({
                "category": "Ontology",
                "message": f"Loaded linked ontology model with {len(ontology_info['classes'])} classes",
            })
        else:
            errors.append({"category": "Ontology", "message": "Linked ontology model not found"})
    else:
        warnings.append({"category": "Ontology", "message": "No ontology file or linked ontology configured"})

    # 3. Check associated datasource tables and columns
    db_tables = {}
    ds_ids = scene.get('datasource_ids', [])
    if ds_ids:
        try:
            from ontology_intelligence.web.routes.datasource import _load_datasources
            datasources = [d for d in _load_datasources() if d.get('id') in ds_ids]
            for ds in datasources:
                tables = _get_db_tables_and_columns(ds)
                if tables:
                    db_tables.update(tables)
                    passed.append({
                        "category": "Datasource",
                        "message": f"{ds.get('label') or ds.get('id')} connected, found {len(tables)} tables",
                    })
                else:
                    warnings.append({
                        "category": "Datasource",
                        "message": f"No tables found or connection failed for {ds.get('label') or ds.get('id')}",
                    })
        except Exception as e:
            warnings.append({"category": "Datasource", "message": f"Datasource validation failed: {e}"})
    elif scene.get('data_mode') != 'virtual':
        warnings.append({"category": "Datasource", "message": "No datasource associated with this scene"})

    for mapping in mappings:
        table_name = mapping.get("table_name", "")
        prefix = f"Mapping:{table_name or 'unknown'}"
        if not table_name:
            errors.append({"category": prefix, "message": "Mapping rule is missing table_name"})
            continue

        db_columns = db_tables.get(table_name, [])
        if db_tables and not db_columns:
            errors.append({"category": prefix, "message": f"Table '{table_name}' not found in associated datasources"})
            continue

        strategy = mapping.get("entity_class_strategy", {})
        node_id_col = mapping.get("node_id_column", "")
        if strategy.get("type") != "relationship" and db_columns and node_id_col not in db_columns:
            errors.append({"category": prefix, "message": f"Primary key column '{node_id_col}' not found"})

        if strategy.get("type") == "static":
            class_name = strategy.get("class_name", "")
            if ontology_info["classes"] and class_name not in ontology_info["classes"]:
                warnings.append({"category": prefix, "message": f"Class '{class_name}' not found in ontology"})
        elif strategy.get("type") == "dynamic_column":
            col = strategy.get("column", "")
            if db_columns and col not in db_columns:
                errors.append({"category": prefix, "message": f"Dynamic class column '{col}' not found"})
        elif strategy.get("type") == "relationship":
            source_col = strategy.get("source_column", "")
            target_col = strategy.get("target_column", "")
            source_class = strategy.get("source_class", "")
            target_class = strategy.get("target_class", "")
            onto_prop = strategy.get("ontology_property", "")
            if db_columns and source_col not in db_columns:
                errors.append({"category": prefix, "message": f"Relationship source column '{source_col}' not found"})
            if db_columns and target_col not in db_columns:
                errors.append({"category": prefix, "message": f"Relationship target column '{target_col}' not found"})
            if ontology_info["classes"] and source_class not in ontology_info["classes"]:
                warnings.append({"category": prefix, "message": f"Relationship source class '{source_class}' not found in ontology"})
            if ontology_info["classes"] and target_class not in ontology_info["classes"]:
                warnings.append({"category": prefix, "message": f"Relationship target class '{target_class}' not found in ontology"})
            if ontology_info["object_properties"] and onto_prop not in ontology_info["object_properties"]:
                warnings.append({"category": prefix, "message": f"Relationship object property '{onto_prop}' not found in ontology"})
            else:
                rel_info = ontology_details["object_properties"].get(onto_prop, {})
                domain = rel_info.get("domain")
                range_ = rel_info.get("range")
                if domain and source_class and not _class_matches(source_class, domain, ontology_details["class_parents"]):
                    warnings.append({"category": prefix, "message": f"Relationship property '{onto_prop}' domain '{domain}' does not match source class '{source_class}'"})
                if range_ and target_class and not _class_matches(target_class, range_, ontology_details["class_parents"]):
                    warnings.append({"category": prefix, "message": f"Relationship property '{onto_prop}' range '{range_}' does not match target class '{target_class}'"})
            for rp in mapping.get("relationship_properties", []):
                column = rp.get("column", "")
                prop_name = rp.get("property") or rp.get("ontology_property") or ""
                if db_columns and column not in db_columns:
                    errors.append({"category": prefix, "message": f"Relationship property column '{column}' not found"})
                if not prop_name:
                    errors.append({"category": prefix, "message": "Relationship property mapping is missing property"})
        else:
            errors.append({"category": prefix, "message": f"Unsupported mapping strategy '{strategy.get('type')}'"})

        for dp in mapping.get("data_properties", []):
            column = dp.get("column", "")
            onto_prop = dp.get("ontology_property", "")
            if db_columns and column not in db_columns:
                errors.append({"category": prefix, "message": f"Data column '{column}' not found"})
            if ontology_info["data_properties"] and onto_prop not in ontology_info["data_properties"]:
                warnings.append({"category": prefix, "message": f"Data property '{onto_prop}' not found in ontology"})
            elif strategy.get("type") == "static":
                class_name = strategy.get("class_name", "")
                prop_info = ontology_details["data_properties"].get(onto_prop, {})
                domains = prop_info.get("domains") or set()
                if domains and class_name and not any(
                    _class_matches(class_name, domain, ontology_details["class_parents"])
                    for domain in domains
                ):
                    warnings.append({"category": prefix, "message": f"Data property '{onto_prop}' domain mismatch with class '{class_name}'"})

        for vf in mapping.get("vectorize_fields", []):
            if db_columns and vf not in db_columns:
                errors.append({"category": prefix, "message": f"Vector field '{vf}' not found"})

        for op in mapping.get("object_properties", []):
            fk_col = op.get("foreign_key_column", "")
            target_label = op.get("target_label", "")
            onto_prop = op.get("ontology_property", "")
            if db_columns and fk_col not in db_columns:
                errors.append({"category": prefix, "message": f"Foreign key column '{fk_col}' not found"})
            if ontology_info["classes"] and target_label not in ontology_info["classes"]:
                warnings.append({"category": prefix, "message": f"Target class '{target_label}' not found in ontology"})
            if ontology_info["object_properties"] and onto_prop not in ontology_info["object_properties"]:
                warnings.append({"category": prefix, "message": f"Object property '{onto_prop}' not found in ontology"})
            else:
                rel_info = ontology_details["object_properties"].get(onto_prop, {})
                domain = rel_info.get("domain")
                range_ = rel_info.get("range")
                current_class = strategy.get("class_name", "") if strategy.get("type") == "static" else ""
                direction = op.get("direction", "OUTGOING")
                source_class = target_label if direction == "INCOMING" else current_class
                dest_class = current_class if direction == "INCOMING" else target_label
                if domain and source_class and not _class_matches(source_class, domain, ontology_details["class_parents"]):
                    warnings.append({"category": prefix, "message": f"Object property '{onto_prop}' domain '{domain}' does not match source class '{source_class}'"})
                if range_ and dest_class and not _class_matches(dest_class, range_, ontology_details["class_parents"]):
                    warnings.append({"category": prefix, "message": f"Object property '{onto_prop}' range '{range_}' does not match target class '{dest_class}'"})

    # 4. Summary
    summary = "Passed" if not errors else f"{len(errors)} errors found"
    if warnings:
        summary += f", {len(warnings)} warnings"
    summary += f", {len(passed)} checks passed"

    return {"errors": errors, "warnings": warnings, "passed": passed, "summary": summary}
