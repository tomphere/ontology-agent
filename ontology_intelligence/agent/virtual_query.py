# =============================================================================
# Virtual Query Engine - Query original databases without migration to Neo4j
# =============================================================================
# In virtual mode, the agent translates natural language to SQL and queries
# the original database directly, instead of generating Cypher for Neo4j.
# =============================================================================

import os
import re
import logging
from typing import Optional

from langchain_core.tools import StructuredTool

from ontology_intelligence.config import settings

logger = logging.getLogger(__name__)


def build_virtual_schema(mapping_config: dict, datasource_config: dict) -> str:
    """
    Build a SQL schema description from mapping YAML and datasource config.
    This description is injected into the LLM prompt so it can generate correct SQL.
    """
    schema_parts = []
    mappings = mapping_config.get('mappings', [])

    for m in mappings:
        table = m.get('table_name', '')
        props = m.get('data_properties', [])
        obj_props = m.get('object_properties', [])

        columns = []
        # Primary key
        pk = m.get('node_id_column', 'id')
        columns.append(f"  {pk} (PRIMARY KEY)")

        # Data properties
        for dp in props:
            col = dp.get('column', '')
            onto_prop = dp.get('ontology_property', '')
            columns.append(f"  {col}  -- maps to ontology: {onto_prop}")

        # Foreign keys (object properties)
        for op in obj_props:
            fk = op.get('foreign_key_column', '')
            target = op.get('target_label', '')
            rel = op.get('ontology_property', '')
            direction = op.get('direction', 'OUTGOING')
            columns.append(f"  {fk} (FK -> {target})  -- relationship: {rel} ({direction})")

        schema_parts.append(f"TABLE {table}:\n" + "\n".join(columns))

    db_info = f"Database: {datasource_config.get('type', 'mysql')} - {datasource_config.get('database', '')}"
    return db_info + "\n\n" + "\n\n".join(schema_parts)


def execute_virtual_query(sql: str, datasource_config: dict) -> list:
    """
    Safely execute a SQL query against the original database.
    Only SELECT queries are allowed for security.
    """
    # Security: only allow SELECT queries
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith('SELECT'):
        raise ValueError("Only SELECT queries are allowed in virtual mode")
    sql_without_trailing_semicolon = sql.strip().rstrip(';')
    if ';' in sql_without_trailing_semicolon:
        raise ValueError("Only a single SELECT statement is allowed")
    if re.search(r'(--|/\*|\*/)', sql):
        raise ValueError("SQL comments are not allowed in virtual mode")

    # Check for dangerous keywords
    dangerous = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'TRUNCATE', 'CREATE', 'EXEC']
    for word in dangerous:
        if re.search(rf'\b{word}\b', sql_stripped):
            raise ValueError(f"Query contains forbidden keyword: {word}")

    ds_type = datasource_config.get('type', 'mysql').lower()

    try:
        if ds_type == 'mysql':
            import pymysql
            conn = pymysql.connect(
                host=datasource_config['host'],
                port=int(datasource_config.get('port', 3306)),
                user=datasource_config['user'],
                password=datasource_config.get('password', ''),
                database=datasource_config['database'],
                connect_timeout=10,
            )
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        elif ds_type == 'postgresql':
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(
                host=datasource_config['host'],
                port=int(datasource_config.get('port', 5432)),
                user=datasource_config['user'],
                password=datasource_config.get('password', ''),
                database=datasource_config['database'],
                connect_timeout=10,
            )
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            raise ValueError(f"Unsupported database type for virtual query: {ds_type}")

        # Execute with row limit for safety
        if 'LIMIT' not in sql_stripped:
            sql = sql.rstrip(';') + ' LIMIT 100'

        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()

        # Convert to list of dicts
        if ds_type == 'mysql':
            return [dict(row) for row in rows]
        else:
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"[Virtual Query] SQL execution failed: {e}")
        raise


def build_virtual_query_tool(
    schema_description: str,
    datasource_config: dict,
) -> StructuredTool:
    """
    Build a LangChain StructuredTool that the agent can use to query
    the original database via SQL in virtual mode.
    """

    def query_database(sql_query: str) -> str:
        """Execute a SQL query against the original database and return results."""
        try:
            results = execute_virtual_query(sql_query, datasource_config)
            if not results:
                return "Query returned no results."
            # Format as readable text
            header = list(results[0].keys())
            lines = [" | ".join(str(row.get(h, '')) for h in header) for row in results[:50]]
            return f"Columns: {', '.join(header)}\n" + "\n".join(lines) + f"\n\n({len(results)} rows returned)"
        except ValueError as e:
            return f"Query rejected: {e}"
        except Exception as e:
            return f"Query error: {e}"

    return StructuredTool.from_function(
        func=query_database,
        name="query_database",
        description=(
            f"Execute a SQL query against the original database. "
            f"Use standard SQL syntax. Only SELECT queries are allowed.\n\n"
            f"Database Schema:\n{schema_description}"
        ),
    )


# SQL Generation Prompt Template
SQL_GENERATION_TEMPLATE = """You are an expert SQL developer. Given the following database schema and a user question,
generate a correct SQL query to answer the question.

IMPORTANT RULES:
1. Use ONLY standard SQL syntax compatible with {db_type}
2. Always use case-insensitive matching: use LOWER() or ILIKE for string comparisons
3. Add LIMIT 100 to prevent excessive data retrieval
4. Only generate SELECT queries - never modify data
5. Use table aliases for clarity
6. If the question cannot be answered with the available schema, explain why

Database Schema:
{schema}

User Question: {question}

Generate the SQL query:"""
