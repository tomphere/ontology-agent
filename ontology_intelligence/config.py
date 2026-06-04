# =============================================================================
# 统一配置管理
# =============================================================================
# 从 .env 文件加载所有配置，消除各模块中重复的 os.getenv() 调用
# =============================================================================

import os
from pathlib import Path
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

# 自动查找项目根目录的 .env 文件
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)


class _Settings:
    """集中管理所有环境变量配置"""

    # ---- 项目根目录 ----
    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    # ---- MySQL ----
    @property
    def mysql_host(self): return os.getenv("MYSQL_HOST", "localhost")
    @property
    def mysql_port(self): return int(os.getenv("MYSQL_PORT", "3306"))
    @property
    def mysql_user(self): return os.getenv("MYSQL_USER", "root")
    @property
    def mysql_password(self): return os.getenv("MYSQL_PASSWORD", "")
    @property
    def mysql_db(self): return os.getenv("MYSQL_DB", "it_ops")
    @property
    def mysql_config(self) -> dict:
        return {
            "host": self.mysql_host,
            "port": self.mysql_port,
            "user": self.mysql_user,
            "password": self.mysql_password,
            "database": self.mysql_db,
            "charset": "utf8mb4",
        }

    # ---- Neo4j ----
    @property
    def neo4j_uri(self): return os.getenv("NEO4J_URI", "bolt://localhost:7687")
    @property
    def neo4j_http(self): return os.getenv("NEO4J_HTTP", "http://localhost:7474")
    @property
    def neo4j_user(self): return os.getenv("NEO4J_USER", "neo4j")
    @property
    def neo4j_password(self): return os.getenv("NEO4J_PASSWORD", "password")
    @property
    def neo4j_auth(self): return (self.neo4j_user, self.neo4j_password)

    # ---- 运行环境与 Web 边界 ----
    @property
    def app_env(self): return os.getenv("APP_ENV", os.getenv("ENV", "development")).lower()
    @property
    def is_production(self) -> bool:
        return self.app_env in ("prod", "production")
    @property
    def cors_origins(self) -> list:
        raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
        return [item.strip() for item in raw.split(",") if item.strip()]

    # ---- LLM 配置（统一 OpenAI 兼容接口） ----
    @property
    def llm_provider(self): return os.getenv("LLM_PROVIDER", "openai")
    @property
    def llm_base_url(self): return os.getenv("LLM_BASE_URL", "") or None
    @property
    def llm_api_key(self):
        # 优先读取统一 key，向后兼容 LLM_API_KEY
        return os.getenv("LLM_API_KEY", "") or os.getenv("LLM_API_KEY", "")
    @property
    def llm_model(self):
        return os.getenv("LLM_MODEL", "") or os.getenv("LLM_MODEL", "gpt-4o")
    @property
    def llm_embedding_model(self):
        return os.getenv("LLM_EMBEDDING_MODEL", "") or os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")
    @property
    def llm_embedding_base_url(self):
        # 允许单独配置 Embedding 的地址，否则回退到通用地址
        return os.getenv("LLM_EMBEDDING_BASE_URL", "") or os.getenv("LLM_BASE_URL", "") or None
    @property
    def llm_embedding_api_key(self):
        # 允许单独配置 Embedding 的 Key，否则回退到通用 Key
        return os.getenv("LLM_EMBEDDING_API_KEY", "") or self.llm_api_key
    @property
    def llm_embedding_dimensions(self):
        return int(os.getenv("LLM_EMBEDDING_DIMENSIONS", "1536"))

    # ---- 本体 ----
    @property
    def ontology_dir(self) -> str:
        d = os.getenv("ONTOLOGY_DIR", "")
        if not d:
            d = str(PROJECT_ROOT / "ontology_workspace")
        # 跨平台路径规范化
        return str(Path(d))
    @property
    def mapping_file(self) -> str:
        f = os.getenv("MAPPING_FILE", "database_mapping.yaml")
        p = Path(f)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return str(p)

    # ---- 插件 ----
    @property
    def plugin_dir(self) -> str:
        return str(PROJECT_ROOT / "ontology_intelligence" / "plugins")

    # ---- Kafka ----
    @property
    def kafka_broker(self): return os.getenv("KAFKA_BROKER", "localhost:9092")
    @property
    def cdc_scene_id(self): return os.getenv("CDC_SCENE_ID", "") or None

    # ---- Langfuse ----
    @property
    def langfuse_secret_key(self): return os.getenv("LANGFUSE_SECRET_KEY", "")
    @property
    def langfuse_public_key(self): return os.getenv("LANGFUSE_PUBLIC_KEY", "")
    @property
    def langfuse_host(self):
        # 兼容 LANGFUSE_BASE_URL和LANGFUSE_HOST两种命名
        return os.getenv("LANGFUSE_HOST", "") or os.getenv("LANGFUSE_BASE_URL", "")

    @property
    def langfuse_enabled(self) -> bool:
        """检查 Langfuse 配置是否完整"""
        return bool(self.langfuse_secret_key and self.langfuse_public_key and self.langfuse_host)

    # ---- Web 平台 ----
    @property
    def jwt_secret(self): return os.getenv("JWT_SECRET", "replace_with_a_long_random_secret")
    @property
    def admin_password(self): return os.getenv("ADMIN_PASSWORD", "replace_with_a_strong_admin_password")
    @property
    def admin_password_hash(self): return os.getenv("ADMIN_PASSWORD_HASH", "")

    def validate_runtime_security(self):
        """Fail fast in production when known placeholder secrets are still active."""
        if not self.is_production:
            return
        errors = []
        if self.jwt_secret == "replace_with_a_long_random_secret" or len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET must be set to a strong random value in production")
        if not self.admin_password_hash and self.admin_password == "replace_with_a_strong_admin_password":
            errors.append("ADMIN_PASSWORD_HASH or a non-placeholder ADMIN_PASSWORD is required in production")
        if self.neo4j_password in ("", "password", "your_neo4j_password"):
            errors.append("NEO4J_PASSWORD must not use the default placeholder in production")
        if errors:
            raise RuntimeError("; ".join(errors))

    # ---- 数据源配置文件 ----
    @property
    def datasources_file(self) -> str:
        f = os.getenv("DATASOURCES_FILE", "datasources.yaml")
        p = Path(f)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return str(p)
    @property
    def users_file(self) -> str:
        f = os.getenv("USERS_FILE", "data/users/users.json")
        p = Path(f)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return str(p)

    def reload(self):
        """重新加载 .env 文件"""
        load_dotenv(_env_path, override=False)

    def __repr__(self):
        return (
            f"Settings(llm_provider={self.llm_provider}, llm_model={self.llm_model}, "
            f"neo4j_uri={self.neo4j_uri}, mysql_host={self.mysql_host})"
        )


# 全局单例
settings = _Settings()
