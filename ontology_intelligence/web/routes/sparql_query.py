from fastapi import APIRouter, Depends
from rdflib import Graph
from rdflib.plugins.sparql import prepareQuery
from ontology_intelligence.web.routes.auth import verify_token
from ontology_intelligence.web.routes.ontology_studio import _load_ontology_model, _build_owlready2_ontology
import logging
import tempfile
import os

router = APIRouter(tags=["sparql-query"])
logger = logging.getLogger(__name__)

def _build_rdf_graph(model: dict):
    onto = _build_owlready2_ontology(model)
    fd, path = tempfile.mkstemp(suffix='.rdf')
    os.close(fd)
    try:
        onto.save(file=path, format="rdfxml")
        g = Graph()
        g.parse(path, format="xml")
        return g
    finally:
        if os.path.exists(path):
            os.remove(path)

@router.post("/scene/{scene_id}/studio/sparql")
async def sparql_query(scene_id: str, payload: dict, username: str = Depends(verify_token)):
    """执行 SPARQL 查询"""
    query = payload.get("query", "")
    model = _load_ontology_model(scene_id)
    
    # 将本体转换为 RDF 图
    g = _build_rdf_graph(model)
    
    try:
        # 执行 SPARQL 查询
        results = g.query(query)
        
        # 格式化结果
        formatted_results = []
        for row in results:
            formatted_results.append({
                str(var): str(val) for var, val in zip(results.vars, row)
            })
        
        return {
            "success": True,
            "results": formatted_results,
            "count": len(formatted_results)
        }
    except Exception as e:
        logger.error(f"SPARQL Error: {e}")
        return {
            "success": False,
            "error": str(e)
        }
