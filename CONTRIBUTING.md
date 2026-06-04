# Contributing

Thanks for your interest in Ontology Intelligence Agent.

This project is maintained as open-source infrastructure for ontology-driven knowledge graphs, Neo4j synchronization, and LLM agent workflows.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env
```

Edit `.env` with local development values only. Never commit real credentials.

## Validation

Before opening a pull request, run the checks that match your change:

```bash
python3 -m compileall -q ontology_intelligence tests
cd frontend && npm run build
```

When external services are available, also run:

```bash
make sync
make verify
```

## Pull Requests

Please keep pull requests focused. Include:

- A short description of the problem and solution
- Screenshots for UI changes
- Validation commands you ran
- Notes about external service dependencies, if any

## Security And Privacy

Do not commit `.env`, `.env.*`, `datasources.yaml`, runtime data, local databases, API keys, passwords, user data, or generated session files.

If you find a security issue, rotate any exposed credentials immediately and report the issue privately before publishing details.
