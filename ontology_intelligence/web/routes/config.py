# 配置管理路由
import os
import yaml
import xml.etree.ElementTree as ET
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Query

from ontology_intelligence.config import settings
from ontology_intelligence.security import validate_mapping_identifiers
from ontology_intelligence.web.models import EnvUpdateRequest, MappingUpdateRequest, OntologyDirRequest
from ontology_intelligence.web.routes.auth import verify_token, require_admin, get_current_user
from ontology_intelligence.web.audit import audit_event

router = APIRouter(tags=["config"])

SECRET_KEYWORDS = ("PASSWORD", "SECRET", "TOKEN", "KEY")


def _is_secret_key(key: str) -> bool:
    upper = (key or "").upper()
    return any(part in upper for part in SECRET_KEYWORDS)


def _mask_value(key: str, value: str) -> str:
    if not _is_secret_key(key) or not value:
        return value
    if len(value) <= 4:
        return "********"
    return f"********{value[-4:]}"


def _get_env_path() -> Path:
    return settings.project_root / ".env"


def _get_mapping_path() -> Path:
    return Path(settings.mapping_file)


@router.get("/config/env")
async def get_env_config(current_user: dict = Depends(get_current_user)):
    env_path = _get_env_path()
    if not env_path.exists():
        raise HTTPException(status_code=404, detail=".env 不存在")
    content = env_path.read_text(encoding="utf-8")
    parsed = {}
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.split("#", 1)[0]
            parsed[key.strip()] = value.strip()
    if current_user.get("role") == "admin":
        return {"raw": content, "parsed": parsed, "path": str(env_path), "redacted": False}
    redacted = {key: _mask_value(key, value) for key, value in parsed.items()}
    return {"raw": "", "parsed": redacted, "path": str(env_path), "redacted": True}


@router.put("/config/env")
async def update_env_config(req: EnvUpdateRequest, username: str = Depends(require_admin)):
    _get_env_path().write_text(req.content, encoding="utf-8")
    settings.reload()
    audit_event(username, "config.env.update")
    return {"status": "success", "message": ".env 已更新"}


@router.get("/config/mapping")
async def get_mapping_config(username: str = Depends(verify_token)):
    mapping_path = _get_mapping_path()
    if not mapping_path.exists():
        raise HTTPException(status_code=404, detail="映射配置文件不存在")
    content = mapping_path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(content)
    except Exception:
        parsed = None
    return {"raw": content, "parsed": parsed, "path": str(mapping_path)}


@router.put("/config/mapping")
async def update_mapping_config(req: MappingUpdateRequest, username: str = Depends(require_admin)):
    try:
        parsed = yaml.safe_load(req.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML 格式错误: {e}")
    if parsed is not None and not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="映射配置必须是 YAML 对象")
    identifier_errors = validate_mapping_identifiers(parsed.get("mappings", []) if parsed else [])
    if identifier_errors:
        raise HTTPException(status_code=400, detail="; ".join(identifier_errors))
    _get_mapping_path().write_text(req.content, encoding="utf-8")
    audit_event(username, "config.mapping.update")
    return {"status": "success", "message": "映射配置已更新"}


@router.put("/config/ontology-dir")
async def update_ontology_dir(req: OntologyDirRequest, username: str = Depends(require_admin)):
    env_path = _get_env_path()
    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("ONTOLOGY_DIR") and "=" in line:
            lines[i] = f"ONTOLOGY_DIR={req.ontology_dir}"
            found = True
            break
    if not found:
        lines.append(f"ONTOLOGY_DIR={req.ontology_dir}")
    env_path.write_text("\n".join(lines), encoding="utf-8")
    settings.reload()
    audit_event(username, "config.ontology_dir.update", ontology_dir=req.ontology_dir)
    return {"status": "success", "message": f"本体目录已更新为: {req.ontology_dir}"}


@router.get("/config/ontology-file")
async def read_ontology_file(filename: str = Query(...), username: str = Depends(verify_token)):
    """Parse an OWL/RDF/TTL/etc. ontology file and return structured data"""
    ontology_dir = settings.ontology_dir
    if not ontology_dir or not os.path.isdir(ontology_dir):
        raise HTTPException(status_code=400, detail="Ontology directory not configured or does not exist")
    safe_name = os.path.basename(filename)
    file_path = os.path.join(ontology_dir, safe_name)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")
    try:
        from ontology_intelligence.ontology.parser import parse_ontology
        return parse_ontology(file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")
