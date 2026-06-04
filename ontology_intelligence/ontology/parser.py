# =============================================================================
# Unified Ontology Parser - OWL 2 Support via Owlready2
# =============================================================================
# Uses owlready2 for full OWL 2 DL support, compatible with Protégé 5.6.x
# Supports: RDF/XML (.rdf, .owl), Turtle (.ttl), N-Triples (.nt),
# OWL/XML (.owx)
# =============================================================================

import os
import logging
from typing import Optional

from owlready2 import get_ontology, Thing, ObjectProperty, DataProperty, Restriction, And, Or, Not

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.rdf', '.owl', '.ttl', '.nt', '.n3', '.owx'}


def detect_format(file_path: str) -> Optional[str]:
    """Detect if file is supported by checking extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in SUPPORTED_EXTENSIONS:
        return ext
    return None


def _get_local_name(entity) -> str:
    """Extract local name from an OWL entity."""
    if entity is None:
        return ''
    name = entity.name
    if name:
        return name
    return ''


def parse_ontology(file_path: str) -> dict:
    """
    Parse an ontology file using owlready2.

    Supports: RDF/XML, Turtle, N-Triples, OWL/XML.

    Returns:
        {
            "filename": str,
            "ontology_uri": str,
            "classes": [
                {
                    "name": str,
                    "label": str,
                    "comment": str,
                    "parents": [str, ...],
                    "restrictions": [{"property": str, "type": str, "value": str, "comment": str}, ...],
                    "equivalent_to": [dict, ...],
                    "disjoint_with": [str, ...]
                },
                ...
            ],
            "object_properties": [
                {"name": str, "domain": str, "range": str, "comment": str},
                ...
            ],
            "data_properties": [
                {"name": str, "domains": [str, ...], "range": str, "comment": str},
                ...
            ],
        }
    """
    fmt = detect_format(file_path)
    if fmt is None:
        ext = os.path.splitext(file_path)[1]
        raise ValueError(f"Unsupported ontology format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    try:
        onto = get_ontology(f"file://{file_path}").load()
    except Exception as e:
        logger.error(f"[Ontology Parser] Failed to parse {file_path}: {e}")
        raise ValueError(f"Failed to parse ontology file: {e}")

    logger.info(f"[Ontology Parser] Loaded {file_path}: {len(list(onto.classes()))} classes")

    ontology_uri = onto.base_iri or ''

    classes = []
    for cls in onto.classes():
        name = _get_local_name(cls)
        if not name:
            continue

        label = name
        if cls.label:
            label = cls.label.first()

        comment = ''
        if cls.comment:
            comment = cls.comment.first()

        parents = []
        for parent in cls.is_a:
            if isinstance(parent, Thing.__class__) and hasattr(parent, 'name'):
                parent_name = _get_local_name(parent)
                if parent_name and parent_name != 'Thing':
                    parents.append(parent_name)

        restrictions = []
        for constraint in cls.is_a:
            if hasattr(constraint, 'property') and hasattr(constraint, 'value'):
                restriction = _parse_restriction(constraint)
                if restriction:
                    restrictions.append(restriction)

        # Parse equivalent_to expressions (Union, Intersection, Complement, etc.)
        equivalent_to = []
        if hasattr(cls, 'equivalent_to') and cls.equivalent_to:
            for eq in cls.equivalent_to:
                parsed_eq = _parse_class_expression(eq)
                if parsed_eq:
                    equivalent_to.append(parsed_eq)

        # Parse disjoint_with declarations
        disjoint_with = []
        for disjoint_set in onto.disjoints():
            if cls in disjoint_set.entities:
                for other in disjoint_set.entities:
                    if other != cls and hasattr(other, 'name'):
                        other_name = _get_local_name(other)
                        if other_name:
                            disjoint_with.append(other_name)

        classes.append({
            "name": name,
            "label": label,
            "comment": comment,
            "parents": parents,
            "restrictions": restrictions,
            "equivalent_to": equivalent_to,
            "disjoint_with": disjoint_with,
        })

    object_properties = []
    for prop in onto.object_properties():
        name = _get_local_name(prop)
        if not name:
            continue

        domain = ''
        if prop.domain:
            for d in prop.domain:
                domain = _get_local_name(d)
                if domain:
                    break

        range_ = ''
        if prop.range:
            for r in prop.range:
                range_ = _get_local_name(r)
                if range_:
                    break

        comment = ''
        if prop.comment:
            comment = prop.comment.first()

        object_properties.append({
            "name": name,
            "domain": domain,
            "range": range_,
            "comment": comment,
        })

    data_properties = []
    for prop in onto.data_properties():
        name = _get_local_name(prop)
        if not name:
            continue

        domains = []
        if prop.domain:
            for d in prop.domain:
                dn = _get_local_name(d)
                if dn:
                    domains.append(dn)

        range_ = ''
        if prop.range:
            range_ = str(prop.range[0]) if prop.range else ''

        comment = ''
        if prop.comment:
            comment = prop.comment.first()

        data_properties.append({
            "name": name,
            "domains": domains,
            "range": range_,
            "comment": comment,
        })

    return {
        "filename": os.path.basename(file_path),
        "ontology_uri": ontology_uri,
        "classes": classes,
        "object_properties": object_properties,
        "data_properties": data_properties,
    }


def _parse_class_expression(expr) -> Optional[dict]:
    """Recursively parse an OWL class expression from owlready2.

    Supports:
    - Named class references
    - Intersection (And / owl:intersectionOf)
    - Union (Or / owl:unionOf)
    - Complement (Not / owl:complementOf)
    - Restrictions (some, only, min, max, exactly, value)
    """
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
                parsed = _parse_class_expression(member)
                if parsed:
                    operands.append(parsed)
            if operands:
                return {"type": "intersection", "operands": operands}
            return None

        # Union (Or)
        if isinstance(expr, Or) or (hasattr(expr, 'Classes') and type(expr).__name__ == 'Or'):
            operands = []
            for member in expr.Classes:
                parsed = _parse_class_expression(member)
                if parsed:
                    operands.append(parsed)
            if operands:
                return {"type": "union", "operands": operands}
            return None

        # Complement (Not)
        if isinstance(expr, Not) or type(expr).__name__ == 'Not':
            inner = getattr(expr, 'Class', None)
            if inner is not None:
                parsed = _parse_class_expression(inner)
                if parsed:
                    return {"type": "complement", "operand": parsed}
            return None

        # Restriction
        if isinstance(expr, Restriction) or (hasattr(expr, 'property') and hasattr(expr, 'value')):
            return _parse_restriction(expr)

        return None
    except Exception as e:
        logger.warning(f"[Ontology Parser] Failed to parse class expression: {e}")
        return None


def _parse_restriction(restriction) -> Optional[dict]:
    """Parse an OWL restriction from owlready2.
    
    Handles:
    - some (存在性约束): type=24
    - only (全称约束): type=25
    - exactly (精确基数): type=26
    - min (最小基数): type=27
    - max (最大基数): type=28
    - value (值约束): type=29
    
    Note: owlready2 uses 'type' attribute to distinguish restriction types.
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


def extract_class_names(file_path: str) -> dict:
    """
    Lightweight extraction of class names and property names from an ontology file.
    Used by validation module for quick checks without full parsing.

    Returns:
        {"classes": set[str], "object_properties": set[str], "data_properties": set[str]}
    """
    result = {"classes": set(), "object_properties": set(), "data_properties": set()}

    fmt = detect_format(file_path)
    if fmt is None:
        return result

    try:
        onto = get_ontology(f"file://{file_path}").load()

        for cls in onto.classes():
            name = _get_local_name(cls)
            if name:
                result["classes"].add(name)

        for prop in onto.object_properties():
            name = _get_local_name(prop)
            if name:
                result["object_properties"].add(name)

        for prop in onto.data_properties():
            name = _get_local_name(prop)
            if name:
                result["data_properties"].add(name)

    except Exception as e:
        logger.error(f"[Ontology Parser] Lightweight extraction failed for {file_path}: {e}")

    return result
