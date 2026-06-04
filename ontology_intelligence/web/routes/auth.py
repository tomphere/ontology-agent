# 认证路由
import jwt as pyjwt
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ontology_intelligence.config import settings
from ontology_intelligence.web.models import (
    LoginRequest,
    PasswordChangeRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from ontology_intelligence.web.audit import audit_event
from ontology_intelligence.web import user_store

router = APIRouter(tags=["auth"])
security = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证凭据")
    try:
        payload = pyjwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        user = user_store.get_user(username)
        if not user or user.get("disabled"):
            raise HTTPException(status_code=401, detail="用户不存在")
        return username
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效凭据")


def get_current_user(username: str = Depends(verify_token)):
    user = user_store.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user_store.public_user(username, user)


def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user["username"]


@router.post("/auth/login")
async def login(req: LoginRequest):
    settings.reload()
    user = user_store.verify_user_credentials(req.username, req.password)
    if not user:
        audit_event(req.username, "auth.login", "failed")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(req.username)
    audit_event(req.username, "auth.login", "success")
    return {"token": token, "user": user_store.public_user(req.username, user)}


@router.get("/auth/me")
async def get_me(username: str = Depends(verify_token)):
    user = user_store.get_user(username)
    return user_store.public_user(username, user)


@router.get("/auth/users")
async def list_users(username: str = Depends(require_admin)):
    return {"users": user_store.list_public_users()}


@router.post("/auth/users")
async def create_user(req: UserCreateRequest, username: str = Depends(require_admin)):
    try:
        user = user_store.create_user(req.username, req.display_name or req.username, req.role, req.password)
        audit_event(username, "user.create", created_user=req.username, role=req.role)
        return {"status": "success", "user": user}
    except ValueError as e:
        audit_event(username, "user.create", "failed", created_user=req.username, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/auth/users/{target_username}")
async def update_user(target_username: str, req: UserUpdateRequest, username: str = Depends(require_admin)):
    try:
        user = user_store.update_user(
            target_username,
            display_name=req.display_name,
            role=req.role,
            disabled=req.disabled,
            password=req.password,
        )
        audit_event(username, "user.update", target_user=target_username, role=req.role, disabled=req.disabled)
        return {"status": "success", "user": user}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        audit_event(username, "user.update", "failed", target_user=target_username, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/auth/users/{target_username}")
async def delete_user(target_username: str, username: str = Depends(require_admin)):
    if target_username == username:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")
    try:
        user_store.delete_user(target_username)
        audit_event(username, "user.delete", target_user=target_username)
        return {"status": "success"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        audit_event(username, "user.delete", "failed", target_user=target_username, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/auth/me/password")
async def change_own_password(req: PasswordChangeRequest, username: str = Depends(verify_token)):
    if not user_store.verify_user_credentials(username, req.current_password):
        audit_event(username, "user.password.change", "failed", reason="bad_current_password")
        raise HTTPException(status_code=400, detail="当前密码不正确")
    try:
        user_store.update_user(username, password=req.new_password)
        audit_event(username, "user.password.change")
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
