# Ontology Intelligence Agent

[中文](#中文) | [English](#english)

## 中文

# 企业级本体智能体

Ontology Intelligence Agent 是一个开源的本体驱动知识图谱与 LLM Agent 基础设施项目。它结合 FastAPI、React、Neo4j、RDF/OWL 解析、关系型数据到图谱的映射、CDC 同步和自然语言图谱问答，帮助团队构建可维护的本体知识图谱应用。

本项目由 primary maintainer 持续维护，目标是把关系型业务数据通过本体映射同步到 Neo4j 知识图谱，并通过 LLM/Agent 提供自然语言查询、故障排查和可视化工作台。

## 维护状态

- **维护角色**：Primary maintainer
- **当前版本**：`v0.1.0`
- **维护重点**：架构、发布、文档、issue triage、隐私/安全清理、本体映射、图谱同步和 LLM Agent 工作流
- **开源价值**：连接 semantic-web 工具、Neo4j 图谱同步和实际 LLM Agent 工作流，服务于构建本体驱动知识图谱应用的团队

## 架构

```text
┌─────────────────────────────────────────────────────────┐
│                    Web 前端 (React + Vite)               │
├─────────────────────────────────────────────────────────┤
│                FastAPI 后端 (Python 3.12)                │
│   ┌──────────┬──────────┬──────────┬──────────┐         │
│   │ 认证管理 │ 同步引擎 │ LLM 工厂 │ 图谱浏览 │         │
│   ├──────────┼──────────┼──────────┼──────────┤         │
│   │ 本体管理 │ 数据源   │ 映射校验 │ 智能体   │         │
│   └──────────┴──────────┴──────────┴──────────┘         │
├──────────────────┬──────────────────────────────────────┤
│     Neo4j        │           MySQL / PG / Oracle        │
│   (知识图谱)     │         (业务关系型数据库)             │
└──────────────────┴──────────────────────────────────────┘
```

## 核心功能

- **本体驱动的数据同步**：基于 YAML 映射配置，将关系型数据同步为 Neo4j 知识图谱
- **多模型 LLM 支持**：统一 OpenAI 兼容 API，支持 OpenAI / OpenRouter / Qwen / DeepSeek / Ollama 等
- **智能体对话**：自然语言查询知识图谱，支持复杂推理和语义检索
- **数据工作台**：本体文件上传、多数据源管理、数据映射编辑和一致性校验
- **图谱可视化**：力导向图谱浏览，支持节点信息、关系注释和本体约束开关
- **实时同步**：通过 Kafka / Debezium 支持 CDC 增量数据同步

## 快速开始

### 开发环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env
make dev
```

也可以分别启动：

```bash
make dev-backend     # http://localhost:8888
make dev-frontend    # http://localhost:3000
```

### Docker 部署

```bash
bash scripts/deploy.sh
```

或手动启动：

```bash
docker compose up -d
docker compose -f docker-compose.app.yml up -d --build
```

## 项目结构

```text
ontology-intelligence/
├── ontology_intelligence/     # Python 主包
│   ├── config.py              # 统一配置管理
│   ├── sync/                  # 同步引擎
│   ├── agent/                 # Agent 和 LLM 工厂
│   ├── plugins/               # 可插拔工具
│   └── web/                   # FastAPI 后端
├── frontend/                  # React 前端
├── docs/                      # 发布、运维和项目说明文档
├── scripts/                   # 运维脚本
├── database_mapping.yaml      # 映射配置
├── docker-compose.yml         # 基础设施编排
├── docker-compose.app.yml     # 应用编排
├── Dockerfile                 # 容器构建
├── Makefile                   # 开发命令
└── requirements.txt           # Python 依赖
```

## LLM 配置

在 `.env` 中配置 LLM 后端：

| Provider | LLM_PROVIDER | 说明 |
|----------|--------------|------|
| OpenAI | `openai` | OpenAI API |
| OpenRouter | `openrouter` | OpenRouter 兼容端点 |
| 通义千问 | `qwen` | DashScope / OpenAI 兼容端点 |
| DeepSeek | `deepseek` | DeepSeek 兼容端点 |
| Ollama | `ollama` | 本地 Ollama 服务 |
| 自定义 | `openai` | 任意 OpenAI 兼容 API |

## 贡献与路线图

- [Contributing Guide](CONTRIBUTING.md)
- [Roadmap](docs/ROADMAP.md)
- [GitHub Publishing Checklist](docs/GITHUB_PUBLISHING.md)

## 安全与隐私

不要提交 `.env`、`.env.*`、`datasources.yaml`、运行时数据、本地数据库、API key、数据库密码、JWT secret 或用户数据。发布前请参考 [SECURITY.md](SECURITY.md) 和 [docs/GITHUB_PUBLISHING.md](docs/GITHUB_PUBLISHING.md)。

## 许可证

MIT

---

## English

# Ontology Intelligence Agent

Ontology Intelligence Agent is an open-source infrastructure project for ontology-driven knowledge graphs and LLM agents. It combines FastAPI, React, Neo4j, RDF/OWL parsing, relational-to-graph mapping, CDC synchronization, and natural-language graph QA.

The project is maintained by a primary maintainer and focuses on synchronizing relational data into Neo4j knowledge graphs through ontology mappings, then exposing natural-language querying, troubleshooting, and graph visualization workflows through LLM agents.

## Maintainer Status

- **Maintainer role**: Primary maintainer
- **Current release**: `v0.1.0`
- **Maintenance focus**: architecture, releases, documentation, issue triage, privacy/security cleanup, ontology mapping, graph synchronization, and LLM agent workflows
- **Open-source value**: bridges semantic-web tooling, Neo4j graph synchronization, and practical LLM agent workflows for teams building ontology-backed knowledge graph applications

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                  Web Frontend (React + Vite)             │
├─────────────────────────────────────────────────────────┤
│                FastAPI Backend (Python 3.12)             │
│   ┌──────────┬──────────┬──────────┬──────────┐         │
│   │   Auth   │   Sync   │ LLM Core │  Graph   │         │
│   ├──────────┼──────────┼──────────┼──────────┤         │
│   │ Ontology │ Sources  │ Mapping  │  Agent   │         │
│   └──────────┴──────────┴──────────┴──────────┘         │
├──────────────────┬──────────────────────────────────────┤
│     Neo4j        │           MySQL / PG / Oracle        │
│ Knowledge Graph  │          Relational Sources           │
└──────────────────┴──────────────────────────────────────┘
```

## Features

- **Ontology-driven synchronization**: sync relational data into Neo4j using YAML mapping contracts
- **Multi-provider LLM support**: unified OpenAI-compatible API support for OpenAI, OpenRouter, Qwen, DeepSeek, Ollama, and custom endpoints
- **Agent chat**: natural-language graph querying, semantic search, and reasoning over graph evidence
- **Data workbench**: ontology upload, multi-source management, mapping editing, and validation
- **Graph visualization**: force-directed graph exploration with node details, relationship annotations, and ontology constraints
- **CDC synchronization**: Kafka / Debezium support for incremental data synchronization

## Quick Start

### Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env
make dev
```

Or start backend and frontend separately:

```bash
make dev-backend     # http://localhost:8888
make dev-frontend    # http://localhost:3000
```

### Docker

```bash
bash scripts/deploy.sh
```

Or start services manually:

```bash
docker compose up -d
docker compose -f docker-compose.app.yml up -d --build
```

## Project Structure

```text
ontology-intelligence/
├── ontology_intelligence/     # Python package
│   ├── config.py              # Centralized settings
│   ├── sync/                  # Synchronization engine
│   ├── agent/                 # Agent and LLM factory
│   ├── plugins/               # Pluggable tools
│   └── web/                   # FastAPI backend
├── frontend/                  # React frontend
├── docs/                      # Publishing, operations, and project docs
├── scripts/                   # Operations scripts
├── database_mapping.yaml      # Mapping configuration
├── docker-compose.yml         # Infrastructure compose file
├── docker-compose.app.yml     # Application compose file
├── Dockerfile                 # Container build
├── Makefile                   # Development commands
└── requirements.txt           # Python dependencies
```

## LLM Configuration

Configure the LLM backend in `.env`:

| Provider | LLM_PROVIDER | Notes |
|----------|--------------|-------|
| OpenAI | `openai` | OpenAI API |
| OpenRouter | `openrouter` | OpenRouter-compatible endpoint |
| Qwen | `qwen` | DashScope / OpenAI-compatible endpoint |
| DeepSeek | `deepseek` | DeepSeek-compatible endpoint |
| Ollama | `ollama` | Local Ollama service |
| Custom | `openai` | Any OpenAI-compatible API |

## Contributing And Roadmap

- [Contributing Guide](CONTRIBUTING.md)
- [Roadmap](docs/ROADMAP.md)
- [GitHub Publishing Checklist](docs/GITHUB_PUBLISHING.md)

## Security And Privacy

Do not commit `.env`, `.env.*`, `datasources.yaml`, runtime data, local databases, API keys, database passwords, JWT secrets, or user data. See [SECURITY.md](SECURITY.md) and [docs/GITHUB_PUBLISHING.md](docs/GITHUB_PUBLISHING.md) before publishing.

## License

MIT
