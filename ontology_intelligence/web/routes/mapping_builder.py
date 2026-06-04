# =============================================================================
# Mapping Builder Helper Routes
# =============================================================================
# Provides backend support for the visual mapping configurator:
# - Builder data (DB tables + ontology classes/properties)
# - Visual config to YAML conversion
# - Auto-suggest mapping based on name similarity
# =============================================================================

import os
import yaml
import logging
from difflib import SequenceMatcher
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from ontology_intelligence.security import quote_mysql_identifier, validate_mapping_identifiers
from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.web.audit import audit_event
from ontology_intelligence.web import scene_store

router = APIRouter(tags=["mapping-builder"])
logger = logging.getLogger("web-platform")


# ---- Request Models ----

class FieldMapping(BaseModel):
    column: str
    ontologyProperty: str

class ObjectPropertyMapping(BaseModel):
    foreignKeyColumn: str
    targetLabel: str
    ontologyProperty: str
    direction: str = 'OUTGOING'

class TableMappingConfig(BaseModel):
    table: str
    ontologyClass: str = ''
    primaryKey: str = ''
    classStrategy: str = 'static'
    classStrategyColumn: str = ''
    fieldMappings: List[FieldMapping] = []
    objectProperties: List[ObjectPropertyMapping] = []
    vectorizeFields: List[str] = []

class VisualMappingRequest(BaseModel):
    mappings: List[TableMappingConfig]


# ---- Routes ----

def _load_scene_ontology(scene_id: str) -> Optional[dict]:
    """Load ontology data from an uploaded file or a linked ontology-workbench model."""
    linked_model = scene_store.get_linked_ontology_model(scene_id)
    if linked_model:
        return scene_store.normalize_ontology_model(linked_model)

    ontology_path = scene_store.get_scene_ontology_path(scene_id)
    if ontology_path:
        from ontology_intelligence.ontology.parser import parse_ontology
        return parse_ontology(ontology_path)

    return None

@router.get("/scene/{scene_id}/mapping/builder-data")
async def get_builder_data(scene_id: str, username: str = Depends(verify_token)):
    """
    Get initialization data for the visual mapping builder:
    - List of tables and columns from associated datasources
    - List of classes and properties from the scene's ontology file
    """
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # 1. Get ontology data
    ontology = None
    try:
        ontology = _load_scene_ontology(scene_id)
    except Exception as e:
        logger.error(f"[Builder] Ontology load failed: {e}")

    # 2. Get datasource table structure
    datasource_tables = {}
    ds_ids = scene.get('datasource_ids', [])
    if ds_ids:
        try:
            from ontology_intelligence.web.routes.datasource import _load_datasources, _get_connection
            all_ds = _load_datasources()
            for ds in all_ds:
                if ds['id'] in ds_ids:
                    try:
                        conn = _get_connection(ds)
                        cursor = conn.cursor()
                        tables_info = {}

                        ds_type = ds['type'].lower()
                        if ds_type == 'mysql':
                            cursor.execute("SHOW TABLES")
                            table_names = [r[0] for r in cursor.fetchall()]
                            for tbl in table_names:
                                cursor.execute(f"DESCRIBE {quote_mysql_identifier(tbl, 'table_name')}")
                                tables_info[tbl] = [
                                    {"name": r[0], "type": r[1], "nullable": r[2] == 'YES', "key": r[3] or ''}
                                    for r in cursor.fetchall()
                                ]
                        elif ds_type == 'postgresql':
                            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                            table_names = [r[0] for r in cursor.fetchall()]
                            for tbl in table_names:
                                cursor.execute("""
                                    SELECT column_name, data_type, is_nullable, ''
                                    FROM information_schema.columns WHERE table_name=%s
                                """, (tbl,))
                                tables_info[tbl] = [
                                    {"name": r[0], "type": r[1], "nullable": r[2] == 'YES', "key": ''}
                                    for r in cursor.fetchall()
                                ]

                        conn.close()
                        datasource_tables[ds['id']] = {
                            "label": ds.get('label', ds['database']),
                            "type": ds['type'],
                            "tables": tables_info,
                        }
                    except Exception as e:
                        logger.error(f"[Builder] Failed to load tables from {ds['id']}: {e}")
        except Exception as e:
            logger.error(f"[Builder] Failed to load datasources: {e}")

    return {
        "ontology": ontology,
        "datasources": datasource_tables,
    }


@router.post("/scene/{scene_id}/mapping/from-visual")
async def save_mapping_from_visual(
    scene_id: str,
    req: VisualMappingRequest,
    username: str = Depends(require_admin),
):
    """Convert visual mapping configuration to YAML and save."""
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Build YAML structure
    yaml_mappings = []
    for m in req.mappings:
        if not m.ontologyClass and not m.fieldMappings:
            continue

        entry = {
            "table_name": m.table,
            "node_id_column": m.primaryKey or "id",
        }

        if m.classStrategy == 'dynamic' and m.classStrategyColumn:
            entry["entity_class_strategy"] = {
                "type": "dynamic_column",
                "column": m.classStrategyColumn,
            }
        else:
            entry["entity_class_strategy"] = {
                "type": "static",
                "class_name": m.ontologyClass,
            }

        if m.fieldMappings:
            entry["data_properties"] = [
                {"column": f.column, "ontology_property": f.ontologyProperty}
                for f in m.fieldMappings
            ]

        if m.vectorizeFields:
            entry["vectorize_fields"] = m.vectorizeFields

        if m.objectProperties:
            entry["object_properties"] = [
                {
                    "foreign_key_column": op.foreignKeyColumn,
                    "target_label": op.targetLabel,
                    "ontology_property": op.ontologyProperty,
                    "direction": op.direction,
                }
                for op in m.objectProperties
            ]

        yaml_mappings.append(entry)

    identifier_errors = validate_mapping_identifiers(yaml_mappings)
    if identifier_errors:
        raise HTTPException(status_code=400, detail="; ".join(identifier_errors))

    yaml_content = yaml.dump(
        {"mappings": yaml_mappings},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    # Save to file
    mapping_path = scene_store.get_scene_mapping_path(scene_id)
    with open(mapping_path, 'w', encoding='utf-8') as f:
        f.write("# Auto-generated mapping configuration\n")
        f.write(yaml_content)

    scene_store.update_scene(scene_id)  # touch updated_at
    audit_event(username, "scene.mapping.visual_save", scene_id=scene_id, mapping_count=len(yaml_mappings))
    return {"status": "success", "message": "Mapping saved", "yaml": yaml_content}


@router.post("/scene/{scene_id}/mapping/auto-suggest")
async def auto_suggest_mapping(scene_id: str, username: str = Depends(verify_token)):
    """
    Auto-suggest mapping relationships based on field name / ontology property name similarity.
    Uses string matching heuristics (exact match, prefix removal, fuzzy match).
    """
    scene = scene_store.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Get ontology data
    ontology = _load_scene_ontology(scene_id)
    if not ontology:
        raise HTTPException(status_code=400, detail="No ontology file or linked ontology in this scene")

    # Get all ontology property names
    data_props = {p['name'] for p in ontology.get('data_properties', [])}
    obj_props = {p['name'] for p in ontology.get('object_properties', [])}
    classes = {c['name'] for c in ontology.get('classes', [])}

    suggestions = []

    # Get datasource tables
    ds_ids = scene.get('datasource_ids', [])
    if not ds_ids:
        return {"suggestions": suggestions}

    try:
        from ontology_intelligence.web.routes.datasource import _load_datasources, _get_connection
        all_ds = _load_datasources()
        for ds in all_ds:
            if ds['id'] not in ds_ids:
                continue
            try:
                conn = _get_connection(ds)
                cursor = conn.cursor()
                ds_type = ds['type'].lower()

                if ds_type == 'mysql':
                    cursor.execute("SHOW TABLES")
                    table_names = [r[0] for r in cursor.fetchall()]
                elif ds_type == 'postgresql':
                    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                    table_names = [r[0] for r in cursor.fetchall()]
                else:
                    table_names = []

                for table in table_names:
                    # Suggest class mapping based on table name
                    best_class = _find_best_match(table, classes)

                    if ds_type == 'mysql':
                        cursor.execute(f"DESCRIBE {quote_mysql_identifier(table, 'table_name')}")
                        columns = [{"name": r[0], "type": r[1], "key": r[3] or ''} for r in cursor.fetchall()]
                    elif ds_type == 'postgresql':
                        cursor.execute("""
                            SELECT column_name, data_type, ''
                            FROM information_schema.columns WHERE table_name=%s
                        """, (table,))
                        columns = [{"name": r[0], "type": r[1], "key": ''} for r in cursor.fetchall()]
                    elif ds_type == 'oracle':
                        cursor.execute("""
                            SELECT column_name, data_type, ''
                            FROM user_tab_columns WHERE table_name=:tn ORDER BY column_id
                        """, {"tn": table.upper()})
                        columns = [{"name": r[0], "type": r[1], "key": ''} for r in cursor.fetchall()]
                    else:
                        columns = []

                    field_suggestions = []
                    pk = None
                    for col in columns:
                        if col['key'] == 'PRI':
                            pk = col['name']
                        best_prop = _find_best_match(col['name'], data_props)
                        if best_prop:
                            field_suggestions.append({
                                "column": col['name'],
                                "ontologyProperty": best_prop['match'],
                                "confidence": best_prop['score'],
                            })

                    suggestions.append({
                        "table": table,
                        "suggestedClass": best_class['match'] if best_class else '',
                        "classConfidence": best_class['score'] if best_class else 0,
                        "primaryKey": pk or '',
                        "fieldSuggestions": field_suggestions,
                    })

                conn.close()
            except Exception as e:
                logger.error(f"[AutoSuggest] Error processing datasource {ds['id']}: {e}")
    except Exception as e:
        logger.error(f"[AutoSuggest] Error: {e}")

    return {"suggestions": suggestions}


def _find_best_match(name: str, candidates: set) -> Optional[dict]:
    """Find the best matching candidate for a given name using heuristics."""
    if not candidates:
        return None

    name_lower = name.lower().replace('_', '')

    best = None
    best_score = 0

    for candidate in candidates:
        candidate_lower = candidate.lower()

        # 1. Exact match (case-insensitive)
        if name_lower == candidate_lower:
            return {"match": candidate, "score": 1.0}

        # 2. Remove common prefixes: has, is, get
        stripped = candidate_lower
        for prefix in ('has', 'is', 'get'):
            if stripped.startswith(prefix) and len(stripped) > len(prefix):
                stripped = stripped[len(prefix):]
                break

        if name_lower == stripped:
            return {"match": candidate, "score": 0.95}

        # 3. Containment
        if name_lower in candidate_lower or candidate_lower in name_lower:
            score = 0.7
            if score > best_score:
                best = candidate
                best_score = score
            continue

        # 4. Fuzzy match (SequenceMatcher)
        ratio = SequenceMatcher(None, name_lower, candidate_lower).ratio()
        if ratio > 0.6 and ratio > best_score:
            best = candidate
            best_score = ratio

    if best and best_score >= 0.5:
        return {"match": best, "score": round(best_score, 2)}
    return None
