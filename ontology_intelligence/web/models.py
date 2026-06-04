# =============================================================================
# Pydantic 数据模型
# =============================================================================

from typing import Optional, List
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "user"

class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    disabled: Optional[bool] = None
    password: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class EnvUpdateRequest(BaseModel):
    content: str

class MappingUpdateRequest(BaseModel):
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    scene_id: Optional[str] = None

class OntologyDirRequest(BaseModel):
    ontology_dir: str

class SyncOntologyRequest(BaseModel):
    ontology_dir: Optional[str] = None

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "新对话"
    scene_id: Optional[str] = None

class ChatScoreRequest(BaseModel):
    score_name: str = "answer_quality"
    value: float
    comment: Optional[str] = ""

class AgentInitRequest(BaseModel):
    scene_id: Optional[str] = None

class FetchRemoteRequest(BaseModel):
    url: str

class LLMConfigRequest(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None

class LLMTestRequest(BaseModel):
    provider: str
    base_url: Optional[str] = None
    api_key: str
    model: str

class EmbeddingTestRequest(BaseModel):
    provider: str
    base_url: Optional[str] = None
    api_key: str
    model: str
    dimensions: int = 1536

class DataSourceRequest(BaseModel):
    id: Optional[str] = None
    type: str  # mysql, postgresql, oracle
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: Optional[str] = ""  # For Oracle Schema/Owner
    label: Optional[str] = ""

class DataSourceTestRequest(BaseModel):
    type: str
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: Optional[str] = ""

class ValidationRequest(BaseModel):
    ontology_file: Optional[str] = None
    datasource_id: Optional[str] = None
