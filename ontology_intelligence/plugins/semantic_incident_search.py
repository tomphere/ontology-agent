"""Scene-aware hybrid semantic and graph search for event text."""

import json

try:
    from langchain_core.tools import StructuredTool
except ImportError:
    from langchain.agents import Tool as StructuredTool

try:
    from neo4j import GraphDatabase
    _NEO4J_AVAILABLE = True
except ImportError:
    _NEO4J_AVAILABLE = False

from ontology_intelligence.agent.llm_factory import get_embedding_vector
from ontology_intelligence.config import settings


SCENE_AGNOSTIC = True


def _query_embedding(text: str):
    try:
        return get_embedding_vector(text)
    except Exception:
        return None


def _scene_props(scene_id: str = None) -> str:
    return "{scene_id: $scene_id}" if scene_id else ""


def _clean_persons(persons):
    cleaned = []
    seen = set()
    for person in persons or []:
        if not person or not person.get("name"):
            continue
        key = person.get("id") or person.get("name")
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(person)
    return cleaned


def _format_graph_evidence(enrichment: dict) -> str:
    evidence = []
    grid = enrichment.get("grid")
    police_unit = enrichment.get("police_unit")
    if grid or police_unit:
        evidence.append("辖区:" + " / ".join(str(x) for x in [grid, police_unit] if x))
    calls = enrichment.get("calls") or []
    if calls:
        call = calls[0]
        bits = [call.get("peer"), call.get("time")]
        if call.get("duration_s") not in (None, ""):
            bits.append(f"{call.get('duration_s')}秒")
        evidence.append("通联:" + " / ".join(str(x) for x in bits if x))
    transfers = enrichment.get("transfers") or []
    if transfers:
        transfer = transfers[0]
        bits = [transfer.get("peer"), transfer.get("time")]
        if transfer.get("amount") not in (None, ""):
            bits.append(f"{transfer.get('amount')}元")
        evidence.append("资金:" + " / ".join(str(x) for x in bits if x))
    return "；".join(evidence)


def _build_payload(query: str, records, enrichment_by_person: dict, scene_id: str = None) -> str:
    lines = [
        f"【语义检索 + 本体图谱补证】与“{query}”相关的线索如下，先按长文本相似度召回，再沿本体关系补充实体、风险和关联证据："
    ]
    rows = []
    for idx, rec in enumerate(records, 1):
        labels = [x for x in rec.get("incident_labels", []) if x not in {"SceneEntity", "Thing"}]
        persons = _clean_persons(rec.get("persons") or [])
        person_bits = []
        graph_evidence_bits = []
        for person in persons:
            enrichment = enrichment_by_person.get(person.get("id")) or {}
            bits = [person.get("name")]
            if person.get("id"):
                bits.append(person.get("id"))
            if person.get("role"):
                bits.append(f"角色:{person.get('role')}")
            risk = person.get("riskLevel") or enrichment.get("riskLevel")
            score = person.get("riskScore") or enrichment.get("riskScore")
            if risk:
                bits.append(f"风险:{risk}")
            if score not in (None, ""):
                bits.append(f"分值:{score}")
            person_bits.append(" / ".join(str(x) for x in bits if x))
            graph_evidence = _format_graph_evidence(enrichment)
            if graph_evidence:
                graph_evidence_bits.append(f"{person.get('name')}: {graph_evidence}")

        incident_type = "/".join(labels) or rec.get("ontology_class") or "Incident"
        details = rec.get("details") or "无详情"
        lines.append(
            f"{idx}. 线索 {rec.get('incident_id')}（类型:{incident_type}，相似度:{rec.get('similarity')}）\n"
            f"   时间:{rec.get('event_time') or '未知'}\n"
            f"   内容:{details}\n"
            f"   关联实体:{'；'.join(person_bits) if person_bits else '无明确关联实体'}"
        )
        if graph_evidence_bits:
            lines.append(f"   图谱补证:{'；'.join(graph_evidence_bits)}")

        rows.append({
            "线索编号": rec.get("incident_id"),
            "线索类型": incident_type,
            "相似度": rec.get("similarity"),
            "发生时间": rec.get("event_time"),
            "线索内容": details,
            "关联实体": "；".join(person_bits),
            "图谱补证": "；".join(graph_evidence_bits),
        })

    payload = {
        "__oi_result__": True,
        "content": "\n".join(lines),
        "artifact": {
            "type": "table",
            "columns": ["线索编号", "线索类型", "相似度", "发生时间", "线索内容", "关联实体", "图谱补证"],
            "rows": rows,
            "chartable": False,
            "numeric_columns": ["相似度"],
        },
        "evidence": {
            "tool": "Semantic_Incident_Search",
            "mode": "semantic_vector_recall_then_ontology_graph_enrichment",
            "vector_index": "incident_vector_index",
            "scene_id": scene_id,
            "row_count": len(rows),
        },
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def semantic_incident_search(query: str, scene_id: str = None) -> str:
    """Search vectorized incident text, then enrich matches through ontology graph paths."""
    if not _NEO4J_AVAILABLE:
        return "【工具不可用】neo4j 驱动未安装。"

    embedding = _query_embedding(query)
    if embedding is None:
        return "【向量化失败】无法将问题转为向量，请检查 LLM_EMBEDDING_* 配置。"

    scene_filter = "WHERE inc.scene_id = $scene_id" if scene_id else ""
    person_scene = _scene_props(scene_id)
    rel_scene = _scene_props(scene_id)
    cypher = f"""
    CALL db.index.vector.queryNodes('incident_vector_index', 10, $embedding)
    YIELD node AS inc, score
    {scene_filter}
    OPTIONAL MATCH (p:Person {person_scene})-[rel:involvedIn {rel_scene}]->(inc)
    RETURN
        inc.id AS incident_id,
        labels(inc) AS incident_labels,
        inc.ontology_class AS ontology_class,
        inc.eventTime AS event_time,
        inc.incidentDetails AS details,
        inc.scene_id AS scene_id,
        collect(DISTINCT {{
            name: p.hasName,
            id: p.id,
            riskLevel: p.riskLevel,
            riskScore: p.riskScore,
            role: rel.role
        }}) AS persons,
        round(score * 1000) / 1000.0 AS similarity
    ORDER BY similarity DESC
    LIMIT 5
    """

    try:
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        with driver.session() as session:
            records = list(session.run(cypher, embedding=embedding, scene_id=scene_id))
            person_ids = sorted({
                person.get("id")
                for rec in records
                for person in (rec.get("persons") or [])
                if person and person.get("id")
            })
            enrichment_by_person = {}
            if person_ids:
                scoped_person = _scene_props(scene_id)
                scoped_grid = _scene_props(scene_id)
                scoped_unit = _scene_props(scene_id)
                enrichment_cypher = f"""
                MATCH (p:Person {scoped_person})
                WHERE p.id IN $person_ids
                OPTIONAL MATCH (p)-[:belongsToGrid]->(grid:CommunityGrid {scoped_grid})
                OPTIONAL MATCH (grid)-[:managedBy]->(unit:PoliceUnit {scoped_unit})
                CALL {{
                    WITH p
                    OPTIONAL MATCH (p)-[:ownsAsset]->(phone:Phone)-[call:called]-(peerPhone:Phone)<-[:ownsAsset]-(peer:Person)
                    WHERE peer.id <> p.id
                    RETURN collect(DISTINCT {{
                        peer: peer.hasName,
                        peerId: peer.id,
                        time: call.eventTime,
                        duration_s: call.duration_s
                    }})[..3] AS calls
                }}
                CALL {{
                    WITH p
                    OPTIONAL MATCH (p)-[:ownsAsset]->(acct:BankAcct)-[transfer:transferTo]-(peerAcct:BankAcct)<-[:ownsAsset]-(peer:Person)
                    WHERE peer.id <> p.id
                    RETURN collect(DISTINCT {{
                        peer: peer.hasName,
                        peerId: peer.id,
                        time: transfer.eventTime,
                        amount: transfer.amount
                    }})[..3] AS transfers
                }}
                RETURN
                    p.id AS person_id,
                    p.hasName AS name,
                    p.riskLevel AS riskLevel,
                    p.riskScore AS riskScore,
                    grid.name AS grid,
                    unit.name AS police_unit,
                    calls,
                    transfers
                """
                enrichment_records = list(session.run(enrichment_cypher, person_ids=person_ids, scene_id=scene_id))
                for rec in enrichment_records:
                    if rec.get("person_id"):
                        enrichment_by_person[rec.get("person_id")] = dict(rec)
        driver.close()
    except Exception as e:
        return f"【向量搜索执行失败】{e}\n提示：请确认 incident_vector_index 已创建，且 Incident 节点包含 detailed_docs_embedding。"

    if not records:
        return "未在案事件向量索引中找到相关线索。"
    return _build_payload(query, records, enrichment_by_person, scene_id=scene_id)


def get_tool(scene_id: str = None):
    def _scoped_search(query: str) -> str:
        return semantic_incident_search(query, scene_id=scene_id)

    scope = f"\n当前工具已限制在场景 scene_id={scene_id}。" if scene_id else ""
    return StructuredTool.from_function(
        func=_scoped_search,
        name="Semantic_Incident_Search",
        description=(
            "【事件文本语义检索工具】当用户用自然语言描述事件、线索、告警、报告、"
            "工单备注等非结构化内容时优先调用。"
            "工具会先检索 Incident/Alert/Ticket/Report 的长文本向量，再沿本体关系补充关联实体、"
            "角色、风险、区域和关系证据，适合需要“语义召回 + 图谱解释”的线索排查。"
            f"{scope}"
        ),
    )
