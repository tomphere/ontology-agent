# =============================================================================
# 智能体核心（重构自 04_agent_main.py）
# =============================================================================
# 使用统一 LLM 工厂，支持多模型切换
# =============================================================================

import os
import re
import importlib
import logging
import warnings
import sqlite3
import yaml
import json
import time
import math

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from langchain_core.prompts import PromptTemplate
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain

from ontology_intelligence.config import settings
from ontology_intelligence.security import assert_cypher_identifier
from ontology_intelligence.agent.llm_factory import create_llm

logger = logging.getLogger(__name__)

META_LABELS = ["SceneEntity", "Thing", "Node", "Resource"]
TECHNICAL_RESULT_KEYS = {"scene_id", "scene_uid", "source_pk", "source_table"}
TECHNICAL_LABELS = {
    "id": "ID",
    "ontology_class": "实体类型",
}

AGENT_SYSTEM_PROMPT = (
    "你是一个企业级的领域知识图谱智能分析助手。\n"
    "【工作流程与规范】\n"
    "1. 意图识别：准确理解用户的查询意图。\n"
    "2. 信息收集：调用图谱查询工具检索数据。如果查询报错或未查到结果，允许更换思路（如扩大范围、换用同义词）重试至多 2 次。\n"
    "3. **及时止损**：[极度重要] 如果经过 2 次重试仍然没有返回有效结果，说明可能没有该数据。请立即停止调用工具，直接回复用户“未能在知识图谱中查到相关信息”，严禁陷入死循环反复查询！\n"
    "4. 诚实作答：完全基于图谱返回的数据回答，严禁臆造或编造数据。\n"
    "5. 语言要求：必须使用中文，条理清晰。"
)


def clean_cypher(raw: str) -> str:
    """Remove common Markdown wrappers and extract only the Cypher block."""
    # Specifically look for ```cypher ... ``` first
    cypher_block = re.search(r"```cypher\s+(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    if cypher_block:
        return cypher_block.group(1).strip()
    
    # Fallback: find all code blocks and pick the most likely Cypher one
    blocks = re.findall(r"```(?:[a-zA-Z]*)\s*(.*?)```", raw, flags=re.DOTALL)
    if blocks:
        for b in reversed(blocks):
            if re.search(r'\b(MATCH|CALL|RETURN|WITH|UNWIND)\b', b, re.IGNORECASE):
                return b.strip()
        return blocks[-1].strip()

    cleaned = raw.strip()
    if cleaned.lower().startswith('cypher\n'):
        cleaned = cleaned[7:].strip()
    elif cleaned.lower().startswith('cypher '):
        cleaned = cleaned[7:].strip()
    return cleaned


def _merge_aliases(target: dict, key: str, values: list):
    if not key:
        return
    bucket = target.setdefault(key, [])
    for value in values or []:
        if value and value != key and value not in bucket:
            bucket.append(value)


def normalize_query_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip("？?。.")


def select_query_routing_rule(query: str, query_routing_rules: list, available_classes=None) -> dict:
    """Select a scene-declared query route. Code is generic; business terms live in scene config."""
    normalized = normalize_query_text(query)
    class_set = set(available_classes or [])
    for route in query_routing_rules or []:
        if not route or route.get("enabled", True) is False:
            continue
        match = route.get("match") or {}
        route_classes = set(match.get("classes") or [])
        if route_classes and class_set and not (route_classes & class_set):
            continue
        all_terms = [str(term) for term in match.get("all_terms") or [] if term]
        any_terms = [str(term) for term in match.get("any_terms") or [] if term]
        if all_terms and not all(term in normalized for term in all_terms):
            continue
        if any_terms and not any(term in normalized for term in any_terms):
            continue
        if all_terms or any_terms:
            return route
    return {}


# =============================================================================
# 模块 1：连接 Neo4j
# =============================================================================
def _get_linked_ontology(scene_id: str = None) -> dict:
    if not scene_id:
        return {}
    try:
        from ontology_intelligence.web import scene_store
        model = scene_store.get_linked_ontology_model(scene_id)
        return scene_store.normalize_ontology_model(model) if model else {}
    except Exception:
        return {}


def _get_schema_via_cypher(graph, scene_id: str = None) -> str:
    """使用纯 Cypher 从 Neo4j 提取 Schema（不依赖 APOC）"""
    schema_parts = []
    try:
        if scene_id:
            node_labels_result = graph.query(
                """
                MATCH (n {scene_id: $scene_id})
                UNWIND labels(n) AS label
                WITH DISTINCT label
                WHERE NOT label IN $meta_labels
                RETURN label
                ORDER BY label
                """,
                {"scene_id": scene_id, "meta_labels": META_LABELS},
            )
        else:
            node_labels_result = graph.query(
                "CALL db.labels() YIELD label RETURN label ORDER BY label"
            )
        node_labels = [r['label'] for r in node_labels_result]

        node_props_lines = []
        for label in node_labels:
            try:
                safe_label = assert_cypher_identifier(label, "Neo4j label")
                if scene_id:
                    props_result = graph.query(
                        f"MATCH (n:{safe_label} {{scene_id: $scene_id}}) WITH n LIMIT 1 RETURN keys(n) AS props",
                        {"scene_id": scene_id},
                    )
                else:
                    props_result = graph.query(
                        f"MATCH (n:{safe_label}) WITH n LIMIT 1 RETURN keys(n) AS props"
                    )
                if props_result and props_result[0]['props']:
                    props_str = ", ".join(f"{p}: STRING" for p in sorted(props_result[0]['props']))
                    node_props_lines.append(f"{label} {{{props_str}}}")
                else:
                    node_props_lines.append(f"{label} {{}}")
            except Exception:
                node_props_lines.append(f"{label} {{}}")

        schema_parts.append("Node properties:")
        schema_parts.extend(node_props_lines)

        schema_parts.append("Relationship properties:")

        schema_parts.append("The relationships:")
        try:
            if scene_id:
                rel_patterns = graph.query(
                    """
                    MATCH (a {scene_id: $scene_id})-[r]->(b {scene_id: $scene_id})
                    WHERE r.scene_id = $scene_id
                    WITH a, r, b,
                         [label IN labels(a) WHERE NOT label IN $meta_labels] AS start_labels,
                         [label IN labels(b) WHERE NOT label IN $meta_labels] AS end_labels
                    RETURN DISTINCT
                         coalesce(a.ontology_class, head(start_labels), head(labels(a))) AS start,
                         type(r) AS rel,
                         coalesce(b.ontology_class, head(end_labels), head(labels(b))) AS end
                    ORDER BY start, rel, end
                    LIMIT 200
                    """,
                    {"scene_id": scene_id, "meta_labels": META_LABELS},
                )
            else:
                rel_patterns = graph.query(
                    """
                    MATCH (a)-[r]->(b)
                    WITH a, r, b,
                         [label IN labels(a) WHERE NOT label IN $meta_labels] AS start_labels,
                         [label IN labels(b) WHERE NOT label IN $meta_labels] AS end_labels
                    RETURN DISTINCT
                         coalesce(a.ontology_class, head(start_labels), head(labels(a))) AS start,
                         type(r) AS rel,
                         coalesce(b.ontology_class, head(end_labels), head(labels(b))) AS end
                    ORDER BY start, rel, end
                    LIMIT 200
                    """,
                    {"meta_labels": META_LABELS},
                )
            for p in rel_patterns:
                schema_parts.append(f"(:{p.get('start','?')})-[:{p.get('rel','?')}]->(:{p.get('end','?')})")
        except Exception as e:
            logger.warning(f"[Schema] 关系模式查询失败: {e}")

        return "\n".join(schema_parts)
    except Exception as e:
        logger.warning(f"[Schema] 提取失败: {e}")
        return "（Schema 提取失败）"


def connect_neo4j(scene_id: str = None):
    """建立与 Neo4j 的连接"""
    logger.info(f"[Neo4j] 正在连接: {settings.neo4j_uri}")
    try:
        graph = Neo4jGraph(
            url=settings.neo4j_uri,
            username=settings.neo4j_user,
            password=settings.neo4j_password,
            enhanced_schema=False,
            refresh_schema=False,
        )
        logger.info("[Neo4j] 连接成功")

        logger.info("[Neo4j] 正在提取 Schema...")
        manual_schema = _get_schema_via_cypher(graph, scene_id=scene_id)
        graph.schema = manual_schema
        logger.info(f"[Neo4j] Schema 摘要:\n{graph.schema[:500]}...")
        return graph
    except Exception as e:
        logger.error(f"[Neo4j] 连接失败: {e}")
        logger.error("  请检查 Neo4j 是否运行以及 .env 中的配置")
        raise RuntimeError(f"Neo4j 连接失败: {e}") from e


# =============================================================================
# 模块 2：动态本体语义提取
# =============================================================================
def get_dynamic_ontology_semantics(graph, scene_id: str = None):
    """从 Neo4j 中动态提取本体的语义描述"""
    logger.info("[本体语义] 正在提取...")
    try:
        ontology = _get_linked_ontology(scene_id)
        if ontology:
            classes = ontology.get("classes") or []
            if not classes:
                return "（暂无本体语义描述）"
            semantics = "【当前场景本体类语义定义】\n"
            for item in classes:
                name = item.get("name", "未知")
                bits = []
                label = item.get("label") or ""
                comment = item.get("comment") or item.get("description") or ""
                parents = item.get("parents") or []
                if label and label != name:
                    bits.append(f"标签={label}")
                if parents:
                    bits.append(f"父类={','.join(parents)}")
                if comment:
                    bits.append(f"说明={comment}")
                semantics += f"  - {name}: {'; '.join(bits) if bits else '无补充说明'}\n"
            logger.info(f"[本体语义] 从场景本体提取 {len(classes)} 条类描述")
            return semantics

        result = graph.query("""
        MATCH (c:Class)
        WITH c, c['rdfs__comment'] AS rdfs_comment
        WHERE c.comment IS NOT NULL OR rdfs_comment IS NOT NULL
        RETURN c.name AS class_name, COALESCE(c.comment, rdfs_comment) AS description
        ORDER BY c.name
        """)
        if not result:
            return "（暂无本体语义描述）"
        semantics = "【企业领域本体语义定义（自动从图谱提取）】\n"
        for record in result:
            name = record.get('class_name', '未知')
            desc = record.get('description', '无描述')
            if isinstance(desc, list):
                desc = desc[0] if desc else '无描述'
            semantics += f"  - {name}: {desc}\n"
        logger.info(f"[本体语义] 成功提取 {len(result)} 条类描述")
        return semantics
    except Exception as e:
        logger.warning(f"[本体语义] 查询失败: {e}")
        return "（本体语义查询失败）"


def get_relationship_semantics(graph, scene_id: str = None):
    """从图谱中提取关系语义描述"""
    try:
        ontology = _get_linked_ontology(scene_id)
        if ontology:
            props = ontology.get("object_properties") or []
            if not props:
                return ""
            semantics = "\n【当前场景对象属性（关系）语义定义】\n"
            for item in props:
                name = item.get("name", "未知")
                bits = []
                label = item.get("label") or ""
                comment = item.get("comment") or item.get("description") or ""
                domain = item.get("domain") or ""
                range_ = item.get("range") or ""
                if label and label != name:
                    bits.append(f"标签={label}")
                if domain:
                    bits.append(f"Domain={domain}")
                if range_:
                    bits.append(f"Range={range_}")
                if comment:
                    bits.append(f"说明={comment}")
                semantics += f"  - {name}: {'; '.join(bits) if bits else '无补充说明'}\n"
            return semantics

        result = graph.query("""
        MATCH (r:Relationship)
        WITH r, r['rdfs__comment'] AS rdfs_comment
        WHERE r.comment IS NOT NULL OR rdfs_comment IS NOT NULL
        RETURN r.name AS rel_name, COALESCE(r.comment, rdfs_comment) AS description
        ORDER BY r.name
        """)
        if not result:
            return ""
        semantics = "\n【对象属性（关系）语义定义】\n"
        for record in result:
            name = record.get('rel_name', '未知')
            desc = record.get('description', '无描述')
            if isinstance(desc, list):
                desc = desc[0] if desc else '无描述'
            semantics += f"  - {name}: {desc}\n"
        return semantics
    except Exception as e:
        return ""


def get_data_property_semantics(graph, scene_id: str = None):
    """Extract ontology data-property contracts for Cypher generation."""
    try:
        ontology = _get_linked_ontology(scene_id)
        if ontology:
            props = ontology.get("data_properties") or []
            if not props:
                return ""
            semantics = "\n【当前场景数据属性（节点字段）语义定义】\n"
            for item in props:
                name = item.get("name", "未知")
                label = item.get("label") or ""
                desc = item.get("comment") or item.get("description") or ""
                domains = item.get("domains") or []
                if isinstance(domains, str):
                    domains = [domains]
                range_ = item.get("range") or ""
                bits = []
                if label and label != name:
                    bits.append(f"标签={label}")
                if domains:
                    bits.append(f"Domain={','.join(domains)}")
                if range_:
                    bits.append(f"Range={range_}")
                if desc:
                    bits.append(f"说明={desc}")
                semantics += f"  - {name}: {'; '.join(bits) if bits else '无补充说明'}\n"
            return semantics

        result = graph.query("""
        MATCH (p:DataProperty)
        RETURN p.name AS prop_name,
               p.label AS label,
               p.comment AS description,
               p.domains AS domains,
               p.range AS range
        ORDER BY p.name
        """)
        if not result:
            return ""
        semantics = "\n【数据属性（节点字段）语义定义】\n"
        for record in result:
            name = record.get("prop_name", "未知")
            label = record.get("label") or ""
            desc = record.get("description") or ""
            domains = record.get("domains") or []
            if isinstance(domains, str):
                domains = [domains]
            range_ = record.get("range") or ""
            bits = []
            if label and label != name:
                bits.append(f"中文名={label}")
            if domains:
                bits.append(f"适用类={','.join(domains)}")
            if range_:
                bits.append(f"类型={range_}")
            if desc:
                bits.append(f"说明={desc}")
            semantics += f"  - {name}: {'; '.join(bits) if bits else '无补充说明'}\n"
        return semantics
    except Exception:
        return ""


def get_scene_display_maps(scene_id: str = None, graph=None) -> dict:
    """Build display labels for ontology classes, properties, and relationships."""
    maps = {"classes": {}, "properties": dict(TECHNICAL_LABELS), "relationships": {}}
    ontology = _get_linked_ontology(scene_id)
    if ontology:
        for cls in ontology.get("classes", []):
            name = cls.get("name")
            if name:
                maps["classes"][name] = cls.get("label") or name
        for prop in ontology.get("data_properties", []):
            name = prop.get("name")
            if name:
                maps["properties"][name] = prop.get("label") or name
        for prop in ontology.get("object_properties", []):
            name = prop.get("name")
            if name:
                maps["relationships"][name] = prop.get("label") or name
        return maps

    if not graph:
        return maps
    try:
        for record in graph.query("MATCH (c:Class) RETURN c.name AS name, c.label AS label"):
            if record.get("name"):
                maps["classes"][record["name"]] = record.get("label") or record["name"]
        for record in graph.query("MATCH (p:DataProperty) RETURN p.name AS name, p.label AS label"):
            if record.get("name"):
                maps["properties"][record["name"]] = record.get("label") or record["name"]
        for record in graph.query("MATCH (r:Relationship) RETURN r.name AS name, r.label AS label"):
            if record.get("name"):
                maps["relationships"][record["name"]] = record.get("label") or record["name"]
    except Exception:
        pass
    return maps


def build_scene_ontology_contract(scene_id: str = None) -> dict:
    """Build a compact, executable ontology contract from the scene ontology and mapping."""
    contract = {
        "scene_id": scene_id,
        "linked_ontology_id": "",
        "classes": {},
        "properties": {},
        "relationships": {},
        "aliases": {},
        "rules": [],
        "paths": [],
        "field_mappings": [],
        "vector_fields": [],
        "query_routing": [],
        "mapping_count": 0,
    }
    if not scene_id:
        return contract
    try:
        from ontology_intelligence.web import scene_store

        scene = scene_store.get_scene(scene_id) or {}
        contract["linked_ontology_id"] = scene.get("linked_ontology_id") or ""
        ontology_model = scene_store.get_linked_ontology_model(scene_id)
        ontology = scene_store.normalize_ontology_model(ontology_model) if ontology_model else {}

        for item in ontology.get("classes", []):
            name = item.get("name")
            if not name:
                continue
            contract["classes"][name] = {
                "label": item.get("label") or name,
                "comment": item.get("comment") or item.get("description") or "",
                "parents": item.get("parents") or [],
            }
            _merge_aliases(contract["aliases"], name, [item.get("label"), item.get("comment")])

        for item in ontology.get("data_properties", []):
            name = item.get("name")
            if not name:
                continue
            contract["properties"][name] = {
                "label": item.get("label") or name,
                "comment": item.get("comment") or item.get("description") or "",
                "domains": item.get("domains") or item.get("domain") or [],
                "range": item.get("range") or "",
            }
            _merge_aliases(contract["aliases"], name, [item.get("label"), item.get("comment")])

        for item in ontology.get("object_properties", []):
            name = item.get("name")
            if not name:
                continue
            contract["relationships"][name] = {
                "label": item.get("label") or name,
                "comment": item.get("comment") or item.get("description") or "",
                "domain": item.get("domain") or "",
                "range": item.get("range") or "",
            }
            _merge_aliases(contract["aliases"], name, [item.get("label"), item.get("comment")])

        scene_aliases = scene_store.load_scene_aliases(scene_id)
        for key, values in scene_aliases.items():
            _merge_aliases(contract["aliases"], key, values)
            
        scene_rules = scene_store.load_scene_rules(scene_id)
        contract["rules"].extend(scene_rules)

        mapping_path = scene_store.get_scene_mapping_path(scene_id)
        if not os.path.exists(mapping_path):
            return contract
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping_config = yaml.safe_load(f) or {}

        contract["query_routing"] = scene_store.load_scene_routing(scene_id)
        mappings = mapping_config.get("mappings") or []
        contract["mapping_count"] = len(mappings)

        for mapping in mappings:
            table = mapping.get("table_name", "")
            strategy = mapping.get("entity_class_strategy") or {}
            stype = strategy.get("type")
            if stype == "relationship":
                rel_name = strategy.get("ontology_property", "")
                rel_props = [
                    {"column": rp.get("column"), "property": rp.get("property") or rp.get("ontology_property")}
                    for rp in mapping.get("relationship_properties", [])
                ]
                contract["paths"].append({
                    "table": table,
                    "source": strategy.get("source_class", ""),
                    "relationship": rel_name,
                    "target": strategy.get("target_class", ""),
                    "source_column": strategy.get("source_column", ""),
                    "target_column": strategy.get("target_column", ""),
                    "relationship_properties": rel_props,
                })
                continue

            class_name = strategy.get("class_name") or f"dynamic:{strategy.get('column', '')}"
            for dp in mapping.get("data_properties", []):
                contract["field_mappings"].append({
                    "table": table,
                    "class": class_name,
                    "column": dp.get("column", ""),
                    "property": dp.get("ontology_property", ""),
                })
            for op in mapping.get("object_properties", []):
                if op.get("direction", "OUTGOING") == "INCOMING":
                    source, target = op.get("target_label", ""), class_name
                else:
                    source, target = class_name, op.get("target_label", "")
                contract["paths"].append({
                    "table": table,
                    "source": source,
                    "relationship": op.get("ontology_property", ""),
                    "target": target,
                    "foreign_key_column": op.get("foreign_key_column", ""),
                    "direction": op.get("direction", "OUTGOING"),
                })
            for vf in mapping.get("vectorize_fields", []):
                contract["vector_fields"].append({"table": table, "class": class_name, "column": vf})

        return contract
    except Exception as e:
        logger.warning(f"[本体查询契约] 构建失败: {e}")
        return contract


def build_scene_ontology_contract_semantics(scene_id: str = None) -> str:
    """Render the scene ontology contract as prompt text for Cypher generation."""
    contract = build_scene_ontology_contract(scene_id)
    if not contract.get("mapping_count") and not contract.get("classes"):
        return ""

    lines = ["\n【本体驱动查询契约：优先于 few-shot 的可执行语义】"]
    if contract.get("linked_ontology_id"):
        lines.append(f"  - 权威本体ID: {contract['linked_ontology_id']}")
    if contract.get("rules"):
        lines.append("  - 业务规则:")
        lines.extend(f"    * {rule}" for rule in contract["rules"])

    alias_lines = []
    for key in sorted(contract.get("aliases", {})):
        values = [str(v) for v in contract["aliases"][key] if v]
        if values:
            alias_lines.append(f"{key}={ '/'.join(values[:6]) }")
    if alias_lines:
        lines.append("  - 术语别名: " + "；".join(alias_lines[:28]))

    if contract.get("paths"):
        lines.append("  - 候选查询路径:")
        for path in contract["paths"][:80]:
            rel_props = path.get("relationship_properties") or []
            rel_prop_text = ""
            if rel_props:
                rel_prop_text = "，关系属性 " + ",".join(
                    f"{rp.get('column')}→{rp.get('property')}" for rp in rel_props if rp.get("column")
                )
            lines.append(
                f"    * {path.get('source')}-[:{path.get('relationship')}]->{path.get('target')}"
                f"（来源表 {path.get('table')}{rel_prop_text}）"
            )

    if contract.get("field_mappings"):
        pairs = [
            f"{item['table']}.{item['column']}→{item['class']}.{item['property']}"
            for item in contract["field_mappings"][:80]
        ]
        lines.append("  - 字段落点: " + "；".join(pairs))

    if contract.get("vector_fields"):
        vectors = [f"{item['table']}.{item['column']}({item['class']})" for item in contract["vector_fields"]]
        lines.append("  - 向量字段: " + "；".join(vectors))
    if contract.get("query_routing"):
        lines.append("  - 查询路由规则:")
        for route in contract["query_routing"][:20]:
            match = route.get("match") or {}
            terms = ",".join(str(x) for x in (match.get("any_terms") or [])[:12])
            target = route.get("tool") or route.get("function") or route.get("mode") or route.get("name")
            lines.append(f"    * {route.get('name') or 'unnamed'} -> {target}（触发词:{terms}）")
    lines.append("  - 约束：先根据别名/规则选择类和属性，再只沿候选查询路径连边；few-shot 只能作为样例补充，不能覆盖本契约。")
    return "\n".join(lines) + "\n"


def build_scene_mapping_semantics(scene_id: str = None):
    """Summarize scene mapping.yaml as a query contract for the LLM."""
    if not scene_id:
        return ""
    try:
        from ontology_intelligence.web import scene_store

        mapping_path = scene_store.get_scene_mapping_path(scene_id)
        if not os.path.exists(mapping_path):
            return ""
        with open(mapping_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        mappings = config.get("mappings") or []
        if not mappings:
            return ""

        ontology_model = scene_store.get_linked_ontology_model(scene_id)
        ontology = scene_store.normalize_ontology_model(ontology_model) if ontology_model else {}
        data_prop_meta = {
            prop.get("name"): prop
            for prop in ontology.get("data_properties", [])
            if prop.get("name")
        }
        object_prop_meta = {
            prop.get("name"): prop
            for prop in ontology.get("object_properties", [])
            if prop.get("name")
        }
        class_meta = {
            cls.get("name"): cls
            for cls in ontology.get("classes", [])
            if cls.get("name")
        }

        def describe_class(class_name: str) -> str:
            meta = class_meta.get(class_name or "") or {}
            label = meta.get("label") or ""
            comment = meta.get("comment") or meta.get("description") or ""
            extras = []
            if label and label != class_name:
                extras.append(f"标签={label}")
            if comment:
                extras.append(f"说明={comment}")
            return f"{class_name} ({'; '.join(extras)})" if extras else str(class_name or "")

        def describe_data_property(prop_name: str) -> str:
            meta = data_prop_meta.get(prop_name or "") or {}
            label = meta.get("label") or ""
            comment = meta.get("comment") or meta.get("description") or ""
            domains = meta.get("domains") or []
            if isinstance(domains, str):
                domains = [domains]
            range_ = meta.get("range") or ""
            extras = []
            if label and label != prop_name:
                extras.append(f"标签={label}")
            if domains:
                extras.append(f"Domain={','.join(domains)}")
            if range_:
                extras.append(f"Range={range_}")
            if comment:
                extras.append(f"说明={comment}")
            return f"{prop_name} ({'; '.join(extras)})" if extras else str(prop_name or "")

        def describe_object_property(prop_name: str) -> str:
            meta = object_prop_meta.get(prop_name or "") or {}
            label = meta.get("label") or ""
            comment = meta.get("comment") or meta.get("description") or ""
            domain = meta.get("domain") or ""
            range_ = meta.get("range") or ""
            extras = []
            if label and label != prop_name:
                extras.append(f"标签={label}")
            if domain:
                extras.append(f"Domain={domain}")
            if range_:
                extras.append(f"Range={range_}")
            if comment:
                extras.append(f"说明={comment}")
            return f"{prop_name} ({'; '.join(extras)})" if extras else str(prop_name or "")

        lines = ["\n【场景数据映射契约：自然语言必须落到这些类、属性、关系】"]
        for mapping in mappings:
            table = mapping.get("table_name", "")
            strategy = mapping.get("entity_class_strategy") or {}
            stype = strategy.get("type")
            if stype == "dynamic_column":
                lines.append(f"  - 表 {table}: 动态实体类来自字段 {strategy.get('column')}，节点主键 {mapping.get('node_id_column')}")
            elif stype == "relationship":
                relationship_name = describe_object_property(strategy.get("ontology_property"))
                rel_props = mapping.get("relationship_properties") or []
                rel_prop_text = ""
                if rel_props:
                    rel_prop_text = "，关系属性: " + ", ".join(
                        f"{rp.get('column')}→{rp.get('property') or rp.get('ontology_property')}"
                        for rp in rel_props
                    )
                lines.append(
                    f"  - 桥表 {table}: ({describe_class(strategy.get('source_class'))}.{strategy.get('source_column')})"
                    f"-[:{relationship_name}]->"
                    f"({describe_class(strategy.get('target_class'))}.{strategy.get('target_column')})"
                    f"{rel_prop_text}"
                )
                continue
            else:
                lines.append(f"  - 表 {table}: 实体类 {describe_class(strategy.get('class_name'))}，节点主键 {mapping.get('node_id_column')}")

            data_props = mapping.get("data_properties") or []
            if data_props:
                pairs = [f"{dp.get('column')}→{describe_data_property(dp.get('ontology_property'))}" for dp in data_props]
                lines.append(f"    数据属性: {', '.join(pairs)}")
            object_props = mapping.get("object_properties") or []
            if object_props:
                pairs = [
                    f"{op.get('foreign_key_column')} {op.get('direction', 'OUTGOING')} "
                    f"{describe_object_property(op.get('ontology_property'))} {describe_class(op.get('target_label'))}"
                    for op in object_props
                ]
                lines.append(f"    对象关系: {', '.join(pairs)}")
            vectors = mapping.get("vectorize_fields") or []
            if vectors:
                lines.append(f"    向量化文本字段: {', '.join(vectors)}")
        lines.append("  - 约束：自然语言中的业务词必须通过本场景本体的 label/comment、属性 Domain/Range、以及表字段→本体属性映射动态解析。")
        lines.append("  - 约束：如果当前场景没有声明某个类、属性或关系，不要沿用其他场景的字段名、路径或枚举值。")
        return "\n".join(lines) + "\n"
    except Exception as e:
        logger.warning(f"[场景映射语义] 加载失败: {e}")
        return ""


_FEW_SHOT_CACHE = {}

def _cosine_similarity(v1: list, v2: list) -> float:
    if not v1 or not v2: return 0.0
    dot = sum(x * y for x, y in zip(v1, v2))
    n1 = math.sqrt(sum(x * x for x in v1))
    n2 = math.sqrt(sum(x * x for x in v2))
    return dot / (n1 * n2) if n1 and n2 else 0.0

def parse_few_shot_cypher_examples(few_shots: str) -> list:
    """Extract exact user-question to Cypher examples from scene few_shots text."""
    if not few_shots:
        return []
    examples = []
    pattern = re.compile(
        r"(?:用户问题|用户问|问题|Question)\s*[:：]\s*(?P<question>.+?)\n+"
        r"(?:Cypher|cypher|Cypher查询|查询语句)\s*[:：]\s*(?P<cypher>.*?)(?=\n\s*(?:用户问题|用户问|问题|Question)\s*[:：]|\Z)",
        flags=re.DOTALL,
    )
    for match in pattern.finditer(few_shots):
        question = match.group("question").strip()
        raw_cypher = match.group("cypher").strip()
        cypher = clean_cypher(raw_cypher)
        if question and cypher:
            examples.append({"question": question, "cypher": cypher})
    return examples

def get_scene_few_shots_cache(scene_id: str) -> list:
    """Load and embed few-shot examples with caching based on file modification time."""
    if not scene_id:
        return []
    try:
        from ontology_intelligence.web import scene_store
        from ontology_intelligence.agent.llm_factory import get_embedding_vector

        fs_path = os.path.join(scene_store._scene_dir(scene_id), "few_shots.txt")
        if not os.path.isfile(fs_path):
            return []
            
        mtime = os.path.getmtime(fs_path)
        cache_entry = _FEW_SHOT_CACHE.get(scene_id)
        
        if not cache_entry or cache_entry["mtime"] != mtime:
            with open(fs_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            parsed = parse_few_shot_cypher_examples(content)
            for ex in parsed:
                try:
                    ex["vector"] = get_embedding_vector(ex["question"])
                except Exception as e:
                    logger.warning(f"[Few-Shot Embedding] Failed for '{ex['question']}': {e}")
                    ex["vector"] = None
                    
            _FEW_SHOT_CACHE[scene_id] = {"mtime": mtime, "examples": parsed}
            cache_entry = _FEW_SHOT_CACHE[scene_id]
            logger.info(f"[Few-Shot Cache] Cached {len(parsed)} examples for scene {scene_id}.")
            
        return cache_entry["examples"]
    except Exception as e:
        logger.warning(f"[场景 Few-Shot] 加载与向量化失败: {e}")
        return []

def get_dynamic_few_shots(scene_id: str, query: str, top_k: int = 3) -> str:
    """Retrieve top-K most similar few-shot examples using cosine similarity."""
    examples = get_scene_few_shots_cache(scene_id)
    if not examples:
        return ""
        
    if len(examples) <= top_k:
        top_examples = examples
    else:
        from ontology_intelligence.agent.llm_factory import get_embedding_vector
        query_vector = get_embedding_vector(query)
        
        if not query_vector:
            top_examples = examples[:top_k]
        else:
            scored = []
            for ex in examples:
                sim = _cosine_similarity(query_vector, ex.get("vector"))
                scored.append((sim, ex))
            scored.sort(key=lambda x: x[0], reverse=True)
            top_examples = [ex for sim, ex in scored[:top_k]]
            
    lines = [
        "\n【场景 Agent 提示词 / Few-Shot 引导样本】",
        "根据语义检索，以下是与当前问题最相似的历史查询样例。优先参考样例中的写法：\n"
    ]
    for ex in top_examples:
        lines.append(f"问题: {ex['question']}\nCypher:\n```cypher\n{ex['cypher']}\n```\n")
        
    return "\n".join(lines)


# =============================================================================
# 模块 3：构建 Cypher Prompt
# =============================================================================
def build_cypher_prompt(ontology_semantics, relationship_semantics, scene_id: str = None, data_property_semantics: str = "", mapping_semantics: str = "", ontology_contract_semantics: str = ""):
    """构建注入本体语义的 Cypher 生成 Prompt"""
    scene_scope = ""
    if scene_id:
        scene_scope = f"""
【场景范围】
当前对话绑定场景 scene_id = "{scene_id}"。
所有业务实例查询都必须限制在该场景内：对每个业务节点增加 scene_id = "{scene_id}" 条件。
示例：MATCH (n:当前场景Schema中的类名) WHERE n.scene_id = "{scene_id}" RETURN n
不要把 Class、Relationship、Resource 等本体元数据节点当作业务实例节点过滤。
"""

    CYPHER_GENERATION_TEMPLATE = """你是一个精通 Neo4j Cypher 查询语言的图数据查询专家。
请根据以下图谱结构信息和语义定义，将用户的自然语言问题转化为准确的 Cypher 查询语句。

============================================================
【图谱 Schema】
{schema}

{ontology_semantics}
{relationship_semantics}
{data_property_semantics}
{ontology_contract_semantics}
{mapping_semantics}
{few_shot_semantics}
{scene_scope}
============================================================

【查询规范】
1. 节点已打上完整继承链标签，只能引用 Schema 中声明的 Label 和关系类型。
2. 严禁在 MATCH 中使用属性精确匹配，必须在 WHERE 中使用 CONTAINS。
3. 字符串过滤（如 CONTAINS, =）必须使用 toLower() 函数或正则 (?i) 实现“不区分大小写”的匹配。
4. 不要画蛇添足地添加不必要的关系链，简单查询只需 MATCH 目标节点。
5. 不要在普通 Cypher 中生成 $embedding 参数；语义向量检索应交给专用工具处理。
6. 必须严格使用上方“数据属性”和“场景数据映射契约”中出现的属性名、类名和关系名，不能沿用其他场景的字段名或路径。
7. 解析用户的业务词时，优先根据当前场景本体的 label/comment、属性 Domain/Range、表字段名和字段→本体属性映射来选择属性。
8. 如果用户提到枚举值、等级、状态、类型、颜色或分类，使用用户原文中的值做 CONTAINS/正则匹配；不要把它翻译成其他场景的编码。
9. 如果用户问跨实体关联，必须从“本体驱动查询契约/场景数据映射契约”的候选路径中选择路径；没有契约支持时先返回无法确定路径。
10. 如果用户问“某类属性是什么”，先在映射契约中找到对应属性，再生成 Cypher。
11. few-shot 只作为相近样例参考；如果 few-shot 与本体查询契约冲突，必须服从本体查询契约。
12. 必须在 RETURN 子句中使用 `AS` 关键字为每个返回的变量或属性设置中文别名（如 `RETURN p1 AS 王海涛, ph1 AS 通话号码`），严禁直接返回英文字母变量名。

用户问题: {question}

【输出格式要求】
请务必按以下两步进行输出，这非常重要：
第一步：使用 ```thought ... ``` 代码块输出你的思考过程。在思考过程中，必须明确列出：
   1. 目标实体与属性过滤条件（识别出用户问题中的业务词汇应该映射到哪个 Label 和属性上）。
   2. 选择的候选查询路径（参考上方提供的候选查询路径，不要自己生造路径）。
第二步：将最终的 Cypher 语句包裹在 ```cypher ... ``` 代码块中返回。"""

    return PromptTemplate(
        template=CYPHER_GENERATION_TEMPLATE,
        input_variables=["schema", "question", "few_shot_semantics"],
        partial_variables={
            "ontology_semantics": ontology_semantics,
            "relationship_semantics": relationship_semantics,
            "data_property_semantics": data_property_semantics,
            "ontology_contract_semantics": ontology_contract_semantics,
            "mapping_semantics": mapping_semantics,
            "scene_scope": scene_scope,
        },
    )


# =============================================================================
# 模块 4：动态插件加载
# =============================================================================
def load_plugins(scene_id: str = None):
    """动态加载 ontology_intelligence/plugins/ 目录下的工具插件"""
    plugin_dir = settings.plugin_dir
    loaded_tools = []

    logger.info(f"\n{'='*50}")
    logger.info(f"[插件系统] 扫描目录: {plugin_dir}")
    logger.info(f"{'='*50}")

    if not os.path.exists(plugin_dir):
        logger.warning(f"[插件系统] 目录不存在: {plugin_dir}")
        return loaded_tools

    plugin_files = [
        f for f in os.listdir(plugin_dir)
        if f.endswith('.py') and f != '__init__.py'
    ]

    if not plugin_files:
        logger.info("[插件系统] 未发现任何插件")
        return loaded_tools

    for filename in sorted(plugin_files):
        module_name = filename[:-3]
        mod_path = f"ontology_intelligence.plugins.{module_name}"
        try:
            module = importlib.import_module(mod_path)
        except ImportError as e:
            logger.error(f"[插件系统] ✗ 导入失败 {filename}: {e}")
            continue

        if not hasattr(module, 'get_tool'):
            logger.warning(f"[插件系统] ⚠ {filename}: 缺少 get_tool()")
            continue
        if scene_id:
            supports_scene = getattr(module, "supports_scene", None)
            scene_ids = getattr(module, "SCENE_IDS", None)
            scene_agnostic = bool(getattr(module, "SCENE_AGNOSTIC", False))
            if callable(supports_scene):
                try:
                    if not supports_scene(scene_id):
                        logger.info(f"[插件系统] 跳过: {filename} 未声明支持场景 {scene_id}")
                        continue
                except Exception as e:
                    logger.warning(f"[插件系统] 跳过: {filename} 场景兼容性检查失败: {e}")
                    continue
            elif scene_ids is not None:
                if scene_id not in set(scene_ids):
                    logger.info(f"[插件系统] 跳过: {filename} 未包含场景 {scene_id}")
                    continue
            elif not scene_agnostic:
                logger.info(f"[插件系统] 跳过: {filename} 未声明为场景通用插件")
                continue
        try:
            try:
                tool = module.get_tool(scene_id=scene_id)
            except TypeError:
                tool = module.get_tool()
            if not isinstance(tool, StructuredTool):
                tool = StructuredTool.from_function(
                    func=tool.func, name=tool.name, description=tool.description,
                )
            loaded_tools.append(tool)
            logger.info(f"[插件系统] ✓ 加载: {tool.name} ({filename})")
        except Exception as e:
            logger.error(f"[插件系统] ✗ 异常 {filename}: {e}")

    logger.info(f"[插件系统] 共加载 {len(loaded_tools)} 个插件\n")
    return loaded_tools


# =============================================================================
# 模块 5：构建图谱查询工具
# =============================================================================
def build_graph_query_tool(graph, cypher_prompt, llm, display_maps: dict = None, scene_id: str = None, few_shots: str = "", query_routing: list = None):
    """Build a graph query tool that uses scene examples and local result formatting."""
    display_maps = display_maps or {"classes": {}, "properties": dict(TECHNICAL_LABELS), "relationships": {}}
    if query_routing is None and scene_id:
        query_routing = build_scene_ontology_contract(scene_id).get("query_routing", [])
    query_routing = query_routing or []

    # 安全拦截：猴子补丁
    original_query = graph.query
    def safe_query(query: str, params: dict = None):
        if params is None:
            params = {}
        query = clean_cypher(query)
        unsafe_keywords = ["DELETE", "REMOVE", "SET", "MERGE", "CREATE", "DROP"]
        upper_query = query.upper()
        for kw in unsafe_keywords:
            if re.search(rf"\b{kw}\b", upper_query):
                raise ValueError(f"【安全拦截】禁止使用 '{kw}'")
        return original_query(query, params)
    graph.query = safe_query

    def _display_key(key: str, alias_labels: dict = None) -> str:
        if alias_labels and key in alias_labels:
            return alias_labels[key]
        return display_maps.get("properties", {}).get(key, key)

    def _display_value(key: str, value):
        if key == "ontology_class" and isinstance(value, str):
            return display_maps.get("classes", {}).get(value, value)
        return value

    def _plain_props(value):
        try:
            props = dict(value)
        except Exception:
            return None
        return {k: v for k, v in props.items() if k not in TECHNICAL_RESULT_KEYS and not str(k).endswith("_embedding")}

    def _compact_value(value, depth: int = 0):
        if value is None:
            return ""
        if depth > 2:
            return "..."
        if isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, str):
            return value[:160] + ("..." if len(value) > 160 else "")
        if isinstance(value, (list, tuple)):
            if value and all(isinstance(item, (int, float)) for item in value):
                return f"[向量 {len(value)} 维]"
            items = [_compact_value(item, depth + 1) for item in list(value)[:5]]
            suffix = f", ... 共 {len(value)} 项" if len(value) > 5 else ""
            return "[" + ", ".join(str(item) for item in items if item != "") + suffix + "]"

        rel_type = getattr(value, "type", None)
        if rel_type and value.__class__.__name__.lower().endswith("relationship"):
            return f"关系:{rel_type}"

        try:
            props = dict(value)
        except Exception:
            props = None
        if props is not None:
            clean = _plain_props(value) or {}
            priority_keys = [
                "ontology_class", "hasName", "name", "label", "title", "id",
                "riskLevel", "riskScore", "eventTime", "incidentDetails",
                "phoneNumber", "accountNumber", "plateNumber", "tripRoute",
                "purchaseCategory", "recordContent", "hasAddress",
            ]
            ordered_keys = [k for k in priority_keys if k in clean]
            ordered_keys.extend(k for k in clean.keys() if k not in ordered_keys and not str(k).startswith("scene_"))
            parts = []
            for key in ordered_keys[:8]:
                compact = _compact_value(_display_value(key, clean.get(key)), depth + 1)
                if compact:
                    parts.append(f"{_display_key(key)}: {compact}")
            return "{" + "；".join(parts) + "}" if parts else "{}"

        text = str(value)
        return text[:160] + ("..." if len(text) > 160 else "")

    def _split_return_items(return_clause: str) -> list:
        items = []
        buf = []
        depth = 0
        quote = ""
        for ch in return_clause:
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = ""
                continue
            if ch in ("'", '"'):
                quote = ch
                buf.append(ch)
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]}" and depth > 0:
                depth -= 1
            if ch == "," and depth == 0:
                item = "".join(buf).strip()
                if item:
                    items.append(item)
                buf = []
            else:
                buf.append(ch)
        item = "".join(buf).strip()
        if item:
            items.append(item)
        return items

    def _return_alias_labels(cypher: str) -> dict:
        """Infer display labels for Cypher aliases from ontology class/property labels."""
        if not cypher:
            return {}

        variable_classes = {}
        for match in re.finditer(r"\(\s*([A-Za-z_][\w]*)\s*:\s*([A-Za-z_][\w]*)", cypher):
            variable_classes[match.group(1)] = match.group(2)

        return_match = re.search(
            r"\bRETURN\b\s+(.+?)(?:\bORDER\s+BY\b|\bSKIP\b|\bLIMIT\b|$)",
            cypher,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not return_match:
            return {}

        labels = {}
        for item in _split_return_items(return_match.group(1)):
            alias_match = re.search(r"(.+?)\s+AS\s+([A-Za-z_][\w]*)\s*$", item, flags=re.IGNORECASE | re.DOTALL)
            if alias_match:
                expression = alias_match.group(1).strip()
                alias = alias_match.group(2).strip()
            else:
                expression = item.strip()
                alias = ""

            prop_match = re.search(r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b", expression)
            if prop_match and alias:
                variable = prop_match.group(1)
                prop_name = prop_match.group(2)
                prop_label = display_maps.get("properties", {}).get(prop_name, prop_name)
                class_name = variable_classes.get(variable)
                class_label = display_maps.get("classes", {}).get(class_name, class_name) if class_name else ""
                labels[alias] = f"{class_label}{prop_label}" if class_label and prop_label else prop_label or alias
                continue

            if alias:
                labels[alias] = _display_key(alias)
            elif expression in display_maps.get("properties", {}):
                labels[expression] = _display_key(expression)
        return labels

    def _flatten_row(row, alias_labels: dict = None) -> dict:
        if not isinstance(row, dict):
            return {"结果": _compact_value(row)}

        def put_value(target: dict, raw_key: str, value):
            label = _display_key(raw_key, alias_labels)
            if label in target:
                label = f"{label}({raw_key})"
            if label in target:
                idx = 2
                base = label
                while label in target:
                    label = f"{base}_{idx}"
                    idx += 1
            target[label] = value

        visible_items = [(key, value) for key, value in row.items() if value is not None]
        if len(visible_items) == 1:
            _, value = visible_items[0]
            props = _plain_props(value)
            if props is not None:
                flat = {}
                for key, prop_value in props.items():
                    compact = _compact_value(_display_value(key, prop_value))
                    if compact != "":
                        put_value(flat, key, compact)
                return flat
        flat = {}
        for key, value in visible_items:
            props = _plain_props(value)
            if props is not None:
                name = props.get("hasName") or props.get("name") or props.get("label") or props.get("id")
                entity_type = display_maps.get("classes", {}).get(str(props.get("ontology_class")), props.get("ontology_class"))
                put_value(flat, key, " / ".join(str(x) for x in [entity_type, name] if x))
            else:
                put_value(flat, key, _compact_value(_display_value(key, value)))
        return flat

    def _structured_artifact(rows, alias_labels: dict = None) -> dict:
        records = [_flatten_row(row, alias_labels=alias_labels) for row in rows[:200]]
        columns = []
        for record in records:
            for key in record.keys():
                if key not in columns:
                    columns.append(key)
        numeric_columns = [
            col for col in columns
            if any(isinstance(record.get(col), (int, float)) for record in records)
        ]
        return {
            "type": "table",
            "columns": columns,
            "rows": records,
            "chartable": bool(numeric_columns and len(columns) >= 2),
            "numeric_columns": numeric_columns,
        }

    def _format_rows(rows, alias_labels: dict = None) -> str:
        if not rows:
            return ""
        lines = ["查询结果如下："]
        for idx, row in enumerate(rows[:20], 1):
            flat = _flatten_row(row, alias_labels=alias_labels)
            parts = [f"{key}: {value}" for key, value in flat.items() if value != ""]
            lines.append(f"{idx}. " + "；".join(parts))
        if len(rows) > 20:
            lines.append(f"... 其余 {len(rows) - 20} 条已省略")
        return "\n".join(lines)

    def _result_payload(
        content: str,
        rows=None,
        cypher: str = "",
        row_count: int = 0,
        alias_labels: dict = None,
        elapsed_ms: int = None,
        generate_ms: int = None,
        total_ms: int = None,
        fast_path: bool = None,
    ) -> str:
        evidence = {"cypher": cypher, "query": cypher, "row_count": row_count}
        if elapsed_ms is not None:
            evidence["elapsed_ms"] = elapsed_ms
        if generate_ms is not None:
            evidence["generate_ms"] = generate_ms
        if total_ms is not None:
            evidence["total_ms"] = total_ms
        if fast_path is not None:
            evidence["fast_path"] = fast_path
        payload = {
            "__oi_result__": True,
            "content": content,
            "artifact": _structured_artifact(rows or [], alias_labels=alias_labels) if rows else None,
            "evidence": evidence,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _normalize_question(text: str) -> str:
        return normalize_query_text(text)

    def _delegate_query_route(route: dict, user_query: str) -> str:
        function_path = route.get("function") or ""
        if not function_path or "." not in function_path:
            return ""
        try:
            module_name, function_name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            func = getattr(module, function_name)
            try:
                return func(user_query, scene_id=scene_id)
            except TypeError:
                return func(user_query)
        except Exception as e:
            logger.warning(f"[图谱查询] 查询路由 {route.get('name') or function_path} 降级失败: {e}")
            return ""

    def _few_shot_fast_path(user_query: str) -> str:
        """Use exact operator-maintained scene examples, never code-level scene knowledge."""
        normalized = _normalize_question(user_query)
        examples = get_scene_few_shots_cache(scene_id)
        for example in examples:
            example_question = _normalize_question(example.get("question", ""))
            if example_question == normalized or example_question in normalized or normalized in example_question:
                return example.get("cypher", "")
        return ""

    def _validate_and_prepare_cypher(cypher: str, params: dict = None) -> tuple:
        """Validate generated Cypher against the current ontology contract and fill safe params."""
        params = dict(params or {})
        cypher = clean_cypher(cypher)
        if not cypher:
            raise ValueError("未生成可执行 Cypher")

        upper = cypher.upper()
        if "$embedding" in cypher:
            raise ValueError("普通图谱查询不能使用 $embedding；请改用语义检索工具。")
        if not re.search(r"\bMATCH\b|\bRETURN\b|\bCALL\b", upper):
            raise ValueError("生成内容不是查询型 Cypher")

        if scene_id and "$scene_id" in cypher:
            params["scene_id"] = scene_id

        unknown_params = sorted(set(re.findall(r"\$([A-Za-z_][\w]*)", cypher)) - set(params.keys()))
        if unknown_params:
            raise ValueError(f"Cypher 含未注入参数: {', '.join(unknown_params)}")

        class_labels = set(display_maps.get("classes", {}).keys())
        allowed_labels = class_labels | set(META_LABELS) | {"SceneEntity"}
        used_labels = set(re.findall(r":\s*([A-Za-z_][\w]*)", cypher))
        unknown_labels = sorted(label for label in used_labels if label not in allowed_labels and label not in display_maps.get("relationships", {}))
        if class_labels and unknown_labels:
            raise ValueError(f"Cypher 使用了当前本体未声明的 Label: {', '.join(unknown_labels)}")

        allowed_relationships = set(display_maps.get("relationships", {}).keys())
        used_relationships = set(re.findall(r"\[\s*(?:[A-Za-z_][\w]*)?\s*:\s*([A-Za-z_][\w]*)", cypher))
        unknown_relationships = sorted(rel for rel in used_relationships if rel not in allowed_relationships)
        if allowed_relationships and unknown_relationships:
            raise ValueError(f"Cypher 使用了当前本体未声明的关系: {', '.join(unknown_relationships)}")

        return cypher, params

    def _generate_cypher_with_retry(user_query: str, max_retries: int = 3, callbacks=None) -> tuple:
        fast = _few_shot_fast_path(user_query)
        if fast:
            try:
                cypher, params = _validate_and_prepare_cypher(fast, {"scene_id": scene_id} if scene_id else {})
                return cypher, params, True, 0
            except Exception as e:
                logger.warning(f"Fast path Cypher validation failed: {e}")

        started = time.perf_counter()
        dynamic_few_shot_semantics = get_dynamic_few_shots(scene_id, user_query, top_k=3)
        prompt_text = cypher_prompt.format(schema=graph.schema, question=user_query, few_shot_semantics=dynamic_few_shot_semantics)
        
        messages = [{"role": "user", "content": prompt_text}]
        
        last_error = None
        for attempt in range(max_retries):
            # Pass callbacks down so we can stream tokens
            response = llm.invoke(messages, config={"callbacks": callbacks} if callbacks else None)
            raw = response.content if hasattr(response, "content") else str(response)
            cypher = clean_cypher(raw)
            
            try:
                cypher, params = _validate_and_prepare_cypher(cypher, {})
                
                # Phase 3: Self-validation using Neo4j EXPLAIN to check syntax
                explain_query = "EXPLAIN " + cypher
                try:
                    graph.query(explain_query, params)
                except Exception as explain_e:
                    raise ValueError(f"Neo4j 语法解析错误: {explain_e}")
                    
                return cypher, params, False, int((time.perf_counter() - started) * 1000)
                
            except Exception as e:
                last_error = e
                logger.warning(f"[Cypher 纠错] 第 {attempt + 1} 次生成失败，开始自我反思: {e}")
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"你生成的 Cypher 存在以下错误：\n{e}\n请反思并修复上述错误，重新生成正确的 Cypher。必须返回 ```cypher ... ``` 代码块。"
                })
                
        raise ValueError(f"自我纠错尝试 {max_retries} 次后仍无法生成正确的 Cypher。最后一次错误：{last_error}")

    def query_knowledge_graph(query: str, callbacks: list = None) -> str:
        """查询领域知识图谱。"""
        started = time.perf_counter()
        try:
            route = select_query_routing_rule(
                query,
                query_routing,
                available_classes=display_maps.get("classes", {}).keys(),
            )
            if route:
                delegated = _delegate_query_route(route, query)
                if delegated:
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    logger.info(
                        "[ChatTiming] graph_tool delegated_by_query_route route=%s elapsed_ms=%s",
                        route.get("name") or route.get("function"),
                        elapsed_ms,
                    )
                    return delegated

            cypher_query, params, fast_path, generate_ms = _generate_cypher_with_retry(query, max_retries=3, callbacks=callbacks)
            query_started = time.perf_counter()
            context_rows = graph.query(cypher_query, params)
            query_ms = int((time.perf_counter() - query_started) * 1000)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if context_rows:
                logger.info(
                    "[ChatTiming] graph_tool elapsed_ms=%s generate_ms=%s query_ms=%s rows=%s fast_path=%s",
                    elapsed_ms,
                    generate_ms,
                    query_ms,
                    len(context_rows) if hasattr(context_rows, "__len__") else "?",
                    fast_path,
                )
                alias_labels = _return_alias_labels(cypher_query)
                formatted = _format_rows(context_rows, alias_labels=alias_labels)
                return _result_payload(
                    formatted,
                    rows=context_rows,
                    cypher=cypher_query,
                    row_count=len(context_rows) if hasattr(context_rows, "__len__") else 0,
                    alias_labels=alias_labels,
                    elapsed_ms=query_ms,
                    generate_ms=generate_ms,
                    total_ms=elapsed_ms,
                    fast_path=fast_path,
                )
            logger.info(
                "[ChatTiming] graph_tool elapsed_ms=%s generate_ms=%s query_ms=%s rows=0 fast_path=%s",
                elapsed_ms,
                generate_ms,
                query_ms,
                fast_path,
            )
            return _result_payload(
                "未查询到",
                cypher=cypher_query,
                row_count=0,
                elapsed_ms=query_ms,
                generate_ms=generate_ms,
                total_ms=elapsed_ms,
                fast_path=fast_path,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("[ChatTiming] graph_tool elapsed_ms=%s error=true", elapsed_ms)
            logger.error(f"[图谱查询异常] {e}")
            return f"图谱查询异常: {e}\n请分析报错并重试。"

    return StructuredTool.from_function(
        func=query_knowledge_graph,
        name="Knowledge_Graph_Query",
        description=(
            "查询领域知识图谱。适合明确的结构化查询、统计、跨实体关系、指标和属性问答；"
            "如果当前场景 mapping.yaml 声明了 query_routing，命中规则的问题会按场景契约自动转交对应工具。"
        ),
        return_direct=False,
    )


# =============================================================================
# 模块 6：构建 LangGraph Agent
# =============================================================================
def build_agent(tools, llm, db_path=None):
    """构建 LangGraph ReAct 智能体"""
    if db_path is None:
        db_path = str(settings.project_root / "data" / "chat_sessions.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)

    agent = create_react_agent(
        model=llm, tools=tools, checkpointer=memory, prompt=AGENT_SYSTEM_PROMPT,
    )
    return agent


# =============================================================================
# 主程序入口
# =============================================================================
def main():
    """智能体主入口（CLI 交互模式）"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    logger.info("╔════════════════════════════════════════════════════╗")
    logger.info("║   企业级本体智能体 - 图谱查询排障助手 v3.0         ║")
    logger.info("╚════════════════════════════════════════════════════╝\n")

    graph = connect_neo4j()
    ontology_semantics = get_dynamic_ontology_semantics(graph)
    relationship_semantics = get_relationship_semantics(graph)
    data_property_semantics = get_data_property_semantics(graph)
    ontology_contract_semantics = build_scene_ontology_contract_semantics()

    llm = create_llm()
    logger.info(f"[LLM] 使用模型: {settings.llm_model} (provider: {settings.llm_provider})")

    cypher_prompt = build_cypher_prompt(
        ontology_semantics,
        relationship_semantics,
        data_property_semantics=data_property_semantics,
        ontology_contract_semantics=ontology_contract_semantics,
    )
    graph_tool = build_graph_query_tool(graph, cypher_prompt, llm, display_maps=get_scene_display_maps(graph=graph))
    all_tools = [graph_tool]

    plugin_tools = load_plugins()
    all_tools.extend(plugin_tools)

    logger.info(f"\n[工具注册] 共 {len(all_tools)} 个:")
    for tool in all_tools:
        logger.info(f"  → {tool.name}")

    agent = build_agent(all_tools, llm)

    # Langfuse 集成
    try:
        from langfuse.callback import CallbackHandler
        langfuse_handler = CallbackHandler()
        config = {"configurable": {"thread_id": "it-ops-session-001"}, "callbacks": [langfuse_handler]}
        logger.info("[可观测性] Langfuse 已挂载")
    except Exception:
        config = {"configurable": {"thread_id": "it-ops-session-001"}}

    print("\n" + "=" * 60)
    print("  企业级本体智能分析助手已就绪")
    print("  输入 'quit' 或 'exit' 退出")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("\n🧑 [用户]: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ('quit', 'exit', 'q'):
                print("\n智能体已退出。再见！")
                break

            print("\n🤖 [Agent 思考中...]\n")
            response_text = ""
            for event in agent.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config, stream_mode="values",
            ):
                if "messages" in event:
                    last_msg = event["messages"][-1]
                    if hasattr(last_msg, 'content') and last_msg.content:
                        raw = last_msg.content
                        if isinstance(raw, list):
                            parts = [
                                item.get('text', '') if isinstance(item, dict) else str(item)
                                for item in raw
                                if not isinstance(item, dict) or item.get('type') == 'text'
                            ]
                            response_text = ''.join(parts).strip()
                        else:
                            response_text = raw

            if response_text:
                print(f"\n🤖 [Agent 回复]:\n{response_text}")
            else:
                print("\n🤖 未生成有效回复，请重新描述问题。")

        except KeyboardInterrupt:
            print("\n\n智能体已中断。再见！")
            break
        except Exception as e:
            logger.error(f"Agent 异常: {e}")
            print(f"\n⚠ 出错: {e}\n请重试。")


if __name__ == "__main__":
    main()
