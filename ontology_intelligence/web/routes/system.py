# 系统状态路由
import os
import glob
from fastapi import APIRouter, HTTPException, Depends
try:
    from dotenv import dotenv_values
except ImportError:
    def dotenv_values(*args, **kwargs):
        return {}

from ontology_intelligence.config import settings
from ontology_intelligence.web.routes.auth import verify_token

router = APIRouter(tags=["system"])


@router.get("/system/status")
async def get_system_status(username: str = Depends(verify_token)):
    env_path = settings.project_root / ".env"
    env_vals = dotenv_values(env_path) if env_path.exists() else {}

    # Neo4j
    neo4j_status = {"connected": False, "message": "未检测"}
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        with driver.session() as session:
            session.run("RETURN 1 AS ok").single()
        driver.close()
        neo4j_status = {"connected": True, "message": f"已连接 {settings.neo4j_uri}"}
    except Exception as e:
        neo4j_status = {"connected": False, "message": str(e)[:120]}

    # MySQL
    mysql_status = {"connected": False, "message": "未检测"}
    try:
        import pymysql
        conn = pymysql.connect(**{**settings.mysql_config, "connect_timeout": 5})
        conn.close()
        mysql_status = {"connected": True, "message": f"已连接 {settings.mysql_host}:{settings.mysql_port}"}
    except Exception as e:
        mysql_status = {"connected": False, "message": str(e)[:120]}

    # LLM
    llm_key = settings.llm_api_key
    # 检查是否为占位符
    placeholder_prefixes = ("YOUR_", "your_", "replace_with_")
    is_placeholder = not llm_key or llm_key.startswith(placeholder_prefixes)
    llm_status = {
        "configured": not is_placeholder,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "message": "已配置" if not is_placeholder else "未配置 API Key (当前为占位符)"
    }

    # 本体文件
    ontology_dir = settings.ontology_dir
    ontology_files = []
    if os.path.isdir(ontology_dir):
        for ext in ("*.owl", "*.rdf", "*.ttl"):
            ontology_files.extend(glob.glob(os.path.join(ontology_dir, ext)))

    from ontology_intelligence.web.app import agent_state
    return {
        "neo4j": neo4j_status, 
        "mysql": mysql_status, 
        "llm": llm_status, # 统一使用 llm 键名
        "ontology_dir": ontology_dir,
        "ontology_file_count": len(ontology_files),
        "ontology_files": [os.path.basename(f) for f in ontology_files],
        "agent_initialized": agent_state["initialized"],
        "project_dir": str(settings.project_root),
    }


@router.get("/system/graph-stats")
async def get_graph_stats(username: str = Depends(verify_token)):
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        stats = {}
        with driver.session() as session:
            stats["total_nodes"] = session.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
            stats["total_relationships"] = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]
            
            # 过滤掉系统和元标签
            lbl_query = """
            MATCH (n) UNWIND labels(n) AS lbl 
            WITH lbl, count(*) AS cnt 
            WHERE NOT lbl IN ['Class', 'ObjectProperty', 'DataProperty', 'Individual', 'AnnotationProperty', '_GraphConfig', 'Relationship', 'Ticket', 'SceneEntity', 'Thing', 'Node', 'Resource']
            RETURN lbl, cnt ORDER BY cnt DESC LIMIT 50
            """
            r = session.run(lbl_query)
            stats["labels"] = [{"label": rec["lbl"], "count": rec["cnt"]} for rec in r]
            
            # 过滤掉系统和本体关系
            rel_query = """
            MATCH ()-[r]->() 
            WITH type(r) AS tp, count(*) AS cnt 
            WHERE NOT tp IN ['SCO', 'DOMAIN', 'RANGE', 'hasDataProperty']
            RETURN tp, cnt ORDER BY cnt DESC LIMIT 50
            """
            r = session.run(rel_query)
            stats["rel_types"] = [{"type": rec["tp"], "count": rec["cnt"]} for rec in r]
        driver.close()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图谱统计失败: {e}")
