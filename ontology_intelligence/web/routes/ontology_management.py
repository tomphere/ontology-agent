# =============================================================================
# 本体管理路由 - 支持多本体管理
# =============================================================================

import os
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import Optional
from owlready2 import get_ontology, Thing, ObjectProperty, DataProperty, AnnotationProperty, FunctionalProperty, TransitiveProperty, SymmetricProperty, AsymmetricProperty, ReflexiveProperty, IrreflexiveProperty, InverseFunctionalProperty, AllDifferent, AllDisjoint, default_world, types, ObjectPropertyClass, DataPropertyClass, Restriction, And, Or, Not, SOME, ONLY, EXACTLY, MIN, MAX, VALUE

from ontology_intelligence.config import settings
from ontology_intelligence.web.routes.auth import verify_token, require_admin

router = APIRouter(tags=["ontology-management"])
logger = logging.getLogger(__name__)

# 本体数据存储目录
ONTOLOGY_DIR = settings.project_root / "data" / "ontologies"
ONTOLOGY_DIR.mkdir(parents=True, exist_ok=True)


def _get_ontology_path(ontology_id: str) -> Path:
    """获取本体文件路径"""
    return ONTOLOGY_DIR / f"{ontology_id}.json"


def _load_ontology(ontology_id: str) -> dict:
    """加载本体模型"""
    path = _get_ontology_path(ontology_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"本体 {ontology_id} 不存在")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_ontology(ontology_id: str, model: dict):
    """保存本体模型"""
    path = _get_ontology_path(ontology_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(model, f, ensure_ascii=False, indent=2)


def _create_default_model(name: str, iri: str = '') -> dict:
    """创建默认本体模型"""
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": "",
        "ontology_iri": iri or f"http://ontology.example.com/{name.lower().replace(' ', '-')}",
        "version_iri": "",
        "annotations": [],
        "classes": [],
        "object_properties": [],
        "data_properties": [],
        "annotation_properties": [
            {"name": "label", "type": "rdfs:label"},
            {"name": "comment", "type": "rdfs:comment"},
        ],
        "individuals": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


def _get_ontology_index() -> list:
    """获取所有本体索引"""
    index_file = ONTOLOGY_DIR / "index.json"
    if not index_file.exists():
        return []
    with open(index_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_ontology_index(index: list):
    """保存本体索引"""
    index_file = ONTOLOGY_DIR / "index.json"
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _ontology_counts(model: dict) -> dict:
    """根据真实本体模型计算列表页摘要，避免索引统计滞后。"""
    return {
        "classes_count": len(model.get("classes", [])),
        "individuals_count": len(model.get("individuals", [])),
        "properties_count": len(model.get("object_properties", [])) + len(model.get("data_properties", [])),
    }


def _load_ontology_for_summary(ontology_id: str) -> Optional[dict]:
    """优先读取 Studio 模型；没有时再读取管理模型。"""
    studio_path = settings.project_root / "data" / "ontology_studio" / f"{ontology_id}.json"
    for path in (studio_path, _get_ontology_path(ontology_id)):
        if not path.exists():
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取本体摘要失败 {path}: {e}")
    return None


def _hydrate_ontology_summary(item: dict) -> dict:
    model = _load_ontology_for_summary(item.get("id", ""))
    if not model:
        return item

    summary = dict(item)
    for key in ("name", "description", "ontology_iri", "created_at", "updated_at"):
        if model.get(key):
            summary[key] = model[key]
    summary.update(_ontology_counts(model))
    return summary


# =============================================================================
# 本体 CRUD
# =============================================================================

@router.get("/ontologies")
async def list_all_ontologies(username: str = Depends(verify_token)):
    """列出所有本体"""
    index = _get_ontology_index()
    hydrated = [_hydrate_ontology_summary(item) for item in index]
    if hydrated != index:
        _save_ontology_index(hydrated)
    return {"ontologies": hydrated}


@router.post("/ontologies")
async def create_ontology(
    ontology_data: dict,
    username: str = Depends(require_admin)
):
    """创建新本体"""
    if not ontology_data.get("name"):
        raise HTTPException(status_code=400, detail="本体名称不能为空")
    
    ontology_id = str(uuid.uuid4())
    model = _create_default_model(
        name=ontology_data["name"],
        iri=ontology_data.get("iri", "")
    )
    model["id"] = ontology_id
    model["description"] = ontology_data.get("description", "")
    
    _save_ontology(ontology_id, model)
    
    index = _get_ontology_index()
    index.append({
        "id": ontology_id,
        "name": model["name"],
        "description": model["description"],
        "ontology_iri": model["ontology_iri"],
        "classes_count": 0,
        "individuals_count": 0,
        "properties_count": 0,
        "created_at": model["created_at"],
        "updated_at": model["updated_at"],
    })
    _save_ontology_index(index)
    
    return {
        "id": ontology_id,
        "name": model["name"],
        "description": model["description"],
        "message": f"本体 {model['name']} 已创建",
    }


@router.get("/ontologies/{ontology_id}")
async def get_ontology_details(ontology_id: str, username: str = Depends(verify_token)):
    """获取本体详细信息"""
    model = _load_ontology(ontology_id)
    return model


@router.delete("/ontologies/{ontology_id}")
async def delete_ontology(ontology_id: str, username: str = Depends(require_admin)):
    """删除本体"""
    path = _get_ontology_path(ontology_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"本体 {ontology_id} 不存在")
    
    path.unlink()
    
    index = _get_ontology_index()
    index = [o for o in index if o["id"] != ontology_id]
    _save_ontology_index(index)
    
    return {"status": "success", "message": f"本体 {ontology_id} 已删除"}


@router.put("/ontologies/{ontology_id}")
async def update_ontology(
    ontology_id: str,
    ontology_data: dict,
    username: str = Depends(require_admin)
):
    """更新本体元数据"""
    model = _load_ontology(ontology_id)
    
    if "name" in ontology_data:
        model["name"] = ontology_data["name"]
    if "description" in ontology_data:
        model["description"] = ontology_data["description"]
    if "ontology_iri" in ontology_data:
        model["ontology_iri"] = ontology_data["ontology_iri"]
    
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    index = _get_ontology_index()
    for item in index:
        if item["id"] == ontology_id:
            item["name"] = model["name"]
            item["description"] = model["description"]
            item["ontology_iri"] = model["ontology_iri"]
            item["updated_at"] = model["updated_at"]
            break
    _save_ontology_index(index)
    
    return {"status": "success", "message": "本体已更新"}


# =============================================================================
# 类表达式解析辅助函数
# =============================================================================

def _parse_mgmt_class_expression(expr, get_local_name) -> dict:
    """递归解析 owlready2 类表达式为 JSON 格式（用于导入）。

    支持：And (intersection), Or (union), Not (complement), Restriction, Named class
    """
    try:
        # Named class
        if hasattr(expr, 'name') and expr.name:
            name = get_local_name(expr)
            if name and name not in ('Thing', 'Nothing'):
                return {"type": "class", "class": name}
            return None

        # Intersection (And)
        if isinstance(expr, And) or (hasattr(expr, 'Classes') and type(expr).__name__ in ('And', 'Intersection')):
            operands = []
            for member in expr.Classes:
                parsed = _parse_mgmt_class_expression(member, get_local_name)
                if parsed:
                    operands.append(parsed)
            if operands:
                return {"type": "intersection", "operands": operands}
            return None

        # Union (Or)
        if isinstance(expr, Or) or (hasattr(expr, 'Classes') and type(expr).__name__ == 'Or'):
            operands = []
            for member in expr.Classes:
                parsed = _parse_mgmt_class_expression(member, get_local_name)
                if parsed:
                    operands.append(parsed)
            if operands:
                return {"type": "union", "operands": operands}
            return None

        # Complement (Not)
        if isinstance(expr, Not) or type(expr).__name__ == 'Not':
            inner = getattr(expr, 'Class', None)
            if inner is not None:
                parsed = _parse_mgmt_class_expression(inner, get_local_name)
                if parsed:
                    return {"type": "complement", "operand": parsed}
            return None

        # Restriction
        if isinstance(expr, Restriction) or (hasattr(expr, 'property') and hasattr(expr, 'value')):
            prop_name = get_local_name(expr.property) if hasattr(expr, 'property') else ''
            if not prop_name:
                return None

            rest_type_num = getattr(expr, 'type', SOME)
            type_map = {SOME: 'some', ONLY: 'only', EXACTLY: 'exactly', MIN: 'min', MAX: 'max', VALUE: 'value'}
            cardinality_type = type_map.get(rest_type_num, 'some')

            filler = getattr(expr, 'value', None)
            rest_value = ''
            if filler:
                if hasattr(filler, 'name'):
                    rest_value = get_local_name(filler)
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


def _build_mgmt_restriction(rest_data: dict, onto) -> object:
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
        elif rest_type in ("min", "max", "exactly"):
            card = int(cardinality) if cardinality is not None else 1
            target_cls = onto.search_one(iri=f"*#{rest_value}") if rest_value else None
            fn = getattr(prop, rest_type)
            return fn(card, target_cls) if target_cls else fn(card)

        return None
    except Exception as e:
        logger.warning(f"构建限制条件失败: {e}")
        return None


# =============================================================================
# 本体导入
# =============================================================================

@router.post("/ontologies/{ontology_id}/import")
async def import_ontology(
    ontology_id: str,
    file: UploadFile = File(...),
    username: str = Depends(require_admin)
):
    """导入本体文件（OWL/RDF/TTL等）"""
    model = _load_ontology(ontology_id)
    
    content = await file.read()
    temp_file = ONTOLOGY_DIR / f"temp_import_{ontology_id}_{file.filename}"
    
    try:
        with open(temp_file, 'wb') as f:
            f.write(content)
        
        onto = get_ontology(f"file://{temp_file}").load()
        
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析本体文件失败: {str(e)}")
    finally:
        if temp_file.exists():
            temp_file.unlink()
    
    stats = {
        "new_classes": 0,
        "new_object_properties": 0,
        "new_data_properties": 0,
        "new_individuals": 0,
    }
    
    existing_classes = {c["name"] for c in model["classes"]}
    existing_object_props = {p["name"] for p in model["object_properties"]}
    existing_data_props = {p["name"] for p in model["data_properties"]}
    existing_individuals = {i["name"] for i in model["individuals"]}
    
    # 添加 Thing 基类（Protégé 风格）
    if 'Thing' not in existing_classes:
        model["classes"].append({
            "name": "Thing",
            "label": "owl:Thing",
            "parents": [],
            "description": "所有类的根节点",
            "equivalent_to": [],
            "restrictions": [],
            "disjoint_with": [],
        })
        existing_classes.add('Thing')
        stats["new_classes"] += 1
    
    def get_local_name(entity):
        """从OWL实体中提取本地名称"""
        if entity is None:
            return ''
        name = entity.name
        if name:
            return name
        return ''
    
    for cls in onto.classes():
        cls_name = get_local_name(cls)
        if not cls_name or cls_name in ['Nothing'] or cls_name.startswith('owl:'):
            continue
        
        if cls_name not in existing_classes:
            label = cls_name
            if cls.label:
                label = cls.label.first()
            
            comment = ''
            if cls.comment:
                comment = cls.comment.first()
            
            parents = []
            inferred_restrictions = []
            for parent in cls.is_a:
                # 处理命名类（有 name 属性）
                if hasattr(parent, 'name') and parent.name:
                    parent_name = get_local_name(parent)
                    if parent_name and parent_name not in ['Nothing']:
                        parents.append(parent_name)
                # 处理推理出的限制条件（Restriction 没有 name 属性）
                elif isinstance(parent, Restriction):
                    prop_name = get_local_name(parent.property) if hasattr(parent, 'property') else ''
                    
                    # 使用 type 属性判断限制类型
                    rest_type_num = getattr(parent, 'type', SOME)
                    if rest_type_num == SOME:
                        rest_type = 'some'
                    elif rest_type_num == ONLY:
                        rest_type = 'only'
                    elif rest_type_num == EXACTLY:
                        rest_type = 'exactly'
                    elif rest_type_num == MIN:
                        rest_type = 'min'
                    elif rest_type_num == MAX:
                        rest_type = 'max'
                    elif rest_type_num == VALUE:
                        rest_type = 'value'
                    else:
                        rest_type = 'some'
                    
                    # value 属性存储 filler（填充类或数据类型）
                    filler = getattr(parent, 'value', None)
                    if filler:
                        if hasattr(filler, 'name'):
                            rest_value = get_local_name(filler)
                        elif filler is str:
                            rest_value = 'xsd:string'
                        elif filler is int:
                            rest_value = 'xsd:integer'
                        elif filler is float:
                            rest_value = 'xsd:float'
                        elif filler is bool:
                            rest_value = 'xsd:boolean'
                        else:
                            rest_value = str(filler)
                    else:
                        rest_value = ''
                    
                    inferred_restrictions.append({
                        'property': prop_name,
                        'cardinalityType': rest_type,
                        'value': rest_value,
                        'cardinality': getattr(parent, 'cardinality', None),
                    })
            
            # 如果没有父类，默认继承 Thing
            if not parents:
                parents = ['Thing']
            
            # 处理等价类表达式 - 统一使用 operands 格式
            equivalent_to = []
            if hasattr(cls, 'equivalent_to') and cls.equivalent_to:
                for eq in cls.equivalent_to:
                    parsed_eq = _parse_mgmt_class_expression(eq, get_local_name)
                    if parsed_eq:
                        equivalent_to.append(parsed_eq)
            
            logger.info(f"导入类: {cls_name}, 父类: {parents}, equivalent_to: {equivalent_to}, inferred_restrictions: {inferred_restrictions}")
            
            # 获取 disjoint_with 信息
            disjoint_with = []
            for disjoint_set in onto.disjoints():
                if cls in disjoint_set.entities:
                    for other in disjoint_set.entities:
                        if other != cls and hasattr(other, 'name'):
                            other_name = get_local_name(other)
                            if other_name and other_name not in ['Nothing']:
                                disjoint_with.append(other_name)
            
            model["classes"].append({
                "name": cls_name,
                "label": label,
                "parents": parents,
                "description": comment,
                "equivalent_to": equivalent_to,
                "restrictions": inferred_restrictions,
                "disjoint_with": disjoint_with,
            })
            existing_classes.add(cls_name)
            stats["new_classes"] += 1
    
    # 添加 topObjectProperty 基类（Protégé 风格）
    if 'topObjectProperty' not in existing_object_props:
        model["object_properties"].append({
            "name": "topObjectProperty",
            "label": "owl:topObjectProperty",
            "comment": "",
            "domain": [],
            "range": [],
            "description": "所有对象属性的根节点",
            "sub_property_of": "",
            "inverse_of": "",
            "characteristics": [],
            "disjoint_with": [],
        })
        existing_object_props.add('topObjectProperty')
        stats["new_object_properties"] += 1
    
    for prop in onto.properties():
        # 只处理对象属性
        if not isinstance(prop, ObjectPropertyClass):
            continue
            
        prop_name = get_local_name(prop)
        if not prop_name:
            continue
        
        if prop_name not in existing_object_props:
            label = prop_name
            if prop.label:
                label = prop.label.first()
            
            domains = []
            if prop.domain:
                for d in prop.domain:
                    d_name = get_local_name(d)
                    if d_name and d_name not in ['Thing', 'Nothing']:
                        domains.append(d_name)
            
            ranges = []
            if prop.range:
                for r in prop.range:
                    r_name = get_local_name(r)
                    if r_name and r_name not in ['Thing', 'Nothing']:
                        ranges.append(r_name)
            
            characteristics = []
            if FunctionalProperty in prop.is_a:
                characteristics.append('Functional')
            if TransitiveProperty in prop.is_a:
                characteristics.append('TransitiveProperty')
            if SymmetricProperty in prop.is_a:
                characteristics.append('SymmetricProperty')
            if AsymmetricProperty in prop.is_a:
                characteristics.append('AsymmetricProperty')
            if ReflexiveProperty in prop.is_a:
                characteristics.append('ReflexiveProperty')
            if IrreflexiveProperty in prop.is_a:
                characteristics.append('IrreflexiveProperty')
            if InverseFunctionalProperty in prop.is_a:
                characteristics.append('InverseFunctional')
            
            inverse_of = ''
            if prop.inverse_property:
                inverse_of = get_local_name(prop.inverse_property)
            
            # 过滤掉 owlready2 内部基类和特性类
            INTERNAL_CLASSES = {'ObjectProperty', 'Thing', 'SymmetricProperty', 'TransitiveProperty', 
                              'FunctionalProperty', 'InverseFunctionalProperty', 'AsymmetricProperty',
                              'ReflexiveProperty', 'IrreflexiveProperty'}
            
            sub_property_of = 'topObjectProperty'
            for parent in prop.is_a:
                if hasattr(parent, 'name') and parent.name and parent.name != prop_name:
                    if parent.name not in INTERNAL_CLASSES:
                        sub_property_of = parent.name
                        break
            
            logger.info(f"导入对象属性: {prop_name}, sub_property_of: {sub_property_of}, is_a: {[p.name for p in prop.is_a if hasattr(p, 'name')]}")
            
            model["object_properties"].append({
                "name": prop_name,
                "label": label,
                "comment": "",
                "domain": domains,
                "range": ranges,
                "description": "",
                "sub_property_of": sub_property_of,
                "inverse_of": inverse_of,
                "characteristics": characteristics,
                "disjoint_with": [],
            })
            existing_object_props.add(prop_name)
            stats["new_object_properties"] += 1
    
    # 添加 topDataProperty 基类（Protégé 风格）
    if 'topDataProperty' not in existing_data_props:
        model["data_properties"].append({
            "name": "topDataProperty",
            "label": "owl:topDataProperty",
            "comment": "",
            "domain": [],
            "range": "xsd:string",
            "description": "所有数据属性的根节点",
            "sub_property_of": "",
        })
        existing_data_props.add('topDataProperty')
        stats["new_data_properties"] += 1
    
    for prop in onto.properties():
        # 只处理数据属性
        if not isinstance(prop, DataPropertyClass):
            continue
            
        prop_name = get_local_name(prop)
        if not prop_name:
            continue
        
        if prop_name not in existing_data_props:
            label = prop_name
            if prop.label:
                label = prop.label.first()
            
            domains = []
            if prop.domain:
                for d in prop.domain:
                    d_name = get_local_name(d)
                    if d_name and d_name not in ['Thing', 'Nothing']:
                        domains.append(d_name)
            
            range_val = 'xsd:string'
            if prop.range:
                range_val = str(prop.range[0]) if prop.range else 'xsd:string'
                if not range_val.startswith('xsd:'):
                    range_val = f'xsd:{range_val}'
            
            # 过滤掉 owlready2 内部基类和特性类
            INTERNAL_CLASSES = {'DataProperty', 'DatatypeProperty', 'Thing', 'SymmetricProperty', 'TransitiveProperty', 
                              'FunctionalProperty', 'InverseFunctionalProperty', 'AsymmetricProperty',
                              'ReflexiveProperty', 'IrreflexiveProperty'}
            
            sub_property_of = 'topDataProperty'
            for parent in prop.is_a:
                if hasattr(parent, 'name') and parent.name and parent.name != prop_name:
                    if parent.name not in INTERNAL_CLASSES:
                        sub_property_of = parent.name
                        break
            
            logger.info(f"导入数据属性: {prop_name}, sub_property_of: {sub_property_of}, is_a: {[p.name for p in prop.is_a if hasattr(p, 'name')]}")
            
            model["data_properties"].append({
                "name": prop_name,
                "label": label,
                "comment": "",
                "domain": domains,
                "range": range_val,
                "description": "",
                "sub_property_of": sub_property_of,
                "characteristics": [],
                "disjoint_with": [],
            })
            existing_data_props.add(prop_name)
            stats["new_data_properties"] += 1
    
    for ind in onto.individuals():
        ind_name = get_local_name(ind)
        if not ind_name:
            continue
        
        if ind_name not in existing_individuals:
            label = ind_name
            if ind.label:
                label = ind.label.first()
            
            comment = ''
            if ind.comment:
                comment = ind.comment.first()
            
            types = []
            if ind.is_a:
                for t in ind.is_a:
                    if hasattr(t, 'name') and t.name and t.name not in ['Thing', 'Nothing']:
                        t_name = get_local_name(t)
                        if t_name in existing_classes:
                            types.append(t_name)
            
            data_property_values = {}
            for prop in onto.data_properties():
                values = list(ind.get_properties(prop))
                if values:
                    prop_name = get_local_name(prop)
                    data_property_values[prop_name] = [str(v) for v in values]
            
            object_property_values = {}
            for prop in onto.object_properties():
                values = list(ind.get_properties(prop))
                if values:
                    prop_name = get_local_name(prop)
                    object_property_values[prop_name] = [get_local_name(v) for v in values if hasattr(v, 'name')]
            
            model["individuals"].append({
                "name": ind_name,
                "label": label,
                "comment": comment,
                "types": types,
                "data_property_values": data_property_values,
                "object_property_values": object_property_values,
                "same_as": [],
                "different_from": [],
            })
            existing_individuals.add(ind_name)
            stats["new_individuals"] += 1
    
    if not any(c["name"] == "Thing" for c in model["classes"]):
        model["classes"].append({
            "name": "Thing",
            "label": "Thing",
            "parents": [],
            "description": "OWL根类",
        })
    
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    index = _get_ontology_index()
    for item in index:
        if item["id"] == ontology_id:
            item["classes_count"] = len(model["classes"])
            item["individuals_count"] = len(model["individuals"])
            item["properties_count"] = len(model["object_properties"]) + len(model["data_properties"])
            item["updated_at"] = model["updated_at"]
            break
    _save_ontology_index(index)
    
    return {
        "status": "success",
        "message": "导入成功",
        "stats": stats,
    }


# =============================================================================
# 本体导出
# =============================================================================

@router.get("/ontologies/{ontology_id}/export")
async def export_ontology_endpoint(
    ontology_id: str,
    format: str = 'turtle',
    username: str = Depends(verify_token)
):
    """导出本体为指定格式"""
    model = _load_ontology(ontology_id)
    
    onto = get_ontology(model["ontology_iri"])
    
    with onto:
        # 显式创建 topObjectProperty 和 topDataProperty 基类
        top_obj_prop = types.new_class('topObjectProperty', (ObjectProperty,))
        top_obj_prop.label = ['owl:topObjectProperty']
        
        top_data_prop = types.new_class('topDataProperty', (DataProperty,))
        top_data_prop.label = ['owl:topDataProperty']
        
        for cls in model["classes"]:
            cls_name = cls["name"]
            if cls_name in ['Thing', 'Nothing']:
                continue
            
            new_cls = types.new_class(cls_name, (Thing,))
            
            if cls.get("label"):
                new_cls.label = [cls["label"]]
            if cls.get("description"):
                new_cls.comment = [cls["description"]]
            
            parents = []
            for parent in cls.get("parents", []):
                if parent in ['Thing', 'Nothing']:
                    continue
                parent_cls = onto.search_one(iri=f"*#{parent}")
                if parent_cls:
                    parents.append(parent_cls)
            
            if parents:
                new_cls.is_a = parents
            
            # 处理等价类表达式导出
            for equiv in cls.get("equivalent_to", []):
                if isinstance(equiv, dict):
                    if equiv.get("type") == "class":
                        # 简单类引用
                        equiv_cls = onto.search_one(iri=f"*#{equiv['class']}")
                        if equiv_cls:
                            new_cls.equivalent_to.append(equiv_cls)
                    elif equiv.get("type") == "intersection":
                        # 交集表达式：A AND B AND Restriction
                        members = []
                        for operand in equiv.get("operands", []):
                            if operand.get("type") == "class":
                                member_cls = onto.search_one(iri=f"*#{operand['class']}")
                                if member_cls:
                                    members.append(member_cls)
                            elif operand.get("type") == "restriction":
                                prop_name = operand.get("property", "")
                                rest_type = operand.get("cardinalityType", "some")
                                rest_value = operand.get("value", "")
                                
                                if not prop_name:
                                    continue
                                
                                prop = onto.search_one(iri=f"*#{prop_name}")
                                if not prop:
                                    continue
                                
                                if rest_type == "value":
                                    members.append(prop.value(rest_value))
                                elif rest_type == "some":
                                    target_cls = onto.search_one(iri=f"*#{rest_value}")
                                    if target_cls:
                                        members.append(prop.some(target_cls))
                                elif rest_type == "only":
                                    target_cls = onto.search_one(iri=f"*#{rest_value}")
                                    if target_cls:
                                        members.append(prop.only(target_cls))
                                elif rest_type == "min":
                                    try:
                                        cardinality = int(rest_value) if rest_value else 1
                                        members.append(prop.min(cardinality))
                                    except ValueError:
                                        pass
                                elif rest_type == "max":
                                    try:
                                        cardinality = int(rest_value) if rest_value else 1
                                        members.append(prop.max(cardinality))
                                    except ValueError:
                                        pass
                                elif rest_type == "exactly":
                                    try:
                                        cardinality = int(rest_value) if rest_value else 1
                                        members.append(prop.exactly(cardinality))
                                    except ValueError:
                                        pass
                        
                        if members:
                            new_cls.equivalent_to.append(And(members))
                    elif equiv.get("type") == "union":
                        # 并集表达式 - 支持 class 和 restriction 操作数
                        members = []
                        for operand in equiv.get("operands", []):
                            if operand.get("type") == "class":
                                member_cls = onto.search_one(iri=f"*#{operand['class']}")
                                if member_cls:
                                    members.append(member_cls)
                            elif operand.get("type") == "restriction":
                                rest_expr = _build_mgmt_restriction(operand, onto)
                                if rest_expr:
                                    members.append(rest_expr)
                        if members:
                            new_cls.equivalent_to.append(Or(members))
                    elif equiv.get("type") == "complement":
                        # 补集表达式
                        operand = equiv.get("operand")
                        if operand:
                            if operand.get("type") == "class":
                                inner_cls = onto.search_one(iri=f"*#{operand['class']}")
                                if inner_cls:
                                    new_cls.equivalent_to.append(Not(inner_cls))
                            elif operand.get("type") == "restriction":
                                rest_expr = _build_mgmt_restriction(operand, onto)
                                if rest_expr:
                                    new_cls.equivalent_to.append(Not(rest_expr))
                elif isinstance(equiv, str):
                    # 兼容旧格式：简单字符串
                    equiv_cls = onto.search_one(iri=f"*#{equiv}")
                    if equiv_cls:
                        new_cls.equivalent_to.append(equiv_cls)
            
            for disjoint in cls.get("disjoint_with", []):
                disjoint_cls = onto.search_one(iri=f"*#{disjoint}")
                if disjoint_cls:
                    AllDisjoint([new_cls, disjoint_cls])
        
        for prop in model["object_properties"]:
            prop_name = prop["name"]
            if prop_name in ['topObjectProperty']:
                continue
            new_prop = types.new_class(prop_name, (ObjectProperty,))
            
            if prop.get("label"):
                new_prop.label = [prop["label"]]
            if prop.get("description"):
                new_prop.comment = [prop["description"]]
            
            # 设置父属性关系 - 显式设置 subPropertyOf
            sub_prop_of = prop.get("sub_property_of", "")
            if sub_prop_of and sub_prop_of not in ['topObjectProperty', '']:
                # 有自定义父属性
                parent_prop = onto.search_one(iri=f"*#{sub_prop_of}")
                if parent_prop:
                    new_prop.is_a.append(parent_prop)
            else:
                # 默认父属性是 topObjectProperty，显式声明以便 Protégé 正确显示层次
                new_prop.is_a.append(top_obj_prop)
            
            if prop.get("domain"):
                domain_cls = onto.search_one(iri=f"*#{prop['domain']}")
                if domain_cls:
                    new_prop.domain = [domain_cls]
            
            if prop.get("range"):
                range_cls = onto.search_one(iri=f"*#{prop['range']}")
                if range_cls:
                    new_prop.range = [range_cls]
            
            if prop.get("inverse_of"):
                inverse_prop = onto.search_one(iri=f"*#{prop['inverse_of']}")
                if inverse_prop:
                    new_prop.inverse_property = inverse_prop
            
            for char in prop.get("characteristics", []):
                char_map = {
                    'Functional': FunctionalProperty,
                    'TransitiveProperty': TransitiveProperty,
                    'SymmetricProperty': SymmetricProperty,
                    'AsymmetricProperty': AsymmetricProperty,
                    'ReflexiveProperty': ReflexiveProperty,
                    'IrreflexiveProperty': IrreflexiveProperty,
                    'InverseFunctional': InverseFunctionalProperty,
                }
                if char in char_map:
                    new_prop.is_a.append(char_map[char])
        
        for prop in model["data_properties"]:
            prop_name = prop["name"]
            if prop_name in ['topDataProperty']:
                continue
            new_prop = types.new_class(prop_name, (DataProperty,))
            
            if prop.get("label"):
                new_prop.label = [prop["label"]]
            if prop.get("description"):
                new_prop.comment = [prop["description"]]
            
            # 设置父属性关系 - 显式设置 subPropertyOf
            sub_prop_of = prop.get("sub_property_of", "")
            if sub_prop_of and sub_prop_of not in ['topDataProperty', '']:
                # 有自定义父属性
                parent_prop = onto.search_one(iri=f"*#{sub_prop_of}")
                if parent_prop:
                    new_prop.is_a.append(parent_prop)
            else:
                # 默认父属性是 topDataProperty，显式声明以便 Protégé 正确显示层次
                new_prop.is_a.append(top_data_prop)
            
            if prop.get("domain"):
                domain_cls = onto.search_one(iri=f"*#{prop['domain']}")
                if domain_cls:
                    new_prop.domain = [domain_cls]
        
        for ind in model["individuals"]:
            ind_name = ind["name"]
            new_ind = Thing[ind_name]
            
            if ind.get("label"):
                new_ind.label = [ind["label"]]
            
            if ind.get("class"):
                cls = onto.search_one(iri=f"*#{ind['class']}")
                if cls:
                    new_ind.is_a.append(cls)
    
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.owl', delete=False) as tmp:
        tmp_path = tmp.name
    
    format_map = {
        'turtle': '.ttl',
        'ttl': '.ttl',
        'xml': '.owl',
        'rdf': '.owl',
        'owl': '.owl',
        'n3': '.n3',
        'nt': '.nt',
        'json-ld': '.jsonld',
    }
    
    onto.save(file=tmp_path, format="rdfxml")
    
    with open(tmp_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    import os
    os.unlink(tmp_path)
    
    return {
        "content": content,
        "format": format,
        "filename": f"{model['name']}{format_map.get(format, '.owl')}",
        "triple_count": len(model["classes"]) + len(model["object_properties"]) + len(model["data_properties"]) + len(model["individuals"]),
    }


# =============================================================================
# 本体统计
# =============================================================================

@router.get("/ontologies/{ontology_id}/stats")
async def get_ontology_stats(ontology_id: str, username: str = Depends(verify_token)):
    """获取本体统计信息"""
    model = _load_ontology(ontology_id)
    return {
        "name": model["name"],
        "classes_count": len(model["classes"]),
        "object_properties_count": len(model["object_properties"]),
        "data_properties_count": len(model["data_properties"]),
        "annotation_properties_count": len(model["annotation_properties"]),
        "individuals_count": len(model["individuals"]),
        "updated_at": model.get("updated_at", ""),
    }


# =============================================================================
# 本体元数据
# =============================================================================

@router.get("/ontologies/{ontology_id}/metadata")
async def get_ontology_metadata(ontology_id: str, username: str = Depends(verify_token)):
    """获取本体元数据"""
    model = _load_ontology(ontology_id)
    return {
        "ontology_iri": model["ontology_iri"],
        "version_iri": model["version_iri"],
        "annotations": model["annotations"],
    }


@router.put("/ontologies/{ontology_id}/metadata")
async def update_ontology_metadata(
    ontology_id: str,
    metadata: dict,
    username: str = Depends(require_admin)
):
    """更新本体元数据"""
    model = _load_ontology(ontology_id)
    if "ontology_iri" in metadata:
        model["ontology_iri"] = metadata["ontology_iri"]
    if "version_iri" in metadata:
        model["version_iri"] = metadata["version_iri"]
    if "annotations" in metadata:
        model["annotations"] = metadata["annotations"]
    
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": "本体元数据已更新"}


# =============================================================================
# 类管理
# =============================================================================

@router.get("/ontologies/{ontology_id}/classes")
async def list_classes(ontology_id: str, username: str = Depends(verify_token)):
    """列出所有类"""
    model = _load_ontology(ontology_id)
    
    # 过滤掉非类元素（对象属性名、数据属性名、本体IRI等）
    object_prop_names = {p["name"] for p in model.get("object_properties", [])}
    data_prop_names = {p["name"] for p in model.get("data_properties", [])}
    ontology_iri_local = None
    if model.get("ontology_iri"):
        iri = model["ontology_iri"]
        if '#' in iri:
            ontology_iri_local = iri.split('#')[-1]
        elif '/' in iri:
            ontology_iri_local = iri.split('/')[-1]
    
    filtered_classes = []
    for c in model["classes"]:
        name = c["name"]
        # 跳过对象属性名
        if name in object_prop_names:
            continue
        # 跳过数据属性名
        if name in data_prop_names:
            continue
        # 跳过本体IRI的本地名
        if ontology_iri_local and name == ontology_iri_local:
            continue
        filtered_classes.append(c)
    
    return {"classes": filtered_classes}


@router.post("/ontologies/{ontology_id}/classes")
async def create_class(
    ontology_id: str,
    class_data: dict,
    username: str = Depends(require_admin)
):
    """创建新类"""
    if not class_data.get("name"):
        raise HTTPException(status_code=400, detail="类名称不能为空")
    
    model = _load_ontology(ontology_id)
    existing = next((c for c in model["classes"] if c["name"] == class_data["name"]), None)
    if existing:
        raise HTTPException(status_code=400, detail=f"类 {class_data['name']} 已存在")
    
    new_class = {
        "name": class_data["name"],
        "label": class_data.get("label", class_data["name"]),
        "parents": class_data.get("parents", []),
        "description": class_data.get("description", ""),
    }
    model["classes"].append(new_class)
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"类 {new_class['name']} 已创建", "class": new_class}


@router.put("/ontologies/{ontology_id}/classes/{class_name}")
async def update_class(
    ontology_id: str,
    class_name: str,
    class_data: dict,
    username: str = Depends(require_admin)
):
    """更新类"""
    model = _load_ontology(ontology_id)
    cls = next((c for c in model["classes"] if c["name"] == class_name), None)
    if not cls:
        raise HTTPException(status_code=404, detail=f"类 {class_name} 不存在")
    
    if "label" in class_data:
        cls["label"] = class_data["label"]
    if "parents" in class_data:
        cls["parents"] = class_data["parents"]
    if "description" in class_data:
        cls["description"] = class_data["description"]
    if "comment" in class_data:
        cls["comment"] = class_data["comment"]
    if "disjoint_with" in class_data:
        cls["disjoint_with"] = class_data["disjoint_with"]
    if "equivalent_to" in class_data:
        cls["equivalent_to"] = class_data["equivalent_to"]
    if "restrictions" in class_data:
        cls["restrictions"] = class_data["restrictions"]
    
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"类 {class_name} 已更新"}


@router.delete("/ontologies/{ontology_id}/classes/{class_name}")
async def delete_class(
    ontology_id: str,
    class_name: str,
    username: str = Depends(require_admin)
):
    """删除类"""
    model = _load_ontology(ontology_id)
    model["classes"] = [c for c in model["classes"] if c["name"] != class_name]
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"类 {class_name} 已删除"}


# =============================================================================
# 对象属性管理
# =============================================================================

@router.get("/ontologies/{ontology_id}/object-properties")
async def list_object_properties(ontology_id: str, username: str = Depends(verify_token)):
    """列出所有对象属性"""
    model = _load_ontology(ontology_id)
    return {"object_properties": model["object_properties"]}


@router.post("/ontologies/{ontology_id}/object-properties")
async def create_object_property(
    ontology_id: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """创建新对象属性"""
    if not prop_data.get("name"):
        raise HTTPException(status_code=400, detail="属性名称不能为空")
    
    model = _load_ontology(ontology_id)
    existing = next((p for p in model["object_properties"] if p["name"] == prop_data["name"]), None)
    if existing:
        raise HTTPException(status_code=400, detail=f"对象属性 {prop_data['name']} 已存在")
    
    new_prop = {
        "name": prop_data["name"],
        "label": prop_data.get("label", prop_data["name"]),
        "comment": prop_data.get("comment", ""),
        "domain": prop_data.get("domain", []),
        "range": prop_data.get("range", []),
        "description": prop_data.get("description", ""),
        "sub_property_of": prop_data.get("sub_property_of", ""),
        "characteristics": prop_data.get("characteristics", []),
        "inverse_of": prop_data.get("inverse_of", ""),
    }
    model["object_properties"].append(new_prop)
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"对象属性 {new_prop['name']} 已创建", "property": new_prop}


@router.put("/ontologies/{ontology_id}/object-properties/{prop_name}")
async def update_object_property(
    ontology_id: str,
    prop_name: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """更新对象属性"""
    model = _load_ontology(ontology_id)
    prop = next((p for p in model["object_properties"] if p["name"] == prop_name), None)
    if not prop:
        raise HTTPException(status_code=404, detail=f"对象属性 {prop_name} 不存在")
    
    if "label" in prop_data:
        prop["label"] = prop_data["label"]
    if "comment" in prop_data:
        prop["comment"] = prop_data["comment"]
    if "domain" in prop_data:
        prop["domain"] = prop_data["domain"]
    if "range" in prop_data:
        prop["range"] = prop_data["range"]
    if "description" in prop_data:
        prop["description"] = prop_data["description"]
    if "sub_property_of" in prop_data:
        prop["sub_property_of"] = prop_data["sub_property_of"]
    if "characteristics" in prop_data:
        prop["characteristics"] = prop_data["characteristics"]
    if "inverse_of" in prop_data:
        prop["inverse_of"] = prop_data["inverse_of"]
    
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"对象属性 {prop_name} 已更新"}


@router.delete("/ontologies/{ontology_id}/object-properties/{prop_name}")
async def delete_object_property(
    ontology_id: str,
    prop_name: str,
    username: str = Depends(require_admin)
):
    """删除对象属性"""
    model = _load_ontology(ontology_id)
    model["object_properties"] = [p for p in model["object_properties"] if p["name"] != prop_name]
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"对象属性 {prop_name} 已删除"}


# =============================================================================
# 数据属性管理
# =============================================================================

@router.get("/ontologies/{ontology_id}/data-properties")
async def list_data_properties(ontology_id: str, username: str = Depends(verify_token)):
    """列出所有数据属性"""
    model = _load_ontology(ontology_id)
    return {"data_properties": model["data_properties"]}


@router.post("/ontologies/{ontology_id}/data-properties")
async def create_data_property(
    ontology_id: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """创建新数据属性"""
    if not prop_data.get("name"):
        raise HTTPException(status_code=400, detail="属性名称不能为空")
    
    model = _load_ontology(ontology_id)
    existing = next((p for p in model["data_properties"] if p["name"] == prop_data["name"]), None)
    if existing:
        raise HTTPException(status_code=400, detail=f"数据属性 {prop_data['name']} 已存在")
    
    new_prop = {
        "name": prop_data["name"],
        "label": prop_data.get("label", prop_data["name"]),
        "comment": prop_data.get("comment", ""),
        "domain": prop_data.get("domain", []),
        "range": prop_data.get("range", "xsd:string"),
        "description": prop_data.get("description", ""),
        "sub_property_of": prop_data.get("sub_property_of", ""),
        "characteristics": prop_data.get("characteristics", []),
        "disjoint_with": prop_data.get("disjoint_with", []),
    }
    model["data_properties"].append(new_prop)
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"数据属性 {new_prop['name']} 已创建", "property": new_prop}


@router.put("/ontologies/{ontology_id}/data-properties/{prop_name}")
async def update_data_property(
    ontology_id: str,
    prop_name: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """更新数据属性"""
    model = _load_ontology(ontology_id)
    prop = next((p for p in model["data_properties"] if p["name"] == prop_name), None)
    if not prop:
        raise HTTPException(status_code=404, detail=f"数据属性 {prop_name} 不存在")
    
    if "label" in prop_data:
        prop["label"] = prop_data["label"]
    if "comment" in prop_data:
        prop["comment"] = prop_data["comment"]
    if "domain" in prop_data:
        prop["domain"] = prop_data["domain"]
    if "range" in prop_data:
        prop["range"] = prop_data["range"]
    if "description" in prop_data:
        prop["description"] = prop_data["description"]
    if "sub_property_of" in prop_data:
        prop["sub_property_of"] = prop_data["sub_property_of"]
    if "characteristics" in prop_data:
        prop["characteristics"] = prop_data["characteristics"]
    if "disjoint_with" in prop_data:
        prop["disjoint_with"] = prop_data["disjoint_with"]
    
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"数据属性 {prop_name} 已更新"}


@router.delete("/ontologies/{ontology_id}/data-properties/{prop_name}")
async def delete_data_property(
    ontology_id: str,
    prop_name: str,
    username: str = Depends(require_admin)
):
    """删除数据属性"""
    model = _load_ontology(ontology_id)
    model["data_properties"] = [p for p in model["data_properties"] if p["name"] != prop_name]
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"数据属性 {prop_name} 已删除"}


# =============================================================================
# 注释属性管理
# =============================================================================

@router.get("/ontologies/{ontology_id}/annotation-properties")
async def list_annotation_properties(ontology_id: str, username: str = Depends(verify_token)):
    """列出所有注释属性"""
    model = _load_ontology(ontology_id)
    return {"annotation_properties": model["annotation_properties"]}


@router.post("/ontologies/{ontology_id}/annotation-properties")
async def create_annotation_property(
    ontology_id: str,
    prop_data: dict,
    username: str = Depends(require_admin)
):
    """创建新注释属性"""
    if not prop_data.get("name"):
        raise HTTPException(status_code=400, detail="属性名称不能为空")
    
    model = _load_ontology(ontology_id)
    existing = next((p for p in model["annotation_properties"] if p["name"] == prop_data["name"]), None)
    if existing:
        raise HTTPException(status_code=400, detail=f"注释属性 {prop_data['name']} 已存在")
    
    new_prop = {
        "name": prop_data["name"],
        "type": prop_data.get("type", "rdfs:label"),
    }
    model["annotation_properties"].append(new_prop)
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"注释属性 {new_prop['name']} 已创建", "property": new_prop}


@router.delete("/ontologies/{ontology_id}/annotation-properties/{prop_name}")
async def delete_annotation_property(
    ontology_id: str,
    prop_name: str,
    username: str = Depends(require_admin)
):
    """删除注释属性"""
    model = _load_ontology(ontology_id)
    model["annotation_properties"] = [p for p in model["annotation_properties"] if p["name"] != prop_name]
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"注释属性 {prop_name} 已删除"}


# =============================================================================
# 个体管理
# =============================================================================

@router.get("/ontologies/{ontology_id}/individuals")
async def list_individuals(ontology_id: str, username: str = Depends(verify_token)):
    """列出所有个体"""
    model = _load_ontology(ontology_id)
    return {"individuals": model["individuals"]}


@router.post("/ontologies/{ontology_id}/individuals")
async def create_individual(
    ontology_id: str,
    ind_data: dict,
    username: str = Depends(require_admin)
):
    """创建新个体"""
    if not ind_data.get("name"):
        raise HTTPException(status_code=400, detail="个体名称不能为空")
    
    model = _load_ontology(ontology_id)
    existing = next((i for i in model["individuals"] if i["name"] == ind_data["name"]), None)
    if existing:
        raise HTTPException(status_code=400, detail=f"个体 {ind_data['name']} 已存在")
    
    new_ind = {
        "name": ind_data["name"],
        "label": ind_data.get("label", ind_data["name"]),
        "comment": ind_data.get("comment", ""),
        "types": ind_data.get("types", []),
        "data_property_values": ind_data.get("data_property_values", {}),
        "object_property_values": ind_data.get("object_property_values", {}),
        "same_as": ind_data.get("same_as", []),
        "different_from": ind_data.get("different_from", []),
    }
    model["individuals"].append(new_ind)
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"个体 {new_ind['name']} 已创建", "individual": new_ind}


@router.put("/ontologies/{ontology_id}/individuals/{ind_name}")
async def update_individual(
    ontology_id: str,
    ind_name: str,
    ind_data: dict,
    username: str = Depends(require_admin)
):
    """更新个体"""
    model = _load_ontology(ontology_id)
    ind = next((i for i in model["individuals"] if i["name"] == ind_name), None)
    if not ind:
        raise HTTPException(status_code=404, detail=f"个体 {ind_name} 不存在")
    
    if "label" in ind_data:
        ind["label"] = ind_data["label"]
    if "comment" in ind_data:
        ind["comment"] = ind_data["comment"]
    if "types" in ind_data:
        ind["types"] = ind_data["types"]
    if "data_property_values" in ind_data:
        ind["data_property_values"] = ind_data["data_property_values"]
    if "object_property_values" in ind_data:
        ind["object_property_values"] = ind_data["object_property_values"]
    if "same_as" in ind_data:
        ind["same_as"] = ind_data["same_as"]
    if "different_from" in ind_data:
        ind["different_from"] = ind_data["different_from"]
    
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"个体 {ind_name} 已更新"}


@router.delete("/ontologies/{ontology_id}/individuals/{ind_name}")
async def delete_individual(
    ontology_id: str,
    ind_name: str,
    username: str = Depends(require_admin)
):
    """删除个体"""
    model = _load_ontology(ontology_id)
    model["individuals"] = [i for i in model["individuals"] if i["name"] != ind_name]
    model["updated_at"] = datetime.now().isoformat()
    _save_ontology(ontology_id, model)
    
    return {"status": "success", "message": f"个体 {ind_name} 已删除"}


# =============================================================================
# 类层次结构
# =============================================================================

@router.get("/ontologies/{ontology_id}/class-hierarchy")
async def get_class_hierarchy(ontology_id: str, username: str = Depends(verify_token)):
    """获取类层次结构"""
    model = _load_ontology(ontology_id)
    
    # 过滤掉非类元素（对象属性名、数据属性名、本体IRI等）
    object_prop_names = {p["name"] for p in model.get("object_properties", [])}
    data_prop_names = {p["name"] for p in model.get("data_properties", [])}
    ontology_iri_local = None
    if model.get("ontology_iri"):
        iri = model["ontology_iri"]
        if '#' in iri:
            ontology_iri_local = iri.split('#')[-1]
        elif '/' in iri:
            ontology_iri_local = iri.split('/')[-1]
    
    classes = []
    for c in model["classes"]:
        name = c["name"]
        if name in object_prop_names:
            continue
        if name in data_prop_names:
            continue
        if ontology_iri_local and name == ontology_iri_local:
            continue
        classes.append(c)
    
    class_map = {c["name"]: c for c in classes}
    
    roots = []
    for cls in classes:
        if not cls.get("parents") or len(cls["parents"]) == 0:
            roots.append(cls["name"])
    
    def build_tree(class_name, visited=None):
        if visited is None:
            visited = set()
        if class_name in visited:
            return {"name": class_name, "label": class_map.get(class_name, {}).get("label", class_name), "children": [], "is_circular": True}
        visited.add(class_name)
        
        cls = class_map.get(class_name)
        if not cls:
            return None
        
        children = []
        for other in classes:
            if class_name in other.get("parents", []):
                child = build_tree(other["name"], visited.copy())
                if child:
                    children.append(child)
        
        return {
            "name": class_name,
            "label": cls.get("label", class_name),
            "children": children,
        }
    
    hierarchy = []
    for root in roots:
        tree = build_tree(root)
        if tree:
            hierarchy.append(tree)
    
    return {
        "hierarchy": hierarchy,
        "total_classes": len(classes),
        "root_classes": len(roots),
        "warnings": ["发现循环引用" if any(c.get("is_circular") for c in classes) else None],
    }


# =============================================================================
# 推理缓存
# =============================================================================

class _MgmtReasonerCache:
    """推理结果内存缓存"""
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
    
    def get(self, ontology_id: str):
        return self._cache.get(ontology_id)
    
    def put(self, ontology_id: str, result: dict):
        self._cache[ontology_id] = result
        self._timestamps[ontology_id] = datetime.now().isoformat()
    
    def invalidate(self, ontology_id: str):
        self._cache.pop(ontology_id, None)
        self._timestamps.pop(ontology_id, None)

_mgmt_reasoner_cache = _MgmtReasonerCache()


def _mgmt_run_json_reasoning(model: dict) -> dict:
    """JSON 数据层面的基础推理"""
    issues = []
    inferred_relations = []
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
                issues.append({
                    "type": "error",
                    "category": "disjoint_violation",
                    "message": f"类 '{cls['name']}' 与其不相交的类 '{disjoint_cls}' 存在继承关系",
                    "entity": cls["name"],
                    "explanation": f"'{cls['name']}' 声明与 '{disjoint_cls}' 不相交，但通过类层次结构存在继承关系",
                })
        
        for equiv in cls.get("equivalent_to", []):
            equiv_name = equiv if isinstance(equiv, str) else (equiv.get("class") if isinstance(equiv, dict) and equiv.get("type") == "class" else None)
            if equiv_name and equiv_name in class_map:
                other = class_map[equiv_name]
                if cls["name"] in other.get("disjoint_with", []):
                    issues.append({
                        "type": "error",
                        "category": "equivalent_disjoint",
                        "message": f"类 '{cls['name']}' 与 '{equiv_name}' 既等价又不相交",
                        "entity": cls["name"],
                        "explanation": f"逻辑矛盾：等价且不相交",
                    })
    
    # 个体不相交检查
    for ind in individuals:
        ind_types = set(ind.get("types", []) if isinstance(ind.get("types"), list) else ([ind.get("class")] if ind.get("class") else []))
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
                            "explanation": f"'{type1}' 和 '{type2}' 被声明为不相交类",
                        })
    
    # 推导子类关系
    for cls in classes:
        all_parents = get_all_parents(cls["name"])
        direct = set(cls.get("parents", []))
        for p in all_parents - direct:
            if p and p != cls["name"]:
                inferred_relations.append({
                    "type": "subClassOf", "subject": cls["name"], "object": p,
                    "inferred": True, "reason": "通过类层次传递性推导",
                })
    
    # 推导个体类型
    for ind in individuals:
        current_types = set(ind.get("types", []) if isinstance(ind.get("types"), list) else ([ind.get("class")] if ind.get("class") else []))
        all_parents = set()
        for t in current_types:
            all_parents.update(get_all_parents(t))
        for implied in all_parents - current_types:
            if implied:
                inferred_relations.append({
                    "type": "instanceOf", "subject": ind["name"], "object": implied,
                    "inferred": True, "reason": "通过类层次推导",
                })
    
    for issue in issues:
        entity = issue.get("entity", "")
        if entity:
            explanations.setdefault(entity, []).append(issue.get("explanation", issue["message"]))
    
    return {"issues": issues, "inferred_relations": inferred_relations, "warnings": [], "explanations": explanations}


def _mgmt_run_hermit_reasoning(model: dict) -> dict:
    """使用 owlready2 + HermiT 推理"""
    from owlready2 import sync_reasoner_hermit
    
    iri = model.get("ontology_iri", "http://reasoning.mgmt/onto")
    onto = get_ontology(iri)
    
    with onto:
        for cls_data in model.get("classes", []):
            if cls_data["name"] in ('Thing', 'Nothing'):
                continue
            types.new_class(cls_data["name"], (Thing,))
        
        for cls_data in model.get("classes", []):
            if cls_data["name"] in ('Thing', 'Nothing'):
                continue
            new_cls = onto.search_one(iri=f"*#{cls_data['name']}")
            if not new_cls:
                continue
            parents = [onto.search_one(iri=f"*#{p}") for p in cls_data.get("parents", []) if p not in ('Thing', 'Nothing')]
            parents = [p for p in parents if p]
            if parents:
                new_cls.is_a = parents
            for equiv in cls_data.get("equivalent_to", []):
                if isinstance(equiv, dict):
                    if equiv.get("type") == "intersection":
                        operands = [onto.search_one(iri=f"*#{op['class']}") for op in equiv.get("operands", []) if op.get("type") == "class"]
                        operands = [o for o in operands if o]
                        if operands:
                            new_cls.equivalent_to.append(And(operands))
                    elif equiv.get("type") == "union":
                        operands = [onto.search_one(iri=f"*#{op['class']}") for op in equiv.get("operands", []) if op.get("type") == "class"]
                        operands = [o for o in operands if o]
                        if operands:
                            new_cls.equivalent_to.append(Or(operands))
                    elif equiv.get("type") == "complement" and equiv.get("operand", {}).get("type") == "class":
                        c = onto.search_one(iri=f"*#{equiv['operand']['class']}")
                        if c:
                            new_cls.equivalent_to.append(Not(c))
            for disjoint in cls_data.get("disjoint_with", []):
                dc = onto.search_one(iri=f"*#{disjoint}")
                if dc:
                    AllDisjoint([new_cls, dc])
        
        for prop_data in model.get("object_properties", []):
            if prop_data["name"] not in ('topObjectProperty',):
                types.new_class(prop_data["name"], (ObjectProperty,))
        for prop_data in model.get("data_properties", []):
            if prop_data["name"] not in ('topDataProperty',):
                types.new_class(prop_data["name"], (DataProperty,))
    
    pre_parents = {}
    for cls in onto.classes():
        if cls.name and cls.name not in ('Thing', 'Nothing'):
            pre_parents[cls.name] = {p.name for p in cls.is_a if hasattr(p, 'name') and p.name}
    
    with onto:
        sync_reasoner_hermit(infer_property_values=True)
    
    issues = []
    inferred_relations = []
    explanations = {}
    
    for cls in onto.inconsistent_classes():
        cn = cls.name if hasattr(cls, 'name') else str(cls)
        issues.append({
            "type": "error", "category": "inconsistent_class",
            "message": f"类 '{cn}' 被推理机判定为不一致",
            "entity": cn, "explanation": f"HermiT: '{cn}' 公理存在逻辑矛盾",
        })
        explanations.setdefault(cn, []).append(f"HermiT: '{cn}' 公理矛盾")
    
    for cls in onto.classes():
        if not cls.name or cls.name in ('Thing', 'Nothing'):
            continue
        post = {p.name for p in cls.is_a if hasattr(p, 'name') and p.name}
        for np in post - pre_parents.get(cls.name, set()) - {'Thing'}:
            if np and np != cls.name:
                inferred_relations.append({
                    "type": "subClassOf", "subject": cls.name, "object": np,
                    "inferred": True, "reason": "HermiT 推理机基于公理推导",
                })
    
    return {"issues": issues, "inferred_relations": inferred_relations, "warnings": [], "explanations": explanations}


@router.post("/ontologies/{ontology_id}/reason")
async def reason_ontology(ontology_id: str, username: str = Depends(require_admin)):
    """对本体进行推理（增强版 - HermiT + 解释 + 日志 + 缓存）"""
    import time
    import io
    
    cached = _mgmt_reasoner_cache.get(ontology_id)
    if cached is not None:
        cached["from_cache"] = True
        return cached
    
    model = _load_ontology(ontology_id)
    start_time = time.time()
    
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(log_handler)
    
    reasoner_type = "hermit"
    try:
        logger.info("开始推理 - 尝试使用 HermiT")
        result = _mgmt_run_hermit_reasoning(model)
        logger.info("HermiT 推理完成")
        json_result = _mgmt_run_json_reasoning(model)
        existing_msgs = {i["message"] for i in result["issues"]}
        for issue in json_result["issues"]:
            if issue["message"] not in existing_msgs:
                result["issues"].append(issue)
        existing_rels = {(r["type"], r["subject"], r["object"]) for r in result["inferred_relations"]}
        for rel in json_result["inferred_relations"]:
            if (rel["type"], rel["subject"], rel["object"]) not in existing_rels:
                result["inferred_relations"].append(rel)
        for entity, expl_list in json_result["explanations"].items():
            result["explanations"].setdefault(entity, []).extend(expl_list)
    except Exception as e:
        logger.warning(f"HermiT 失败，降级为 JSON 推理: {e}")
        reasoner_type = "json_fallback"
        result = _mgmt_run_json_reasoning(model)
    finally:
        logger.removeHandler(log_handler)
    
    duration_ms = int((time.time() - start_time) * 1000)
    is_consistent = len([i for i in result["issues"] if i["type"] == "error"]) == 0
    
    response = {
        "is_consistent": is_consistent,
        "issues": result["issues"],
        "inferred_relations": result["inferred_relations"],
        "explanations": result["explanations"],
        "warnings": result["warnings"],
        "log": log_stream.getvalue(),
        "duration_ms": duration_ms,
        "reasoner_type": reasoner_type,
        "from_cache": False,
        "stats": {
            "total_issues": len(result["issues"]),
            "errors": len([i for i in result["issues"] if i["type"] == "error"]),
            "warnings": len(result["warnings"]),
            "inferred_relations": len(result["inferred_relations"]),
            "inferred_subclasses": len([r for r in result["inferred_relations"] if r["type"] == "subClassOf"]),
            "inferred_types": len([r for r in result["inferred_relations"] if r["type"] == "instanceOf"]),
        }
    }
    _mgmt_reasoner_cache.put(ontology_id, response)
    return response


@router.delete("/ontologies/{ontology_id}/reason/cache")
async def clear_mgmt_reason_cache(ontology_id: str, username: str = Depends(require_admin)):
    """手动清除推理缓存"""
    _mgmt_reasoner_cache.invalidate(ontology_id)
    return {"status": "success", "message": "推理缓存已清除"}


# =============================================================================
# 本体版本管理
# =============================================================================

VERSIONS_DIR = ONTOLOGY_DIR / "versions"
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/ontologies/{ontology_id}/version")
async def create_version(
    ontology_id: str,
    version_data: dict,
    username: str = Depends(require_admin)
):
    """创建本体版本快照"""
    if not version_data.get("version"):
        raise HTTPException(status_code=400, detail="版本号不能为空")
    
    model = _load_ontology(ontology_id)
    
    version_file = VERSIONS_DIR / f"{ontology_id}_v{version_data['version']}.json"
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


@router.get("/ontologies/{ontology_id}/versions")
async def list_versions(ontology_id: str, username: str = Depends(verify_token)):
    """列出所有版本"""
    versions = []
    for f in VERSIONS_DIR.glob(f"{ontology_id}_v*.json"):
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


@router.get("/ontologies/{ontology_id}/version/{version}")
async def get_version(ontology_id: str, version: str, username: str = Depends(verify_token)):
    """获取指定版本的详细信息"""
    version_file = VERSIONS_DIR / f"{ontology_id}_v{version}.json"
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


@router.post("/ontologies/{ontology_id}/version/{version}/restore")
async def restore_version(ontology_id: str, version: str, username: str = Depends(require_admin)):
    """恢复到指定版本"""
    version_file = VERSIONS_DIR / f"{ontology_id}_v{version}.json"
    if not version_file.exists():
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")
    
    with open(version_file, 'r', encoding='utf-8') as f:
        snapshot = json.load(f)
    
    _save_ontology(ontology_id, snapshot["model"])
    
    return {
        "status": "success",
        "message": f"已恢复到版本 {version}",
        "version": version,
    }


@router.delete("/ontologies/{ontology_id}/version/{version}")
async def delete_version(ontology_id: str, version: str, username: str = Depends(require_admin)):
    """删除指定版本"""
    version_file = VERSIONS_DIR / f"{ontology_id}_v{version}.json"
    if not version_file.exists():
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")
    
    version_file.unlink()
    
    return {
        "status": "success",
        "message": f"版本 {version} 已删除",
    }
