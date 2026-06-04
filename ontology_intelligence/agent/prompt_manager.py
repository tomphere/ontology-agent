"""Prompt 管理模块（带容错和本地备份）

核心设计原则：
1. Langfuse 正常时：从云端加载 Prompt（支持热更新）
2. Langfuse 不可用时：自动降级到本地备份（主功能不受影响）
3. 所有操作带超时和异常捕获，不阻塞主流程
"""

import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# 本地备份 Prompt（与 Langfuse 中保持一致，作为降级兜底）
# =============================================================================

BACKUP_PROMPTS = {
    "kg-agent-system": """你是一个企业级知识图谱智能分析助手。

【角色定位】
你运行于合规受控的企业知识图谱智能引擎中，负责基于 Neo4j 知识图谱回答用户的问题。

【执行规范】
1. 只要用户提问，你必须优先通过调用 Knowledge_Graph_Query 工具来查询数据！不要尝试自己思考或回答不知道！
2. 完全基于图谱返回的数据回答，严禁臆造或编造数据。

【防死循环军规】
1. 如果你使用工具后，工具返回了"未查询到"，这说明当前查询参数在数据库中没有任何符合条件的数据。
2. 此时，绝对禁止再次使用完全一模一样的参数去重复死循环调用相同的工具！
3. 你可以尝试换一种说法重新查询（最多可以重试 1 次），如果重试依然无果，请果断停止调用工具，直接回复用户"未能在知识图谱中查出"，结束当前回复回合！""",

    "kg-cypher-generation": """你是一个精通 Neo4j Cypher 查询语言的图数据查询专家。
请根据以下图谱结构信息和语义定义，将用户的自然语言问题转化为准确的 Cypher 查询语句。

============================================================
【图谱 Schema】
{schema}

{ontology_semantics}
{relationship_semantics}
============================================================

【查询规范】
1. 关系类型严格绑定：你的每一条边 (a)-[:REL]->(b) 必须存在于上方 The relationships: 列表中！
2. 属性字段优先原则：当查询实体等级、状态或风险分值时，必须直接使用属性进行过滤。
3. 只能使用上文中明确列出的属性，不准凭空捏造不在 Schema Node properties 里的字段。
4. 字符串过滤必须使用 toLower() 函数或正则 (?i) 实现"不区分大小写"的匹配。

{few_shots}
用户问题: {question}

重要且严格的规约：
返回的结果必须是纯文本的且可直接执行的 Cypher 语句，绝对不要包含任何 markdown 代码块标记，也不要添加任何解释性文字。只输出 Cypher 语句本身！""",

    "kg-report-generation": """你是专业的知识图谱汇报助手。
请完全无条件信任以下 Information 区域返回的数据，并整理输出给用户。

【最高优先级军规】：
1. 无论用户问题是什么语气，只要 Information 数组不为空，就代表图数据库精确查出了数据！你必须直接回复"有的，查询结果如下："并老老实实播报所有的实体名词。
2. 只有当 Information 明确为 [] 时，才说明该条件下没有任何数据，此时你才可以说"未查询到数据"。
3. **针对字段缺失的处理**：Information 中有多少字段就播报多少字段，如果某个字段值是 null，跳过该字段或标注为"未知"即可，**绝对禁止因为个别字段缺失，就把整个查询结果粗暴地总结为"暂无详情"**。绝对不许编造未返回的日期或案发事实！

Information:
{context}

Question: {question}
Helpful Answer:""",
}


class PromptManager:
    """Prompt 管理器，带多级降级策略
    
    降级优先级：
    1. 内存缓存（最快，避免重复请求）
    2. Langfuse 云端（可热更新）
    3. 本地备份（保底，Langfuse 不可用时使用）
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._cache: Dict[str, Any] = {}
        self._langfuse_available = True
        self._initialized = True
    
    def _get_langfuse_client(self):
        """获取 Langfuse 客户端（带超时和容错）"""
        try:
            from langfuse import Langfuse
            from ontology_intelligence.config import settings
            
            if not settings.langfuse_enabled:
                return None
            
            client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                timeout=5,
            )
            return client
        except Exception as e:
            logger.warning(f"[PromptManager] Langfuse 客户端创建失败: {e}")
            return None
    
    def get_prompt(self, name: str, label: str = "production", **variables) -> str:
        """获取 Prompt 并渲染变量
        
        Args:
            name: Prompt 名称（对应 Langfuse 中的 Prompt name）
            label: 环境标签（production / development）
            **variables: 运行时变量，用于替换 Prompt 中的 {{variable}} 占位符
        
        Returns:
            渲染后的 Prompt 字符串
        
        示例:
            prompt = manager.get_prompt(
                "kg-cypher-generation",
                schema=neo4j_schema,
                ontology_semantics=semantics,
                question=user_question
            )
        """
        # 优先级 1: 内存缓存
        cache_key = f"{name}:{label}"
        if cache_key in self._cache:
            prompt_obj = self._cache[cache_key]
            try:
                return prompt_obj.compile(**variables)
            except Exception:
                # 缓存的 prompt 编译失败，清除缓存重试
                del self._cache[cache_key]
        
        # 优先级 2: Langfuse 云端
        if self._langfuse_available:
            try:
                client = self._get_langfuse_client()
                if client:
                    prompt_obj = client.get_prompt(name, label=label)
                    self._cache[cache_key] = prompt_obj
                    logger.info(f"[PromptManager] 从 Langfuse 加载: {name} (v{prompt_obj.version})")
                    return prompt_obj.compile(**variables)
            except Exception as e:
                logger.warning(f"[PromptManager] Langfuse 加载失败，降级到本地备份: {e}")
                self._langfuse_available = False
        
        # 优先级 3: 本地备份
        if name in BACKUP_PROMPTS:
            logger.info(f"[PromptManager] 使用本地备份: {name}")
            template = BACKUP_PROMPTS[name]
            try:
                return template.format(**variables)
            except KeyError as e:
                # 变量不匹配，返回原始模板
                logger.warning(f"[PromptManager] 变量不匹配: {e}，返回原始模板")
                return template
        
        # 优先级 4: 空字符串（最后防线）
        logger.error(f"[PromptManager] 未找到 Prompt: {name}")
        return ""
    
    def get_raw_prompt(self, name: str, label: str = "production") -> Optional[str]:
        """获取原始 Prompt 模板（不渲染变量）
        
        用于查看 Prompt 内容或调试。
        """
        cache_key = f"{name}:{label}"
        if cache_key in self._cache:
            return self._cache[cache_key].prompt
        
        if self._langfuse_available:
            try:
                client = self._get_langfuse_client()
                if client:
                    prompt_obj = client.get_prompt(name, label=label)
                    self._cache[cache_key] = prompt_obj
                    return prompt_obj.prompt
            except Exception as e:
                logger.warning(f"[PromptManager] 获取原始 Prompt 失败: {e}")
                self._langfuse_available = False
        
        return BACKUP_PROMPTS.get(name)
    
    def refresh_cache(self, name: str = None):
        """刷新缓存
        
        Args:
            name: 指定 Prompt 名称，None 则清除所有缓存
        """
        if name:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{name}:")]
            for k in keys_to_remove:
                del self._cache[k]
            logger.info(f"[PromptManager] 已刷新缓存: {name}")
        else:
            self._cache.clear()
            self._langfuse_available = True
            logger.info("[PromptManager] 已清除所有缓存")
    
    def is_langfuse_available(self) -> bool:
        """检查 Langfuse 是否可用"""
        return self._langfuse_available


# 全局单例
prompt_manager = PromptManager()
