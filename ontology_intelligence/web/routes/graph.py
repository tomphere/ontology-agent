# 图谱浏览路由（增强版）
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from ontology_intelligence.config import settings
from ontology_intelligence.security import assert_cypher_identifier
from ontology_intelligence.web.routes.auth import verify_token
from ontology_intelligence.web import scene_store

router = APIRouter(tags=["graph"])

META_LABELS = {"SceneEntity", "Thing", "Node", "Resource"}
TECHNICAL_RESULT_KEYS = {"scene_id", "scene_uid", "source_pk", "source_table"}
ONTOLOGY_LABELS = {
    "Class": "本体类",
    "ObjectProperty": "对象属性",
    "DataProperty": "数据属性",
}


def _primary_label(labels: list, props: dict = None) -> str:
    props = props or {}
    if props.get("ontology_class"):
        return str(props["ontology_class"])
    business_labels = [label for label in labels if label not in META_LABELS]
    if business_labels:
        return business_labels[0]
    return labels[0] if labels else "Node"


def _display_property_candidates(scene_id: str = None) -> list:
    """Find likely display-name properties from the linked ontology and mapping."""
    candidates = []
    models = []
    if scene_id:
        m = scene_store.get_linked_ontology_model(scene_id)
        if m: models.append(m)
    else:
        try:
            from ontology_intelligence.web.routes.ontology_management import _get_ontology_index, _load_ontology
            index = _get_ontology_index()
            for item in index:
                try:
                    models.append(_load_ontology(item['id']))
                except: continue
        except: pass

    for model in models:
        ontology = scene_store.normalize_ontology_model(model)
        for prop in ontology.get("data_properties", []):
            name = prop.get("name")
            if not name:
                continue
            search_text = " ".join([
                str(prop.get("name") or ""),
                str(prop.get("label") or ""),
                str(prop.get("comment") or prop.get("description") or ""),
            ]).lower()
            if any(token in search_text for token in ("name", "title", "label", "display", "名称", "姓名", "标题", "显示名")):
                candidates.append(name)

    if scene_id:
        try:
            import yaml
            mapping_path = scene_store.get_scene_mapping_path(scene_id)
            with open(mapping_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            for mapping in config.get("mappings") or []:
                for item in mapping.get("data_properties") or []:
                    column = str(item.get("column") or "").lower()
                    prop = item.get("ontology_property")
                    if prop and any(token in column for token in ("name", "title", "label", "display")):
                        candidates.append(prop)
        except Exception:
            pass

    candidates.extend(["name", "label", "title", "id", "uri"])
    seen = set()
    ordered = []
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _display_maps(scene_id: str = None) -> dict:
    models = []
    if scene_id:
        m = scene_store.get_linked_ontology_model(scene_id)
        if m: models.append(m)
    else:
        # Aggregate all ontologies for global view fallback
        try:
            from ontology_intelligence.web.routes.ontology_management import _get_ontology_index, _load_ontology
            index = _get_ontology_index()
            for item in index:
                try:
                    models.append(_load_ontology(item['id']))
                except: continue
        except: pass

    maps = {
        "classes": dict(ONTOLOGY_LABELS),
        "properties": {"id": "ID", "ontology_class": "实体类型"},
        "relationships": {},
    }

    for model in models:
        ontology = scene_store.normalize_ontology_model(model)
        for cls in ontology.get("classes", []):
            if cls.get("name"):
                maps["classes"][cls["name"]] = cls.get("label") or cls["name"]
        for prop in ontology.get("data_properties", []):
            if prop.get("name"):
                maps["properties"][prop["name"]] = prop.get("label") or prop["name"]
        for prop in ontology.get("object_properties", []):
            if prop.get("name"):
                maps["relationships"][prop["name"]] = prop.get("label") or prop["name"]
    return maps


def _display_value(key: str, value, maps: dict):
    if key == "ontology_class" and isinstance(value, str):
        return maps.get("classes", {}).get(value, value)
    return value


def _display_properties(props: dict, maps: dict) -> dict:
    result = {}
    for key, value in props.items():
        if key in TECHNICAL_RESULT_KEYS or key.endswith("_embedding"):
            continue
        label = maps.get("properties", {}).get(key, key)
        result[label] = str(_display_value(key, value, maps))[:200]
    return result


def _node_payload(node, display_keys: list = None, maps: dict = None) -> dict:
    props = dict(node)
    labels = list(node.labels)
    maps = maps or _display_maps()
    label = _primary_label(labels, props)
    display = ""
    for key in display_keys or ["name", "label", "title", "id", "uri"]:
        if props.get(key):
            display = props.get(key)
            break
    if isinstance(display, str) and "#" in display:
        display = display.split("#")[-1]
    return {
        "id": str(node.element_id),
        "label": label,
        "display_label": maps.get("classes", {}).get(label, label),
        "labels": labels,
        "name": str(display)[:60],
        "properties": {k: str(v)[:200] for k, v in props.items() if k not in TECHNICAL_RESULT_KEYS and not k.endswith("_embedding")},
        "display_properties": _display_properties(props, maps),
    }


def _ontology_graph(scene_id: str = None) -> dict:
    model = scene_store.get_linked_ontology_model(scene_id) if scene_id else None
    
    # Fallback: if no linked model, try to find the first ontology in management
    if not model:
        try:
            from ontology_intelligence.web.routes.ontology_management import _get_ontology_index, _load_ontology
            index = _get_ontology_index()
            if index:
                # Use the first available ontology as a global fallback
                model = _load_ontology(index[0]['id'])
        except Exception:
            pass

    if not model:
        return {"nodes": [], "links": [], "total_nodes": 0, "total_links": 0, "scene_id": scene_id, "scope": "ontology"}

    ontology = scene_store.normalize_ontology_model(model)
    maps = _display_maps(scene_id)
    nodes = {}
    links = []

    for cls in ontology.get("classes", []):
        cid = f"class:{cls.get('name')}"
        nodes[cid] = {
            "id": cid,
            "label": "Class",
            "display_label": ONTOLOGY_LABELS["Class"],
            "labels": ["Class"],
            "name": cls.get("label") or cls.get("name"),
            "properties": {"name": cls.get("name", ""), "comment": cls.get("comment", "")},
            "display_properties": {"名称": cls.get("name", ""), "说明": cls.get("comment", "")},
        }
        for parent in cls.get("parents") or []:
            if not parent or parent in scene_store.TOP_ONTOLOGY_CLASSES:
                continue
            pid = f"class:{parent}"
            nodes.setdefault(pid, {
                "id": pid, "label": "Class", "display_label": ONTOLOGY_LABELS["Class"], "labels": ["Class"],
                "name": maps["classes"].get(parent, parent), "properties": {"name": parent},
                "display_properties": {"名称": parent},
            })
            links.append({"source": cid, "target": pid, "type": "subClassOf", "display_type": "父类", "properties": {}})

    for prop in ontology.get("object_properties", []):
        pid = f"object_property:{prop.get('name')}"
        nodes[pid] = {
            "id": pid,
            "label": "ObjectProperty",
            "display_label": ONTOLOGY_LABELS["ObjectProperty"],
            "labels": ["ObjectProperty"],
            "name": prop.get("label") or prop.get("name"),
            "properties": {
                "name": prop.get("name", ""),
                "domain": prop.get("domain", ""),
                "range": prop.get("range", ""),
                "comment": prop.get("comment", ""),
            },
            "display_properties": {
                "名称": prop.get("name", ""),
                "定义域": maps["classes"].get(prop.get("domain"), prop.get("domain", "")),
                "值域": maps["classes"].get(prop.get("range"), prop.get("range", "")),
                "说明": prop.get("comment", ""),
            },
        }
        domain = prop.get("domain")
        range_ = prop.get("range")
        if domain:
            did = f"class:{domain}"
            nodes.setdefault(did, {"id": did, "label": "Class", "display_label": ONTOLOGY_LABELS["Class"], "labels": ["Class"], "name": maps["classes"].get(domain, domain), "properties": {"name": domain}, "display_properties": {"名称": domain}})
            links.append({"source": did, "target": pid, "type": "domain", "display_type": "定义域", "properties": {}})
        if range_:
            rid = f"class:{range_}"
            nodes.setdefault(rid, {"id": rid, "label": "Class", "display_label": ONTOLOGY_LABELS["Class"], "labels": ["Class"], "name": maps["classes"].get(range_, range_), "properties": {"name": range_}, "display_properties": {"名称": range_}})
            links.append({"source": pid, "target": rid, "type": "range", "display_type": "值域", "properties": {}})

    for prop in ontology.get("data_properties", []):
        pid = f"data_property:{prop.get('name')}"
        nodes[pid] = {
            "id": pid,
            "label": "DataProperty",
            "display_label": ONTOLOGY_LABELS["DataProperty"],
            "labels": ["DataProperty"],
            "name": prop.get("label") or prop.get("name"),
            "properties": {
                "name": prop.get("name", ""),
                "domains": ", ".join(prop.get("domains") or []),
                "range": prop.get("range", ""),
                "comment": prop.get("comment", ""),
            },
            "display_properties": {
                "名称": prop.get("name", ""),
                "适用类": "、".join(maps["classes"].get(x, x) for x in (prop.get("domains") or prop.get("domain") or [])),
                "类型": prop.get("range", ""),
                "说明": prop.get("comment", ""),
            },
        }
        for domain in prop.get("domains") or prop.get("domain") or []:
            did = f"class:{domain}"
            nodes.setdefault(did, {"id": did, "label": "Class", "display_label": ONTOLOGY_LABELS["Class"], "labels": ["Class"], "name": maps["classes"].get(domain, domain), "properties": {"name": domain}, "display_properties": {"名称": domain}})
            links.append({"source": did, "target": pid, "type": "hasDataProperty", "display_type": "数据属性", "properties": {}})

    return {
        "nodes": list(nodes.values()),
        "links": links,
        "total_nodes": len(nodes),
        "total_links": len(links),
        "scene_id": scene_id,
        "scope": "ontology",
        "label_options": ["Class", "ObjectProperty", "DataProperty"],
        "rel_options": sorted({link["type"] for link in links}),
        "label_display": {key: maps["classes"].get(key, key) for key in ["Class", "ObjectProperty", "DataProperty"]},
        "rel_display": {
            "subClassOf": "父类",
            "domain": "定义域",
            "range": "值域",
            "hasDataProperty": "数据属性",
        },
    }


@router.get("/graph/explore")
async def explore_graph(
    username: str = Depends(verify_token),
    label: Optional[str] = Query(None),
    rel_type: Optional[str] = Query(None),
    scene_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    scope: str = Query("data"),
):
    """返回图谱节点和关系数据"""
    try:
        if scope == "ontology":
            graph = _ontology_graph(scene_id)
            if label:
                graph["nodes"] = [n for n in graph["nodes"] if n["label"] == label]
                node_ids = {n["id"] for n in graph["nodes"]}
                graph["links"] = [l for l in graph["links"] if l["source"] in node_ids and l["target"] in node_ids]
                graph["total_nodes"] = len(graph["nodes"])
                graph["total_links"] = len(graph["links"])
            if rel_type:
                graph["links"] = [l for l in graph["links"] if l["type"] == rel_type]
                node_ids = {x for l in graph["links"] for x in (l["source"], l["target"])}
                graph["nodes"] = [n for n in graph["nodes"] if n["id"] in node_ids]
                graph["total_nodes"] = len(graph["nodes"])
                graph["total_links"] = len(graph["links"])
            return graph
        if scope != "data":
            raise HTTPException(status_code=400, detail="scope must be 'data' or 'ontology'")

        safe_label = assert_cypher_identifier(label, "label") if label else None
        safe_rel_type = assert_cypher_identifier(rel_type, "rel_type") if rel_type else None
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        nodes = {}
        links = []
        label_options = []
        rel_options = []
        display_keys = _display_property_candidates(scene_id)
        maps = _display_maps(scene_id)

        with driver.session() as session:
            # For business graph without a scene, we must filter out meta labels from the base query
            if scope == "data" and not scene_id:
                sys_labels = ["Class", "ObjectProperty", "DataProperty", "Individual", "AnnotationProperty", "_GraphConfig", "Relationship", "Ticket"]
                meta_exclude = " AND ".join(f"NOT n:{lbl} AND NOT m:{lbl}" for lbl in sys_labels)
                if safe_label and safe_rel_type:
                    cypher = f"MATCH (n)-[r:{safe_rel_type}]->(m) WHERE (n:{safe_label} OR m:{safe_label}) AND {meta_exclude}"
                elif safe_label:
                    cypher = f"MATCH (n)-[r]->(m) WHERE (n:{safe_label} OR m:{safe_label}) AND {meta_exclude}"
                elif safe_rel_type:
                    cypher = f"MATCH (n)-[r:{safe_rel_type}]->(m) WHERE {meta_exclude}"
                else:
                    cypher = f"MATCH (n)-[r]->(m) WHERE {meta_exclude}"
            else:
                if safe_label and safe_rel_type:
                    cypher = f"MATCH (n)-[r:{safe_rel_type}]->(m) WHERE (n:{safe_label} OR m:{safe_label})"
                elif safe_label:
                    cypher = f"MATCH (n)-[r]->(m) WHERE (n:{safe_label} OR m:{safe_label})"
                elif safe_rel_type:
                    cypher = f"MATCH (n)-[r:{safe_rel_type}]->(m)"
                else:
                    cypher = f"MATCH (n)-[r]->(m)"
                
            if scene_id:
                cypher += (" AND " if " WHERE " in cypher else " WHERE ")
                cypher += "n.scene_id = $scene_id AND m.scene_id = $scene_id"
            cypher += f" RETURN n, r, m LIMIT {limit}"

            if scene_id:
                option_result = session.run("""
                    MATCH (n {scene_id: $scene_id})
                    RETURN collect(DISTINCT n.ontology_class) AS ontology_classes
                """, scene_id=scene_id).single()
                label_options = sorted([x for x in (option_result["ontology_classes"] if option_result else []) if x])
                rel_options = [
                    r["rel"] for r in session.run("""
                        MATCH ()-[rel]->() WHERE rel.scene_id = $scene_id
                        RETURN DISTINCT type(rel) AS rel ORDER BY rel
                    """, scene_id=scene_id)
                ]

            result = session.run(cypher, scene_id=scene_id)
            for record in result:
                n, m, r = record["n"], record["m"], record["r"]
                for node in [n, m]:
                    nid = str(node.element_id)
                    if nid not in nodes:
                        nodes[nid] = _node_payload(node, display_keys, maps)
                links.append({
                    "source": str(n.element_id),
                    "target": str(m.element_id),
                    "type": r.type,
                    "display_type": maps.get("relationships", {}).get(r.type, r.type),
                    "properties": {k: str(v)[:100] for k, v in dict(r).items()},
                })
        driver.close()
        
        # Ensure options are populated even if result is small or empty
        if not label_options and not safe_label and not safe_rel_type:
            try:
                from neo4j import GraphDatabase
                tmp_driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
                with tmp_driver.session() as s:
                    raw_labels = [r["label"] for r in s.run("CALL db.labels() YIELD label RETURN label")]
                    label_options = sorted([
                        l for l in raw_labels 
                        if l not in META_LABELS and l not in {"Class", "ObjectProperty", "DataProperty", "Individual", "AnnotationProperty", "_GraphConfig", "Relationship", "Ticket"}
                    ])
                    rel_options = sorted([
                        r["rel"] for r in s.run("CALL db.relationshipTypes() YIELD relationshipType AS rel RETURN rel")
                        if r["rel"] not in {"SCO", "DOMAIN", "RANGE", "hasDataProperty"}
                    ])
                tmp_driver.close()
            except:
                pass

        return {"nodes": list(nodes.values()), "links": links,
                "total_nodes": len(nodes), "total_links": len(links), "scene_id": scene_id,
                "scope": scope, "label_options": label_options, "rel_options": rel_options,
                "label_display": {label: maps.get("classes", {}).get(label, label) for label in label_options},
                "rel_display": {rel: maps.get("relationships", {}).get(rel, rel) for rel in rel_options}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图谱查询失败: {e}")


@router.get("/graph/node/{node_id}/neighbors")
async def get_node_neighbors(node_id: str, username: str = Depends(verify_token)):
    """获取节点的所有邻居和关系"""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        neighbors = []
        with driver.session() as session:
            # 出边
            result = session.run("""
                MATCH (n)-[r]->(m) WHERE elementId(n) = $nid
                RETURN type(r) AS rel_type, labels(m) AS labels,
                       m.name AS name, m.id AS id, 'outgoing' AS direction
                LIMIT 50
            """, nid=node_id)
            for rec in result:
                neighbors.append({
                    "rel_type": rec["rel_type"], "direction": rec["direction"],
                    "labels": rec["labels"], "name": rec["name"], "id": rec["id"],
                })
            # 入边
            result = session.run("""
                MATCH (m)-[r]->(n) WHERE elementId(n) = $nid
                RETURN type(r) AS rel_type, labels(m) AS labels,
                       m.name AS name, m.id AS id, 'incoming' AS direction
                LIMIT 50
            """, nid=node_id)
            for rec in result:
                neighbors.append({
                    "rel_type": rec["rel_type"], "direction": rec["direction"],
                    "labels": rec["labels"], "name": rec["name"], "id": rec["id"],
                })
        driver.close()
        return {"node_id": node_id, "neighbors": neighbors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/graph/node/{node_id}/ontology-info")
async def get_node_ontology_info(node_id: str, username: str = Depends(verify_token)):
    """获取节点对应本体类的约束和描述"""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        info = {"node_id": node_id, "labels": [], "class_info": []}
        with driver.session() as session:
            # 获取节点标签
            result = session.run("MATCH (n) WHERE elementId(n) = $nid RETURN labels(n) AS labels", nid=node_id)
            rec = result.single()
            if rec:
                info["labels"] = rec["labels"]
                # 查找对应的 Class 信息
                for label in rec["labels"]:
                    class_result = session.run("""
                        MATCH (c:Class {name: $name})
                        OPTIONAL MATCH (c)-[:SCO]->(parent:Class)
                        WITH c, parent, c['rdfs__comment'] AS rdfs_comment
                        RETURN c.name AS name,
                               COALESCE(c.comment, rdfs_comment) AS comment,
                               collect(DISTINCT parent.name) AS parents
                    """, name=label)
                    class_rec = class_result.single()
                    if class_rec and class_rec["name"]:
                        comment = class_rec["comment"]
                        if isinstance(comment, list):
                            comment = comment[0] if comment else ""
                        info["class_info"].append({
                            "class_name": class_rec["name"],
                            "comment": comment or "",
                            "parents": [p for p in class_rec["parents"] if p],
                        })
        driver.close()
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")
