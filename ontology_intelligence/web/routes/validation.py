# 一致性校验路由
import os
import yaml
import logging
import xml.etree.ElementTree as ET
from fastapi import APIRouter, HTTPException, Depends

from ontology_intelligence.config import settings
from ontology_intelligence.security import quote_mysql_identifier, validate_mapping_identifiers
from ontology_intelligence.web.models import ValidationRequest
from ontology_intelligence.web.routes.auth import verify_token
from ontology_intelligence.web.routes.datasource import _load_datasources, _get_connection

router = APIRouter(tags=["validation"])
logger = logging.getLogger("web-platform")


def _parse_ontology_classes(filepath: str) -> dict:
    """Extract class names, properties from an ontology file (multi-format support via rdflib)."""
    try:
        from ontology_intelligence.ontology.parser import extract_class_names
        return extract_class_names(filepath)
    except Exception as e:
        logger.error(f"Ontology parse failed {filepath}: {e}")
        return {"classes": set(), "object_properties": set(), "data_properties": set()}


def _parse_ontology_details(filepath: str) -> dict:
    """Extract classes plus property domain/range details from ontology."""
    details = {
        "classes": set(),
        "class_parents": {},
        "object_properties": {},
        "data_properties": {},
    }
    try:
        from ontology_intelligence.ontology.parser import parse_ontology
        parsed = parse_ontology(filepath)
        for cls in parsed.get("classes", []):
            name = cls.get("name")
            if name:
                details["classes"].add(name)
                details["class_parents"][name] = set(cls.get("parents") or [])
        for prop in parsed.get("object_properties", []):
            name = prop.get("name")
            if name:
                details["object_properties"][name] = {
                    "domain": prop.get("domain") or "",
                    "range": prop.get("range") or "",
                }
        for prop in parsed.get("data_properties", []):
            name = prop.get("name")
            if name:
                details["data_properties"][name] = {
                    "domains": set(prop.get("domains") or []),
                    "range": prop.get("range") or "",
                }
    except Exception as e:
        logger.error(f"Ontology detail parse failed {filepath}: {e}")
    return details


def _class_matches(actual: str, expected: str, class_parents: dict) -> bool:
    if not actual or not expected:
        return True
    if actual == expected:
        return True
    return expected in class_parents.get(actual, set())


def _run_shacl_validation(filepath: str) -> dict:
    """Run optional SHACL validation when the ontology file contains SHACL shapes."""
    try:
        from rdflib import Graph
        from rdflib.namespace import RDF, SH
        from ontology_intelligence.ontology.parser import detect_format

        fmt = detect_format(filepath)
        graph = Graph()
        graph.parse(filepath, format=fmt)
        has_shapes = any(graph.subjects(RDF.type, SH.NodeShape)) or any(graph.subjects(RDF.type, SH.PropertyShape))
        if not has_shapes:
            return {"status": "skipped", "message": "未发现 SHACL shape"}
    except Exception as e:
        return {"status": "warning", "message": f"SHACL 预检查失败: {e}"}

    try:
        from pyshacl import validate
    except ImportError:
        return {"status": "warning", "message": "未安装 pyshacl，已跳过 SHACL 校验"}

    try:
        conforms, _, report_text = validate(
            data_graph=filepath,
            shacl_graph=filepath,
            inference="rdfs",
            abort_on_first=False,
            meta_shacl=False,
            debug=False,
        )
        if conforms:
            return {"status": "passed", "message": "SHACL 约束校验通过"}
        return {"status": "error", "message": f"SHACL 约束校验失败: {str(report_text)[:2000]}"}
    except Exception as e:
        return {"status": "error", "message": f"SHACL 校验执行失败: {e}"}


def _get_db_tables_and_columns(ds: dict) -> dict:
    """获取数据源的表结构"""
    tables = {}
    try:
        conn = _get_connection(ds)
        ds_type = ds["type"].lower()
        cursor = conn.cursor()

        if ds_type == "mysql":
            cursor.execute("SHOW TABLES")
            table_names = [r[0] for r in cursor.fetchall()]
            for tbl in table_names:
                cursor.execute(f"DESCRIBE {quote_mysql_identifier(tbl, 'table_name')}")
                tables[tbl] = [r[0] for r in cursor.fetchall()]
        elif ds_type == "postgresql":
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            table_names = [r[0] for r in cursor.fetchall()]
            for tbl in table_names:
                cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name=%s", (tbl,))
                tables[tbl] = [r[0] for r in cursor.fetchall()]
        elif ds_type == "oracle":
            cursor.execute("SELECT table_name FROM user_tables")
            table_names = [r[0] for r in cursor.fetchall()]
            for tbl in table_names:
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name=:tn", {"tn": tbl})
                tables[tbl] = [r[0] for r in cursor.fetchall()]
        conn.close()
    except Exception as e:
        logger.error(f"获取表结构失败: {e}")
    return tables


@router.post("/validation/check")
async def run_validation(req: ValidationRequest = None, username: str = Depends(verify_token)):
    """
    执行全量一致性校验：
    1. 本体文件 ↔ 映射配置
    2. 映射配置 ↔ 数据库表
    3. 字段名一致性
    """
    errors = []
    warnings = []
    passed = []

    # 1. 加载映射配置
    mapping_path = settings.mapping_file
    if not os.path.exists(mapping_path):
        errors.append({"category": "映射配置", "message": f"映射配置文件不存在: {mapping_path}"})
        return {"errors": errors, "warnings": warnings, "passed": passed, "summary": "校验中断"}

    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping_config = yaml.safe_load(f)
    if mapping_config is not None and not isinstance(mapping_config, dict):
        errors.append({"category": "映射配置", "message": "映射配置必须是 YAML 对象"})
        return {"errors": errors, "warnings": warnings, "passed": passed, "summary": "校验中断"}
    mapping_config = mapping_config or {}
    mappings = mapping_config.get("mappings", [])
    if not mappings:
        errors.append({"category": "映射配置", "message": "映射配置为空，缺少 mappings 键"})
        return {"errors": errors, "warnings": warnings, "passed": passed, "summary": "校验中断"}
    passed.append({"category": "映射配置", "message": f"已加载 {len(mappings)} 个映射规则"})
    for error in validate_mapping_identifiers(mappings):
        errors.append({"category": "映射配置", "message": error})

    # 2. 加载本体文件
    ontology_dir = settings.ontology_dir
    ontology_info = {"classes": set(), "object_properties": set(), "data_properties": set()}
    ontology_details = {"class_parents": {}, "object_properties": {}, "data_properties": {}}
    if os.path.isdir(ontology_dir):
        for ext in ('*.owl', '*.rdf', '*.ttl'):
            import glob
            for filepath in glob.glob(os.path.join(ontology_dir, ext)):
                info = _parse_ontology_classes(filepath)
                ontology_info["classes"].update(info["classes"])
                ontology_info["object_properties"].update(info["object_properties"])
                ontology_info["data_properties"].update(info["data_properties"])
                details = _parse_ontology_details(filepath)
                ontology_details["class_parents"].update(details["class_parents"])
                ontology_details["object_properties"].update(details["object_properties"])
                ontology_details["data_properties"].update(details["data_properties"])
                shacl_result = _run_shacl_validation(filepath)
                if shacl_result["status"] == "passed":
                    passed.append({"category": "SHACL", "message": f"{os.path.basename(filepath)}: {shacl_result['message']}"})
                elif shacl_result["status"] == "error":
                    errors.append({"category": "SHACL", "message": f"{os.path.basename(filepath)}: {shacl_result['message']}"})
                elif shacl_result["status"] == "warning":
                    warnings.append({"category": "SHACL", "message": f"{os.path.basename(filepath)}: {shacl_result['message']}"})

        if ontology_info["classes"]:
            passed.append({"category": "本体文件", "message": f"发现 {len(ontology_info['classes'])} 个类: {', '.join(sorted(ontology_info['classes']))}"})
        else:
            warnings.append({"category": "本体文件", "message": "未从本体文件中解析出任何类（可能格式不支持或目录为空）"})
    else:
        warnings.append({"category": "本体文件", "message": f"本体目录不存在: {ontology_dir}"})

    # 3. 获取数据库表结构
    db_tables = {}
    ds_found = False
    
    if req and req.datasource_id:
        try:
            from ontology_intelligence.web.routes.datasource import _load_datasources
            all_ds = _load_datasources()
            ds = next((d for d in all_ds if d["id"] == req.datasource_id), None)
            if ds:
                db_tables = _get_db_tables_and_columns(ds)
                ds_found = True
                passed.append({"category": "数据库", "message": f"连接数据源 {ds.get('label', req.datasource_id)} 成功，发现 {len(db_tables)} 张表"})
            else:
                warnings.append({"category": "数据库", "message": f"数据源 {req.datasource_id} 不存在"})
        except Exception as e:
            warnings.append({"category": "数据库", "message": f"连接数据源失败: {str(e)[:100]}，跳过数据库校验"})

    # 优先使用 .env 中的 MySQL 配置作为回退
    if not ds_found:
        try:
            import pymysql
            conn = pymysql.connect(**{**settings.mysql_config, "connect_timeout": 5})
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            table_names = [r[0] for r in cursor.fetchall()]
            for tbl in table_names:
                cursor.execute(f"DESCRIBE {quote_mysql_identifier(tbl, 'table_name')}")
                db_tables[tbl] = [r[0] for r in cursor.fetchall()]
            conn.close()
            passed.append({"category": "数据库", "message": f"连接默认 MySQL 成功，发现 {len(db_tables)} 张表"})
        except Exception as e:
            warnings.append({"category": "数据库", "message": f"默认 MySQL 连接失败: {str(e)[:100]}，跳过数据库校验"})

    # 4. 逐条校验映射规则
    for mapping in mappings:
        table_name = mapping.get("table_name", "未知")
        prefix = f"[{table_name}]"

        # 4.1 检查表是否存在
        if db_tables:
            if table_name in db_tables:
                passed.append({"category": prefix, "message": f"表 {table_name} 在数据库中存在"})
            else:
                errors.append({"category": prefix, "message": f"映射引用的表 '{table_name}' 在数据库中不存在"})
                continue

        # 4.2 检查字段映射
        db_columns = db_tables.get(table_name, [])
        strategy = mapping.get("entity_class_strategy", {})
        for dp in mapping.get("data_properties", []):
            column = dp.get("column", "")
            onto_prop = dp.get("ontology_property", "")

            # 检查 column 是否在数据库表中
            if db_columns and column not in db_columns:
                errors.append({
                    "category": prefix,
                    "message": f"字段映射错误：映射配置引用的列 '{column}' 在表 '{table_name}' 中不存在。"
                               f"数据库实际列: {', '.join(db_columns)}",
                })

            # 检查 ontology_property 是否在本体中
            if ontology_info["data_properties"] and onto_prop not in ontology_info["data_properties"]:
                warnings.append({
                    "category": prefix,
                    "message": f"本体属性 '{onto_prop}' 未在本体文件中找到（映射列 '{column}'）",
                })
            elif strategy.get("type") == "static":
                class_name = strategy.get("class_name", "")
                prop_info = ontology_details["data_properties"].get(onto_prop, {})
                domains = prop_info.get("domains") or set()
                if domains and class_name and not any(
                    _class_matches(class_name, domain, ontology_details["class_parents"])
                    for domain in domains
                ):
                    warnings.append({
                        "category": prefix,
                        "message": f"数据属性 '{onto_prop}' 的 domain {', '.join(sorted(domains))} 与类 '{class_name}' 不匹配",
                    })

        for vf in mapping.get("vectorize_fields", []):
            if db_columns and vf not in db_columns:
                errors.append({
                    "category": prefix,
                    "message": f"向量化字段 '{vf}' 在表 '{table_name}' 中不存在",
                })

        # 4.3 检查 node_id_column
        node_id_col = mapping.get("node_id_column", "")
        if db_columns and node_id_col not in db_columns:
            errors.append({
                "category": prefix,
                "message": f"主键列 '{node_id_col}' 在表 '{table_name}' 中不存在",
            })

        # 4.4 检查类策略
        if strategy.get("type") == "dynamic_column":
            col = strategy.get("column", "")
            if db_columns and col not in db_columns:
                errors.append({
                    "category": prefix,
                    "message": f"动态类策略引用的列 '{col}' 在表 '{table_name}' 中不存在",
                })
        elif strategy.get("type") == "static":
            class_name = strategy.get("class_name", "")
            if ontology_info["classes"] and class_name not in ontology_info["classes"]:
                warnings.append({
                    "category": prefix,
                    "message": f"静态类名 '{class_name}' 未在本体文件中找到",
                })

        # 4.5 检查对象属性
        for op in mapping.get("object_properties", []):
            fk_col = op.get("foreign_key_column", "")
            target_label = op.get("target_label", "")
            onto_prop = op.get("ontology_property", "")

            if db_columns and fk_col not in db_columns:
                errors.append({
                    "category": prefix,
                    "message": f"外键列 '{fk_col}' 在表 '{table_name}' 中不存在",
                })
            if ontology_info["classes"] and target_label not in ontology_info["classes"]:
                warnings.append({
                    "category": prefix,
                    "message": f"关系目标类 '{target_label}' 未在本体文件中找到",
                })
            if ontology_info["object_properties"] and onto_prop not in ontology_info["object_properties"]:
                warnings.append({
                    "category": prefix,
                    "message": f"对象属性 '{onto_prop}' 未在本体文件中找到",
                })
            else:
                rel_info = ontology_details["object_properties"].get(onto_prop, {})
                domain = rel_info.get("domain")
                range_ = rel_info.get("range")
                current_class = strategy.get("class_name", "") if strategy.get("type") == "static" else ""
                if direction := op.get("direction", "OUTGOING"):
                    source_class = target_label if direction == "INCOMING" else current_class
                    dest_class = current_class if direction == "INCOMING" else target_label
                    if domain and source_class and not _class_matches(source_class, domain, ontology_details["class_parents"]):
                        warnings.append({
                            "category": prefix,
                            "message": f"对象属性 '{onto_prop}' 的 domain '{domain}' 与源类 '{source_class}' 不匹配",
                        })
                    if range_ and dest_class and not _class_matches(dest_class, range_, ontology_details["class_parents"]):
                        warnings.append({
                            "category": prefix,
                            "message": f"对象属性 '{onto_prop}' 的 range '{range_}' 与目标类 '{dest_class}' 不匹配",
                        })

    # 5. 汇总
    summary = "通过" if not errors else f"发现 {len(errors)} 个错误"
    if warnings:
        summary += f"，{len(warnings)} 个警告"
    summary += f"，{len(passed)} 项通过"

    return {"errors": errors, "warnings": warnings, "passed": passed, "summary": summary}
