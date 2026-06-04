# =============================================================================
# SWRL 规则路由
# =============================================================================

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends

from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.web.routes.ontology_studio import _load_ontology_model, _save_ontology_model

router = APIRouter(tags=["swrl-rules"])
logger = logging.getLogger(__name__)

@router.get("/scene/{scene_id}/studio/swrl-rules")
async def get_swrl_rules(scene_id: str, username: str = Depends(verify_token)):
    """获取指定场景的所有 SWRL 规则"""
    model = _load_ontology_model(scene_id)
    rules = model.get("swrl_rules", [])
    return {"status": "success", "rules": rules}


@router.post("/scene/{scene_id}/studio/swrl-rules")
async def create_swrl_rule(scene_id: str, rule_data: Dict[str, Any], username: str = Depends(require_admin)):
    """创建或更新 SWRL 规则"""
    model = _load_ontology_model(scene_id)
    
    rule = {
        "name": rule_data.get("name"),
        "label": rule_data.get("label", rule_data.get("name")),
        "comment": rule_data.get("comment", ""),
        "body": rule_data.get("body", ""),      # 规则体（前提条件）
        "head": rule_data.get("head", ""),      # 规则头（结论）
        "enabled": rule_data.get("enabled", True)
    }
    
    if not rule["name"]:
        raise HTTPException(status_code=400, detail="规则名称不能为空")
        
    swrl_rules = model.setdefault("swrl_rules", [])
    
    # 检查是否已存在，存在则更新
    for i, r in enumerate(swrl_rules):
        if r["name"] == rule["name"]:
            swrl_rules[i] = rule
            _save_ontology_model(scene_id, model)
            return {"status": "success", "rule": rule, "action": "updated"}
            
    # 不存在则添加
    swrl_rules.append(rule)
    _save_ontology_model(scene_id, model)
    
    return {"status": "success", "rule": rule, "action": "created"}

@router.delete("/scene/{scene_id}/studio/swrl-rules/{rule_name}")
async def delete_swrl_rule(scene_id: str, rule_name: str, username: str = Depends(require_admin)):
    """删除指定的 SWRL 规则"""
    model = _load_ontology_model(scene_id)
    
    if "swrl_rules" not in model:
        raise HTTPException(status_code=404, detail="找不到规则")
        
    swrl_rules = model["swrl_rules"]
    for i, r in enumerate(swrl_rules):
        if r["name"] == rule_name:
            deleted_rule = swrl_rules.pop(i)
            _save_ontology_model(scene_id, model)
            return {"status": "success", "deleted": deleted_rule}
            
    raise HTTPException(status_code=404, detail=f"找不到名为 {rule_name} 的规则")
