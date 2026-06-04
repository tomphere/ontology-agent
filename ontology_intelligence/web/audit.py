import json
import logging
from datetime import datetime, timezone
from typing import Any

from ontology_intelligence.config import settings

logger = logging.getLogger("web-platform.audit")


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def audit_event(username: str, action: str, status: str = "success", **details):
    """Append a structured audit event to data/audit/audit.log."""
    try:
        audit_dir = settings.project_root / "data" / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "time": datetime.now(timezone.utc).isoformat(),
            "username": username or "anonymous",
            "action": action,
            "status": status,
            "details": _safe_json(details),
        }
        with open(audit_dir / "audit.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to write audit event: {e}")


def _parse_time(value: str):
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def read_audit_events(
    limit: int = 200,
    username: str = None,
    action: str = None,
    status: str = None,
    since: str = None,
    until: str = None,
) -> list:
    """Read recent audit events from newest to oldest."""
    audit_file = settings.project_root / "data" / "audit" / "audit.log"
    if not audit_file.exists():
        return []
    since_dt = _parse_time(since)
    until_dt = _parse_time(until)
    events = []
    try:
        with open(audit_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if username and event.get("username") != username:
                continue
            if action and event.get("action") != action:
                continue
            if status and event.get("status") != status:
                continue
            event_time = _parse_time(event.get("time", ""))
            if since_dt and event_time and event_time < since_dt:
                continue
            if until_dt and event_time and event_time > until_dt:
                continue
            events.append(event)
            if len(events) >= limit:
                break
    except Exception as e:
        logger.warning(f"Failed to read audit events: {e}")
    return events
