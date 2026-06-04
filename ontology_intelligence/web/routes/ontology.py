# 本体文件上传管理路由
import os
import shutil
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List

from ontology_intelligence.config import settings
from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.web.audit import audit_event

router = APIRouter(tags=["ontology"])

ALLOWED_EXTENSIONS = {'.owl', '.rdf', '.ttl', '.n3', '.nt', '.jsonld', '.owx'}


@router.get("/ontology/files")
async def list_ontology_files(username: str = Depends(verify_token)):
    """列出本体目录中的文件"""
    ontology_dir = settings.ontology_dir
    if not os.path.isdir(ontology_dir):
        return {"files": [], "ontology_dir": ontology_dir, "exists": False}
    files = []
    for f in os.listdir(ontology_dir):
        ext = os.path.splitext(f)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            full_path = os.path.join(ontology_dir, f)
            files.append({
                "name": f,
                "size": os.path.getsize(full_path),
                "modified": os.path.getmtime(full_path),
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files, "ontology_dir": ontology_dir, "exists": True}


@router.post("/ontology/upload")
async def upload_ontology_file(
    file: UploadFile = File(...),
    username: str = Depends(require_admin),
):
    """上传本体文件"""
    ontology_dir = settings.ontology_dir
    os.makedirs(ontology_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}。支持: {', '.join(ALLOWED_EXTENSIONS)}")

    save_path = os.path.join(ontology_dir, file.filename)
    try:
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
        audit_event(username, "ontology.upload", filename=file.filename, size=len(content))
        return {
            "status": "success",
            "message": f"文件 {file.filename} 上传成功",
            "filename": file.filename,
            "size": len(content),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


@router.delete("/ontology/files/{filename}")
async def delete_ontology_file(filename: str, username: str = Depends(require_admin)):
    """删除本体文件"""
    ontology_dir = settings.ontology_dir
    safe_name = os.path.basename(filename)
    file_path = os.path.join(ontology_dir, safe_name)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")
    try:
        os.remove(file_path)
        audit_event(username, "ontology.delete", filename=safe_name)
        return {"status": "success", "message": f"文件 {safe_name} 已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
