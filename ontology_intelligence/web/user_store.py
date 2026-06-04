"""Persistent user storage for the web platform."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ontology_intelligence.config import settings
from ontology_intelligence.security import hash_password, verify_password


USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,31}$")
VALID_ROLES = {"admin", "user"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _users_path() -> Path:
    path = Path(settings.users_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _seed_admin() -> dict:
    password_hash = settings.admin_password_hash or hash_password(settings.admin_password)
    return {
        "username": "admin",
        "display_name": "系统管理员",
        "role": "admin",
        "disabled": False,
        "password_hash": password_hash,
        "created_at": _now(),
        "updated_at": _now(),
    }


def load_users() -> dict:
    """Load users indexed by username, creating the default admin on first run."""
    path = _users_path()
    if not path.exists():
        users = {"admin": _seed_admin()}
        save_users(users)
        return users
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        users = data.get("users", {}) if isinstance(data, dict) else {}
        if "admin" not in users:
            users["admin"] = _seed_admin()
            save_users(users)
        return users
    except Exception:
        users = {"admin": _seed_admin()}
        save_users(users)
        return users


def save_users(users: dict):
    path = _users_path()
    path.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=2), encoding="utf-8")


def public_user(username: str, user: dict) -> dict:
    return {
        "username": username,
        "display_name": user.get("display_name") or username,
        "role": user.get("role", "user"),
        "disabled": bool(user.get("disabled", False)),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }


def list_public_users() -> list:
    users = load_users()
    return [public_user(username, user) for username, user in sorted(users.items())]


def get_user(username: str) -> Optional[dict]:
    return load_users().get(username)


def verify_user_credentials(username: str, password: str) -> Optional[dict]:
    user = get_user(username)
    if not user or user.get("disabled"):
        return None
    password_hash = user.get("password_hash", "")
    if not password_hash and username == "admin":
        if settings.admin_password_hash:
            password_hash = settings.admin_password_hash
        elif password == settings.admin_password:
            return user
    if verify_password(password, password_hash):
        return user
    return None


def _validate_username(username: str):
    if not USERNAME_RE.match(username or ""):
        raise ValueError("用户名需以字母开头，长度 3-32，仅允许字母、数字、下划线、点和短横线")


def _validate_role(role: str):
    if role not in VALID_ROLES:
        raise ValueError("角色只能是 admin 或 user")


def _active_admin_count(users: dict) -> int:
    return sum(1 for user in users.values() if user.get("role") == "admin" and not user.get("disabled"))


def create_user(username: str, display_name: str, role: str, password: str) -> dict:
    _validate_username(username)
    _validate_role(role)
    if not password or len(password) < 8:
        raise ValueError("密码长度至少 8 位")
    users = load_users()
    if username in users:
        raise ValueError("用户已存在")
    now = _now()
    users[username] = {
        "username": username,
        "display_name": display_name or username,
        "role": role,
        "disabled": False,
        "password_hash": hash_password(password),
        "created_at": now,
        "updated_at": now,
    }
    save_users(users)
    return public_user(username, users[username])


def update_user(username: str, *, display_name=None, role=None, disabled=None, password=None) -> dict:
    users = load_users()
    if username not in users:
        raise KeyError("用户不存在")
    user = users[username]
    if role is not None:
        _validate_role(role)
        old_role = user.get("role")
        user["role"] = role
        if old_role == "admin" and role != "admin" and _active_admin_count(users) == 0:
            user["role"] = old_role
            raise ValueError("至少需要保留一个启用的管理员")
    if display_name is not None:
        user["display_name"] = display_name or username
    if disabled is not None:
        old_disabled = bool(user.get("disabled"))
        user["disabled"] = bool(disabled)
        if user.get("role") == "admin" and user["disabled"] and _active_admin_count(users) == 0:
            user["disabled"] = old_disabled
            raise ValueError("至少需要保留一个启用的管理员")
    if password:
        if len(password) < 8:
            raise ValueError("密码长度至少 8 位")
        user["password_hash"] = hash_password(password)
    user["updated_at"] = _now()
    users[username] = user
    save_users(users)
    return public_user(username, user)


def delete_user(username: str):
    users = load_users()
    if username not in users:
        raise KeyError("用户不存在")
    removed = users.pop(username)
    if removed.get("role") == "admin" and _active_admin_count(users) == 0:
        users[username] = removed
        raise ValueError("至少需要保留一个启用的管理员")
    save_users(users)
