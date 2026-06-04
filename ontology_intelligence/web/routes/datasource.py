# 多数据源管理路由
import os
import uuid
import yaml
import logging
from fastapi import APIRouter, HTTPException, Depends, Query

from ontology_intelligence.config import settings
from ontology_intelligence.security import assert_sql_identifier, quote_ansi_identifier, quote_mysql_identifier
from ontology_intelligence.web.models import DataSourceRequest, DataSourceTestRequest
from ontology_intelligence.web.routes.auth import verify_token, require_admin
from ontology_intelligence.web.audit import audit_event

router = APIRouter(tags=["datasource"])
logger = logging.getLogger("web-platform")


def _load_datasources() -> list:
    path = settings.datasources_file
    if not os.path.exists(path):
        return []
    if os.path.isdir(path):
        logger.error(f"[数据源] 路径 {path} 是一个目录，而不是文件！请检查 Docker 挂载。")
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data.get("datasources", []) if data else []
    except Exception as e:
        logger.error(f"[数据源] 加载失败: {e}")
        return []


def _save_datasources(datasources: list):
    path = settings.datasources_file
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump({"datasources": datasources}, f, allow_unicode=True, default_flow_style=False)


def _get_connection(ds: dict):
    """根据数据源类型创建连接"""
    ds_type = ds["type"].lower()
    if ds_type == "mysql":
        import pymysql
        return pymysql.connect(
            host=ds["host"], port=ds["port"], user=ds["user"],
            password=ds["password"], database=ds["database"],
            charset="utf8mb4", connect_timeout=5,
        )
    elif ds_type == "postgresql":
        import psycopg2
        return psycopg2.connect(
            host=ds["host"], port=ds["port"], user=ds["user"],
            password=ds["password"], dbname=ds["database"],
            connect_timeout=5,
        )
    elif ds_type == "oracle":
        import oracledb
        dsn = f"{ds['host']}:{ds['port']}/{ds['database']}"
        return oracledb.connect(user=ds["user"], password=ds["password"], dsn=dsn)
    else:
        raise ValueError(f"不支持的数据库类型: {ds_type}")


@router.get("/datasource/list")
async def list_datasources(username: str = Depends(verify_token)):
    datasources = _load_datasources()
    # 隐藏密码
    safe = []
    for ds in datasources:
        d = dict(ds)
        d["password"] = "***"
        safe.append(d)
    return {"datasources": safe}


@router.post("/datasource/add")
async def add_datasource(req: DataSourceRequest, username: str = Depends(require_admin)):
    datasources = _load_datasources()
    ds_id = req.id or f"ds-{str(uuid.uuid4())[:8]}"
    ds = {
        "id": ds_id, "type": req.type, "host": req.host, "port": req.port,
        "user": req.user, "password": req.password, "database": req.database,
        "schema": req.schema or "",
        "label": req.label or f"{req.type}://{req.host}:{req.port}/{req.database}",
    }
    # 更新或添加
    existing = next((i for i, d in enumerate(datasources) if d["id"] == ds_id), None)
    if existing is not None:
        datasources[existing] = ds
    else:
        datasources.append(ds)
    _save_datasources(datasources)
    audit_event(username, "datasource.save", datasource_id=ds_id, type=req.type, host=req.host, database=req.database)
    return {"status": "success", "id": ds_id, "message": "数据源已保存"}


@router.delete("/datasource/{ds_id}")
async def delete_datasource(ds_id: str, username: str = Depends(require_admin)):
    datasources = _load_datasources()
    datasources = [d for d in datasources if d["id"] != ds_id]
    _save_datasources(datasources)
    audit_event(username, "datasource.delete", datasource_id=ds_id)
    return {"status": "success"}


@router.post("/datasource/test")
async def test_datasource(req: DataSourceTestRequest, username: str = Depends(verify_token)):
    try:
        conn = _get_connection({
            "type": req.type, "host": req.host, "port": req.port,
            "user": req.user, "password": req.password, "database": req.database,
            "schema": req.schema or "",
        })
        conn.close()
        return {"success": True, "message": f"连接成功: {req.host}:{req.port}/{req.database}"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)[:200]}"}


@router.get("/datasource/{ds_id}/tables")
async def get_tables(ds_id: str, username: str = Depends(verify_token)):
    datasources = _load_datasources()
    ds = next((d for d in datasources if d["id"] == ds_id), None)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        conn = _get_connection(ds)
        ds_type = ds["type"].lower()
        if ds_type == "mysql":
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
        elif ds_type == "postgresql":
            cursor = conn.cursor()
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            tables = [row[0] for row in cursor.fetchall()]
        elif ds_type == "oracle":
            cursor = conn.cursor()
            owner = ds.get("schema")
            if owner:
                cursor.execute("SELECT table_name FROM all_tables WHERE owner = :owner ORDER BY table_name", {"owner": owner.upper()})
            else:
                cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
            tables = [row[0] for row in cursor.fetchall()]
        else:
            tables = []
        conn.close()
        return {"tables": tables}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/datasource/{ds_id}/tables/{table_name}/columns")
async def get_columns(ds_id: str, table_name: str, username: str = Depends(verify_token)):
    try:
        assert_sql_identifier(table_name, "table_name")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    datasources = _load_datasources()
    ds = next((d for d in datasources if d["id"] == ds_id), None)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        conn = _get_connection(ds)
        ds_type = ds["type"].lower()
        columns = []
        if ds_type == "mysql":
            cursor = conn.cursor()
            cursor.execute(f"DESCRIBE {quote_mysql_identifier(table_name, 'table_name')}")
            for row in cursor.fetchall():
                columns.append({"name": row[0], "type": row[1], "nullable": row[2] == "YES", "key": row[3] or ""})
        elif ds_type == "postgresql":
            cursor = conn.cursor()
            cursor.execute(f"""SELECT column_name, data_type, is_nullable FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public' ORDER BY ordinal_position""", (table_name,))
            for row in cursor.fetchall():
                columns.append({"name": row[0], "type": row[1], "nullable": row[2] == "YES", "key": ""})
        elif ds_type == "oracle":
            cursor = conn.cursor()
            owner = ds.get("schema")
            if owner:
                cursor.execute(f"""SELECT column_name, data_type, nullable FROM all_tab_columns
                    WHERE table_name = :tn AND owner = :owner ORDER BY column_id""", 
                    {"tn": table_name.upper(), "owner": owner.upper()})
            else:
                cursor.execute(f"""SELECT column_name, data_type, nullable FROM user_tab_columns
                    WHERE table_name = :tn ORDER BY column_id""", {"tn": table_name.upper()})
            for row in cursor.fetchall():
                columns.append({"name": row[0], "type": row[1], "nullable": row[2] == "Y", "key": ""})
        conn.close()
        return {"table": table_name, "columns": columns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/datasource/{ds_id}/tables/{table_name}/preview")
async def preview_table(ds_id: str, table_name: str, limit: int = Query(50, ge=1, le=200),
                        username: str = Depends(verify_token)):
    try:
        assert_sql_identifier(table_name, "table_name")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    datasources = _load_datasources()
    ds = next((d for d in datasources if d["id"] == ds_id), None)
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    try:
        conn = _get_connection(ds)
        ds_type = ds["type"].lower()
        if ds_type == "mysql":
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(f"SELECT * FROM {quote_mysql_identifier(table_name, 'table_name')} LIMIT {limit}")
        elif ds_type == "postgresql":
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(f"SELECT * FROM {quote_ansi_identifier(table_name, 'table_name')} LIMIT {limit}")
        elif ds_type == "oracle":
            owner = ds.get("schema")
            table_ident = quote_ansi_identifier(table_name.upper(), 'table_name')
            if owner:
                table_ident = f"{quote_ansi_identifier(owner.upper(), 'owner')}.{table_ident}"
            
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table_ident} WHERE ROWNUM <= {limit}")
            cols = [d[0] for d in cursor.description]
            rows_raw = cursor.fetchall()
            conn.close()
            return {"table": table_name, "rows": [dict(zip(cols, r)) for r in rows_raw], "total": len(rows_raw)}
        else:
            conn.close()
            return {"table": table_name, "rows": [], "total": 0}

        rows = cursor.fetchall()
        conn.close()
        # Convert non-serializable types to str
        safe_rows = []
        for row in rows:
            safe_row = {}
            for k, v in row.items():
                if isinstance(v, (str, int, float, bool, type(None))):
                    safe_row[k] = v
                else:
                    safe_row[k] = str(v)
            safe_rows.append(safe_row)
        return {"table": table_name, "rows": safe_rows, "total": len(safe_rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览失败: {e}")
