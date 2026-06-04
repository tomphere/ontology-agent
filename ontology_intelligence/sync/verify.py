# =============================================================================
# Neo4j 数据同步校验脚本（重构自 05_verify_sync.py）
# =============================================================================
# 使用统一配置，消除 Windows 特有代码，保持完整校验逻辑
# =============================================================================

import sys
import logging
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

from ontology_intelligence.config import settings

logger = logging.getLogger(__name__)


# 终端颜色
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_pass(msg):  print(f"  {Colors.GREEN}✓ [通过]{Colors.RESET} {msg}")
def print_fail(msg):  print(f"  {Colors.RED}✗ [失败]{Colors.RESET} {msg}")
def print_warn(msg):  print(f"  {Colors.YELLOW}⚠ [警告]{Colors.RESET} {msg}")
def print_info(msg):  print(f"  {Colors.BLUE}ℹ [信息]{Colors.RESET} {msg}")
def print_fix(msg):   print(f"    {Colors.YELLOW}→ 修复方法: {msg}{Colors.RESET}")
def print_section(title):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}  {title}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")


def check_connection():
    print_section("校验 1/8：Neo4j 连接性")
    try:
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=settings.neo4j_auth)
        with driver.session() as session:
            result = session.run("RETURN 1 AS test").single()
            if result and result["test"] == 1:
                print_pass(f"成功连接到 Neo4j: {settings.neo4j_uri}")
                return driver
    except ServiceUnavailable:
        print_fail(f"无法连接到 Neo4j: {settings.neo4j_uri}")
        print_fix("请检查 Neo4j 是否正在运行，以及 .env 中的地址和端口")
        return None
    except AuthError:
        print_fail(f"Neo4j 认证失败: 用户名={settings.neo4j_user}")
        print_fix("请检查 .env 中 NEO4J_USER 和 NEO4J_PASSWORD")
        return None
    except Exception as e:
        print_fail(f"连接异常: {e}")
        return None


def check_n10s_config(session):
    print_section("校验 2/8：n10s 插件配置")
    try:
        result = session.run("CALL n10s.graphconfig.show() YIELD param, value RETURN param, value")
        configs = {r["param"]: r["value"] for r in result}
        if configs:
            print_pass(f"n10s 已初始化，共 {len(configs)} 个配置项")
            handle_uris = configs.get("handleVocabUris", "未设置")
            if handle_uris == "IGNORE":
                print_pass(f"handleVocabUris = IGNORE")
            else:
                print_warn(f"handleVocabUris = {handle_uris}（推荐 IGNORE）")
            return True
        else:
            print_fail("n10s 配置为空")
            return False
    except Exception as e:
        if "no procedure" in str(e).lower() or "unknown" in str(e).lower():
            print_fail("n10s 插件未安装或未启用")
        else:
            print_fail(f"n10s 配置检查异常: {e}")
        return False


def check_ontology_import(session):
    print_section("校验 3/8：本体导入 (TBox)")
    result = session.run("MATCH (c:Class) RETURN count(c) AS cnt").single()
    class_count = result["cnt"] if result else 0
    if class_count > 0:
        print_pass(f"已导入 {class_count} 个 Class 节点")
        classes = session.run("MATCH (c:Class) RETURN c.name AS name ORDER BY name")
        names = [r["name"] for r in classes if r["name"]]
        print_info(f"类列表: {', '.join(names)}")
    else:
        print_fail("未找到任何 Class 节点")
        print_fix("检查 ONTOLOGY_DIR 目录下是否有 .rdf/.owl 文件")
        return False

    result = session.run("MATCH ()-[r:SCO]->() RETURN count(r) AS cnt").single()
    sco_count = result["cnt"] if result else 0
    if sco_count > 0:
        print_pass(f"已建立 {sco_count} 条 SCO 继承关系")
    else:
        print_warn("未找到 SCO 关系")
    return True


def check_instance_data(session):
    print_section("校验 4/8：实例数据 (ABox)")
    result = session.run("""
        MATCH (n) WHERE NOT n:Class AND NOT n:Relationship AND NOT n:_GraphConfig
              AND NOT n:_NsPrefDef AND NOT n:Resource
        RETURN labels(n) AS labels, count(n) AS cnt ORDER BY cnt DESC
    """)
    total_nodes = 0
    for r in result:
        labels = [l for l in r["labels"] if not l.startswith("_")]
        if labels:
            total_nodes += r["cnt"]
            print_info(f"  {':'.join(labels)} → {r['cnt']} 个")
    if total_nodes > 0:
        print_pass(f"共同步 {total_nodes} 个实例节点")
        return True
    else:
        print_fail("未找到任何实例节点")
        print_fix("请检查 MySQL 连接和 database_mapping.yaml 配置")
        return False


def check_relationships(session):
    print_section("校验 5/8：关系完整性")
    result = session.run("""
        MATCH ()-[r]->() WHERE type(r) <> 'SCO' AND type(r) <> 'DOMAIN' AND type(r) <> 'RANGE'
        RETURN type(r) AS rel_type, count(r) AS cnt ORDER BY cnt DESC
    """)
    rel_stats = [(r["rel_type"], r["cnt"]) for r in result]
    total_rels = sum(cnt for _, cnt in rel_stats)
    if total_rels > 0:
        print_pass(f"共建立 {total_rels} 条实例关系")
        for rel_type, count in rel_stats:
            print_info(f"  :{rel_type} → {count} 条")
        return True
    else:
        print_fail("未找到实例关系")
        return False


def check_vector_index(session):
    print_section("校验 6/8：向量索引与 Embedding")
    try:
        result = session.run("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name, type")
        indexes = list(result)
        if indexes:
            print_pass(f"向量索引已创建: {', '.join(r['name'] for r in indexes)}")
        else:
            print_warn("未创建向量索引")
    except Exception:
        print_warn("无法查询索引信息")

    result = session.run("MATCH (t:Ticket) WHERE t.issue_description_embedding IS NOT NULL RETURN count(t) AS cnt").single()
    embed_count = result["cnt"] if result else 0
    result2 = session.run("MATCH (t:Ticket) RETURN count(t) AS cnt").single()
    total_tickets = result2["cnt"] if result2 else 0
    if total_tickets == 0:
        print_warn("没有 Ticket 节点")
    elif embed_count == total_tickets:
        print_pass(f"所有 {embed_count}/{total_tickets} 个 Ticket 已向量化")
    elif embed_count > 0:
        print_warn(f"部分向量化: {embed_count}/{total_tickets}")
    else:
        print_warn(f"没有 Ticket 包含 embedding 属性")
    return True


def check_materialized_labels(session):
    print_section("校验 7/8：物化推理标签")
    result = session.run("MATCH (n:Server) RETURN n.id AS id, labels(n) AS labels LIMIT 3")
    servers = list(result)
    if not servers:
        print_warn("没有 Server 节点，跳过")
        return True
    all_ok = True
    for s in servers:
        if "IT_Asset" in s["labels"]:
            print_pass(f"Server '{s['id']}' 包含父类标签 IT_Asset")
        else:
            print_fail(f"Server '{s['id']}' 未包含 IT_Asset")
            all_ok = False
    return all_ok


def check_ontology_semantics(session):
    print_section("校验 8/8：本体语义描述")
    result = session.run("""
        MATCH (c:Class) WHERE c.comment IS NOT NULL OR c.rdfs__comment IS NOT NULL
        RETURN c.name AS name, COALESCE(c.comment, c.rdfs__comment) AS desc ORDER BY c.name
    """)
    records = list(result)
    if records:
        print_pass(f"共 {len(records)} 个类有语义描述")
        for r in records:
            desc = r["desc"]
            if isinstance(desc, list):
                desc = desc[0] if desc else "无"
            print_info(f"  {r['name']}: {str(desc)[:60]}...")
    else:
        print_warn("没有 Class 包含 rdfs:comment")
    return True


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print(f"\n{Colors.BOLD}{'#'*60}{Colors.RESET}")
    print(f"{Colors.BOLD}#  企业级本体智能体 - Neo4j 数据同步校验工具 v3.0  #{Colors.RESET}")
    print(f"{Colors.BOLD}{'#'*60}{Colors.RESET}")
    print(f"\n{Colors.BLUE}目标: {settings.neo4j_uri}{Colors.RESET}")

    driver = check_connection()
    if not driver:
        print(f"\n{Colors.RED}连接失败，无法继续校验。{Colors.RESET}")
        return

    results = {}
    with driver.session() as session:
        results["n10s 配置"] = check_n10s_config(session)
        results["本体导入"] = check_ontology_import(session)
        results["实例数据"] = check_instance_data(session)
        results["关系完整性"] = check_relationships(session)
        results["向量索引"] = check_vector_index(session)
        results["物化推理"] = check_materialized_labels(session)
        results["语义描述"] = check_ontology_semantics(session)
    driver.close()

    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}  校验汇总{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
    all_passed = True
    for name, passed in results.items():
        icon = f"{Colors.GREEN}✓{Colors.RESET}" if passed else f"{Colors.RED}✗{Colors.RESET}"
        print(f"  {icon} {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n{Colors.GREEN}{Colors.BOLD}  🎉 所有校验通过！{Colors.RESET}\n")
    else:
        failed = [n for n, p in results.items() if not p]
        print(f"\n{Colors.RED}{Colors.BOLD}  ⚠ 未通过: {', '.join(failed)}{Colors.RESET}\n")


if __name__ == "__main__":
    main()
