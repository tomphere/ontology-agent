"""Security helpers shared by web routes and sync code."""

import base64
import hashlib
import hmac
import re
import secrets


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260000
SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CYPHER_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def hash_password(password: str, *, salt: str = None, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    """Return a portable PBKDF2-SHA256 password hash string."""
    if not password:
        raise ValueError("Password must not be empty")
    salt = salt or secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    encoded = base64.b64encode(digest).decode("ascii")
    return f"{PASSWORD_HASH_ALGORITHM}${iterations}${salt}${encoded}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against the configured PBKDF2-SHA256 hash format."""
    if not password or not password_hash:
        return False
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        actual = hash_password(password, salt=salt, iterations=int(iterations)).rsplit("$", 1)[-1]
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def assert_sql_identifier(value: str, field_name: str = "SQL identifier") -> str:
    if not isinstance(value, str) or not SQL_IDENTIFIER_RE.match(value):
        raise ValueError(f"{field_name} contains unsafe characters: {value!r}")
    return value


def quote_mysql_identifier(value: str, field_name: str = "MySQL identifier") -> str:
    return f"`{assert_sql_identifier(value, field_name)}`"


def quote_ansi_identifier(value: str, field_name: str = "SQL identifier") -> str:
    return f'"{assert_sql_identifier(value, field_name)}"'


def assert_cypher_identifier(value: str, field_name: str = "Cypher identifier") -> str:
    if not isinstance(value, str) or not CYPHER_IDENTIFIER_RE.match(value):
        raise ValueError(f"{field_name} contains unsafe characters: {value!r}")
    return value


def cypher_label(value: str, field_name: str = "Cypher label") -> str:
    return f":{assert_cypher_identifier(value, field_name)}" if value else ""


def validate_mapping_identifiers(mappings: list) -> list:
    """Validate dynamic identifiers that will later be interpolated into SQL/Cypher."""
    errors = []
    for idx, mapping in enumerate(mappings or []):
        prefix = f"mapping[{idx}]"
        if not isinstance(mapping, dict):
            errors.append(f"{prefix} must be an object")
            continue
        strategy = mapping.get("entity_class_strategy") or {}
        strategy_type = strategy.get("type")
        checks = [("table_name", mapping.get("table_name"))]
        if strategy_type != "relationship":
            checks.append(("node_id_column", mapping.get("node_id_column")))
        for name, value in checks:
            try:
                assert_sql_identifier(value, f"{prefix}.{name}")
            except ValueError as exc:
                errors.append(str(exc))

        if strategy_type == "dynamic_column":
            try:
                assert_sql_identifier(strategy.get("column"), f"{prefix}.entity_class_strategy.column")
            except ValueError as exc:
                errors.append(str(exc))
        elif strategy_type == "static":
            try:
                assert_cypher_identifier(strategy.get("class_name"), f"{prefix}.entity_class_strategy.class_name")
            except ValueError as exc:
                errors.append(str(exc))
        elif strategy_type == "relationship":
            for name in ("source_column", "target_column"):
                try:
                    assert_sql_identifier(strategy.get(name), f"{prefix}.entity_class_strategy.{name}")
                except ValueError as exc:
                    errors.append(str(exc))
            for name in ("source_class", "target_class", "ontology_property"):
                try:
                    assert_cypher_identifier(strategy.get(name), f"{prefix}.entity_class_strategy.{name}")
                except ValueError as exc:
                    errors.append(str(exc))

        for dp_idx, dp in enumerate(mapping.get("data_properties", [])):
            try:
                assert_sql_identifier(dp.get("column"), f"{prefix}.data_properties[{dp_idx}].column")
            except ValueError as exc:
                errors.append(str(exc))

        for vf_idx, vf in enumerate(mapping.get("vectorize_fields", [])):
            try:
                assert_sql_identifier(vf, f"{prefix}.vectorize_fields[{vf_idx}]")
            except ValueError as exc:
                errors.append(str(exc))

        for rp_idx, rp in enumerate(mapping.get("relationship_properties", [])):
            try:
                assert_sql_identifier(rp.get("column"), f"{prefix}.relationship_properties[{rp_idx}].column")
            except ValueError as exc:
                errors.append(str(exc))
            try:
                assert_cypher_identifier(
                    rp.get("property") or rp.get("ontology_property"),
                    f"{prefix}.relationship_properties[{rp_idx}].property",
                )
            except ValueError as exc:
                errors.append(str(exc))

        for op_idx, op in enumerate(mapping.get("object_properties", [])):
            try:
                assert_sql_identifier(op.get("foreign_key_column"), f"{prefix}.object_properties[{op_idx}].foreign_key_column")
            except ValueError as exc:
                errors.append(str(exc))
            for name in ("target_label", "ontology_property"):
                try:
                    assert_cypher_identifier(op.get(name), f"{prefix}.object_properties[{op_idx}].{name}")
                except ValueError as exc:
                    errors.append(str(exc))
    return errors
