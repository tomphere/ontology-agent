"""Administration routes for audit and graph governance."""

import csv
import json
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from ontology_intelligence.web.audit import audit_event, read_audit_events
from ontology_intelligence.web.routes.auth import require_admin
from ontology_intelligence.web import scene_store


router = APIRouter(tags=["admin"])


class GraphAdoptSceneRequest(BaseModel):
    scene_id: str
    dry_run: bool = True


@router.get("/admin/audit")
async def list_audit_events(
    limit: int = Query(200, ge=1, le=1000),
    event_username: str = Query(None),
    action: str = Query(None),
    status: str = Query(None),
    since: str = Query(None),
    until: str = Query(None),
    username: str = Depends(require_admin),
):
    events = read_audit_events(
        limit=limit,
        username=event_username,
        action=action,
        status=status,
        since=since,
        until=until,
    )
    return {"events": events, "total": len(events)}


@router.get("/admin/audit/export")
async def export_audit_events(
    limit: int = Query(1000, ge=1, le=5000),
    event_username: str = Query(None),
    action: str = Query(None),
    status: str = Query(None),
    since: str = Query(None),
    until: str = Query(None),
    export_format: str = Query("csv"),
    username: str = Depends(require_admin),
):
    events = read_audit_events(
        limit=limit,
        username=event_username,
        action=action,
        status=status,
        since=since,
        until=until,
    )
    audit_event(username, "audit.export", format=export_format, count=len(events))

    if export_format == "jsonl":
        body = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
        return Response(
            content=body + ("\n" if body else ""),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=audit-events.jsonl"},
        )
    if export_format != "csv":
        raise HTTPException(status_code=400, detail="export_format must be csv or jsonl")

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["time", "username", "action", "status", "details"])
    writer.writeheader()
    for event in events:
        writer.writerow({
            "time": event.get("time", ""),
            "username": event.get("username", ""),
            "action": event.get("action", ""),
            "status": event.get("status", ""),
            "details": json.dumps(event.get("details", {}), ensure_ascii=False),
        })
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit-events.csv"},
    )


@router.post("/admin/graph/adopt-scene")
async def adopt_scene_graph(req: GraphAdoptSceneRequest, username: str = Depends(require_admin)):
    scene = scene_store.get_scene(req.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    mapping_path = scene_store.get_scene_mapping_path(req.scene_id)
    try:
        from ontology_intelligence.sync.engine import adopt_global_graph_into_scene
        result = adopt_global_graph_into_scene(req.scene_id, mapping_file=mapping_path, dry_run=req.dry_run)
        audit_event(username, "graph.adopt_scene", scene_id=req.scene_id, dry_run=req.dry_run, result=result)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("errors") or result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        audit_event(username, "graph.adopt_scene", "failed", scene_id=req.scene_id, dry_run=req.dry_run, error=str(e))
        raise HTTPException(status_code=500, detail=f"Graph migration failed: {e}")
