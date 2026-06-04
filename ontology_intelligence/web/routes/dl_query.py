from fastapi import APIRouter, Depends
from ontology_intelligence.web.routes.auth import verify_token
from ontology_intelligence.web.routes.ontology_studio import _load_ontology_model, _build_owlready2_ontology
import logging
from owlready2 import *
import re

router = APIRouter(tags=["dl-query"])
logger = logging.getLogger(__name__)

def tokenize(query: str):
    """简单分词"""
    tokens = re.findall(r'\(|\)|and|or|not|some|only|min|max|exactly|value|[a-zA-Z0-9_:-]+', query)
    return tokens

def parse_expression(tokens, onto):
    """简化的表达式解析"""
    # 这是一个极其简化的 mock，实际中应该实现完整的 DL Query 解析器
    if not tokens:
        return Thing
    
    # 尝试匹配单个类名
    token = tokens[0]
    cls = onto.search_one(iri=f"*#{token}")
    if cls:
        return cls
        
    return Thing

def parse_dl_query(query: str, onto):
    """解析 DL Query 字符串"""
    tokens = tokenize(query)
    return parse_expression(tokens, onto)

def _get_entity_name(entity):
    if hasattr(entity, "name"):
        return entity.name
    return str(entity)

@router.post("/scene/{scene_id}/studio/dl-query")
async def dl_query(scene_id: str, payload: dict, username: str = Depends(verify_token)):
    """执行 DL Query"""
    query = payload.get("query", "")
    include_instances = payload.get("include_instances", True)
    include_subclasses = payload.get("include_subclasses", False)
    include_superclasses = payload.get("include_superclasses", False)
    include_equivalent = payload.get("include_equivalent", False)

    model = _load_ontology_model(scene_id)
    onto = _build_owlready2_ontology(model)
    
    try:
        # 解析 DL Query
        expression = parse_dl_query(query, onto)
        
        results = {
            "instances": [],
            "subclasses": [],
            "superclasses": [],
            "equivalent_classes": []
        }
        
        if expression and expression != Thing:
            # Instances
            if include_instances:
                results["instances"] = [_get_entity_name(ind) for ind in expression.instances()]
            
            # Sub classes
            if include_subclasses and hasattr(expression, "subclasses"):
                results["subclasses"] = [_get_entity_name(cls) for cls in expression.subclasses() if cls != expression]
                
            # Super classes
            if include_superclasses:
                if hasattr(expression, "ancestors"):
                    ancestors = expression.ancestors()
                    results["superclasses"] = [_get_entity_name(cls) for cls in ancestors if cls != expression and cls != Thing and cls != owl.Thing]
                elif hasattr(expression, "is_a"):
                    results["superclasses"] = [_get_entity_name(cls) for cls in expression.is_a if cls != expression]
                    
            # Equivalent classes
            if include_equivalent and hasattr(expression, "equivalent_to"):
                results["equivalent_classes"] = [_get_entity_name(cls) for cls in expression.equivalent_to if cls != expression]
            
        # Calculate total count
        count = len(results["instances"]) + len(results["subclasses"]) + len(results["superclasses"]) + len(results["equivalent_classes"])
            
        return {
            "success": True,
            "results": results,
            "count": count
        }
    except Exception as e:
        logger.error(f"DL Query Error: {e}")
        return {
            "success": False,
            "error": str(e)
        }
