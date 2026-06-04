# =============================================================================
# 同步引擎 - 本体文件同步 + MySQL→Neo4j 数据映射
# =============================================================================
# 重构自 03_sync_engine.py，消除重复代码，使用统一配置和 LLM 工厂
# =============================================================================

import os
import glob
import yaml
import time
import logging
from decimal import Decimal

import pymysql
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from neo4j import GraphDatabase

from ontology_intelligence.config import settings
from ontology_intelligence.security import (
    assert_cypher_identifier,
    cypher_label,
    quote_mysql_identifier,
    validate_mapping_identifiers,
)

logger = logging.getLogger(__name__)

# Neo4j 驱动（懒初始化）
_neo4j_driver = None


def _neo4j_safe_value(value):
    """Convert DB driver values that Neo4j cannot serialize directly."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _neo4j_safe_props(props: dict) -> dict:
    return {key: _neo4j_safe_value(value) for key, value in (props or {}).items()}


def _get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=settings.neo4j_auth
        )
    return _neo4j_driver


def close_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver:
        _neo4j_driver.close()
        _neo4j_driver = None


# =============================================================================
# 模块 1：Neo4j 环境初始化
# =============================================================================
def init_neo4j_environment():
    """初始化 Neo4j 图数据库环境：n10s 配置 + 唯一约束 + 向量索引"""
    logger.info("========== 开始初始化 Neo4j 环境 ==========")
    driver = _get_neo4j_driver()

    with driver.session() as session:
        # 1. 初始化 n10s 配置
        try:
            session.run("""
                CALL n10s.graphconfig.init({
                    handleVocabUris: 'IGNORE',
                    handleMultival: 'ARRAY',
                    handleRDFTypes: 'LABELS'
                })
            """)
            logger.info("[n10s] 语义配置初始化完成")
        except Exception as e:
            logger.warning(f"[n10s] 配置初始化跳过（可能已初始化）: {e}")

        # 2. 创建 n10s 资源唯一约束
        try:
            session.run("""
                CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS
                FOR (r:Resource) REQUIRE r.uri IS UNIQUE
            """)
            logger.info("[约束] n10s 资源 URI 唯一约束已创建")
        except Exception as e:
            logger.warning(f"[约束] 创建跳过: {e}")

        # 3. 创建向量索引
        try:
            dims = settings.llm_embedding_dimensions
            session.run(f"""
                CREATE VECTOR INDEX ticket_vector_index IF NOT EXISTS
                FOR (t:Ticket) ON (t.issue_description_embedding)
                OPTIONS {{indexConfig: {{
                    `vector.dimensions`: {dims},
                    `vector.similarity_function`: 'cosine'
                }}}}
            """)
            logger.info(f"[索引] 工单描述向量索引已创建（{dims}维, cosine）")
            session.run(f"""
                CREATE VECTOR INDEX incident_vector_index IF NOT EXISTS
                FOR (i:Incident) ON (i.detailed_docs_embedding)
                OPTIONS {{indexConfig: {{
                    `vector.dimensions`: {dims},
                    `vector.similarity_function`: 'cosine'
                }}}}
            """)
            logger.info(f"[索引] 事件文本向量索引已创建（{dims}维, cosine）")
        except Exception as e:
            logger.warning(f"[索引] 向量索引创建跳过: {e}")

        # 4. 创建场景实例索引/约束
        try:
            session.run("""
                CREATE CONSTRAINT scene_entity_uid IF NOT EXISTS
                FOR (n:SceneEntity) REQUIRE n.scene_uid IS UNIQUE
            """)
            session.run("""
                CREATE INDEX scene_entity_scene_id IF NOT EXISTS
                FOR (n:SceneEntity) ON (n.scene_id)
            """)
            logger.info("[约束] 场景实例唯一约束与索引已创建")
        except Exception as e:
            logger.warning(f"[约束] 场景实例约束/索引创建跳过: {e}")

    logger.info("========== Neo4j 环境初始化完成 ==========\n")


# =============================================================================
# 模块 2：OWL/RDF 本体文件同步
# =============================================================================
def sync_single_ontology_file(file_path: str):
    """将单个 OWL/RDF 本体文件推送到 Neo4j n10s 插件。"""
    logger.info(f"[本体同步] 正在推送文件: {file_path}")
    driver = _get_neo4j_driver()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            rdf_content = f.read()

        ext = os.path.splitext(file_path)[1].lower()
        format_map = {
            '.rdf': 'RDF/XML', '.owl': 'RDF/XML', '.owx': 'RDF/XML',
            '.ttl': 'Turtle', '.nt': 'N-Triples', '.n3': 'N3',
            '.jsonld': 'JSON-LD',
        }
        rdf_format = format_map.get(ext, 'RDF/XML')

        with driver.session() as session:
            result = session.run(
                "CALL n10s.onto.import.inline($rdf_content, $format)",
                rdf_content=rdf_content, format=rdf_format,
            )
            record = result.single()
            if record:
                stats = {key: record[key] for key in record.keys()}
                logger.info(f"[本体同步] 成功！导入统计: {stats}")
            else:
                logger.info("[本体同步] 完成（无返回统计）")
    except FileNotFoundError:
        logger.error(f"[本体同步] 文件不存在: {file_path}")
    except Exception as e:
        logger.error(f"[本体同步] 异常: {e}")


def sync_all_ontology_files(ontology_dir: str = None):
    """扫描本体工作目录，同步所有本体文件到 Neo4j。"""
    ontology_dir = ontology_dir or settings.ontology_dir
    logger.info(f"[本体同步] 扫描目录: {ontology_dir}")

    if not os.path.exists(ontology_dir):
        logger.warning(f"[本体同步] 目录不存在: {ontology_dir}")
        return

    patterns = ['*.owl', '*.rdf', '*.ttl', '*.n3', '*.nt', '*.jsonld', '*.owx']
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(ontology_dir, pattern)))

    if not files:
        logger.warning(f"[本体同步] 未找到本体文件")
        return

    logger.info(f"[本体同步] 发现 {len(files)} 个本体文件")
    for f in files:
        sync_single_ontology_file(f)


def sync_ontology_model_to_neo4j(model: dict):
    """Materialize an ontology-workbench JSON model into Neo4j metadata nodes.

    Scene-linked ontology models may not have a physical RDF file. The sync engine
    still needs Class/SCO metadata to materialize superclass labels and Relationship
    metadata for agent prompt semantics.
    """
    driver = _get_neo4j_driver()
    classes = model.get("classes", []) or []
    object_properties = model.get("object_properties", []) or []
    data_properties = model.get("data_properties", []) or []

    with driver.session() as session:
        for cls in classes:
            name = cls.get("name")
            if not name:
                continue
            try:
                assert_cypher_identifier(name, "ontology class")
            except ValueError as e:
                logger.warning(f"[本体模型同步] 跳过非法类名 {name!r}: {e}")
                continue
            session.run(
                """
                MERGE (c:Class {name: $name})
                SET c.label = $label,
                    c.comment = $comment,
                    c.source = 'linked_ontology_model'
                """,
                name=name,
                label=cls.get("label") or name,
                comment=cls.get("comment") or "",
            ).consume()
            for parent in cls.get("parents") or []:
                if not parent:
                    continue
                try:
                    assert_cypher_identifier(parent, "ontology parent class")
                except ValueError as e:
                    logger.warning(f"[本体模型同步] 跳过非法父类名 {parent!r}: {e}")
                    continue
                session.run(
                    """
                    MERGE (c:Class {name: $name})
                    MERGE (p:Class {name: $parent})
                    MERGE (c)-[:SCO]->(p)
                    """,
                    name=name,
                    parent=parent,
                ).consume()

        for prop in object_properties:
            name = prop.get("name")
            if not name:
                continue
            try:
                assert_cypher_identifier(name, "ontology object property")
            except ValueError as e:
                logger.warning(f"[本体模型同步] 跳过非法对象属性 {name!r}: {e}")
                continue
            session.run(
                """
                MERGE (r:Relationship {name: $name})
                SET r.label = $label,
                    r.comment = $comment,
                    r.domain = $domain,
                    r.range = $range,
                    r.source = 'linked_ontology_model'
                """,
                name=name,
                label=prop.get("label") or name,
                comment=prop.get("comment") or "",
                domain=prop.get("domain") or "",
                range=prop.get("range") or "",
            ).consume()

        for prop in data_properties:
            name = prop.get("name")
            if not name:
                continue
            try:
                assert_cypher_identifier(name, "ontology data property")
            except ValueError as e:
                logger.warning(f"[本体模型同步] 跳过非法数据属性 {name!r}: {e}")
                continue
            session.run(
                """
                MERGE (p:DataProperty {name: $name})
                SET p.label = $label,
                    p.comment = $comment,
                    p.domains = $domains,
                    p.range = $range,
                    p.source = 'linked_ontology_model'
                """,
                name=name,
                label=prop.get("label") or name,
                comment=prop.get("comment") or "",
                domains=prop.get("domains") or [],
                range=prop.get("range") or "",
            ).consume()

    logger.info(
        f"[本体模型同步] 已同步 linked ontology model: "
        f"classes={len(classes)}, object_properties={len(object_properties)}, data_properties={len(data_properties)}"
    )


class OntologyDirectoryWatchdog(FileSystemEventHandler):
    """本体目录文件监听器，自动热更新。"""
    SUPPORTED_EXTENSIONS = ('.owl', '.rdf', '.ttl', '.n3', '.nt', '.jsonld', '.owx')

    def __init__(self):
        super().__init__()
        self._last_sync_time = {}
        self._debounce_seconds = 3

    def _should_process(self, event):
        if event.is_directory:
            return False
        if not event.src_path.lower().endswith(self.SUPPORTED_EXTENSIONS):
            return False
        current_time = time.time()
        last_time = self._last_sync_time.get(event.src_path, 0)
        if current_time - last_time < self._debounce_seconds:
            return False
        self._last_sync_time[event.src_path] = current_time
        return True

    def on_modified(self, event):
        if self._should_process(event):
            logger.info(f"[Watchdog] 检测到本体文件修改: {os.path.basename(event.src_path)}")
            sync_single_ontology_file(event.src_path)

    def on_created(self, event):
        if self._should_process(event):
            logger.info(f"[Watchdog] 检测到新增本体文件: {os.path.basename(event.src_path)}")
            sync_single_ontology_file(event.src_path)


# =============================================================================
# 模块 3：Embedding 向量生成
# =============================================================================
def get_embedding(text: str):
    """调用统一的 LLM 工厂生成文本向量。"""
    if not text:
        return None
    try:
        from ontology_intelligence.agent.llm_factory import get_embedding_vector
        return get_embedding_vector(text)
    except Exception as e:
        logger.error(f"[向量化] 生成嵌入失败: {e}")
        return None


# =============================================================================
# 模块 4：本体继承关系物化
# =============================================================================
_superclass_cache = {}

def get_superclass_labels(session, class_name: str) -> list:
    """查询 Neo4j 中的本体继承树，获取指定类的所有父类标签。"""
    global _superclass_cache
    if class_name in _superclass_cache:
        return _superclass_cache[class_name]
    try:
        result = session.run("""
            MATCH (c:Class {name: $class_name})-[:SCO*0..]->(parent:Class)
            RETURN collect(DISTINCT parent.name) AS labels
        """, class_name=class_name)
        record = result.single()
        if record and record["labels"]:
            labels = [l for l in record["labels"] if l]
            if labels:
                _superclass_cache[class_name] = labels
                return labels
    except Exception as e:
        logger.debug(f"[物化推理] 查询父类失败: {e}")
    _superclass_cache[class_name] = [class_name]
    return [class_name]


# =============================================================================
# 模块 5：MySQL → Neo4j 数据驱动同步引擎
# =============================================================================
def load_mapping_config(mapping_file: str = None) -> list:
    """加载 YAML 映射配置文件。"""
    mapping_file = mapping_file or settings.mapping_file
    if not os.path.exists(mapping_file):
        logger.error(f"[映射配置] 文件不存在: {mapping_file}")
        return []
    with open(mapping_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict) or 'mappings' not in config:
        logger.error("[映射配置] 配置文件格式错误，缺少 'mappings' 键")
        return []
    logger.info(f"[映射配置] 已加载 {len(config['mappings'])} 个表映射规则")
    return config['mappings']


def sync_mysql_to_neo4j(mysql_config: dict = None, mapping_file: str = None, scene_id: str = None):
    """核心同步函数：基于 YAML 映射配置，将 MySQL 数据动态转换为 Neo4j 图数据。"""
    logger.info("========== 开始 MySQL → Neo4j 数据同步 ==========")
    driver = _get_neo4j_driver()
    summary = {"status": "success", "scene_id": scene_id, "tables": [], "errors": []}

    def record_error(message: str):
        if len(summary["errors"]) < 50:
            summary["errors"].append(message)

    mappings = load_mapping_config(mapping_file)
    if not mappings:
        summary["status"] = "error"
        record_error("未加载到有效映射配置")
        return summary
    identifier_errors = validate_mapping_identifiers(mappings)
    if identifier_errors:
        summary["status"] = "error"
        for error in identifier_errors:
            record_error(error)
        return summary

    mysql_cfg = mysql_config or settings.mysql_config
    try:
        mysql_conn = pymysql.connect(**mysql_cfg)
        cursor = mysql_conn.cursor(pymysql.cursors.DictCursor)
        logger.info(f"[MySQL] 连接成功: {mysql_cfg['host']}:{mysql_cfg['port']}/{mysql_cfg['database']}")
    except Exception as e:
        logger.error(f"[MySQL] 连接失败: {e}")
        summary["status"] = "error"
        record_error(f"MySQL 连接失败: {e}")
        return summary

    with driver.session() as session:
        for mapping in mappings:
            table_name = mapping['table_name']
            logger.info(f"\n----- 同步表: {table_name} -----")

            try:
                cursor.execute(f"SELECT * FROM {quote_mysql_identifier(table_name, 'table_name')}")
                rows = cursor.fetchall()
                logger.info(f"[MySQL] 读取 {len(rows)} 条记录")
            except Exception as e:
                logger.error(f"[MySQL] 读取表 {table_name} 失败: {e}")
                record_error(f"读取表 {table_name} 失败: {e}")
                continue

            node_count = 0
            relation_count = 0
            vector_count = 0

            # 节点数据按 labels_cypher 和 merge_key_name 分组
            nodes_to_create = {}
            # 关系数据按 (src_label, tgt_label, rel_type) 分组
            rels_to_create = {}
            # 对象属性关系按 (base_label, target_label, rel_type, direction) 分组
            obj_rels_to_create = {}
            
            import concurrent.futures
            
            def process_row(row):
                result = {"type": None}
                strategy = mapping['entity_class_strategy']
                if strategy['type'] == 'relationship':
                    src_col = strategy.get('source_column')
                    src_cls = strategy.get('source_class')
                    tgt_col = strategy.get('target_column')
                    tgt_cls = strategy.get('target_class')
                    rel_name = strategy.get('ontology_property')
                    
                    try:
                        src_label = cypher_label(src_cls, "relationship source class")
                        tgt_label = cypher_label(tgt_cls, "relationship target class")
                        rel_type = assert_cypher_identifier(rel_name, "relationship type")
                    except Exception as e:
                        return {"type": "error", "error": f"关系映射标识符非法: {e}"}

                    src_val = row.get(src_col)
                    tgt_val = row.get(tgt_col)
                    if not src_val or not tgt_val or not rel_name:
                        return {"type": "skip"}

                    rel_props = {
                        "scene_id": scene_id,
                        "source_table": table_name,
                    } if scene_id else {"source_table": table_name}
                    
                    for rp in mapping.get("relationship_properties", []):
                        column = rp.get("column")
                        prop_name = rp.get("property") or rp.get("ontology_property")
                        if column in row and prop_name:
                            rel_props[prop_name] = _neo4j_safe_value(row.get(column))
                    
                    rel_key = (src_label, tgt_label, rel_type)
                    return {"type": "rel", "key": rel_key, "src_val": src_val, "tgt_val": tgt_val, "props": rel_props}
                    
                # 节点实体
                if strategy['type'] == 'dynamic_column':
                    base_label = row.get(strategy['column'], 'Unknown')
                elif strategy['type'] == 'static':
                    base_label = strategy['class_name']
                else:
                    return {"type": "skip"}
                    
                try:
                    assert_cypher_identifier(base_label, "entity class label")
                except Exception as e:
                    return {"type": "error", "error": f"动态/静态类名非法: {e}"}

                node_id = row.get(mapping['node_id_column'])
                if node_id is None:
                    return {"type": "error", "error": f"记录缺少主键列 {mapping['node_id_column']}"}

                props = {'id': node_id, 'ontology_class': base_label}
                merge_key_name = "id"
                merge_key_value = node_id
                if scene_id:
                    merge_key_name = "scene_uid"
                    merge_key_value = f"{scene_id}:{table_name}:{node_id}"
                    props.update({
                        "scene_id": scene_id,
                        "scene_uid": merge_key_value,
                        "source_table": table_name,
                        "source_pk": str(node_id),
                    })
                    
                for dp in mapping.get('data_properties', []):
                    column_name = dp['column']
                    onto_prop = dp['ontology_property']
                    if column_name in row:
                        props[onto_prop] = _neo4j_safe_value(row[column_name])

                local_vector_count = 0
                for vf in mapping.get('vectorize_fields', []):
                    text_value = row.get(vf)
                    if text_value:
                        embedding = get_embedding(str(text_value))
                        if embedding:
                            props[f"{vf}_embedding"] = embedding
                            local_vector_count += 1

                # 推理不需要多线程环境里再查数据库，如果没缓存，由于缓存已经提前填充，这里会很快
                all_labels = get_superclass_labels(session, base_label) if base_label else []
                valid_labels = []
                for label in all_labels:
                    if not label: continue
                    try:
                        valid_labels.append(assert_cypher_identifier(label, "inferred class label"))
                    except Exception as e:
                        pass
                if scene_id and "SceneEntity" not in valid_labels:
                    valid_labels.append("SceneEntity")
                labels_cypher = ":".join(valid_labels)
                
                node_res = {
                    "type": "node", 
                    "key": (labels_cypher, merge_key_name), 
                    "merge_key_value": merge_key_value, 
                    "props": props,
                    "vector_count": local_vector_count
                }
                
                obj_rels = []
                for op in mapping.get('object_properties', []):
                    fk_column = op['foreign_key_column']
                    fk_value = row.get(fk_column)
                    if not fk_value: continue
                    target_label = op['target_label']
                    rel_name = op['ontology_property']
                    direction = op.get('direction', 'OUTGOING')
                    try:
                        target_label_cypher = cypher_label(target_label, "target label")
                        base_label_cypher = cypher_label(base_label, "source label")
                        rel_type = assert_cypher_identifier(rel_name, "relationship type")
                        obj_rels.append({
                            "key": (base_label_cypher, target_label_cypher, rel_type, direction),
                            "node_id": node_id,
                            "fk_val": fk_value,
                            "scene_uid": merge_key_value
                        })
                    except Exception:
                        pass
                        
                node_res["obj_rels"] = obj_rels
                return node_res

            # 并发执行数据转换和 Embedding 生成
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(process_row, rows))
                
            for res in results:
                if res["type"] == "error":
                    record_error(f"表 {table_name} 错误: {res['error']}")
                elif res["type"] == "rel":
                    rels_to_create.setdefault(res["key"], []).append({
                        "src_val": res["src_val"], "tgt_val": res["tgt_val"], "props": res["props"]
                    })
                elif res["type"] == "node":
                    nodes_to_create.setdefault(res["key"], []).append({
                        "merge_key_value": res["merge_key_value"], "props": _neo4j_safe_props(res["props"])
                    })
                    vector_count += res["vector_count"]
                    for orel in res.get("obj_rels", []):
                        obj_rels_to_create.setdefault(orel["key"], []).append({
                            "node_id": orel["node_id"], "fk_val": orel["fk_val"], "scene_uid": orel["scene_uid"]
                        })

            # 执行批量写入
            for (src_label, tgt_label, rel_type), batch in rels_to_create.items():
                if scene_id:
                    cypher = (
                        f"UNWIND $batch AS item "
                        f"MATCH (s{src_label} {{id: item.src_val, scene_id: $scene_id}}) "
                        f"MATCH (t{tgt_label} {{id: item.tgt_val, scene_id: $scene_id}}) "
                        f"MERGE (s)-[r:{rel_type}]->(t) "
                        f"SET r += item.props"
                    )
                else:
                    cypher = (
                        f"UNWIND $batch AS item "
                        f"MATCH (s{src_label} {{id: item.src_val}}) "
                        f"MATCH (t{tgt_label} {{id: item.tgt_val}}) "
                        f"MERGE (s)-[r:{rel_type}]->(t) "
                        f"SET r += item.props"
                    )
                try:
                    session.run(cypher, batch=batch, scene_id=scene_id)
                    relation_count += len(batch)
                except Exception as e:
                    logger.error(f"[Neo4j] 批量建立桥接关系失败: {e}")
                    record_error(f"表 {table_name} 批量建立桥接关系失败: {e}")
                    
            for (labels_cypher, merge_key_name), batch in nodes_to_create.items():
                n_labels = f":{labels_cypher}" if labels_cypher else ""
                cypher = (
                    f"UNWIND $batch AS item "
                    f"MERGE (n{n_labels} {{{merge_key_name}: item.merge_key_value}}) "
                    f"SET n += item.props"
                )
                try:
                    session.run(cypher, batch=batch)
                    node_count += len(batch)
                except Exception as e:
                    logger.error(f"[Neo4j] 批量写入节点失败: {e}")
                    record_error(f"表 {table_name} 批量写入节点失败: {e}")
                    
            for (base_label_cypher, target_label_cypher, rel_type, direction), batch in obj_rels_to_create.items():
                if scene_id:
                    if direction == 'INCOMING':
                        cypher = (
                            f"UNWIND $batch AS item "
                            f"MATCH (current{base_label_cypher} {{scene_uid: item.scene_uid}}) "
                            f"OPTIONAL MATCH (t1{target_label_cypher} {{id: item.fk_val, scene_id: $scene_id}}) "
                            f"WITH current, item, t1 "
                            f"OPTIONAL MATCH (t2 {{id: item.fk_val, scene_id: $scene_id}}) WHERE t1 IS NULL "
                            f"WITH current, item, COALESCE(t1, t2) AS target "
                            f"WHERE target IS NOT NULL "
                            f"MERGE (target)-[r:{rel_type}]->(current) "
                            f"SET r.scene_id = $scene_id"
                        )
                    else:
                        cypher = (
                            f"UNWIND $batch AS item "
                            f"MATCH (current{base_label_cypher} {{scene_uid: item.scene_uid}}) "
                            f"OPTIONAL MATCH (t1{target_label_cypher} {{id: item.fk_val, scene_id: $scene_id}}) "
                            f"WITH current, item, t1 "
                            f"OPTIONAL MATCH (t2 {{id: item.fk_val, scene_id: $scene_id}}) WHERE t1 IS NULL "
                            f"WITH current, item, COALESCE(t1, t2) AS target "
                            f"WHERE target IS NOT NULL "
                            f"MERGE (current)-[r:{rel_type}]->(target) "
                            f"SET r.scene_id = $scene_id"
                        )
                else:
                    if direction == 'INCOMING':
                        cypher = (
                            f"UNWIND $batch AS item "
                            f"MATCH (current{base_label_cypher} {{id: item.node_id}}) "
                            f"OPTIONAL MATCH (t1{target_label_cypher} {{id: item.fk_val}}) "
                            f"WITH current, item, t1 "
                            f"OPTIONAL MATCH (t2 {{id: item.fk_val}}) WHERE t1 IS NULL "
                            f"WITH current, COALESCE(t1, t2) AS target "
                            f"WHERE target IS NOT NULL "
                            f"MERGE (target)-[:{rel_type}]->(current)"
                        )
                    else:
                        cypher = (
                            f"UNWIND $batch AS item "
                            f"MATCH (current{base_label_cypher} {{id: item.node_id}}) "
                            f"OPTIONAL MATCH (t1{target_label_cypher} {{id: item.fk_val}}) "
                            f"WITH current, item, t1 "
                            f"OPTIONAL MATCH (t2 {{id: item.fk_val}}) WHERE t1 IS NULL "
                            f"WITH current, COALESCE(t1, t2) AS target "
                            f"WHERE target IS NOT NULL "
                            f"MERGE (current)-[:{rel_type}]->(target)"
                        )
                try:
                    session.run(cypher, batch=batch, scene_id=scene_id)
                    relation_count += len(batch)
                except Exception as e:
                    logger.error(f"[Neo4j] 批量建立对象关系失败: {e}")
                    record_error(f"表 {table_name} 批量建立对象关系失败: {e}")

            logger.info(
                f"[同步完成] 表 {table_name}: "
                f"节点 {node_count} 个, 关系 {relation_count} 条, 向量 {vector_count} 个"
            )
            summary["tables"].append({
                "table": table_name,
                "nodes": node_count,
                "relationships": relation_count,
                "vectors": vector_count,
            })

    mysql_conn.close()
    if summary["errors"]:
        summary["status"] = "error"
    logger.info("========== MySQL → Neo4j 数据同步完成 ==========\n")
    return summary


def purge_scene_graph(scene_id: str) -> dict:
    """Delete all Neo4j business data written into a scene namespace."""
    if not scene_id:
        raise ValueError("scene_id is required")

    logger.info(f"[场景清理] 开始清理 scene_id={scene_id}")
    driver = _get_neo4j_driver()
    with driver.session() as session:
        rel_count = session.run("""
            MATCH ()-[r]-()
            WHERE r.scene_id = $scene_id
            RETURN count(r) AS count
        """, scene_id=scene_id).single()["count"]
        session.run("""
            MATCH ()-[r]-()
            WHERE r.scene_id = $scene_id
            DELETE r
        """, scene_id=scene_id).consume()

        node_count = session.run("""
            MATCH (n)
            WHERE n.scene_id = $scene_id
            RETURN count(n) AS count
        """, scene_id=scene_id).single()["count"]
        session.run("""
            MATCH (n)
            WHERE n.scene_id = $scene_id
            DETACH DELETE n
        """, scene_id=scene_id).consume()

    logger.info(f"[场景清理] 完成 scene_id={scene_id}: nodes={node_count}, relationships={rel_count}")
    return {"scene_id": scene_id, "nodes_deleted": node_count, "relationships_deleted": rel_count}


def _scene_graph_counts(session, scene_id: str) -> dict:
    node_count = session.run("""
        MATCH (n)
        WHERE n.scene_id = $scene_id
        RETURN count(n) AS count
    """, scene_id=scene_id).single()["count"]
    relationship_count = session.run("""
        MATCH ()-[r]->()
        WHERE r.scene_id = $scene_id
        RETURN count(r) AS count
    """, scene_id=scene_id).single()["count"]
    return {"nodes": node_count, "relationships": relationship_count}


def adopt_global_graph_into_scene(scene_id: str, mapping_file: str = None, dry_run: bool = True) -> dict:
    """Attach existing global business nodes to a scene namespace using mapping labels."""
    if not scene_id:
        raise ValueError("scene_id is required")

    mappings = load_mapping_config(mapping_file)
    identifier_errors = validate_mapping_identifiers(mappings)
    if identifier_errors:
        return {"status": "error", "scene_id": scene_id, "dry_run": dry_run, "errors": identifier_errors}

    summary = {
        "status": "success",
        "scene_id": scene_id,
        "dry_run": dry_run,
        "before": {},
        "after": {},
        "tables": [],
        "planned_nodes": 0,
        "adopted_nodes": 0,
        "relationships": 0,
        "dynamic_mappings_skipped": 0,
        "conflicts": [],
        "errors": [],
    }
    driver = _get_neo4j_driver()
    with driver.session() as session:
        summary["before"] = _scene_graph_counts(session, scene_id)
        for mapping in mappings:
            strategy = mapping.get("entity_class_strategy") or {}
            if strategy.get("type") != "static":
                summary["dynamic_mappings_skipped"] += 1
                continue
            table_name = mapping.get("table_name")
            class_name = strategy.get("class_name")
            try:
                label = assert_cypher_identifier(class_name, "entity class label")
            except ValueError as e:
                summary["errors"].append(str(e))
                continue

            count_query = (
                f"MATCH (n:{label}) "
                "WHERE n.scene_id IS NULL AND n.id IS NOT NULL "
                "RETURN count(n) AS count"
            )
            count = session.run(count_query).single()["count"]
            conflict_count = session.run(
                f"MATCH (n:{label}) "
                "WHERE n.scene_id IS NULL AND n.id IS NOT NULL "
                "WITH $scene_id + ':' + $table_name + ':' + toString(n.id) AS uid "
                "MATCH (existing) "
                "WHERE existing.scene_uid = uid "
                "RETURN count(existing) AS count",
                scene_id=scene_id,
                table_name=table_name,
            ).single()["count"]
            summary["planned_nodes"] += count
            if conflict_count:
                summary["conflicts"].append({
                    "table": table_name,
                    "class": class_name,
                    "conflicting_scene_uid_count": conflict_count,
                })
            if not dry_run and count:
                session.run(
                    f"MATCH (n:{label}) "
                    "WHERE n.scene_id IS NULL AND n.id IS NOT NULL "
                    "WITH n, $scene_id + ':' + $table_name + ':' + toString(n.id) AS uid "
                    "WHERE NOT EXISTS { MATCH (existing) WHERE existing.scene_uid = uid } "
                    "SET n:SceneEntity, "
                    "n.scene_id = $scene_id, "
                    "n.scene_uid = uid, "
                    "n.source_table = $table_name, "
                    "n.source_pk = toString(n.id)",
                    scene_id=scene_id,
                    table_name=table_name,
                ).consume()
                adopted_count = count - conflict_count
            else:
                adopted_count = 0
            summary["adopted_nodes"] += max(adopted_count, 0)
            summary["tables"].append({
                "table": table_name,
                "class": class_name,
                "planned_nodes": count,
                "adopted_nodes": max(adopted_count, 0),
                "conflicts": conflict_count,
            })

        relationship_count = session.run("""
            MATCH (a)-[r]->(b)
            WHERE a.scene_id = $scene_id AND b.scene_id = $scene_id AND r.scene_id IS NULL
            RETURN count(r) AS count
        """, scene_id=scene_id).single()["count"]
        if not dry_run and relationship_count:
            session.run("""
                MATCH (a)-[r]->(b)
                WHERE a.scene_id = $scene_id AND b.scene_id = $scene_id AND r.scene_id IS NULL
                SET r.scene_id = $scene_id
            """, scene_id=scene_id).consume()
        summary["relationships"] = relationship_count
        summary["after"] = _scene_graph_counts(session, scene_id)

    if summary["errors"]:
        summary["status"] = "error"
    elif summary["conflicts"]:
        summary["status"] = "warning"
    return summary


# =============================================================================
# 主程序入口
# =============================================================================
def main():
    """同步引擎主入口：初始化 -> 全量同步 -> 文件监听"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    logger.info("╔════════════════════════════════════════════════╗")
    logger.info("║   企业级本体智能体 - 全自动同步引擎 v3.0      ║")
    logger.info("╚════════════════════════════════════════════════╝\n")

    init_neo4j_environment()
    sync_all_ontology_files()
    sync_mysql_to_neo4j()

    ontology_dir = settings.ontology_dir
    if os.path.exists(ontology_dir):
        observer = Observer()
        watchdog_handler = OntologyDirectoryWatchdog()
        observer.schedule(watchdog_handler, path=ontology_dir, recursive=False)
        observer.start()
        logger.info(f"[Watchdog] 正在监听本体目录: {ontology_dir}")
        logger.info("[提示] 按 Ctrl+C 停止同步引擎\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n[Watchdog] 正在优雅关闭文件监听...")
            observer.stop()
            observer.join()
    else:
        logger.warning(f"[Watchdog] 目录不存在，跳过文件监听: {ontology_dir}")

    close_neo4j_driver()
    logger.info("同步引擎已停止。")


if __name__ == "__main__":
    main()
