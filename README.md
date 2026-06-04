# 企业级本体智能体 (Ontology Intelligence)

基于知识图谱的企业级智能运维分析平台。将 MySQL 关系型数据通过本体映射同步至 Neo4j 图数据库，结合大语言模型（支持 OpenAI / LLM / Qwen / Ollama 等）实现自然语言驱动的智能查询和故障排查。

## 🏗️ 架构

```
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

## ✨ 核心功能

- **本体驱动的数据同步**：基于 YAML 映射配置，自动将 MySQL 数据同步为 Neo4j 知识图谱
- **多模型 LLM 支持**：统一 OpenAI 兼容 API，支持 OpenAI / LLM / OpenRouter / Qwen / Ollama 等
- **智能体对话**：自然语言查询知识图谱，支持复杂推理和工单语义搜索
- **数据工作台**：本体文件上传、多数据源管理、数据映射编辑、一致性校验
- **图谱可视化**：力导向图谱浏览，支持节点信息/关系注释/本体约束开关
- **实时同步**：通过 Kafka/Debezium 实现 CDC 增量数据同步

## 🚀 快速开始

### 开发环境（macOS / Linux）

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际配置

# 4. 启动
make dev
# 或分别启动：
#   make dev-backend    # 后端 http://localhost:8888
#   make dev-frontend   # 前端 http://localhost:3000
```

### Docker 部署（Linux 服务器）

```bash
# 一键部署
bash scripts/deploy.sh
```

或手动：

```bash
# 1. 启动基础设施（Neo4j, Kafka 等）
docker compose up -d

# 2. 启动应用（后端 + 前端）
docker compose -f docker-compose.app.yml up -d --build

# 前端: http://your-server:3000
# 后端: http://your-server:8888
```

## 📁 项目结构

```
ontology-intelligence/
├── ontology_intelligence/     # Python 主包
│   ├── config.py              # 统一配置管理
│   ├── sync/                  # 同步引擎
│   │   ├── engine.py          # 全量同步
│   │   ├── kafka_consumer.py  # CDC 增量同步
│   │   └── verify.py          # 数据校验
│   ├── agent/                 # 智能体
│   │   ├── core.py            # Agent 主逻辑
│   │   └── llm_factory.py     # LLM 多模型工厂
│   ├── plugins/               # 可插拔工具
│   └── web/                   # Web 后端
│       ├── app.py             # FastAPI 入口
│       ├── models.py          # 数据模型
│       └── routes/            # 路由模块
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

## ⚙️ LLM 配置

在 `.env` 中配置 LLM 后端：

| Provider | LLM_PROVIDER | LLM_BASE_URL | 说明 |
|----------|-------------|--------------|------|
| OpenAI | `openai` | (默认) | api.openai.com |
| LLM | `LLM` | (默认) | OpenAI 兼容端点 |
| OpenRouter | `openrouter` | (默认) | openrouter.ai |
| 通义千问 | `qwen` | (默认) | dashscope |
| DeepSeek | `deepseek` | (默认) | api.deepseek.com |
| Ollama | `ollama` | (默认) | 本地 11434 端口 |
| 自定义 | `openai` | 你的端点 URL | 任何兼容 API |

## 🖥️ 部署要求

### 最低配置
- **CPU**: 4 vCPU
- **内存**: 16 GB RAM
- **磁盘**: 100 GB SSD
- **OS**: Docker 部署支持任意 Linux（包括 CentOS 7.6）

### 软件依赖
- Docker 20.10+
- Docker Compose v2+
- Python 3.10+（本地开发）
- Node.js 18+（本地开发）

## ✅ 内网上线最小检查清单

上线前按顺序完成以下检查：

1. 将 `.env` 中 `APP_ENV=production`，并设置强随机 `JWT_SECRET`、非占位 `NEO4J_PASSWORD`，生产环境优先使用 `ADMIN_PASSWORD_HASH`。
2. 设置 `CORS_ORIGINS` 为实际前端访问地址，例如 `http://内网IP:3001`，不要使用通配来源。
3. 启动基础设施：`make docker-up`，确认 Neo4j/Kafka 服务健康；应用容器通过 `ontology-intelligence-net` 网络访问基础设施。
4. 启动应用：`make docker-app`，访问 `/healthz` 和前端登录页。
5. 运行验证：`make test`、`cd frontend && npm run build`；外部服务可用时再运行 `make sync` 和 `make verify`。
6. 用管理员账号完成一次场景创建、本体/映射配置、同步、Agent 初始化、问答、评分和审计查看。

## 📜 License

MIT
