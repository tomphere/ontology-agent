# 同步引擎控制路由
import os
import asyncio
import time
import logging
import ipaddress
import socket
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends

from ontology_intelligence.config import settings
from ontology_intelligence.web.models import SyncOntologyRequest, FetchRemoteRequest
from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.web.audit import audit_event

router = APIRouter(tags=["sync"])
logger = logging.getLogger("web-platform")
MAX_REMOTE_ONTOLOGY_BYTES = 20 * 1024 * 1024
REMOTE_FETCH_TIMEOUT_SECONDS = 10


def _get_sync_state():
    from ontology_intelligence.web.app import sync_state
    return sync_state


def _get_sync_executor():
    from ontology_intelligence.web.app import sync_executor
    return sync_executor


def _sync_result(kind: str, status: str, started_at: str, message: str, result=None, error: str = None) -> dict:
    payload = {
        "kind": kind,
        "status": status,
        "message": message,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
    }
    if result is not None:
        payload["result"] = result
    if error:
        payload["error"] = error
    return payload


def _is_private_hostname(hostname: str) -> bool:
    if not hostname:
        return True
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return True
    return False


def _validate_remote_ontology_url(url: str):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="必须输入有效的 HTTP/HTTPS 链接")
    if _is_private_hostname(parsed.hostname):
        raise HTTPException(status_code=400, detail="禁止从本机、内网或保留地址下载远程本体")
    return parsed


@router.post("/sync/ontology")
async def trigger_ontology_sync(req: SyncOntologyRequest = None, username: str = Depends(require_admin)):
    state = _get_sync_state()
    if state["ontology_syncing"]:
        raise HTTPException(status_code=409, detail="同步进行中")
    state["ontology_syncing"] = True
    state["ontology_result"] = None
    state["ontology_started_at"] = datetime.now().isoformat()
    custom_dir = req.ontology_dir if req else None

    def _run():
        started_at = state["ontology_started_at"]
        try:
            settings.reload()
            if custom_dir:
                os.environ["ONTOLOGY_DIR"] = custom_dir
            from ontology_intelligence.sync.engine import init_neo4j_environment, sync_all_ontology_files
            init_neo4j_environment()
            sync_all_ontology_files(custom_dir)
            state["last_ontology_sync"] = datetime.now().isoformat()
            state["ontology_result"] = _sync_result("ontology", "success", started_at, "本体同步完成")
            audit_event(username, "sync.ontology", ontology_dir=custom_dir or settings.ontology_dir)
            return state["ontology_result"]
        except Exception as e:
            logger.error(f"本体同步失败: {e}")
            state["ontology_result"] = _sync_result("ontology", "error", started_at, "本体同步失败", error=str(e))
            audit_event(username, "sync.ontology", "failed", error=str(e))
            return state["ontology_result"]
        finally:
            state["ontology_syncing"] = False

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_sync_executor(), _run)


@router.post("/sync/database")
async def trigger_database_sync(username: str = Depends(require_admin)):
    state = _get_sync_state()
    if state["database_syncing"]:
        raise HTTPException(status_code=409, detail="同步进行中")
    state["database_syncing"] = True
    state["database_result"] = None
    state["database_started_at"] = datetime.now().isoformat()

    def _run():
        started_at = state["database_started_at"]
        try:
            settings.reload()
            from ontology_intelligence.sync.engine import init_neo4j_environment, sync_mysql_to_neo4j
            init_neo4j_environment()
            result = sync_mysql_to_neo4j()
            if isinstance(result, dict) and result.get("errors"):
                state["database_result"] = _sync_result("database", "error", started_at, "数据库同步存在错误", result=result, error="; ".join(result["errors"]))
                audit_event(username, "sync.database", "failed", result=result)
                return state["database_result"]
            state["last_database_sync"] = datetime.now().isoformat()
            state["database_result"] = _sync_result("database", "success", started_at, "数据库同步完成", result=result)
            audit_event(username, "sync.database", result=result)
            return state["database_result"]
        except Exception as e:
            logger.error(f"数据库同步失败: {e}")
            state["database_result"] = _sync_result("database", "error", started_at, "数据库同步失败", error=str(e))
            audit_event(username, "sync.database", "failed", error=str(e))
            return state["database_result"]
        finally:
            state["database_syncing"] = False

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_sync_executor(), _run)


@router.get("/sync/status")
async def get_sync_status(username: str = Depends(verify_token)):
    return _get_sync_state()


@router.post("/sync/fetch-remote")
async def fetch_remote_ontology(req: FetchRemoteRequest, username: str = Depends(require_admin)):
    ontology_dir = settings.ontology_dir
    if not ontology_dir or not os.path.isdir(ontology_dir):
        raise HTTPException(status_code=400, detail="本体目录不存在或未配置")
    import urllib.request
    url = req.url.strip()
    parsed_url = _validate_remote_ontology_url(url)
    try:
        filename = os.path.basename(parsed_url.path)
        if not filename or filename.lower() == "raw":
            filename = f"remote_{int(time.time())}.owl"
        save_path = os.path.join(ontology_dir, filename)
        req_obj = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        total = 0
        with urllib.request.urlopen(req_obj, timeout=REMOTE_FETCH_TIMEOUT_SECONDS) as response, open(save_path, 'wb') as out_file:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_REMOTE_ONTOLOGY_BYTES:
                raise HTTPException(status_code=400, detail="远程本体文件超过 20MB 限制")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_REMOTE_ONTOLOGY_BYTES:
                    raise HTTPException(status_code=400, detail="远程本体文件超过 20MB 限制")
                out_file.write(chunk)
        audit_event(username, "ontology.fetch_remote", url=url, filename=filename)
        return {"status": "success", "message": f"已保存: {filename}", "file": filename}
    except HTTPException:
        if 'save_path' in locals() and os.path.exists(save_path):
            os.remove(save_path)
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {e}")
