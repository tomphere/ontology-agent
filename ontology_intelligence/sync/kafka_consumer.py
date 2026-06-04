# =============================================================================
# Kafka CDC 实时增量同步服务（重构自 06_kafka_consumer.py）
# =============================================================================
# 复用 sync/engine.py 的核心逻辑，消除重复代码
# =============================================================================

import json
import logging

from ontology_intelligence.config import settings
from ontology_intelligence.security import assert_cypher_identifier, validate_mapping_identifiers
from ontology_intelligence.sync.engine import (
    _get_neo4j_driver, close_neo4j_driver,
    get_embedding, get_superclass_labels, load_mapping_config,
)

logger = logging.getLogger(__name__)


def _scene_uid(scene_id: str, table_name: str, node_id) -> str:
    return f"{scene_id}:{table_name}:{node_id}"


def _sync_relationship_record_to_neo4j(row: dict, table_name: str, mapping: dict, scene_id: str = None, delete: bool = False):
    strategy = mapping.get('entity_class_strategy') or {}
    src_col = strategy.get('source_column')
    tgt_col = strategy.get('target_column')
    src_val = row.get(src_col)
    tgt_val = row.get(tgt_col)
    if src_val is None or tgt_val is None:
        return
    try:
        src_label = assert_cypher_identifier(strategy.get('source_class'), "relationship source class")
        tgt_label = assert_cypher_identifier(strategy.get('target_class'), "relationship target class")
        rel_name = assert_cypher_identifier(strategy.get('ontology_property'), "relationship type")
    except ValueError as e:
        logger.error(f"[CDC] 跳过非法桥接关系标识符: {e}")
        return

    driver = _get_neo4j_driver()
    with driver.session() as session:
        if scene_id:
            match = (
                f"MATCH (s:{src_label} {{id: $src_val, scene_id: $scene_id}}) "
                f"MATCH (t:{tgt_label} {{id: $tgt_val, scene_id: $scene_id}}) "
            )
            params = {"src_val": src_val, "tgt_val": tgt_val, "scene_id": scene_id}
        else:
            match = (
                f"MATCH (s:{src_label} {{id: $src_val}}) "
                f"MATCH (t:{tgt_label} {{id: $tgt_val}}) "
            )
            params = {"src_val": src_val, "tgt_val": tgt_val}
        if delete:
            session.run(match + f"MATCH (s)-[r:{rel_name}]->(t) DELETE r", **params).consume()
        else:
            set_scene = " SET r.scene_id = $scene_id" if scene_id else ""
            session.run(match + f"MERGE (s)-[r:{rel_name}]->(t)" + set_scene, **params).consume()


def sync_record_to_neo4j(row: dict, table_name: str, mapping: dict, scene_id: str = None):
    """复用同步引擎的核心映射逻辑处理单条记录"""
    strategy = mapping['entity_class_strategy']
    if strategy.get('type') == 'relationship':
        _sync_relationship_record_to_neo4j(row, table_name, mapping, scene_id=scene_id)
        return

    driver = _get_neo4j_driver()

    with driver.session() as session:
        if strategy['type'] == 'dynamic_column':
            class_label = row.get(strategy['column'], "Unknown")
        else:
            class_label = strategy['class_name']
        try:
            assert_cypher_identifier(class_label, "entity class label")
        except ValueError as e:
            logger.error(f"[CDC] 跳过非法类名: {e}")
            return

        node_id = row.get(mapping['node_id_column'])
        if node_id is None:
            return

        # 映射属性
        props = {'id': node_id}
        merge_key_name = "id"
        merge_key_value = node_id
        if scene_id:
            merge_key_name = "scene_uid"
            merge_key_value = _scene_uid(scene_id, table_name, node_id)
            props.update({
                "scene_id": scene_id,
                "scene_uid": merge_key_value,
                "source_table": table_name,
                "source_pk": str(node_id),
            })
        for dp in mapping.get('data_properties', []):
            if dp['column'] in row:
                props[dp['ontology_property']] = row[dp['column']]

        # 向量化
        for vf in mapping.get('vectorize_fields', []):
            if row.get(vf):
                emb = get_embedding(row[vf])
                if emb:
                    props[f"{vf}_embedding"] = emb

        # 物化推理
        all_labels = get_superclass_labels(session, class_label)
        valid_labels = []
        for label in all_labels:
            try:
                valid_labels.append(assert_cypher_identifier(label, "inferred class label"))
            except ValueError as e:
                logger.error(f"[CDC] 跳过非法推理类名: {e}")
        if scene_id and "SceneEntity" not in valid_labels:
            valid_labels.append("SceneEntity")
        labels_cypher = ":".join(valid_labels)
        n_labels = f":{labels_cypher}" if labels_cypher else ""

        # 写入节点
        session.run(
            f"MERGE (n{n_labels} {{{merge_key_name}: $merge_key_value}}) SET n += $props",
            merge_key_value=merge_key_value, props=props,
        )

        # 处理关系
        for op in mapping.get('object_properties', []):
            fk_val = row.get(op['foreign_key_column'])
            if not fk_val:
                continue
            try:
                rel_name = assert_cypher_identifier(op['ontology_property'], "relationship type")
                target_lbl = assert_cypher_identifier(op['target_label'], "target label")
            except ValueError as e:
                logger.error(f"[CDC] 跳过非法关系标识符: {e}")
                continue
            if scene_id:
                if op.get('direction') == 'INCOMING':
                    cypher = (
                        f"MATCH (source{n_labels} {{scene_uid: $source_uid}}) "
                        f"MATCH (target:{target_lbl} {{id: $target_id, scene_id: $scene_id}}) "
                        f"MERGE (target)-[r:{rel_name}]->(source) "
                        f"SET r.scene_id = $scene_id"
                    )
                else:
                    cypher = (
                        f"MATCH (source{n_labels} {{scene_uid: $source_uid}}) "
                        f"MATCH (target:{target_lbl} {{id: $target_id, scene_id: $scene_id}}) "
                        f"MERGE (source)-[r:{rel_name}]->(target) "
                        f"SET r.scene_id = $scene_id"
                    )
                session.run(cypher, source_uid=merge_key_value, target_id=fk_val, scene_id=scene_id)
            else:
                if op.get('direction') == 'INCOMING':
                    cypher = (
                        f"MATCH (source{n_labels} {{id: $source_id}}) "
                        f"MERGE (target:{target_lbl} {{id: $target_id}}) "
                        f"MERGE (target)-[:{rel_name}]->(source)"
                    )
                else:
                    cypher = (
                        f"MATCH (source{n_labels} {{id: $source_id}}) "
                        f"MERGE (target:{target_lbl} {{id: $target_id}}) "
                        f"MERGE (source)-[:{rel_name}]->(target)"
                    )
                session.run(cypher, source_id=node_id, target_id=fk_val)


def process_cdc_message(msg_value: str, mappings: list, scene_id: str = None):
    """处理来自 Debezium 的 CDC 消息"""
    try:
        payload = json.loads(msg_value)
        if 'payload' not in payload:
            return
        data_payload = payload['payload']
        if not data_payload or 'op' not in data_payload:
            return

        op = data_payload['op']
        source = data_payload.get('source', {})
        table_name = source.get('table')
        if not table_name:
            return

        mapping = next((m for m in mappings if m['table_name'] == table_name), None)
        if not mapping:
            return

        if op in ('c', 'u', 'r'):
            after_row = data_payload.get('after')
            if after_row:
                node_id_col = mapping.get('node_id_column')
                logger.info(f"[{table_name}] 捕获到 UPSERT 事件，同步 ID: {after_row.get(node_id_col) if node_id_col else 'relationship'}")
                sync_record_to_neo4j(after_row, table_name, mapping, scene_id=scene_id)
        elif op == 'd':
            before_row = data_payload.get('before')
            if before_row:
                if (mapping.get('entity_class_strategy') or {}).get('type') == 'relationship':
                    _sync_relationship_record_to_neo4j(before_row, table_name, mapping, scene_id=scene_id, delete=True)
                    return
                node_id = before_row.get(mapping['node_id_column'])
                logger.info(f"[{table_name}] 捕获到 DELETE 事件，删除 ID: {node_id}")
                driver = _get_neo4j_driver()
                with driver.session() as session:
                    if scene_id:
                        session.run(
                            "MATCH (n {scene_uid: $scene_uid}) DETACH DELETE n",
                            scene_uid=_scene_uid(scene_id, table_name, node_id),
                        )
                    else:
                        session.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)
    except Exception as e:
        logger.error(f"处理消息失败: {e}")


def main():
    """Kafka Consumer 主入口"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    try:
        from confluent_kafka import Consumer, KafkaError, KafkaException
    except ImportError:
        logger.error("confluent-kafka 未安装。请执行: pip install confluent-kafka")
        return

    mappings = load_mapping_config()
    identifier_errors = validate_mapping_identifiers(mappings)
    if identifier_errors:
        logger.error(f"映射标识符校验失败，停止 CDC: {identifier_errors}")
        return
    prefix = "itops.it_ops"
    topics = [f"{prefix}.{m['table_name']}" for m in mappings]
    scene_id = settings.cdc_scene_id

    conf = {
        'bootstrap.servers': settings.kafka_broker,
        'group.id': 'neo4j_sync_consumer_group',
        'auto.offset.reset': 'earliest',
    }

    consumer = Consumer(conf)
    try:
        consumer.subscribe(topics)
        logger.info(f"成功连接 Kafka，正在监听主题: {topics}, scene_id={scene_id or 'global'}")
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    raise KafkaException(msg.error())
            value = msg.value().decode('utf-8')
            process_cdc_message(value, mappings, scene_id=scene_id)
    except KeyboardInterrupt:
        logger.info("程序收到中断信号，退出...")
    finally:
        consumer.close()
        close_neo4j_driver()


if __name__ == "__main__":
    main()
