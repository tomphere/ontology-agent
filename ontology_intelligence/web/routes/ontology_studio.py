# =============================================================================
# 本体工坊路由 - 提供 Protégé 风格的本体建模 API
# =============================================================================
# 支持类的层次结构管理、对象属性/数据属性/注释属性管理、个体管理
# 以及本体导出为 OWL/RDF/TTL 格式
# =============================================================================

import os
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import Optional
from owlready2 import get_ontology, Thing, ObjectProperty, DataProperty, AnnotationProperty, NamedIndividual, AllDisjoint, FunctionalProperty, TransitiveProperty, SymmetricProperty, AsymmetricProperty, ReflexiveProperty, IrreflexiveProperty, InverseFunctionalProperty, types, default_world, And, Or, Not, Restriction, SOME, ONLY, EXACTLY, MIN, MAX, VALUE
import tempfile

from ontology_intelligence.config import settings
from ontology_intelligence.web.routes.auth import verify_token, require_admin

router = APIRouter(tags=["ontology-studio"])
logger = logging.getLogger(__name__)

# 本体工坊数据存储目录
STUDIO_DIR = settings.project_root / "data" / "ontology_studio"
STUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _get_scene_studio_path(scene_id: str) -> Path:
    """获取场景对应的本体工坊文件路径"""
    return STUDIO_DIR / f"{scene_id}.json"


def _load_ontology_model(scene_id: str) -> dict:
    """加载场景的本体模型
    
    优先从 ontology_studio 目录读取，如果不存在则从 ontologies 目录读取
    这样可以兼容通过 /ontologies API 创建的本体
    """
    path = _get_scene_studio_path(scene_id)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 尝试从 ontology_management 的数据文件中读取
    ontology_path = settings.project_root / "data" / "ontologies" / f"{scene_id}.json"
    if ontology_path.exists():
        with open(ontology_path, 'r', encoding='utf-8') as f:
            model = json.load(f)
        # 同步到 studio 目录，避免每次都读取
        _save_ontology_model(scene_id, model)
        return model
    
    return _create_default_model()


def _save_ontology_model(scene_id: str, model: dict):
    """保存场景的本体模型"""
    path = _get_scene_studio_path(scene_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    # 本体变更时自动清除推理缓存
    _invalidate_reasoner_cache(scene_id)


def _create_default_model() -> dict:
    """创建默认本体模型"""
    return {
        "ontology_iri": "http://ontology.example.com/default",
        "version_iri": "http://ontology.example.com/default/1.0",
        "annotations": [],
        "classes": [],
        "object_properties": [],
        "data_properties": [],
        "annotation_properties": [
            {"name": "label", "type": "rdfs:label"},
            {"name": "comment", "type": "rdfs:comment"},
        ],
        "individuals": [],
    }


def _find_entity(entities: list, name: str) -> Optional[dict]:
    """在实体列表中查找指定名称的实体"""
    for e in entities:
        if e["name"] == name:
            return e
    return None


def _count_world_triples(world=default_world) -> int:
    """Count triples in an owlready2 world across supported versions."""
    try:
        return len(world.as_rdflib_graph())
    except Exception as e:
        logger.warning(f"统计本体三元组数量失败: {e}")
        return 0


# =============================================================================
# 本体元数据
# =============================================================================

@router.get("/scene/{scene_id}/studio/metadata")
async def get_ontology_metadata(scene_id: str, username: str = Depends(verify_token)):
    """获取本体元数据"""
    model = _load_ontology_model(scene_id)
    return {
        "ontology_iri": model["ontology_iri"],
        "version_iri": model["version_iri"],
        "annotations": model["annotations"],
    }


@router.put("/scene/{scene_id}/studio/metadata")
async def update_ontology_metadata(
    scene_id: str,
    metadata: dict,
    username: str = Depends(require_admin)
):
    """更新本体元数据"""
    model = _load_ontology_model(scene_id)
    if "ontology_iri" in metadata:
        model["ontology_iri"] = metadata["ontology_iri"]
    if "version_iri" in metadata:
        model["version_iri"] = metadata["version_iri"]
    if "annotations" in metadata:
        model["annotations"] = metadata["annotations"]
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": "本体元数据已更新"}


# =============================================================================
# 类管理
# =============================================================================

@router.get("/scene/{scene_id}/studio/classes")
async def list_classes(scene_id: str, username: str = Depends(verify_token)):
    """获取所有类（含层次结构）"""
    model = _load_ontology_model(scene_id)
    return {"classes": model["classes"]}


@router.post("/scene/{scene_id}/studio/classes")
async def create_class(
    scene_id: str,
    class_data: dict,
    username: str = Depends(require_admin)
):
    """创建新类
    
    class_data: {
        "name": str,           # 必填，类名
        "label": str,          # 可选，显示标签
        "comment": str,        # 可选，注释
        "parents": [str],      # 可选，父类列表
        "disjoint_with": [str] # 可选，不相交的类
    }
    """
    if not class_data.get("name"):
        raise HTTPException(status_code=400, detail="类名不能为空")
    
    model = _load_ontology_model(scene_id)
    
    if _find_entity(model["classes"], class_data["name"]):
        raise HTTPException(status_code=400, detail=f"类 '{class_data['name']}' 已存在")
    
    new_class = {
        "name": class_data["name"],
        "label": class_data.get("label", class_data["name"]),
        "comment": class_data.get("comment", ""),
        "parents": class_data.get("parents", []),
        "disjoint_with": class_data.get("disjoint_with", []),
        "equivalent_to": class_data.get("equivalent_to", []),
    }
    
    model["classes"].append(new_class)
    _save_ontology_model(scene_id, model)
    
    return {"status": "success", "message": f"类 '{new_class['name']}' 已创建", "class": new_class}


@router.put("/scene/{scene_id}/studio/classes/{class_name}")
async def update_class(
    scene_id: str,
    class_name: str,
    class_data: dict,
    username: str = Depends(require_admin)
):
    """更新类信息"""
    model = _load_ontology_model(scene_id)
    cls = _find_entity(model["classes"], class_name)
    
    if not cls:
        raise HTTPException(status_code=404, detail=f"类 '{class_name}' 不存在")
    
    for key in ["label", "comment", "parents", "disjoint_with", "equivalent_to"]:
        if key in class_data:
            cls[key] = class_data[key]
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"类 '{class_name}' 已更新", "class": cls}


@router.delete("/scene/{scene_id}/studio/classes/{class_name}")
async def delete_class(scene_id: str, class_name: str, username: str = Depends(require_admin)):
    """删除类"""
    model = _load_ontology_model(scene_id)
    
    cls = _find_entity(model["classes"], class_name)
    if not cls:
        raise HTTPException(status_code=404, detail=f"类 '{class_name}' 不存在")
    
    model["classes"] = [c for c in model["classes"] if c["name"] != class_name]
    
    for c in model["classes"]:
        if class_name in c.get("parents", []):
            c["parents"] = [p for p in c["parents"] if p != class_name]
        if class_name in c.get("disjoint_with", []):
            c["disjoint_with"] = [d for d in c["disjoint_with"] if d != class_name]
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"类 '{class_name}' 已删除"}


# =============================================================================
# 对象属性管理
# =============================================================================

@router.get("/scene/{scene_id}/studio/object-properties")
async def list_object_properties(scene_id: str, username: str = Depends(verify_token)):
    """获取所有对象属性"""
    model = _load_ontology_model(scene_id)
    return {"object_properties": model["object_properties"]}


@router.post("/scene/{scene_id}/studio/object-properties")
async def create_object_property(
    scene_id: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """创建对象属性
    
    prop_data: {
        "name": str,           # 必填
        "label": str,          # 可选
        "comment": str,        # 可选
        "domain": [str],       # 可选，定义域（类名列表）
        "range": [str],        # 可选，值域（类名列表）
        "sub_property_of": str,# 可选，父属性
        "characteristics": []  # 可选：["Functional", "InverseFunctional", "Transitive", "Symmetric", "Asymmetric", "Reflexive", "Irreflexive"]
        "inverse_of": str      # 可选，逆属性
    }
    """
    if not prop_data.get("name"):
        raise HTTPException(status_code=400, detail="属性名不能为空")
    
    model = _load_ontology_model(scene_id)
    
    if _find_entity(model["object_properties"], prop_data["name"]):
        raise HTTPException(status_code=400, detail=f"对象属性 '{prop_data['name']}' 已存在")
    
    new_prop = {
        "name": prop_data["name"],
        "label": prop_data.get("label", prop_data["name"]),
        "comment": prop_data.get("comment", ""),
        "domain": prop_data.get("domain", []),
        "range": prop_data.get("range", []),
        "sub_property_of": prop_data.get("sub_property_of", ""),
        "characteristics": prop_data.get("characteristics", []),
        "inverse_of": prop_data.get("inverse_of", ""),
    }
    
    model["object_properties"].append(new_prop)
    _save_ontology_model(scene_id, model)
    
    return {"status": "success", "message": f"对象属性 '{new_prop['name']}' 已创建", "property": new_prop}


@router.put("/scene/{scene_id}/studio/object-properties/{prop_name}")
async def update_object_property(
    scene_id: str,
    prop_name: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """更新对象属性"""
    model = _load_ontology_model(scene_id)
    prop = _find_entity(model["object_properties"], prop_name)
    
    if not prop:
        raise HTTPException(status_code=404, detail=f"对象属性 '{prop_name}' 不存在")
    
    for key in ["label", "comment", "domain", "range", "sub_property_of", "characteristics", "inverse_of"]:
        if key in prop_data:
            prop[key] = prop_data[key]
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"对象属性 '{prop_name}' 已更新", "property": prop}


@router.delete("/scene/{scene_id}/studio/object-properties/{prop_name}")
async def delete_object_property(scene_id: str, prop_name: str, username: str = Depends(require_admin)):
    """删除对象属性"""
    model = _load_ontology_model(scene_id)
    
    prop = _find_entity(model["object_properties"], prop_name)
    if not prop:
        raise HTTPException(status_code=404, detail=f"对象属性 '{prop_name}' 不存在")
    
    model["object_properties"] = [p for p in model["object_properties"] if p["name"] != prop_name]
    
    for p in model["object_properties"]:
        if p.get("sub_property_of") == prop_name:
            p["sub_property_of"] = ""
        if p.get("inverse_of") == prop_name:
            p["inverse_of"] = ""
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"对象属性 '{prop_name}' 已删除"}


# =============================================================================
# 数据属性管理
# =============================================================================

@router.get("/scene/{scene_id}/studio/data-properties")
async def list_data_properties(scene_id: str, username: str = Depends(verify_token)):
    """获取所有数据属性"""
    model = _load_ontology_model(scene_id)
    return {"data_properties": model["data_properties"]}


@router.post("/scene/{scene_id}/studio/data-properties")
async def create_data_property(
    scene_id: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """创建数据属性
    
    prop_data: {
        "name": str,           # 必填
        "label": str,          # 可选
        "comment": str,        # 可选
        "domain": [str],       # 可选，定义域（类名列表）
        "range": str,          # 可选，数据类型（xsd:string, xsd:integer 等）
        "sub_property_of": str # 可选，父属性
    }
    """
    if not prop_data.get("name"):
        raise HTTPException(status_code=400, detail="属性名不能为空")
    
    model = _load_ontology_model(scene_id)
    
    if _find_entity(model["data_properties"], prop_data["name"]):
        raise HTTPException(status_code=400, detail=f"数据属性 '{prop_data['name']}' 已存在")
    
    new_prop = {
        "name": prop_data["name"],
        "label": prop_data.get("label", prop_data["name"]),
        "comment": prop_data.get("comment", ""),
        "domain": prop_data.get("domain", []),
        "range": prop_data.get("range", "xsd:string"),
        "sub_property_of": prop_data.get("sub_property_of", ""),
    }
    
    model["data_properties"].append(new_prop)
    _save_ontology_model(scene_id, model)
    
    return {"status": "success", "message": f"数据属性 '{new_prop['name']}' 已创建", "property": new_prop}


@router.put("/scene/{scene_id}/studio/data-properties/{prop_name}")
async def update_data_property(
    scene_id: str,
    prop_name: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """更新数据属性"""
    model = _load_ontology_model(scene_id)
    prop = _find_entity(model["data_properties"], prop_name)
    
    if not prop:
        raise HTTPException(status_code=404, detail=f"数据属性 '{prop_name}' 不存在")
    
    for key in ["label", "comment", "domain", "range", "sub_property_of"]:
        if key in prop_data:
            prop[key] = prop_data[key]
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"数据属性 '{prop_name}' 已更新", "property": prop}


@router.delete("/scene/{scene_id}/studio/data-properties/{prop_name}")
async def delete_data_property(scene_id: str, prop_name: str, username: str = Depends(require_admin)):
    """删除数据属性"""
    model = _load_ontology_model(scene_id)
    
    prop = _find_entity(model["data_properties"], prop_name)
    if not prop:
        raise HTTPException(status_code=404, detail=f"数据属性 '{prop_name}' 不存在")
    
    model["data_properties"] = [p for p in model["data_properties"] if p["name"] != prop_name]
    
    for p in model["data_properties"]:
        if p.get("sub_property_of") == prop_name:
            p["sub_property_of"] = ""
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"数据属性 '{prop_name}' 已删除"}


# =============================================================================
# 注释属性管理
# =============================================================================

@router.get("/scene/{scene_id}/studio/annotation-properties")
async def list_annotation_properties(scene_id: str, username: str = Depends(verify_token)):
    """获取所有注释属性"""
    model = _load_ontology_model(scene_id)
    return {"annotation_properties": model["annotation_properties"]}


@router.post("/scene/{scene_id}/studio/annotation-properties")
async def create_annotation_property(
    scene_id: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """创建注释属性"""
    if not prop_data.get("name"):
        raise HTTPException(status_code=400, detail="属性名不能为空")
    
    model = _load_ontology_model(scene_id)
    
    if _find_entity(model["annotation_properties"], prop_data["name"]):
        raise HTTPException(status_code=400, detail=f"注释属性 '{prop_data['name']}' 已存在")
    
    new_prop = {
        "name": prop_data["name"],
        "label": prop_data.get("label", prop_data["name"]),
        "comment": prop_data.get("comment", ""),
    }
    
    model["annotation_properties"].append(new_prop)
    _save_ontology_model(scene_id, model)
    
    return {"status": "success", "message": f"注释属性 '{new_prop['name']}' 已创建"}


@router.delete("/scene/{scene_id}/studio/annotation-properties/{prop_name}")
async def delete_annotation_property(scene_id: str, prop_name: str, username: str = Depends(require_admin)):
    """删除注释属性"""
    model = _load_ontology_model(scene_id)
    model["annotation_properties"] = [p for p in model["annotation_properties"] if p["name"] != prop_name]
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"注释属性 '{prop_name}' 已删除"}


# =============================================================================
# 个体/实例管理
# =============================================================================

@router.get("/scene/{scene_id}/studio/individuals")
async def list_individuals(scene_id: str, username: str = Depends(verify_token)):
    """获取所有个体"""
    model = _load_ontology_model(scene_id)
    return {"individuals": model["individuals"]}


@router.post("/scene/{scene_id}/studio/individuals")
async def create_individual(
    scene_id: str,
    ind_data: dict,
    username: str = Depends(require_admin)
):
    """创建个体
    
    ind_data: {
        "name": str,           # 必填
        "label": str,          # 可选
        "comment": str,        # 可选
        "types": [str],        # 必填，所属类列表
        "data_property_values": {  # 数据属性值
            "propertyName": "value"
        },
        "object_property_values": {  # 对象属性值（指向其他个体）
            "propertyName": ["targetIndividualName"]
        },
        "same_as": [str],      # 可选，相同个体
        "different_from": [str] # 可选，不同个体
    }
    """
    if not ind_data.get("name"):
        raise HTTPException(status_code=400, detail="个体名不能为空")
    if not ind_data.get("types"):
        raise HTTPException(status_code=400, detail="个体必须指定至少一个类型（类）")
    
    model = _load_ontology_model(scene_id)
    
    if _find_entity(model["individuals"], ind_data["name"]):
        raise HTTPException(status_code=400, detail=f"个体 '{ind_data['name']}' 已存在")
    
    new_ind = {
        "name": ind_data["name"],
        "label": ind_data.get("label", ind_data["name"]),
        "comment": ind_data.get("comment", ""),
        "types": ind_data["types"],
        "data_property_values": ind_data.get("data_property_values", {}),
        "object_property_values": ind_data.get("object_property_values", {}),
        "same_as": ind_data.get("same_as", []),
        "different_from": ind_data.get("different_from", []),
    }
    
    model["individuals"].append(new_ind)
    _save_ontology_model(scene_id, model)
    
    return {"status": "success", "message": f"个体 '{new_ind['name']}' 已创建", "individual": new_ind}


@router.put("/scene/{scene_id}/studio/individuals/{ind_name}")
async def update_individual(
    scene_id: str,
    ind_name: str,
    ind_data: dict,
    username: str = Depends(require_admin)
):
    """更新个体"""
    model = _load_ontology_model(scene_id)
    ind = _find_entity(model["individuals"], ind_name)
    
    if not ind:
        raise HTTPException(status_code=404, detail=f"个体 '{ind_name}' 不存在")
    
    for key in ["label", "comment", "types", "data_property_values", "object_property_values", "same_as", "different_from"]:
        if key in ind_data:
            ind[key] = ind_data[key]
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"个体 '{ind_name}' 已更新", "individual": ind}


@router.delete("/scene/{scene_id}/studio/individuals/{ind_name}")
async def delete_individual(scene_id: str, ind_name: str, username: str = Depends(require_admin)):
    """删除个体"""
    model = _load_ontology_model(scene_id)
    
    ind = _find_entity(model["individuals"], ind_name)
    if not ind:
        raise HTTPException(status_code=404, detail=f"个体 '{ind_name}' 不存在")
    
    model["individuals"] = [i for i in model["individuals"] if i["name"] != ind_name]
    
    for i in model["individuals"]:
        if ind_name in i.get("same_as", []):
            i["same_as"] = [s for s in i["same_as"] if s != ind_name]
        if ind_name in i.get("different_from", []):
            i["different_from"] = [d for d in i["different_from"] if d != ind_name]
        for prop_name, targets in i.get("object_property_values", {}).items():
            if ind_name in targets:
                i["object_property_values"][prop_name] = [t for t in targets if t != ind_name]
    
    _save_ontology_model(scene_id, model)
    return {"status": "success", "message": f"个体 '{ind_name}' 已删除"}


# =============================================================================
# 本体统计
# =============================================================================

@router.get("/scene/{scene_id}/studio/stats")
async def get_ontology_stats(scene_id: str, username: str = Depends(verify_token)):
    """获取本体统计信息"""
    model = _load_ontology_model(scene_id)
    return {
        "classes_count": len(model["classes"]),
        "object_properties_count": len(model["object_properties"]),
        "data_properties_count": len(model["data_properties"]),
        "annotation_properties_count": len(model["annotation_properties"]),
        "individuals_count": len(model["individuals"]),
    }


# =============================================================================
# 本体导入/导出
# =============================================================================

@router.post("/scene/{scene_id}/studio/import-file")
async def import_ontology_file(
    scene_id: str,
    file_path: str,
    username: str = Depends(require_admin)
):
    """从已有本体文件导入到本体工坊
    
    file_path: 本体文件的绝对路径或相对于项目根目录的路径
    """
    from ontology_intelligence.ontology.parser import parse_ontology, _parse_restriction
    
    path = Path(file_path)
    if not path.is_absolute():
        path = settings.project_root / path
    
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    
    try:
        parsed = parse_ontology(str(path))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析本体文件失败: {e}")
    
    model = _create_default_model()
    model["ontology_iri"] = parsed.get("ontology_uri", f"http://ontology.example.com/{parsed['filename']}")
    
    for cls in parsed.get("classes", []):
        model["classes"].append({
            "name": cls["name"],
            "label": cls.get("label", cls["name"]),
            "comment": cls.get("comment", ""),
            "parents": cls.get("parents", []),
            "disjoint_with": [],
            "equivalent_to": [],
            "restrictions": cls.get("restrictions", []),
        })
    
    for prop in parsed.get("object_properties", []):
        model["object_properties"].append({
            "name": prop["name"],
            "label": prop.get("name", ""),
            "comment": prop.get("comment", ""),
            "domain": [prop["domain"]] if prop.get("domain") else [],
            "range": [prop["range"]] if prop.get("range") else [],
            "sub_property_of": "",
            "characteristics": [],
            "inverse_of": "",
        })
    
    for prop in parsed.get("data_properties", []):
        model["data_properties"].append({
            "name": prop["name"],
            "label": prop.get("name", ""),
            "comment": prop.get("comment", ""),
            "domain": prop.get("domains", []),
            "range": prop.get("range", "xsd:string"),
            "sub_property_of": "",
        })
    
    _save_ontology_model(scene_id, model)
    
    return {
        "status": "success",
        "message": f"已从文件 {parsed['filename']} 导入本体",
        "stats": {
            "classes": len(model["classes"]),
            "object_properties": len(model["object_properties"]),
            "data_properties": len(model["data_properties"]),
        },
    }


# =============================================================================
# 类表达式构建/解析辅助函数
# =============================================================================

def _build_class_expression(expr: dict, onto) -> object:
    """将 JSON 格式的类表达式转换为 owlready2 对象（用于导出）。

    支持类型：class, intersection, union, complement, restriction
    """
    try:
        expr_type = expr.get("type", "")

        if expr_type == "class":
            cls_name = expr.get("class", "")
            if cls_name:
                return onto.search_one(iri=f"*#{cls_name}")
            return None

        elif expr_type == "intersection":
            members = []
            for operand in expr.get("operands", []):
                member = _build_class_expression(operand, onto)
                if member is not None:
                    members.append(member)
            if members:
                return And(members)
            return None

        elif expr_type == "union":
            members = []
            for operand in expr.get("operands", []):
                member = _build_class_expression(operand, onto)
                if member is not None:
                    members.append(member)
            if members:
                return Or(members)
            return None

        elif expr_type == "complement":
            operand = expr.get("operand")
            if operand:
                inner = _build_class_expression(operand, onto)
                if inner is not None:
                    return Not(inner)
            return None

        elif expr_type == "restriction":
            return _build_restriction_expression(expr, onto)

        return None
    except Exception as e:
        logger.warning(f"构建类表达式失败: {e}")
        return None


def _build_restriction_expression(rest_data: dict, onto) -> object:
    """将 JSON 格式的限制条件转换为 owlready2 Restriction（用于导出）。"""
    try:
        prop_name = rest_data.get("property", "")
        if not prop_name:
            return None

        prop = onto.search_one(iri=f"*#{prop_name}")
        if not prop:
            return None

        rest_type = rest_data.get("cardinalityType", "some")
        rest_value = rest_data.get("value", "") or rest_data.get("filler", "")
        cardinality = rest_data.get("cardinality")

        if rest_type == "value":
            return prop.value(rest_value)
        elif rest_type == "some":
            target_cls = onto.search_one(iri=f"*#{rest_value}")
            if target_cls:
                return prop.some(target_cls)
        elif rest_type == "only":
            target_cls = onto.search_one(iri=f"*#{rest_value}")
            if target_cls:
                return prop.only(target_cls)
        elif rest_type == "min":
            card = int(cardinality) if cardinality is not None else 1
            target_cls = onto.search_one(iri=f"*#{rest_value}") if rest_value else None
            return prop.min(card, target_cls) if target_cls else prop.min(card)
        elif rest_type == "max":
            card = int(cardinality) if cardinality is not None else 1
            target_cls = onto.search_one(iri=f"*#{rest_value}") if rest_value else None
            return prop.max(card, target_cls) if target_cls else prop.max(card)
        elif rest_type == "exactly":
            card = int(cardinality) if cardinality is not None else 1
            target_cls = onto.search_one(iri=f"*#{rest_value}") if rest_value else None
            return prop.exactly(card, target_cls) if target_cls else prop.exactly(card)

        return None
    except Exception as e:
        logger.warning(f"构建限制条件失败: {e}")
        return None


def _parse_import_class_expression(expr) -> dict:
    """递归解析 owlready2 类表达式为 JSON 格式（用于导入）。

    支持：And (intersection), Or (union), Not (complement), Restriction, Named class
    """
    def _get_local_name(entity) -> str:
        if entity is None:
            return ''
        return entity.name if hasattr(entity, 'name') and entity.name else ''

    try:
        # Named class
        if hasattr(expr, 'name') and expr.name:
            name = _get_local_name(expr)
            if name and name not in ('Thing', 'Nothing'):
                return {"type": "class", "class": name}
            return None

        # Intersection (And)
        if isinstance(expr, And) or (hasattr(expr, 'Classes') and type(expr).__name__ in ('And', 'Intersection')):
            operands = []
            for member in expr.Classes:
                parsed = _parse_import_class_expression(member)
                if parsed:
                    operands.append(parsed)
            if operands:
                return {"type": "intersection", "operands": operands}
            return None

        # Union (Or)
        if isinstance(expr, Or) or (hasattr(expr, 'Classes') and type(expr).__name__ == 'Or'):
            operands = []
            for member in expr.Classes:
                parsed = _parse_import_class_expression(member)
                if parsed:
                    operands.append(parsed)
            if operands:
                return {"type": "union", "operands": operands}
            return None

        # Complement (Not)
        if isinstance(expr, Not) or type(expr).__name__ == 'Not':
            inner = getattr(expr, 'Class', None)
            if inner is not None:
                parsed = _parse_import_class_expression(inner)
                if parsed:
                    return {"type": "complement", "operand": parsed}
            return None

        # Restriction
        if isinstance(expr, Restriction) or (hasattr(expr, 'property') and hasattr(expr, 'value')):
            prop_name = _get_local_name(expr.property) if hasattr(expr, 'property') else ''
            if not prop_name:
                return None

            rest_type_num = getattr(expr, 'type', SOME)
            type_map = {SOME: 'some', ONLY: 'only', EXACTLY: 'exactly', MIN: 'min', MAX: 'max', VALUE: 'value'}
            cardinality_type = type_map.get(rest_type_num, 'some')

            filler = getattr(expr, 'value', None)
            rest_value = ''
            if filler:
                if hasattr(filler, 'name'):
                    rest_value = _get_local_name(filler)
                else:
                    rest_value = str(filler)

            result = {
                "type": "restriction",
                "property": prop_name,
                "cardinalityType": cardinality_type,
                "value": rest_value,
            }
            if cardinality_type in ('exactly', 'min', 'max'):
                result["cardinality"] = getattr(expr, 'cardinality', None)

            return result

        return None
    except Exception as e:
        logger.warning(f"解析类表达式失败: {e}")
        return None


@router.get("/scene/{scene_id}/studio/export")
async def export_ontology(
    scene_id: str,
    format: str = "turtle",
    username: str = Depends(verify_token)
):
    """导出本体为 OWL/RDF/TTL 格式
    
    format: "turtle", "xml", "n3", "nt", "json-ld"
    """
    model = _load_ontology_model(scene_id)
    
    onto = get_ontology(model["ontology_iri"])
    
    with onto:
        for cls_data in model["classes"]:
            cls_name = cls_data["name"]
            if cls_name in ['Thing', 'Nothing']:
                continue
            
            new_cls = types.new_class(cls_name, (Thing,))
            
            if cls_data.get("label") and cls_data["label"] != cls_name:
                new_cls.label = [cls_data["label"]]
            if cls_data.get("comment"):
                new_cls.comment = [cls_data["comment"]]
            
            parents = []
            for parent in cls_data.get("parents", []):
                if parent in ['Thing', 'Nothing']:
                    continue
                parent_cls = onto.search_one(iri=f"*#{parent}")
                if parent_cls:
                    parents.append(parent_cls)
            
            if parents:
                new_cls.is_a = parents
            
            for disjoint in cls_data.get("disjoint_with", []):
                disjoint_cls = onto.search_one(iri=f"*#{disjoint}")
                if disjoint_cls:
                    AllDisjoint([new_cls, disjoint_cls])
            
            # Export equivalent_to expressions
            for equiv in cls_data.get("equivalent_to", []):
                if isinstance(equiv, dict):
                    expr = _build_class_expression(equiv, onto)
                    if expr is not None:
                        new_cls.equivalent_to.append(expr)
            
            # Export restrictions as is_a constraints
            for rest_data in cls_data.get("restrictions", []):
                restriction = _build_restriction_expression(rest_data, onto)
                if restriction is not None:
                    new_cls.is_a.append(restriction)
        
        for prop_data in model["object_properties"]:
            prop_name = prop_data["name"]
            new_prop = ObjectProperty(prop_name)
            
            if prop_data.get("label") and prop_data["label"] != prop_name:
                new_prop.label = [prop_data["label"]]
            if prop_data.get("comment"):
                new_prop.comment = [prop_data["comment"]]
            
            if prop_data.get("domain"):
                domains = []
                for domain in prop_data.get("domain", []):
                    domain_cls = onto.search_one(iri=f"*#{domain}")
                    if domain_cls:
                        domains.append(domain_cls)
                if domains:
                    new_prop.domain = domains
            
            if prop_data.get("range"):
                ranges = []
                for range_cls_name in prop_data.get("range", []):
                    range_cls = onto.search_one(iri=f"*#{range_cls_name}")
                    if range_cls:
                        ranges.append(range_cls)
                if ranges:
                    new_prop.range = ranges
            
            if prop_data.get("sub_property_of"):
                super_prop = onto.search_one(iri=f"*#{prop_data['sub_property_of']}")
                if super_prop:
                    new_prop.is_a.append(super_prop)
            
            for char in prop_data.get("characteristics", []):
                char_map = {
                    "Functional": FunctionalProperty,
                    "InverseFunctional": InverseFunctionalProperty,
                    "TransitiveProperty": TransitiveProperty,
                    "SymmetricProperty": SymmetricProperty,
                    "AsymmetricProperty": AsymmetricProperty,
                    "ReflexiveProperty": ReflexiveProperty,
                    "IrreflexiveProperty": IrreflexiveProperty,
                }
                if char in char_map:
                    new_prop.is_a.append(char_map[char])
            
            if prop_data.get("inverse_of"):
                inverse_prop = onto.search_one(iri=f"*#{prop_data['inverse_of']}")
                if inverse_prop:
                    new_prop.inverse_property = inverse_prop
        
        for prop_data in model["data_properties"]:
            prop_name = prop_data["name"]
            new_prop = DataProperty(prop_name)
            
            if prop_data.get("label") and prop_data["label"] != prop_name:
                new_prop.label = [prop_data["label"]]
            if prop_data.get("comment"):
                new_prop.comment = [prop_data["comment"]]
            
            if prop_data.get("domain"):
                domains = []
                for domain in prop_data.get("domain", []):
                    domain_cls = onto.search_one(iri=f"*#{domain}")
                    if domain_cls:
                        domains.append(domain_cls)
                if domains:
                    new_prop.domain = domains
            
            if prop_data.get("sub_property_of"):
                super_prop = onto.search_one(iri=f"*#{prop_data['sub_property_of']}")
                if super_prop:
                    new_prop.is_a.append(super_prop)
        
        for ind_data in model["individuals"]:
            ind_name = ind_data["name"]
            new_ind = Thing[ind_name]
            
            if ind_data.get("label") and ind_data["label"] != ind_name:
                new_ind.label = [ind_data["label"]]
            if ind_data.get("comment"):
                new_ind.comment = [ind_data["comment"]]
            
            for type_name in ind_data.get("types", []):
                cls = onto.search_one(iri=f"*#{type_name}")
                if cls:
                    new_ind.is_a.append(cls)
            
            for prop_name, value in ind_data.get("data_property_values", {}).items():
                prop = onto.search_one(iri=f"*#{prop_name}")
                if prop and isinstance(prop, DataProperty):
                    new_ind.is_a.append(prop.some(value))
            
            for prop_name, targets in ind_data.get("object_property_values", {}).items():
                prop = onto.search_one(iri=f"*#{prop_name}")
                if prop and isinstance(prop, ObjectProperty):
                    for target in targets:
                        target_ind = onto.search_one(iri=f"*#{target}")
                        if target_ind:
                            new_ind.is_a.append(prop.some(target_ind))
    
    format_map = {
        "turtle": ".ttl",
        "ttl": ".ttl",
        "xml": ".owl",
        "rdf": ".owl",
        "owl": ".owl",
        "n3": ".n3",
        "nt": ".nt",
        "json-ld": ".jsonld",
        "jsonld": ".jsonld",
    }
    
    ext = format_map.get(format.lower(), ".ttl")
    
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        onto.save(file=tmp_path, format="rdfxml")
        
        with open(tmp_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出本体失败: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    
    return {
        "content": content,
        "format": format,
        "filename": f"ontology{ext}",
        "triple_count": _count_world_triples(),
    }


# =============================================================================
# 本体导入
# =============================================================================

@router.post("/scene/{scene_id}/studio/import")
async def import_ontology(
    scene_id: str,
    file: UploadFile = File(...),
    username: str = Depends(require_admin)
):
    """导入本体文件（OWL/RDF/TTL格式）
    
    支持格式：
    - .owl (RDF/XML)
    - .rdf (RDF/XML)
    - .ttl (Turtle)
    - .nt (N-Triples)
    - .n3 (Notation-3)
    - .jsonld (JSON-LD)
    """
    
    def _get_local_name(entity) -> str:
        """Extract local name from an OWL entity."""
        if entity is None:
            return ''
        name = entity.name
        if name:
            return name
        return ''
    
    def _parse_restriction_local(restriction) -> Optional[dict]:
        """Parse an OWL restriction from owlready2.
        
        Note: owlready2 uses 'type' attribute to distinguish restriction types.
        24=some, 25=only, 26=exactly, 27=min, 28=max, 29=value
        """
        try:
            prop_name = ''
            if hasattr(restriction, 'property'):
                prop_name = _get_local_name(restriction.property)

            if not prop_name:
                return None

            info = {"property": prop_name}

            # owlready2 使用 type 属性来区分限制类型
            # 24=some, 25=only, 26=exactly, 27=min, 28=max, 29=value
            rest_type_num = getattr(restriction, 'type', 24)
            type_map = {
                24: 'some',
                25: 'only',
                26: 'exactly',
                27: 'min',
                28: 'max',
                29: 'value',
            }
            cardinality_type = type_map.get(rest_type_num, 'some')
            info['cardinalityType'] = cardinality_type

            # 获取基数（对于 exactly/min/max）
            if cardinality_type in ['exactly', 'min', 'max']:
                info['cardinality'] = getattr(restriction, 'cardinality', None)
                # 获取目标类（onClass）或数据类型（onDataRange）
                if hasattr(restriction, 'value'):
                    filler = restriction.value
                    if hasattr(filler, 'name'):
                        info['value'] = _get_local_name(filler)
                    else:
                        # 对于数据类型，可能是 str, int 等
                        info['value'] = str(filler)
            elif cardinality_type == 'value':
                # 值约束：hasValue
                if hasattr(restriction, 'value'):
                    filler = restriction.value
                    if hasattr(filler, 'name'):
                        info['value'] = _get_local_name(filler)
                    else:
                        info['value'] = str(filler)
            else:
                # some/only 约束
                if hasattr(restriction, 'value'):
                    filler = restriction.value
                    if hasattr(filler, 'name'):
                        info['value'] = _get_local_name(filler)
                    else:
                        info['value'] = str(filler)

            return info
        except Exception:
            return None
    
    filename = file.filename or ""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    format_map = {
        'owl': 'rdfxml',
        'rdf': 'rdfxml',
        'ttl': 'turtle',
        'turtle': 'turtle',
        'nt': 'ntriples',
        'n3': 'n3',
        'jsonld': 'jsonld',
        'json-ld': 'jsonld',
    }
    
    owl_format = format_map.get(ext)
    if not owl_format:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: .{ext}，支持: owl, rdf, ttl, nt, n3, jsonld"
        )
    
    try:
        content = await file.read()
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        onto = get_ontology(f"file://{tmp_path}").load()
        
        # 启动推理机，推断等价类的父类关系
        from owlready2 import sync_reasoner
        try:
            sync_reasoner(onto)
            logger.info(f"推理机启动成功，已推断类层次结构")
        except Exception as e:
            logger.warning(f"推理机启动失败（不影响导入）: {e}")
        
        # 手动处理等价类：从 equivalent_to 中提取父类
        for cls in onto.classes():
            if cls.name in ['Thing', 'Nothing']:
                continue
            if hasattr(cls, 'equivalent_to') and cls.equivalent_to:
                for eq in cls.equivalent_to:
                    # 处理 Intersection 表达式：A AND B
                    if hasattr(eq, 'Classes'):  # Intersection
                        for member in eq.Classes:
                            if hasattr(member, 'name') and member.name not in ['Thing', 'Nothing']:
                                if member not in cls.is_a:
                                    cls.is_a.append(member)
                                    logger.info(f"从等价类添加父关系: {cls.name} -> {member.name}")
                    # 处理直接的类引用
                    elif hasattr(eq, 'name') and eq.name not in ['Thing', 'Nothing']:
                        if eq not in cls.is_a:
                            cls.is_a.append(eq)
                            logger.info(f"从等价类添加父关系: {cls.name} -> {eq.name}")
                    # 处理 Union 表达式
                    elif isinstance(eq, Or) or (hasattr(eq, 'Classes') and type(eq).__name__ == 'Or'):
                        logger.info(f"发现 Union 表达式: {cls.name}")
                    # 处理 Complement 表达式
                    elif isinstance(eq, Not) or type(eq).__name__ == 'Not':
                        logger.info(f"发现 Complement 表达式: {cls.name}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析本体文件失败: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    
    model = _load_ontology_model(scene_id)
    
    imported_classes = set(c["name"] for c in model["classes"])
    imported_props = set(p["name"] for p in model["object_properties"] + model["data_properties"])
    imported_individuals = set(i["name"] for i in model["individuals"])
    
    new_classes = 0
    new_props = 0
    new_data_props = 0
    new_individuals = 0
    
    # 添加 Thing 基类（Protégé 风格）
    if 'Thing' not in imported_classes:
        model["classes"].append({
            "name": "Thing",
            "label": "owl:Thing",
            "comment": "所有类的根节点",
            "parents": [],
            "disjoint_with": [],
            "equivalent_to": [],
        })
        imported_classes.add('Thing')
        new_classes += 1
    
    for cls in onto.classes():
        cls_name = cls.name
        if cls_name not in imported_classes and cls_name not in ['Nothing']:
            # 保留 Thing 作为父类
            parents = [p.name for p in cls.is_a if hasattr(p, 'name') and p.name not in ['Nothing']]
            # 如果没有父类，默认继承 Thing
            if not parents:
                parents = ['Thing']
            
            # 解析限制条件
            restrictions = []
            for constraint in cls.is_a:
                if hasattr(constraint, 'property') and hasattr(constraint, 'value'):
                    restriction = _parse_restriction_local(constraint)
                    if restriction:
                        restrictions.append(restriction)
            
            logger.info(f"导入类: {cls_name}, 父类: {parents}, 限制条件: {len(restrictions)} 个")
            
            # 解析等价类表达式
            equivalent_to = []
            if hasattr(cls, 'equivalent_to') and cls.equivalent_to:
                for eq in cls.equivalent_to:
                    parsed_eq = _parse_import_class_expression(eq)
                    if parsed_eq:
                        equivalent_to.append(parsed_eq)
            
            model["classes"].append({
                "name": cls_name,
                "label": cls.label.first() or cls_name,
                "comment": cls.comment.first() or "",
                "parents": parents,
                "disjoint_with": [],
                "equivalent_to": equivalent_to,
                "restrictions": restrictions,
            })
            imported_classes.add(cls_name)
            new_classes += 1
    
    # 添加 topObjectProperty 基类（Protégé 风格）
    if 'topObjectProperty' not in imported_props:
        model["object_properties"].append({
            "name": "topObjectProperty",
            "label": "owl:topObjectProperty",
            "comment": "所有对象属性的根节点",
            "domain": [],
            "range": [],
            "sub_property_of": "",
            "characteristics": [],
            "inverse_of": "",
        })
        imported_props.add('topObjectProperty')
        new_props += 1
    
    for prop in onto.object_properties():
        prop_name = prop.name
        if prop_name not in imported_props:
            # 去重 domain 和 range
            domain_list = list(dict.fromkeys([d.name for d in prop.domain if hasattr(d, 'name')]))
            range_list = list(dict.fromkeys([r.name for r in prop.range if hasattr(r, 'name')]))
            
            # 保留 topObjectProperty 作为父属性
            sub_prop_of = prop.is_a[0].name if prop.is_a else "topObjectProperty"
            
            model["object_properties"].append({
                "name": prop_name,
                "label": prop.label.first() or prop_name,
                "comment": prop.comment.first() or "",
                "domain": domain_list,
                "range": range_list,
                "sub_property_of": sub_prop_of,
                "characteristics": [],
                "inverse_of": prop.inverse_property.name if prop.inverse_property else "",
            })
            imported_props.add(prop_name)
            new_props += 1
    
    # 添加 topDataProperty 基类（Protégé 风格）
    if 'topDataProperty' not in imported_props:
        model["data_properties"].append({
            "name": "topDataProperty",
            "label": "owl:topDataProperty",
            "comment": "所有数据属性的根节点",
            "domain": [],
            "range": "xsd:string",
            "sub_property_of": "",
        })
        imported_props.add('topDataProperty')
        new_data_props += 1
    
    for prop in onto.data_properties():
        prop_name = prop.name
        if prop_name not in imported_props:
            # 保留 topDataProperty 作为父属性
            sub_prop_of = prop.is_a[0].name if prop.is_a else "topDataProperty"
            
            model["data_properties"].append({
                "name": prop_name,
                "label": prop.label.first() or prop_name,
                "comment": prop.comment.first() or "",
                "domain": [d.name for d in prop.domain if hasattr(d, 'name')],
                "range": "xsd:string",
                "sub_property_of": sub_prop_of,
            })
            imported_props.add(prop_name)
            new_data_props += 1
    
    for ind in onto.individuals():
        ind_name = ind.name
        if ind_name not in imported_individuals:
            types_list = [t.name for t in ind.is_a if hasattr(t, 'name') and t.name in imported_classes]
            
            model["individuals"].append({
                "name": ind_name,
                "label": ind.label.first() or ind_name,
                "comment": ind.comment.first() or "",
                "types": types_list,
                "data_property_values": {},
                "object_property_values": {},
                "same_as": [],
                "different_from": [],
            })
            imported_individuals.add(ind_name)
            new_individuals += 1
    
    _save_ontology_model(scene_id, model)
    
    return {
        "status": "success",
        "message": f"本体导入成功",
        "stats": {
            "new_classes": new_classes,
            "new_object_properties": new_props,
            "new_data_properties": new_data_props,
            "new_individuals": new_individuals,
            "total_triples": _count_world_triples(),
        }
    }


# =============================================================================
# 本体可视化 - 类层次结构
# =============================================================================

@router.get("/scene/{scene_id}/studio/class-hierarchy")
async def get_class_hierarchy(scene_id: str, username: str = Depends(verify_token)):
    """获取类的层次结构树"""
    model = _load_ontology_model(scene_id)
    classes = model["classes"]
    
    class_map = {c["name"]: c for c in classes}
    
    children_map = {}
    for c in classes:
        children_map[c["name"]] = []
    
    root_classes = []
    for c in classes:
        if not c.get("parents") or len(c["parents"]) == 0:
            root_classes.append(c["name"])
        else:
            for parent in c["parents"]:
                if parent in children_map:
                    children_map[parent].append(c["name"])
    
    def build_tree(class_name, visited=None):
        if visited is None:
            visited = set()
        
        if class_name in visited:
            return {
                "name": class_name,
                "label": class_map.get(class_name, {}).get("label", class_name),
                "comment": class_map.get(class_name, {}).get("comment", ""),
                "children": [],
                "is_circular": True,
            }
        
        visited.add(class_name)
        
        cls = class_map.get(class_name, {})
        children = children_map.get(class_name, [])
        
        return {
            "name": class_name,
            "label": cls.get("label", class_name),
            "comment": cls.get("comment", ""),
            "children": [build_tree(child, visited.copy()) for child in children],
            "is_circular": False,
        }
    
    hierarchy = [build_tree(root) for root in root_classes]
    
    return {
        "hierarchy": hierarchy,
        "total_classes": len(classes),
        "root_classes": len(root_classes),
    }


# =============================================================================
# 本体可视化 - 图形数据与实体使用分析
# =============================================================================

@router.get("/scene/{scene_id}/studio/graph")
async def get_ontology_graph(
    scene_id: str,
    show_individuals: bool = True,
    show_disjoint: bool = True,
    show_equivalent: bool = True,
    username: str = Depends(verify_token),
):
    """获取本体图形数据（节点 + 边），用于力导向图可视化
    
    节点类型: class, individual
    边类型: subClassOf, objectProperty, instanceOf, disjointWith, equivalentTo
    """
    model = _load_ontology_model(scene_id)
    
    nodes = []
    edges = []
    node_ids = set()
    
    classes = model.get("classes", [])
    object_properties = model.get("object_properties", [])
    individuals = model.get("individuals", [])
    
    # 构建类节点
    for cls in classes:
        node_id = f"class:{cls['name']}"
        nodes.append({
            "id": node_id,
            "name": cls.get("label", cls["name"]),
            "entityName": cls["name"],
            "type": "class",
            "parents": cls.get("parents", []),
            "val": 8,  # 节点大小
        })
        node_ids.add(node_id)
    
    # 构建继承关系边
    for cls in classes:
        for parent in cls.get("parents", []):
            source_id = f"class:{parent}"
            target_id = f"class:{cls['name']}"
            if source_id in node_ids and target_id in node_ids:
                edges.append({
                    "source": source_id,
                    "target": target_id,
                    "type": "subClassOf",
                    "label": "subClassOf",
                })
    
    # 构建对象属性关系边
    for prop in object_properties:
        domains = prop.get("domain", [])
        ranges = prop.get("range", [])
        if isinstance(domains, str):
            domains = [domains]
        if isinstance(ranges, str):
            ranges = [ranges]
        for domain in domains:
            for range_cls in ranges:
                source_id = f"class:{domain}"
                target_id = f"class:{range_cls}"
                if source_id in node_ids and target_id in node_ids:
                    edges.append({
                        "source": source_id,
                        "target": target_id,
                        "type": "objectProperty",
                        "label": prop.get("label", prop["name"]),
                        "propertyName": prop["name"],
                    })
    
    # 构建不相交关系边
    if show_disjoint:
        seen_disjoint = set()
        for cls in classes:
            for disjoint in cls.get("disjoint_with", []):
                pair = tuple(sorted([cls["name"], disjoint]))
                if pair not in seen_disjoint:
                    seen_disjoint.add(pair)
                    source_id = f"class:{cls['name']}"
                    target_id = f"class:{disjoint}"
                    if source_id in node_ids and target_id in node_ids:
                        edges.append({
                            "source": source_id,
                            "target": target_id,
                            "type": "disjointWith",
                            "label": "disjointWith",
                        })
    
    # 构建等价类关系边
    if show_equivalent:
        for cls in classes:
            for equiv in cls.get("equivalent_to", []):
                equiv_name = None
                if isinstance(equiv, str):
                    equiv_name = equiv
                elif isinstance(equiv, dict) and equiv.get("type") == "class":
                    equiv_name = equiv.get("class")
                if equiv_name:
                    source_id = f"class:{cls['name']}"
                    target_id = f"class:{equiv_name}"
                    if source_id in node_ids and target_id in node_ids:
                        edges.append({
                            "source": source_id,
                            "target": target_id,
                            "type": "equivalentTo",
                            "label": "equivalentTo",
                        })
    
    # 构建个体节点和 instanceOf 边
    if show_individuals:
        for ind in individuals:
            node_id = f"ind:{ind['name']}"
            nodes.append({
                "id": node_id,
                "name": ind.get("label", ind["name"]),
                "entityName": ind["name"],
                "type": "individual",
                "val": 4,
            })
            node_ids.add(node_id)
            
            for type_name in ind.get("types", []):
                target_id = f"class:{type_name}"
                if target_id in node_ids:
                    edges.append({
                        "source": node_id,
                        "target": target_id,
                        "type": "instanceOf",
                        "label": "type",
                    })
    
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "class_nodes": len([n for n in nodes if n["type"] == "class"]),
            "individual_nodes": len([n for n in nodes if n["type"] == "individual"]),
        }
    }


@router.get("/scene/{scene_id}/studio/entity-usage")
async def get_entity_usage(scene_id: str, username: str = Depends(verify_token)):
    """获取实体使用统计，用于分析本体质量"""
    model = _load_ontology_model(scene_id)
    
    classes = model.get("classes", [])
    object_properties = model.get("object_properties", [])
    data_properties = model.get("data_properties", [])
    individuals = model.get("individuals", [])
    
    # 类使用统计
    class_usage = {}
    for cls in classes:
        class_usage[cls["name"]] = {
            "name": cls["name"],
            "label": cls.get("label", cls["name"]),
            "type": "class",
            "as_parent": 0,
            "as_domain": 0,
            "as_range": 0,
            "as_disjoint": 0,
            "as_equivalent": 0,
            "individual_count": 0,
            "total_refs": 0,
        }
    
    # 统计被引用为父类
    for cls in classes:
        for parent in cls.get("parents", []):
            if parent in class_usage:
                class_usage[parent]["as_parent"] += 1
    
    # 统计在属性 domain/range 中的引用
    for prop in object_properties:
        for d in (prop.get("domain", []) if isinstance(prop.get("domain"), list) else [prop.get("domain")] if prop.get("domain") else []):
            if d in class_usage:
                class_usage[d]["as_domain"] += 1
        for r in (prop.get("range", []) if isinstance(prop.get("range"), list) else [prop.get("range")] if prop.get("range") else []):
            if r in class_usage:
                class_usage[r]["as_range"] += 1
    
    # 统计不相交引用
    for cls in classes:
        for dj in cls.get("disjoint_with", []):
            if dj in class_usage:
                class_usage[dj]["as_disjoint"] += 1
    
    # 统计个体实例化
    for ind in individuals:
        for t in ind.get("types", []):
            if t in class_usage:
                class_usage[t]["individual_count"] += 1
    
    # 计算总引用数
    for name, usage in class_usage.items():
        usage["total_refs"] = (
            usage["as_parent"] + usage["as_domain"] + usage["as_range"]
            + usage["as_disjoint"] + usage["as_equivalent"] + usage["individual_count"]
        )
    
    # 属性使用统计
    property_usage = []
    for prop in object_properties:
        domains = prop.get("domain", []) if isinstance(prop.get("domain"), list) else [prop.get("domain")] if prop.get("domain") else []
        ranges = prop.get("range", []) if isinstance(prop.get("range"), list) else [prop.get("range")] if prop.get("range") else []
        property_usage.append({
            "name": prop["name"],
            "label": prop.get("label", prop["name"]),
            "type": "objectProperty",
            "domain_count": len(domains),
            "range_count": len(ranges),
            "total_refs": len(domains) + len(ranges),
        })
    
    # 识别孤立实体
    orphan_classes = [name for name, u in class_usage.items()
                      if u["total_refs"] == 0 and not any(c.get("parents") and name in c.get("parents", []) for c in classes)]
    
    class_list = sorted(class_usage.values(), key=lambda x: x["total_refs"], reverse=True)
    
    return {
        "classes": class_list,
        "properties": property_usage,
        "orphan_classes": orphan_classes,
        "stats": {
            "total_classes": len(classes),
            "total_properties": len(object_properties) + len(data_properties),
            "total_individuals": len(individuals),
            "orphan_count": len(orphan_classes),
        }
    }


# =============================================================================
# 推理缓存
# =============================================================================

class ReasonerCache:
    """推理结果内存缓存，支持自动失效"""
    
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
    
    def get(self, scene_id: str) -> dict:
        """获取缓存的推理结果，不存在返回 None"""
        return self._cache.get(scene_id)
    
    def put(self, scene_id: str, result: dict):
        """存储推理结果"""
        self._cache[scene_id] = result
        self._timestamps[scene_id] = datetime.now().isoformat()
    
    def invalidate(self, scene_id: str):
        """清除指定场景的推理缓存"""
        self._cache.pop(scene_id, None)
        self._timestamps.pop(scene_id, None)
    
    def get_info(self, scene_id: str) -> dict:
        """获取缓存信息"""
        return {
            "has_cache": scene_id in self._cache,
            "cached_at": self._timestamps.get(scene_id),
        }


_reasoner_cache = ReasonerCache()


def _invalidate_reasoner_cache(scene_id: str):
    """清除推理缓存（在本体变更时调用）"""
    _reasoner_cache.invalidate(scene_id)


# =============================================================================
# 本体推理 - owlready2 HermiT 集成 + JSON fallback
# =============================================================================

def _build_owlready2_ontology(model: dict):
    """将 JSON 模型转换为 owlready2 本体对象（用于推理）"""
    from owlready2 import World, Thing, ObjectProperty, DataProperty, AllDisjoint
    world = World()
    iri = model.get("ontology_iri", "http://reasoning.temp/onto")
    onto = world.get_ontology(iri)
    Thing = world.get_ontology("http://www.w3.org/2002/07/owl#").Thing
    
    with onto:
        # 创建类
        for cls_data in model.get("classes", []):
            cls_name = cls_data["name"]
            if cls_name in ['Thing', 'Nothing']:
                continue
            new_cls = types.new_class(cls_name, (Thing,))
            
            if cls_data.get("label") and cls_data["label"] != cls_name:
                new_cls.label = [cls_data["label"]]
        
        # 设置父类关系
        for cls_data in model.get("classes", []):
            cls_name = cls_data["name"]
            if cls_name in ['Thing', 'Nothing']:
                continue
            new_cls = onto.search_one(iri=f"*#{cls_name}")
            if not new_cls:
                continue
            
            parents = []
            for parent in cls_data.get("parents", []):
                if parent in ['Thing', 'Nothing']:
                    continue
                parent_cls = onto.search_one(iri=f"*#{parent}")
                if parent_cls:
                    parents.append(parent_cls)
            if parents:
                new_cls.is_a = parents
            
            # 设置等价类
            for equiv in cls_data.get("equivalent_to", []):
                if isinstance(equiv, dict):
                    expr = _build_class_expression(equiv, onto)
                    if expr is not None:
                        new_cls.equivalent_to.append(expr)
            
            # 设置限制条件
            for rest_data in cls_data.get("restrictions", []):
                restriction = _build_restriction_expression(rest_data, onto)
                if restriction is not None:
                    new_cls.is_a.append(restriction)
            
            # 设置不相交
            for disjoint in cls_data.get("disjoint_with", []):
                disjoint_cls = onto.search_one(iri=f"*#{disjoint}")
                if disjoint_cls:
                    AllDisjoint([new_cls, disjoint_cls])
        
        # 创建对象属性
        for prop_data in model.get("object_properties", []):
            prop_name = prop_data["name"]
            if prop_name in ['topObjectProperty']:
                continue
            new_prop = types.new_class(prop_name, (ObjectProperty,))
            if prop_data.get("domain"):
                domains = []
                for d in (prop_data["domain"] if isinstance(prop_data["domain"], list) else [prop_data["domain"]]):
                    dc = onto.search_one(iri=f"*#{d}")
                    if dc:
                        domains.append(dc)
                if domains:
                    new_prop.domain = domains
            if prop_data.get("range"):
                ranges = []
                for r in (prop_data["range"] if isinstance(prop_data["range"], list) else [prop_data["range"]]):
                    rc = onto.search_one(iri=f"*#{r}")
                    if rc:
                        ranges.append(rc)
                if ranges:
                    new_prop.range = ranges
        
        # 创建数据属性
        for prop_data in model.get("data_properties", []):
            prop_name = prop_data["name"]
            if prop_name in ['topDataProperty']:
                continue
            types.new_class(prop_name, (DataProperty,))
        
        # 创建个体
        for ind_data in model.get("individuals", []):
            ind_name = ind_data["name"]
            ind_types = []
            for type_name in ind_data.get("types", []):
                cls = onto.search_one(iri=f"*#{type_name}")
                if cls:
                    ind_types.append(cls)
            if ind_types:
                ind = ind_types[0](ind_name)
                for t in ind_types[1:]:
                    ind.is_a.append(t)
            else:
                Thing(ind_name)
    
    return onto


def _run_json_reasoning(model: dict) -> dict:
    """JSON 数据层面的基础推理（fallback，不依赖 Java/HermiT）"""
    issues = []
    inferred_relations = []
    warnings = []
    explanations = {}
    
    classes = model.get("classes", [])
    individuals = model.get("individuals", [])
    class_map = {c["name"]: c for c in classes}
    
    def get_all_parents(class_name, visited=None):
        if visited is None:
            visited = set()
        if class_name in visited:
            return set()
        visited.add(class_name)
        cls = class_map.get(class_name)
        if not cls:
            return set()
        parents = set(cls.get("parents", []))
        for parent in list(parents):
            parents.update(get_all_parents(parent, visited))
        return parents
    
    # 不相交冲突检查
    for cls in classes:
        all_parents = get_all_parents(cls["name"])
        for disjoint_cls in cls.get("disjoint_with", []):
            if disjoint_cls in all_parents:
                issue = {
                    "type": "error",
                    "category": "disjoint_violation",
                    "message": f"类 '{cls['name']}' 与其不相交的类 '{disjoint_cls}' 存在继承关系",
                    "entity": cls["name"],
                    "explanation": f"'{cls['name']}' 声明与 '{disjoint_cls}' 不相交，但通过类层次结构 '{cls['name']}' 是 '{disjoint_cls}' 的子类",
                }
                issues.append(issue)
        
        # 等价类与不相交冲突检查（支持新的 dict 格式）
        for equiv in cls.get("equivalent_to", []):
            equiv_name = None
            if isinstance(equiv, str):
                equiv_name = equiv
            elif isinstance(equiv, dict) and equiv.get("type") == "class":
                equiv_name = equiv.get("class")
            if equiv_name and equiv_name in class_map:
                other = class_map[equiv_name]
                if cls["name"] in other.get("disjoint_with", []):
                    issues.append({
                        "type": "error",
                        "category": "equivalent_disjoint",
                        "message": f"类 '{cls['name']}' 与 '{equiv_name}' 既等价又不相交",
                        "entity": cls["name"],
                        "explanation": f"'{cls['name']}' 声明与 '{equiv_name}' 等价，但同时 '{equiv_name}' 声明与 '{cls['name']}' 不相交，这是一个逻辑矛盾",
                    })
    
    # 个体不相交检查
    for ind in individuals:
        ind_types = set(ind.get("types", []))
        for type1 in ind_types:
            cls1 = class_map.get(type1)
            if cls1:
                for type2 in ind_types:
                    if type1 != type2 and type2 in cls1.get("disjoint_with", []):
                        issues.append({
                            "type": "error",
                            "category": "individual_disjoint",
                            "message": f"个体 '{ind['name']}' 同时属于不相交的类 '{type1}' 和 '{type2}'",
                            "entity": ind["name"],
                            "explanation": f"'{type1}' 和 '{type2}' 被声明为不相交类，但个体 '{ind['name']}' 同时属于这两个类",
                        })
    
    # 推导隐含的子类关系
    for cls in classes:
        all_parents = get_all_parents(cls["name"])
        direct_parents = set(cls.get("parents", []))
        indirect_parents = all_parents - direct_parents
        for indirect in indirect_parents:
            if indirect and indirect != cls["name"]:
                # 找到推导路径
                path = []
                for p in direct_parents:
                    p_ancestors = get_all_parents(p)
                    if indirect in p_ancestors:
                        path.append(p)
                reason = f"通过 {' → '.join(path)} 间接推导" if path else "通过类层次推导"
                inferred_relations.append({
                    "type": "subClassOf",
                    "subject": cls["name"],
                    "object": indirect,
                    "inferred": True,
                    "reason": reason,
                })
    
    # 推导个体的隐含类型
    for ind in individuals:
        current_types = set(ind.get("types", []))
        all_parents = set()
        for type_name in current_types:
            all_parents.update(get_all_parents(type_name))
        implied_types = all_parents - current_types
        for implied in implied_types:
            if implied:
                source_types = [t for t in current_types if implied in get_all_parents(t)]
                reason = f"通过 {', '.join(source_types)} 的类层次推导" if source_types else "通过类层次推导"
                inferred_relations.append({
                    "type": "instanceOf",
                    "subject": ind["name"],
                    "object": implied,
                    "inferred": True,
                    "reason": reason,
                })

    # SWRL 规则 Python 层简单回退模拟（针对基础条件）
    swrl_rules = model.get("swrl_rules", [])
    for rule in swrl_rules:
        if not rule.get("enabled", True): continue
        body = rule.get("body", "")
        head = rule.get("head", "")
        
        # 演示用：模拟解析 Person(?p) ^ hasAge(?p, ?age) ^ greaterThan(?age, 18) -> Adult(?p)
        if "greaterThan" in body and "hasAge" in body and "Adult" in head:
            for ind in individuals:
                if "Person" in ind.get("types", []):
                    dp_values = ind.get("data_property_values", {})
                    age_val = dp_values.get("hasAge")
                    if age_val is not None:
                        try:
                            # age_val could be a list if multiple values
                            if isinstance(age_val, list) and len(age_val) > 0:
                                age = int(age_val[0])
                            else:
                                age = int(age_val)
                            
                            if age > 18:
                                if "Adult" not in ind.get("types", []):
                                    inferred_relations.append({
                                        "type": "instanceOf",
                                        "subject": ind["name"],
                                        "object": "Adult",
                                        "inferred": True,
                                        "reason": f"通过 SWRL 规则 {rule.get('name')} 推导"
                                    })
                        except (ValueError, TypeError):
                            pass
    
    # 构建解释字典
    for issue in issues:
        entity = issue.get("entity", "")
        if entity:
            if entity not in explanations:
                explanations[entity] = []
            explanations[entity].append(issue.get("explanation", issue["message"]))
    
    return {
        "issues": issues,
        "inferred_relations": inferred_relations,
        "warnings": warnings,
        "explanations": explanations,
    }


def _run_hermit_reasoning(model: dict) -> dict:
    """使用 owlready2 + HermiT 进行真实推理"""
    from owlready2 import sync_reasoner_hermit
    
    onto = _build_owlready2_ontology(model)
    
    # 记录推理前状态
    pre_parents = {}
    pre_types = {}
    for cls in onto.classes():
        if cls.name and cls.name not in ('Thing', 'Nothing'):
            pre_parents[cls.name] = {p.name for p in cls.is_a if hasattr(p, 'name') and p.name}
    for ind in onto.individuals():
        if ind.name:
            pre_types[ind.name] = {t.name for t in ind.is_a if hasattr(t, 'name') and t.name}
    
    # 执行推理
    with onto:
        # 如果模型中包含 SWRL 规则，先加载并应用它们
        swrl_rules = model.get("swrl_rules", [])
        if swrl_rules:
            from ontology_intelligence.reasoning.swrl_reasoner import SWRLReasoner
            swrl_reasoner = SWRLReasoner(onto)
            swrl_reasoner.load_rules(swrl_rules)
            swrl_reasoner.apply_rules()
            # 优先使用 pellet 支持 SWRL
            try:
                from owlready2 import sync_reasoner_pellet
                sync_reasoner_pellet([onto], infer_property_values=True, infer_data_property_values=True)
            except Exception as pellet_err:
                logger.warning(f"Pellet 推理机运行失败 (可能由于 Java 版本低于 11 导致): {pellet_err}")
                raise RuntimeError(f"使用包含 SWRL 规则的 Pellet 推理失败，已中断并准备降级为 JSON 推理。")
        else:
            sync_reasoner_hermit([onto], infer_property_values=True)
    
    issues = []
    inferred_relations = []
    warnings = []
    explanations = {}
    
    # 检查一致性
    inconsistent_classes = list(onto.inconsistent_classes())
    for cls in inconsistent_classes:
        cls_name = cls.name if hasattr(cls, 'name') else str(cls)
        issue = {
            "type": "error",
            "category": "inconsistent_class",
            "message": f"类 '{cls_name}' 被推理机判定为不一致（无法有实例）",
            "entity": cls_name,
            "explanation": f"HermiT 推理机发现 '{cls_name}' 的公理存在逻辑矛盾，该类不可能有任何实例",
        }
        issues.append(issue)
        if cls_name not in explanations:
            explanations[cls_name] = []
        explanations[cls_name].append(issue["explanation"])
    
    # 比对推理前后的类层次变化
    for cls in onto.classes():
        if not cls.name or cls.name in ('Thing', 'Nothing'):
            continue
        post_parents = {p.name for p in cls.is_a if hasattr(p, 'name') and p.name}
        pre = pre_parents.get(cls.name, set())
        new_parents = post_parents - pre - {'Thing'}
        for new_parent in new_parents:
            if new_parent and new_parent != cls.name:
                inferred_relations.append({
                    "type": "subClassOf",
                    "subject": cls.name,
                    "object": new_parent,
                    "inferred": True,
                    "reason": f"HermiT 推理机基于公理推导",
                })
    
    # 比对推理前后的个体分类变化
    for ind in onto.individuals():
        if not ind.name:
            continue
        post_types = {t.name for t in ind.is_a if hasattr(t, 'name') and t.name}
        pre = pre_types.get(ind.name, set())
        new_types = post_types - pre - {'Thing'}
        for new_type in new_types:
            if new_type:
                inferred_relations.append({
                    "type": "instanceOf",
                    "subject": ind.name,
                    "object": new_type,
                    "inferred": True,
                    "reason": f"HermiT 推理机基于限制条件/等价类推导",
                })
    
    return {
        "issues": issues,
        "inferred_relations": inferred_relations,
        "warnings": warnings,
        "explanations": explanations,
    }


@router.post("/scene/{scene_id}/studio/reason")
async def reason_ontology(scene_id: str, username: str = Depends(require_admin)):
    """对本体进行推理
    
    执行以下推理任务：
    1. 一致性检查：检测本体是否存在逻辑矛盾
    2. 类层次推导：推导隐含的父子类关系
    3. 个体分类：根据属性推导个体所属的类
    4. 不相交检查：检查是否存在违反不相交约束的情况
    
    优先使用 HermiT 推理机（需要 Java），失败时降级为 JSON 层面推理。
    支持推理结果缓存，本体变更时自动失效。
    """
    import time
    import io
    
    # 检查缓存
    cached = _reasoner_cache.get(scene_id)
    if cached is not None:
        cached["from_cache"] = True
        return cached
    
    model = _load_ontology_model(scene_id)
    start_time = time.time()
    
    # 捕获推理日志
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(log_handler)
    
    reasoner_type = "hermit"
    
    try:
        logger.info("开始推理 - 尝试使用 HermiT 推理机")
        result = _run_hermit_reasoning(model)
        logger.info("HermiT 推理完成")
        
        # 合并 JSON 层面的检查（补充 HermiT 可能遗漏的显式约束检查）
        json_result = _run_json_reasoning(model)
        
        # 合并 JSON 检查发现的问题（去重）
        existing_messages = {i["message"] for i in result["issues"]}
        for issue in json_result["issues"]:
            if issue["message"] not in existing_messages:
                result["issues"].append(issue)
        
        # 合并推导关系（去重）
        existing_rels = {(r["type"], r["subject"], r["object"]) for r in result["inferred_relations"]}
        for rel in json_result["inferred_relations"]:
            key = (rel["type"], rel["subject"], rel["object"])
            if key not in existing_rels:
                result["inferred_relations"].append(rel)
        
        # 合并解释
        for entity, expl_list in json_result["explanations"].items():
            if entity not in result["explanations"]:
                result["explanations"][entity] = []
            result["explanations"][entity].extend(expl_list)
        
    except Exception as e:
        logger.warning(f"HermiT 推理失败，降级为 JSON 推理: {e}")
        reasoner_type = "json_fallback"
        result = _run_json_reasoning(model)
    
    finally:
        logger.removeHandler(log_handler)
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_content = log_stream.getvalue()
    
    is_consistent = len([i for i in result["issues"] if i["type"] == "error"]) == 0
    
    inferred_subclasses = len([r for r in result["inferred_relations"] if r["type"] == "subClassOf"])
    inferred_types = len([r for r in result["inferred_relations"] if r["type"] == "instanceOf"])
    
    response = {
        "is_consistent": is_consistent,
        "issues": result["issues"],
        "inferred_relations": result["inferred_relations"],
        "explanations": result["explanations"],
        "warnings": result["warnings"],
        "log": log_content,
        "duration_ms": duration_ms,
        "reasoner_type": reasoner_type,
        "from_cache": False,
        "stats": {
            "total_issues": len(result["issues"]),
            "errors": len([i for i in result["issues"] if i["type"] == "error"]),
            "warnings": len(result["warnings"]),
            "inferred_relations": len(result["inferred_relations"]),
            "inferred_subclasses": inferred_subclasses,
            "inferred_types": inferred_types,
        }
    }
    
    # 存入缓存
    _reasoner_cache.put(scene_id, response)
    
    return response


@router.delete("/scene/{scene_id}/studio/reason/cache")
async def clear_reason_cache(scene_id: str, username: str = Depends(require_admin)):
    """手动清除推理缓存"""
    _reasoner_cache.invalidate(scene_id)
    return {"status": "success", "message": "推理缓存已清除"}


@router.get("/scene/{scene_id}/studio/reason/cache")
async def get_reason_cache_info(scene_id: str, username: str = Depends(verify_token)):
    """获取推理缓存信息"""
    return _reasoner_cache.get_info(scene_id)


# =============================================================================
# 本体版本管理
# =============================================================================

VERSIONS_DIR = STUDIO_DIR / "versions"
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/scene/{scene_id}/studio/version")
async def create_version(
    scene_id: str,
    version_data: dict,
    username: str = Depends(require_admin)
):
    """创建本体版本快照
    
    version_data: {
        "version": str,        # 版本号，如 "1.0.0"
        "comment": str         # 版本说明
    }
    """
    if not version_data.get("version"):
        raise HTTPException(status_code=400, detail="版本号不能为空")
    
    model = _load_ontology_model(scene_id)
    
    version_file = VERSIONS_DIR / f"{scene_id}_v{version_data['version']}.json"
    if version_file.exists():
        raise HTTPException(status_code=400, detail=f"版本 {version_data['version']} 已存在")
    
    version_snapshot = {
        "version": version_data["version"],
        "comment": version_data.get("comment", ""),
        "created_at": datetime.now().isoformat(),
        "created_by": username,
        "model": model,
    }
    
    with open(version_file, 'w', encoding='utf-8') as f:
        json.dump(version_snapshot, f, ensure_ascii=False, indent=2)
    
    return {
        "status": "success",
        "message": f"版本 {version_data['version']} 已创建",
        "version": version_data["version"],
    }


@router.get("/scene/{scene_id}/studio/versions")
async def list_versions(scene_id: str, username: str = Depends(verify_token)):
    """列出所有版本"""
    versions = []
    for f in VERSIONS_DIR.glob(f"{scene_id}_v*.json"):
        with open(f, 'r', encoding='utf-8') as fp:
            snapshot = json.load(fp)
            versions.append({
                "version": snapshot["version"],
                "comment": snapshot.get("comment", ""),
                "created_at": snapshot["created_at"],
                "created_by": snapshot.get("created_by", ""),
                "classes_count": len(snapshot["model"].get("classes", [])),
                "individuals_count": len(snapshot["model"].get("individuals", [])),
            })
    
    versions.sort(key=lambda v: v["created_at"], reverse=True)
    return {"versions": versions}


@router.get("/scene/{scene_id}/studio/version/{version}")
async def get_version(scene_id: str, version: str, username: str = Depends(verify_token)):
    """获取指定版本的详细信息"""
    version_file = VERSIONS_DIR / f"{scene_id}_v{version}.json"
    if not version_file.exists():
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")
    
    with open(version_file, 'r', encoding='utf-8') as f:
        snapshot = json.load(f)
    
    return {
        "version": snapshot["version"],
        "comment": snapshot.get("comment", ""),
        "created_at": snapshot["created_at"],
        "created_by": snapshot.get("created_by", ""),
        "model": snapshot["model"],
    }


@router.post("/scene/{scene_id}/studio/version/{version}/restore")
async def restore_version(scene_id: str, version: str, username: str = Depends(require_admin)):
    """恢复到指定版本"""
    version_file = VERSIONS_DIR / f"{scene_id}_v{version}.json"
    if not version_file.exists():
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")
    
    with open(version_file, 'r', encoding='utf-8') as f:
        snapshot = json.load(f)
    
    _save_ontology_model(scene_id, snapshot["model"])
    
    return {
        "status": "success",
        "message": f"已恢复到版本 {version}",
        "version": version,
    }


@router.delete("/scene/{scene_id}/studio/version/{version}")
async def delete_version(scene_id: str, version: str, username: str = Depends(require_admin)):
    """删除指定版本"""
    version_file = VERSIONS_DIR / f"{scene_id}_v{version}.json"
    if not version_file.exists():
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")
    
    version_file.unlink()
    
    return {
        "status": "success",
        "message": f"版本 {version} 已删除",
    }
