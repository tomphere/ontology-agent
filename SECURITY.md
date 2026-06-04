# Security Policy

## Sensitive Data

Do not commit real credentials, API keys, database connection files, runtime data, local user information, or generated session databases.

Use `.env.example` as the only committed environment template. Keep `.env`, `.env.*`, `datasources.yaml`, `data/`, and `ontology_workspace/` local.

## Reporting

If you find a leaked secret or sensitive data exposure, rotate the affected credential immediately and remove the data from any public repository history.
