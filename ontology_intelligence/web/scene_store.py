# =============================================================================
# Scene Store - Scene metadata storage layer
# =============================================================================

import os
import json
import uuid
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ontology_intelligence.config import settings

logger = logging.getLogger(__name__)

TOP_ONTOLOGY_CLASSES = {"Thing", "Nothing", "owl:Thing", "owl:Nothing"}
TOP_OBJECT_PROPERTIES = {"topObjectProperty", "owl:topObjectProperty"}
TOP_DATA_PROPERTIES = {"topDataProperty", "owl:topDataProperty"}


def _scenes_dir() -> str:
    """Get the scenes data directory path."""
    d = os.path.join(str(settings.project_root), 'data', 'scenes')
    os.makedirs(d, exist_ok=True)
    return d


def _index_path() -> str:
    """Get the scenes.json index file path."""
    return os.path.join(_scenes_dir(), 'scenes.json')


def _load_index() -> list:
    """Load scenes index from disk."""
    path = _index_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[Scene Store] Failed to load index: {e}")
        return []


def _save_index(scenes: list):
    """Save scenes index to disk."""
    path = _index_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2, default=str)


def _scene_dir(scene_id: str) -> str:
    """Get a specific scene's directory path."""
    d = os.path.join(_scenes_dir(), scene_id)
    os.makedirs(d, exist_ok=True)
    return d


def list_scenes() -> list:
    """List all scenes."""
    scenes = _load_index()
    # Enrich with file status
    for s in scenes:
        sd = os.path.join(_scenes_dir(), s['id'])
        s['has_ontology'] = bool(s.get('ontology_file')) and os.path.isfile(
            os.path.join(sd, s.get('ontology_file', ''))
        )
        mapping_path = os.path.join(sd, 'mapping.yaml')
        s['has_mapping'] = os.path.isfile(mapping_path)
        s['has_linked_ontology'] = bool(s.get('linked_ontology_id'))
    return scenes


def get_scene(scene_id: str) -> Optional[dict]:
    """Get a scene by ID."""
    scenes = _load_index()
    for s in scenes:
        if s['id'] == scene_id:
            sd = _scene_dir(scene_id)
            s['has_ontology'] = bool(s.get('ontology_file')) and os.path.isfile(
                os.path.join(sd, s.get('ontology_file', ''))
            )
            mapping_path = os.path.join(sd, 'mapping.yaml')
            s['has_mapping'] = os.path.isfile(mapping_path)
            s['has_linked_ontology'] = bool(s.get('linked_ontology_id'))
            return s
    return None


def create_scene(name: str, description: str = '', data_mode: str = 'import') -> dict:
    """Create a new scene."""
    scene_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    scene = {
        'id': scene_id,
        'name': name,
        'description': description,
        'data_mode': data_mode,
        'ontology_file': '',
        'linked_ontology_id': '',
        'datasource_ids': [],
        'created_at': now,
        'updated_at': now,
    }

    # Create scene directory
    _scene_dir(scene_id)

    # Create empty mapping.yaml
    mapping_path = os.path.join(_scene_dir(scene_id), 'mapping.yaml')
    with open(mapping_path, 'w', encoding='utf-8') as f:
        f.write("# Mapping configuration for scene: {}\nmappings: []\n".format(name))

    # Add to index
    scenes = _load_index()
    scenes.append(scene)
    _save_index(scenes)

    logger.info(f"[Scene Store] Created scene '{name}' (id={scene_id})")
    return scene


def update_scene(scene_id: str, **kwargs) -> Optional[dict]:
    """Update a scene's metadata."""
    scenes = _load_index()
    for i, s in enumerate(scenes):
        if s['id'] == scene_id:
            for key in ('name', 'description', 'data_mode', 'ontology_file', 'linked_ontology_id', 'datasource_ids'):
                if key in kwargs:
                    if key == 'linked_ontology_id':
                        s[key] = kwargs[key] or ''
                    else:
                        s[key] = kwargs[key]
            s['updated_at'] = datetime.now().isoformat()
            scenes[i] = s
            _save_index(scenes)
            return s
    return None


def delete_scene(scene_id: str) -> bool:
    """Delete a scene and its files."""
    scenes = _load_index()
    new_scenes = [s for s in scenes if s['id'] != scene_id]
    if len(new_scenes) == len(scenes):
        return False

    # Remove scene directory
    sd = os.path.join(_scenes_dir(), scene_id)
    if os.path.isdir(sd):
        shutil.rmtree(sd, ignore_errors=True)

    _save_index(new_scenes)
    logger.info(f"[Scene Store] Deleted scene {scene_id}")
    return True


def get_scene_ontology_path(scene_id: str) -> Optional[str]:
    """Get the full path to a scene's ontology file."""
    scene = get_scene(scene_id)
    if not scene or not scene.get('ontology_file'):
        return None
    path = os.path.join(_scene_dir(scene_id), scene['ontology_file'])
    return path if os.path.isfile(path) else None


def get_scene_mapping_path(scene_id: str) -> str:
    """Get the full path to a scene's mapping.yaml file."""
    return os.path.join(_scene_dir(scene_id), 'mapping.yaml')


def get_scene_rules_path(scene_id: str) -> str:
    """Get the full path to a scene's rules.yaml file."""
    return os.path.join(_scene_dir(scene_id), 'rules.yaml')


def get_scene_aliases_path(scene_id: str) -> str:
    """Get the full path to a scene's aliases.yaml file."""
    return os.path.join(_scene_dir(scene_id), 'aliases.yaml')


def get_scene_routing_path(scene_id: str) -> str:
    """Get the full path to a scene's routing.yaml file."""
    return os.path.join(_scene_dir(scene_id), 'routing.yaml')


def load_scene_rules(scene_id: str) -> list:
    """Load business rules for a scene."""
    path = get_scene_rules_path(scene_id)
    if not os.path.isfile(path):
        return []
    try:
        import yaml
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get('rules', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    except Exception as e:
        logger.error(f"[Scene Store] Failed to load rules for scene {scene_id}: {e}")
        return []


def load_scene_aliases(scene_id: str) -> dict:
    """Load aliases for a scene."""
    path = get_scene_aliases_path(scene_id)
    if not os.path.isfile(path):
        return {}
    try:
        import yaml
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get('aliases', {}) if isinstance(data, dict) else (data if isinstance(data, dict) else {})
    except Exception as e:
        logger.error(f"[Scene Store] Failed to load aliases for scene {scene_id}: {e}")
        return {}

def load_scene_routing(scene_id: str) -> list:
    """Load query routing rules for a scene."""
    path = get_scene_routing_path(scene_id)
    if not os.path.isfile(path):
        return []
    try:
        import yaml
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get('query_routing', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    except Exception as e:
        logger.error(f"[Scene Store] Failed to load routing for scene {scene_id}: {e}")
        return []

def get_linked_ontology_model(scene_id: str) -> Optional[dict]:
    """Load the ontology-workbench model linked to a scene, if any."""
    scene = get_scene(scene_id)
    ontology_id = scene.get("linked_ontology_id") if scene else None
    if not ontology_id:
        return None
    paths = [
        Path(settings.project_root) / "data" / "ontology_studio" / f"{ontology_id}.json",
        Path(settings.project_root) / "data" / "ontologies" / f"{ontology_id}.json",
    ]
    for path in paths:
        if not path.exists():
            continue
        try:
            model = json.loads(path.read_text(encoding="utf-8"))
            model.setdefault("id", ontology_id)
            return model
        except Exception as e:
            logger.error(f"[Scene Store] Failed to load linked ontology {ontology_id} from {path}: {e}")
    return None


def normalize_ontology_model(model: dict) -> dict:
    """Normalize an ontology-workbench JSON model to the parser response shape."""
    def first_value(value):
        if isinstance(value, list):
            return value[0] if value else ''
        return value or ''

    classes = []
    for cls in model.get("classes", []):
        item = dict(cls)
        if "parents" not in item:
            parent = item.get("sub_class_of")
            item["parents"] = [parent] if parent else []
        classes.append(item)

    object_properties = []
    for prop in model.get("object_properties", []):
        item = dict(prop)
        item["domain"] = first_value(item.get("domain"))
        item["range"] = first_value(item.get("range"))
        object_properties.append(item)

    data_properties = []
    for prop in model.get("data_properties", []):
        item = dict(prop)
        if "domains" not in item:
            domain = item.get("domain", [])
            item["domains"] = domain if isinstance(domain, list) else ([domain] if domain else [])
        item["range"] = first_value(item.get("range"))
        data_properties.append(item)

    return {
        "filename": model.get("name") or model.get("id") or "linked-ontology",
        "ontology_uri": model.get("ontology_iri", ""),
        "classes": classes,
        "object_properties": object_properties,
        "data_properties": data_properties,
        "source": "linked_ontology",
        "linked_ontology_id": model.get("id", ""),
    }
